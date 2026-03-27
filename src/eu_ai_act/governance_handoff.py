"""Governance aggregation helpers for handoff outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

GovernanceMode = Literal["observe", "enforce"]
GovernanceExportTarget = Literal["jira", "servicenow"]
SecurityGateProfile = Literal["strict", "balanced", "lenient"]

_GATE_ORDER: tuple[tuple[str, str], ...] = (
    ("security_gate", "security"),
    ("collaboration_gate", "collaboration"),
    ("export_ops_gate", "export_ops"),
)


@dataclass(frozen=True)
class GovernanceHandoffPolicy:
    """Resolved policy used by governance-aware handoff execution."""

    mode: GovernanceMode
    security_enabled: bool
    collaboration_enabled: bool
    export_ops_enabled: bool
    security_profile: SecurityGateProfile
    export_target: GovernanceExportTarget | None
    collaboration_policy: dict[str, Any]
    export_ops_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "gates": {
                "security": self.security_enabled,
                "collaboration": self.collaboration_enabled,
                "export_ops": self.export_ops_enabled,
            },
            "security": {
                "profile": self.security_profile,
            },
            "collaboration": dict(self.collaboration_policy),
            "export_ops": {
                "target": self.export_target,
                **dict(self.export_ops_policy),
            },
        }


@dataclass(frozen=True)
class GovernanceDecision:
    """Deterministic combined governance decision payload."""

    mode: GovernanceMode
    failed: bool
    reason_codes: list[str]
    evaluated_gates: list[str]
    failed_gates: list[str]
    security_gate: dict[str, Any] | None
    collaboration_gate: dict[str, Any] | None
    export_ops_gate: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize governance decision for JSON outputs."""
        return {
            "mode": self.mode,
            "failed": self.failed,
            "reason_codes": list(self.reason_codes),
            "evaluated_gates": list(self.evaluated_gates),
            "failed_gates": list(self.failed_gates),
            "security_gate": self.security_gate,
            "collaboration_gate": self.collaboration_gate,
            "export_ops_gate": self.export_ops_gate,
        }


def build_governance_decision(
    *,
    mode: str,
    security_gate: dict[str, Any] | None,
    collaboration_gate: dict[str, Any] | None,
    export_ops_gate: dict[str, Any] | None = None,
) -> GovernanceDecision:
    """Build deterministic governance output from gate payloads."""
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"observe", "enforce"}:
        raise ValueError("governance mode must be one of: observe, enforce")

    gate_payloads: dict[str, dict[str, Any] | None] = {
        "security_gate": security_gate,
        "collaboration_gate": collaboration_gate,
        "export_ops_gate": export_ops_gate,
    }

    evaluated_gates: list[str] = []
    failed_gates: list[str] = []
    reason_codes: list[str] = []

    for gate_key, reason_prefix in _GATE_ORDER:
        payload = gate_payloads[gate_key]
        if payload is None:
            continue
        evaluated_gates.append(gate_key)
        gate_failed = bool(payload.get("failed", False))
        if gate_failed:
            failed_gates.append(gate_key)
            for reason in _extract_reasons(payload):
                reason_codes.append(f"{reason_prefix}:{reason}")

    return GovernanceDecision(
        mode=normalized_mode,  # type: ignore[arg-type]
        failed=bool(failed_gates),
        reason_codes=reason_codes,
        evaluated_gates=evaluated_gates,
        failed_gates=failed_gates,
        security_gate=security_gate,
        collaboration_gate=collaboration_gate,
        export_ops_gate=export_ops_gate,
    )


def resolve_governance_handoff_policy(
    *,
    policy_payload: dict[str, Any] | None = None,
    mode: str | None = None,
    export_target: str | None = None,
    security_enabled: bool | None = None,
    collaboration_enabled: bool | None = None,
    export_ops_enabled: bool | None = None,
    security_profile: str | None = None,
) -> GovernanceHandoffPolicy:
    """Resolve governance handoff policy with precedence: CLI > file > defaults."""
    values: dict[str, Any] = {
        "mode": "observe",
        "security_enabled": True,
        "collaboration_enabled": True,
        "export_ops_enabled": False,
        "security_profile": "balanced",
        "export_target": None,
        "collaboration_policy": {},
        "export_ops_policy": {},
    }

    if policy_payload is not None:
        if not isinstance(policy_payload, dict):
            raise ValueError("Policy file must be a mapping object.")

        if "mode" in policy_payload:
            values["mode"] = policy_payload.get("mode")

        gates_payload = policy_payload.get("gates")
        if gates_payload is not None:
            if not isinstance(gates_payload, dict):
                raise ValueError("Policy field 'gates' must be an object.")
            if "security" in gates_payload:
                values["security_enabled"] = bool(gates_payload.get("security"))
            if "collaboration" in gates_payload:
                values["collaboration_enabled"] = bool(gates_payload.get("collaboration"))
            if "export_ops" in gates_payload:
                values["export_ops_enabled"] = bool(gates_payload.get("export_ops"))

        security_payload = policy_payload.get("security")
        if security_payload is not None:
            if not isinstance(security_payload, dict):
                raise ValueError("Policy field 'security' must be an object.")
            if "profile" in security_payload:
                values["security_profile"] = security_payload.get("profile")

        collaboration_payload = policy_payload.get("collaboration")
        if collaboration_payload is not None:
            if not isinstance(collaboration_payload, dict):
                raise ValueError("Policy field 'collaboration' must be an object.")
            values["collaboration_policy"] = dict(collaboration_payload)

        export_ops_payload = policy_payload.get("export_ops")
        if export_ops_payload is not None:
            if not isinstance(export_ops_payload, dict):
                raise ValueError("Policy field 'export_ops' must be an object.")
            export_ops_payload_copy = dict(export_ops_payload)
            if "target" in export_ops_payload_copy:
                values["export_target"] = export_ops_payload_copy.pop("target")
            values["export_ops_policy"] = export_ops_payload_copy

    if mode is not None:
        values["mode"] = mode
    if security_enabled is not None:
        values["security_enabled"] = security_enabled
    if collaboration_enabled is not None:
        values["collaboration_enabled"] = collaboration_enabled
    if export_ops_enabled is not None:
        values["export_ops_enabled"] = export_ops_enabled
    if security_profile is not None:
        values["security_profile"] = security_profile
    if export_target is not None:
        values["export_target"] = export_target
        values["export_ops_enabled"] = True

    resolved_mode = str(values["mode"]).strip().lower()
    if resolved_mode not in {"observe", "enforce"}:
        raise ValueError("Policy mode must be one of: observe, enforce.")

    resolved_profile = str(values["security_profile"]).strip().lower()
    if resolved_profile not in {"strict", "balanced", "lenient"}:
        raise ValueError("Policy security.profile must be one of: strict, balanced, lenient.")

    resolved_export_target: GovernanceExportTarget | None = None
    if values["export_target"] is not None:
        target_value = str(values["export_target"]).strip().lower()
        if target_value not in {"jira", "servicenow"}:
            raise ValueError("Policy export_ops.target must be one of: jira, servicenow.")
        resolved_export_target = cast(GovernanceExportTarget, target_value)

    resolved_export_ops_enabled = bool(values["export_ops_enabled"])
    if resolved_export_ops_enabled and resolved_export_target is None:
        raise ValueError(
            "Export ops governance gate is enabled but export target is missing. "
            "Set --export-target or policy export_ops.target."
        )

    collaboration_policy_payload = values["collaboration_policy"]
    if not isinstance(collaboration_policy_payload, dict):
        raise ValueError("Policy field 'collaboration' must be an object.")
    export_ops_policy_payload = values["export_ops_policy"]
    if not isinstance(export_ops_policy_payload, dict):
        raise ValueError("Policy field 'export_ops' must be an object.")

    return GovernanceHandoffPolicy(
        mode=cast(GovernanceMode, resolved_mode),
        security_enabled=bool(values["security_enabled"]),
        collaboration_enabled=bool(values["collaboration_enabled"]),
        export_ops_enabled=resolved_export_ops_enabled,
        security_profile=cast(SecurityGateProfile, resolved_profile),
        export_target=resolved_export_target,
        collaboration_policy=dict(collaboration_policy_payload),
        export_ops_policy=dict(export_ops_policy_payload),
    )


def _extract_reasons(payload: dict[str, Any]) -> list[str]:
    """Extract reason list from known gate payload shapes."""
    raw_reason_codes = payload.get("reason_codes")
    if isinstance(raw_reason_codes, list):
        normalized = [str(item).strip() for item in raw_reason_codes if str(item).strip()]
        if normalized:
            return normalized

    raw_reason = payload.get("reason")
    if isinstance(raw_reason, str) and raw_reason.strip():
        return [raw_reason.strip()]

    return ["failed_without_reason_code"]
