"""Unit tests for security gate evaluator behavior."""

from __future__ import annotations

import pytest

from eu_ai_act.security_gate import SecurityGateEvaluator


def test_observe_mode_never_fails() -> None:
    evaluator = SecurityGateEvaluator()

    result = evaluator.evaluate(
        security_summary={"framework": "owasp-llm-top-10", "non_compliant_count": 4},
        mode="observe",
    )

    assert result.mode == "observe"
    assert result.failed is False
    assert result.non_compliant_count == 4
    assert result.reason == "observe_mode_no_blocking"


def test_enforce_mode_fails_when_non_compliant_controls_exist() -> None:
    evaluator = SecurityGateEvaluator()

    result = evaluator.evaluate(
        security_summary={"framework": "owasp-llm-top-10", "non_compliant_count": 1},
        mode="enforce",
    )

    assert result.mode == "enforce"
    assert result.failed is True
    assert result.reason == "security_non_compliant_controls_detected"


def test_enforce_mode_passes_when_non_compliant_controls_absent() -> None:
    evaluator = SecurityGateEvaluator()

    result = evaluator.evaluate(
        security_summary={"framework": "owasp-llm-top-10", "non_compliant_count": 0},
        mode="enforce",
    )

    assert result.mode == "enforce"
    assert result.failed is False
    assert result.reason == "security_non_compliant_controls_not_detected"


def test_invalid_mode_raises_clear_error() -> None:
    evaluator = SecurityGateEvaluator()

    with pytest.raises(ValueError, match="Invalid security gate mode"):
        evaluator.evaluate(security_summary={"non_compliant_count": 0}, mode="strict")


def test_invalid_non_compliant_count_raises_clear_error() -> None:
    evaluator = SecurityGateEvaluator()

    with pytest.raises(ValueError, match="must be an integer"):
        evaluator.evaluate(security_summary={"non_compliant_count": "oops"}, mode="observe")
