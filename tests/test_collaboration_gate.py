"""Unit tests for collaboration governance gate evaluator behavior."""

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
