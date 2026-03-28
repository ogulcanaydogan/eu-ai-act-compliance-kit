"""Ops closeout evaluator for release evidence automation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx

OpsCloseoutMode = Literal["observe", "enforce"]


@dataclass(frozen=True)
class OpsCloseoutCheck:
    """Single deterministic closeout check result."""

    name: str
    url: str
    ok: bool
    http_status: int | None
    details: str

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "failed": self.failed,
            "reason_codes": list(self.reason_codes),
            "failed_checks": list(self.failed_checks),
            "passed_checks": list(self.passed_checks),
            "checks": [check.to_dict() for check in self.checks],
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

        failed_checks = [check.name for check in checks if not check.ok]
        passed_checks = [check.name for check in checks if check.ok]
        reason_codes = [f"{name}_failed" for name in failed_checks]

        return OpsCloseoutResult(
            mode=mode,
            failed=bool(failed_checks),
            reason_codes=reason_codes,
            failed_checks=failed_checks,
            passed_checks=passed_checks,
            checks=checks,
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
        ok = status == "completed" and conclusion == "success"

        return OpsCloseoutCheck(
            name="github_run",
            url=html_url,
            ok=ok,
            http_status=response.status_code,
            details=f"status={status or 'unknown'}, conclusion={conclusion or 'unknown'}",
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
        ok = has_wheel and has_sdist

        return OpsCloseoutCheck(
            name="github_release",
            url=html_url,
            ok=ok,
            http_status=response.status_code,
            details=(
                "assets="
                f"{len(asset_names)},has_wheel={str(has_wheel).lower()},"
                f"has_sdist={str(has_sdist).lower()}"
            ),
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

        ok = response.status_code == 200
        return OpsCloseoutCheck(
            name="rtd",
            url=rtd_url,
            ok=ok,
            http_status=response.status_code,
            details="ok" if ok else "unexpected_status_code",
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
                error=None,
            )
        except httpx.HTTPError as exc:
            return _SafeHttpResponse(status_code=None, body=b"", error=str(exc))


@dataclass(frozen=True)
class _SafeHttpResponse:
    """Internal normalized HTTP response wrapper."""

    status_code: int | None
    body: bytes
    error: str | None


def normalize_ops_closeout_mode(mode: str) -> OpsCloseoutMode:
    """Validate and normalize closeout mode."""
    resolved = mode.strip().lower()
    if resolved not in {"observe", "enforce"}:
        raise ValueError("mode must be one of: observe, enforce")
    return cast(OpsCloseoutMode, resolved)
