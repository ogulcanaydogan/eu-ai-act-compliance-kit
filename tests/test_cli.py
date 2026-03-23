"""CLI smoke tests for stabilized output contracts."""

import json
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

import eu_ai_act.cli as cli_module
from eu_ai_act.cli import main
from eu_ai_act.exporter import ExportPushError
from eu_ai_act.reporter import ReportGenerator

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


class TestCLI:
    """End-to-end checks for key CLI commands."""

    @pytest.fixture(autouse=True)
    def _isolate_history_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EU_AI_ACT_HISTORY_PATH", str(tmp_path / "history.jsonl"))

    def test_cli_version_option_returns_version_string(self):
        """`--version` should succeed without runtime metadata inference errors."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "version" in result.output.lower()
        assert "0.1.11" in result.output
        assert "runtimeerror" not in result.output.lower()

    def test_articles_uses_normalized_mapping(self):
        """`articles --tier minimal` should use shared article mapping."""
        runner = CliRunner()
        result = runner.invoke(main, ["articles", "--tier", "minimal"])

        assert result.exit_code == 0
        assert "Art. 69" in result.output

    def test_check_json_contains_summary_and_findings(self):
        """`check --json` should preserve old fields and include new detail fields."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(main, ["check", str(system_yaml), "--json"])

        assert result.exit_code == 0
        json_start = result.output.find("{")
        payload = json.loads(result.output[json_start:])

        assert payload["system_name"] == "Medical Imaging Diagnosis AI"
        assert payload["risk_tier"] == "high_risk"
        assert payload["status"] == "compliance_check_completed"
        assert "message" in payload
        assert "articles_applicable" in payload
        assert "summary" in payload
        assert "findings" in payload
        assert "transparency" in payload
        assert "gpai_summary" in payload
        assert "audit_trail" in payload
        assert "generated_at" in payload

        summary = payload["summary"]
        assert summary["total_requirements"] == 6
        assert "compliant_count" in summary
        assert "non_compliant_count" in summary
        assert "partial_count" in summary
        assert "not_assessed_count" in summary
        assert "compliance_percentage" in summary

    def test_markdown_outputs_use_real_timestamps(self):
        """Checklist/report markdown outputs should not contain literal shell placeholders."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "spam_filter.yaml"

        report_result = runner.invoke(main, ["report", str(system_yaml), "--format", "md"])
        checklist_result = runner.invoke(main, ["checklist", str(system_yaml), "--format", "md"])

        assert report_result.exit_code == 0
        assert checklist_result.exit_code == 0
        assert "$(date)" not in report_result.output
        assert "$(date)" not in checklist_result.output
        assert "Report Generated:" in report_result.output
        assert "Generated:" in checklist_result.output
        assert "coming in phase" not in checklist_result.output.lower()

    def test_checklist_json_contains_legacy_and_new_fields(self):
        """Checklist JSON should keep legacy keys and expose expanded summary/items."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(main, ["checklist", str(system_yaml), "--format", "json"])

        assert result.exit_code == 0
        json_start = result.output.find("{")
        payload = json.loads(result.output[json_start:])

        # Backward-compatible fields
        assert payload["system"] == "Medical Imaging Diagnosis AI"
        assert payload["risk_tier"] == "high_risk"
        assert payload["checklist"] == "generated"

        # Expanded fields
        assert "generated_at" in payload
        assert "summary" in payload
        assert "items" in payload
        assert "compliant_count" in payload
        assert payload["summary"]["total_requirements"] == 6
        assert payload["summary"]["actionable_count"] == 1

    def test_medical_checklist_markdown_contains_action_item(self):
        """Medical example should show at least one actionable task in checklist markdown."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(main, ["checklist", str(system_yaml), "--format", "md"])

        assert result.exit_code == 0
        assert "**Actionable Tasks:** 1" in result.output
        assert "Art. 43" in result.output

    def test_transparency_command_json(self):
        """`transparency --json` should return structured findings."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        result = runner.invoke(main, ["transparency", str(system_yaml), "--json"])

        assert result.exit_code == 0
        json_start = result.output.find("{")
        payload = json.loads(result.output[json_start:])
        assert payload["system_name"] == "Customer Support Chatbot"
        assert isinstance(payload["findings"], list)
        assert payload["finding_count"] >= 1

    def test_gpai_command_json(self):
        """`gpai --json` should return systemic-risk and findings payload."""
        runner = CliRunner()
        model_yaml = EXAMPLES_DIR / "gpai_model.yaml"
        result = runner.invoke(main, ["gpai", str(model_yaml), "--json"])

        assert result.exit_code == 0
        json_start = result.output.find("{")
        payload = json.loads(result.output[json_start:])
        assert payload["model_name"] == "Aurora Foundation Model XL"
        assert payload["systemic_risk_flag"] is True
        assert isinstance(payload["findings"], list)
        assert payload["compliance_gaps"]

    def test_report_includes_transparency_and_gpai_sections(self):
        """`report` outputs should include transparency and GPAI sections."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        json_result = runner.invoke(main, ["report", str(system_yaml), "--format", "json"])
        md_result = runner.invoke(main, ["report", str(system_yaml), "--format", "md"])
        html_result = runner.invoke(main, ["report", str(system_yaml), "--format", "html"])

        assert json_result.exit_code == 0
        assert md_result.exit_code == 0
        assert html_result.exit_code == 0

        json_payload = json.loads(json_result.output[json_result.output.find("{") :])
        assert "transparency_findings" in json_payload
        assert "gpai_assessment" in json_payload
        assert "compliance_findings" in json_payload
        assert "audit_trail" in json_payload
        assert "recommended_actions" in json_payload
        assert "recommended_action_count" in json_payload
        assert json_payload["recommended_action_count"] == len(json_payload["recommended_actions"])

        assert "## Transparency Findings" in md_result.output
        assert "## GPAI Assessment" in md_result.output
        assert "## Recommended Actions" in md_result.output
        assert "## Audit Trail" in md_result.output
        assert "Transparency Findings" in html_result.output
        assert "GPAI Assessment" in html_result.output
        assert "Recommended Actions" in html_result.output
        assert "Audit Trail" in html_result.output

    def test_history_commands_list_show_diff_json(self):
        """`history` commands should return structured list/show/diff payloads."""
        runner = CliRunner()

        spam_yaml = EXAMPLES_DIR / "spam_filter.yaml"
        social_yaml = EXAMPLES_DIR / "social_scoring.yaml"

        first = runner.invoke(main, ["check", str(spam_yaml), "--json"])
        second = runner.invoke(main, ["check", str(social_yaml), "--json"])

        assert first.exit_code == 0
        assert second.exit_code == 0

        list_result = runner.invoke(
            main,
            ["history", "list", "--event-type", "check", "--limit", "2", "--json"],
        )
        assert list_result.exit_code == 0
        list_payload = json.loads(list_result.output[list_result.output.find("{") :])
        assert list_payload["count"] == 2
        assert len(list_payload["events"]) == 2

        newer_id = list_payload["events"][0]["event_id"]
        older_id = list_payload["events"][1]["event_id"]

        show_result = runner.invoke(main, ["history", "show", newer_id, "--json"])
        assert show_result.exit_code == 0
        show_payload = json.loads(show_result.output[show_result.output.find("{") :])
        assert show_payload["event_id"] == newer_id
        assert show_payload["event_type"] == "check"

        diff_result = runner.invoke(main, ["history", "diff", older_id, newer_id, "--json"])
        assert diff_result.exit_code == 0
        diff_payload = json.loads(diff_result.output[diff_result.output.find("{") :])
        assert "risk_tier_change" in diff_payload
        assert "summary_changes" in diff_payload
        assert "finding_status_changes" in diff_payload
        assert "added_findings" in diff_payload
        assert "removed_findings" in diff_payload
        assert diff_payload["risk_tier_change"]["changed"] is True

    def test_history_write_failure_warns_without_failing_check_or_report(self, monkeypatch):
        """History write failures should not fail check/report commands."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"

        def _raise_history_error(*_args, **_kwargs):
            raise OSError("disk is read-only")

        monkeypatch.setattr(cli_module, "append_event", _raise_history_error)

        check_result = runner.invoke(main, ["check", str(system_yaml), "--json"])
        report_result = runner.invoke(main, ["report", str(system_yaml), "--format", "json"])

        assert check_result.exit_code == 0
        assert report_result.exit_code == 0
        check_stream = check_result.output + getattr(check_result, "stderr", "")
        report_stream = report_result.output + getattr(report_result, "stderr", "")
        assert "Warning: failed to write history event:" in check_stream
        assert "Warning: failed to write history event:" in report_stream

    def test_dashboard_build_writes_default_outputs_and_contract(self):
        """`dashboard build` should write default JSON/HTML files in current working directory."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            systems_dir = Path("systems")
            systems_dir.mkdir()
            (systems_dir / "spam_filter.yaml").write_text(
                (EXAMPLES_DIR / "spam_filter.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = runner.invoke(main, ["dashboard", "build", str(systems_dir)])
            assert result.exit_code == 0
            assert Path("dashboard.json").exists()
            assert Path("dashboard.html").exists()

            payload = json.loads(Path("dashboard.json").read_text(encoding="utf-8"))
            for key in [
                "generated_at",
                "scan_root",
                "scanned_file_count",
                "valid_system_count",
                "invalid_descriptor_count",
                "risk_tier_distribution",
                "average_compliance_percentage",
                "systems",
                "errors",
            ]:
                assert key in payload
            assert payload["valid_system_count"] == 1
            assert payload["invalid_descriptor_count"] == 0

    def test_dashboard_build_output_dir_override(self, tmp_path):
        """`dashboard build --output-dir` should write artifacts to the provided path."""
        runner = CliRunner()
        systems_dir = tmp_path / "systems"
        systems_dir.mkdir()
        (systems_dir / "medical.yaml").write_text(
            (EXAMPLES_DIR / "medical_diagnosis.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        output_dir = tmp_path / "dashboard-out"
        result = runner.invoke(
            main,
            ["dashboard", "build", str(systems_dir), "--output-dir", str(output_dir)],
        )

        assert result.exit_code == 0
        assert (output_dir / "dashboard.json").exists()
        assert (output_dir / "dashboard.html").exists()

    def test_report_pdf_requires_output_path(self):
        """PDF format should fail fast when output path is not provided."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        result = runner.invoke(main, ["report", str(system_yaml), "--format", "pdf"])

        assert result.exit_code != 0
        assert "--output/-o is required when --format pdf" in result.output

    def test_report_pdf_writes_binary_file_with_output(self, monkeypatch, tmp_path):
        """PDF report should write binary bytes to the provided output path."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        output_path = tmp_path / "report.pdf"

        def _fake_pdf(*args, **kwargs):
            return b"%PDF-1.7\nmock-pdf"

        monkeypatch.setattr(ReportGenerator, "generate_pdf_report", _fake_pdf)

        result = runner.invoke(
            main,
            ["report", str(system_yaml), "--format", "pdf", "-o", str(output_path)],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        assert output_path.read_bytes().startswith(b"%PDF-1.7")

    def test_export_check_json_contract(self):
        """`export check --json` should emit canonical contract plus adapter payload."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(
            main,
            ["export", "check", str(system_yaml), "--target", "jira", "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        for key in [
            "schema_version",
            "generated_at",
            "source_type",
            "target",
            "system_name",
            "risk_tier",
            "summary",
            "items",
            "adapter_payload",
        ]:
            assert key in payload
        assert payload["source_type"] == "check"
        assert payload["target"] == "jira"
        assert payload["descriptor_path"].endswith("examples/medical_diagnosis.yaml")
        assert payload["adapter_payload"]["format"] == "jira/issues/v1"

    def test_export_history_json_contract(self):
        """`export history --json` should include history metadata and adapter payload."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        check_result = runner.invoke(main, ["check", str(system_yaml), "--json"])
        assert check_result.exit_code == 0

        list_result = runner.invoke(main, ["history", "list", "--event-type", "check", "--json"])
        assert list_result.exit_code == 0
        list_payload = json.loads(list_result.output[list_result.output.find("{") :])
        event_id = list_payload["events"][0]["event_id"]

        export_result = runner.invoke(
            main,
            ["export", "history", event_id, "--target", "servicenow", "--json"],
        )
        assert export_result.exit_code == 0
        payload = json.loads(export_result.output[export_result.output.find("{") :])
        assert payload["source_type"] == "history"
        assert payload["event_id"] == event_id
        assert "history_generated_at" in payload
        assert payload["adapter_payload"]["format"] == "servicenow/records/v1"

    def test_export_check_output_file(self, tmp_path):
        """`export check -o` should write JSON artifact to file."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "spam_filter.yaml"
        output_path = tmp_path / "export.json"

        result = runner.invoke(
            main,
            [
                "export",
                "check",
                str(system_yaml),
                "--target",
                "generic",
                "--output",
                str(output_path),
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["target"] == "generic"
        assert payload["adapter_payload"]["format"] == "generic/v1"

    def test_export_history_invalid_event_fails(self):
        """`export history` should fail deterministically for unknown event ids."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["export", "history", "missing-event-id", "--target", "generic", "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "Error loading history event" in output

    def test_export_batch_json_contract_success(self, tmp_path):
        """`export batch --json` should process all valid descriptors and return aggregate metrics."""
        runner = CliRunner()
        descriptor_dir = tmp_path / "descriptors"
        descriptor_dir.mkdir(parents=True, exist_ok=True)
        (descriptor_dir / "a.yaml").write_text(
            (EXAMPLES_DIR / "spam_filter.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (descriptor_dir / "b.yaml").write_text(
            (EXAMPLES_DIR / "chatbot.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            ["export", "batch", str(descriptor_dir), "--target", "generic", "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["scan_root"] == str(descriptor_dir.resolve())
        assert payload["target"] == "generic"
        assert payload["total_files"] == 2
        assert payload["processed_count"] == 2
        assert payload["success_count"] == 2
        assert payload["failure_count"] == 0
        assert payload["invalid_count"] == 0
        assert len(payload["results"]) == 2
        assert all(item["status"] == "success" for item in payload["results"])

    def test_export_batch_mixed_valid_invalid_returns_nonzero(self, tmp_path):
        """Batch export should continue on invalid descriptors and return non-zero summary result."""
        runner = CliRunner()
        descriptor_dir = tmp_path / "descriptors"
        descriptor_dir.mkdir(parents=True, exist_ok=True)
        (descriptor_dir / "a_valid.yaml").write_text(
            (EXAMPLES_DIR / "spam_filter.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (descriptor_dir / "b_invalid.yaml").write_text(
            "name: broken\nuse_cases: [\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            ["export", "batch", str(descriptor_dir), "--target", "generic", "--json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["total_files"] == 2
        assert payload["processed_count"] == 1
        assert payload["success_count"] == 1
        assert payload["failure_count"] == 0
        assert payload["invalid_count"] == 1
        statuses = [item["status"] for item in payload["results"]]
        assert statuses == ["success", "invalid_descriptor"]

    def test_export_batch_push_failure_continues_and_returns_nonzero(self, monkeypatch, tmp_path):
        """Batch push should continue after push failures and surface non-zero aggregate status."""
        runner = CliRunner()
        descriptor_dir = tmp_path / "descriptors"
        descriptor_dir.mkdir(parents=True, exist_ok=True)
        (descriptor_dir / "a.yaml").write_text(
            (EXAMPLES_DIR / "medical_diagnosis.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (descriptor_dir / "b.yaml").write_text(
            (EXAMPLES_DIR / "chatbot.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        call_counter = {"count": 0}

        def _fake_push(_self, _envelope, dry_run=False, push_mode="create"):
            call_counter["count"] += 1
            if call_counter["count"] == 1:
                raise ExportPushError(
                    "simulated push failure",
                    push_result={
                        "target": "jira",
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
                "target": "jira",
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

        monkeypatch.setattr(cli_module.ExportPusher, "push", _fake_push)

        result = runner.invoke(
            main,
            [
                "export",
                "batch",
                str(descriptor_dir),
                "--target",
                "jira",
                "--push",
                "--json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["processed_count"] == 2
        assert payload["success_count"] == 1
        assert payload["failure_count"] == 1
        assert payload["invalid_count"] == 0
        assert call_counter["count"] == 2

    def test_export_batch_push_generic_target_fails(self, tmp_path):
        """Batch command should reject live push for generic target."""
        runner = CliRunner()
        descriptor_dir = tmp_path / "descriptors"
        descriptor_dir.mkdir(parents=True, exist_ok=True)
        (descriptor_dir / "a.yaml").write_text(
            (EXAMPLES_DIR / "spam_filter.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "export",
                "batch",
                str(descriptor_dir),
                "--target",
                "generic",
                "--push",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "Live push is not supported for target 'generic'" in output

    def test_export_reconcile_json_contract_and_nonzero_on_missing(self, monkeypatch, tmp_path):
        """Reconcile should return deterministic contract and non-zero exit on missing records."""
        runner = CliRunner()
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
                            "requirement_id": "Art. 11",
                            "status": "partial",
                            "remote_ref": "EUAI-404",
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

        def handler(request):
            if str(request.url).endswith("/EUAI-1"):
                return httpx.Response(
                    status_code=200,
                    json={"key": "EUAI-1", "fields": {"labels": ["status-non_compliant"]}},
                )
            return httpx.Response(status_code=404, text="not found")

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.exporter.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "export",
                "reconcile",
                "--target",
                "jira",
                "--idempotency-path",
                str(ledger_path),
                "--json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["target"] == "jira"
        assert payload["checked_count"] == 2
        assert payload["exists_count"] == 1
        assert payload["in_sync_count"] == 1
        assert payload["drift_count"] == 0
        assert payload["missing_count"] == 1
        assert payload["error_count"] == 0
        assert payload["repair_planned_count"] == 0
        assert payload["repair_applied_count"] == 0
        assert payload["repair_failed_count"] == 0
        assert payload["repair_enabled"] is False
        assert payload["apply"] is False

    def test_export_reconcile_output_file(self, monkeypatch, tmp_path):
        """Reconcile should support output file mode and preserve exit-zero success behavior."""
        runner = CliRunner()
        output_path = tmp_path / "reconcile.json"

        monkeypatch.setattr(
            cli_module,
            "reconcile_export_push_records",
            lambda **_kwargs: {
                "generated_at": "2026-03-22T00:00:00+00:00",
                "target": "jira",
                "ledger_path": "/tmp/ledger.jsonl",
                "filters": {"system_name": None, "requirement_id": None, "limit": 50},
                "repair_enabled": False,
                "apply": False,
                "checked_count": 1,
                "exists_count": 1,
                "in_sync_count": 1,
                "drift_count": 0,
                "missing_count": 0,
                "error_count": 0,
                "repair_planned_count": 0,
                "repair_applied_count": 0,
                "repair_failed_count": 0,
                "results": [{"record_index": 1, "status": "exists"}],
            },
        )

        result = runner.invoke(
            main,
            [
                "export",
                "reconcile",
                "--target",
                "jira",
                "--output",
                str(output_path),
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["exists_count"] == 1
        assert payload["drift_count"] == 0
        assert payload["missing_count"] == 0
        assert payload["error_count"] == 0

    def test_export_reconcile_apply_without_repair_fails(self):
        """`--apply` should be rejected unless `--repair` is explicitly enabled."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["export", "reconcile", "--target", "jira", "--apply", "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "--apply can only be used together with --repair" in output

    def test_export_reconcile_json_contract_and_nonzero_on_drift(self, monkeypatch):
        """Drift findings should produce non-zero exit even without missing/error records."""
        runner = CliRunner()

        monkeypatch.setattr(
            cli_module,
            "reconcile_export_push_records",
            lambda **_kwargs: {
                "generated_at": "2026-03-23T00:00:00+00:00",
                "target": "jira",
                "ledger_path": "/tmp/ledger.jsonl",
                "filters": {"system_name": None, "requirement_id": None, "limit": 50},
                "repair_enabled": True,
                "apply": False,
                "checked_count": 1,
                "exists_count": 1,
                "in_sync_count": 0,
                "drift_count": 1,
                "missing_count": 0,
                "error_count": 0,
                "repair_planned_count": 1,
                "repair_applied_count": 0,
                "repair_failed_count": 0,
                "results": [
                    {
                        "record_index": 1,
                        "status": "exists",
                        "drift_status": "status_mismatch",
                    }
                ],
            },
        )

        result = runner.invoke(
            main,
            ["export", "reconcile", "--target", "jira", "--repair", "--json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["drift_count"] == 1
        assert payload["missing_count"] == 0
        assert payload["error_count"] == 0

    def test_export_reconcile_forwards_repair_and_apply_flags(self, monkeypatch):
        """Reconcile command should pass repair/apply flags to exporter runtime."""
        runner = CliRunner()
        captured: dict[str, object] = {}

        def _fake_reconcile(**kwargs):
            captured.update(kwargs)
            return {
                "generated_at": "2026-03-23T00:00:00+00:00",
                "target": "jira",
                "ledger_path": "/tmp/ledger.jsonl",
                "filters": {"system_name": None, "requirement_id": None, "limit": 50},
                "repair_enabled": kwargs.get("repair_enabled", False),
                "apply": kwargs.get("apply", False),
                "checked_count": 1,
                "exists_count": 1,
                "in_sync_count": 1,
                "drift_count": 0,
                "missing_count": 0,
                "error_count": 0,
                "repair_planned_count": 0,
                "repair_applied_count": 0,
                "repair_failed_count": 0,
                "results": [{"record_index": 1, "status": "exists"}],
            }

        monkeypatch.setattr(cli_module, "reconcile_export_push_records", _fake_reconcile)

        result = runner.invoke(
            main,
            [
                "export",
                "reconcile",
                "--target",
                "jira",
                "--repair",
                "--apply",
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert captured["repair_enabled"] is True
        assert captured["apply"] is True

    def test_export_reconcile_invalid_limit_fails(self):
        """Reconcile should validate non-positive limit values."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["export", "reconcile", "--target", "jira", "--limit", "0", "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "--limit must be >= 1" in output

    def test_export_ledger_list_json_contract(self, tmp_path):
        """`export ledger list --json` should return deterministic filtered records payload."""
        runner = CliRunner()
        ledger_path = tmp_path / ".eu_ai_act" / "export_push_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "idempotency_key": "k1",
                            "target": "jira",
                            "system_name": "Medical Imaging Diagnosis AI",
                            "requirement_id": "Art. 10",
                            "status": "non_compliant",
                            "pushed_at": "2026-03-22T10:00:00+00:00",
                        }
                    ),
                    json.dumps(
                        {
                            "idempotency_key": "k2",
                            "target": "servicenow",
                            "system_name": "Customer Support Chatbot",
                            "requirement_id": "Art. 50",
                            "status": "partial",
                            "pushed_at": "2026-03-22T11:00:00+00:00",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "export",
                "ledger",
                "list",
                "--idempotency-path",
                str(ledger_path),
                "--target",
                "jira",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["path"] == str(ledger_path)
        assert payload["count"] == 1
        assert payload["filters"]["target"] == "jira"
        assert payload["records"][0]["idempotency_key"] == "k1"

    def test_export_ledger_stats_json_contract(self, tmp_path):
        """`export ledger stats --json` should return aggregate counters and distributions."""
        runner = CliRunner()
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
                            "requirement_id": "Art. 10",
                            "status": "non_compliant",
                            "pushed_at": "2026-03-22T10:00:00+00:00",
                        }
                    ),
                    json.dumps(
                        {
                            "idempotency_key": "k2",
                            "target": "jira",
                            "system_name": "System A",
                            "requirement_id": "Art. 11",
                            "status": "partial",
                            "pushed_at": "2026-03-22T11:00:00+00:00",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            ["export", "ledger", "stats", "--idempotency-path", str(ledger_path), "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["path"] == str(ledger_path)
        assert payload["total_records"] == 2
        assert payload["unique_idempotency_key_count"] == 2
        assert payload["target_distribution"]["jira"] == 2
        assert payload["status_distribution"]["non_compliant"] == 1
        assert payload["status_distribution"]["partial"] == 1

    def test_export_ledger_list_invalid_limit_fails(self):
        """`export ledger list` should validate non-positive limit values."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["export", "ledger", "list", "--limit", "0", "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "--limit must be >= 1" in output

    def test_export_check_dry_run_without_push_emits_simulated_push_result(self):
        """`--dry-run` without `--push` should keep payload-only behavior and include simulated summary."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        result = runner.invoke(
            main,
            ["export", "check", str(system_yaml), "--target", "jira", "--dry-run", "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert "push_result" in payload
        assert payload["push_result"]["dry_run"] is True
        assert payload["push_result"]["push_mode"] == "create"
        assert payload["push_result"]["pushed_count"] == 0
        assert payload["push_result"]["created_count"] == 0
        assert payload["push_result"]["updated_count"] == 0
        assert payload["push_result"]["failed_count"] == 0
        assert payload["push_result"]["skipped_duplicate_count"] == 0
        assert payload["push_result"]["failure_reason"] is None
        assert payload["push_result"]["max_retries"] == 3
        assert payload["push_result"]["retry_backoff_seconds"] == 1.0
        assert payload["push_result"]["timeout_seconds"] == 30.0
        assert payload["push_result"]["idempotency_enabled"] is True
        assert payload["push_result"]["idempotency_path"].endswith(
            ".eu_ai_act/export_push_ledger.jsonl"
        )
        assert "no remote api call" in payload["push_result"]["message"].lower()

    def test_export_check_push_mode_without_push_fails(self):
        """`--push-mode` should be rejected unless `--push` is explicitly enabled."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(
            main,
            [
                "export",
                "check",
                str(system_yaml),
                "--target",
                "jira",
                "--push-mode",
                "upsert",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "--push-mode can only be used together with --push" in output

    def test_export_history_push_mode_without_push_fails(self):
        """History export should enforce the same push-mode validation contract."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        check_result = runner.invoke(main, ["check", str(system_yaml), "--json"])
        assert check_result.exit_code == 0

        list_result = runner.invoke(main, ["history", "list", "--event-type", "check", "--json"])
        assert list_result.exit_code == 0
        event_id = json.loads(list_result.output[list_result.output.find("{") :])["events"][0][
            "event_id"
        ]

        result = runner.invoke(
            main,
            [
                "export",
                "history",
                event_id,
                "--target",
                "servicenow",
                "--push-mode",
                "upsert",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "--push-mode can only be used together with --push" in output

    def test_export_push_mode_is_forwarded_to_pusher(self, monkeypatch):
        """`--push-mode upsert` should be passed to ExportPusher and reflected in push_result."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        captured: dict[str, object] = {}

        def _fake_push(_self, _envelope, dry_run=False, push_mode="create"):
            captured["push_mode"] = push_mode
            return {
                "target": "jira",
                "dry_run": dry_run,
                "push_mode": push_mode,
                "attempted_actionable_count": 1,
                "pushed_count": 0,
                "created_count": 0,
                "updated_count": 1,
                "failed_count": 0,
                "skipped_duplicate_count": 0,
                "failure_reason": None,
                "max_retries": 3,
                "retry_backoff_seconds": 1.0,
                "timeout_seconds": 30.0,
                "idempotency_enabled": True,
                "idempotency_path": None,
                "results": [{"status": "success", "operation": "updated", "issue_key": "EUAI-99"}],
            }

        monkeypatch.setattr(cli_module.ExportPusher, "push", _fake_push)

        result = runner.invoke(
            main,
            [
                "export",
                "check",
                str(system_yaml),
                "--target",
                "jira",
                "--push",
                "--push-mode",
                "upsert",
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert captured["push_mode"] == "upsert"
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["push_result"]["push_mode"] == "upsert"
        assert payload["push_result"]["updated_count"] == 1

    def test_export_push_mode_create_is_forwarded_to_pusher(self, monkeypatch):
        """Explicit `--push-mode create` should be forwarded and reported deterministically."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        captured: dict[str, object] = {}

        def _fake_push(_self, _envelope, dry_run=False, push_mode="create"):
            captured["push_mode"] = push_mode
            return {
                "target": "jira",
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
                "results": [{"status": "success", "operation": "created", "issue_key": "EUAI-1"}],
            }

        monkeypatch.setattr(cli_module.ExportPusher, "push", _fake_push)

        result = runner.invoke(
            main,
            [
                "export",
                "check",
                str(system_yaml),
                "--target",
                "jira",
                "--push",
                "--push-mode",
                "create",
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert captured["push_mode"] == "create"
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["push_result"]["push_mode"] == "create"
        assert payload["push_result"]["created_count"] == 1
        assert payload["push_result"]["updated_count"] == 0

    def test_export_check_dry_run_with_push_mode_upsert_reports_push_mode(self):
        """Dry-run should keep no-network behavior and expose selected push-mode."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        result = runner.invoke(
            main,
            [
                "export",
                "check",
                str(system_yaml),
                "--target",
                "jira",
                "--push",
                "--dry-run",
                "--push-mode",
                "upsert",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["push_result"]["dry_run"] is True
        assert payload["push_result"]["push_mode"] == "upsert"
        assert payload["push_result"]["pushed_count"] == 0
        assert payload["push_result"]["created_count"] == 0
        assert payload["push_result"]["updated_count"] == 0

    def test_export_push_generic_target_fails(self):
        """`--push` should fail deterministically for unsupported generic target."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "spam_filter.yaml"

        result = runner.invoke(
            main,
            ["export", "check", str(system_yaml), "--target", "generic", "--push", "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "Live push is not supported for target 'generic'" in output

    def test_export_push_calls_pusher_and_includes_push_result(self, monkeypatch):
        """`--push` should include live push result in output payload when pusher succeeds."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        def _fake_push(_self, _envelope, dry_run=False, push_mode="create"):
            return {
                "target": "jira",
                "dry_run": dry_run,
                "push_mode": push_mode,
                "attempted_actionable_count": 2,
                "pushed_count": 2,
                "created_count": 2,
                "updated_count": 0,
                "failed_count": 0,
                "results": [{"status": "success", "issue_key": "EUAI-1"}],
            }

        monkeypatch.setattr(cli_module.ExportPusher, "push", _fake_push)

        result = runner.invoke(
            main,
            ["export", "check", str(system_yaml), "--target", "jira", "--push", "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["push_result"]["target"] == "jira"
        assert payload["push_result"]["push_mode"] == "create"
        assert payload["push_result"]["pushed_count"] == 2
        assert payload["push_result"]["created_count"] == 2
        assert payload["push_result"]["updated_count"] == 0
        assert payload["push_result"]["failed_count"] == 0

    def test_export_push_uses_custom_idempotency_path(self, monkeypatch, tmp_path):
        """`--idempotency-path` should be wired to ExportPusher for live push mode."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        custom_ledger = tmp_path / "custom-ledger.jsonl"
        captured: dict[str, object] = {}

        def _fake_push(self, _envelope, dry_run=False, push_mode="create"):
            captured["idempotency_enabled"] = self.idempotency_enabled
            captured["idempotency_path"] = self.idempotency_path
            return {
                "target": "jira",
                "dry_run": dry_run,
                "push_mode": push_mode,
                "attempted_actionable_count": 2,
                "pushed_count": 1,
                "created_count": 1,
                "updated_count": 0,
                "failed_count": 0,
                "skipped_duplicate_count": 1,
                "failure_reason": None,
                "max_retries": 3,
                "retry_backoff_seconds": 1.0,
                "timeout_seconds": 30.0,
                "idempotency_enabled": True,
                "idempotency_path": str(custom_ledger),
                "results": [
                    {"status": "success", "issue_key": "EUAI-1"},
                    {"status": "skipped_duplicate", "item_index": 2},
                ],
            }

        monkeypatch.setattr(cli_module.ExportPusher, "push", _fake_push)

        result = runner.invoke(
            main,
            [
                "export",
                "check",
                str(system_yaml),
                "--target",
                "jira",
                "--push",
                "--idempotency-path",
                str(custom_ledger),
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert captured["idempotency_enabled"] is True
        assert str(captured["idempotency_path"]) == str(custom_ledger)
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["push_result"]["skipped_duplicate_count"] == 1
        assert payload["push_result"]["idempotency_path"] == str(custom_ledger)

    def test_export_push_disable_idempotency_flag(self, monkeypatch):
        """`--disable-idempotency` should disable duplicate-skip ledger behavior."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        captured: dict[str, object] = {}

        def _fake_push(self, _envelope, dry_run=False, push_mode="create"):
            captured["idempotency_enabled"] = self.idempotency_enabled
            captured["idempotency_path"] = self.idempotency_path
            return {
                "target": "jira",
                "dry_run": dry_run,
                "push_mode": push_mode,
                "attempted_actionable_count": 2,
                "pushed_count": 2,
                "created_count": 2,
                "updated_count": 0,
                "failed_count": 0,
                "skipped_duplicate_count": 0,
                "failure_reason": None,
                "max_retries": 3,
                "retry_backoff_seconds": 1.0,
                "timeout_seconds": 30.0,
                "idempotency_enabled": False,
                "idempotency_path": None,
                "results": [],
            }

        monkeypatch.setattr(cli_module.ExportPusher, "push", _fake_push)

        result = runner.invoke(
            main,
            [
                "export",
                "check",
                str(system_yaml),
                "--target",
                "jira",
                "--push",
                "--disable-idempotency",
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert captured["idempotency_enabled"] is False
        assert captured["idempotency_path"] is None
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["push_result"]["idempotency_enabled"] is False
        assert payload["push_result"]["idempotency_path"] is None

    def test_export_history_push_uses_custom_idempotency_path(self, monkeypatch, tmp_path):
        """History export should pass custom idempotency path through to pusher."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        check_result = runner.invoke(main, ["check", str(system_yaml), "--json"])
        assert check_result.exit_code == 0
        list_result = runner.invoke(main, ["history", "list", "--event-type", "check", "--json"])
        assert list_result.exit_code == 0
        event_id = json.loads(list_result.output[list_result.output.find("{") :])["events"][0][
            "event_id"
        ]
        custom_ledger = tmp_path / "history-ledger.jsonl"
        captured: dict[str, object] = {}

        def _fake_push(self, _envelope, dry_run=False, push_mode="create"):
            captured["idempotency_enabled"] = self.idempotency_enabled
            captured["idempotency_path"] = self.idempotency_path
            return {
                "target": "servicenow",
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
                "idempotency_path": str(custom_ledger),
                "results": [{"status": "success", "sys_id": "SYS-1"}],
            }

        monkeypatch.setattr(cli_module.ExportPusher, "push", _fake_push)

        result = runner.invoke(
            main,
            [
                "export",
                "history",
                event_id,
                "--target",
                "servicenow",
                "--push",
                "--idempotency-path",
                str(custom_ledger),
                "--json",
            ],
        )

        assert result.exit_code == 0
        assert captured["idempotency_enabled"] is True
        assert str(captured["idempotency_path"]) == str(custom_ledger)

    def test_export_push_failure_returns_nonzero_with_clear_error(self, monkeypatch):
        """`--push` should return non-zero with deterministic error message on push failure."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        def _raise_push_failure(_self, _envelope, dry_run=False, push_mode="create"):
            raise RuntimeError("Jira push failed with HTTP transport error: timeout")

        monkeypatch.setattr(cli_module.ExportPusher, "push", _raise_push_failure)

        result = runner.invoke(
            main,
            ["export", "check", str(system_yaml), "--target", "jira", "--push", "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "Error pushing export payload" in output
        assert "HTTP transport error" in output
        assert "timeout" in output

    @pytest.mark.parametrize(
        ("flag", "value", "expected_error"),
        [
            ("--max-retries", "-1", "--max-retries must be >= 0"),
            ("--retry-backoff-seconds", "0", "--retry-backoff-seconds must be > 0"),
            ("--timeout-seconds", "0", "--timeout-seconds must be > 0"),
        ],
    )
    def test_export_check_invalid_push_tuning_flags_fail(
        self, flag: str, value: str, expected_error: str
    ):
        """Invalid retry/backoff/timeout values should fail with deterministic CLI errors."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        result = runner.invoke(
            main,
            ["export", "check", str(system_yaml), "--target", "jira", flag, value, "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert expected_error in output

    def test_export_history_invalid_timeout_flag_fails(self):
        """History export should validate timeout tuning flags before push execution."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "chatbot.yaml"
        check_result = runner.invoke(main, ["check", str(system_yaml), "--json"])
        assert check_result.exit_code == 0

        list_result = runner.invoke(main, ["history", "list", "--event-type", "check", "--json"])
        assert list_result.exit_code == 0
        event_id = json.loads(list_result.output[list_result.output.find("{") :])["events"][0][
            "event_id"
        ]

        result = runner.invoke(
            main,
            [
                "export",
                "history",
                event_id,
                "--target",
                "jira",
                "--timeout-seconds",
                "-1",
                "--json",
            ],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "--timeout-seconds must be > 0" in output

    def test_export_push_retry_exhaustion_error_is_reported(self, monkeypatch):
        """Push retry exhaustion should surface fail-fast reason via deterministic error output."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        def _raise_push_failure(_self, _envelope, dry_run=False, push_mode="create"):
            raise ExportPushError(
                "Jira push aborted on item 1: jira API returned HTTP 503: temporary outage",
                push_result={
                    "target": "jira",
                    "dry_run": dry_run,
                    "push_mode": push_mode,
                    "attempted_actionable_count": 1,
                    "pushed_count": 0,
                    "created_count": 0,
                    "updated_count": 0,
                    "failed_count": 1,
                    "failure_reason": "jira API returned HTTP 503: temporary outage",
                    "max_retries": 3,
                    "retry_backoff_seconds": 1.0,
                    "timeout_seconds": 30.0,
                    "results": [],
                },
            )

        monkeypatch.setattr(cli_module.ExportPusher, "push", _raise_push_failure)

        result = runner.invoke(
            main,
            ["export", "check", str(system_yaml), "--target", "jira", "--push", "--json"],
        )

        assert result.exit_code != 0
        output = result.output + getattr(result, "stderr", "")
        assert "Jira push aborted on item 1" in output
        assert "HTTP 503" in output
