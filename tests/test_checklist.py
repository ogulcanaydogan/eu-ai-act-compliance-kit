"""Tests for checklist generation behavior."""

from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.checklist import ChecklistGenerator
from eu_ai_act.schema import (
    AISystemDescriptor,
    DataPractice,
    HumanOversight,
    UseCase,
    UseCaseDomain,
)


class TestChecklistGenerator:
    """Coverage for actionable checklist generation."""

    def test_high_risk_generates_action_item_for_art43(self):
        """High-risk checklist should include Art.43 action when conformity is partial."""
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

        checker = ComplianceChecker()
        report = checker.check(descriptor)
        checklist = ChecklistGenerator().generate(
            descriptor, report.risk_tier, findings=report.findings
        )

        assert checklist.summary.compliant_count == 5
        assert checklist.summary.actionable_count == 1
        assert checklist.total_items == 1
        assert any(
            item.article == "Art. 43" and item.status == "partial" for item in checklist.items
        )
        assert all(
            item.status in {"non_compliant", "partial", "not_assessed"} for item in checklist.items
        )

    def test_limited_risk_disclosure_gap_generates_art50_action(self):
        """Limited-risk systems with disclosure gaps should produce an Art.50 task."""
        descriptor = AISystemDescriptor(
            name="Support Chatbot",
            description="Customer support chatbot that generates responses for user questions.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.GENERAL_PURPOSE,
                    description="Text generation assistant for support answers.",
                    autonomous_decision=False,
                    impacts_fundamental_rights=False,
                )
            ],
            data_practices=[DataPractice(type="personal", explicit_consent=True)],
            human_oversight=HumanOversight(
                oversight_mechanism="continuous_monitoring",
                fallback_procedure="Escalate unresolved queries to human support.",
                review_frequency="continuous_monitoring",
                human_authority=True,
            ),
            training_data_source="Broad training corpus for a large language model.",
            documentation=True,
            performance_monitoring=True,
        )

        checker = ComplianceChecker()
        report = checker.check(descriptor)
        checklist = ChecklistGenerator().generate(
            descriptor, report.risk_tier, findings=report.findings
        )

        assert checklist.total_items == 1
        assert checklist.items[0].article == "Art. 50"
        assert checklist.items[0].status == "non_compliant"
        assert checklist.items[0].deadline_months == 6

    def test_minimal_risk_returns_empty_action_list(self):
        """Minimal-risk systems should produce no actionable checklist items."""
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

        checker = ComplianceChecker()
        report = checker.check(descriptor)
        checklist = ChecklistGenerator().generate(
            descriptor, report.risk_tier, findings=report.findings
        )

        assert checklist.total_items == 0
        assert checklist.items == []
        assert checklist.summary.total_requirements == 0
        assert checklist.summary.compliant_count == 0
