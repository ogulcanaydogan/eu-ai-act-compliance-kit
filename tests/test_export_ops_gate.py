"""Unit tests for export operations governance policy evaluator."""

import pytest

from eu_ai_act.export_ops_gate import (
    ExportOpsGateEvaluator,
    ExportOpsGateResult,
    resolve_export_ops_gate_policy,
)


def test_resolve_export_ops_gate_policy_defaults():
    """Policy resolver should return deterministic defaults when no input is provided."""
    policy = resolve_export_ops_gate_policy()

    assert policy.mode == "observe"
    assert policy.since_hours == 24.0
    assert policy.limit == 200
    assert policy.open_failures_max == 0
    assert policy.drift_max == 0
    assert policy.min_success_rate == 95.0


def test_resolve_export_ops_gate_policy_cli_overrides_policy_file_values():
    """CLI-provided values should override policy-file values deterministically."""
    policy = resolve_export_ops_gate_policy(
        policy_payload={
            "mode": "enforce",
            "window": {"since_hours": 12, "limit": 50},
            "thresholds": {
                "open_failures_max": 1,
                "drift_max": 2,
                "min_success_rate": 80.0,
            },
        },
        mode="observe",
        min_success_rate=97.5,
    )

    assert policy.mode == "observe"
    assert policy.since_hours == 12.0
    assert policy.limit == 50
    assert policy.open_failures_max == 1
    assert policy.drift_max == 2
    assert policy.min_success_rate == 97.5


def test_export_ops_gate_evaluator_observe_mode_tracks_threshold_breaches():
    """Observe mode should compute failures/reasons without implying enforcement behavior."""
    policy = resolve_export_ops_gate_policy(
        mode="observe",
        open_failures_max=0,
        drift_max=0,
        min_success_rate=95.0,
    )
    result = ExportOpsGateEvaluator().evaluate(
        policy=policy,
        rollup_metrics={"open_failures_count": 1, "success_rate": 90.0},
        reconcile_metrics={"drift_count": 1, "has_reconcile_data": True},
    )

    assert result.mode == "observe"
    assert result.failed is True
    assert "open_failures_threshold_exceeded" in result.reason_codes
    assert "drift_threshold_exceeded" in result.reason_codes
    assert "success_rate_below_threshold" in result.reason_codes


def test_export_ops_gate_evaluator_enforce_fails_when_reconcile_data_missing():
    """Enforce mode should fail deterministically when reconcile data is missing."""
    policy = resolve_export_ops_gate_policy(
        mode="enforce",
        open_failures_max=0,
        drift_max=0,
        min_success_rate=95.0,
    )
    result = ExportOpsGateEvaluator().evaluate(
        policy=policy,
        rollup_metrics={"open_failures_count": 0, "success_rate": 100.0},
        reconcile_metrics={"drift_count": 0, "has_reconcile_data": False},
    )

    assert result.mode == "enforce"
    assert result.failed is True
    assert result.reason_codes == ["missing_reconcile_data"]


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"policy_payload": []}, "Policy file must be a mapping object."),
        ({"policy_payload": {"window": "x"}}, "Policy field 'window' must be an object."),
        ({"policy_payload": {"thresholds": 5}}, "Policy field 'thresholds' must be an object."),
        ({"mode": "blocking"}, "Policy mode must be one of: observe, enforce."),
        ({"since_hours": -1}, "Policy window.since_hours must be >= 0."),
        ({"limit": 0}, "Policy window.limit must be >= 1."),
        ({"open_failures_max": -1}, "Policy thresholds.open_failures_max must be >= 0."),
        ({"drift_max": -1}, "Policy thresholds.drift_max must be >= 0."),
        (
            {"min_success_rate": 101},
            "Policy thresholds.min_success_rate must be between 0 and 100.",
        ),
        ({"min_success_rate": -1}, "Policy thresholds.min_success_rate must be between 0 and 100."),
    ],
)
def test_resolve_export_ops_gate_policy_validation_errors(kwargs, match):
    """Invalid policy inputs should raise descriptive ValueErrors."""
    with pytest.raises(ValueError, match=match):
        resolve_export_ops_gate_policy(**kwargs)


def test_export_ops_gate_policy_to_dict_round_trips():
    """Policy.to_dict output should round-trip back through the resolver unchanged."""
    policy = resolve_export_ops_gate_policy(
        mode="enforce",
        since_hours=12,
        limit=50,
        open_failures_max=1,
        drift_max=2,
        min_success_rate=90.0,
    )

    restored = resolve_export_ops_gate_policy(policy_payload=policy.to_dict())

    assert restored == policy


def test_resolve_export_ops_gate_policy_direct_window_overrides():
    """Direct since_hours/limit kwargs should override defaults without a policy file."""
    policy = resolve_export_ops_gate_policy(since_hours=12, limit=50)

    assert policy.since_hours == 12.0
    assert policy.limit == 50


def test_resolve_export_ops_gate_policy_normalizes_mode_casing():
    """Mode should be normalized (trimmed + lowercased) before validation."""
    policy = resolve_export_ops_gate_policy(mode="  Enforce  ")

    assert policy.mode == "enforce"


def test_export_ops_gate_result_to_dict_returns_defensive_copies():
    """to_dict should serialize all fields and not leak mutations back to the result."""
    policy = resolve_export_ops_gate_policy(mode="observe", open_failures_max=0)
    result = ExportOpsGateEvaluator().evaluate(
        policy=policy,
        rollup_metrics={"open_failures_count": 3, "success_rate": 100.0},
        reconcile_metrics={"drift_count": 0, "has_reconcile_data": True},
    )

    assert isinstance(result, ExportOpsGateResult)
    payload = result.to_dict()
    assert payload["mode"] == "observe"
    assert payload["failed"] is True
    assert payload["reason_codes"] == ["open_failures_threshold_exceeded"]
    assert set(payload["decision_details"]) == {
        "open_failures",
        "drift",
        "success_rate",
        "reconcile_data",
    }

    # Mutating the returned payload must not affect the frozen result.
    payload["reason_codes"].append("injected")
    payload["decision_details"]["injected_key"] = True
    assert result.reason_codes == ["open_failures_threshold_exceeded"]
    assert "injected_key" not in result.decision_details
