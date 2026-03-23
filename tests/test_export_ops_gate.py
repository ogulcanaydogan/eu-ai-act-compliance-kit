"""Unit tests for export operations governance policy evaluator."""

from eu_ai_act.export_ops_gate import ExportOpsGateEvaluator, resolve_export_ops_gate_policy


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
