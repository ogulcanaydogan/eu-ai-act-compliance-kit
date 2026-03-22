"""Tests for export push ledger query and stats helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eu_ai_act.exporter import list_export_push_ledger_records, summarize_export_push_ledger


def _write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def test_list_export_push_ledger_records_filters_and_limit(tmp_path):
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    _write_records(
        ledger_path,
        [
            {
                "idempotency_key": "k1",
                "target": "jira",
                "system_name": "System A",
                "requirement_id": "Art. 10",
                "status": "non_compliant",
                "pushed_at": "2026-03-22T10:00:00+00:00",
            },
            {
                "idempotency_key": "k2",
                "target": "servicenow",
                "system_name": "System A",
                "requirement_id": "Art. 11",
                "status": "partial",
                "pushed_at": "2026-03-22T11:00:00+00:00",
            },
            {
                "idempotency_key": "k3",
                "target": "jira",
                "system_name": "System B",
                "requirement_id": "Art. 10",
                "status": "non_compliant",
                "pushed_at": "2026-03-22T12:00:00+00:00",
            },
        ],
    )

    resolved_path, records = list_export_push_ledger_records(
        idempotency_path=ledger_path,
        target="jira",
        requirement_id="Art. 10",
        limit=1,
    )

    assert resolved_path == ledger_path
    assert len(records) == 1
    assert records[0]["idempotency_key"] == "k3"
    assert records[0]["target"] == "jira"
    assert records[0]["requirement_id"] == "Art. 10"


def test_summarize_export_push_ledger_returns_distributions(tmp_path):
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    _write_records(
        ledger_path,
        [
            {
                "idempotency_key": "k1",
                "target": "jira",
                "system_name": "System A",
                "requirement_id": "Art. 10",
                "status": "non_compliant",
                "pushed_at": "2026-03-22T10:00:00+00:00",
            },
            {
                "idempotency_key": "k2",
                "target": "jira",
                "system_name": "System A",
                "requirement_id": "Art. 11",
                "status": "partial",
                "pushed_at": "2026-03-22T11:00:00+00:00",
            },
            {
                "idempotency_key": "k3",
                "target": "servicenow",
                "system_name": "System B",
                "requirement_id": "Art. 50",
                "status": "not_assessed",
                "pushed_at": "2026-03-22T12:00:00+00:00",
            },
        ],
    )

    summary = summarize_export_push_ledger(idempotency_path=ledger_path)

    assert summary["path"] == str(ledger_path)
    assert summary["total_records"] == 3
    assert summary["unique_idempotency_key_count"] == 3
    assert summary["target_distribution"] == {"jira": 2, "servicenow": 1}
    assert summary["status_distribution"]["non_compliant"] == 1
    assert summary["status_distribution"]["partial"] == 1
    assert summary["status_distribution"]["not_assessed"] == 1
    assert summary["first_pushed_at"] == "2026-03-22T10:00:00+00:00"
    assert summary["last_pushed_at"] == "2026-03-22T12:00:00+00:00"


def test_list_export_push_ledger_records_invalid_json_raises(tmp_path):
    ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text('{"idempotency_key":"k1"}\n{"broken_json":', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON in export push ledger"):
        list_export_push_ledger_records(idempotency_path=ledger_path)
