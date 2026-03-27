"""Unit tests for governance handoff aggregation runtime."""

import pytest

from eu_ai_act.governance_handoff import (
    build_governance_decision,
    resolve_governance_handoff_policy,
)


def test_build_governance_decision_aggregates_failed_gates_and_reasons():
    decision = build_governance_decision(
        mode="enforce",
        security_gate={
            "failed": True,
            "reason": "security_balanced_threshold_breached",
        },
        collaboration_gate={
            "failed": True,
            "reason_codes": ["blocked_threshold_exceeded"],
        },
        export_ops_gate={
            "failed": False,
            "reason_codes": [],
        },
    )

    assert decision.mode == "enforce"
    assert decision.failed is True
    assert decision.evaluated_gates == ["security_gate", "collaboration_gate", "export_ops_gate"]
    assert decision.failed_gates == ["security_gate", "collaboration_gate"]
    assert decision.reason_codes == [
        "security:security_balanced_threshold_breached",
        "collaboration:blocked_threshold_exceeded",
    ]


def test_build_governance_decision_skips_optional_export_gate_when_not_provided():
    decision = build_governance_decision(
        mode="observe",
        security_gate={"failed": False, "reason": "observe_mode_no_blocking"},
        collaboration_gate={"failed": False, "reason_codes": []},
        export_ops_gate=None,
    )

    assert decision.mode == "observe"
    assert decision.failed is False
    assert decision.evaluated_gates == ["security_gate", "collaboration_gate"]
    assert decision.failed_gates == []
    assert decision.reason_codes == []
    assert decision.export_ops_gate is None


def test_resolve_governance_handoff_policy_defaults():
    policy = resolve_governance_handoff_policy()

    assert policy.mode == "observe"
    assert policy.security_enabled is True
    assert policy.collaboration_enabled is True
    assert policy.export_ops_enabled is False
    assert policy.security_profile == "balanced"
    assert policy.export_target is None


def test_resolve_governance_handoff_policy_cli_overrides_file_values():
    policy = resolve_governance_handoff_policy(
        policy_payload={
            "mode": "enforce",
            "gates": {
                "security": False,
                "collaboration": False,
                "export_ops": False,
            },
            "security": {"profile": "strict"},
            "export_ops": {"target": "servicenow"},
        },
        mode="observe",
        security_enabled=True,
        collaboration_enabled=True,
        export_target="jira",
        security_profile="balanced",
    )

    assert policy.mode == "observe"
    assert policy.security_enabled is True
    assert policy.collaboration_enabled is True
    assert policy.export_ops_enabled is True
    assert policy.export_target == "jira"
    assert policy.security_profile == "balanced"


def test_resolve_governance_handoff_policy_enforce_missing_export_target_fails():
    with pytest.raises(ValueError, match="export target is missing"):
        resolve_governance_handoff_policy(
            policy_payload={"gates": {"export_ops": True}},
        )
