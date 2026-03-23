"""Deterministic security gate evaluator for OWASP mapping summaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

SecurityGateMode = Literal["observe", "enforce"]


@dataclass(frozen=True)
class SecurityGateResult:
    """Evaluation result for security gate policy."""

    mode: SecurityGateMode
    failed: bool
    reason: str
    non_compliant_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize security gate result."""
        return {
            "mode": self.mode,
            "failed": self.failed,
            "reason": self.reason,
            "non_compliant_count": self.non_compliant_count,
        }


class SecurityGateEvaluator:
    """Evaluate observe/enforce security gate behavior from summary payloads."""

    DEFAULT_MODE: SecurityGateMode = "observe"
    VALID_MODES: tuple[SecurityGateMode, ...] = ("observe", "enforce")

    def evaluate(
        self,
        security_summary: Mapping[str, Any] | None,
        mode: str = DEFAULT_MODE,
    ) -> SecurityGateResult:
        """Evaluate gate status using deterministic non-compliant control threshold."""
        normalized_mode = self._normalize_mode(mode)
        non_compliant_count = self._extract_non_compliant_count(security_summary)
        failed = normalized_mode == "enforce" and non_compliant_count > 0

        if normalized_mode == "observe":
            reason = "observe_mode_no_blocking"
        elif failed:
            reason = "security_non_compliant_controls_detected"
        else:
            reason = "security_non_compliant_controls_not_detected"

        return SecurityGateResult(
            mode=normalized_mode,
            failed=failed,
            reason=reason,
            non_compliant_count=non_compliant_count,
        )

    def _normalize_mode(self, mode: str) -> SecurityGateMode:
        normalized = mode.strip().lower()
        if normalized not in self.VALID_MODES:
            allowed = ", ".join(self.VALID_MODES)
            raise ValueError(f"Invalid security gate mode: {mode}. Expected one of: {allowed}.")
        return normalized  # type: ignore[return-value]

    def _extract_non_compliant_count(self, security_summary: Mapping[str, Any] | None) -> int:
        if security_summary is None:
            return 0
        value = security_summary.get("non_compliant_count", 0)
        if isinstance(value, bool):
            raise ValueError("security_summary.non_compliant_count must be an integer.")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive cast path
            raise ValueError("security_summary.non_compliant_count must be an integer.") from exc
        if normalized < 0:
            raise ValueError("security_summary.non_compliant_count must be >= 0.")
        return normalized
