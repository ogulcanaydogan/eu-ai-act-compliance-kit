"""Policy-based collaboration governance evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

CollaborationGateMode = Literal["observe", "enforce"]


@dataclass(frozen=True)
class CollaborationGatePolicy:
    """Resolved policy thresholds used by collaboration governance gate."""

    mode: CollaborationGateMode
    system_name: str | None
    limit: int
    blocked_max: int
    unassigned_actionable_max: int
    stale_actionable_max: int | None
    blocked_stale_max: int | None
    review_stale_max: int | None
    stale_after_hours: float
    blocked_stale_after_hours: float
    review_stale_after_hours: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "scope": {
                "system": self.system_name,
            },
            "window": {
                "limit": self.limit,
            },
            "thresholds": {
                "blocked_max": self.blocked_max,
                "unassigned_actionable_max": self.unassigned_actionable_max,
                "stale_actionable_max": self.stale_actionable_max,
                "blocked_stale_max": self.blocked_stale_max,
                "review_stale_max": self.review_stale_max,
            },
            "sla": {
                "stale_after_hours": self.stale_after_hours,
                "blocked_stale_after_hours": self.blocked_stale_after_hours,
                "review_stale_after_hours": self.review_stale_after_hours,
            },
        }


@dataclass(frozen=True)
class CollaborationGateResult:
    """Deterministic gate decision payload."""

    mode: CollaborationGateMode
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


class CollaborationGateEvaluator:
    """Evaluate collaboration metrics against collaboration governance policy."""

    def evaluate(
        self,
        *,
        policy: CollaborationGatePolicy,
        metrics: dict[str, Any],
    ) -> CollaborationGateResult:
        blocked_count = int(metrics.get("blocked_count", 0) or 0)
        unassigned_actionable_count = int(metrics.get("unassigned_actionable_count", 0) or 0)
        stale_actionable_count = int(metrics.get("stale_actionable_count", 0) or 0)
        blocked_stale_count = int(metrics.get("blocked_stale_count", 0) or 0)
        review_stale_count = int(metrics.get("review_stale_count", 0) or 0)
        has_collaboration_data = bool(metrics.get("has_collaboration_data", False))

        missing_data_violation = policy.mode == "enforce" and not has_collaboration_data
        blocked_violation = blocked_count > policy.blocked_max
        unassigned_actionable_violation = (
            unassigned_actionable_count > policy.unassigned_actionable_max
        )
        stale_actionable_violation = (
            policy.stale_actionable_max is not None
            and stale_actionable_count > policy.stale_actionable_max
        )
        blocked_stale_violation = (
            policy.blocked_stale_max is not None and blocked_stale_count > policy.blocked_stale_max
        )
        review_stale_violation = (
            policy.review_stale_max is not None and review_stale_count > policy.review_stale_max
        )

        reason_codes: list[str] = []
        if missing_data_violation:
            reason_codes.append("missing_collaboration_data")
        if blocked_violation:
            reason_codes.append("blocked_threshold_exceeded")
        if unassigned_actionable_violation:
            reason_codes.append("unassigned_actionable_threshold_exceeded")
        if stale_actionable_violation:
            reason_codes.append("stale_actionable_threshold_exceeded")
        if blocked_stale_violation:
            reason_codes.append("blocked_stale_threshold_exceeded")
        if review_stale_violation:
            reason_codes.append("review_stale_threshold_exceeded")

        failed = bool(reason_codes)
        decision_details = {
            "blocked": {
                "actual": blocked_count,
                "threshold_max": policy.blocked_max,
                "violated": blocked_violation,
            },
            "unassigned_actionable": {
                "actual": unassigned_actionable_count,
                "threshold_max": policy.unassigned_actionable_max,
                "violated": unassigned_actionable_violation,
            },
            "stale_actionable": {
                "actual": stale_actionable_count,
                "threshold_max": policy.stale_actionable_max,
                "violated": stale_actionable_violation,
                "enabled": policy.stale_actionable_max is not None,
                "sla_hours": policy.stale_after_hours,
            },
            "blocked_stale": {
                "actual": blocked_stale_count,
                "threshold_max": policy.blocked_stale_max,
                "violated": blocked_stale_violation,
                "enabled": policy.blocked_stale_max is not None,
                "sla_hours": policy.blocked_stale_after_hours,
            },
            "review_stale": {
                "actual": review_stale_count,
                "threshold_max": policy.review_stale_max,
                "violated": review_stale_violation,
                "enabled": policy.review_stale_max is not None,
                "sla_hours": policy.review_stale_after_hours,
            },
            "data_presence": {
                "has_collaboration_data": has_collaboration_data,
                "violated": missing_data_violation,
            },
        }
        return CollaborationGateResult(
            mode=policy.mode,
            failed=failed,
            reason_codes=reason_codes,
            decision_details=decision_details,
        )


def resolve_collaboration_gate_policy(
    *,
    policy_payload: dict[str, Any] | None = None,
    mode: str | None = None,
    system_name: str | None = None,
    limit: int | None = None,
    blocked_max: int | None = None,
    unassigned_actionable_max: int | None = None,
    stale_actionable_max: int | None = None,
    blocked_stale_max: int | None = None,
    review_stale_max: int | None = None,
    stale_after_hours: float | None = None,
    blocked_stale_after_hours: float | None = None,
    review_stale_after_hours: float | None = None,
) -> CollaborationGatePolicy:
    """Resolve policy with precedence: CLI flags > policy file > defaults."""
    values: dict[str, Any] = {
        "mode": "observe",
        "system_name": None,
        "limit": 200,
        "blocked_max": 0,
        "unassigned_actionable_max": 0,
        "stale_actionable_max": None,
        "blocked_stale_max": None,
        "review_stale_max": None,
        "stale_after_hours": 72.0,
        "blocked_stale_after_hours": 72.0,
        "review_stale_after_hours": 48.0,
    }

    if policy_payload is not None:
        if not isinstance(policy_payload, dict):
            raise ValueError("Policy file must be a mapping object.")

        mode_file = policy_payload.get("mode")
        if mode_file is not None:
            values["mode"] = mode_file

        scope = policy_payload.get("scope")
        if scope is not None:
            if not isinstance(scope, dict):
                raise ValueError("Policy field 'scope' must be an object.")
            if "system" in scope:
                values["system_name"] = scope.get("system")

        window = policy_payload.get("window")
        if window is not None:
            if not isinstance(window, dict):
                raise ValueError("Policy field 'window' must be an object.")
            if "limit" in window:
                values["limit"] = window.get("limit")

        thresholds = policy_payload.get("thresholds")
        if thresholds is not None:
            if not isinstance(thresholds, dict):
                raise ValueError("Policy field 'thresholds' must be an object.")
            if "blocked_max" in thresholds:
                values["blocked_max"] = thresholds.get("blocked_max")
            if "unassigned_actionable_max" in thresholds:
                values["unassigned_actionable_max"] = thresholds.get("unassigned_actionable_max")
            if "stale_actionable_max" in thresholds:
                values["stale_actionable_max"] = thresholds.get("stale_actionable_max")
            if "blocked_stale_max" in thresholds:
                values["blocked_stale_max"] = thresholds.get("blocked_stale_max")
            if "review_stale_max" in thresholds:
                values["review_stale_max"] = thresholds.get("review_stale_max")

        sla = policy_payload.get("sla")
        if sla is not None:
            if not isinstance(sla, dict):
                raise ValueError("Policy field 'sla' must be an object.")
            if "stale_after_hours" in sla:
                values["stale_after_hours"] = sla.get("stale_after_hours")
            if "blocked_stale_after_hours" in sla:
                values["blocked_stale_after_hours"] = sla.get("blocked_stale_after_hours")
            if "review_stale_after_hours" in sla:
                values["review_stale_after_hours"] = sla.get("review_stale_after_hours")

    if mode is not None:
        values["mode"] = mode
    if system_name is not None:
        values["system_name"] = system_name
    if limit is not None:
        values["limit"] = limit
    if blocked_max is not None:
        values["blocked_max"] = blocked_max
    if unassigned_actionable_max is not None:
        values["unassigned_actionable_max"] = unassigned_actionable_max
    if stale_actionable_max is not None:
        values["stale_actionable_max"] = stale_actionable_max
    if blocked_stale_max is not None:
        values["blocked_stale_max"] = blocked_stale_max
    if review_stale_max is not None:
        values["review_stale_max"] = review_stale_max
    if stale_after_hours is not None:
        values["stale_after_hours"] = stale_after_hours
    if blocked_stale_after_hours is not None:
        values["blocked_stale_after_hours"] = blocked_stale_after_hours
    if review_stale_after_hours is not None:
        values["review_stale_after_hours"] = review_stale_after_hours

    resolved_mode = str(values["mode"]).strip().lower()
    if resolved_mode not in {"observe", "enforce"}:
        raise ValueError("Policy mode must be one of: observe, enforce.")

    resolved_system: str | None
    system_value = values["system_name"]
    if system_value is None:
        resolved_system = None
    elif not isinstance(system_value, str):
        raise ValueError("Policy scope.system must be null or a string.")
    else:
        resolved_system = system_value.strip() or None

    resolved_limit = int(values["limit"])
    if resolved_limit < 1:
        raise ValueError("Policy window.limit must be >= 1.")

    resolved_blocked_max = int(values["blocked_max"])
    if resolved_blocked_max < 0:
        raise ValueError("Policy thresholds.blocked_max must be >= 0.")

    resolved_unassigned_actionable_max = int(values["unassigned_actionable_max"])
    if resolved_unassigned_actionable_max < 0:
        raise ValueError("Policy thresholds.unassigned_actionable_max must be >= 0.")

    stale_actionable_value = values["stale_actionable_max"]
    resolved_stale_actionable_max: int | None
    if stale_actionable_value is None:
        resolved_stale_actionable_max = None
    else:
        resolved_stale_actionable_max = int(stale_actionable_value)
        if resolved_stale_actionable_max < 0:
            raise ValueError("Policy thresholds.stale_actionable_max must be >= 0.")

    blocked_stale_value = values["blocked_stale_max"]
    resolved_blocked_stale_max: int | None
    if blocked_stale_value is None:
        resolved_blocked_stale_max = None
    else:
        resolved_blocked_stale_max = int(blocked_stale_value)
        if resolved_blocked_stale_max < 0:
            raise ValueError("Policy thresholds.blocked_stale_max must be >= 0.")

    review_stale_value = values["review_stale_max"]
    resolved_review_stale_max: int | None
    if review_stale_value is None:
        resolved_review_stale_max = None
    else:
        resolved_review_stale_max = int(review_stale_value)
        if resolved_review_stale_max < 0:
            raise ValueError("Policy thresholds.review_stale_max must be >= 0.")

    resolved_stale_after_hours = float(values["stale_after_hours"])
    if resolved_stale_after_hours <= 0:
        raise ValueError("Policy sla.stale_after_hours must be > 0.")

    resolved_blocked_stale_after_hours = float(values["blocked_stale_after_hours"])
    if resolved_blocked_stale_after_hours <= 0:
        raise ValueError("Policy sla.blocked_stale_after_hours must be > 0.")

    resolved_review_stale_after_hours = float(values["review_stale_after_hours"])
    if resolved_review_stale_after_hours <= 0:
        raise ValueError("Policy sla.review_stale_after_hours must be > 0.")

    return CollaborationGatePolicy(
        mode=cast(CollaborationGateMode, resolved_mode),
        system_name=resolved_system,
        limit=resolved_limit,
        blocked_max=resolved_blocked_max,
        unassigned_actionable_max=resolved_unassigned_actionable_max,
        stale_actionable_max=resolved_stale_actionable_max,
        blocked_stale_max=resolved_blocked_stale_max,
        review_stale_max=resolved_review_stale_max,
        stale_after_hours=resolved_stale_after_hours,
        blocked_stale_after_hours=resolved_blocked_stale_after_hours,
        review_stale_after_hours=resolved_review_stale_after_hours,
    )
