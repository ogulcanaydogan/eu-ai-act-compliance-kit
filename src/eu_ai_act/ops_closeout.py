"""Ops closeout evaluator for release evidence automation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal, cast

import httpx

OpsCloseoutMode = Literal["observe", "enforce"]


@dataclass(frozen=True)
class OpsCloseoutWaiver:
    """Time-bounded waiver definition for reason-code level suppression."""

    reason_code: str
    expires_at: datetime
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "note": self.note,
        }


@dataclass(frozen=True)
class OpsCloseoutPolicy:
    """Resolved ops closeout policy with deterministic precedence."""

    mode: OpsCloseoutMode
    release_version: str | None
    release_run_id: int | None
    repo: str
    pypi_project: str
    rtd_url: str
    max_run_age_hours: float | None
    max_release_age_hours: float | None
    max_rtd_age_hours: float | None
    waivers: list[OpsCloseoutWaiver]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "repo": self.repo,
            "pypi_project": self.pypi_project,
            "rtd_url": self.rtd_url,
            "release": {
                "version": self.release_version,
                "run_id": self.release_run_id,
            },
            "thresholds": {
                "max_run_age_hours": self.max_run_age_hours,
                "max_release_age_hours": self.max_release_age_hours,
                "max_rtd_age_hours": self.max_rtd_age_hours,
            },
            "waivers": [waiver.to_dict() for waiver in self.waivers],
        }


@dataclass(frozen=True)
class OpsCloseoutCheck:
    """Single deterministic closeout check result."""

    name: str
    url: str
    ok: bool
    http_status: int | None
    details: str
    observed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "ok": self.ok,
            "http_status": self.http_status,
            "details": self.details,
        }


@dataclass(frozen=True)
class OpsCloseoutResult:
    """Aggregated deterministic closeout decision payload."""

    mode: OpsCloseoutMode
    failed: bool
    reason_codes: list[str]
    failed_checks: list[str]
    passed_checks: list[str]
    checks: list[OpsCloseoutCheck]
    freshness_metrics: dict[str, float | None]
    freshness_thresholds: dict[str, float | None]
    freshness_reason_codes: list[str]
    waiver_summary: dict[str, int]
    waived_reason_codes: list[str]
    expired_waiver_reason_codes: list[str]
    effective_reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "failed": self.failed,
            "reason_codes": list(self.reason_codes),
            "failed_checks": list(self.failed_checks),
            "passed_checks": list(self.passed_checks),
            "checks": [check.to_dict() for check in self.checks],
            "freshness_metrics": dict(self.freshness_metrics),
            "freshness_thresholds": dict(self.freshness_thresholds),
            "freshness_reason_codes": list(self.freshness_reason_codes),
            "waiver_summary": dict(self.waiver_summary),
            "waived_reason_codes": list(self.waived_reason_codes),
            "expired_waiver_reason_codes": list(self.expired_waiver_reason_codes),
            "effective_reason_codes": list(self.effective_reason_codes),
        }


class OpsCloseoutEvaluator:
    """Evaluate release closeout checks for GitHub run/release, PyPI, and RTD."""

    def evaluate(
        self,
        *,
        mode: OpsCloseoutMode,
        version: str,
        release_run_id: int,
        repo: str,
        pypi_project: str,
        rtd_url: str,
        github_api_base_url: str = "https://api.github.com",
        pypi_base_url: str = "https://pypi.org",
        timeout_seconds: float = 20.0,
        max_run_age_hours: float | None = None,
        max_release_age_hours: float | None = None,
        max_rtd_age_hours: float | None = None,
        waivers: list[OpsCloseoutWaiver] | None = None,
    ) -> OpsCloseoutResult:
        """Run all closeout checks and return deterministic decision payload."""
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            checks = [
                self._check_github_run(
                    client=client,
                    repo=repo,
                    release_run_id=release_run_id,
                    github_api_base_url=github_api_base_url,
                ),
                self._check_github_release(
                    client=client,
                    repo=repo,
                    version=version,
                    github_api_base_url=github_api_base_url,
                ),
                self._check_pypi_version(
                    client=client,
                    pypi_project=pypi_project,
                    expected_version=version,
                    pypi_base_url=pypi_base_url,
                ),
                self._check_rtd(client=client, rtd_url=rtd_url),
            ]

        now_utc = datetime.now(UTC)
        freshness_metrics: dict[str, float | None] = {
            "run_age_hours": None,
            "release_age_hours": None,
            "rtd_age_hours": None,
        }
        freshness_thresholds: dict[str, float | None] = {
            "max_run_age_hours": max_run_age_hours,
            "max_release_age_hours": max_release_age_hours,
            "max_rtd_age_hours": max_rtd_age_hours,
        }
        freshness_reason_codes: list[str] = []

        if max_run_age_hours is not None:
            run_age = self._age_hours_from_check(
                checks=checks, check_name="github_run", now_utc=now_utc
            )
            freshness_metrics["run_age_hours"] = run_age
            if run_age is not None and run_age > max_run_age_hours:
                freshness_reason_codes.append("github_run_stale")

        if max_release_age_hours is not None:
            release_age = self._age_hours_from_check(
                checks=checks,
                check_name="github_release",
                now_utc=now_utc,
            )
            freshness_metrics["release_age_hours"] = release_age
            if release_age is not None and release_age > max_release_age_hours:
                freshness_reason_codes.append("github_release_stale")

        if max_rtd_age_hours is not None:
            rtd_age = self._age_hours_from_check(checks=checks, check_name="rtd", now_utc=now_utc)
            freshness_metrics["rtd_age_hours"] = rtd_age
            if rtd_age is None or rtd_age > max_rtd_age_hours:
                freshness_reason_codes.append("rtd_stale_or_unknown")

        failed_checks = [check.name for check in checks if not check.ok]
        passed_checks = [check.name for check in checks if check.ok]
        reason_codes = [f"{name}_failed" for name in failed_checks]
        reason_codes.extend(freshness_reason_codes)

        waivers = waivers or []
        waived_reason_codes: set[str] = set()
        expired_waiver_reason_codes: set[str] = set()
        reason_set = set(reason_codes)
        for waiver in waivers:
            if waiver.reason_code not in reason_set:
                continue
            if waiver.expires_at >= now_utc:
                waived_reason_codes.add(waiver.reason_code)
            else:
                expired_waiver_reason_codes.add(waiver.reason_code)

        effective_reason_codes = [code for code in reason_codes if code not in waived_reason_codes]
        waiver_summary = {
            "configured_count": len(waivers),
            "matched_count": len(waived_reason_codes | expired_waiver_reason_codes),
            "waived_count": len(waived_reason_codes),
            "expired_count": len(expired_waiver_reason_codes),
        }

        return OpsCloseoutResult(
            mode=mode,
            failed=bool(effective_reason_codes),
            reason_codes=reason_codes,
            failed_checks=failed_checks,
            passed_checks=passed_checks,
            checks=checks,
            freshness_metrics=freshness_metrics,
            freshness_thresholds=freshness_thresholds,
            freshness_reason_codes=freshness_reason_codes,
            waiver_summary=waiver_summary,
            waived_reason_codes=sorted(waived_reason_codes),
            expired_waiver_reason_codes=sorted(expired_waiver_reason_codes),
            effective_reason_codes=effective_reason_codes,
        )

    def _check_github_run(
        self,
        *,
        client: httpx.Client,
        repo: str,
        release_run_id: int,
        github_api_base_url: str,
    ) -> OpsCloseoutCheck:
        api_url = (
            f"{github_api_base_url.rstrip('/')}" f"/repos/{repo}/actions/runs/{release_run_id}"
        )
        default_url = f"https://github.com/{repo}/actions/runs/{release_run_id}"
        response = self._safe_get(client=client, url=api_url)
        if response.error is not None:
            return OpsCloseoutCheck(
                name="github_run",
                url=default_url,
                ok=False,
                http_status=None,
                details=f"request_error={response.error}",
            )

        if response.status_code != 200:
            return OpsCloseoutCheck(
                name="github_run",
                url=default_url,
                ok=False,
                http_status=response.status_code,
                details="unexpected_status_code",
            )

        payload = self._safe_json(response.body)
        if payload is None:
            return OpsCloseoutCheck(
                name="github_run",
                url=default_url,
                ok=False,
                http_status=response.status_code,
                details="invalid_json_payload",
            )

        status = str(payload.get("status") or "").strip().lower()
        conclusion = str(payload.get("conclusion") or "").strip().lower()
        html_url = str(payload.get("html_url") or default_url)
        observed_at = self._first_non_empty_str(
            payload.get("updated_at"),
            payload.get("run_started_at"),
            payload.get("created_at"),
        )
        ok = status == "completed" and conclusion == "success"

        details = f"status={status or 'unknown'}, conclusion={conclusion or 'unknown'}"
        if observed_at:
            details = f"{details}, observed_at={observed_at}"

        return OpsCloseoutCheck(
            name="github_run",
            url=html_url,
            ok=ok,
            http_status=response.status_code,
            details=details,
            observed_at=observed_at,
        )

    def _check_github_release(
        self,
        *,
        client: httpx.Client,
        repo: str,
        version: str,
        github_api_base_url: str,
    ) -> OpsCloseoutCheck:
        tag = f"v{version}"
        api_url = f"{github_api_base_url.rstrip('/')}/repos/{repo}/releases/tags/{tag}"
        default_url = f"https://github.com/{repo}/releases/tag/{tag}"

        response = self._safe_get(client=client, url=api_url)
        if response.error is not None:
            return OpsCloseoutCheck(
                name="github_release",
                url=default_url,
                ok=False,
                http_status=None,
                details=f"request_error={response.error}",
            )

        if response.status_code != 200:
            return OpsCloseoutCheck(
                name="github_release",
                url=default_url,
                ok=False,
                http_status=response.status_code,
                details="release_not_found_or_unavailable",
            )

        payload = self._safe_json(response.body)
        if payload is None:
            return OpsCloseoutCheck(
                name="github_release",
                url=default_url,
                ok=False,
                http_status=response.status_code,
                details="invalid_json_payload",
            )

        html_url = str(payload.get("html_url") or default_url)
        assets = payload.get("assets", [])
        if not isinstance(assets, list):
            assets = []
        asset_names = [str(item.get("name") or "") for item in assets if isinstance(item, dict)]
        has_wheel = any(name.endswith(".whl") for name in asset_names)
        has_sdist = any(name.endswith(".tar.gz") for name in asset_names)
        observed_at = self._first_non_empty_str(
            payload.get("published_at"), payload.get("created_at")
        )
        ok = has_wheel and has_sdist

        details = (
            "assets="
            f"{len(asset_names)},has_wheel={str(has_wheel).lower()},"
            f"has_sdist={str(has_sdist).lower()}"
        )
        if observed_at:
            details = f"{details},observed_at={observed_at}"

        return OpsCloseoutCheck(
            name="github_release",
            url=html_url,
            ok=ok,
            http_status=response.status_code,
            details=details,
            observed_at=observed_at,
        )

    def _check_pypi_version(
        self,
        *,
        client: httpx.Client,
        pypi_project: str,
        expected_version: str,
        pypi_base_url: str,
    ) -> OpsCloseoutCheck:
        url = f"{pypi_base_url.rstrip('/')}/pypi/{pypi_project}/json"
        response = self._safe_get(client=client, url=url)
        if response.error is not None:
            return OpsCloseoutCheck(
                name="pypi_version",
                url=url,
                ok=False,
                http_status=None,
                details=f"request_error={response.error}",
            )

        if response.status_code != 200:
            return OpsCloseoutCheck(
                name="pypi_version",
                url=url,
                ok=False,
                http_status=response.status_code,
                details="package_unavailable",
            )

        payload = self._safe_json(response.body)
        if payload is None:
            return OpsCloseoutCheck(
                name="pypi_version",
                url=url,
                ok=False,
                http_status=response.status_code,
                details="invalid_json_payload",
            )

        info = payload.get("info", {})
        if not isinstance(info, dict):
            info = {}
        actual_version = str(info.get("version") or "")
        ok = actual_version == expected_version

        return OpsCloseoutCheck(
            name="pypi_version",
            url=url,
            ok=ok,
            http_status=response.status_code,
            details=f"expected={expected_version},actual={actual_version or 'unknown'}",
        )

    def _check_rtd(self, *, client: httpx.Client, rtd_url: str) -> OpsCloseoutCheck:
        response = self._safe_get(client=client, url=rtd_url)
        if response.error is not None:
            return OpsCloseoutCheck(
                name="rtd",
                url=rtd_url,
                ok=False,
                http_status=None,
                details=f"request_error={response.error}",
            )

        last_modified = response.headers.get("last-modified")
        ok = response.status_code == 200
        details = "ok" if ok else "unexpected_status_code"
        if last_modified:
            details = f"{details},last_modified={last_modified}"

        return OpsCloseoutCheck(
            name="rtd",
            url=rtd_url,
            ok=ok,
            http_status=response.status_code,
            details=details,
            observed_at=last_modified,
        )

    @staticmethod
    def _safe_json(payload: bytes) -> dict[str, Any] | None:
        try:
            raw = cast(dict[str, Any], httpx.Response(200, content=payload).json())
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        return raw

    @staticmethod
    def _safe_get(*, client: httpx.Client, url: str) -> _SafeHttpResponse:
        try:
            response = client.get(url)
            return _SafeHttpResponse(
                status_code=response.status_code,
                body=response.content,
                headers={str(k).lower(): str(v) for k, v in response.headers.items()},
                error=None,
            )
        except httpx.HTTPError as exc:
            return _SafeHttpResponse(status_code=None, body=b"", headers={}, error=str(exc))

    @staticmethod
    def _first_non_empty_str(*values: Any) -> str | None:
        for raw in values:
            value = str(raw or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        candidate = value.strip()
        if not candidate:
            return None

        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(candidate)
            except (TypeError, ValueError):
                return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _age_hours_from_check(
        self,
        *,
        checks: list[OpsCloseoutCheck],
        check_name: str,
        now_utc: datetime,
    ) -> float | None:
        check = next((item for item in checks if item.name == check_name), None)
        if check is None:
            return None

        observed_at = self._parse_datetime(check.observed_at)
        if observed_at is None:
            return None

        delta_seconds = max((now_utc - observed_at).total_seconds(), 0.0)
        return round(delta_seconds / 3600.0, 3)


@dataclass(frozen=True)
class _SafeHttpResponse:
    """Internal normalized HTTP response wrapper."""

    status_code: int | None
    body: bytes
    headers: dict[str, str]
    error: str | None


def normalize_ops_closeout_mode(mode: str) -> OpsCloseoutMode:
    """Validate and normalize closeout mode."""
    resolved = mode.strip().lower()
    if resolved not in {"observe", "enforce"}:
        raise ValueError("mode must be one of: observe, enforce")
    return cast(OpsCloseoutMode, resolved)


def resolve_ops_closeout_policy(
    *,
    policy_payload: dict[str, Any] | None = None,
    mode: str | None = None,
    release_version: str | None = None,
    release_run_id: int | None = None,
    repo: str | None = None,
    pypi_project: str | None = None,
    rtd_url: str | None = None,
    max_run_age_hours: float | None = None,
    max_release_age_hours: float | None = None,
    max_rtd_age_hours: float | None = None,
    waivers: list[dict[str, str | None]] | None = None,
) -> OpsCloseoutPolicy:
    """Resolve ops closeout policy with precedence: CLI > policy file > defaults."""
    values: dict[str, Any] = {
        "mode": "observe",
        "repo": "ogulcanaydogan/eu-ai-act-compliance-kit",
        "pypi_project": "eu-ai-act-compliance-kit",
        "rtd_url": "https://eu-ai-act-compliance-kit.readthedocs.io/en/latest/",
        "release_version": None,
        "release_run_id": None,
        "max_run_age_hours": None,
        "max_release_age_hours": None,
        "max_rtd_age_hours": None,
        "waivers": [],
    }

    if policy_payload is not None:
        if not isinstance(policy_payload, dict):
            raise ValueError("Policy file must be a mapping object.")
        if "mode" in policy_payload:
            values["mode"] = policy_payload.get("mode")
        if "repo" in policy_payload:
            values["repo"] = policy_payload.get("repo")
        if "pypi_project" in policy_payload:
            values["pypi_project"] = policy_payload.get("pypi_project")
        if "rtd_url" in policy_payload:
            values["rtd_url"] = policy_payload.get("rtd_url")
        release_payload = policy_payload.get("release")
        if release_payload is not None:
            if not isinstance(release_payload, dict):
                raise ValueError("Policy field 'release' must be an object.")
            if "version" in release_payload:
                values["release_version"] = release_payload.get("version")
            if "run_id" in release_payload:
                values["release_run_id"] = release_payload.get("run_id")

        thresholds_payload = policy_payload.get("thresholds")
        if thresholds_payload is not None:
            if not isinstance(thresholds_payload, dict):
                raise ValueError("Policy field 'thresholds' must be an object.")
            if "max_run_age_hours" in thresholds_payload:
                values["max_run_age_hours"] = thresholds_payload.get("max_run_age_hours")
            if "max_release_age_hours" in thresholds_payload:
                values["max_release_age_hours"] = thresholds_payload.get("max_release_age_hours")
            if "max_rtd_age_hours" in thresholds_payload:
                values["max_rtd_age_hours"] = thresholds_payload.get("max_rtd_age_hours")
        waivers_payload = policy_payload.get("waivers")
        if waivers_payload is not None:
            values["waivers"] = waivers_payload

    if mode is not None:
        values["mode"] = mode
    if release_version is not None:
        values["release_version"] = release_version
    if release_run_id is not None:
        values["release_run_id"] = release_run_id
    if repo is not None:
        values["repo"] = repo
    if pypi_project is not None:
        values["pypi_project"] = pypi_project
    if rtd_url is not None:
        values["rtd_url"] = rtd_url
    if max_run_age_hours is not None:
        values["max_run_age_hours"] = max_run_age_hours
    if max_release_age_hours is not None:
        values["max_release_age_hours"] = max_release_age_hours
    if max_rtd_age_hours is not None:
        values["max_rtd_age_hours"] = max_rtd_age_hours
    if waivers is not None:
        values["waivers"] = waivers

    resolved_mode = normalize_ops_closeout_mode(str(values["mode"]))

    resolved_repo = str(values["repo"] or "").strip()
    if "/" not in resolved_repo or resolved_repo.count("/") != 1:
        raise ValueError("Policy repo must be in '<owner>/<name>' format.")

    resolved_pypi_project = str(values["pypi_project"] or "").strip()
    if not resolved_pypi_project:
        raise ValueError("Policy pypi_project must be a non-empty string.")

    resolved_rtd_url = str(values["rtd_url"] or "").strip()
    if not resolved_rtd_url:
        raise ValueError("Policy rtd_url must be a non-empty string.")

    raw_version = values["release_version"]
    resolved_release_version: str | None = None
    if raw_version is not None:
        resolved_release_version = str(raw_version).strip()
        if not resolved_release_version:
            raise ValueError("Policy release.version must be non-empty when provided.")

    raw_run_id = values["release_run_id"]
    resolved_release_run_id: int | None = None
    if raw_run_id is not None:
        try:
            resolved_release_run_id = int(raw_run_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Policy release.run_id must be an integer.") from exc
        if resolved_release_run_id < 1:
            raise ValueError("Policy release.run_id must be >= 1.")

    resolved_max_run_age_hours = _coerce_optional_positive_float(
        values["max_run_age_hours"], "Policy thresholds.max_run_age_hours"
    )
    resolved_max_release_age_hours = _coerce_optional_positive_float(
        values["max_release_age_hours"], "Policy thresholds.max_release_age_hours"
    )
    resolved_max_rtd_age_hours = _coerce_optional_positive_float(
        values["max_rtd_age_hours"], "Policy thresholds.max_rtd_age_hours"
    )
    resolved_waivers = _coerce_ops_closeout_waivers(values["waivers"])

    return OpsCloseoutPolicy(
        mode=resolved_mode,
        release_version=resolved_release_version,
        release_run_id=resolved_release_run_id,
        repo=resolved_repo,
        pypi_project=resolved_pypi_project,
        rtd_url=resolved_rtd_url,
        max_run_age_hours=resolved_max_run_age_hours,
        max_release_age_hours=resolved_max_release_age_hours,
        max_rtd_age_hours=resolved_max_rtd_age_hours,
        waivers=resolved_waivers,
    )


def _coerce_optional_positive_float(value: Any, field_name: str) -> float | None:
    """Normalize optional positive float config fields."""
    if value is None:
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc
    if normalized <= 0:
        raise ValueError(f"{field_name} must be > 0 when provided.")
    return normalized


def _coerce_ops_closeout_waivers(value: Any) -> list[OpsCloseoutWaiver]:
    """Normalize optional waiver list payload."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Policy waivers must be a list.")

    normalized: list[OpsCloseoutWaiver] = []
    for index, raw in enumerate(value):
        entry_name = f"Policy waivers[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{entry_name} must be an object.")

        reason_code_raw = raw.get("reason_code")
        reason_code = str(reason_code_raw or "").strip()
        if not reason_code:
            raise ValueError(f"{entry_name}.reason_code must be a non-empty string.")

        expires_at_raw = raw.get("expires_at")
        expires_at_text = str(expires_at_raw or "").strip()
        if not expires_at_text:
            raise ValueError(f"{entry_name}.expires_at must be a non-empty ISO8601 UTC string.")

        expires_at = OpsCloseoutEvaluator._parse_datetime(expires_at_text)
        if expires_at is None:
            raise ValueError(f"{entry_name}.expires_at must be a valid ISO8601 UTC datetime.")
        if expires_at.utcoffset() != UTC.utcoffset(expires_at):
            raise ValueError(f"{entry_name}.expires_at must be in UTC.")

        note_raw = raw.get("note")
        note: str | None
        if note_raw is None:
            note = None
        else:
            note = str(note_raw).strip() or None

        normalized.append(
            OpsCloseoutWaiver(
                reason_code=reason_code,
                expires_at=expires_at,
                note=note,
            )
        )
    return normalized
