"""Unit tests for OWASP LLM Top 10 security mapping runtime."""

from eu_ai_act.checker import (
    ComplianceFinding,
    ComplianceReport,
    ComplianceStatus,
    ComplianceSummary,
)
from eu_ai_act.schema import RiskTier
from eu_ai_act.security_mapping import SecurityMapper


def _finding(
    requirement_id: str,
    status: ComplianceStatus,
    *,
    gap: str = "",
    steps: list[str] | None = None,
) -> ComplianceFinding:
    return ComplianceFinding(
        requirement_id=requirement_id,
        requirement_title=f"{requirement_id} title",
        status=status,
        description=f"{requirement_id} description",
        gap_analysis=gap,
        remediation_steps=steps or [],
        severity="HIGH",
    )


def _report(findings: dict[str, ComplianceFinding]) -> ComplianceReport:
    summary = ComplianceSummary(
        total_requirements=len(findings),
        compliant_count=sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.COMPLIANT
        ),
        non_compliant_count=sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.NON_COMPLIANT
        ),
        partial_count=sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.PARTIAL
        ),
        not_assessed_count=sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.NOT_ASSESSED
        ),
    )
    return ComplianceReport(
        system_name="test-system",
        risk_tier=RiskTier.HIGH_RISK,
        findings=findings,
        summary=summary,
        audit_trail=[],
        generated_at="2026-03-23T00:00:00+00:00",
    )


class TestSecurityMapper:
    """Status derivation and summary coverage for OWASP control mapping."""

    def test_mapping_derives_deterministic_statuses_and_summary(self):
        mapper = SecurityMapper()
        report = _report(
            {
                "Art. 5": _finding("Art. 5", ComplianceStatus.COMPLIANT),
                "Art. 10": _finding(
                    "Art. 10",
                    ComplianceStatus.NON_COMPLIANT,
                    gap="Data governance controls missing.",
                    steps=["Document data provenance and quality controls."],
                ),
                "Art. 11": _finding("Art. 11", ComplianceStatus.COMPLIANT),
                "Art. 13": _finding(
                    "Art. 13",
                    ComplianceStatus.PARTIAL,
                    gap="Transparency guidance is incomplete.",
                    steps=["Expand user-facing transparency notices."],
                ),
                "Art. 14": _finding(
                    "Art. 14",
                    ComplianceStatus.NOT_ASSESSED,
                    gap="Human oversight evidence unavailable.",
                    steps=["Provide oversight operating procedures."],
                ),
                "Art. 15": _finding("Art. 15", ComplianceStatus.COMPLIANT),
                "Art. 43": _finding("Art. 43", ComplianceStatus.COMPLIANT),
                "Art. 50": _finding("Art. 50", ComplianceStatus.COMPLIANT),
            }
        )

        result = mapper.map_from_compliance(report)
        controls = {control.control_id: control for control in result.controls}

        assert [control.control_id for control in result.controls][0] == "LLM01"
        assert [control.control_id for control in result.controls][-1] == "LLM10"

        assert controls["LLM03"].status == ComplianceStatus.NON_COMPLIANT
        assert controls["LLM09"].status == ComplianceStatus.PARTIAL
        assert controls["LLM04"].status == ComplianceStatus.COMPLIANT
        assert controls["LLM08"].status == ComplianceStatus.NOT_ASSESSED

        summary = result.summary
        assert summary.total_controls == 10
        assert summary.compliant_count == 3
        assert summary.non_compliant_count == 2
        assert summary.partial_count == 3
        assert summary.not_assessed_count == 2
        assert summary.coverage_percentage == 80.0

    def test_mapping_without_linked_findings_defaults_to_not_assessed(self):
        mapper = SecurityMapper()
        result = mapper.map_from_compliance(_report({}))

        assert len(result.controls) == 10
        assert all(control.status == ComplianceStatus.NOT_ASSESSED for control in result.controls)
        assert result.summary.total_controls == 10
        assert result.summary.not_assessed_count == 10
        assert result.summary.coverage_percentage == 0.0
