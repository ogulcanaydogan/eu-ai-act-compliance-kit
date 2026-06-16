"""Tests for ArticleDatabase — article retrieval and tier-based queries."""

from eu_ai_act.articles import Article, ArticleDatabase
from eu_ai_act.schema import RiskTier


class TestArticleDatabase:
    """Coverage for ArticleDatabase public interface."""

    def setup_method(self) -> None:
        self.db = ArticleDatabase()

    # --- get_article ---

    def test_get_known_article_returns_article(self) -> None:
        article = self.db.get_article("6")
        assert article is not None
        assert isinstance(article, Article)
        assert article.article_id == "6"

    def test_get_article_has_expected_fields(self) -> None:
        article = self.db.get_article("5")
        assert article is not None
        assert article.title
        assert article.summary
        assert article.requirements
        assert isinstance(article.risk_tiers, list)
        assert isinstance(article.related_articles, list)

    def test_get_unknown_article_returns_none(self) -> None:
        assert self.db.get_article("999") is None

    def test_get_article_empty_string_returns_none(self) -> None:
        assert self.db.get_article("") is None

    # --- get_articles_by_tier ---

    def test_high_risk_articles_returned(self) -> None:
        articles = self.db.get_articles_by_tier(RiskTier.HIGH_RISK)
        assert len(articles) > 0
        for article in articles:
            assert RiskTier.HIGH_RISK in article.risk_tiers

    def test_unacceptable_tier_returns_article_5(self) -> None:
        articles = self.db.get_articles_by_tier(RiskTier.UNACCEPTABLE)
        ids = [a.article_id for a in articles]
        assert "5" in ids

    def test_limited_tier_returns_articles(self) -> None:
        articles = self.db.get_articles_by_tier(RiskTier.LIMITED)
        assert len(articles) > 0
        for article in articles:
            assert RiskTier.LIMITED in article.risk_tiers

    def test_minimal_tier_returns_empty(self) -> None:
        # No article in the DB targets MINIMAL risk tier
        articles = self.db.get_articles_by_tier(RiskTier.MINIMAL)
        assert articles == []

    # --- get_requirements_by_tier ---

    def test_requirements_by_tier_structure(self) -> None:
        reqs = self.db.get_requirements_by_tier(RiskTier.HIGH_RISK)
        assert isinstance(reqs, dict)
        for article_id, requirements in reqs.items():
            assert isinstance(article_id, str)
            assert isinstance(requirements, list)
            assert len(requirements) > 0

    def test_requirements_by_tier_matches_articles(self) -> None:
        articles = self.db.get_articles_by_tier(RiskTier.HIGH_RISK)
        reqs = self.db.get_requirements_by_tier(RiskTier.HIGH_RISK)
        article_ids = {a.article_id for a in articles}
        assert set(reqs.keys()) == article_ids

    def test_requirements_by_unacceptable_tier(self) -> None:
        reqs = self.db.get_requirements_by_tier(RiskTier.UNACCEPTABLE)
        assert "5" in reqs
        assert len(reqs["5"]) > 0
