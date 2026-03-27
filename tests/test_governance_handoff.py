"""Unit tests for governance handoff aggregation runtime."""

from eu_ai_act.governance_handoff import build_governance_decision


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
