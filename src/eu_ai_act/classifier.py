"""
Risk Classification Engine

Classifies AI systems into risk tiers according to EU AI Act Article 6 and Annex III.
Uses a decision tree based on use case domain, data sensitivity, and autonomy level.
"""

from dataclasses import dataclass, field

from eu_ai_act.schema import AISystemDescriptor, RiskTier, UseCaseDomain


@dataclass
class RiskClassification:
    """
    Result of risk tier classification.

    Attributes:
        tier: Assigned risk tier
        reasoning: Human-readable explanation of the classification
        articles_applicable: List of applicable EU AI Act articles
        confidence: Confidence score (0.0-1.0)
        contributing_factors: List of factors that influenced the classification
    """

    tier: RiskTier
    reasoning: str
    articles_applicable: list[str]
    confidence: float
    contributing_factors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"Risk Tier: {self.tier.value} (confidence: {self.confidence:.0%})\n{self.reasoning}"


class RiskClassifier:
    """
    Classifies AI systems into risk tiers based on EU AI Act requirements.

    The classification is based on:
    1. Use case domain (Annex III high-risk categories)
    2. Data sensitivity (biometric, personal, sensitive data)
    3. Autonomy level (autonomous vs. human-reviewed decisions)
    4. Impact on fundamental rights
    """

    # High-risk categories from EU AI Act Annex III
    HIGH_RISK_DOMAINS = {
        UseCaseDomain.BIOMETRIC,
        UseCaseDomain.CRITICAL_INFRASTRUCTURE,
        UseCaseDomain.LAW_ENFORCEMENT,
        UseCaseDomain.EMPLOYMENT,
        UseCaseDomain.CREDIT_SCORING,
        UseCaseDomain.EDUCATION,
        UseCaseDomain.HEALTHCARE,
    }

    # Prohibited use cases (Article 5)
    PROHIBITED_KEYWORDS = {
        "social scoring",
        "social credit",
        "biometric identification",
        "real-time biometric",
        "behavior manipulation",
        "subliminal",
        "vulnerable",
        "exploit",
    }
    ARTICLES_BY_TIER = {
        RiskTier.UNACCEPTABLE: ["Art. 5"],
        RiskTier.HIGH_RISK: [
            "Art. 6",
            "Art. 10",
            "Art. 11",
            "Art. 13",
            "Art. 14",
            "Art. 15",
            "Art. 43",
        ],
        RiskTier.LIMITED: ["Art. 50", "Art. 51-55"],
        RiskTier.MINIMAL: ["Art. 69"],
    }

    def classify(self, descriptor: AISystemDescriptor) -> RiskClassification:
        """
        Classify an AI system into a risk tier.

        Args:
            descriptor: AI system descriptor

        Returns:
            RiskClassification with tier, reasoning, and applicable articles
        """
        factors: list[str] = []

        # Check for prohibited practices (Article 5)
        prohibited_check = self._check_prohibited(descriptor)
        if prohibited_check:
            factors.extend(prohibited_check["factors"])
            return RiskClassification(
                tier=RiskTier.UNACCEPTABLE,
                reasoning=prohibited_check["reasoning"],
                articles_applicable=self.get_applicable_articles(RiskTier.UNACCEPTABLE),
                confidence=0.95,
                contributing_factors=factors,
            )

        # Check for high-risk indicators
        high_risk_check = self._check_high_risk(descriptor)
        if high_risk_check["is_high_risk"]:
            factors.extend(high_risk_check["factors"])
            return RiskClassification(
                tier=RiskTier.HIGH_RISK,
                reasoning=high_risk_check["reasoning"],
                articles_applicable=self.get_applicable_articles(RiskTier.HIGH_RISK),
                confidence=high_risk_check["confidence"],
                contributing_factors=factors,
            )

        # Check for limited risk (transparency only)
        limited_check = self._check_limited_risk(descriptor)
        if limited_check["is_limited"]:
            factors.extend(limited_check["factors"])
            return RiskClassification(
                tier=RiskTier.LIMITED,
                reasoning=limited_check["reasoning"],
                articles_applicable=self.get_applicable_articles(RiskTier.LIMITED),
                confidence=limited_check["confidence"],
                contributing_factors=factors,
            )

        # Default: minimal risk
        factors.append("No high-risk indicators detected")
        return RiskClassification(
            tier=RiskTier.MINIMAL,
            reasoning="System poses minimal risk. No high-risk characteristics identified.",
            articles_applicable=self.get_applicable_articles(RiskTier.MINIMAL),
            confidence=0.85,
            contributing_factors=factors,
        )

    def _check_prohibited(self, descriptor: AISystemDescriptor) -> dict | None:
        """
        Check for Article 5 prohibited practices.

        Returns:
            Dict with prohibition details, or None if not prohibited
        """
        prohibited_text = (
            descriptor.description.lower()
            + " ".join(uc.description.lower() for uc in descriptor.use_cases)
        ).lower()

        for keyword in self.PROHIBITED_KEYWORDS:
            if keyword in prohibited_text:
                return {
                    "reasoning": (
                        f"System describes or implements '{keyword}', which is prohibited "
                        "under Article 5 of the EU AI Act (2024/1689). This practice is "
                        "banned due to unacceptable risk to fundamental rights and freedoms."
                    ),
                    "factors": [f"Detected prohibited term: '{keyword}'"],
                }

        # Check for explicit social scoring use case
        for use_case in descriptor.use_cases:
            if "social" in use_case.description.lower() and "score" in use_case.description.lower():
                return {
                    "reasoning": (
                        "System implements social scoring, which is explicitly prohibited under "
                        "Article 5(1)(a) of the EU AI Act. Social credit systems cannot be deployed."
                    ),
                    "factors": ["Explicit social scoring use case"],
                }

        return None

    def _check_high_risk(self, descriptor: AISystemDescriptor) -> dict:
        """
        Check for high-risk indicators (Article 6, Annex III).

        Returns:
            Dict with high-risk assessment
        """
        factors: list[str] = []
        confidence = 0.0

        # Check use case domain
        high_risk_domains = [
            uc for uc in descriptor.use_cases if uc.domain in self.HIGH_RISK_DOMAINS
        ]
        if high_risk_domains:
            factors.append(
                f"High-risk domain detected: {', '.join(uc.domain.value for uc in high_risk_domains)}"
            )
            confidence = 0.90

        rights_impact = any(uc.impacts_fundamental_rights for uc in descriptor.use_cases)
        if rights_impact:
            factors.append("System decisions significantly impact fundamental rights")
            confidence = max(confidence, 0.80)

        autonomous_decisions = any(uc.autonomous_decision for uc in descriptor.use_cases)
        if autonomous_decisions and rights_impact:
            factors.append("System makes autonomous decisions in rights-impacting contexts")
            confidence = max(confidence, 0.85)

        biometric_data = [dp for dp in descriptor.data_practices if "biometric" in dp.type.lower()]
        if biometric_data:
            factors.append("System processes biometric data")
            confidence = max(confidence, 0.95)

        sensitive_data = [
            dp
            for dp in descriptor.data_practices
            if ("sensitive" in dp.type.lower() or "health" in dp.type.lower())
            and not dp.explicit_consent
        ]
        if sensitive_data:
            factors.append("System processes sensitive data without explicit consent")
            confidence = max(confidence, 0.80)

        personal_without_consent = [
            dp
            for dp in descriptor.data_practices
            if dp.type.lower() == "personal" and not dp.explicit_consent
        ]
        if personal_without_consent:
            factors.append("System processes personal data without explicit consent")

        has_human_override = descriptor.human_oversight.human_authority
        if not has_human_override:
            factors.append("System does not allow human override of decisions")
            confidence = max(confidence, 0.80)

        if not descriptor.documentation:
            factors.append("System lacks comprehensive technical documentation")
            confidence = max(confidence, 0.70)

        if not descriptor.performance_monitoring:
            factors.append("System performance is not continuously monitored")
            confidence = max(confidence, 0.75)

        strong_signal_count = 0
        if biometric_data:
            strong_signal_count += 1
        if sensitive_data:
            strong_signal_count += 1
        if autonomous_decisions and rights_impact:
            strong_signal_count += 1
        if not has_human_override:
            strong_signal_count += 1

        # Narrowed rule:
        # - Annex III domain => high-risk
        # - Otherwise require rights impact plus at least one strong signal
        is_high_risk = bool(high_risk_domains) or (rights_impact and strong_signal_count >= 1)

        reasoning = (
            "System is classified as high-risk under Article 6 and Annex III of the EU AI Act. "
            "It must comply with comprehensive requirements including data governance, documentation, "
            "transparency, human oversight, and continuous monitoring. "
        )
        if factors:
            reasoning += f"Key factors: {'; '.join(factors)}."

        return {
            "is_high_risk": is_high_risk,
            "reasoning": reasoning,
            "factors": factors,
            "confidence": min(confidence, 0.95),
        }

    def _check_limited_risk(self, descriptor: AISystemDescriptor) -> dict:
        """
        Check for limited-risk systems (Article 50, transparency obligations).

        Returns:
            Dict with limited-risk assessment
        """
        factors: list[str] = []
        confidence = 0.0

        # Check for AI-generated content that requires disclosure
        for use_case in descriptor.use_cases:
            desc_lower = use_case.description.lower()
            if any(
                keyword in desc_lower
                for keyword in ["deepfake", "synthetic", "generated", "chatbot", "text generation"]
            ):
                factors.append(
                    f"System generates AI-synthesized content requiring disclosure ({use_case.domain.value})"
                )
                confidence = max(confidence, 0.85)

        # Check for general-purpose AI models
        training_lower = descriptor.training_data_source.lower()
        if any(
            keyword in training_lower
            for keyword in ["general purpose", "broad training", "large language", "multimodal"]
        ):
            factors.append("System appears to be a general-purpose AI model")
            confidence = max(confidence, 0.80)

        is_limited = confidence >= 0.75

        reasoning = (
            "System is classified as limited-risk requiring transparency obligations under "
            "Article 50 and Articles 51-55 (GPAI). The primary requirement is clear disclosure "
            "of AI-generated or AI-synthesized content. "
        )
        if factors:
            reasoning += f"Key factors: {'; '.join(factors)}."

        return {
            "is_limited": is_limited,
            "reasoning": reasoning,
            "factors": factors,
            "confidence": min(confidence, 0.90),
        }

    def get_applicable_articles(self, tier: RiskTier) -> list[str]:
        """
        Get list of applicable EU AI Act articles for a given risk tier.

        Args:
            tier: Risk tier

        Returns:
            List of applicable article references
        """
        return self.ARTICLES_BY_TIER.get(tier, [])
