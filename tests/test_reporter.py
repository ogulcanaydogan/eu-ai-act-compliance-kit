"""Tests for centralized report generation."""

import builtins
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.checklist import ChecklistGenerator
from eu_ai_act.classifier import RiskClassifier
from eu_ai_act.cli import _build_gpai_model_info_from_descriptor, _collect_transparency_findings
from eu_ai_act.gpai import GPAIAssessor
from eu_ai_act.reporter import ReportGenerator
from eu_ai_act.schema import load_system_descriptor_from_file
from eu_ai_act.transparency import TransparencyChecker

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


def _build_report_inputs(system_yaml: Path):
    descriptor = load_system_descriptor_from_file(str(system_yaml))
    classifier = RiskClassifier()
    checker = ComplianceChecker()
    checklist_generator = ChecklistGenerator()
    transparency_checker = TransparencyChecker()
    gpai_assessor = GPAIAssessor()

    classification = classifier.classify(descriptor)
    compliance_report = checker.check(descriptor)
    transparency_findings = _collect_transparency_findings(transparency_checker, descriptor)
    gpai_assessment = gpai_assessor.assess(_build_gpai_model_info_from_descriptor(descriptor))
    checklist = checklist_generator.generate(
        descriptor=descriptor,
        tier=compliance_report.risk_tier,
        findings=compliance_report.findings,
        generated_at=compliance_report.generated_at,
    )

    return (
        descriptor,
        classification,
        compliance_report,
        transparency_findings,
        gpai_assessment,
        checklist,
    )


class TestReportGenerator:
    """Coverage for centralized report payload and renderers."""

    def test_json_keeps_existing_fields_and_adds_extended_fields(self):
        """JSON report should preserve prior top-level keys and add new detail fields."""
        (
            descriptor,
            classification,
            compliance_report,
            transparency_findings,
            gpai_assessment,
            checklist,
        ) = _build_report_inputs(EXAMPLES_DIR / "medical_diagnosis.yaml")

        result = ReportGenerator().generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
            format="json",
        )
        payload = json.loads(result)

        for key in [
            "system_name",
            "version",
            "generated_at",
            "risk_tier",
            "confidence",
            "reasoning",
            "articles_applicable",
            "status",
            "compliance_summary",
            "transparency_findings",
            "gpai_assessment",
        ]:
            assert key in payload

        for key in [
            "compliance_findings",
            "security_mapping",
            "audit_trail",
            "recommended_actions",
            "recommended_action_count",
        ]:
            assert key in payload

        assert payload["recommended_action_count"] == len(payload["recommended_actions"])

    def test_recommended_actions_come_from_checklist_items(self):
        """Recommended actions should map one-to-one from generated checklist items."""
        (
            descriptor,
            classification,
            compliance_report,
            transparency_findings,
            gpai_assessment,
            checklist,
        ) = _build_report_inputs(EXAMPLES_DIR / "medical_diagnosis.yaml")

        payload = json.loads(
            ReportGenerator().generate_report(
                descriptor=descriptor,
                classification=classification,
                compliance_report=compliance_report,
                transparency_findings=transparency_findings,
                gpai_assessment=gpai_assessment,
                checklist=checklist,
                format="json",
            )
        )

        report_action_ids = {item["id"] for item in payload["recommended_actions"]}
        checklist_ids = {item.id for item in checklist.items}
        assert report_action_ids == checklist_ids

        required_fields = {
            "id",
            "title",
            "article",
            "severity",
            "status",
            "deadline_months",
            "guidance",
            "success_criteria",
            "gap_analysis",
        }
        for action in payload["recommended_actions"]:
            assert required_fields <= set(action.keys())

    def test_json_includes_audit_trail_and_compliance_findings(self):
        """Report should include checker audit trail and finding payload."""
        (
            descriptor,
            classification,
            compliance_report,
            transparency_findings,
            gpai_assessment,
            checklist,
        ) = _build_report_inputs(EXAMPLES_DIR / "medical_diagnosis.yaml")

        payload = json.loads(
            ReportGenerator().generate_report(
                descriptor=descriptor,
                classification=classification,
                compliance_report=compliance_report,
                transparency_findings=transparency_findings,
                gpai_assessment=gpai_assessment,
                checklist=checklist,
                format="json",
            )
        )

        assert payload["audit_trail"] == compliance_report.audit_trail
        assert "Art. 43" in payload["compliance_findings"]
        assert payload["compliance_findings"]["Art. 43"]["status"] in {
            "partial",
            "non_compliant",
            "not_assessed",
        }

    def test_markdown_and_html_include_required_sections(self):
        """Markdown/HTML output should expose standardized section headers."""
        (
            descriptor,
            classification,
            compliance_report,
            transparency_findings,
            gpai_assessment,
            checklist,
        ) = _build_report_inputs(EXAMPLES_DIR / "chatbot.yaml")

        generator = ReportGenerator()
        markdown = generator.generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
            format="md",
        )
        html = generator.generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
            format="html",
        )

        for section in [
            "## Executive Summary",
            "## Compliance Summary",
            "## Compliance Findings",
            "## Security Mapping (OWASP LLM Top 10)",
            "## Transparency Findings",
            "## GPAI Assessment",
            "## Recommended Actions",
            "## Audit Trail",
        ]:
            assert section in markdown

        assert "No actionable items identified." in markdown

        for section in [
            "Executive Summary",
            "Compliance Summary",
            "Compliance Findings",
            "Security Mapping (OWASP LLM Top 10)",
            "Transparency Findings",
            "GPAI Assessment",
            "Recommended Actions",
            "Audit Trail",
        ]:
            assert section in html

    def test_pdf_generation_uses_weasyprint_engine(self, monkeypatch):
        """PDF generation should route through WeasyPrint and return bytes."""
        (
            descriptor,
            classification,
            compliance_report,
            transparency_findings,
            gpai_assessment,
            checklist,
        ) = _build_report_inputs(EXAMPLES_DIR / "medical_diagnosis.yaml")

        class FakeHTML:
            def __init__(self, string: str):
                assert "Compliance Report" in string
                self._string = string

            def write_pdf(self) -> bytes:
                return b"%PDF-1.7\nfake-pdf-bytes"

        monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))

        pdf_bytes = ReportGenerator().generate_pdf_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
        )
        assert pdf_bytes.startswith(b"%PDF-1.7")

    def test_pdf_generation_missing_dependency_raises_clear_error(self, monkeypatch):
        """Missing WeasyPrint should return a deterministic installation hint."""
        (
            descriptor,
            classification,
            compliance_report,
            transparency_findings,
            gpai_assessment,
            checklist,
        ) = _build_report_inputs(EXAMPLES_DIR / "medical_diagnosis.yaml")

        real_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "weasyprint":
                raise ImportError("No module named weasyprint")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _fake_import)

        with pytest.raises(RuntimeError) as exc_info:
            ReportGenerator().generate_pdf_report(
                descriptor=descriptor,
                classification=classification,
                compliance_report=compliance_report,
                transparency_findings=transparency_findings,
                gpai_assessment=gpai_assessment,
                checklist=checklist,
            )
        message = str(exc_info.value)
        assert "weasyprint" in message.lower()
        assert 'pip install -e ".[reporting]"' in message
