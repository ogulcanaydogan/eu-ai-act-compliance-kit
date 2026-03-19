"""
EU AI Act Articles Database

Structured database of relevant articles from EU AI Act (Regulation 2024/1689).
Contains article titles, summaries, requirements, and deadlines.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from eu_ai_act.schema import RiskTier


@dataclass
class Article:
    """
    Represents a single EU AI Act article.

    Attributes:
        article_id: Article number (e.g., "6", "10", "11")
        title: Article title
        summary: Brief summary of requirements
        full_text: Complete article text
        risk_tiers: Which risk tiers are affected
        requirements: List of specific requirements
        deadline_months: Months from enforcement to comply
        related_articles: Cross-references to related articles
    """
    article_id: str
    title: str
    summary: str
    full_text: str
    risk_tiers: List[RiskTier]
    requirements: List[str]
    deadline_months: int
    related_articles: List[str]


class ArticleDatabase:
    """Database of EU AI Act articles and requirements."""

    def __init__(self):
        """Initialize article database."""
        self._articles = self._load_articles()

    def get_article(self, article_id: str) -> Optional[Article]:
        """
        Retrieve an article by ID.

        Args:
            article_id: Article number (e.g., "6", "10")

        Returns:
            Article object or None if not found
        """
        return self._articles.get(article_id)

    def get_articles_by_tier(self, tier: RiskTier) -> List[Article]:
        """
        Get all articles applicable to a risk tier.

        Args:
            tier: Risk tier

        Returns:
            List of applicable articles
        """
        return [article for article in self._articles.values() if tier in article.risk_tiers]

    def get_requirements_by_tier(self, tier: RiskTier) -> Dict[str, List[str]]:
        """
        Get all requirements for a risk tier.

        Args:
            tier: Risk tier

        Returns:
            Dictionary mapping article IDs to requirement lists
        """
        requirements: Dict[str, List[str]] = {}
        for article in self.get_articles_by_tier(tier):
            requirements[article.article_id] = article.requirements
        return requirements

    def _load_articles(self) -> Dict[str, Article]:
        """Load all articles from database."""
        return {
            "5": Article(
                article_id="5",
                title="Prohibited practices",
                summary="Prohibits AI systems that create unacceptable risk to fundamental rights.",
                full_text="Article 5 prohibits specific AI practices from market placement and use.",
                risk_tiers=[RiskTier.UNACCEPTABLE],
                requirements=[
                    "Do not deploy social scoring systems.",
                    "Do not use prohibited manipulative or exploitative AI practices.",
                    "Do not place prohibited biometric surveillance systems on the market without legal basis.",
                ],
                deadline_months=0,
                related_articles=["69"],
            ),
            "6": Article(
                article_id="6",
                title="Classification of high-risk AI systems",
                summary="Defines criteria and categories for high-risk AI systems.",
                full_text="Article 6 defines high-risk qualification and links to Annex III categories.",
                risk_tiers=[RiskTier.HIGH_RISK],
                requirements=[
                    "Classify systems against Annex III high-risk categories.",
                    "Apply high-risk obligations (Arts. 10-15 and conformity assessment).",
                ],
                deadline_months=24,
                related_articles=["10", "11", "13", "14", "15", "43"],
            ),
            "50": Article(
                article_id="50",
                title="Transparency obligations for certain AI systems",
                summary="Requires disclosure for AI interactions and synthetic/generated content.",
                full_text="Article 50 establishes disclosure duties for AI-generated or manipulated content.",
                risk_tiers=[RiskTier.LIMITED, RiskTier.HIGH_RISK],
                requirements=[
                    "Inform users when they interact with an AI system where required.",
                    "Disclose AI-generated or manipulated content as applicable.",
                    "Ensure synthetic/deepfake-like outputs are appropriately labeled or disclosed.",
                ],
                deadline_months=6,
                related_articles=["51", "52", "55"],
            ),
            "51": Article(
                article_id="51",
                title="GPAI documentation obligations",
                summary="Requires technical and training-data related documentation for GPAI models.",
                full_text="Article 51 requires documentation enabling downstream compliance and oversight.",
                risk_tiers=[RiskTier.LIMITED, RiskTier.HIGH_RISK],
                requirements=[
                    "Maintain technical documentation for GPAI models.",
                    "Document training data and relevant governance information.",
                ],
                deadline_months=24,
                related_articles=["52", "55"],
            ),
            "52": Article(
                article_id="52",
                title="GPAI model cards and capability transparency",
                summary="Requires transparency on GPAI model capabilities and known limitations.",
                full_text="Article 52 requires model-card style disclosures and capability information.",
                risk_tiers=[RiskTier.LIMITED, RiskTier.HIGH_RISK],
                requirements=[
                    "Provide model-card level capability and limitation information.",
                    "Disclose known risks and operational constraints to downstream actors.",
                ],
                deadline_months=24,
                related_articles=["51", "53", "55"],
            ),
            "53": Article(
                article_id="53",
                title="Systemic risk assessment for GPAI",
                summary="Requires systemic-risk assessment processes for qualifying GPAI models.",
                full_text="Article 53 introduces systemic-risk assessment obligations for designated GPAI models.",
                risk_tiers=[RiskTier.HIGH_RISK],
                requirements=[
                    "Assess whether the model presents systemic risk signals.",
                    "Document and maintain systemic-risk assessment evidence.",
                ],
                deadline_months=24,
                related_articles=["52", "54"],
            ),
            "54": Article(
                article_id="54",
                title="Systemic risk mitigation measures",
                summary="Requires mitigation and monitoring controls for systemic-risk GPAI models.",
                full_text="Article 54 requires mitigation plans and operational controls for systemic-risk models.",
                risk_tiers=[RiskTier.HIGH_RISK],
                requirements=[
                    "Define mitigation controls for identified systemic risks.",
                    "Operate post-market monitoring and incident response workflows.",
                ],
                deadline_months=24,
                related_articles=["53", "55"],
            ),
            "55": Article(
                article_id="55",
                title="Downstream information and compliance enablement",
                summary="Requires providing information so downstream providers/deployers can comply.",
                full_text="Article 55 focuses on downstream transparency and compliance-enabling information.",
                risk_tiers=[RiskTier.LIMITED, RiskTier.HIGH_RISK],
                requirements=[
                    "Provide sufficient documentation for downstream compliance activities.",
                    "Disclose usage constraints and relevant safety information.",
                ],
                deadline_months=24,
                related_articles=["50", "51", "52"],
            ),
        }
