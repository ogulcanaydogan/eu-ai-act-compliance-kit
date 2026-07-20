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
    security_summary: dict | None = None,
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
        "security_summary": security_summary,
    }
    return HistoryEvent.from_dict(payload)


def _valid_payload(**overrides: object) -> dict:
    """Return a fresh, valid ``from_dict`` payload, with optional field overrides."""
    payload: dict = {
        "event_id": "evt-valid",
        "event_type": "check",
        "generated_at": "2026-03-19T08:00:00+00:00",
        "system_name": "System A",
        "descriptor_path": "examples/a.yaml",
        "risk_tier": "minimal",
        "summary": {
            "total_requirements": 1,
            "compliant_count": 1,
            "non_compliant_count": 0,
            "partial_count": 0,
            "not_assessed_count": 0,
            "compliance_percentage": 100.0,
        },
        "finding_statuses": {"Art. 5": "compliant"},
        "report_format": None,
        "security_summary": None,
    }
    payload.update(overrides)
    return payload


def _valid_security_summary(**overrides: object) -> dict:
    summary: dict = {
        "framework": "owasp-llm-top-10",
        "total_controls": 10,
        "compliant_count": 1,
        "non_compliant_count": 1,
        "partial_count": 0,
        "not_assessed_count": 0,
        "coverage_percentage": 50.0,
    }
    summary.update(overrides)
    return summary


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
                security_summary={
                    "framework": "owasp-llm-top-10",
                    "total_controls": 10,
                    "compliant_count": 2,
                    "non_compliant_count": 4,
                    "partial_count": 1,
                    "not_assessed_count": 3,
                    "coverage_percentage": 70.0,
                },
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
                security_summary={
                    "framework": "owasp-llm-top-10",
                    "total_controls": 10,
                    "compliant_count": 4,
                    "non_compliant_count": 3,
                    "partial_count": 1,
                    "not_assessed_count": 2,
                    "coverage_percentage": 80.0,
                },
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
        assert diff["security_summary_change"]["available"] is True
        assert diff["security_summary_change"]["coverage_percentage"]["delta"] == 10.0
        assert diff["security_summary_change"]["non_compliant_count"]["delta"] == -1
        assert diff["security_summary_change"]["partial_count"]["delta"] == 0
        assert diff["security_summary_change"]["not_assessed_count"]["delta"] == -1

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
            security_summary={
                "framework": "owasp-llm-top-10",
                "total_controls": 10,
                "compliant_count": 8,
                "non_compliant_count": 0,
                "partial_count": 2,
                "not_assessed_count": 0,
                "coverage_percentage": 100.0,
            },
        )
        append_event(event, history_path=history_path)

        raw_lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        payload = json.loads(raw_lines[0])
        assert payload["event_id"] == "evt-json"
        assert payload["event_type"] == "report"
        assert payload["report_format"] == "html"
        assert payload["security_summary"]["framework"] == "owasp-llm-top-10"
        assert payload["security_summary"]["total_controls"] == 10


class TestHistoryEventValidation:
    def test_payload_must_be_object(self):
        with pytest.raises(ValueError, match="payload must be an object"):
            HistoryEvent.from_dict(["not", "a", "dict"])

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValueError, match="event_type must be"):
            HistoryEvent.from_dict(_valid_payload(event_type="audit"))

    @pytest.mark.parametrize(
        "field",
        ["event_id", "system_name", "descriptor_path", "risk_tier"],
    )
    def test_required_string_fields_reject_empty(self, field):
        with pytest.raises(ValueError, match=f"{field} must be a non-empty string"):
            HistoryEvent.from_dict(_valid_payload(**{field: ""}))

    def test_generated_at_must_be_non_empty_string(self):
        with pytest.raises(ValueError, match="generated_at must be"):
            HistoryEvent.from_dict(_valid_payload(generated_at=""))

    def test_report_format_rejects_empty_string(self):
        with pytest.raises(ValueError, match="report_format must be"):
            HistoryEvent.from_dict(_valid_payload(report_format=""))


class TestSummaryNormalization:
    def test_summary_must_be_object(self):
        with pytest.raises(ValueError, match="Summary must be an object"):
            HistoryEvent.from_dict(_valid_payload(summary=["not", "a", "dict"]))

    def test_summary_missing_field_rejected(self):
        broken = _valid_payload()["summary"]
        broken.pop("partial_count")
        with pytest.raises(ValueError, match="missing required field 'partial_count'"):
            HistoryEvent.from_dict(_valid_payload(summary=broken))

    def test_integer_field_rejects_bool(self):
        payload = _valid_payload()
        payload["summary"]["compliant_count"] = True
        with pytest.raises(ValueError, match="must be an integer"):
            HistoryEvent.from_dict(payload)

    def test_integer_field_rejects_non_int(self):
        payload = _valid_payload()
        payload["summary"]["compliant_count"] = "3"
        with pytest.raises(ValueError, match="must be an integer"):
            HistoryEvent.from_dict(payload)

    def test_float_field_rejects_non_numeric(self):
        payload = _valid_payload()
        payload["summary"]["compliance_percentage"] = "80"
        with pytest.raises(ValueError, match="must be numeric"):
            HistoryEvent.from_dict(payload)


class TestFindingStatusNormalization:
    def test_finding_statuses_must_be_object(self):
        with pytest.raises(ValueError, match="Finding statuses must be an object"):
            HistoryEvent.from_dict(_valid_payload(finding_statuses=["Art. 5"]))

    def test_finding_status_key_must_be_non_empty(self):
        with pytest.raises(ValueError, match="keys must be non-empty strings"):
            HistoryEvent.from_dict(_valid_payload(finding_statuses={"": "compliant"}))

    def test_finding_status_value_must_be_non_empty(self):
        with pytest.raises(ValueError, match="values must be non-empty strings"):
            HistoryEvent.from_dict(_valid_payload(finding_statuses={"Art. 5": ""}))


class TestSecuritySummaryNormalization:
    def test_security_summary_must_be_object(self):
        with pytest.raises(ValueError, match="security_summary must be an object"):
            HistoryEvent.from_dict(_valid_payload(security_summary=["not", "a", "dict"]))

    def test_framework_must_be_null_or_non_empty(self):
        payload = _valid_payload(security_summary=_valid_security_summary(framework="   "))
        with pytest.raises(ValueError, match="framework must be null or a non-empty string"):
            HistoryEvent.from_dict(payload)

    def test_security_summary_missing_field_rejected(self):
        broken = _valid_security_summary()
        broken.pop("coverage_percentage")
        with pytest.raises(ValueError, match="missing required field 'coverage_percentage'"):
            HistoryEvent.from_dict(_valid_payload(security_summary=broken))


class TestHistoryPathAndLoading:
    def test_relative_history_path_resolved_against_cwd(self, tmp_path):
        resolved = resolve_history_path("audit/history.jsonl", cwd=tmp_path)
        assert resolved == (tmp_path / "audit" / "history.jsonl").resolve()

    def test_blank_lines_are_skipped(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        append_event(
            HistoryEvent.from_dict(_valid_payload(event_id="evt-1")),
            history_path=history_path,
        )
        content = history_path.read_text(encoding="utf-8")
        history_path.write_text("\n" + content + "   \n", encoding="utf-8")

        events = list_events(history_path=history_path)
        assert [event.event_id for event in events] == ["evt-1"]

    def test_malformed_json_line_raises_value_error(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        history_path.write_text("{not valid json\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON in history file at line 1"):
            list_events(history_path=history_path)

    def test_list_events_rejects_non_positive_limit(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            list_events(history_path=history_path, limit=0)


class TestDiffMissingEvents:
    def test_diff_without_security_summaries_yields_null_deltas(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        append_event(
            HistoryEvent.from_dict(_valid_payload(event_id="older", risk_tier="minimal")),
            history_path=history_path,
        )
        append_event(
            HistoryEvent.from_dict(_valid_payload(event_id="newer", risk_tier="high_risk")),
            history_path=history_path,
        )

        diff = diff_events("older", "newer", history_path=history_path)

        assert diff["security_summary_change"]["available"] is False
        for field in (
            "coverage_percentage",
            "non_compliant_count",
            "partial_count",
            "not_assessed_count",
        ):
            change = diff["security_summary_change"][field]
            assert change["from"] is None
            assert change["to"] is None
            assert change["delta"] is None

    def test_diff_missing_older_event_raises(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        append_event(
            HistoryEvent.from_dict(_valid_payload(event_id="only")),
            history_path=history_path,
        )
        with pytest.raises(KeyError, match="only-missing"):
            diff_events("only-missing", "only", history_path=history_path)

    def test_diff_missing_newer_event_raises(self, tmp_path):
        history_path = tmp_path / "history.jsonl"
        append_event(
            HistoryEvent.from_dict(_valid_payload(event_id="only")),
            history_path=history_path,
        )
        with pytest.raises(KeyError, match="newer-missing"):
            diff_events("only", "newer-missing", history_path=history_path)
