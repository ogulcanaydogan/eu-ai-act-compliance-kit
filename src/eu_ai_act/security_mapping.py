"""
OWASP LLM Top 10 security mapping runtime.

Maps EU AI Act compliance findings to OWASP LLM control status signals using
deterministic, rule-based aggregation.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from eu_ai_act.checker import ComplianceFinding, ComplianceReport, ComplianceStatus


@dataclass(frozen=True)
class SecurityControlDefinition:
    """Static mapping definition for one OWASP LLM control."""

    control_id: str
    title: str
    severity: str
    linked_requirements: tuple[str, ...]
    default_recommendation: str


@dataclass
class SecurityControlResult:
    """Mapped status for one OWASP LLM control."""

    control_id: str
    title: str
    status: ComplianceStatus
    severity: str
    linked_requirements: list[str]
    gap_analysis: str
    recommendations: list[str]

    def to_dict(self) -> dict:
        """Serialize security control result."""
        return {
            "control_id": self.control_id,
            "title": self.title,
            "status": self.status.value,
            "severity": self.severity,
            "linked_requirements": self.linked_requirements,
            "gap_analysis": self.gap_analysis,
            "recommendations": self.recommendations,
        }


@dataclass
class SecurityMappingSummary:
    """Summary statistics for OWASP control mapping output."""

    total_controls: int
    compliant_count: int
    non_compliant_count: int
    partial_count: int
    not_assessed_count: int
    coverage_percentage: float

    def to_dict(self) -> dict:
        """Serialize summary payload."""
        return {
            "total_controls": self.total_controls,
            "compliant_count": self.compliant_count,
            "non_compliant_count": self.non_compliant_count,
            "partial_count": self.partial_count,
            "not_assessed_count": self.not_assessed_count,
            "coverage_percentage": round(self.coverage_percentage, 2),
        }


@dataclass
class SecurityMappingResult:
    """Top-level OWASP LLM mapping result."""

    framework: str
    generated_at: str
    summary: SecurityMappingSummary
    controls: list[SecurityControlResult]

    def to_dict(self) -> dict:
        """Serialize full mapping payload."""
        return {
            "framework": self.framework,
            "generated_at": self.generated_at,
            "summary": self.summary.to_dict(),
            "controls": [control.to_dict() for control in self.controls],
        }


class SecurityMapper:
    """Deterministic mapper from compliance findings to OWASP LLM Top 10 controls."""

    FRAMEWORK = "owasp-llm-top-10"

    CONTROL_DEFINITIONS: tuple[SecurityControlDefinition, ...] = (
        SecurityControlDefinition(
            control_id="LLM01",
            title="Prompt Injection",
            severity="HIGH",
            linked_requirements=("Art. 13", "Art. 14", "Art. 50"),
            default_recommendation="Strengthen prompt isolation, content filtering, and user safeguards.",
        ),
        SecurityControlDefinition(
            control_id="LLM02",
            title="Insecure Output Handling",
            severity="HIGH",
            linked_requirements=("Art. 13", "Art. 15", "Art. 50"),
            default_recommendation="Add output validation and downstream safety enforcement controls.",
        ),
        SecurityControlDefinition(
            control_id="LLM03",
            title="Training Data Poisoning",
            severity="HIGH",
            linked_requirements=("Art. 10", "Art. 11"),
            default_recommendation="Tighten training data provenance, curation, and integrity checks.",
        ),
        SecurityControlDefinition(
            control_id="LLM04",
            title="Model Denial of Service",
            severity="MEDIUM",
            linked_requirements=("Art. 15",),
            default_recommendation="Define resilience controls and abuse throttling for model endpoints.",
        ),
        SecurityControlDefinition(
            control_id="LLM05",
            title="Supply Chain Vulnerabilities",
            severity="HIGH",
            linked_requirements=("Art. 11", "Art. 43"),
            default_recommendation="Document supply chain dependencies and harden conformity controls.",
        ),
        SecurityControlDefinition(
            control_id="LLM06",
            title="Sensitive Information Disclosure",
            severity="HIGH",
            linked_requirements=("Art. 10", "Art. 13", "Art. 50"),
            default_recommendation="Enforce sensitive data minimization and disclosure safeguards.",
        ),
        SecurityControlDefinition(
            control_id="LLM07",
            title="Insecure Plugin Design",
            severity="MEDIUM",
            linked_requirements=("Art. 14", "Art. 15"),
            default_recommendation="Restrict plugin permissions and enforce oversight controls.",
        ),
        SecurityControlDefinition(
            control_id="LLM08",
            title="Excessive Agency",
            severity="CRITICAL",
            linked_requirements=("Art. 5", "Art. 14"),
            default_recommendation="Reduce autonomous scope and require human intervention gates.",
        ),
        SecurityControlDefinition(
            control_id="LLM09",
            title="Overreliance",
            severity="MEDIUM",
            linked_requirements=("Art. 13", "Art. 14"),
            default_recommendation="Improve user transparency and operator review checkpoints.",
        ),
        SecurityControlDefinition(
            control_id="LLM10",
            title="Model Theft",
            severity="MEDIUM",
            linked_requirements=("Art. 15", "Art. 43"),
            default_recommendation="Strengthen model access controls and monitoring for extraction attempts.",
        ),
    )

    def map_from_compliance(self, report: ComplianceReport) -> SecurityMappingResult:
        """Map compliance findings to OWASP LLM Top 10 controls."""
        controls: list[SecurityControlResult] = []

        for definition in self.CONTROL_DEFINITIONS:
            findings = [
                report.findings[requirement_id]
                for requirement_id in definition.linked_requirements
                if requirement_id in report.findings
            ]
            status = self._derive_status(findings)
            controls.append(
                SecurityControlResult(
                    control_id=definition.control_id,
                    title=definition.title,
                    status=status,
                    severity=definition.severity,
                    linked_requirements=list(definition.linked_requirements),
                    gap_analysis=self._build_gap_analysis(status, findings),
                    recommendations=self._build_recommendations(status, findings, definition),
                )
            )

        summary = self._summarize(controls)
        return SecurityMappingResult(
            framework=self.FRAMEWORK,
            generated_at=self._utc_now(),
            summary=summary,
            controls=controls,
        )

    def _derive_status(self, findings: list[ComplianceFinding]) -> ComplianceStatus:
        """Derive control status from mapped requirement statuses."""
        if not findings:
            return ComplianceStatus.NOT_ASSESSED

        statuses = [finding.status for finding in findings]
        if ComplianceStatus.NON_COMPLIANT in statuses:
            return ComplianceStatus.NON_COMPLIANT
        if ComplianceStatus.PARTIAL in statuses:
            return ComplianceStatus.PARTIAL
        if ComplianceStatus.NOT_ASSESSED in statuses:
            return ComplianceStatus.NOT_ASSESSED
        return ComplianceStatus.COMPLIANT

    def _build_gap_analysis(
        self,
        status: ComplianceStatus,
        findings: list[ComplianceFinding],
    ) -> str:
        """Build deterministic gap analysis text from linked findings."""
        if status == ComplianceStatus.COMPLIANT:
            return ""
        if not findings:
            return "No linked EU AI Act findings available to confirm this OWASP control."

        ordered_unique_gaps: list[str] = []
        for finding in findings:
            gap = finding.gap_analysis.strip()
            if gap and gap not in ordered_unique_gaps:
                ordered_unique_gaps.append(gap)

        if ordered_unique_gaps:
            return " | ".join(ordered_unique_gaps[:3])
        return "Linked findings do not provide enough detail to confirm full control coverage."

    def _build_recommendations(
        self,
        status: ComplianceStatus,
        findings: list[ComplianceFinding],
        definition: SecurityControlDefinition,
    ) -> list[str]:
        """Build recommendations from linked findings with deterministic fallback."""
        if status == ComplianceStatus.COMPLIANT:
            return []

        recommendations: list[str] = []
        for finding in findings:
            for step in finding.remediation_steps:
                clean_step = step.strip()
                if clean_step and clean_step not in recommendations:
                    recommendations.append(clean_step)

        if recommendations:
            return recommendations[:5]
        return [definition.default_recommendation]

    def _summarize(self, controls: list[SecurityControlResult]) -> SecurityMappingSummary:
        """Summarize mapped OWASP control statuses."""
        total = len(controls)
        compliant_count = sum(
            1 for control in controls if control.status == ComplianceStatus.COMPLIANT
        )
        non_compliant_count = sum(
            1 for control in controls if control.status == ComplianceStatus.NON_COMPLIANT
        )
        partial_count = sum(1 for control in controls if control.status == ComplianceStatus.PARTIAL)
        not_assessed_count = sum(
            1 for control in controls if control.status == ComplianceStatus.NOT_ASSESSED
        )
        covered = total - not_assessed_count
        coverage_percentage = (covered / total * 100) if total else 0.0

        return SecurityMappingSummary(
            total_controls=total,
            compliant_count=compliant_count,
            non_compliant_count=non_compliant_count,
            partial_count=partial_count,
            not_assessed_count=not_assessed_count,
            coverage_percentage=coverage_percentage,
        )

    def _utc_now(self) -> str:
        """Return UTC ISO timestamp with seconds precision."""
        return datetime.now(UTC).isoformat(timespec="seconds")
