"""
Compliance Checker Engine

Assesses AI systems against specific EU AI Act requirements based on their
risk tier classification. Returns detailed compliance findings for each requirement.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from eu_ai_act.classifier import RiskClassifier
from eu_ai_act.schema import AISystemDescriptor, RiskTier


class ComplianceStatus(StrEnum):
    """Status of compliance with a requirement."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"


@dataclass
class ComplianceFinding:
    """
    Result of assessing a single requirement.

    Attributes:
        requirement_id: Unique identifier (e.g., "Art.10.1.a")
        requirement_title: Human-readable requirement title
        status: Compliance status
        description: Detailed description of the requirement
        gap_analysis: What is missing or non-compliant
        remediation_steps: How to become compliant
        severity: CRITICAL, HIGH, MEDIUM, LOW
    """

    requirement_id: str
    requirement_title: str
    status: ComplianceStatus
    description: str
    gap_analysis: str = ""
    remediation_steps: list[str] = field(default_factory=list)
    severity: str = "MEDIUM"


@dataclass
class ComplianceSummary:
    """Summary statistics of compliance assessment."""

    total_requirements: int
    compliant_count: int
    non_compliant_count: int
    partial_count: int
    not_assessed_count: int

    @property
    def compliance_percentage(self) -> float:
        """Calculate overall compliance percentage."""
        if self.total_requirements == 0:
            return 0.0
        compliant = self.compliant_count + (self.partial_count * 0.5)
        return (compliant / self.total_requirements) * 100


@dataclass
class ComplianceReport:
    """
    Full compliance assessment report.

    Attributes:
        system_name: Name of the assessed system
        risk_tier: Assigned risk tier
        findings: Dictionary of findings by requirement ID
        summary: Compliance summary statistics
        audit_trail: List of timestamped checks performed
        generated_at: Report generation timestamp
    """

    system_name: str
    risk_tier: RiskTier
    findings: dict[str, ComplianceFinding]
    summary: ComplianceSummary
    audit_trail: list[str] = field(default_factory=list)
    generated_at: str = ""


class ComplianceChecker:
    """
    Checks AI systems against EU AI Act requirements.

    For each applicable requirement based on risk tier, performs assessment and
    returns detailed compliance findings.
    """

    def __init__(self):
        """Initialize compliance checker."""
        self.classifier = RiskClassifier()
        self.requirement_database = self._load_requirement_database()

    def check(self, descriptor: AISystemDescriptor) -> ComplianceReport:
        """
        Perform full compliance check on an AI system.

        Args:
            descriptor: AI system descriptor

        Returns:
            ComplianceReport with detailed findings
        """
        generated_at = self._utc_now()
        classification = self.classifier.classify(descriptor)
        findings: dict[str, ComplianceFinding] = {}
        audit_trail = [
            f"{generated_at} Started compliance assessment",
            (
                f"{generated_at} Classified as {classification.tier.value} "
                f"({classification.confidence:.0%} confidence)"
            ),
        ]

        if classification.tier == RiskTier.UNACCEPTABLE:
            finding = self._check_prohibited_practices()
            findings[finding.requirement_id] = finding
        elif classification.tier == RiskTier.HIGH_RISK:
            for finding in [
                self._check_data_governance(descriptor),
                self._check_documentation(descriptor),
                self._check_transparency(descriptor),
                self._check_human_oversight(descriptor),
                self._check_accuracy_robustness(descriptor),
                self._check_conformity_assessment(descriptor),
            ]:
                findings[finding.requirement_id] = finding
        elif classification.tier == RiskTier.LIMITED:
            finding = self._check_limited_transparency(descriptor)
            findings[finding.requirement_id] = finding
        else:
            audit_trail.append(
                f"{generated_at} No mandatory requirement checks defined for {RiskTier.MINIMAL.value}"
            )

        summary = self._summarize(findings)
        audit_trail.append(
            f"{generated_at} Completed compliance assessment with {summary.total_requirements} findings"
        )

        return ComplianceReport(
            system_name=descriptor.name,
            risk_tier=classification.tier,
            findings=findings,
            summary=summary,
            audit_trail=audit_trail,
            generated_at=generated_at,
        )

    def _load_requirement_database(self) -> dict[str, dict]:
        """Load requirement definitions from articles database."""
        return {
            "Art. 5": {
                "title": "Prohibited practices",
                "description": "Systems in this category are prohibited and cannot be placed on the market.",
                "severity": "CRITICAL",
            },
            "Art. 10": {
                "title": "Data governance and quality",
                "description": "High-risk systems require robust data governance, quality controls, and bias mitigation.",
                "severity": "HIGH",
            },
            "Art. 11": {
                "title": "Technical documentation and record-keeping",
                "description": "Providers must maintain up-to-date technical documentation and records.",
                "severity": "HIGH",
            },
            "Art. 13": {
                "title": "Transparency and information to users",
                "description": "High-risk AI should be transparent and provide sufficient information to deployers.",
                "severity": "HIGH",
            },
            "Art. 14": {
                "title": "Human oversight",
                "description": "High-risk AI systems must support effective human oversight and intervention.",
                "severity": "CRITICAL",
            },
            "Art. 15": {
                "title": "Accuracy, robustness, and cybersecurity",
                "description": "High-risk AI systems need measurable performance, monitoring, and incident response.",
                "severity": "HIGH",
            },
            "Art. 43": {
                "title": "Conformity assessment",
                "description": "High-risk systems require conformity assessment before market placement.",
                "severity": "HIGH",
            },
            "Art. 50": {
                "title": "Transparency obligations for limited-risk AI",
                "description": "Users must be informed when interacting with AI-generated or synthetic content.",
                "severity": "MEDIUM",
            },
        }

    def _check_data_governance(self, descriptor: AISystemDescriptor) -> ComplianceFinding:
        """Check Article 10: Data governance and quality requirements."""
        sensitive_practices = [
            dp
            for dp in descriptor.data_practices
            if "sensitive" in dp.type.lower()
            or "health" in dp.type.lower()
            or "biometric" in dp.type.lower()
        ]

        if any(not dp.explicit_consent for dp in sensitive_practices):
            return self._make_finding(
                "Art. 10",
                ComplianceStatus.NON_COMPLIANT,
                gap_analysis="Sensitive/biometric data is processed without explicit consent.",
                remediation_steps=[
                    "Collect explicit and auditable consent for sensitive data processing.",
                    "Block training/inference flows until consent controls are enforced.",
                ],
            )

        if sensitive_practices and any(not dp.anonymization for dp in sensitive_practices):
            return self._make_finding(
                "Art. 10",
                ComplianceStatus.PARTIAL,
                gap_analysis="Sensitive/biometric data exists but anonymization controls are not fully documented.",
                remediation_steps=[
                    "Document anonymization or pseudonymization controls for each sensitive data flow.",
                    "Track re-identification risk and mitigation ownership.",
                ],
            )

        if sensitive_practices:
            return self._make_finding("Art. 10", ComplianceStatus.COMPLIANT)

        return self._make_finding(
            "Art. 10",
            ComplianceStatus.NOT_ASSESSED,
            gap_analysis="Insufficient evidence to verify high-risk data governance controls.",
            remediation_steps=[
                "Provide data governance documentation mapped to Art. 10 controls.",
            ],
        )

    def _check_documentation(self, descriptor: AISystemDescriptor) -> ComplianceFinding:
        """Check Article 11: Documentation and record-keeping requirements."""
        if descriptor.documentation:
            return self._make_finding("Art. 11", ComplianceStatus.COMPLIANT)

        return self._make_finding(
            "Art. 11",
            ComplianceStatus.NON_COMPLIANT,
            gap_analysis="System-level technical documentation is missing or incomplete.",
            remediation_steps=[
                "Publish a technical file covering design, data, evaluation, and risk controls.",
                "Version documentation and link it to releases.",
            ],
        )

    def _check_transparency(self, descriptor: AISystemDescriptor) -> ComplianceFinding:
        """Check Article 13: Transparency requirements."""
        if descriptor.documentation and descriptor.incident_procedure:
            return self._make_finding("Art. 13", ComplianceStatus.COMPLIANT)
        if descriptor.documentation or descriptor.incident_procedure:
            return self._make_finding(
                "Art. 13",
                ComplianceStatus.PARTIAL,
                gap_analysis="Transparency controls exist but user-facing disclosures are only partially evidenced.",
                remediation_steps=[
                    "Add explicit deployer/user information packs on model behavior and limits.",
                    "Document fallback behavior and escalation paths for users.",
                ],
            )

        return self._make_finding(
            "Art. 13",
            ComplianceStatus.NON_COMPLIANT,
            gap_analysis="No evidence of user-facing transparency controls.",
            remediation_steps=[
                "Define disclosures on intended purpose, performance, and limitations.",
            ],
        )

    def _check_human_oversight(self, descriptor: AISystemDescriptor) -> ComplianceFinding:
        """Check Article 14: Human oversight requirements."""
        oversight = descriptor.human_oversight
        has_mechanism = oversight.oversight_mechanism.strip().lower() not in {"", "none"}
        has_fallback = bool(oversight.fallback_procedure and oversight.fallback_procedure.strip())
        has_review_loop = oversight.review_frequency.strip().lower() not in {"", "none", "never"}

        if oversight.human_authority and has_mechanism and has_fallback and has_review_loop:
            return self._make_finding("Art. 14", ComplianceStatus.COMPLIANT)

        if oversight.human_authority and has_mechanism:
            return self._make_finding(
                "Art. 14",
                ComplianceStatus.PARTIAL,
                gap_analysis="Human oversight exists but fallback/review details are incomplete.",
                remediation_steps=[
                    "Define fallback and escalation procedures for failed or contested AI outcomes.",
                    "Set explicit review cadence and accountability.",
                ],
            )

        return self._make_finding(
            "Art. 14",
            ComplianceStatus.NON_COMPLIANT,
            gap_analysis="System cannot be effectively overridden by a human decision-maker.",
            remediation_steps=[
                "Introduce human override authority and documented intervention points.",
            ],
        )

    def _check_accuracy_robustness(self, descriptor: AISystemDescriptor) -> ComplianceFinding:
        """Check Article 15: Accuracy, robustness, and cybersecurity requirements."""
        if descriptor.performance_monitoring and descriptor.incident_procedure:
            return self._make_finding("Art. 15", ComplianceStatus.COMPLIANT)
        if descriptor.performance_monitoring or descriptor.incident_procedure:
            return self._make_finding(
                "Art. 15",
                ComplianceStatus.PARTIAL,
                gap_analysis="Performance/incident controls are partially defined but not complete.",
                remediation_steps=[
                    "Add measurable robustness thresholds and alerting rules.",
                    "Document incident response ownership and recovery timelines.",
                ],
            )

        return self._make_finding(
            "Art. 15",
            ComplianceStatus.NON_COMPLIANT,
            gap_analysis="No evidence of ongoing monitoring or incident response controls.",
            remediation_steps=[
                "Implement continuous monitoring and incident handling procedures.",
            ],
        )

    def _check_conformity_assessment(self, descriptor: AISystemDescriptor) -> ComplianceFinding:
        """Check Article 43: Conformity assessment procedures."""
        evidence_text = " ".join(
            [
                descriptor.description,
                descriptor.training_data_source,
                descriptor.incident_procedure or "",
            ]
        ).lower()
        conformity_keywords = [
            "conformity assessment",
            "ce mark",
            "notified body",
            "annex vii",
            "annex vi",
        ]
        has_explicit_evidence = any(keyword in evidence_text for keyword in conformity_keywords)

        if has_explicit_evidence:
            return self._make_finding("Art. 43", ComplianceStatus.COMPLIANT)

        if (
            descriptor.documentation
            and descriptor.performance_monitoring
            and descriptor.human_oversight.human_authority
        ):
            return self._make_finding(
                "Art. 43",
                ComplianceStatus.PARTIAL,
                gap_analysis="Baseline controls exist but no explicit conformity assessment evidence was provided.",
                remediation_steps=[
                    "Document conformity assessment pathway and responsible legal entity.",
                    "Attach audit artifacts or notified-body evidence where applicable.",
                ],
            )

        return self._make_finding(
            "Art. 43",
            ComplianceStatus.NOT_ASSESSED,
            gap_analysis="Insufficient evidence to determine conformity assessment status.",
            remediation_steps=[
                "Provide conformity assessment records and referenced procedures.",
            ],
        )

    def _check_limited_transparency(self, descriptor: AISystemDescriptor) -> ComplianceFinding:
        """Check Article 50 transparency obligations for limited-risk systems."""
        text = " ".join(
            [descriptor.description, descriptor.training_data_source]
            + [use_case.description for use_case in descriptor.use_cases]
        ).lower()
        generation_keywords = [
            "deepfake",
            "synthetic",
            "generated",
            "chatbot",
            "generative",
            "text generation",
        ]
        disclosure_keywords = [
            "disclos",
            "inform",
            "transparent",
            "label",
            "ai-generated",
            "ai generated",
        ]
        produces_generated_content = any(keyword in text for keyword in generation_keywords)
        has_disclosure_evidence = any(keyword in text for keyword in disclosure_keywords)

        if produces_generated_content and has_disclosure_evidence:
            return self._make_finding("Art. 50", ComplianceStatus.COMPLIANT)
        if produces_generated_content and not has_disclosure_evidence:
            return self._make_finding(
                "Art. 50",
                ComplianceStatus.NON_COMPLIANT,
                gap_analysis="AI-generated/synthetic content is present without clear disclosure evidence.",
                remediation_steps=[
                    "Add clear notices that users are interacting with AI-generated content.",
                    "Store disclosure language in product and policy artifacts.",
                ],
            )

        return self._make_finding(
            "Art. 50",
            ComplianceStatus.NOT_ASSESSED,
            gap_analysis="Unable to confirm whether Art. 50 disclosure obligations apply from the provided descriptor.",
            remediation_steps=[
                "Clarify whether the system generates or transforms content perceptible to users.",
            ],
        )

    def _check_prohibited_practices(self) -> ComplianceFinding:
        """Check prohibited use under Article 5."""
        return self._make_finding(
            "Art. 5",
            ComplianceStatus.NON_COMPLIANT,
            gap_analysis="System was classified as unacceptable risk and is prohibited under Art. 5.",
            remediation_steps=[
                "Do not deploy this system in the EU market.",
                "Redesign the use case to remove prohibited practices.",
            ],
        )

    def _make_finding(
        self,
        requirement_id: str,
        status: ComplianceStatus,
        gap_analysis: str = "",
        remediation_steps: list[str] | None = None,
    ) -> ComplianceFinding:
        """Build a finding using canonical requirement metadata."""
        requirement = self.requirement_database[requirement_id]
        return ComplianceFinding(
            requirement_id=requirement_id,
            requirement_title=requirement["title"],
            status=status,
            description=requirement["description"],
            gap_analysis=gap_analysis,
            remediation_steps=remediation_steps or [],
            severity=requirement["severity"],
        )

    def _summarize(self, findings: dict[str, ComplianceFinding]) -> ComplianceSummary:
        """Build summary counts from finding statuses."""
        compliant_count = sum(
            1 for f in findings.values() if f.status == ComplianceStatus.COMPLIANT
        )
        non_compliant_count = sum(
            1 for f in findings.values() if f.status == ComplianceStatus.NON_COMPLIANT
        )
        partial_count = sum(1 for f in findings.values() if f.status == ComplianceStatus.PARTIAL)
        not_assessed_count = sum(
            1 for f in findings.values() if f.status == ComplianceStatus.NOT_ASSESSED
        )
        return ComplianceSummary(
            total_requirements=len(findings),
            compliant_count=compliant_count,
            non_compliant_count=non_compliant_count,
            partial_count=partial_count,
            not_assessed_count=not_assessed_count,
        )

    def _utc_now(self) -> str:
        """Return ISO-8601 UTC timestamp."""
        return datetime.now(UTC).isoformat(timespec="seconds")
