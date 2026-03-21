"""Tests for payload-first external export generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.exporter import ExportGenerator
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
