"""Tests for compliance checker core logic."""

from eu_ai_act.checker import ComplianceChecker, ComplianceStatus
from eu_ai_act.schema import (
    AISystemDescriptor,
    DataPractice,
    HumanOversight,
    RiskTier,
    UseCase,
    UseCaseDomain,
)


class TestComplianceChecker:
    """Coverage for Phase 2.1 compliance checking behavior."""

    def test_high_risk_report_contains_expected_findings(self):
        """High-risk systems should evaluate Art.10/11/13/14/15/43."""
        descriptor = AISystemDescriptor(
            name="Medical Imaging AI",
            version="1.0.0",
            description="AI system analyzing medical images in healthcare operations.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.HEALTHCARE,
                    description="Detects abnormalities in radiology images with clinician review.",
                    autonomous_decision=False,
                    impacts_fundamental_rights=True,
                )
            ],
            data_practices=[
                DataPractice(
                    type="sensitive_health",
                    retention_period=365,
                    sharing_third_parties=False,
                    explicit_consent=True,
                    anonymization="Pseudonymized training and evaluation datasets",
                )
            ],
            human_oversight=HumanOversight(
                oversight_mechanism="approval_required",
                fallback_procedure="Escalate to senior clinician on any ambiguous output.",
                review_frequency="per_decision",
                human_authority=True,
            ),
            training_data_source="Curated and quality-reviewed clinical imaging datasets.",
            documentation=True,
            performance_monitoring=True,
            incident_procedure="Continuous monitoring with incident escalation within one hour.",
        )

        report = ComplianceChecker().check(descriptor)

        assert report.risk_tier == RiskTier.HIGH_RISK
        assert set(report.findings.keys()) == {"Art. 10", "Art. 11", "Art. 13", "Art. 14", "Art. 15", "Art. 43"}
        assert report.summary.total_requirements == 6
        assert report.summary.compliant_count == 5
        assert report.summary.partial_count == 1
        assert report.findings["Art. 43"].status == ComplianceStatus.PARTIAL

    def test_unacceptable_system_is_non_compliant_art5(self):
        """Unacceptable systems should return a single critical Art.5 non-compliance."""
        descriptor = AISystemDescriptor(
            name="Social Credit System",
            description="System performs social scoring to assign citizen trust scores.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.OTHER,
                    description="Social scoring affects service access and public benefits.",
                    autonomous_decision=True,
                    impacts_fundamental_rights=True,
                )
            ],
            data_practices=[DataPractice(type="personal", explicit_consent=False)],
            human_oversight=HumanOversight(
                oversight_mechanism="none",
                fallback_procedure="No fallback available.",
                review_frequency="never",
                human_authority=False,
            ),
            training_data_source="Behavioral and government records used for scoring.",
            documentation=False,
            performance_monitoring=False,
        )

        report = ComplianceChecker().check(descriptor)

        assert report.risk_tier == RiskTier.UNACCEPTABLE
        assert report.summary.total_requirements == 1
        assert report.summary.non_compliant_count == 1
        assert report.findings["Art. 5"].status == ComplianceStatus.NON_COMPLIANT

    def test_limited_risk_checks_art50(self):
        """Limited-risk systems should evaluate Art.50 transparency obligations."""
        descriptor = AISystemDescriptor(
            name="Support Chatbot",
            description=(
                "Customer support chatbot that generates responses and clearly informs users "
                "that content is AI-generated."
            ),
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.GENERAL_PURPOSE,
                    description="Chatbot generates answers and discloses that it is an AI assistant.",
                    autonomous_decision=False,
                    impacts_fundamental_rights=False,
                )
            ],
            data_practices=[DataPractice(type="personal", explicit_consent=True)],
            human_oversight=HumanOversight(
                oversight_mechanism="continuous_monitoring",
                fallback_procedure="Escalate unresolved cases to a human support specialist.",
                review_frequency="continuous_monitoring",
                human_authority=True,
            ),
            training_data_source="Broad training corpus for a large language model.",
            documentation=True,
            performance_monitoring=True,
        )

        report = ComplianceChecker().check(descriptor)

        assert report.risk_tier == RiskTier.LIMITED
        assert report.summary.total_requirements == 1
        assert report.summary.compliant_count == 1
        assert report.findings["Art. 50"].status == ComplianceStatus.COMPLIANT

    def test_minimal_risk_has_empty_findings(self):
        """Minimal-risk systems should return a valid empty summary."""
        descriptor = AISystemDescriptor(
            name="Spam Filter",
            description="Email spam filter with user-controlled override and no rights impact.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.CONTENT_MODERATION,
                    description="Filters likely spam while letting users restore messages.",
                    autonomous_decision=True,
                    impacts_fundamental_rights=False,
                )
            ],
            data_practices=[DataPractice(type="personal", explicit_consent=False)],
            human_oversight=HumanOversight(
                oversight_mechanism="user_controlled",
                fallback_procedure="Users can move any message back to inbox.",
                review_frequency="user_controlled",
                human_authority=True,
            ),
            training_data_source="Heuristic and historical labeled spam data.",
            documentation=False,
            performance_monitoring=True,
        )

        report = ComplianceChecker().check(descriptor)

        assert report.risk_tier == RiskTier.MINIMAL
        assert report.findings == {}
        assert report.summary.total_requirements == 0
        assert report.summary.compliance_percentage == 0.0
