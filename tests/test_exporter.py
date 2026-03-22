"""Tests for payload-first external export generation."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from eu_ai_act.checker import ComplianceChecker, ComplianceStatus
from eu_ai_act.exporter import ExportGenerator, ExportPushError, ExportPusher
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
        ExportPusher().push(envelope)


def test_push_dry_run_for_jira_requires_no_credentials():
    """Dry-run should not require environment credentials and should return deterministic summary."""
    descriptor = load_system_descriptor_from_file(EXAMPLES_DIR / "medical_diagnosis.yaml")
    report = ComplianceChecker().check(descriptor)
    envelope = ExportGenerator().from_check(report=report, target="jira")

    result = ExportPusher().push(envelope, dry_run=True)

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
        ExportPusher().push(envelope, dry_run=False)


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

    result = ExportPusher().push(envelope)
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

    result = ExportPusher(max_retries=3).push(envelope)
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

    result = ExportPusher(max_retries=3).push(envelope)
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

    result = ExportPusher(max_retries=3).push(envelope)
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
        ExportPusher(max_retries=2).push(envelope)

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
        ExportPusher(max_retries=5).push(envelope)

    push_result = exc_info.value.push_result
    assert push_result["failed_count"] == 1
    assert push_result["results"][0]["attempts"] == 1
    assert "HTTP 400" in push_result["failure_reason"]
    assert call_counter["count"] == 1
