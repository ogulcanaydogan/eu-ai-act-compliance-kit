"""Deterministic security gate evaluator for OWASP mapping summaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

SecurityGateMode = Literal["observe", "enforce"]
SecurityGateProfile = Literal["strict", "balanced", "lenient"]


@dataclass(frozen=True)
class SecurityGateResult:
    """Evaluation result for security gate policy."""

    mode: SecurityGateMode
    profile: SecurityGateProfile
    effective_profile: SecurityGateProfile
    failed: bool
    reason: str
    non_compliant_count: int
    partial_count: int
    not_assessed_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize security gate result."""
        return {
            "mode": self.mode,
            "profile": self.profile,
            "effective_profile": self.effective_profile,
            "failed": self.failed,
            "reason": self.reason,
            "non_compliant_count": self.non_compliant_count,
            "partial_count": self.partial_count,
            "not_assessed_count": self.not_assessed_count,
        }


class SecurityGateEvaluator:
    """Evaluate observe/enforce security gate behavior from summary payloads."""

    DEFAULT_MODE: SecurityGateMode = "observe"
    DEFAULT_PROFILE: SecurityGateProfile = "balanced"
    VALID_MODES: tuple[SecurityGateMode, ...] = ("observe", "enforce")
    VALID_PROFILES: tuple[SecurityGateProfile, ...] = ("strict", "balanced", "lenient")
    TIER_AWARE_LENIENT_OVERRIDE_TIERS: tuple[str, ...] = ("high_risk", "unacceptable")

    def evaluate(
        self,
        security_summary: Mapping[str, Any] | None,
        mode: str = DEFAULT_MODE,
        profile: str = DEFAULT_PROFILE,
        risk_tier: str | None = None,
    ) -> SecurityGateResult:
        """Evaluate gate status using deterministic non-compliant control threshold."""
        normalized_mode = self._normalize_mode(mode)
        normalized_profile = self._normalize_profile(profile)
        effective_profile = self._effective_profile(
            profile=normalized_profile,
            risk_tier=risk_tier,
        )
        non_compliant_count = self._extract_count(security_summary, "non_compliant_count")
        partial_count = self._extract_count(security_summary, "partial_count")
        not_assessed_count = self._extract_count(security_summary, "not_assessed_count")

        if normalized_mode == "observe":
            failed = False
            reason = "observe_mode_no_blocking"
        else:
            failed, reason = self._evaluate_enforce(
                profile=effective_profile,
                non_compliant_count=non_compliant_count,
                partial_count=partial_count,
                not_assessed_count=not_assessed_count,
            )

        return SecurityGateResult(
            mode=normalized_mode,
            profile=normalized_profile,
            effective_profile=effective_profile,
            failed=failed,
            reason=reason,
            non_compliant_count=non_compliant_count,
            partial_count=partial_count,
            not_assessed_count=not_assessed_count,
        )

    def _normalize_mode(self, mode: str) -> SecurityGateMode:
        normalized = mode.strip().lower()
        if normalized not in self.VALID_MODES:
            allowed = ", ".join(self.VALID_MODES)
            raise ValueError(f"Invalid security gate mode: {mode}. Expected one of: {allowed}.")
        return normalized  # type: ignore[return-value]

    def _normalize_profile(self, profile: str) -> SecurityGateProfile:
        normalized = profile.strip().lower()
        if normalized not in self.VALID_PROFILES:
            allowed = ", ".join(self.VALID_PROFILES)
            raise ValueError(
                f"Invalid security gate profile: {profile}. Expected one of: {allowed}."
            )
        return normalized  # type: ignore[return-value]

    def _effective_profile(
        self,
        profile: SecurityGateProfile,
        risk_tier: str | None,
    ) -> SecurityGateProfile:
        normalized_tier = str(risk_tier or "").strip().lower()
        if profile == "lenient" and normalized_tier in self.TIER_AWARE_LENIENT_OVERRIDE_TIERS:
            return "balanced"
        return profile

    def _extract_count(self, security_summary: Mapping[str, Any] | None, key: str) -> int:
        if security_summary is None:
            return 0
        value = security_summary.get(key, 0)
        if isinstance(value, bool):
            raise ValueError(f"security_summary.{key} must be an integer.")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive cast path
            raise ValueError(f"security_summary.{key} must be an integer.") from exc
        if normalized < 0:
            raise ValueError(f"security_summary.{key} must be >= 0.")
        return normalized

    def _evaluate_enforce(
        self,
        profile: SecurityGateProfile,
        non_compliant_count: int,
        partial_count: int,
        not_assessed_count: int,
    ) -> tuple[bool, str]:
        if profile == "strict":
            failed = non_compliant_count > 0 or partial_count > 0 or not_assessed_count > 0
            reason = (
                "security_strict_threshold_breached"
                if failed
                else "security_strict_threshold_not_breached"
            )
            return failed, reason

        if profile == "balanced":
            failed = non_compliant_count > 0
            reason = (
                "security_balanced_threshold_breached"
                if failed
                else "security_balanced_threshold_not_breached"
            )
            return failed, reason

        # lenient
        failed = non_compliant_count >= 2
        reason = (
            "security_lenient_threshold_breached"
            if failed
            else "security_lenient_threshold_not_breached"
        )
        return failed, reason
