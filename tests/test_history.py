"""Tests for audit history storage and diff utilities."""

import json

import pytest

from eu_ai_act.history import (
    HistoryEvent,
    append_event,
    diff_events,
    get_event,
    list_events,
    resolve_history_path,
)


def _make_event(
    *,
    event_id: str,
    event_type: str,
    generated_at: str,
    system_name: str,
    descriptor_path: str,
    risk_tier: str,
    summary: dict,
    finding_statuses: dict,
    report_format: str | None = None,
) -> HistoryEvent:
    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "generated_at": generated_at,
        "system_name": system_name,
        "descriptor_path": descriptor_path,
        "risk_tier": risk_tier,
        "summary": summary,
        "finding_statuses": finding_statuses,
        "report_format": report_format,
    }
    return HistoryEvent.from_dict(payload)


class TestHistoryStorage:
    def test_append_and_list_with_filters(self, tmp_path):
        history_path = tmp_path / "history.jsonl"

        events = [
            _make_event(
                event_id="evt-1",
                event_type="check",
                generated_at="2026-03-19T08:00:00+00:00",
                system_name="System A",
                descriptor_path="examples/a.yaml",
                risk_tier="minimal",
                summary={
                    "total_requirements": 0,
                    "compliant_count": 0,
                    "non_compliant_count": 0,
                    "partial_count": 0,
                    "not_assessed_count": 0,
                    "compliance_percentage": 0.0,
                },
                finding_statuses={},
            ),
            _make_event(
                event_id="evt-2",
                event_type="report",
                generated_at="2026-03-19T08:01:00+00:00",
                system_name="System A",
                descriptor_path="examples/a.yaml",
                risk_tier="high_risk",
                summary={
                    "total_requirements": 6,
                    "compliant_count": 4,
                    "non_compliant_count": 1,
                    "partial_count": 1,
                    "not_assessed_count": 0,
                    "compliance_percentage": 75.0,
                },
                finding_statuses={"Art. 10": "partial"},
                report_format="json",
            ),
            _make_event(
                event_id="evt-3",
                event_type="check",
                generated_at="2026-03-19T08:02:00+00:00",
                system_name="System B",
                descriptor_path="examples/b.yaml",
                risk_tier="unacceptable",
                summary={
                    "total_requirements": 1,
                    "compliant_count": 0,
                    "non_compliant_count": 1,
                    "partial_count": 0,
                    "not_assessed_count": 0,
                    "compliance_percentage": 0.0,
                },
                finding_statuses={"Art. 5": "non_compliant"},
            ),
        ]
        for event in events:
            append_event(event, history_path=history_path)

        all_events = list_events(history_path=history_path)
        assert [event.event_id for event in all_events] == ["evt-3", "evt-2", "evt-1"]

        system_events = list_events(history_path=history_path, system="System A")
        assert [event.event_id for event in system_events] == ["evt-2", "evt-1"]

        report_events = list_events(history_path=history_path, event_type="report")
        assert [event.event_id for event in report_events] == ["evt-2"]

        limited_events = list_events(history_path=history_path, limit=2)
        assert [event.event_id for event in limited_events] == ["evt-3", "evt-2"]

    def test_get_event_not_found_raises(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        append_event(
            _make_event(
                event_id="evt-1",
                event_type="check",
                generated_at="2026-03-19T08:00:00+00:00",
                system_name="System A",
                descriptor_path="examples/a.yaml",
                risk_tier="minimal",
                summary={
                    "total_requirements": 0,
                    "compliant_count": 0,
                    "non_compliant_count": 0,
                    "partial_count": 0,
                    "not_assessed_count": 0,
                    "compliance_percentage": 0.0,
                },
                finding_statuses={},
            ),
            history_path=history_path,
        )

        with pytest.raises(KeyError):
            get_event("does-not-exist", history_path=history_path)

    def test_diff_events_reports_tier_summary_and_finding_changes(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        append_event(
            _make_event(
                event_id="older",
                event_type="check",
                generated_at="2026-03-19T08:00:00+00:00",
                system_name="System A",
                descriptor_path="examples/a.yaml",
                risk_tier="limited",
                summary={
                    "total_requirements": 2,
                    "compliant_count": 0,
                    "non_compliant_count": 1,
                    "partial_count": 0,
                    "not_assessed_count": 1,
                    "compliance_percentage": 25.0,
                },
                finding_statuses={"Art. 10": "partial", "Art. 50": "not_assessed"},
            ),
            history_path=history_path,
        )
        append_event(
            _make_event(
                event_id="newer",
                event_type="check",
                generated_at="2026-03-19T08:02:00+00:00",
                system_name="System A",
                descriptor_path="examples/a.yaml",
                risk_tier="high_risk",
                summary={
                    "total_requirements": 3,
                    "compliant_count": 1,
                    "non_compliant_count": 1,
                    "partial_count": 1,
                    "not_assessed_count": 0,
                    "compliance_percentage": 50.0,
                },
                finding_statuses={"Art. 10": "compliant", "Art. 43": "partial"},
            ),
            history_path=history_path,
        )

        diff = diff_events("older", "newer", history_path=history_path)

        assert diff["risk_tier_change"]["from"] == "limited"
        assert diff["risk_tier_change"]["to"] == "high_risk"
        assert diff["risk_tier_change"]["changed"] is True

        assert diff["summary_changes"]["total_requirements"]["delta"] == 1
        assert diff["summary_changes"]["compliance_percentage"]["delta"] == 25.0

        assert diff["finding_status_changes"] == [
            {"requirement_id": "Art. 10", "from": "partial", "to": "compliant"}
        ]
        assert diff["added_findings"] == [{"requirement_id": "Art. 43", "status": "partial"}]
        assert diff["removed_findings"] == [{"requirement_id": "Art. 50", "status": "not_assessed"}]

    def test_invalid_jsonl_raises_clear_error(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        history_path.write_text(
            '{"event_id":"ok","event_type":"check"}\nnot-json\n', encoding="utf-8"
        )

        with pytest.raises(ValueError):
            list_events(history_path=history_path)

    def test_default_history_path_resolution(self, tmp_path):
        project_root = tmp_path / "project"
        nested = project_root / "src" / "subdir"
        nested.mkdir(parents=True)
        (project_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

        resolved = resolve_history_path(cwd=nested)
        assert resolved == project_root / ".eu_ai_act" / "history.jsonl"

        no_project = tmp_path / "no-project"
        no_project.mkdir()
        fallback = resolve_history_path(cwd=no_project)
        assert fallback == no_project / ".eu_ai_act" / "history.jsonl"

    def test_json_roundtrip_payload_shape(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        event = _make_event(
            event_id="evt-json",
            event_type="report",
            generated_at="2026-03-19T10:00:00+00:00",
            system_name="System C",
            descriptor_path="examples/c.yaml",
            risk_tier="high_risk",
            summary={
                "total_requirements": 6,
                "compliant_count": 5,
                "non_compliant_count": 0,
                "partial_count": 1,
                "not_assessed_count": 0,
                "compliance_percentage": 91.67,
            },
            finding_statuses={"Art. 43": "partial"},
            report_format="html",
        )
        append_event(event, history_path=history_path)

        raw_lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        payload = json.loads(raw_lines[0])
        assert payload["event_id"] == "evt-json"
        assert payload["event_type"] == "report"
        assert payload["report_format"] == "html"
