"""Unit tests for ops closeout evaluator."""

from __future__ import annotations

import httpx
import pytest

from eu_ai_act.ops_closeout import (
    OpsCloseoutEvaluator,
    normalize_ops_closeout_mode,
    resolve_ops_closeout_policy,
)


def _patch_http_client(monkeypatch: pytest.MonkeyPatch, handler):
    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return original_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)


def test_ops_closeout_evaluator_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """All checks passing should produce success decision with empty reasons."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/runs/234"):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "https://github.com/acme/repo/actions/runs/234",
                },
            )
        if request.url.path.endswith("/releases/tags/v0.1.29"):
            return httpx.Response(
                200,
                json={
                    "html_url": "https://github.com/acme/repo/releases/tag/v0.1.29",
                    "assets": [
                        {"name": "eu_ai_act_compliance_kit-0.1.29-py3-none-any.whl"},
                        {"name": "eu_ai_act_compliance_kit-0.1.29.tar.gz"},
                    ],
                },
            )
        if request.url.path.endswith("/pypi/eu-ai-act-compliance-kit/json"):
            return httpx.Response(200, json={"info": {"version": "0.1.29"}})
        if request.url.path == "/rtd":
            return httpx.Response(200, text="ok")
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)

    result = OpsCloseoutEvaluator().evaluate(
        mode="observe",
        version="0.1.29",
        release_run_id=234,
        repo="acme/repo",
        pypi_project="eu-ai-act-compliance-kit",
        rtd_url="https://example.test/rtd",
        github_api_base_url="https://example.test/api",
        pypi_base_url="https://example.test",
    )

    assert result.mode == "observe"
    assert result.failed is False
    assert result.reason_codes == []
    assert result.failed_checks == []
    assert sorted(result.passed_checks) == [
        "github_release",
        "github_run",
        "pypi_version",
        "rtd",
    ]


def test_ops_closeout_evaluator_observe_mode_tracks_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observe mode should report failures without changing mode semantics."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/runs/11"):
            return httpx.Response(200, json={"status": "completed", "conclusion": "success"})
        if request.url.path.endswith("/releases/tags/v0.1.29"):
            return httpx.Response(200, json={"assets": [{"name": "pkg.whl"}]})
        if request.url.path.endswith("/pypi/eu-ai-act-compliance-kit/json"):
            return httpx.Response(200, json={"info": {"version": "0.1.27"}})
        if request.url.path == "/rtd":
            return httpx.Response(200, text="ok")
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)

    result = OpsCloseoutEvaluator().evaluate(
        mode="observe",
        version="0.1.29",
        release_run_id=11,
        repo="acme/repo",
        pypi_project="eu-ai-act-compliance-kit",
        rtd_url="https://example.test/rtd",
        github_api_base_url="https://example.test/api",
        pypi_base_url="https://example.test",
    )

    assert result.mode == "observe"
    assert result.failed is True
    assert "github_release_failed" in result.reason_codes
    assert "pypi_version_failed" in result.reason_codes


def test_ops_closeout_evaluator_enforce_mode_marks_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce mode should flag failures for failed checks deterministically."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/runs/99"):
            return httpx.Response(200, json={"status": "completed", "conclusion": "failure"})
        if request.url.path.endswith("/releases/tags/v0.1.29"):
            return httpx.Response(404, text="missing")
        if request.url.path.endswith("/pypi/eu-ai-act-compliance-kit/json"):
            return httpx.Response(404, text="missing")
        if request.url.path == "/rtd":
            return httpx.Response(503, text="down")
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)

    result = OpsCloseoutEvaluator().evaluate(
        mode="enforce",
        version="0.1.29",
        release_run_id=99,
        repo="acme/repo",
        pypi_project="eu-ai-act-compliance-kit",
        rtd_url="https://example.test/rtd",
        github_api_base_url="https://example.test/api",
        pypi_base_url="https://example.test",
    )

    assert result.mode == "enforce"
    assert result.failed is True
    assert result.reason_codes == [
        "github_run_failed",
        "github_release_failed",
        "pypi_version_failed",
        "rtd_failed",
    ]


def test_normalize_ops_closeout_mode_rejects_invalid_value() -> None:
    """Mode normalization should validate known mode values."""
    with pytest.raises(ValueError, match="mode must be one of"):
        normalize_ops_closeout_mode("invalid")


def test_resolve_ops_closeout_policy_precedence_cli_over_file() -> None:
    """CLI overrides should take precedence over policy file and defaults."""
    policy = resolve_ops_closeout_policy(
        policy_payload={
            "mode": "enforce",
            "repo": "acme/platform",
            "pypi_project": "acme-platform",
            "rtd_url": "https://docs.example.com/en/latest/",
            "release": {
                "version": "9.9.9",
                "run_id": 99,
            },
        },
        mode="observe",
        release_version="0.1.29",
        release_run_id=234,
        repo="acme/repo",
        pypi_project="eu-ai-act-compliance-kit",
        rtd_url="https://example.test/rtd",
    )

    assert policy.mode == "observe"
    assert policy.release_version == "0.1.29"
    assert policy.release_run_id == 234
    assert policy.repo == "acme/repo"
    assert policy.pypi_project == "eu-ai-act-compliance-kit"
    assert policy.rtd_url == "https://example.test/rtd"


def test_resolve_ops_closeout_policy_defaults_allow_missing_release_inputs() -> None:
    """Release fields are optional in resolved policy for observe-mode diagnostics."""
    policy = resolve_ops_closeout_policy()
    assert policy.mode == "observe"
    assert policy.release_version is None
    assert policy.release_run_id is None


def test_resolve_ops_closeout_policy_rejects_invalid_release_run_id() -> None:
    """Policy parser should reject invalid release.run_id values."""
    with pytest.raises(ValueError, match="release.run_id"):
        resolve_ops_closeout_policy(policy_payload={"release": {"run_id": 0}})
