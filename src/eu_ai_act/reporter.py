"""
Report Generator

Generates compliance reports in multiple formats (JSON, HTML, Markdown, PDF).
Creates audit-ready documentation of AI system assessments.
"""

import html
import json
from datetime import UTC, datetime
from typing import Any, cast

from eu_ai_act.checker import ComplianceFinding, ComplianceReport
from eu_ai_act.checklist import ChecklistItem, ComplianceChecklist
from eu_ai_act.classifier import RiskClassification
from eu_ai_act.gpai import GPAIAssessment
from eu_ai_act.security_mapping import SecurityMapper
from eu_ai_act.schema import AISystemDescriptor
from eu_ai_act.transparency import TransparencyFinding


class ReportGenerator:
    """
    Generates compliance reports in multiple formats.

    Supports JSON, HTML, Markdown, and PDF output for audit documentation.
    """

    def __init__(self) -> None:
        """Initialize report generator dependencies."""
        self.security_mapper = SecurityMapper()

    def generate_report(
        self,
        descriptor: AISystemDescriptor,
        classification: RiskClassification,
        compliance_report: ComplianceReport | None = None,
        transparency_findings: list[TransparencyFinding] | None = None,
        gpai_assessment: GPAIAssessment | None = None,
        checklist: ComplianceChecklist | None = None,
        format: str = "json",
    ) -> str:
        """Generate a report using a shared payload and format-specific renderers."""
        payload = self._build_payload(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings or [],
            gpai_assessment=gpai_assessment,
            checklist=checklist,
        )

        if format == "json":
            return json.dumps(payload, indent=2)
        if format == "md":
            return self._render_markdown(payload)
        if format == "html":
            return self._render_html(payload)
        raise ValueError(f"Unsupported report format: {format}")

    def generate_json_report(
        self,
        descriptor: AISystemDescriptor,
        classification: RiskClassification,
        compliance_report: ComplianceReport | None = None,
        transparency_findings: list[TransparencyFinding] | None = None,
        gpai_assessment: GPAIAssessment | None = None,
        checklist: ComplianceChecklist | None = None,
    ) -> str:
        """Backward-compatible wrapper for JSON report generation."""
        return self.generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
            format="json",
        )

    def generate_markdown_report(
        self,
        descriptor: AISystemDescriptor,
        classification: RiskClassification,
        compliance_report: ComplianceReport | None = None,
        transparency_findings: list[TransparencyFinding] | None = None,
        gpai_assessment: GPAIAssessment | None = None,
        checklist: ComplianceChecklist | None = None,
    ) -> str:
        """Backward-compatible wrapper for Markdown report generation."""
        return self.generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
            format="md",
        )

    def generate_html_report(
        self,
        descriptor: AISystemDescriptor,
        classification: RiskClassification,
        compliance_report: ComplianceReport | None = None,
        transparency_findings: list[TransparencyFinding] | None = None,
        gpai_assessment: GPAIAssessment | None = None,
        checklist: ComplianceChecklist | None = None,
    ) -> str:
        """Backward-compatible wrapper for HTML report generation."""
        return self.generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
            format="html",
        )

    def generate_pdf_report(
        self,
        descriptor: AISystemDescriptor,
        classification: RiskClassification,
        compliance_report: ComplianceReport | None = None,
        transparency_findings: list[TransparencyFinding] | None = None,
        gpai_assessment: GPAIAssessment | None = None,
        checklist: ComplianceChecklist | None = None,
    ) -> bytes:
        """
        Generate PDF bytes.
        """
        try:
            from weasyprint import HTML
        except Exception as exc:
            raise RuntimeError(
                "PDF generation requires optional dependency 'weasyprint'. "
                'Install reporting extras with: pip install -e ".[reporting]"'
            ) from exc

        html_report = self.generate_html_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist,
        )
        try:
            pdf_bytes = HTML(string=html_report).write_pdf()
            return cast(bytes, pdf_bytes)
        except Exception as exc:
            raise RuntimeError(
                "Failed to generate PDF with WeasyPrint. Ensure WeasyPrint system dependencies "
                "are installed and retry."
            ) from exc

    def _build_payload(
        self,
        descriptor: AISystemDescriptor,
        classification: RiskClassification,
        compliance_report: ComplianceReport | None,
        transparency_findings: list[TransparencyFinding],
        gpai_assessment: GPAIAssessment | None,
        checklist: ComplianceChecklist | None,
    ) -> dict[str, Any]:
        """Build shared report payload for all renderers."""
        generated_at = self._utc_timestamp()

        if compliance_report is None:
            compliance_summary = {
                "total_requirements": 0,
                "compliant_count": 0,
                "non_compliant_count": 0,
                "partial_count": 0,
                "not_assessed_count": 0,
                "compliance_percentage": 0.0,
            }
            compliance_findings: dict[str, dict[str, Any]] = {}
            audit_trail: list[str] = []
            security_mapping_payload: dict[str, Any] = {
                "framework": SecurityMapper.FRAMEWORK,
                "generated_at": generated_at,
                "summary": {
                    "total_controls": 0,
                    "compliant_count": 0,
                    "non_compliant_count": 0,
                    "partial_count": 0,
                    "not_assessed_count": 0,
                    "coverage_percentage": 0.0,
                },
                "controls": [],
            }
        else:
            compliance_summary = {
                "total_requirements": compliance_report.summary.total_requirements,
                "compliant_count": compliance_report.summary.compliant_count,
                "non_compliant_count": compliance_report.summary.non_compliant_count,
                "partial_count": compliance_report.summary.partial_count,
                "not_assessed_count": compliance_report.summary.not_assessed_count,
                "compliance_percentage": round(compliance_report.summary.compliance_percentage, 2),
            }
            compliance_findings = {
                finding_id: self._serialize_compliance_finding(finding)
                for finding_id, finding in compliance_report.findings.items()
            }
            audit_trail = compliance_report.audit_trail
            security_mapping_payload = self.security_mapper.map_from_compliance(
                compliance_report
            ).to_dict()

        transparency_payload = [
            self._serialize_transparency_finding(finding) for finding in transparency_findings
        ]

        if gpai_assessment is None:
            gpai_payload: dict[str, Any] = {
                "systemic_risk_flag": False,
                "compliance_gaps": [],
                "recommendations": [],
                "findings": [],
            }
        else:
            gpai_payload = {
                "systemic_risk_flag": gpai_assessment.systemic_risk_flag,
                "compliance_gaps": gpai_assessment.compliance_gaps,
                "recommendations": gpai_assessment.recommendations,
                "findings": [
                    self._serialize_gpai_finding(finding) for finding in gpai_assessment.findings
                ],
            }

        recommended_actions = (
            [self._serialize_checklist_item(item) for item in checklist.items] if checklist else []
        )

        return {
            "system_name": descriptor.name,
            "version": descriptor.version,
            "generated_at": generated_at,
            "risk_tier": classification.tier.value,
            "confidence": classification.confidence,
            "reasoning": classification.reasoning,
            "articles_applicable": classification.articles_applicable,
            "status": "report_generated",
            "compliance_summary": compliance_summary,
            "compliance_findings": compliance_findings,
            "transparency_findings": transparency_payload,
            "gpai_assessment": gpai_payload,
            "security_mapping": security_mapping_payload,
            "audit_trail": audit_trail,
            "recommended_actions": recommended_actions,
            "recommended_action_count": len(recommended_actions),
        }

    def _render_markdown(self, payload: dict[str, Any]) -> str:
        """Render report payload as Markdown."""
        lines = [
            f"# Compliance Report: {payload['system_name']}",
            "",
            f"**Version:** {payload['version']}",
            f"**Risk Tier:** {payload['risk_tier'].upper()}",
            f"**Confidence:** {payload['confidence']:.0%}",
            f"**Report Generated:** {payload['generated_at']}",
            "",
            "## Executive Summary",
            payload["reasoning"],
            "",
            "## Compliance Summary",
            f"- Total Requirements: {payload['compliance_summary']['total_requirements']}",
            f"- Compliant: {payload['compliance_summary']['compliant_count']}",
            f"- Non-compliant: {payload['compliance_summary']['non_compliant_count']}",
            f"- Partial: {payload['compliance_summary']['partial_count']}",
            f"- Not Assessed: {payload['compliance_summary']['not_assessed_count']}",
            f"- Compliance Percentage: {payload['compliance_summary']['compliance_percentage']:.2f}",
            "",
            "## Compliance Findings",
        ]

        if payload["compliance_findings"]:
            for requirement_id, finding in payload["compliance_findings"].items():
                lines.append(
                    f"- [{finding['status']}] {requirement_id}: {finding['title']} "
                    f"(severity: {finding['severity']})"
                )
                if finding["gap_analysis"]:
                    lines.append(f"  Gap: {finding['gap_analysis']}")
        else:
            lines.append("- No compliance findings generated.")

        lines.extend(
            [
                "",
                "## Security Mapping (OWASP LLM Top 10)",
                f"- Total Controls: {payload['security_mapping']['summary']['total_controls']}",
                f"- Compliant: {payload['security_mapping']['summary']['compliant_count']}",
                f"- Non-compliant: {payload['security_mapping']['summary']['non_compliant_count']}",
                f"- Partial: {payload['security_mapping']['summary']['partial_count']}",
                f"- Not Assessed: {payload['security_mapping']['summary']['not_assessed_count']}",
                (
                    "- Coverage Percentage: "
                    f"{payload['security_mapping']['summary']['coverage_percentage']:.2f}"
                ),
            ]
        )
        if payload["security_mapping"]["controls"]:
            for control in payload["security_mapping"]["controls"]:
                lines.append(
                    f"- [{control['status']}] {control['control_id']}: {control['title']} "
                    f"(severity: {control['severity']})"
                )
                if control["gap_analysis"]:
                    lines.append(f"  Gap: {control['gap_analysis']}")
        else:
            lines.append("- No security mapping controls generated.")

        lines.extend(["", "## Transparency Findings"])
        if payload["transparency_findings"]:
            for finding in payload["transparency_findings"]:
                lines.append(
                    f"- [{finding['status']}] {finding['requirement_id']}: {finding['title']} "
                    f"(severity: {finding['severity']})"
                )
                if finding["gap_analysis"]:
                    lines.append(f"  Gap: {finding['gap_analysis']}")
        else:
            lines.append("- No transparency findings generated.")

        lines.extend(
            [
                "",
                "## GPAI Assessment",
                f"- Systemic Risk Flag: {'YES' if payload['gpai_assessment']['systemic_risk_flag'] else 'NO'}",
                f"- Compliance Gaps: {len(payload['gpai_assessment']['compliance_gaps'])}",
            ]
        )
        if payload["gpai_assessment"]["compliance_gaps"]:
            for gap in payload["gpai_assessment"]["compliance_gaps"]:
                lines.append(f"- {gap}")
        else:
            lines.append("- No GPAI compliance gaps detected.")

        lines.extend(["", "## Recommended Actions"])
        if payload["recommended_actions"]:
            for action in payload["recommended_actions"]:
                lines.append(
                    f"- {action['id']}: {action['title']} ({action['article']}, "
                    f"{action['severity']}, {action['status']}, {action['deadline_months']} months)"
                )
                if action["gap_analysis"]:
                    lines.append(f"  Gap: {action['gap_analysis']}")
                lines.append(f"  Guidance: {action['guidance']}")
                lines.append(f"  Success Criteria: {action['success_criteria']}")
        else:
            lines.append("- No actionable items identified.")

        lines.extend(["", "## Audit Trail"])
        if payload["audit_trail"]:
            for step in payload["audit_trail"]:
                lines.append(f"- {step}")
        else:
            lines.append("- No audit trail entries available.")

        lines.extend(
            ["", "---", "Report generated from compliance, transparency, and GPAI signals."]
        )
        return "\n".join(lines)

    def _render_html(self, payload: dict[str, Any]) -> str:
        """Render report payload as HTML."""
        tier_color = {
            "unacceptable": "#dc2626",
            "high_risk": "#ea580c",
            "limited": "#ca8a04",
            "minimal": "#16a34a",
        }.get(payload["risk_tier"], "#4b5563")

        compliance_rows = self._build_compliance_rows(payload)
        security_rows = self._build_security_rows(payload)
        transparency_rows = self._build_transparency_rows(payload)
        gpai_gap_rows = self._build_simple_list(
            payload["gpai_assessment"]["compliance_gaps"], "No GPAI compliance gaps detected."
        )
        action_rows = self._build_action_rows(payload)
        audit_rows = self._build_simple_list(
            payload["audit_trail"], "No audit trail entries available."
        )

        return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Compliance Report: {html.escape(payload['system_name'])}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f3f4f6; color: #111827; }}
        .container {{ max-width: 980px; margin: 0 auto; background: #ffffff; padding: 28px; border-radius: 8px; }}
        h1 {{ margin-top: 0; }}
        h2 {{ margin-top: 28px; border-bottom: 1px solid #d1d5db; padding-bottom: 6px; }}
        .risk-tier {{ background: {tier_color}; color: white; padding: 12px; border-radius: 6px; font-weight: bold; margin: 12px 0 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; vertical-align: top; }}
        th {{ background: #f9fafb; }}
        ul {{ padding-left: 20px; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class=\"container\">
        <h1>Compliance Report: {html.escape(payload['system_name'])}</h1>
        <p><strong>Version:</strong> {html.escape(payload['version'])}</p>
        <p><strong>Report Generated:</strong> {html.escape(payload['generated_at'])}</p>
        <div class=\"risk-tier\">{html.escape(payload['risk_tier'].upper())} ({payload['confidence']:.0%} confidence)</div>

        <h2>Executive Summary</h2>
        <p>{html.escape(payload['reasoning'])}</p>

        <h2>Compliance Summary</h2>
        <ul>
            <li>Total Requirements: {payload['compliance_summary']['total_requirements']}</li>
            <li>Compliant: {payload['compliance_summary']['compliant_count']}</li>
            <li>Non-compliant: {payload['compliance_summary']['non_compliant_count']}</li>
            <li>Partial: {payload['compliance_summary']['partial_count']}</li>
            <li>Not Assessed: {payload['compliance_summary']['not_assessed_count']}</li>
            <li>Compliance Percentage: {payload['compliance_summary']['compliance_percentage']:.2f}</li>
        </ul>

        <h2>Compliance Findings</h2>
        {compliance_rows}

        <h2>Security Mapping (OWASP LLM Top 10)</h2>
        <ul>
            <li>Total Controls: {payload['security_mapping']['summary']['total_controls']}</li>
            <li>Compliant: {payload['security_mapping']['summary']['compliant_count']}</li>
            <li>Non-compliant: {payload['security_mapping']['summary']['non_compliant_count']}</li>
            <li>Partial: {payload['security_mapping']['summary']['partial_count']}</li>
            <li>Not Assessed: {payload['security_mapping']['summary']['not_assessed_count']}</li>
            <li>Coverage Percentage: {payload['security_mapping']['summary']['coverage_percentage']:.2f}</li>
        </ul>
        {security_rows}

        <h2>Transparency Findings</h2>
        {transparency_rows}

        <h2>GPAI Assessment</h2>
        <p><strong>Systemic Risk Flag:</strong> {"YES" if payload['gpai_assessment']['systemic_risk_flag'] else "NO"}</p>
        <p><strong>Compliance Gaps:</strong> {len(payload['gpai_assessment']['compliance_gaps'])}</p>
        {gpai_gap_rows}

        <h2>Recommended Actions</h2>
        {action_rows}

        <h2>Audit Trail</h2>
        {audit_rows}
    </div>
</body>
</html>
"""

    def _build_compliance_rows(self, payload: dict[str, Any]) -> str:
        """Build HTML block for compliance findings."""
        if not payload["compliance_findings"]:
            return "<p>No compliance findings generated.</p>"

        rows = []
        for requirement_id, finding in payload["compliance_findings"].items():
            rows.append(
                "<tr>"
                f"<td>{html.escape(requirement_id)}</td>"
                f"<td>{html.escape(finding['title'])}</td>"
                f"<td>{html.escape(finding['status'])}</td>"
                f"<td>{html.escape(finding['severity'])}</td>"
                f"<td>{html.escape(finding['gap_analysis'] or '-')}</td>"
                "</tr>"
            )

        return (
            "<table><thead><tr>"
            "<th>Requirement</th><th>Title</th><th>Status</th><th>Severity</th><th>Gap</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )

    def _build_security_rows(self, payload: dict[str, Any]) -> str:
        """Build HTML block for OWASP security controls."""
        controls = payload["security_mapping"]["controls"]
        if not controls:
            return "<p>No security mapping controls generated.</p>"

        rows = []
        for control in controls:
            rows.append(
                "<tr>"
                f"<td>{html.escape(control['control_id'])}</td>"
                f"<td>{html.escape(control['title'])}</td>"
                f"<td>{html.escape(control['status'])}</td>"
                f"<td>{html.escape(control['severity'])}</td>"
                f"<td>{html.escape(control['gap_analysis'] or '-')}</td>"
                "</tr>"
            )

        return (
            "<table><thead><tr>"
            "<th>Control</th><th>Title</th><th>Status</th><th>Severity</th><th>Gap</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )

    def _build_transparency_rows(self, payload: dict[str, Any]) -> str:
        """Build HTML block for transparency findings."""
        findings = payload["transparency_findings"]
        if not findings:
            return "<p>No transparency findings generated.</p>"

        rows = []
        for finding in findings:
            rows.append(
                "<tr>"
                f"<td>{html.escape(finding['requirement_id'])}</td>"
                f"<td>{html.escape(finding['title'])}</td>"
                f"<td>{html.escape(finding['status'])}</td>"
                f"<td>{html.escape(finding['severity'])}</td>"
                f"<td>{html.escape(finding['gap_analysis'] or '-')}</td>"
                "</tr>"
            )

        return (
            "<table><thead><tr>"
            "<th>Requirement</th><th>Title</th><th>Status</th><th>Severity</th><th>Gap</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )

    def _build_action_rows(self, payload: dict[str, Any]) -> str:
        """Build HTML block for checklist-driven recommended actions."""
        actions = payload["recommended_actions"]
        if not actions:
            return "<p>No actionable items identified.</p>"

        rows = []
        for action in actions:
            rows.append(
                "<tr>"
                f"<td>{html.escape(action['id'])}</td>"
                f"<td>{html.escape(action['title'])}</td>"
                f"<td>{html.escape(action['article'])}</td>"
                f"<td>{html.escape(action['severity'])}</td>"
                f"<td>{html.escape(action['status'])}</td>"
                f"<td>{action['deadline_months']}</td>"
                f"<td>{html.escape(action['gap_analysis'] or '-')}</td>"
                f"<td>{html.escape(action['guidance'])}</td>"
                f"<td>{html.escape(action['success_criteria'])}</td>"
                "</tr>"
            )

        return (
            "<table><thead><tr>"
            "<th>ID</th><th>Title</th><th>Article</th><th>Severity</th><th>Status</th>"
            "<th>Deadline (months)</th><th>Gap</th><th>Guidance</th><th>Success Criteria</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )

    def _build_simple_list(self, values: list[str], empty_message: str) -> str:
        """Render list values as HTML or return a fallback message."""
        if not values:
            return f"<p>{html.escape(empty_message)}</p>"
        items = "".join(f"<li>{html.escape(value)}</li>" for value in values)
        return f"<ul>{items}</ul>"

    def _serialize_compliance_finding(self, finding: ComplianceFinding) -> dict[str, Any]:
        """Serialize compliance finding payload."""
        return {
            "title": finding.requirement_title,
            "status": finding.status.value,
            "description": finding.description,
            "gap_analysis": finding.gap_analysis,
            "remediation_steps": finding.remediation_steps,
            "severity": finding.severity,
        }

    def _serialize_transparency_finding(self, finding: TransparencyFinding) -> dict[str, Any]:
        """Serialize transparency finding payload."""
        return {
            "requirement_id": finding.requirement_id,
            "status": finding.status.value,
            "severity": finding.severity,
            "title": finding.title,
            "description": finding.description,
            "gap_analysis": finding.gap_analysis,
            "recommendations": finding.recommendations,
        }

    def _serialize_gpai_finding(self, finding) -> dict[str, Any]:
        """Serialize GPAI finding payload."""
        return {
            "requirement_id": finding.requirement_id,
            "status": finding.status.value,
            "severity": finding.severity,
            "title": finding.title,
            "description": finding.description,
            "gap_analysis": finding.gap_analysis,
            "recommendations": finding.recommendations,
        }

    def _serialize_checklist_item(self, item: ChecklistItem) -> dict[str, Any]:
        """Serialize checklist action for report payload."""
        return {
            "id": item.id,
            "title": item.title,
            "article": item.article,
            "severity": item.severity,
            "status": item.status,
            "deadline_months": item.deadline_months,
            "guidance": item.guidance,
            "success_criteria": item.success_criteria,
            "gap_analysis": item.gap_analysis,
        }

    def _utc_timestamp(self) -> str:
        """Return ISO-8601 UTC timestamp."""
        return datetime.now(UTC).isoformat(timespec="seconds")
