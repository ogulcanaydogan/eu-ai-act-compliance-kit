"""Tests for multi-system dashboard generation."""

import json
from pathlib import Path

from eu_ai_act.dashboard import DashboardGenerator
from eu_ai_act.history import append_event, build_event

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


def _copy_example(source_name: str, destination: Path) -> None:
    destination.write_text(
        (EXAMPLES_DIR / source_name).read_text(encoding="utf-8"), encoding="utf-8"
    )


class TestDashboardGenerator:
    def test_build_mixed_directory_with_invalid_descriptor(self, tmp_path):
        scan_root = tmp_path / "scan"
        scan_root.mkdir()
        _copy_example("medical_diagnosis.yaml", scan_root / "medical.yaml")
        _copy_example("spam_filter.yaml", scan_root / "spam.yaml")
        (scan_root / "broken.yaml").write_text("name: broken\nuse_cases: [\n", encoding="utf-8")

        payload = DashboardGenerator().build(scan_root)

        assert payload["scanned_file_count"] == 3
        assert payload["valid_system_count"] == 2
        assert payload["invalid_descriptor_count"] == 1
        assert len(payload["systems"]) == 2
        assert len(payload["errors"]) == 1
        assert payload["risk_tier_distribution"]["high_risk"] == 1
        assert payload["risk_tier_distribution"]["minimal"] == 1
        assert payload["risk_tier_distribution"]["limited"] == 0
        assert payload["risk_tier_distribution"]["unacceptable"] == 0
        assert "average_security_coverage_percentage" in payload
        assert "security_control_status_distribution" in payload

        first_system = payload["systems"][0]
        for key in [
            "system_name",
            "descriptor_path",
            "risk_tier",
            "compliance_percentage",
            "total_requirements",
            "non_compliant_count",
            "partial_count",
            "not_assessed_count",
            "security_summary",
            "generated_at",
        ]:
            assert key in first_system
        assert first_system["security_summary"]["framework"] == "owasp-llm-top-10"
        assert first_system["security_summary"]["total_controls"] == 10

    def test_aggregate_metrics_average_matches_system_rows(self, tmp_path):
        scan_root = tmp_path / "scan"
        scan_root.mkdir()
        _copy_example("medical_diagnosis.yaml", scan_root / "medical.yaml")
        _copy_example("spam_filter.yaml", scan_root / "spam.yaml")

        payload = DashboardGenerator().build(scan_root)
        expected_average = round(
            sum(system["compliance_percentage"] for system in payload["systems"])
            / len(payload["systems"]),
            2,
        )
        expected_security_average = round(
            sum(system["security_summary"]["coverage_percentage"] for system in payload["systems"])
            / len(payload["systems"]),
            2,
        )
        assert payload["average_compliance_percentage"] == expected_average
        assert payload["average_security_coverage_percentage"] == expected_security_average

    def test_no_valid_systems_returns_empty_systems_and_errors(self, tmp_path):
        scan_root = tmp_path / "scan"
        scan_root.mkdir()
        (scan_root / "invalid_one.yaml").write_text(
            "name: broken\nuse_cases: [\n", encoding="utf-8"
        )
        (scan_root / "invalid_two.yml").write_text(
            "description: missing required fields\n", encoding="utf-8"
        )

        payload = DashboardGenerator().build(scan_root)

        assert payload["valid_system_count"] == 0
        assert payload["invalid_descriptor_count"] == 2
        assert payload["systems"] == []
        assert len(payload["errors"]) == 2

    def test_include_history_populates_history_trends(self, tmp_path):
        scan_root = tmp_path / "scan"
        scan_root.mkdir()
        _copy_example("spam_filter.yaml", scan_root / "spam.yaml")

        history_path = tmp_path / "history.jsonl"
        event_old = build_event(
            event_type="check",
            system_name="Email Spam Filter",
            descriptor_path=str(scan_root / "spam.yaml"),
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
            generated_at="2026-03-19T08:00:00+00:00",
        )
        event_new = build_event(
            event_type="report",
            system_name="Email Spam Filter",
            descriptor_path=str(scan_root / "spam.yaml"),
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
            report_format="json",
            generated_at="2026-03-19T08:05:00+00:00",
        )
        append_event(event_old, history_path=history_path)
        append_event(event_new, history_path=history_path)

        payload = DashboardGenerator().build(
            scan_root,
            include_history=True,
            history_path=history_path,
        )

        assert "history_trends" in payload
        assert len(payload["history_trends"]) == 1
        trend = payload["history_trends"][0]
        assert trend["system_name"] == "Email Spam Filter"
        assert trend["event_count"] == 2
        assert trend["latest_generated_at"] == "2026-03-19T08:05:00+00:00"
        assert trend["compliance_percentage_delta"] == 0.0

    def test_render_html_contains_expected_sections(self, tmp_path):
        scan_root = tmp_path / "scan"
        scan_root.mkdir()
        _copy_example("spam_filter.yaml", scan_root / "spam.yaml")

        generator = DashboardGenerator()
        payload = generator.build(scan_root)
        html_output = generator.render_html(payload)

        assert "EU AI Act Multi-System Dashboard" in html_output
        assert "Risk Tier Distribution" in html_output
        assert "Security Mapping Overview" in html_output
        assert "Invalid Descriptors" in html_output
        assert "Email Spam Filter" in html_output

    def test_to_json_returns_parseable_payload(self, tmp_path):
        scan_root = tmp_path / "scan"
        scan_root.mkdir()
        _copy_example("spam_filter.yaml", scan_root / "spam.yaml")
        payload = DashboardGenerator().build(scan_root)

        raw = DashboardGenerator.to_json(payload)
        parsed = json.loads(raw)
        assert parsed["scan_root"] == str(scan_root.resolve())
