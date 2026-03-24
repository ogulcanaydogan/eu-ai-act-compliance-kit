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


def test_resolve_collaboration_gate_policy_cli_overrides_policy_file():
    """CLI-provided values should override policy file fields deterministically."""
    policy = resolve_collaboration_gate_policy(
        policy_payload={
            "mode": "enforce",
            "scope": {"system": "Fraud Assistant"},
            "window": {"limit": 50},
            "thresholds": {"blocked_max": 2, "unassigned_actionable_max": 3},
        },
        mode="observe",
        blocked_max=0,
    )

    assert policy.mode == "observe"
    assert policy.system_name == "Fraud Assistant"
    assert policy.limit == 50
    assert policy.blocked_max == 0
    assert policy.unassigned_actionable_max == 3


def test_collaboration_gate_observe_reports_violations_without_enforcement():
    """Observe mode should still compute threshold violations and mark failed=true in payload."""
    policy = resolve_collaboration_gate_policy(
        mode="observe",
        blocked_max=0,
        unassigned_actionable_max=0,
    )
    result = CollaborationGateEvaluator().evaluate(
        policy=policy,
        metrics={
            "has_collaboration_data": True,
            "blocked_count": 1,
            "unassigned_actionable_count": 2,
        },
    )

    assert result.mode == "observe"
    assert result.failed is True
    assert "blocked_threshold_exceeded" in result.reason_codes
    assert "unassigned_actionable_threshold_exceeded" in result.reason_codes


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
        },
    )

    assert result.mode == "enforce"
    assert result.failed is True
    assert result.reason_codes == ["missing_collaboration_data"]
