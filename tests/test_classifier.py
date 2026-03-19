"""
Tests for risk classification engine.

Tests RiskClassifier logic for categorizing AI systems into risk tiers.
"""

import pytest
from eu_ai_act.schema import (
    AISystemDescriptor,
    UseCase,
    DataPractice,
    HumanOversight,
    UseCaseDomain,
)
from eu_ai_act.classifier import RiskClassifier, RiskTier


class TestRiskClassifierHighRisk:
    """Test high-risk system classification."""

    @pytest.fixture
    def medical_ai_descriptor(self):
        """High-risk medical imaging AI system."""
        return AISystemDescriptor(
            name="Medical Imaging AI",
            version="1.0.0",
            description="Analyzes CT/MRI scans for tumor detection in hospitals",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.HEALTHCARE,
                    description="Detects tumors in medical imaging",
                    autonomous_decision=False,
                    impacts_fundamental_rights=True,
                )
            ],
            data_practices=[
                DataPractice(
                    type="sensitive_health",
                    retention_period=2555,
                    sharing_third_parties=False,
                    explicit_consent=True,
                )
            ],
            human_oversight=HumanOversight(
                oversight_mechanism="approval_required",
                fallback_procedure="Senior radiologist manual review",
                review_frequency="per_decision",
                human_authority=True,
            ),
            training_data_source="500,000 de-identified medical images",
            documentation=True,
            performance_monitoring=True,
        )

    def test_classify_medical_ai_as_high_risk(self, medical_ai_descriptor):
        """Test that medical AI is classified as high-risk."""
        classifier = RiskClassifier()
        classification = classifier.classify(medical_ai_descriptor)

        assert classification.tier == RiskTier.HIGH_RISK
        assert classification.confidence >= 0.85
        assert "Art. 6" in classification.articles_applicable
        assert "Art. 10" in classification.articles_applicable
        assert "Art. 14" in classification.articles_applicable

    def test_classification_reasoning_provided(self, medical_ai_descriptor):
        """Test that classification includes explanation."""
        classifier = RiskClassifier()
        classification = classifier.classify(medical_ai_descriptor)

        assert classification.reasoning
        assert "high-risk" in classification.reasoning.lower()

    def test_contributing_factors_included(self, medical_ai_descriptor):
        """Test that contributing factors are provided."""
        classifier = RiskClassifier()
        classification = classifier.classify(medical_ai_descriptor)

        assert classification.contributing_factors
        assert any("healthcare" in factor.lower() for factor in classification.contributing_factors)


class TestRiskClassifierHighRiskEmployment:
    """Test high-risk employment system classification."""

    @pytest.fixture
    def hiring_ai_descriptor(self):
        """High-risk resume screening AI system."""
        return AISystemDescriptor(
            name="Resume Screening AI",
            version="2.0.0",
            description="Screens job applications for candidate qualification",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.EMPLOYMENT,
                    description="Analyzes resumes and applications",
                    autonomous_decision=False,
                    impacts_fundamental_rights=True,
                )
            ],
            data_practices=[
                DataPractice(
                    type="personal",
                    retention_period=180,
                    sharing_third_parties=True,
                    explicit_consent=True,
                )
            ],
            human_oversight=HumanOversight(
                oversight_mechanism="approval_required",
                fallback_procedure="HR manager manual review",
                review_frequency="per_decision",
                human_authority=True,
            ),
            training_data_source="Historical hiring records",
            documentation=True,
            performance_monitoring=True,
        )

    def test_classify_hiring_ai_as_high_risk(self, hiring_ai_descriptor):
        """Test that hiring AI is classified as high-risk."""
        classifier = RiskClassifier()
        classification = classifier.classify(hiring_ai_descriptor)

        assert classification.tier == RiskTier.HIGH_RISK
        assert classification.confidence >= 0.85
        assert "Art. 6" in classification.articles_applicable


class TestRiskClassifierProhibited:
    """Test prohibited practice detection."""

    @pytest.fixture
    def social_scoring_descriptor(self):
        """Social credit scoring system (prohibited)."""
        return AISystemDescriptor(
            name="Social Credit System",
            version="1.0.0",
            description="System evaluates social credit scores for citizens",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.OTHER,
                    description="Social credit scoring restricts services",
                    autonomous_decision=True,
                    impacts_fundamental_rights=True,
                )
            ],
            data_practices=[
                DataPractice(
                    type="personal",
                    retention_period=36500,
                    sharing_third_parties=True,
                    explicit_consent=False,
                )
            ],
            human_oversight=HumanOversight(
                oversight_mechanism="none",
                fallback_procedure="None",
                review_frequency="never",
                human_authority=False,
            ),
            training_data_source="Behavioral tracking data",
            documentation=False,
            performance_monitoring=False,
        )

    def test_classify_social_scoring_as_unacceptable(self, social_scoring_descriptor):
        """Test that social scoring is classified as unacceptable."""
        classifier = RiskClassifier()
        classification = classifier.classify(social_scoring_descriptor)

        assert classification.tier == RiskTier.UNACCEPTABLE
        assert "Art. 5" in classification.articles_applicable
        assert "prohibited" in classification.reasoning.lower()

    def test_unacceptable_tier_high_confidence(self, social_scoring_descriptor):
        """Test that unacceptable classification has high confidence."""
        classifier = RiskClassifier()
        classification = classifier.classify(social_scoring_descriptor)

        assert classification.confidence >= 0.90


class TestRiskClassifierMinimal:
    """Test minimal-risk system classification."""

    @pytest.fixture
    def spam_filter_descriptor(self):
        """Minimal-risk spam filter system."""
        return AISystemDescriptor(
            name="Email Spam Filter",
            version="4.0.0",
            description="Filters spam emails from user inbox",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.CONTENT_MODERATION,
                    description="Detects and filters spam emails",
                    autonomous_decision=True,
                    impacts_fundamental_rights=False,
                )
            ],
            data_practices=[
                DataPractice(
                    type="personal",
                    retention_period=30,
                    sharing_third_parties=False,
                    explicit_consent=False,
                )
            ],
            human_oversight=HumanOversight(
                oversight_mechanism="user_controlled",
                fallback_procedure="Users can restore emails from spam",
                review_frequency="user_controlled",
                human_authority=True,
            ),
            training_data_source="Public spam/legitimate email corpus",
            documentation=False,
            performance_monitoring=True,
        )

    def test_classify_spam_filter_as_minimal(self, spam_filter_descriptor):
        """Test that spam filter is classified as minimal-risk."""
        classifier = RiskClassifier()
        classification = classifier.classify(spam_filter_descriptor)

        assert classification.tier == RiskTier.MINIMAL
        assert classification.confidence >= 0.75


class TestRiskClassifierArticles:
    """Test article retrieval by risk tier."""

    def test_get_articles_for_high_risk(self):
        """Test that high-risk tier returns appropriate articles."""
        classifier = RiskClassifier()
        articles = classifier.get_applicable_articles(RiskTier.HIGH_RISK)

        assert "Art. 6" in articles
        assert "Art. 10" in articles
        assert "Art. 14" in articles
        assert "Art. 43" in articles

    def test_get_articles_for_unacceptable(self):
        """Test that unacceptable tier returns Article 5."""
        classifier = RiskClassifier()
        articles = classifier.get_applicable_articles(RiskTier.UNACCEPTABLE)

        assert "Art. 5" in articles

    def test_get_articles_for_minimal(self):
        """Test that minimal tier returns basic articles."""
        classifier = RiskClassifier()
        articles = classifier.get_applicable_articles(RiskTier.MINIMAL)

        assert articles  # Should have some articles


class TestRiskClassifierEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_missing_safeguards_lowers_confidence(self):
        """Test that missing safeguards lowers confidence but doesn't change tier."""
        descriptor_with_safeguards = AISystemDescriptor(
            name="System A",
            description="Healthcare AI",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.HEALTHCARE,
                    description="Medical analysis",
                    impacts_fundamental_rights=True,
                )
            ],
            data_practices=[DataPractice(type="sensitive_health")],
            human_oversight=HumanOversight(
                oversight_mechanism="approval_required",
                fallback_procedure="Manual",
                review_frequency="per_decision",
                human_authority=True,
            ),
            training_data_source="Medical data",
            documentation=True,
            performance_monitoring=True,
        )

        descriptor_without_safeguards = AISystemDescriptor(
            name="System B",
            description="Healthcare AI",
            use_cases=[
                UseCase(
                    domain=UseCaseDomain.HEALTHCARE,
                    description="Medical analysis",
                    impacts_fundamental_rights=True,
                )
            ],
            data_practices=[DataPractice(type="sensitive_health")],
            human_oversight=HumanOversight(
                oversight_mechanism="approval_required",
                fallback_procedure="Manual",
                review_frequency="per_decision",
                human_authority=True,
            ),
            training_data_source="Medical data",
            documentation=False,
            performance_monitoring=False,
        )

        classifier = RiskClassifier()
        class_a = classifier.classify(descriptor_with_safeguards)
        class_b = classifier.classify(descriptor_without_safeguards)

        # Both should be high-risk but confidence may differ
        assert class_a.tier == RiskTier.HIGH_RISK
        assert class_b.tier == RiskTier.HIGH_RISK
        assert class_a.confidence >= class_b.confidence
