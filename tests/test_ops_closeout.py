"""Unit tests for ops closeout evaluator."""

from __future__ import annotations

import httpx
import pytest

from eu_ai_act.ops_closeout import (
    OpsCloseoutEvaluator,
    normalize_ops_closeout_mode,
    resolve_latest_release_inputs,
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
    assert result.freshness_reason_codes == []
    assert result.waiver_summary == {
        "configured_count": 0,
        "matched_count": 0,
        "waived_count": 0,
        "expired_count": 0,
    }
    assert result.waived_reason_codes == []
    assert result.expired_waiver_reason_codes == []
    assert result.effective_reason_codes == []
    assert result.freshness_metrics == {
        "run_age_hours": None,
        "release_age_hours": None,
        "rtd_age_hours": None,
    }
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
    assert "github_release_failed" in result.effective_reason_codes
    assert "pypi_version_failed" in result.effective_reason_codes
    assert result.freshness_reason_codes == []
    assert result.waived_reason_codes == []
    assert result.expired_waiver_reason_codes == []


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
    assert result.effective_reason_codes == [
        "github_run_failed",
        "github_release_failed",
        "pypi_version_failed",
        "rtd_failed",
    ]
    assert result.freshness_reason_codes == []
    assert result.waived_reason_codes == []
    assert result.expired_waiver_reason_codes == []


def test_ops_closeout_evaluator_freshness_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured freshness thresholds should append deterministic stale reason codes."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/runs/234"):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "conclusion": "success",
                    "updated_at": "2026-03-20T00:00:00Z",
                },
            )
        if request.url.path.endswith("/releases/tags/v0.1.29"):
            return httpx.Response(
                200,
                json={
                    "assets": [
                        {"name": "eu_ai_act_compliance_kit-0.1.29-py3-none-any.whl"},
                        {"name": "eu_ai_act_compliance_kit-0.1.29.tar.gz"},
                    ],
                    "published_at": "2026-03-20T00:00:00Z",
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
        max_run_age_hours=1.0,
        max_release_age_hours=1.0,
        max_rtd_age_hours=1.0,
    )

    assert result.failed is True
    assert "github_run_stale" in result.freshness_reason_codes
    assert "github_release_stale" in result.freshness_reason_codes
    assert "rtd_stale_or_unknown" in result.freshness_reason_codes
    assert "github_run_stale" in result.effective_reason_codes
    assert "github_release_stale" in result.effective_reason_codes
    assert "rtd_stale_or_unknown" in result.effective_reason_codes
    assert result.freshness_metrics["run_age_hours"] is not None
    assert result.freshness_metrics["release_age_hours"] is not None
    assert result.freshness_metrics["rtd_age_hours"] is None


def test_ops_closeout_evaluator_applies_active_waivers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Active waivers should suppress matching reason codes from effective decision."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/runs/234"):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "conclusion": "success",
                    "updated_at": "2026-03-20T00:00:00Z",
                },
            )
        if request.url.path.endswith("/releases/tags/v0.1.29"):
            return httpx.Response(
                200,
                json={
                    "assets": [
                        {"name": "eu_ai_act_compliance_kit-0.1.29-py3-none-any.whl"},
                        {"name": "eu_ai_act_compliance_kit-0.1.29.tar.gz"},
                    ],
                    "published_at": "2026-03-20T00:00:00Z",
                },
            )
        if request.url.path.endswith("/pypi/eu-ai-act-compliance-kit/json"):
            return httpx.Response(200, json={"info": {"version": "0.1.29"}})
        if request.url.path == "/rtd":
            return httpx.Response(200, text="ok")
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)

    policy = resolve_ops_closeout_policy(
        waivers=[
            {
                "reason_code": "github_run_stale",
                "expires_at": "2099-01-01T00:00:00Z",
                "note": "temporary waiver",
            },
            {
                "reason_code": "github_release_stale",
                "expires_at": "2099-01-01T00:00:00Z",
            },
            {
                "reason_code": "rtd_stale_or_unknown",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        ],
    )

    result = OpsCloseoutEvaluator().evaluate(
        mode="enforce",
        version="0.1.29",
        release_run_id=234,
        repo="acme/repo",
        pypi_project="eu-ai-act-compliance-kit",
        rtd_url="https://example.test/rtd",
        github_api_base_url="https://example.test/api",
        pypi_base_url="https://example.test",
        max_run_age_hours=1.0,
        max_release_age_hours=1.0,
        max_rtd_age_hours=1.0,
        waivers=policy.waivers,
    )

    assert result.failed is False
    assert "github_run_stale" in result.reason_codes
    assert "github_release_stale" in result.reason_codes
    assert "rtd_stale_or_unknown" in result.reason_codes
    assert result.effective_reason_codes == []
    assert sorted(result.waived_reason_codes) == [
        "github_release_stale",
        "github_run_stale",
        "rtd_stale_or_unknown",
    ]
    assert result.expired_waiver_reason_codes == []
    assert result.waiver_summary == {
        "configured_count": 3,
        "matched_count": 3,
        "waived_count": 3,
        "expired_count": 0,
    }


def test_ops_closeout_evaluator_reports_expired_waiver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expired waivers must not suppress matching reasons in effective decision."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/runs/234"):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "conclusion": "success",
                    "updated_at": "2026-03-20T00:00:00Z",
                },
            )
        if request.url.path.endswith("/releases/tags/v0.1.29"):
            return httpx.Response(
                200,
                json={
                    "assets": [
                        {"name": "eu_ai_act_compliance_kit-0.1.29-py3-none-any.whl"},
                        {"name": "eu_ai_act_compliance_kit-0.1.29.tar.gz"},
                    ],
                    "published_at": "2026-03-20T00:00:00Z",
                },
            )
        if request.url.path.endswith("/pypi/eu-ai-act-compliance-kit/json"):
            return httpx.Response(200, json={"info": {"version": "0.1.29"}})
        if request.url.path == "/rtd":
            return httpx.Response(200, text="ok")
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)

    policy = resolve_ops_closeout_policy(
        waivers=[
            {
                "reason_code": "github_run_stale",
                "expires_at": "2000-01-01T00:00:00Z",
            }
        ],
    )
    result = OpsCloseoutEvaluator().evaluate(
        mode="enforce",
        version="0.1.29",
        release_run_id=234,
        repo="acme/repo",
        pypi_project="eu-ai-act-compliance-kit",
        rtd_url="https://example.test/rtd",
        github_api_base_url="https://example.test/api",
        pypi_base_url="https://example.test",
        max_run_age_hours=1.0,
        max_release_age_hours=1.0,
        max_rtd_age_hours=1.0,
        waivers=policy.waivers,
    )

    assert result.failed is True
    assert "github_run_stale" in result.effective_reason_codes
    assert result.waived_reason_codes == []
    assert result.expired_waiver_reason_codes == ["github_run_stale"]
    assert result.waiver_summary == {
        "configured_count": 1,
        "matched_count": 1,
        "waived_count": 0,
        "expired_count": 1,
    }


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
                "resolve_latest": True,
            },
            "thresholds": {
                "max_run_age_hours": 48,
                "max_release_age_hours": 72,
                "max_rtd_age_hours": 24,
            },
        },
        mode="observe",
        release_version="0.1.29",
        release_run_id=234,
        repo="acme/repo",
        pypi_project="eu-ai-act-compliance-kit",
        rtd_url="https://example.test/rtd",
        max_run_age_hours=12,
        resolve_latest_release=False,
    )

    assert policy.mode == "observe"
    assert policy.release_version == "0.1.29"
    assert policy.release_run_id == 234
    assert policy.repo == "acme/repo"
    assert policy.pypi_project == "eu-ai-act-compliance-kit"
    assert policy.rtd_url == "https://example.test/rtd"
    assert policy.max_run_age_hours == 12
    assert policy.max_release_age_hours == 72
    assert policy.max_rtd_age_hours == 24
    assert policy.resolve_latest_release is False
    assert policy.waivers == []


def test_resolve_ops_closeout_policy_cli_waivers_override_policy_waivers() -> None:
    """CLI waiver overrides should replace policy-file waivers deterministically."""
    policy = resolve_ops_closeout_policy(
        policy_payload={
            "waivers": [
                {
                    "reason_code": "github_run_stale",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
        waivers=[
            {
                "reason_code": "github_release_stale",
                "expires_at": "2099-01-02T00:00:00Z",
                "note": "cli override",
            }
        ],
    )

    assert len(policy.waivers) == 1
    assert policy.waivers[0].reason_code == "github_release_stale"
    assert policy.waivers[0].expires_at.isoformat().replace("+00:00", "Z") == "2099-01-02T00:00:00Z"
    assert policy.waivers[0].note == "cli override"


def test_resolve_ops_closeout_policy_defaults_allow_missing_release_inputs() -> None:
    """Release fields are optional in resolved policy for observe-mode diagnostics."""
    policy = resolve_ops_closeout_policy()
    assert policy.mode == "observe"
    assert policy.release_version is None
    assert policy.release_run_id is None
    assert policy.resolve_latest_release is False
    assert policy.waivers == []


def test_resolve_ops_closeout_policy_rejects_invalid_release_run_id() -> None:
    """Policy parser should reject invalid release.run_id values."""
    with pytest.raises(ValueError, match="release.run_id"):
        resolve_ops_closeout_policy(policy_payload={"release": {"run_id": 0}})


def test_resolve_ops_closeout_policy_rejects_invalid_freshness_threshold() -> None:
    """Policy parser should reject non-positive freshness threshold values."""
    with pytest.raises(ValueError, match="max_run_age_hours"):
        resolve_ops_closeout_policy(policy_payload={"thresholds": {"max_run_age_hours": 0}})


def test_resolve_ops_closeout_policy_parses_resolve_latest_flag() -> None:
    """Policy parser should preserve release.resolve_latest toggle."""
    policy = resolve_ops_closeout_policy(policy_payload={"release": {"resolve_latest": True}})
    assert policy.resolve_latest_release is True


def test_resolve_ops_closeout_policy_rejects_invalid_resolve_latest_flag() -> None:
    """Policy parser should reject invalid non-boolean resolve_latest values."""
    with pytest.raises(ValueError, match="release.resolve_latest"):
        resolve_ops_closeout_policy(policy_payload={"release": {"resolve_latest": "maybe"}})


def test_resolve_ops_closeout_policy_rejects_invalid_waiver_expires_at() -> None:
    """Policy parser should reject waiver entries with invalid expiry datetime."""
    with pytest.raises(ValueError, match="expires_at"):
        resolve_ops_closeout_policy(
            policy_payload={
                "waivers": [
                    {
                        "reason_code": "github_run_stale",
                        "expires_at": "invalid",
                    }
                ]
            }
        )


def test_resolve_ops_closeout_policy_rejects_missing_waiver_reason_code() -> None:
    """Policy parser should reject waiver entries without non-empty reason_code."""
    with pytest.raises(ValueError, match="reason_code"):
        resolve_ops_closeout_policy(
            policy_payload={
                "waivers": [
                    {
                        "reason_code": "",
                        "expires_at": "2099-01-01T00:00:00Z",
                    }
                ]
            }
        )


def test_resolve_latest_release_inputs_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Latest release resolver should return highest semver and matching successful run id."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/acme/repo/releases"):
            return httpx.Response(
                200,
                json=[
                    {"tag_name": "v0.1.30", "draft": False},
                    {"tag_name": "v0.1.31", "draft": False},
                    {"tag_name": "docs-preview", "draft": False},
                ],
            )
        if request.url.path.endswith("/repos/acme/repo/actions/workflows/release.yml/runs"):
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 900,
                            "head_branch": "v0.1.30",
                            "status": "completed",
                            "conclusion": "success",
                        },
                        {
                            "id": 1000,
                            "head_branch": "v0.1.31",
                            "status": "completed",
                            "conclusion": "failure",
                        },
                        {
                            "id": 1001,
                            "head_branch": "v0.1.31",
                            "status": "completed",
                            "conclusion": "success",
                        },
                        {
                            "id": 1002,
                            "head_branch": "v0.1.31",
                            "status": "completed",
                            "conclusion": "success",
                        },
                    ]
                },
            )
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)
    result = resolve_latest_release_inputs(
        repo="acme/repo",
        github_api_base_url="https://example.test/api",
    )

    assert result.resolved_version == "0.1.31"
    assert result.resolved_run_id == 1002
    assert result.reason_codes == []
    assert result.resolution_source == "github_release_workflow_runs_api"


def test_resolve_latest_release_inputs_prefers_requested_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should use requested version for run lookup when version is explicitly provided."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/acme/repo/releases"):
            return httpx.Response(
                200,
                json=[
                    {"tag_name": "v0.1.30", "draft": False},
                    {"tag_name": "v0.1.31", "draft": False},
                ],
            )
        if request.url.path.endswith("/repos/acme/repo/actions/workflows/release.yml/runs"):
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 900,
                            "head_branch": "v0.1.30",
                            "status": "completed",
                            "conclusion": "success",
                        },
                        {
                            "id": 1002,
                            "head_branch": "v0.1.31",
                            "status": "completed",
                            "conclusion": "success",
                        },
                    ]
                },
            )
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)
    result = resolve_latest_release_inputs(
        repo="acme/repo",
        preferred_version="0.1.30",
        github_api_base_url="https://example.test/api",
    )

    assert result.resolved_version == "0.1.30"
    assert result.resolved_run_id == 900
    assert result.reason_codes == []
    assert result.resolution_source == "github_release_workflow_runs_api"


def test_resolve_latest_release_inputs_reports_missing_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should emit deterministic reason when no semver release exists."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/acme/repo/releases"):
            return httpx.Response(200, json=[{"tag_name": "nightly", "draft": False}])
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)
    result = resolve_latest_release_inputs(
        repo="acme/repo",
        github_api_base_url="https://example.test/api",
    )

    assert result.resolved_version is None
    assert result.resolved_run_id is None
    assert result.reason_codes == ["latest_release_not_found"]


def test_resolve_latest_release_inputs_reports_missing_release_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should emit deterministic reason when matching successful release run is absent."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/acme/repo/releases"):
            return httpx.Response(200, json=[{"tag_name": "v0.1.31", "draft": False}])
        if request.url.path.endswith("/repos/acme/repo/actions/workflows/release.yml/runs"):
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 1000,
                            "head_branch": "v0.1.31",
                            "status": "in_progress",
                            "conclusion": "",
                        },
                        {
                            "id": 1001,
                            "head_branch": "v0.1.31",
                            "status": "completed",
                            "conclusion": "failure",
                        },
                    ]
                },
            )
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)
    result = resolve_latest_release_inputs(
        repo="acme/repo",
        github_api_base_url="https://example.test/api",
    )

    assert result.resolved_version == "0.1.31"
    assert result.resolved_run_id is None
    assert result.reason_codes == ["latest_release_run_not_found"]


def test_resolve_latest_release_inputs_reports_resolution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should emit generic resolution failure on upstream request error."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/acme/repo/releases"):
            return httpx.Response(500, text="boom")
        return httpx.Response(404)

    _patch_http_client(monkeypatch, handler)
    result = resolve_latest_release_inputs(
        repo="acme/repo",
        github_api_base_url="https://example.test/api",
    )

    assert result.resolved_version is None
    assert result.resolved_run_id is None
    assert result.reason_codes == ["release_resolution_failed"]
