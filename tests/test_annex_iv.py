"""Tests for Annex IV technical documentation coverage checker."""

from pathlib import Path

from eu_ai_act.annexes.annex_iv import (
    AnnexIVSection,
    annex_iv_coverage_summary,
    check_annex_iv_completeness,
)
from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.classifier import RiskClassifier
from eu_ai_act.reporter import ReportGenerator
from eu_ai_act.schema import load_system_descriptor_from_file

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


def _full_doc() -> dict:
    return {
        "intended_purpose": "Fraud detection in online payments",
        "version": "1.0.0",
        "hardware_requirements": "x86-64, 16 GB RAM",
        "architecture": "Gradient-boosted trees + rule layer",
        "training_data": "Internal transaction logs 2020-2024",
        "design_choices": "Threshold calibrated for 1% FPR",
        "monitoring_plan": "Monthly drift report via Evidently",
        "performance_metrics": "AUC-ROC 0.95, F1 0.88",
        "robustness_measures": "Adversarial feature perturbation tests",
        "dataset_provenance": "Internal, GDPR Article 6(1)(b) lawful basis",
        "preprocessing_steps": "Normalisation, missing-value imputation",
        "bias_analysis": "Demographic parity gap < 2%",
        "risk_register": "FMEA table, 12 risks identified",
        "residual_risk_evaluation": "3 residual risks accepted by DPO",
        "change_log": "v1.0.1: retrained with Q1-2025 data",
        "post_market_impact_assessments": "Impact reassessment after each release",
        "harmonised_standards": "ISO/IEC 42001:2023",
        "deviation_justifications": "N/A — all requirements met",
        "declaration_of_conformity": "doc/eu-doc-conformity.pdf",
        "conformity_assessment_procedure": "Internal assessment per Art. 43(2)",
    }


def test_full_coverage():
    findings = check_annex_iv_completeness(_full_doc())
    assert all(f.covered for f in findings), [f for f in findings if not f.covered]
    summary = annex_iv_coverage_summary(findings)
    assert summary["coverage_pct"] == 100
    assert summary["critical_missing"] == []


def test_missing_section_detected():
    doc = _full_doc()
    del doc["risk_register"]
    del doc["residual_risk_evaluation"]
    findings = check_annex_iv_completeness(doc)
    risk_finding = next(f for f in findings if f.section == AnnexIVSection.RISK_MANAGEMENT)
    assert not risk_finding.covered
    assert "risk_register" in risk_finding.missing_fields
    assert risk_finding.severity == "CRITICAL"


def test_summary_critical_missing():
    doc = _full_doc()
    del doc["intended_purpose"]
    findings = check_annex_iv_completeness(doc)
    summary = annex_iv_coverage_summary(findings)
    assert AnnexIVSection.GENERAL_DESCRIPTION.value in summary["critical_missing"]
    assert summary["coverage_pct"] < 100


def test_empty_doc_all_missing():
    findings = check_annex_iv_completeness({})
    assert not any(f.covered for f in findings)
    summary = annex_iv_coverage_summary(findings)
    assert summary["coverage_pct"] == 0
    assert len(summary["critical_missing"]) > 0


def test_eight_sections_returned():
    findings = check_annex_iv_completeness(_full_doc())
    assert len(findings) == 8
    section_ids = {f.section for f in findings}
    assert section_ids == set(AnnexIVSection)


# ---------------------------------------------------------------------------
# Reporter integration tests
# ---------------------------------------------------------------------------


def _build_base_reporter_inputs(system_yaml: Path):
    descriptor = load_system_descriptor_from_file(str(system_yaml))
    classifier = RiskClassifier()
    checker = ComplianceChecker()
    classification = classifier.classify(descriptor)
    compliance_report = checker.check(descriptor)
    return descriptor, classification, compliance_report


class TestReporterAnnexIVIntegration:
    """Reporter renders Annex IV section only when annex_iv_findings is supplied."""

    def test_markdown_contains_annex_iv_heading_when_findings_present(self):
        descriptor, classification, compliance_report = _build_base_reporter_inputs(
            EXAMPLES_DIR / "medical_diagnosis.yaml"
        )
        findings = check_annex_iv_completeness(_full_doc())
        result = ReportGenerator().generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            annex_iv_findings=findings,
            format="md",
        )
        assert "## Annex IV" in result
        assert "Coverage:" in result

    def test_markdown_omits_annex_iv_section_when_findings_absent(self):
        descriptor, classification, compliance_report = _build_base_reporter_inputs(
            EXAMPLES_DIR / "medical_diagnosis.yaml"
        )
        result = ReportGenerator().generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            annex_iv_findings=None,
            format="md",
        )
        assert "Annex IV" not in result

    def test_html_contains_annex_iv_heading_when_findings_present(self):
        descriptor, classification, compliance_report = _build_base_reporter_inputs(
            EXAMPLES_DIR / "spam_filter.yaml"
        )
        findings = check_annex_iv_completeness(_full_doc())
        result = ReportGenerator().generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            annex_iv_findings=findings,
            format="html",
        )
        assert "Annex IV" in result
        assert "Technical Documentation Coverage" in result

    def test_markdown_table_rows_match_finding_count(self):
        findings = check_annex_iv_completeness(_full_doc())
        descriptor, classification, compliance_report = _build_base_reporter_inputs(
            EXAMPLES_DIR / "spam_filter.yaml"
        )
        result = ReportGenerator().generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            annex_iv_findings=findings,
            format="md",
        )
        # Each finding produces one Markdown table row starting with "| "
        table_rows = [
            line
            for line in result.splitlines()
            if line.startswith("| ") and "---" not in line and "Section" not in line
        ]
        assert len(table_rows) == len(findings)
