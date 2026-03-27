"""Governance aggregation helpers for handoff outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

GovernanceMode = Literal["observe", "enforce"]

_GATE_ORDER: tuple[tuple[str, str], ...] = (
    ("security_gate", "security"),
    ("collaboration_gate", "collaboration"),
    ("export_ops_gate", "export_ops"),
)


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
