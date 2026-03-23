"""Unit tests for security gate evaluator behavior."""

from __future__ import annotations

import pytest

from eu_ai_act.security_gate import SecurityGateEvaluator


def _summary(
    *,
    non_compliant: int = 0,
    partial: int = 0,
    not_assessed: int = 0,
) -> dict[str, int]:
    return {
        "non_compliant_count": non_compliant,
        "partial_count": partial,
        "not_assessed_count": not_assessed,
    }


def test_observe_mode_never_fails_even_with_issues() -> None:
    evaluator = SecurityGateEvaluator()

    result = evaluator.evaluate(
        security_summary=_summary(non_compliant=2, partial=1, not_assessed=3),
        mode="observe",
        profile="strict",
        risk_tier="high_risk",
    )

    assert result.mode == "observe"
    assert result.profile == "strict"
    assert result.effective_profile == "strict"
    assert result.failed is False
    assert result.reason == "observe_mode_no_blocking"


def test_enforce_strict_fails_on_partial_without_non_compliant() -> None:
    evaluator = SecurityGateEvaluator()
    result = evaluator.evaluate(
        security_summary=_summary(non_compliant=0, partial=1, not_assessed=0),
        mode="enforce",
        profile="strict",
        risk_tier="minimal",
    )
    assert result.failed is True
    assert result.reason == "security_strict_threshold_breached"


def test_enforce_balanced_fails_only_for_non_compliant() -> None:
    evaluator = SecurityGateEvaluator()
    result = evaluator.evaluate(
        security_summary=_summary(non_compliant=0, partial=3, not_assessed=2),
        mode="enforce",
        profile="balanced",
        risk_tier="limited",
    )
    assert result.failed is False
    assert result.reason == "security_balanced_threshold_not_breached"


def test_enforce_lenient_fails_only_when_non_compliant_at_least_two() -> None:
    evaluator = SecurityGateEvaluator()
    result_pass = evaluator.evaluate(
        security_summary=_summary(non_compliant=1),
        mode="enforce",
        profile="lenient",
        risk_tier="minimal",
    )
    result_fail = evaluator.evaluate(
        security_summary=_summary(non_compliant=2),
        mode="enforce",
        profile="lenient",
        risk_tier="minimal",
    )

    assert result_pass.failed is False
    assert result_pass.reason == "security_lenient_threshold_not_breached"
    assert result_fail.failed is True
    assert result_fail.reason == "security_lenient_threshold_breached"


def test_tier_aware_lenient_is_upgraded_to_balanced_for_high_risk() -> None:
    evaluator = SecurityGateEvaluator()

    result = evaluator.evaluate(
        security_summary=_summary(non_compliant=1),
        mode="enforce",
        profile="lenient",
        risk_tier="high_risk",
    )

    assert result.profile == "lenient"
    assert result.effective_profile == "balanced"
    assert result.failed is True
    assert result.reason == "security_balanced_threshold_breached"


def test_tier_aware_lenient_is_upgraded_to_balanced_for_unacceptable() -> None:
    evaluator = SecurityGateEvaluator()

    result = evaluator.evaluate(
        security_summary=_summary(non_compliant=1),
        mode="enforce",
        profile="lenient",
        risk_tier="unacceptable",
    )

    assert result.effective_profile == "balanced"
    assert result.failed is True


def test_invalid_mode_raises_clear_error() -> None:
    evaluator = SecurityGateEvaluator()

    with pytest.raises(ValueError, match="Invalid security gate mode"):
        evaluator.evaluate(security_summary=_summary(), mode="invalid")


def test_invalid_profile_raises_clear_error() -> None:
    evaluator = SecurityGateEvaluator()

    with pytest.raises(ValueError, match="Invalid security gate profile"):
        evaluator.evaluate(security_summary=_summary(), mode="observe", profile="default")


def test_invalid_counts_raise_clear_error() -> None:
    evaluator = SecurityGateEvaluator()

    with pytest.raises(ValueError, match="non_compliant_count must be an integer"):
        evaluator.evaluate(
            security_summary={"non_compliant_count": "oops"},
            mode="observe",
            profile="balanced",
        )

    with pytest.raises(ValueError, match="partial_count must be >= 0"):
        evaluator.evaluate(
            security_summary={"partial_count": -1},
            mode="observe",
            profile="balanced",
        )

    with pytest.raises(ValueError, match="not_assessed_count must be an integer"):
        evaluator.evaluate(
            security_summary={"not_assessed_count": "x"},
            mode="observe",
            profile="balanced",
        )
