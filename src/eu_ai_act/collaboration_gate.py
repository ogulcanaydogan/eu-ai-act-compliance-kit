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
        has_collaboration_data = bool(metrics.get("has_collaboration_data", False))

        missing_data_violation = policy.mode == "enforce" and not has_collaboration_data
        blocked_violation = blocked_count > policy.blocked_max
        unassigned_actionable_violation = (
            unassigned_actionable_count > policy.unassigned_actionable_max
        )

        reason_codes: list[str] = []
        if missing_data_violation:
            reason_codes.append("missing_collaboration_data")
        if blocked_violation:
            reason_codes.append("blocked_threshold_exceeded")
        if unassigned_actionable_violation:
            reason_codes.append("unassigned_actionable_threshold_exceeded")

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
) -> CollaborationGatePolicy:
    """Resolve policy with precedence: CLI flags > policy file > defaults."""
    values: dict[str, Any] = {
        "mode": "observe",
        "system_name": None,
        "limit": 200,
        "blocked_max": 0,
        "unassigned_actionable_max": 0,
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

    return CollaborationGatePolicy(
        mode=cast(CollaborationGateMode, resolved_mode),
        system_name=resolved_system,
        limit=resolved_limit,
        blocked_max=resolved_blocked_max,
        unassigned_actionable_max=resolved_unassigned_actionable_max,
    )
