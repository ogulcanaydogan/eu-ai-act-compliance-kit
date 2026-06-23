"""Unit tests for collaboration governance gate evaluator behavior."""

import pytest

from eu_ai_act.collaboration_gate import (
    CollaborationGateEvaluator,
    resolve_collaboration_gate_policy,
)


def test_resolve_collaboration_gate_policy_defaults():
    """Resolver should return deterministic defaults when no input is provided."""
    policy = resolve_collaboration_gate_policy()

    assert policy.mode == "observe"
    assert policy.system_name is None
    assert policy.limit == 200
    assert policy.blocked_max == 0
    assert policy.unassigned_actionable_max == 0
    assert policy.stale_actionable_max is None
    assert policy.blocked_stale_max is None
    assert policy.review_stale_max is None
    assert policy.stale_after_hours == 72.0
    assert policy.blocked_stale_after_hours == 72.0
    assert policy.review_stale_after_hours == 48.0


def test_resolve_collaboration_gate_policy_cli_overrides_policy_file():
    """CLI-provided values should override policy file fields deterministically."""
    policy = resolve_collaboration_gate_policy(
        policy_payload={
            "mode": "enforce",
            "scope": {"system": "Fraud Assistant"},
            "window": {"limit": 50},
            "thresholds": {
                "blocked_max": 2,
                "unassigned_actionable_max": 3,
                "stale_actionable_max": 4,
                "blocked_stale_max": 5,
                "review_stale_max": 6,
            },
            "sla": {
                "stale_after_hours": 24,
                "blocked_stale_after_hours": 12,
                "review_stale_after_hours": 8,
            },
        },
        mode="observe",
        blocked_max=0,
        stale_after_hours=36,
    )

    assert policy.mode == "observe"
    assert policy.system_name == "Fraud Assistant"
    assert policy.limit == 50
    assert policy.blocked_max == 0
    assert policy.unassigned_actionable_max == 3
    assert policy.stale_actionable_max == 4
    assert policy.blocked_stale_max == 5
    assert policy.review_stale_max == 6
    assert policy.stale_after_hours == 36
    assert policy.blocked_stale_after_hours == 12
    assert policy.review_stale_after_hours == 8


def test_collaboration_gate_observe_reports_violations_without_enforcement():
    """Observe mode should still compute threshold violations and mark failed=true in payload."""
    policy = resolve_collaboration_gate_policy(
        mode="observe",
        blocked_max=0,
        unassigned_actionable_max=0,
        stale_actionable_max=0,
        blocked_stale_max=0,
        review_stale_max=0,
    )
    result = CollaborationGateEvaluator().evaluate(
        policy=policy,
        metrics={
            "has_collaboration_data": True,
            "blocked_count": 1,
            "unassigned_actionable_count": 2,
            "stale_actionable_count": 1,
            "blocked_stale_count": 1,
            "review_stale_count": 1,
        },
    )

    assert result.mode == "observe"
    assert result.failed is True
    assert "blocked_threshold_exceeded" in result.reason_codes
    assert "unassigned_actionable_threshold_exceeded" in result.reason_codes
    assert "stale_actionable_threshold_exceeded" in result.reason_codes
    assert "blocked_stale_threshold_exceeded" in result.reason_codes
    assert "review_stale_threshold_exceeded" in result.reason_codes


def test_collaboration_gate_enforce_fails_when_collaboration_data_missing():
    """Enforce mode should fail deterministically when collaboration data is missing."""
    policy = resolve_collaboration_gate_policy(
        mode="enforce",
        blocked_max=0,
        unassigned_actionable_max=0,
    )
    result = CollaborationGateEvaluator().evaluate(
        policy=policy,
        metrics={
            "has_collaboration_data": False,
            "blocked_count": 0,
            "unassigned_actionable_count": 0,
            "stale_actionable_count": 0,
            "blocked_stale_count": 0,
            "review_stale_count": 0,
        },
    )

    assert result.mode == "enforce"
    assert result.failed is True
    assert result.reason_codes == ["missing_collaboration_data"]


def test_collaboration_gate_stale_thresholds_disabled_when_not_configured():
    """Stale counts should not trigger failures when stale thresholds are unset."""
    policy = resolve_collaboration_gate_policy(
        mode="enforce",
        blocked_max=100,
        unassigned_actionable_max=100,
    )
    result = CollaborationGateEvaluator().evaluate(
        policy=policy,
        metrics={
            "has_collaboration_data": True,
            "blocked_count": 0,
            "unassigned_actionable_count": 0,
            "stale_actionable_count": 50,
            "blocked_stale_count": 25,
            "review_stale_count": 25,
        },
    )

    assert result.failed is False
    assert result.reason_codes == []


def test_collaboration_gate_enforce_passes_with_data_and_zero_violations():
    """Enforce mode should pass when data is present and no thresholds are violated."""
    policy = resolve_collaboration_gate_policy(
        mode="enforce",
        blocked_max=0,
        unassigned_actionable_max=0,
    )
    result = CollaborationGateEvaluator().evaluate(
        policy=policy,
        metrics={
            "has_collaboration_data": True,
            "blocked_count": 0,
            "unassigned_actionable_count": 0,
            "stale_actionable_count": 0,
            "blocked_stale_count": 0,
            "review_stale_count": 0,
        },
    )

    assert result.mode == "enforce"
    assert result.failed is False
    assert result.reason_codes == []


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"policy_payload": "not-a-dict"}, "must be a mapping object"),
        ({"policy_payload": {"scope": "x"}}, r"'scope' must be an object"),
        ({"policy_payload": {"window": "x"}}, r"'window' must be an object"),
        ({"policy_payload": {"thresholds": "x"}}, r"'thresholds' must be an object"),
        ({"policy_payload": {"sla": "x"}}, r"'sla' must be an object"),
        ({"mode": "audit"}, "mode must be one of"),
        ({"policy_payload": {"scope": {"system": 123}}}, "scope.system must be null or a string"),
        ({"limit": 0}, r"window.limit must be >= 1"),
        ({"blocked_max": -1}, r"blocked_max must be >= 0"),
        ({"unassigned_actionable_max": -1}, r"unassigned_actionable_max must be >= 0"),
        ({"stale_actionable_max": -1}, r"stale_actionable_max must be >= 0"),
        ({"blocked_stale_max": -1}, r"blocked_stale_max must be >= 0"),
        ({"review_stale_max": -1}, r"review_stale_max must be >= 0"),
        ({"stale_after_hours": 0}, r"stale_after_hours must be > 0"),
        ({"blocked_stale_after_hours": 0}, r"blocked_stale_after_hours must be > 0"),
        ({"review_stale_after_hours": 0}, r"review_stale_after_hours must be > 0"),
    ],
)
def test_resolve_collaboration_gate_policy_rejects_invalid_values(kwargs, match):
    """The resolver should reject malformed policy fields with an actionable error."""
    with pytest.raises(ValueError, match=match):
        resolve_collaboration_gate_policy(**kwargs)


def test_collaboration_gate_policy_to_dict_round_trips():
    """Policy.to_dict() should produce a payload the resolver can re-ingest unchanged."""
    policy = resolve_collaboration_gate_policy(
        policy_payload={
            "mode": "enforce",
            "scope": {"system": "Fraud Assistant"},
            "window": {"limit": 50},
            "thresholds": {
                "blocked_max": 2,
                "unassigned_actionable_max": 3,
                "stale_actionable_max": 4,
                "blocked_stale_max": 5,
                "review_stale_max": 6,
            },
            "sla": {
                "stale_after_hours": 24,
                "blocked_stale_after_hours": 12,
                "review_stale_after_hours": 8,
            },
        }
    )

    payload = policy.to_dict()
    assert payload["mode"] == "enforce"
    assert payload["scope"]["system"] == "Fraud Assistant"
    assert payload["window"]["limit"] == 50
    assert payload["thresholds"]["blocked_max"] == 2
    assert payload["thresholds"]["review_stale_max"] == 6
    assert payload["sla"]["review_stale_after_hours"] == 8

    # Re-resolving the serialized payload yields an equivalent policy.
    assert resolve_collaboration_gate_policy(policy_payload=payload) == policy


def test_collaboration_gate_result_to_dict_returns_defensive_copies():
    """Result.to_dict() should expose decision data as copies, not shared references."""
    policy = resolve_collaboration_gate_policy(mode="observe", blocked_max=0)
    result = CollaborationGateEvaluator().evaluate(
        policy=policy,
        metrics={
            "has_collaboration_data": True,
            "blocked_count": 1,
            "unassigned_actionable_count": 0,
            "stale_actionable_count": 0,
            "blocked_stale_count": 0,
            "review_stale_count": 0,
        },
    )

    payload = result.to_dict()
    assert payload["mode"] == "observe"
    assert payload["failed"] is True
    assert "blocked_threshold_exceeded" in payload["reason_codes"]
    assert isinstance(payload["decision_details"], dict)

    # Mutating the serialized copy must not affect the frozen result.
    payload["reason_codes"].append("mutated")
    assert "mutated" not in result.reason_codes


def test_resolve_collaboration_gate_policy_system_name_override():
    """The system_name keyword should override the policy file scope and be trimmed."""
    policy = resolve_collaboration_gate_policy(
        policy_payload={"scope": {"system": "From File"}},
        system_name="  Fraud Detector  ",
    )

    assert policy.system_name == "Fraud Detector"
