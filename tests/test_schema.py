"""
Tests for AI system descriptor schema validation.

Tests Pydantic models for validating AI system descriptors.
"""

from datetime import timedelta
import warnings

import pytest
from eu_ai_act.schema import (
    AISystemDescriptor,
    DataPractice,
    HumanOversight,
    RiskTier,
    UseCase,
    UseCaseDomain,
)


def _build_valid_descriptor() -> AISystemDescriptor:
    """Create a valid descriptor used by multiple tests."""
    return AISystemDescriptor(
        name="Test System",
        version="1.0.0",
        description="Test AI system for compliance assessment",
        use_cases=[
            UseCase(
                domain=UseCaseDomain.HEALTHCARE,
                description="Analyzes medical images",
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
            )
        ],
        human_oversight=HumanOversight(
            oversight_mechanism="approval_required",
            fallback_procedure="Manual review",
            review_frequency="per_decision",
            human_authority=True,
        ),
        training_data_source="De-identified medical data",
        documentation=True,
        performance_monitoring=True,
    )


class TestAISystemDescriptor:
    """Test AISystemDescriptor schema validation."""

    def test_valid_descriptor(self):
        """Test that valid descriptor validates successfully."""
        descriptor = _build_valid_descriptor()
        assert descriptor.name == "Test System"
        assert len(descriptor.use_cases) == 1
        assert descriptor.human_oversight.human_authority is True

    def test_missing_required_field(self):
        """Test that missing required field raises validation error."""
        with pytest.raises(ValueError):
            AISystemDescriptor(
                name="Test System",
                # Missing description
                version="1.0.0",
                use_cases=[],
                data_practices=[],
                human_oversight=HumanOversight(
                    oversight_mechanism="approval_required",
                    fallback_procedure="Manual review",
                    review_frequency="per_decision",
                ),
                training_data_source="Test data",
            )

    def test_empty_use_cases(self):
        """Test that empty use cases list raises validation error."""
        with pytest.raises(ValueError):
            AISystemDescriptor(
                name="Test System",
                description="Test system",
                version="1.0.0",
                use_cases=[],  # Invalid: must have at least one
                data_practices=[
                    DataPractice(type="personal", retention_period=90)
                ],
                human_oversight=HumanOversight(
                    oversight_mechanism="approval_required",
                    fallback_procedure="Manual review",
                    review_frequency="per_decision",
                ),
                training_data_source="Test data",
            )

    def test_empty_data_practices(self):
        """Test that empty data practices list raises validation error."""
        with pytest.raises(ValueError):
            AISystemDescriptor(
                name="Test System",
                description="Test system",
                version="1.0.0",
                use_cases=[
                    UseCase(
                        domain=UseCaseDomain.OTHER,
                        description="Test use case",
                    )
                ],
                data_practices=[],  # Invalid: must have at least one
                human_oversight=HumanOversight(
                    oversight_mechanism="approval_required",
                    fallback_procedure="Manual review",
                    review_frequency="per_decision",
                ),
                training_data_source="Test training data source.",
            )

    def test_default_timestamps_are_timezone_aware_utc(self):
        """Default created_at/last_updated should be timezone-aware UTC timestamps."""
        descriptor = _build_valid_descriptor()
        assert descriptor.created_at is not None
        assert descriptor.last_updated is not None
        assert descriptor.created_at.tzinfo is not None
        assert descriptor.last_updated.tzinfo is not None
        assert descriptor.created_at.utcoffset() == timedelta(0)
        assert descriptor.last_updated.utcoffset() == timedelta(0)

    def test_instantiation_emits_no_pydantic_deprecation_warnings(self):
        """Descriptor creation should not emit known Pydantic v2 deprecation warnings."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _build_valid_descriptor()

        messages = [str(item.message) for item in caught]
        forbidden_fragments = [
            "class-based `config` is deprecated",
            "`min_items` is deprecated",
            "datetime.datetime.utcnow() is deprecated",
        ]
        for fragment in forbidden_fragments:
            assert not any(fragment in message for message in messages), messages

    def test_semantic_versioning(self):
        """Test that version field accepts semantic versioning."""
        descriptor = AISystemDescriptor(
            name="Test System",
            version="2.1.3",
            description="Test system description for semantic versioning validation.",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.OTHER,
                    description="Test use case",
                )
            ],
            data_practices=[DataPractice(type="personal")],
            human_oversight=HumanOversight(
                oversight_mechanism="manual_review",
                fallback_procedure="Escalate",
                review_frequency="daily",
            ),
            training_data_source="Test training data source used for model evaluation.",
        )
        assert descriptor.version == "2.1.3"


class TestUseCase:
    """Test UseCase model validation."""

    def test_valid_use_case(self):
        """Test valid use case creation."""
        uc = UseCase(
            domain=UseCaseDomain.EMPLOYMENT,
            description="Analyzes job applications for hiring decisions",
            autonomous_decision=False,
            impacts_fundamental_rights=True,
        )
        assert uc.domain == UseCaseDomain.EMPLOYMENT
        assert uc.autonomous_decision is False

    def test_use_case_requires_description(self):
        """Test that description is required."""
        with pytest.raises(ValueError):
            UseCase(
                domain=UseCaseDomain.HEALTHCARE,
                description="",  # Too short
            )


class TestDataPractice:
    """Test DataPractice model validation."""

    def test_valid_data_practice(self):
        """Test valid data practice creation."""
        dp = DataPractice(
            type="personal",
            retention_period=180,
            sharing_third_parties=True,
            explicit_consent=True,
        )
        assert dp.type == "personal"
        assert dp.retention_period == 180

    def test_retention_period_non_negative(self):
        """Test that retention period must be non-negative."""
        dp = DataPractice(
            type="personal",
            retention_period=0,  # Allowed: immediate deletion
        )
        assert dp.retention_period == 0


class TestHumanOversight:
    """Test HumanOversight model validation."""

    def test_valid_human_oversight(self):
        """Test valid human oversight configuration."""
        ho = HumanOversight(
            oversight_mechanism="approval_required",
            fallback_procedure="Manual review by senior staff",
            review_frequency="per_decision",
            human_authority=True,
        )
        assert ho.oversight_mechanism == "approval_required"
        assert ho.human_authority is True

    def test_human_oversight_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValueError):
            HumanOversight(
                oversight_mechanism="approval_required",
                # Missing fallback_procedure
                review_frequency="per_decision",
            )


class TestRiskTier:
    """Test RiskTier enum."""

    def test_all_risk_tiers(self):
        """Test all risk tier values."""
        assert RiskTier.UNACCEPTABLE.value == "unacceptable"
        assert RiskTier.HIGH_RISK.value == "high_risk"
        assert RiskTier.LIMITED.value == "limited"
        assert RiskTier.MINIMAL.value == "minimal"


class TestUseCaseDomain:
    """Test UseCaseDomain enum."""

    def test_all_use_case_domains(self):
        """Test all use case domain values."""
        expected_domains = [
            "biometric",
            "critical_infrastructure",
            "law_enforcement",
            "employment",
            "credit_scoring",
            "education",
            "general_purpose",
            "healthcare",
            "content_moderation",
            "other",
        ]
        for domain in expected_domains:
            assert UseCaseDomain(domain)
