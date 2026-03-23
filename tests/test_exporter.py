"""Tests for payload-first external export generation."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from eu_ai_act.checker import ComplianceChecker, ComplianceStatus
from eu_ai_act.exporter import (
    ExportGenerator,
    ExportPusher,
    ExportPushError,
    list_export_ops_log_records,
    reconcile_export_push_records,
    replay_export_push_failures,
    run_export_batch,
    summarize_export_ops_rollup,
)
from eu_ai_act.history import build_event
from eu_ai_act.schema import load_system_descriptor_from_file

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


def test_from_check_generic_contract_and_status_actionability():
    """Check-source export should expose canonical contract with normalized statuses."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)

    envelope = ExportGenerator().from_check(report=report, target="generic")
    payload = envelope.to_dict()

    assert payload["schema_version"] == "1.0"
    assert payload["source_type"] == "check"
    assert payload["target"] == "generic"
    assert payload["system_name"] == descriptor.name
    assert payload["risk_tier"] == "high_risk"
    assert "security_mapping" in payload
    assert payload["security_mapping"]["framework"] == "owasp-llm-top-10"
    assert payload["security_mapping"]["summary"]["total_controls"] == 10
    assert len(payload["security_mapping"]["controls"]) == 10

    summary = payload["summary"]
    assert summary["total_requirements"] == 6
    assert "compliance_percentage" in summary

    items = payload["items"]
    assert len(items) == 6
    for item in items:
        assert item["status"] in {"non_compliant", "partial", "not_assessed", "compliant"}
        assert item["actionable"] == (
            item["status"] in {"non_compliant", "partial", "not_assessed"}
        )
        assert item["article"].startswith("Art.")

    adapter_payload = payload["adapter_payload"]
    assert adapter_payload["format"] == "generic/v1"
    assert len(adapter_payload["records"]) == len(items)


def test_from_check_can_include_descriptor_path_metadata():
    """Check-source export should preserve descriptor identity when provided."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)

    payload = (
        ExportGenerator()
        .from_check(
            report=report,
            target="generic",
            descriptor_path="/tmp/medical_diagnosis.yaml",
        )
        .to_dict()
    )

    assert payload["descriptor_path"] == "/tmp/medical_diagnosis.yaml"


def test_from_check_jira_and_servicenow_adapters_only_include_actionable_items():
    """Jira and ServiceNow payloads should generate records only for actionable items."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    generator = ExportGenerator()

    jira_payload = generator.from_check(report=report, target="jira").to_dict()
    servicenow_payload = generator.from_check(report=report, target="servicenow").to_dict()

    actionable_count = sum(1 for item in jira_payload["items"] if item["actionable"])

    assert jira_payload["adapter_payload"]["format"] == "jira/issues/v1"
    assert len(jira_payload["adapter_payload"]["issues"]) == actionable_count
    if actionable_count:
        jira_issue_fields = jira_payload["adapter_payload"]["issues"][0]["fields"]
        assert "summary" in jira_issue_fields
        assert "description" in jira_issue_fields
        assert "labels" in jira_issue_fields

    assert servicenow_payload["adapter_payload"]["format"] == "servicenow/records/v1"
    assert len(servicenow_payload["adapter_payload"]["records"]) == actionable_count
    if actionable_count:
        snow_record = servicenow_payload["adapter_payload"]["records"][0]
        assert "short_description" in snow_record
        assert "description" in snow_record
        assert snow_record["category"] == "compliance"


def test_from_history_preserves_event_metadata():
    """History-source export should include history metadata and normalized items."""
    event = build_event(
        event_type="check",
        system_name="Snapshot System",
        descriptor_path="/tmp/snapshot.yaml",
        risk_tier="limited",
        summary={
            "total_requirements": 2,
            "compliant_count": 1,
            "non_compliant_count": 0,
            "partial_count": 1,
            "not_assessed_count": 0,
            "compliance_percentage": 75.0,
        },
        finding_statuses={"Art. 50": "partial", "Art. 11": "compliant"},
    )

    payload = ExportGenerator().from_history(event=event, target="servicenow").to_dict()

    assert payload["source_type"] == "history"
    assert payload["event_id"] == event.event_id
    assert payload["event_type"] == "check"
    assert payload["descriptor_path"] == "/tmp/snapshot.yaml"
    assert payload["history_generated_at"] == event.generated_at
    assert payload["summary"]["partial_count"] == 1
    assert "security_mapping" in payload
    assert payload["security_mapping"]["framework"] == "owasp-llm-top-10"
    assert payload["security_mapping"]["summary"]["total_controls"] == 10
    assert len(payload["security_mapping"]["controls"]) == 10
    assert len(payload["items"]) == 2
    assert payload["adapter_payload"]["format"] == "servicenow/records/v1"
    assert payload["adapter_payload"]["actionable_count"] == 1


def test_invalid_target_raises_value_error():
    """Unsupported adapter target should fail deterministically."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "spam_filter.yaml")
    report = ComplianceChecker().check(descriptor)

    with pytest.raises(ValueError, match="Unsupported export target"):
        ExportGenerator().from_check(report=report, target="unknown")  # type: ignore[arg-type]


def test_invalid_history_status_raises_value_error():
    """Unsupported status values in history events should fail export generation."""
    event = build_event(
        event_type="check",
        system_name="Broken Snapshot",
        descriptor_path="/tmp/broken.yaml",
        risk_tier="minimal",
        summary={
            "total_requirements": 1,
            "compliant_count": 0,
            "non_compliant_count": 0,
            "partial_count": 0,
            "not_assessed_count": 1,
            "compliance_percentage": 0.0,
        },
        finding_statuses={"Art. 69": "blocked"},
    )

    with pytest.raises(ValueError, match="Unsupported status value"):
        ExportGenerator().from_history(event=event, target="generic")


def test_push_rejects_generic_target():
    """Live push should fail for generic target by contract."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "spam_filter.yaml")
    report = ComplianceChecker().check(descriptor)
    envelope = ExportGenerator().from_check(report=report, target="generic")

    with pytest.raises(ValueError, match="Live push is not supported for target 'generic'"):
        ExportPusher(idempotency_enabled=False).push(envelope)


def test_push_dry_run_for_jira_requires_no_credentials():
    """Dry-run should not require environment credentials and should return deterministic summary."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    envelope = ExportGenerator().from_check(report=report, target="jira")

    result = ExportPusher(idempotency_enabled=False).push(envelope, dry_run=True)

    assert result["target"] == "jira"
    assert result["dry_run"] is True
    assert result["attempted_actionable_count"] == sum(
        1 for item in envelope.items if item.actionable
    )
    assert result["pushed_count"] == 0
    assert result["failed_count"] == 0


def test_push_jira_missing_env_raises_value_error(monkeypatch):
    """Live Jira push should fail-fast when required environment variables are missing."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    envelope = ExportGenerator().from_check(report=report, target="jira")

    for key in [
        "EU_AI_ACT_JIRA_BASE_URL",
        "EU_AI_ACT_JIRA_EMAIL",
        "EU_AI_ACT_JIRA_API_TOKEN",
        "EU_AI_ACT_JIRA_PROJECT_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(
        ValueError, match="Missing required environment variable: EU_AI_ACT_JIRA_BASE_URL"
    ):
        ExportPusher(idempotency_enabled=False).push(envelope, dry_run=False)


def test_push_jira_success_with_mock_transport(monkeypatch):
    """Live Jira push should report success counts when remote API responds 201."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    envelope = ExportGenerator().from_check(report=report, target="jira")
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://example.atlassian.net/rest/api/3/issue"
        return httpx.Response(status_code=201, json={"key": "EUAI-100"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    result = ExportPusher(idempotency_enabled=False).push(envelope)
    assert result["target"] == "jira"
    assert result["dry_run"] is False
    assert result["attempted_actionable_count"] == len(envelope.adapter_payload["issues"])
    assert result["pushed_count"] == len(envelope.adapter_payload["issues"])
    assert result["failed_count"] == 0
    assert result["failure_reason"] is None


def test_push_jira_retries_on_5xx_then_succeeds(monkeypatch):
    """Retryable 5xx responses should be retried with eventual success."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return httpx.Response(status_code=503, text="temporary outage")
        return httpx.Response(status_code=201, json={"key": f"EUAI-{call_counter['count']}"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    result = ExportPusher(max_retries=3, idempotency_enabled=False).push(envelope)
    issue_count = len(envelope.adapter_payload["issues"])
    assert result["pushed_count"] == issue_count
    assert result["failed_count"] == 0
    assert result["results"][0]["attempts"] == 2
    assert result["results"][0]["retries_used"] == 1
    assert call_counter["count"] == issue_count + 1


def test_push_jira_retries_on_429_then_succeeds(monkeypatch):
    """Retryable 429 responses should be retried before succeeding."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return httpx.Response(status_code=429, text="rate limit")
        return httpx.Response(status_code=201, json={"key": f"EUAI-{call_counter['count']}"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    result = ExportPusher(max_retries=3, idempotency_enabled=False).push(envelope)
    issue_count = len(envelope.adapter_payload["issues"])
    assert result["pushed_count"] == issue_count
    assert result["failed_count"] == 0
    assert result["results"][0]["attempts"] == 2
    assert result["results"][0]["retries_used"] == 1
    assert call_counter["count"] == issue_count + 1


def test_push_jira_retries_on_transport_error_then_succeeds(monkeypatch):
    """Transport errors should be retried with backoff before eventual success."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise httpx.TransportError("connection reset by peer")
        return httpx.Response(status_code=201, json={"key": f"EUAI-{call_counter['count']}"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    result = ExportPusher(max_retries=3, idempotency_enabled=False).push(envelope)
    issue_count = len(envelope.adapter_payload["issues"])
    assert result["pushed_count"] == issue_count
    assert result["failed_count"] == 0
    assert result["results"][0]["attempts"] == 2
    assert result["results"][0]["retries_used"] == 1
    assert call_counter["count"] == issue_count + 1


def test_push_jira_retry_exhaustion_fails_fast(monkeypatch):
    """Retryable failures should abort after retries are exhausted on first failing item."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        return httpx.Response(status_code=503, text="temporary outage")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    with pytest.raises(ExportPushError) as exc_info:
        ExportPusher(max_retries=2, idempotency_enabled=False).push(envelope)

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["pushed_count"] == 0
    assert "HTTP 503" in push_result["failure_reason"]
    assert push_result["results"][0]["attempts"] == 3
    assert call_counter["count"] == 3


def test_push_jira_does_not_retry_non_retryable_4xx(monkeypatch):
    """Non-retryable 4xx responses should fail immediately without retry loop."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        return httpx.Response(status_code=400, text="bad request")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    with pytest.raises(ExportPushError) as exc_info:
        ExportPusher(max_retries=5, idempotency_enabled=False).push(envelope)

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["results"][0]["attempts"] == 1
    assert "HTTP 400" in push_result["failure_reason"]
    assert call_counter["count"] == 1


def test_push_jira_upsert_lookup_miss_creates(monkeypatch):
    """Upsert mode should create new Jira issues when lookup finds no existing issue."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"search": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["search"] += 1
            return httpx.Response(status_code=200, json={"issues": []})
        if request.method == "POST":
            call_counter["create"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            labels = payload["fields"].get("labels", [])
            assert any(label.startswith("eu-ai-act-idem-") for label in labels)
            return httpx.Response(status_code=201, json={"key": f"EUAI-{call_counter['create']}"})
        call_counter["update"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    result = ExportPusher(idempotency_enabled=False, max_retries=0).push(
        envelope,
        push_mode="upsert",
    )
    issue_count = len(envelope.adapter_payload["issues"])
    assert result["push_mode"] == "upsert"
    assert result["pushed_count"] == issue_count
    assert result["created_count"] == issue_count
    assert result["updated_count"] == 0
    assert call_counter["search"] == issue_count
    assert call_counter["create"] == issue_count
    assert call_counter["update"] == 0
    assert all(item["operation"] == "created" for item in result["results"])


def test_push_jira_upsert_lookup_hit_updates(monkeypatch):
    """Upsert mode should update Jira issues when lookup matches by idempotency label."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"search": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["search"] += 1
            return httpx.Response(
                status_code=200,
                json={"issues": [{"key": f"EUAI-{call_counter['search']}"}]},
            )
        if request.method == "PUT":
            call_counter["update"] += 1
            return httpx.Response(status_code=204, text="")
        call_counter["create"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    result = ExportPusher(idempotency_enabled=False, max_retries=0).push(
        envelope,
        push_mode="upsert",
    )
    issue_count = len(envelope.adapter_payload["issues"])
    assert result["push_mode"] == "upsert"
    assert result["pushed_count"] == issue_count
    assert result["created_count"] == 0
    assert result["updated_count"] == issue_count
    assert call_counter["search"] == issue_count
    assert call_counter["update"] == issue_count
    assert call_counter["create"] == 0
    assert all(item["operation"] == "updated" for item in result["results"])


def test_push_jira_upsert_lookup_non_retryable_4xx_fails_fast(monkeypatch):
    """Non-retryable 4xx during Jira lookup should abort immediately in upsert mode."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for finding in report.findings.values():
        finding.status = ComplianceStatus.COMPLIANT
    first_requirement = next(iter(report.findings.keys()))
    report.findings[first_requirement].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"search": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["search"] += 1
            return httpx.Response(status_code=400, text="bad search request")
        if request.method == "POST":
            call_counter["create"] += 1
        if request.method == "PUT":
            call_counter["update"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    with pytest.raises(ExportPushError) as exc_info:
        ExportPusher(idempotency_enabled=False, max_retries=3).push(
            envelope,
            push_mode="upsert",
        )

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["created_count"] == 0
    assert push_result["updated_count"] == 0
    assert push_result["results"][0]["operation"] == "lookup"
    assert push_result["results"][0]["attempts"] == 1
    assert "HTTP 400" in push_result["failure_reason"]
    assert call_counter["search"] == 1
    assert call_counter["create"] == 0
    assert call_counter["update"] == 0


def test_push_jira_upsert_lookup_retries_on_5xx_then_updates(monkeypatch):
    """Retryable lookup failures in upsert mode should retry, then update on match."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for finding in report.findings.values():
        finding.status = ComplianceStatus.COMPLIANT
    first_requirement = next(iter(report.findings.keys()))
    report.findings[first_requirement].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"search": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["search"] += 1
            if call_counter["search"] == 1:
                return httpx.Response(status_code=503, text="temporary search outage")
            return httpx.Response(status_code=200, json={"issues": [{"key": "EUAI-42"}]})
        if request.method == "PUT":
            call_counter["update"] += 1
            return httpx.Response(status_code=204, text="")
        call_counter["create"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    result = ExportPusher(idempotency_enabled=False, max_retries=3).push(
        envelope,
        push_mode="upsert",
    )
    assert result["pushed_count"] == 1
    assert result["created_count"] == 0
    assert result["updated_count"] == 1
    assert call_counter["search"] == 2
    assert call_counter["update"] == 1
    assert call_counter["create"] == 0
    assert result["results"][0]["operation"] == "updated"


def test_push_jira_upsert_create_retry_exhaustion_fails_fast(monkeypatch):
    """Upsert create branch should fail-fast after retry exhaustion."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for finding in report.findings.values():
        finding.status = ComplianceStatus.COMPLIANT
    first_requirement = next(iter(report.findings.keys()))
    report.findings[first_requirement].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"search": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["search"] += 1
            return httpx.Response(status_code=200, json={"issues": []})
        if request.method == "POST":
            call_counter["create"] += 1
            return httpx.Response(status_code=503, text="temporary create outage")
        call_counter["update"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    with pytest.raises(ExportPushError) as exc_info:
        ExportPusher(idempotency_enabled=False, max_retries=2).push(
            envelope,
            push_mode="upsert",
        )

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["pushed_count"] == 0
    assert push_result["created_count"] == 0
    assert push_result["updated_count"] == 0
    assert push_result["results"][0]["operation"] == "created"
    assert push_result["results"][0]["attempts"] == 3
    assert "HTTP 503" in push_result["failure_reason"]
    assert call_counter["search"] == 1
    assert call_counter["create"] == 3
    assert call_counter["update"] == 0


def test_push_jira_upsert_update_non_retryable_4xx_fails_immediately(monkeypatch):
    """Upsert update branch should not retry non-retryable 4xx responses."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for finding in report.findings.values():
        finding.status = ComplianceStatus.COMPLIANT
    first_requirement = next(iter(report.findings.keys()))
    report.findings[first_requirement].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"search": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["search"] += 1
            return httpx.Response(status_code=200, json={"issues": [{"key": "EUAI-42"}]})
        if request.method == "PUT":
            call_counter["update"] += 1
            return httpx.Response(status_code=400, text="invalid update request")
        call_counter["create"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    with pytest.raises(ExportPushError) as exc_info:
        ExportPusher(idempotency_enabled=False, max_retries=3).push(
            envelope,
            push_mode="upsert",
        )

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["results"][0]["operation"] == "updated"
    assert push_result["results"][0]["attempts"] == 1
    assert "HTTP 400" in push_result["failure_reason"]
    assert call_counter["search"] == 1
    assert call_counter["update"] == 1
    assert call_counter["create"] == 0


def test_push_jira_duplicate_items_are_skipped_via_idempotency_ledger(monkeypatch, tmp_path):
    """Second push with same payload should skip duplicates and avoid remote calls."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        return httpx.Response(status_code=201, json={"key": f"EUAI-{call_counter['count']}"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    ledger_path = tmp_path / "export_push_ledger.jsonl"
    pusher = ExportPusher(idempotency_path=ledger_path, max_retries=0)
    first = pusher.push(envelope)
    second = pusher.push(envelope)

    actionable_count = len(envelope.adapter_payload["issues"])
    assert first["pushed_count"] == actionable_count
    assert first["skipped_duplicate_count"] == 0
    assert second["pushed_count"] == 0
    assert second["skipped_duplicate_count"] == actionable_count
    assert all(item["status"] == "skipped_duplicate" for item in second["results"])
    assert call_counter["count"] == actionable_count
    assert ledger_path.exists()
    assert len(ledger_path.read_text(encoding="utf-8").strip().splitlines()) == actionable_count


def test_push_jira_upsert_ignores_ledger_duplicate_skip(monkeypatch, tmp_path):
    """Upsert mode should still perform lookup/update even when ledger keys already exist."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"search": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["search"] += 1
            return httpx.Response(
                status_code=200,
                json={"issues": [{"key": f"EUAI-{call_counter['search']}"}]},
            )
        if request.method == "PUT":
            call_counter["update"] += 1
            return httpx.Response(status_code=204, text="")
        call_counter["create"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    ledger_path = tmp_path / "export_push_ledger.jsonl"
    pusher = ExportPusher(idempotency_path=ledger_path, max_retries=0)
    first = pusher.push(envelope, push_mode="upsert")
    second = pusher.push(envelope, push_mode="upsert")

    actionable_count = len(envelope.adapter_payload["issues"])
    assert first["updated_count"] == actionable_count
    assert second["updated_count"] == actionable_count
    assert second["skipped_duplicate_count"] == 0
    assert all(item["status"] == "success" for item in second["results"])
    assert call_counter["search"] == actionable_count * 2
    assert call_counter["update"] == actionable_count * 2
    assert call_counter["create"] == 0


def test_push_jira_check_source_idempotency_uses_descriptor_identity(monkeypatch, tmp_path):
    """Different descriptor paths must produce different idempotency keys for check exports."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT

    envelope_a = ExportGenerator().from_check(
        report=report,
        target="jira",
        descriptor_path="/tmp/system_a.yaml",
    )
    envelope_b = ExportGenerator().from_check(
        report=report,
        target="jira",
        descriptor_path="/tmp/system_b.yaml",
    )

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        return httpx.Response(status_code=201, json={"key": f"EUAI-{call_counter['count']}"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    ledger_path = tmp_path / "export_push_ledger.jsonl"
    pusher = ExportPusher(idempotency_path=ledger_path, max_retries=0)

    first = pusher.push(envelope_a)
    second = pusher.push(envelope_b)

    actionable_count = len(envelope_a.adapter_payload["issues"])
    assert first["pushed_count"] == actionable_count
    assert second["pushed_count"] == actionable_count
    assert second["skipped_duplicate_count"] == 0
    assert call_counter["count"] == actionable_count * 2


def test_push_jira_success_with_ledger_write_error_keeps_success(monkeypatch, tmp_path):
    """Ledger write failures after remote success should not flip the command to failed."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=201, json={"key": "EUAI-100"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    pusher = ExportPusher(idempotency_path=tmp_path / "ledger.jsonl", max_retries=0)
    monkeypatch.setattr(
        pusher,
        "_append_ledger_record",
        lambda _record: (_ for _ in ()).throw(OSError("read-only filesystem")),
    )

    result = pusher.push(envelope)

    actionable_count = len(envelope.adapter_payload["issues"])
    assert result["pushed_count"] == actionable_count
    assert result["failed_count"] == 0
    assert all(item["status"] == "success" for item in result["results"])
    assert all(item["ledger_recorded"] is False for item in result["results"])
    assert all("read-only filesystem" in item["ledger_error"] for item in result["results"])


def test_push_dry_run_does_not_write_idempotency_ledger(tmp_path):
    """Dry-run must not create or append to idempotency ledger files."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    envelope = ExportGenerator().from_check(report=report, target="jira")

    ledger_path = tmp_path / "export_push_ledger.jsonl"
    result = ExportPusher(idempotency_path=ledger_path).push(envelope, dry_run=True)

    assert result["dry_run"] is True
    assert result["idempotency_enabled"] is True
    assert result["idempotency_path"] == str(ledger_path)
    assert result["skipped_duplicate_count"] == 0
    assert not ledger_path.exists()


def test_push_disable_idempotency_allows_repeat_pushes(monkeypatch, tmp_path):
    """When idempotency is disabled, repeated pushes should call remote every time."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    call_counter = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        return httpx.Response(status_code=201, json={"key": f"EUAI-{call_counter['count']}"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    ledger_path = tmp_path / "export_push_ledger.jsonl"
    pusher = ExportPusher(idempotency_enabled=False, idempotency_path=ledger_path, max_retries=0)
    first = pusher.push(envelope)
    second = pusher.push(envelope)

    actionable_count = len(envelope.adapter_payload["issues"])
    assert first["idempotency_enabled"] is False
    assert first["idempotency_path"] is None
    assert first["pushed_count"] == actionable_count
    assert second["pushed_count"] == actionable_count
    assert call_counter["count"] == actionable_count * 2
    assert not ledger_path.exists()


def test_push_servicenow_duplicate_items_are_skipped_via_idempotency_ledger(monkeypatch, tmp_path):
    """ServiceNow push should apply the same duplicate-skip idempotency behavior."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="servicenow")

    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_INSTANCE_URL", "https://snow.example.com")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_USERNAME", "ops")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_PASSWORD", "secret")

    call_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        assert str(request.url) == "https://snow.example.com/api/now/table/u_ai_act_compliance"
        return httpx.Response(
            status_code=201,
            json={"result": {"sys_id": f"SYS-{call_counter['count']}"}},
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    ledger_path = tmp_path / "export_push_ledger.jsonl"
    pusher = ExportPusher(idempotency_path=ledger_path, max_retries=0)
    first = pusher.push(envelope)
    second = pusher.push(envelope)

    actionable_count = len(envelope.adapter_payload["records"])
    assert first["target"] == "servicenow"
    assert first["pushed_count"] == actionable_count
    assert first["skipped_duplicate_count"] == 0
    assert second["pushed_count"] == 0
    assert second["skipped_duplicate_count"] == actionable_count
    assert all(item["status"] == "skipped_duplicate" for item in second["results"])
    assert call_counter["count"] == actionable_count


def test_push_servicenow_upsert_lookup_miss_creates(monkeypatch):
    """Upsert mode should create ServiceNow records when lookup does not match."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="servicenow")

    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_INSTANCE_URL", "https://snow.example.com")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_USERNAME", "ops")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_PASSWORD", "secret")

    call_counter = {"lookup": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["lookup"] += 1
            return httpx.Response(status_code=200, json={"result": []})
        if request.method == "POST":
            call_counter["create"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert "u_idempotency_key" in payload
            return httpx.Response(
                status_code=201,
                json={"result": {"sys_id": f"SYS-{call_counter['create']}"}},
            )
        call_counter["update"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    result = ExportPusher(idempotency_enabled=False, max_retries=0).push(
        envelope,
        push_mode="upsert",
    )
    record_count = len(envelope.adapter_payload["records"])
    assert result["push_mode"] == "upsert"
    assert result["pushed_count"] == record_count
    assert result["created_count"] == record_count
    assert result["updated_count"] == 0
    assert call_counter["lookup"] == record_count
    assert call_counter["create"] == record_count
    assert call_counter["update"] == 0
    assert all(item["operation"] == "created" for item in result["results"])


def test_push_servicenow_upsert_lookup_hit_updates_with_custom_lookup_field(monkeypatch):
    """Upsert mode should update ServiceNow records using configured idempotency lookup field."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="servicenow")

    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_INSTANCE_URL", "https://snow.example.com")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_USERNAME", "ops")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_PASSWORD", "secret")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_IDEMPOTENCY_FIELD", "u_custom_idem")

    call_counter = {"lookup": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["lookup"] += 1
            assert "u_custom_idem" in str(request.url)
            return httpx.Response(
                status_code=200,
                json={"result": [{"sys_id": f"SYS-{call_counter['lookup']}"}]},
            )
        if request.method == "PATCH":
            call_counter["update"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert "u_custom_idem" in payload
            return httpx.Response(
                status_code=200,
                json={"result": {"sys_id": f"SYS-{call_counter['update']}"}},
            )
        call_counter["create"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    result = ExportPusher(idempotency_enabled=False, max_retries=0).push(
        envelope,
        push_mode="upsert",
    )
    record_count = len(envelope.adapter_payload["records"])
    assert result["push_mode"] == "upsert"
    assert result["pushed_count"] == record_count
    assert result["created_count"] == 0
    assert result["updated_count"] == record_count
    assert call_counter["lookup"] == record_count
    assert call_counter["update"] == record_count
    assert call_counter["create"] == 0
    assert all(item["operation"] == "updated" for item in result["results"])


def test_push_servicenow_upsert_lookup_retries_on_5xx_then_updates(monkeypatch):
    """Retryable lookup errors in upsert mode should retry and then update."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for finding in report.findings.values():
        finding.status = ComplianceStatus.COMPLIANT
    first_requirement = next(iter(report.findings.keys()))
    report.findings[first_requirement].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="servicenow")

    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_INSTANCE_URL", "https://snow.example.com")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_USERNAME", "ops")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_PASSWORD", "secret")

    call_counter = {"lookup": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["lookup"] += 1
            if call_counter["lookup"] == 1:
                return httpx.Response(status_code=503, text="temporary lookup outage")
            return httpx.Response(status_code=200, json={"result": [{"sys_id": "SYS-42"}]})
        if request.method == "PATCH":
            call_counter["update"] += 1
            return httpx.Response(status_code=200, json={"result": {"sys_id": "SYS-42"}})
        call_counter["create"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    result = ExportPusher(idempotency_enabled=False, max_retries=3).push(
        envelope,
        push_mode="upsert",
    )
    assert result["pushed_count"] == 1
    assert result["created_count"] == 0
    assert result["updated_count"] == 1
    assert call_counter["lookup"] == 2
    assert call_counter["update"] == 1
    assert call_counter["create"] == 0
    assert result["results"][0]["operation"] == "updated"


def test_push_servicenow_upsert_create_retry_exhaustion_fails_fast(monkeypatch):
    """Upsert create branch should fail-fast when retries are exhausted."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for finding in report.findings.values():
        finding.status = ComplianceStatus.COMPLIANT
    first_requirement = next(iter(report.findings.keys()))
    report.findings[first_requirement].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="servicenow")

    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_INSTANCE_URL", "https://snow.example.com")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_USERNAME", "ops")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_PASSWORD", "secret")

    call_counter = {"lookup": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["lookup"] += 1
            return httpx.Response(status_code=200, json={"result": []})
        if request.method == "POST":
            call_counter["create"] += 1
            return httpx.Response(status_code=503, text="temporary create outage")
        call_counter["update"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    with pytest.raises(ExportPushError) as exc_info:
        ExportPusher(idempotency_enabled=False, max_retries=2).push(
            envelope,
            push_mode="upsert",
        )

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["pushed_count"] == 0
    assert push_result["created_count"] == 0
    assert push_result["updated_count"] == 0
    assert push_result["results"][0]["operation"] == "created"
    assert push_result["results"][0]["attempts"] == 3
    assert "HTTP 503" in push_result["failure_reason"]
    assert call_counter["lookup"] == 1
    assert call_counter["create"] == 3
    assert call_counter["update"] == 0


def test_push_servicenow_upsert_update_non_retryable_4xx_fails_immediately(monkeypatch):
    """Upsert update branch should fail immediately on non-retryable 4xx."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for finding in report.findings.values():
        finding.status = ComplianceStatus.COMPLIANT
    first_requirement = next(iter(report.findings.keys()))
    report.findings[first_requirement].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="servicenow")

    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_INSTANCE_URL", "https://snow.example.com")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_USERNAME", "ops")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_PASSWORD", "secret")

    call_counter = {"lookup": 0, "create": 0, "update": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["lookup"] += 1
            return httpx.Response(status_code=200, json={"result": [{"sys_id": "SYS-42"}]})
        if request.method == "PATCH":
            call_counter["update"] += 1
            return httpx.Response(status_code=400, text="invalid update request")
        call_counter["create"] += 1
        return httpx.Response(status_code=500, text="unexpected method")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    with pytest.raises(ExportPushError) as exc_info:
        ExportPusher(idempotency_enabled=False, max_retries=3).push(
            envelope,
            push_mode="upsert",
        )

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["results"][0]["operation"] == "updated"
    assert push_result["results"][0]["attempts"] == 1
    assert "HTTP 400" in push_result["failure_reason"]
    assert call_counter["lookup"] == 1
    assert call_counter["update"] == 1
    assert call_counter["create"] == 0


def test_run_export_batch_mixed_valid_invalid_continues(tmp_path):
    """Batch runner should continue on invalid descriptor files and return aggregate counts."""
    valid_path = tmp_path / "a_valid.yaml"
    valid_path.write_text((EXAMPLES_DIR / "spam_filter.yaml").read_text(encoding="utf-8"))
    invalid_path = tmp_path / "b_invalid.yaml"
    invalid_path.write_text("name: broken\nuse_cases: [\n", encoding="utf-8")

    payload = run_export_batch(
        descriptor_dir=tmp_path,
        target="generic",
        recursive=False,
        push=False,
    )

    assert payload["total_files"] == 2
    assert payload["processed_count"] == 1
    assert payload["success_count"] == 1
    assert payload["failure_count"] == 0
    assert payload["invalid_count"] == 1
    assert [item["descriptor_path"] for item in payload["results"]] == [
        str(valid_path.resolve()),
        str(invalid_path.resolve()),
    ]
    statuses = [item["status"] for item in payload["results"]]
    assert statuses == ["success", "invalid_descriptor"]
    success_entry = payload["results"][0]
    assert success_entry["security_mapping"]["framework"] == "owasp-llm-top-10"
    assert success_entry["security_mapping"]["summary"]["total_controls"] == 10


def test_run_export_batch_push_continues_on_failed_descriptor(monkeypatch, tmp_path):
    """Batch push should continue processing and aggregate failed/successful descriptors."""
    first = tmp_path / "a_first.yaml"
    second = tmp_path / "b_second.yaml"
    first.write_text((EXAMPLES_DIR / "medical_diagnosis.yaml").read_text(encoding="utf-8"))
    second.write_text((EXAMPLES_DIR / "chatbot.yaml").read_text(encoding="utf-8"))

    call_counter = {"count": 0}

    def _fake_push(_self, envelope, dry_run=False, push_mode="create"):
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise ExportPushError(
                "simulated push failure",
                push_result={
                    "target": envelope.target,
                    "dry_run": dry_run,
                    "push_mode": push_mode,
                    "attempted_actionable_count": 1,
                    "pushed_count": 0,
                    "created_count": 0,
                    "updated_count": 0,
                    "failed_count": 1,
                    "skipped_duplicate_count": 0,
                    "failure_reason": "simulated push failure",
                    "max_retries": 3,
                    "retry_backoff_seconds": 1.0,
                    "timeout_seconds": 30.0,
                    "idempotency_enabled": True,
                    "idempotency_path": None,
                    "results": [],
                },
            )
        return {
            "target": envelope.target,
            "dry_run": dry_run,
            "push_mode": push_mode,
            "attempted_actionable_count": 1,
            "pushed_count": 1,
            "created_count": 1,
            "updated_count": 0,
            "failed_count": 0,
            "skipped_duplicate_count": 0,
            "failure_reason": None,
            "max_retries": 3,
            "retry_backoff_seconds": 1.0,
            "timeout_seconds": 30.0,
            "idempotency_enabled": True,
            "idempotency_path": None,
            "results": [],
        }

    monkeypatch.setattr("eu_ai_act.exporter.ExportPusher.push", _fake_push)

    payload = run_export_batch(
        descriptor_dir=tmp_path,
        target="jira",
        recursive=False,
        push=True,
    )

    assert payload["total_files"] == 2
    assert payload["processed_count"] == 2
    assert payload["success_count"] == 1
    assert payload["failure_count"] == 1
    assert payload["invalid_count"] == 0
    assert call_counter["count"] == 2
    statuses = [item["status"] for item in payload["results"]]
    assert statuses == ["failed", "success"]


def test_reconcile_export_push_records_classifies_exists_missing_and_error(monkeypatch, tmp_path):
    """Reconcile should classify ledger records into exists/missing/check_error statuses."""
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "idempotency_key": "k1",
                        "target": "jira",
                        "system_name": "System A",
                        "descriptor_path": "/tmp/a.yaml",
                        "requirement_id": "Art. 10",
                        "status": "non_compliant",
                        "remote_ref": "EUAI-1",
                        "pushed_at": "2026-03-22T10:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "idempotency_key": "k2",
                        "target": "jira",
                        "system_name": "System B",
                        "descriptor_path": "/tmp/b.yaml",
                        "requirement_id": "Art. 11",
                        "status": "partial",
                        "remote_ref": "EUAI-404",
                        "pushed_at": "2026-03-22T11:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "idempotency_key": "k3",
                        "target": "jira",
                        "system_name": "System C",
                        "descriptor_path": "/tmp/c.yaml",
                        "requirement_id": "Art. 13",
                        "status": "not_assessed",
                        "remote_ref": None,
                        "pushed_at": "2026-03-22T12:00:00+00:00",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/EUAI-1"):
            return httpx.Response(
                status_code=200,
                json={"key": "EUAI-1", "fields": {"labels": ["status-non_compliant"]}},
            )
        if str(request.url).endswith("/EUAI-404"):
            return httpx.Response(status_code=404, text="not found")
        return httpx.Response(status_code=500, text="unexpected path")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    payload = reconcile_export_push_records(
        target="jira",
        idempotency_path=ledger_path,
        max_retries=0,
    )

    assert payload["checked_count"] == 3
    assert payload["exists_count"] == 1
    assert payload["in_sync_count"] == 1
    assert payload["drift_count"] == 0
    assert payload["missing_count"] == 1
    assert payload["error_count"] == 1
    assert payload["repair_planned_count"] == 0
    assert payload["repair_applied_count"] == 0
    assert payload["repair_failed_count"] == 0
    statuses = sorted(item["status"] for item in payload["results"])
    assert statuses == ["check_error", "exists", "missing"]
    exists_entry = next(item for item in payload["results"] if item["status"] == "exists")
    assert exists_entry["drift_status"] == "in_sync"
    assert exists_entry["expected_status"] == "non_compliant"
    assert exists_entry["remote_status"] == "non_compliant"


def test_reconcile_export_push_records_retries_on_5xx_then_exists(monkeypatch, tmp_path):
    """Reconcile read checks should retry transient failures and then succeed."""
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "idempotency_key": "k1",
                "target": "jira",
                "system_name": "System A",
                "descriptor_path": "/tmp/a.yaml",
                "requirement_id": "Art. 10",
                "status": "non_compliant",
                "remote_ref": "EUAI-1",
                "pushed_at": "2026-03-22T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")

    call_counter = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return httpx.Response(status_code=503, text="temporary outage")
        return httpx.Response(
            status_code=200,
            json={"key": "EUAI-1", "fields": {"labels": ["status-non_compliant"]}},
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    payload = reconcile_export_push_records(
        target="jira",
        idempotency_path=ledger_path,
        max_retries=3,
    )

    assert payload["checked_count"] == 1
    assert payload["exists_count"] == 1
    assert payload["in_sync_count"] == 1
    assert payload["drift_count"] == 0
    assert payload["missing_count"] == 0
    assert payload["error_count"] == 0
    assert payload["results"][0]["attempts"] == 2
    assert payload["results"][0]["retries_used"] == 1
    assert call_counter["count"] == 2


def test_reconcile_export_push_records_non_retryable_4xx_is_check_error(monkeypatch, tmp_path):
    """Non-retryable 4xx reconcile responses should fail immediately as check_error."""
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "idempotency_key": "k1",
                "target": "jira",
                "system_name": "System A",
                "descriptor_path": "/tmp/a.yaml",
                "requirement_id": "Art. 10",
                "status": "non_compliant",
                "remote_ref": "EUAI-1",
                "pushed_at": "2026-03-22T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")

    call_counter = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_counter["count"] += 1
        return httpx.Response(status_code=400, text="bad request")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    payload = reconcile_export_push_records(
        target="jira",
        idempotency_path=ledger_path,
        max_retries=5,
    )

    assert payload["checked_count"] == 1
    assert payload["exists_count"] == 0
    assert payload["in_sync_count"] == 0
    assert payload["drift_count"] == 0
    assert payload["missing_count"] == 0
    assert payload["error_count"] == 1
    assert payload["results"][0]["status"] == "check_error"
    assert payload["results"][0]["attempts"] == 1
    assert "HTTP 400" in payload["results"][0]["failure_reason"]
    assert call_counter["count"] == 1


def test_reconcile_repair_plan_for_drift_without_apply_does_not_write(monkeypatch, tmp_path):
    """Repair mode without apply should plan drift fixes and avoid write calls."""
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "idempotency_key": "k1",
                "target": "jira",
                "system_name": "System Drift",
                "descriptor_path": "/tmp/drift.yaml",
                "requirement_id": "Art. 13",
                "status": "partial",
                "remote_ref": "EUAI-77",
                "pushed_at": "2026-03-22T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")

    call_counter = {"get": 0, "put": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["get"] += 1
            return httpx.Response(
                status_code=200,
                json={"key": "EUAI-77", "fields": {"labels": ["status-non_compliant", "keep-me"]}},
            )
        if request.method == "PUT":
            call_counter["put"] += 1
            return httpx.Response(status_code=500, text="write should not happen")
        return httpx.Response(status_code=500, text="unexpected request")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    payload = reconcile_export_push_records(
        target="jira",
        idempotency_path=ledger_path,
        max_retries=0,
        repair_enabled=True,
        apply=False,
    )

    assert payload["checked_count"] == 1
    assert payload["exists_count"] == 1
    assert payload["in_sync_count"] == 0
    assert payload["drift_count"] == 1
    assert payload["repair_planned_count"] == 1
    assert payload["repair_applied_count"] == 0
    assert payload["repair_failed_count"] == 0
    assert call_counter["get"] == 1
    assert call_counter["put"] == 0
    repair_entry = payload["results"][0]
    assert repair_entry["drift_status"] == "status_mismatch"
    assert repair_entry["repair_result"]["status"] == "planned"
    repair_labels = repair_entry["repair_plan"]["payload"]["fields"]["labels"]
    assert "keep-me" in repair_labels
    assert "status-partial" in repair_labels
    assert "status-non_compliant" not in repair_labels


def test_reconcile_repair_apply_servicenow_retries_and_succeeds(monkeypatch, tmp_path):
    """Applying ServiceNow repair should use retry policy and succeed after transient errors."""
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "idempotency_key": "k1",
                "target": "servicenow",
                "system_name": "System Drift",
                "descriptor_path": "/tmp/drift.yaml",
                "requirement_id": "Art. 14",
                "status": "partial",
                "remote_ref": "SYS001",
                "pushed_at": "2026-03-22T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_INSTANCE_URL", "https://example.service-now.com")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_USERNAME", "ops")
    monkeypatch.setenv("EU_AI_ACT_SERVICENOW_PASSWORD", "secret")

    call_counter = {"get": 0, "patch": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            call_counter["get"] += 1
            return httpx.Response(status_code=200, json={"result": {"u_status": "non_compliant"}})
        if request.method == "PATCH":
            call_counter["patch"] += 1
            if call_counter["patch"] == 1:
                return httpx.Response(status_code=503, text="temporary outage")
            return httpx.Response(status_code=200, json={"result": {"sys_id": "SYS001"}})
        return httpx.Response(status_code=500, text="unexpected request")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    payload = reconcile_export_push_records(
        target="servicenow",
        idempotency_path=ledger_path,
        max_retries=3,
        repair_enabled=True,
        apply=True,
    )

    assert payload["checked_count"] == 1
    assert payload["exists_count"] == 1
    assert payload["drift_count"] == 1
    assert payload["repair_planned_count"] == 1
    assert payload["repair_applied_count"] == 1
    assert payload["repair_failed_count"] == 0
    assert call_counter["get"] == 1
    assert call_counter["patch"] == 2
    repair_entry = payload["results"][0]
    assert repair_entry["repair_result"]["status"] == "applied"
    assert repair_entry["repair_result"]["attempts"] == 2
    assert repair_entry["repair_result"]["retries_used"] == 1


def test_reconcile_repair_apply_continues_when_one_record_fails(monkeypatch, tmp_path):
    """Repair apply should continue across records and aggregate failures deterministically."""
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "idempotency_key": "k1",
                        "target": "jira",
                        "system_name": "System A",
                        "descriptor_path": "/tmp/a.yaml",
                        "requirement_id": "Art. 10",
                        "status": "partial",
                        "remote_ref": "EUAI-1",
                        "pushed_at": "2026-03-22T10:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "idempotency_key": "k2",
                        "target": "jira",
                        "system_name": "System B",
                        "descriptor_path": "/tmp/b.yaml",
                        "requirement_id": "Art. 11",
                        "status": "not_assessed",
                        "remote_ref": "EUAI-2",
                        "pushed_at": "2026-03-22T11:00:00+00:00",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and url.endswith("/EUAI-1"):
            return httpx.Response(
                status_code=200,
                json={"key": "EUAI-1", "fields": {"labels": ["status-non_compliant"]}},
            )
        if request.method == "GET" and url.endswith("/EUAI-2"):
            return httpx.Response(
                status_code=200,
                json={"key": "EUAI-2", "fields": {"labels": ["status-non_compliant"]}},
            )
        if request.method == "PUT" and url.endswith("/EUAI-1"):
            return httpx.Response(status_code=204, text="")
        if request.method == "PUT" and url.endswith("/EUAI-2"):
            return httpx.Response(status_code=400, text="bad update")
        return httpx.Response(status_code=500, text="unexpected request")

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)
    monkeypatch.setattr(ExportPusher, "_sleep_before_retry", lambda _self, _attempts: None)

    payload = reconcile_export_push_records(
        target="jira",
        idempotency_path=ledger_path,
        max_retries=0,
        repair_enabled=True,
        apply=True,
    )

    assert payload["checked_count"] == 2
    assert payload["exists_count"] == 2
    assert payload["drift_count"] == 2
    assert payload["repair_planned_count"] == 2
    assert payload["repair_applied_count"] == 1
    assert payload["repair_failed_count"] == 1
    failed = [
        item
        for item in payload["results"]
        if item.get("repair_result", {}).get("status") == "failed"
    ]
    assert len(failed) == 1
    assert "HTTP 400" in failed[0]["repair_result"]["failure_reason"]


def test_list_export_ops_log_records_and_invalid_json(tmp_path):
    """Ops log listing should filter deterministically and fail on malformed JSON lines."""
    ops_path = tmp_path / ".eu_ai_act" / "export_ops_log.jsonl"
    ops_path.parent.mkdir(parents=True, exist_ok=True)
    ops_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "attempt_id": "a1",
                        "generated_at": "2026-03-23T10:00:00+00:00",
                        "target": "jira",
                        "system_name": "System A",
                        "requirement_id": "Art. 10",
                        "result": "failed",
                    }
                ),
                json.dumps(
                    {
                        "attempt_id": "a2",
                        "generated_at": "2026-03-23T11:00:00+00:00",
                        "target": "jira",
                        "system_name": "System B",
                        "requirement_id": "Art. 11",
                        "result": "success",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resolved_path, records = list_export_ops_log_records(
        ops_path=ops_path,
        target="jira",
        result="failed",
        limit=10,
    )
    assert resolved_path == ops_path
    assert len(records) == 1
    assert records[0]["attempt_id"] == "a1"

    ops_path.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON in export ops log"):
        list_export_ops_log_records(ops_path=ops_path)


def test_replay_export_push_failures_dedupes_and_marks_unreplayable(tmp_path):
    """Replay should dedupe failed keys, replay actionable check records, and continue on unreplayable."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    actionable_requirement = next(
        requirement_id
        for requirement_id, finding in report.findings.items()
        if finding.status != ComplianceStatus.COMPLIANT
    )

    ops_path = tmp_path / ".eu_ai_act" / "export_ops_log.jsonl"
    ops_path.parent.mkdir(parents=True, exist_ok=True)
    ops_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "attempt_id": "old-failed",
                        "generated_at": "2026-03-23T09:00:00+00:00",
                        "target": "jira",
                        "push_mode": "create",
                        "source_type": "check",
                        "system_name": descriptor.name,
                        "descriptor_path": str(EXAMPLES_DIR / "medical_diagnosis.yaml"),
                        "event_id": None,
                        "requirement_id": actionable_requirement,
                        "status": "non_compliant",
                        "article": "Art. 10",
                        "idempotency_key": "same-key",
                        "operation": "create",
                        "result": "failed",
                        "http_status": 503,
                        "attempts": 3,
                        "retries_used": 2,
                        "remote_ref": None,
                        "failure_reason": "jira API returned HTTP 503",
                    }
                ),
                json.dumps(
                    {
                        "attempt_id": "new-failed",
                        "generated_at": "2026-03-23T10:00:00+00:00",
                        "target": "jira",
                        "push_mode": "create",
                        "source_type": "check",
                        "system_name": descriptor.name,
                        "descriptor_path": str(EXAMPLES_DIR / "medical_diagnosis.yaml"),
                        "event_id": None,
                        "requirement_id": actionable_requirement,
                        "status": "non_compliant",
                        "article": "Art. 10",
                        "idempotency_key": "same-key",
                        "operation": "create",
                        "result": "failed",
                        "http_status": 503,
                        "attempts": 3,
                        "retries_used": 2,
                        "remote_ref": None,
                        "failure_reason": "jira API returned HTTP 503",
                    }
                ),
                json.dumps(
                    {
                        "attempt_id": "missing-history",
                        "generated_at": "2026-03-23T11:00:00+00:00",
                        "target": "jira",
                        "push_mode": "create",
                        "source_type": "history",
                        "system_name": "History System",
                        "descriptor_path": None,
                        "event_id": "missing-event-id",
                        "requirement_id": actionable_requirement,
                        "status": "partial",
                        "article": "Art. 13",
                        "idempotency_key": "history-key",
                        "operation": "create",
                        "result": "failed",
                        "http_status": 500,
                        "attempts": 1,
                        "retries_used": 0,
                        "remote_ref": None,
                        "failure_reason": "history source failed",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = replay_export_push_failures(
        target="jira",
        ops_path=ops_path,
        limit=10,
        dry_run=True,
    )

    assert payload["selected_count"] == 2
    assert payload["replayed_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["unreplayable_count"] == 1
    replayed = [item for item in payload["results"] if item["status"] == "replayed"]
    assert len(replayed) == 1
    assert replayed[0]["push_result"]["dry_run"] is True


def test_summarize_export_ops_rollup_counts_open_failures(tmp_path):
    """Rollup should aggregate metrics/distributions and compute open failures from latest key state."""
    ops_path = tmp_path / ".eu_ai_act" / "export_ops_log.jsonl"
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ops_path.parent.mkdir(parents=True, exist_ok=True)
    ops_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "attempt_id": "a1",
                        "generated_at": "2026-03-23T09:00:00+00:00",
                        "target": "jira",
                        "push_mode": "create",
                        "operation": "create",
                        "result": "failed",
                        "system_name": "System A",
                        "idempotency_key": "k1",
                        "failure_reason": "HTTP 503",
                    }
                ),
                json.dumps(
                    {
                        "attempt_id": "a2",
                        "generated_at": "2026-03-23T10:00:00+00:00",
                        "target": "jira",
                        "push_mode": "create",
                        "operation": "create",
                        "result": "success",
                        "system_name": "System A",
                        "idempotency_key": "k1",
                        "failure_reason": None,
                    }
                ),
                json.dumps(
                    {
                        "attempt_id": "a3",
                        "generated_at": "2026-03-23T11:00:00+00:00",
                        "target": "jira",
                        "push_mode": "upsert",
                        "operation": "update",
                        "result": "failed",
                        "system_name": "System B",
                        "idempotency_key": "k2",
                        "failure_reason": "HTTP 400",
                    }
                ),
                json.dumps(
                    {
                        "attempt_id": "a4",
                        "generated_at": "2026-03-23T12:00:00+00:00",
                        "target": "jira",
                        "push_mode": "create",
                        "operation": "skip_duplicate",
                        "result": "skipped_duplicate",
                        "system_name": "System C",
                        "idempotency_key": "k3",
                        "failure_reason": None,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ledger_path.write_text(
        json.dumps(
            {
                "idempotency_key": "k1",
                "target": "jira",
                "system_name": "System A",
                "descriptor_path": "/tmp/a.yaml",
                "requirement_id": "Art. 10",
                "status": "non_compliant",
                "remote_ref": "EUAI-1",
                "pushed_at": "2026-03-23T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = summarize_export_ops_rollup(
        ops_path=ops_path,
        idempotency_path=ledger_path,
    )

    metrics = payload["metrics"]
    assert metrics["total_attempts"] == 4
    assert metrics["success_count"] == 1
    assert metrics["failed_count"] == 2
    assert metrics["skipped_duplicate_count"] == 1
    assert metrics["open_failures_count"] == 1
    assert payload["distributions"]["by_operation"]["create"] == 2
    assert payload["distributions"]["by_operation"]["update"] == 1
    assert payload["distributions"]["by_operation"]["skip_duplicate"] == 1
    assert "System B" in payload["systems_with_failures"]


def test_push_success_with_ops_log_write_error_keeps_success(monkeypatch):
    """Ops log write failures should not fail push and should surface warning in push result."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    for requirement_id in list(report.findings.keys()):
        report.findings[requirement_id].status = ComplianceStatus.NON_COMPLIANT
    envelope = ExportGenerator().from_check(report=report, target="jira")

    monkeypatch.setenv("EU_AI_ACT_JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("EU_AI_ACT_JIRA_EMAIL", "ops@example.com")
    monkeypatch.setenv("EU_AI_ACT_JIRA_API_TOKEN", "secret")
    monkeypatch.setenv("EU_AI_ACT_JIRA_PROJECT_KEY", "EUAI")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=201, json={"key": "EUAI-100"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def _fake_client(*args, **kwargs):
        return original_client(transport=transport)

    monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

    def _raise_ops_write_error(_self, _record):
        raise OSError("disk full")

    monkeypatch.setattr(ExportPusher, "_append_ops_log_record", _raise_ops_write_error)

    result = ExportPusher(idempotency_enabled=False).push(envelope)
    assert result["pushed_count"] == len(envelope.adapter_payload["issues"])
    assert isinstance(result.get("ops_log_warning"), str)
    assert "export ops log" in result["ops_log_warning"]
