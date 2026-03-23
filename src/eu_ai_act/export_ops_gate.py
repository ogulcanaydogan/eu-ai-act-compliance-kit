"""Policy-based operations gate evaluator for export reliability metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

ExportOpsGateMode = Literal["observe", "enforce"]


@dataclass(frozen=True)
class ExportOpsGatePolicy:
    """Resolved policy thresholds used by export ops gate evaluation."""

    mode: ExportOpsGateMode
    since_hours: float
    limit: int
    open_failures_max: int
    drift_max: int
    min_success_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "window": {
                "since_hours": self.since_hours,
                "limit": self.limit,
            },
            "thresholds": {
                "open_failures_max": self.open_failures_max,
                "drift_max": self.drift_max,
                "min_success_rate": self.min_success_rate,
            },
        }


@dataclass(frozen=True)
class ExportOpsGateResult:
    """Deterministic result returned by export ops gate evaluator."""

    mode: ExportOpsGateMode
    failed: bool
    reason_codes: list[str]
    decision_details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "failed": self.failed,
            "reason_codes": list(self.reason_codes),
            "decision_details": dict(self.decision_details),
        }


class ExportOpsGateEvaluator:
    """Evaluate ops rollup + reconcile metrics against deterministic gate policy."""

    def evaluate(
        self,
        *,
        policy: ExportOpsGatePolicy,
        rollup_metrics: dict[str, Any],
        reconcile_metrics: dict[str, Any],
    ) -> ExportOpsGateResult:
        open_failures_count = int(rollup_metrics.get("open_failures_count", 0) or 0)
        success_rate = float(rollup_metrics.get("success_rate", 0.0) or 0.0)
        drift_count = int(reconcile_metrics.get("drift_count", 0) or 0)
        has_reconcile_data = bool(reconcile_metrics.get("has_reconcile_data", False))

        open_failures_violation = open_failures_count > policy.open_failures_max
        drift_violation = drift_count > policy.drift_max
        success_rate_violation = success_rate < policy.min_success_rate
        missing_reconcile_violation = policy.mode == "enforce" and not has_reconcile_data

        reason_codes: list[str] = []
        if missing_reconcile_violation:
            reason_codes.append("missing_reconcile_data")
        if open_failures_violation:
            reason_codes.append("open_failures_threshold_exceeded")
        if drift_violation:
            reason_codes.append("drift_threshold_exceeded")
        if success_rate_violation:
            reason_codes.append("success_rate_below_threshold")

        failed = bool(reason_codes)
        decision_details = {
            "open_failures": {
                "actual": open_failures_count,
                "threshold_max": policy.open_failures_max,
                "violated": open_failures_violation,
            },
            "drift": {
                "actual": drift_count,
                "threshold_max": policy.drift_max,
                "violated": drift_violation,
            },
            "success_rate": {
                "actual": success_rate,
                "threshold_min": policy.min_success_rate,
                "violated": success_rate_violation,
            },
            "reconcile_data": {
                "has_reconcile_data": has_reconcile_data,
                "violated": missing_reconcile_violation,
            },
        }
        return ExportOpsGateResult(
            mode=policy.mode,
            failed=failed,
            reason_codes=reason_codes,
            decision_details=decision_details,
        )


def resolve_export_ops_gate_policy(
    *,
    policy_payload: dict[str, Any] | None = None,
    mode: str | None = None,
    since_hours: float | None = None,
    limit: int | None = None,
    open_failures_max: int | None = None,
    drift_max: int | None = None,
    min_success_rate: float | None = None,
) -> ExportOpsGatePolicy:
    """Resolve policy defaults with precedence: CLI overrides > file > defaults."""
    values: dict[str, Any] = {
        "mode": "observe",
        "since_hours": 24.0,
        "limit": 200,
        "open_failures_max": 0,
        "drift_max": 0,
        "min_success_rate": 95.0,
    }

    if policy_payload is not None:
        if not isinstance(policy_payload, dict):
            raise ValueError("Policy file must be a mapping object.")

        mode_file = policy_payload.get("mode")
        if mode_file is not None:
            values["mode"] = mode_file

        window = policy_payload.get("window")
        if window is not None:
            if not isinstance(window, dict):
                raise ValueError("Policy field 'window' must be an object.")
            if "since_hours" in window:
                values["since_hours"] = window.get("since_hours")
            if "limit" in window:
                values["limit"] = window.get("limit")

        thresholds = policy_payload.get("thresholds")
        if thresholds is not None:
            if not isinstance(thresholds, dict):
                raise ValueError("Policy field 'thresholds' must be an object.")
            if "open_failures_max" in thresholds:
                values["open_failures_max"] = thresholds.get("open_failures_max")
            if "drift_max" in thresholds:
                values["drift_max"] = thresholds.get("drift_max")
            if "min_success_rate" in thresholds:
                values["min_success_rate"] = thresholds.get("min_success_rate")

    if mode is not None:
        values["mode"] = mode
    if since_hours is not None:
        values["since_hours"] = since_hours
    if limit is not None:
        values["limit"] = limit
    if open_failures_max is not None:
        values["open_failures_max"] = open_failures_max
    if drift_max is not None:
        values["drift_max"] = drift_max
    if min_success_rate is not None:
        values["min_success_rate"] = min_success_rate

    resolved_mode = str(values["mode"]).strip().lower()
    if resolved_mode not in {"observe", "enforce"}:
        raise ValueError("Policy mode must be one of: observe, enforce.")

    resolved_since_hours = float(values["since_hours"])
    if resolved_since_hours < 0:
        raise ValueError("Policy window.since_hours must be >= 0.")

    resolved_limit = int(values["limit"])
    if resolved_limit < 1:
        raise ValueError("Policy window.limit must be >= 1.")

    resolved_open_failures_max = int(values["open_failures_max"])
    if resolved_open_failures_max < 0:
        raise ValueError("Policy thresholds.open_failures_max must be >= 0.")

    resolved_drift_max = int(values["drift_max"])
    if resolved_drift_max < 0:
        raise ValueError("Policy thresholds.drift_max must be >= 0.")

    resolved_min_success_rate = float(values["min_success_rate"])
    if resolved_min_success_rate < 0 or resolved_min_success_rate > 100:
        raise ValueError("Policy thresholds.min_success_rate must be between 0 and 100.")

    return ExportOpsGatePolicy(
        mode=cast(ExportOpsGateMode, resolved_mode),
        since_hours=resolved_since_hours,
        limit=resolved_limit,
        open_failures_max=resolved_open_failures_max,
        drift_max=resolved_drift_max,
        min_success_rate=resolved_min_success_rate,
    )
