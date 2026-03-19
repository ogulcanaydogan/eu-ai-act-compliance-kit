"""Tests for transparency checker logic."""

from eu_ai_act.checker import ComplianceStatus
from eu_ai_act.schema import AISystemDescriptor, DataPractice, HumanOversight, UseCase, UseCaseDomain
from eu_ai_act.transparency import TransparencyChecker


class TestTransparencyChecker:
    """Coverage for Art. 50 and GPAI transparency checks."""

    def test_art50_disclosure_detects_gap(self):
        """Generated-content systems without disclosure should be non-compliant for Art. 50."""
        descriptor = AISystemDescriptor(
            name="Synthetic News Bot",
            description="System generates synthetic articles for social media channels.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.GENERAL_PURPOSE,
                    description="Generated content publishing workflow without any user-facing message.",
                    autonomous_decision=False,
                    impacts_fundamental_rights=False,
                )
            ],
            data_practices=[DataPractice(type="personal", explicit_consent=True)],
            human_oversight=HumanOversight(
                oversight_mechanism="continuous_monitoring",
                fallback_procedure="Editorial review before publication.",
                review_frequency="daily",
                human_authority=True,
            ),
            training_data_source="Broad training corpus and synthetic text datasets.",
            documentation=True,
            performance_monitoring=True,
        )

        finding = TransparencyChecker().check_art50_disclosure(descriptor)[0]

        assert finding.requirement_id == "Art. 50"
        assert finding.status == ComplianceStatus.NON_COMPLIANT

    def test_deepfake_detection_finding(self):
        """Deepfake signal should produce a non-compliant or partial finding."""
        descriptor = AISystemDescriptor(
            name="Voice Clone Suite",
            description="Deepfake voice clone system for synthetic media generation.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.GENERAL_PURPOSE,
                    description="Voice clone deepfake generation pipeline for user content.",
                    autonomous_decision=False,
                    impacts_fundamental_rights=False,
                )
            ],
            data_practices=[DataPractice(type="personal", explicit_consent=True)],
            human_oversight=HumanOversight(
                oversight_mechanism="manual_review",
                fallback_procedure="Human moderation before release.",
                review_frequency="per_decision",
                human_authority=True,
            ),
            training_data_source="Synthetic speech corpus.",
            documentation=True,
            performance_monitoring=True,
        )

        finding = TransparencyChecker().check_deepfake_detection(descriptor)
        assert finding.requirement_id == "Art. 50"
        assert finding.status in {ComplianceStatus.NON_COMPLIANT, ComplianceStatus.PARTIAL}

    def test_gpai_obligations_trigger_for_general_purpose(self):
        """GPAI obligations should be returned when general-purpose signals are present."""
        descriptor = AISystemDescriptor(
            name="Foundation Chat Model",
            description="General purpose foundation model for broad enterprise use.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.GENERAL_PURPOSE,
                    description="General purpose assistant with broad training across domains.",
                    autonomous_decision=False,
                    impacts_fundamental_rights=False,
                )
            ],
            data_practices=[DataPractice(type="personal", explicit_consent=True)],
            human_oversight=HumanOversight(
                oversight_mechanism="continuous_monitoring",
                fallback_procedure="Escalate risky outputs to human reviewer.",
                review_frequency="daily",
                human_authority=True,
            ),
            training_data_source="Broad training corpus with multimodal sources.",
            documentation=True,
            performance_monitoring=True,
            incident_procedure="Incident workflow exists for model misuse.",
        )

        findings = TransparencyChecker().check_gpai_obligations(descriptor)

        article_ids = {finding.requirement_id for finding in findings}
        assert {"Art. 51", "Art. 52", "Art. 53", "Art. 54", "Art. 55"} <= article_ids
