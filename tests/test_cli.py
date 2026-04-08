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
        assert "0.1.35" in result.output
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
        assert "security_summary" in payload
        assert "security_gate" in payload
        assert "audit_trail" in payload
        assert "generated_at" in payload

        summary = payload["summary"]
        assert summary["total_requirements"] == 6
        assert "compliant_count" in summary
        assert "non_compliant_count" in summary
        assert "partial_count" in summary
        assert "not_assessed_count" in summary
        assert "compliance_percentage" in summary

        security_summary = payload["security_summary"]
        assert security_summary["framework"] == "owasp-llm-top-10"
        assert security_summary["total_controls"] == 10
        assert "coverage_percentage" in security_summary

        security_gate = payload["security_gate"]
        assert security_gate["mode"] == "observe"
        assert security_gate["profile"] == "balanced"
        assert security_gate["effective_profile"] == "balanced"
        assert security_gate["failed"] is False
        assert security_gate["reason"] == "observe_mode_no_blocking"
        assert "partial_count" in security_gate
        assert "not_assessed_count" in security_gate

    def test_check_security_gate_enforce_returns_nonzero_for_non_compliant_controls(self):
        """`check --security-gate enforce` should fail when security non-compliant controls exist."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "public_benefits_triage.yaml"
        result = runner.invoke(
            main,
            [
                "check",
                str(system_yaml),
                "--json",
                "--security-gate",
                "enforce",
                "--security-gate-profile",
                "balanced",
            ],
        )

        assert result.exit_code != 0
        json_start = result.output.find("{")
        payload = json.loads(result.output[json_start:])
        assert payload["security_gate"]["mode"] == "enforce"
        assert payload["security_gate"]["profile"] == "balanced"
        assert payload["security_gate"]["failed"] is True
        assert payload["security_gate"]["non_compliant_count"] > 0

    def test_check_security_gate_profile_tier_aware_override(self):
        """Lenient profile should become balanced for high-risk systems in enforce mode."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "public_benefits_triage.yaml"
        result = runner.invoke(
            main,
            [
                "check",
                str(system_yaml),
                "--json",
                "--security-gate",
                "enforce",
                "--security-gate-profile",
                "lenient",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        gate = payload["security_gate"]
        assert gate["profile"] == "lenient"
        assert gate["effective_profile"] == "balanced"
        assert gate["failed"] is True

    def test_check_rejects_invalid_security_gate_mode(self):
        """`check --security-gate` should validate allowed values."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(
            main,
            ["check", str(system_yaml), "--security-gate", "invalid-mode"],
        )

        assert result.exit_code != 0
        assert "Invalid value for '--security-gate'" in result.output

    def test_check_rejects_invalid_security_gate_profile(self):
        """`check --security-gate-profile` should validate allowed values."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(
            main,
            ["check", str(system_yaml), "--security-gate-profile", "invalid-profile"],
        )

        assert result.exit_code != 0
        assert "Invalid value for '--security-gate-profile'" in result.output

    def test_security_map_json_contract_and_output_file(self):
        """`security-map --json` should return OWASP payload and support file output."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        with runner.isolated_filesystem():
            output_path = Path("security_map.json")
            result = runner.invoke(
                main,
                [
                    "security-map",
                    str(system_yaml),
                    "--json",
                    "--output",
                    str(output_path),
                ],
            )

            assert result.exit_code == 0
            assert output_path.exists()
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        assert payload["system_name"] == "Medical Imaging Diagnosis AI"
        assert payload["framework"] == "owasp-llm-top-10"
        assert payload["risk_tier"] == "high_risk"
        assert "generated_at" in payload
        assert "summary" in payload
        assert isinstance(payload["controls"], list)
        assert len(payload["controls"]) == 10

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
        assert "security_mapping" in json_payload
        assert "compliance_findings" in json_payload
        assert "audit_trail" in json_payload
        assert "recommended_actions" in json_payload
        assert "recommended_action_count" in json_payload
        assert json_payload["recommended_action_count"] == len(json_payload["recommended_actions"])

        assert "## Transparency Findings" in md_result.output
        assert "## GPAI Assessment" in md_result.output
        assert "## Security Mapping (OWASP LLM Top 10)" in md_result.output
        assert "## Recommended Actions" in md_result.output
        assert "## Audit Trail" in md_result.output
        assert "Transparency Findings" in html_result.output
        assert "GPAI Assessment" in html_result.output
        assert "Security Mapping (OWASP LLM Top 10)" in html_result.output
        assert "Recommended Actions" in html_result.output
        assert "Audit Trail" in html_result.output

    def test_handoff_generates_expected_artifact_pack(self):
        """`handoff` should generate deterministic GA artifact set and success manifest."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "success"
            assert payload["system_name"] == "Medical Imaging Diagnosis AI"
            assert payload["risk_tier"] == "high_risk"
            assert "compliance_summary" in payload
            assert "security_summary" in payload
            assert "collaboration_summary" in payload

            expected_files = [
                "validate.json",
                "classify.json",
                "check.json",
                "security_map.json",
                "checklist.json",
                "checklist.md",
                "report.html",
                "collaboration_summary.json",
                "handoff_manifest.json",
            ]
            for name in expected_files:
                assert (output_dir / name).exists()

            manifest_payload = json.loads((output_dir / "handoff_manifest.json").read_text())
            assert manifest_payload["status"] == "success"
            assert "artifacts" in manifest_payload

    def test_handoff_governance_generates_artifact_and_manifest_fields(self):
        """`handoff --governance` should emit governance artifact and additive manifest fields."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--governance",
                    "--governance-mode",
                    "observe",
                    "--json",
                ],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "success"
            assert payload["governance_summary"]["mode"] == "observe"
            assert isinstance(payload["governance_failed"], bool)
            assert isinstance(payload["governance_reason_codes"], list)
            assert (output_dir / "governance_gate.json").exists()

            governance_payload = json.loads((output_dir / "governance_gate.json").read_text())
            assert governance_payload["mode"] == "observe"
            assert isinstance(governance_payload["failed"], bool)
            assert governance_payload["export_ops_gate"] is None
            assert governance_payload["evaluated_gates"] == ["security_gate", "collaboration_gate"]

    def test_handoff_governance_enforce_returns_nonzero_on_gate_failure(self):
        """`handoff --governance-mode enforce` should fail when governance decision fails."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "public_benefits_triage.yaml"

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--governance",
                    "--governance-mode",
                    "enforce",
                    "--json",
                ],
            )

            assert result.exit_code != 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "success"
            assert payload["governance_failed"] is True
            assert payload["governance_reason_codes"]
            assert (
                "security:security_balanced_threshold_breached"
                in payload["governance_reason_codes"]
            )
            assert (output_dir / "governance_gate.json").exists()

    def test_handoff_governance_enforce_succeeds_for_non_actionable_descriptor(self):
        """Enforce mode should not fail on missing collaboration data when run has no actionable findings."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "spam_filter.yaml"

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--governance",
                    "--governance-mode",
                    "enforce",
                    "--governance-policy",
                    str(REPO_ROOT / "config" / "governance_handoff_policy.yaml"),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "success"
            assert payload["governance_failed"] is False
            assert payload["governance_reason_codes"] == []
            governance_payload = json.loads((output_dir / "governance_gate.json").read_text())
            assert governance_payload["failed"] is False

    def test_handoff_rejects_export_target_without_governance(self):
        """`handoff --export-target` should require governance mode."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        result = runner.invoke(
            main,
            [
                "handoff",
                str(system_yaml),
                "--export-target",
                "jira",
            ],
        )

        assert result.exit_code != 0
        assert "--export-target requires --governance" in result.output

    def test_handoff_rejects_governance_policy_without_governance(self):
        """`handoff --governance-policy` should require governance mode."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        with runner.isolated_filesystem():
            policy_path = Path("governance_policy.yaml")
            policy_path.write_text("mode: enforce\n", encoding="utf-8")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--governance-policy",
                    str(policy_path),
                ],
            )

        assert result.exit_code != 0
        assert "--governance-policy requires --governance" in result.output

    def test_handoff_invalid_governance_policy_writes_failed_manifest(self):
        """Invalid governance policy should fail with deterministic manifest payload."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            policy_path = Path("governance_policy.yaml")
            policy_path.write_text("- invalid\n- policy\n", encoding="utf-8")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--governance",
                    "--governance-policy",
                    str(policy_path),
                    "--json",
                ],
            )

            assert result.exit_code != 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "failed"
            assert payload["failed_step"] == "governance_policy"
            assert "Governance policy file must contain a YAML object" in payload["error"]
            assert (output_dir / "handoff_manifest.json").exists()

    def test_handoff_governance_policy_file_controls_mode_when_flag_not_passed(self):
        """Policy file mode should apply when --governance-mode is not passed explicitly."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "public_benefits_triage.yaml"

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            policy_path = Path("governance_policy.yaml")
            policy_path.write_text(
                "\n".join(
                    [
                        "mode: enforce",
                        "gates:",
                        "  security: true",
                        "  collaboration: false",
                        "  export_ops: false",
                        "security:",
                        "  profile: balanced",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--governance",
                    "--governance-policy",
                    str(policy_path),
                    "--json",
                ],
            )

            assert result.exit_code != 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["governance_summary"]["mode"] == "enforce"
            assert payload["governance_failed"] is True
            assert (
                "security:security_balanced_threshold_breached"
                in payload["governance_reason_codes"]
            )

    def test_handoff_governance_mode_flag_overrides_policy_mode(self):
        """CLI governance-mode flag should override mode from governance policy file."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "public_benefits_triage.yaml"

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            policy_path = Path("governance_policy.yaml")
            policy_path.write_text(
                "\n".join(
                    [
                        "mode: enforce",
                        "gates:",
                        "  security: true",
                        "  collaboration: false",
                        "  export_ops: false",
                        "security:",
                        "  profile: balanced",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--governance",
                    "--governance-mode",
                    "observe",
                    "--governance-policy",
                    str(policy_path),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["governance_summary"]["mode"] == "observe"

    def test_handoff_writes_failed_manifest_when_mid_step_raises(self, monkeypatch):
        """`handoff` should return non-zero but still write manifest when a middle step fails."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"

        def _raise_report_error(*args, **kwargs):
            raise RuntimeError("html rendering failed")

        monkeypatch.setattr(ReportGenerator, "generate_report", _raise_report_error)

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    str(system_yaml),
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ],
            )

            assert result.exit_code != 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "failed"
            assert payload["failed_step"] == "report_html"
            assert "html rendering failed" in payload["error"]
            assert (output_dir / "handoff_manifest.json").exists()
            # earlier steps should still be present
            assert (output_dir / "check.json").exists()
            assert not (output_dir / "report.html").exists()

    def test_handoff_invalid_descriptor_path_fails_with_manifest(self):
        """`handoff` should fail deterministically for missing descriptor and still emit manifest."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            output_dir = Path("handoff_out")
            result = runner.invoke(
                main,
                [
                    "handoff",
                    "missing.yaml",
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ],
            )

            assert result.exit_code != 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "failed"
            assert payload["failed_step"] == "validate"
            assert (output_dir / "handoff_manifest.json").exists()

    def test_ops_closeout_generates_artifacts_and_json_payload(self, monkeypatch):
        """`ops closeout --json` should write deterministic artifact set and manifest payload."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/234"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/acme/repo/actions/runs/234",
                    },
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "html_url": "https://github.com/acme/repo/releases/tag/v0.1.29",
                        "assets": [
                            {"name": "pkg-0.1.29-py3-none-any.whl"},
                            {"name": "pkg-0.1.29.tar.gz"},
                        ],
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=200, json={"info": {"version": "0.1.29"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=200, text="ok")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        with runner.isolated_filesystem():
            output_dir = Path("ops_closeout")
            result = runner.invoke(
                main,
                [
                    "ops",
                    "closeout",
                    "--version",
                    "0.1.29",
                    "--release-run-id",
                    "234",
                    "--repo",
                    "acme/repo",
                    "--github-api-base-url",
                    "https://example.test/api",
                    "--pypi-base-url",
                    "https://example.test",
                    "--rtd-url",
                    "https://example.test/rtd",
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "success"
            assert payload["failed"] is False
            assert payload["reason_codes"] == []
            assert payload["effective_reason_codes"] == []
            assert payload["resolution"]["attempted"] is False
            assert payload["resolution"]["resolution_source"] == "explicit_inputs"
            assert payload["resolution"]["reason_codes"] == []
            assert payload["freshness_reason_codes"] == []
            assert payload["waived_reason_codes"] == []
            assert payload["expired_waiver_reason_codes"] == []
            assert payload["escalation_enabled"] is False
            assert payload["escalation_required"] is False
            assert payload["escalation_reason_codes"] == []
            assert payload["escalation"]["mode"] == "observe"
            assert payload["escalation"]["escalation_required"] is False
            assert payload["escalation"]["escalation_reason_codes"] == []
            assert payload["waiver_summary"] == {
                "configured_count": 0,
                "matched_count": 0,
                "waived_count": 0,
                "expired_count": 0,
            }
            assert payload["freshness_metrics"] == {
                "run_age_hours": None,
                "release_age_hours": None,
                "rtd_age_hours": None,
            }
            assert (output_dir / "ops_closeout_checks.json").exists()
            assert (output_dir / "ops_closeout_manifest.json").exists()
            assert (output_dir / "ops_closeout_evidence.md").exists()

    def test_ops_closeout_escalation_pack_writes_artifacts(self, monkeypatch):
        """`ops closeout --escalation-pack` should emit deterministic escalation artifacts."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/234"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/acme/repo/actions/runs/234",
                    },
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "html_url": "https://github.com/acme/repo/releases/tag/v0.1.29",
                        "assets": [
                            {"name": "pkg-0.1.29-py3-none-any.whl"},
                            {"name": "pkg-0.1.29.tar.gz"},
                        ],
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=200, json={"info": {"version": "0.1.29"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=200, text="ok")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        with runner.isolated_filesystem():
            output_dir = Path("ops_closeout")
            result = runner.invoke(
                main,
                [
                    "ops",
                    "closeout",
                    "--version",
                    "0.1.29",
                    "--release-run-id",
                    "234",
                    "--repo",
                    "acme/repo",
                    "--github-api-base-url",
                    "https://example.test/api",
                    "--pypi-base-url",
                    "https://example.test",
                    "--rtd-url",
                    "https://example.test/rtd",
                    "--escalation-pack",
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["escalation_enabled"] is True
            assert payload["escalation_required"] is False
            assert payload["escalation_reason_codes"] == []
            assert payload["escalation"]["run_context"]["version"] == "0.1.29"
            assert (output_dir / "ops_closeout_escalation.json").exists()
            assert (output_dir / "ops_closeout_escalation.md").exists()

    def test_ops_closeout_observe_with_escalation_pack_reports_failure_without_nonzero(
        self, monkeypatch
    ):
        """Observe mode with escalation pack should keep exit 0 while marking escalation required."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/11"):
                return httpx.Response(
                    status_code=200, json={"status": "completed", "conclusion": "failure"}
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(status_code=404, text="missing")
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=404, text="missing")
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=503, text="down")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--version",
                "0.1.29",
                "--release-run-id",
                "11",
                "--mode",
                "observe",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--pypi-base-url",
                "https://example.test",
                "--rtd-url",
                "https://example.test/rtd",
                "--escalation-pack",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["failed"] is True
        assert payload["escalation_enabled"] is True
        assert payload["escalation_required"] is True
        assert "github_run_failed" in payload["escalation_reason_codes"]

    def test_ops_closeout_escalation_pack_write_failure_is_nonzero(self, monkeypatch):
        """Escalation artifact write failures must produce deterministic non-zero in all modes."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/234"):
                return httpx.Response(
                    status_code=200,
                    json={"status": "completed", "conclusion": "success"},
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "assets": [
                            {"name": "pkg-0.1.29-py3-none-any.whl"},
                            {"name": "pkg-0.1.29.tar.gz"},
                        ]
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=200, json={"info": {"version": "0.1.29"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=200, text="ok")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        original_write_text = Path.write_text

        def _patched_write_text(self: Path, data: str, *args, **kwargs):
            if self.name == "ops_closeout_escalation.json":
                raise OSError("disk full")
            return original_write_text(self, data, *args, **kwargs)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)
        monkeypatch.setattr(Path, "write_text", _patched_write_text)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--version",
                "0.1.29",
                "--release-run-id",
                "234",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--pypi-base-url",
                "https://example.test",
                "--rtd-url",
                "https://example.test/rtd",
                "--mode",
                "observe",
                "--escalation-pack",
                "--json",
            ],
        )

        assert result.exit_code != 0
        assert "failed to write ops closeout artifacts" in result.output

    def test_ops_closeout_enforce_fails_on_failed_checks(self, monkeypatch):
        """`ops closeout --mode enforce` should return non-zero when any check fails."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/11"):
                return httpx.Response(
                    status_code=200, json={"status": "completed", "conclusion": "failure"}
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(status_code=404, text="missing")
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=404, text="missing")
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=503, text="down")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        with runner.isolated_filesystem():
            output_dir = Path("ops_closeout")
            result = runner.invoke(
                main,
                [
                    "ops",
                    "closeout",
                    "--version",
                    "0.1.29",
                    "--release-run-id",
                    "11",
                    "--mode",
                    "enforce",
                    "--repo",
                    "acme/repo",
                    "--github-api-base-url",
                    "https://example.test/api",
                    "--pypi-base-url",
                    "https://example.test",
                    "--rtd-url",
                    "https://example.test/rtd",
                    "--output-dir",
                    str(output_dir),
                    "--json",
                ],
            )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["failed"] is True
        assert "github_run_failed" in payload["reason_codes"]
        assert "github_release_failed" in payload["reason_codes"]
        assert "pypi_version_failed" in payload["reason_codes"]
        assert "rtd_failed" in payload["reason_codes"]
        assert "github_run_failed" in payload["effective_reason_codes"]
        assert payload["freshness_reason_codes"] == []
        assert payload["waived_reason_codes"] == []
        assert payload["expired_waiver_reason_codes"] == []

    def test_ops_closeout_invalid_repo_format_fails(self):
        """`ops closeout` should fail fast for invalid repo value."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--version",
                "0.1.29",
                "--release-run-id",
                "10",
                "--repo",
                "invalid_repo",
            ],
        )

        assert result.exit_code != 0
        assert "Policy repo must be in '<owner>/<name>'" in result.output

    def test_ops_closeout_policy_file_is_used_when_cli_release_inputs_missing(self, monkeypatch):
        """`ops closeout --policy` should resolve release inputs from policy file."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/234"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/acme/repo/actions/runs/234",
                    },
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "html_url": "https://github.com/acme/repo/releases/tag/v0.1.29",
                        "assets": [
                            {"name": "pkg-0.1.29-py3-none-any.whl"},
                            {"name": "pkg-0.1.29.tar.gz"},
                        ],
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=200, json={"info": {"version": "0.1.29"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=200, text="ok")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        with runner.isolated_filesystem():
            Path("ops_policy.yaml").write_text(
                "\n".join(
                    [
                        "mode: observe",
                        "repo: acme/repo",
                        "pypi_project: eu-ai-act-compliance-kit",
                        "rtd_url: https://example.test/rtd",
                        "release:",
                        "  version: 0.1.29",
                        "  run_id: 234",
                    ]
                ),
                encoding="utf-8",
            )
            result = runner.invoke(
                main,
                [
                    "ops",
                    "closeout",
                    "--policy",
                    "ops_policy.yaml",
                    "--github-api-base-url",
                    "https://example.test/api",
                    "--pypi-base-url",
                    "https://example.test",
                    "--json",
                ],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["status"] == "success"
            assert payload["version"] == "0.1.29"
            assert payload["release_run_id"] == 234
            assert payload["waiver_summary"]["configured_count"] == 0

    def test_ops_closeout_freshness_thresholds_enforce_fail(self, monkeypatch):
        """`ops closeout --mode enforce` should fail when configured freshness thresholds are violated."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/234"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "status": "completed",
                        "conclusion": "success",
                        "updated_at": "2026-03-20T00:00:00Z",
                    },
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "assets": [
                            {"name": "pkg-0.1.29-py3-none-any.whl"},
                            {"name": "pkg-0.1.29.tar.gz"},
                        ],
                        "published_at": "2026-03-20T00:00:00Z",
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=200, json={"info": {"version": "0.1.29"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=200, text="ok")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--version",
                "0.1.29",
                "--release-run-id",
                "234",
                "--mode",
                "enforce",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--pypi-base-url",
                "https://example.test",
                "--rtd-url",
                "https://example.test/rtd",
                "--max-run-age-hours",
                "1",
                "--max-release-age-hours",
                "1",
                "--max-rtd-age-hours",
                "1",
                "--json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["failed"] is True
        assert "github_run_stale" in payload["freshness_reason_codes"]
        assert "github_release_stale" in payload["freshness_reason_codes"]
        assert "rtd_stale_or_unknown" in payload["freshness_reason_codes"]
        assert "github_run_stale" in payload["effective_reason_codes"]
        assert payload["waived_reason_codes"] == []
        assert payload["expired_waiver_reason_codes"] == []

    def test_ops_closeout_enforce_can_waive_stale_reasons_via_cli(self, monkeypatch):
        """Active CLI waivers should suppress matching stale reason codes in enforce mode."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/234"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "status": "completed",
                        "conclusion": "success",
                        "updated_at": "2026-03-20T00:00:00Z",
                    },
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "assets": [
                            {"name": "pkg-0.1.29-py3-none-any.whl"},
                            {"name": "pkg-0.1.29.tar.gz"},
                        ],
                        "published_at": "2026-03-20T00:00:00Z",
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=200, json={"info": {"version": "0.1.29"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(
                    status_code=200,
                    text="ok",
                    headers={"Last-Modified": "Fri, 20 Mar 2026 00:00:00 GMT"},
                )
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--version",
                "0.1.29",
                "--release-run-id",
                "234",
                "--mode",
                "enforce",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--pypi-base-url",
                "https://example.test",
                "--rtd-url",
                "https://example.test/rtd",
                "--max-run-age-hours",
                "1",
                "--max-release-age-hours",
                "1",
                "--max-rtd-age-hours",
                "1",
                "--waiver-reason-code",
                "github_run_stale",
                "--waiver-expires-at",
                "2099-01-01T00:00:00Z",
                "--waiver-reason-code",
                "github_release_stale",
                "--waiver-expires-at",
                "2099-01-01T00:00:00Z",
                "--waiver-reason-code",
                "rtd_stale_or_unknown",
                "--waiver-expires-at",
                "2099-01-01T00:00:00Z",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["failed"] is False
        assert payload["effective_reason_codes"] == []
        assert sorted(payload["waived_reason_codes"]) == [
            "github_release_stale",
            "github_run_stale",
            "rtd_stale_or_unknown",
        ]
        assert payload["expired_waiver_reason_codes"] == []

    def test_ops_closeout_enforce_fails_with_expired_waiver(self, monkeypatch):
        """Expired waiver should not suppress stale failure in enforce mode."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/actions/runs/234"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "status": "completed",
                        "conclusion": "success",
                        "updated_at": "2026-03-20T00:00:00Z",
                    },
                )
            if str(request.url).endswith("/releases/tags/v0.1.29"):
                return httpx.Response(
                    status_code=200,
                    json={
                        "assets": [
                            {"name": "pkg-0.1.29-py3-none-any.whl"},
                            {"name": "pkg-0.1.29.tar.gz"},
                        ],
                        "published_at": "2026-03-20T00:00:00Z",
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(status_code=200, json={"info": {"version": "0.1.29"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(
                    status_code=200,
                    text="ok",
                    headers={"Last-Modified": "Fri, 20 Mar 2026 00:00:00 GMT"},
                )
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--version",
                "0.1.29",
                "--release-run-id",
                "234",
                "--mode",
                "enforce",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--pypi-base-url",
                "https://example.test",
                "--rtd-url",
                "https://example.test/rtd",
                "--max-run-age-hours",
                "1",
                "--max-release-age-hours",
                "1",
                "--max-rtd-age-hours",
                "1",
                "--waiver-reason-code",
                "github_run_stale",
                "--waiver-expires-at",
                "2000-01-01T00:00:00Z",
                "--json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["failed"] is True
        assert "github_run_stale" in payload["effective_reason_codes"]
        assert payload["waived_reason_codes"] == []
        assert payload["expired_waiver_reason_codes"] == ["github_run_stale"]

    def test_ops_closeout_rejects_mismatched_waiver_flags(self):
        """CLI should fail fast when waiver reason and expiry counts differ."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--waiver-reason-code",
                "github_run_stale",
            ],
        )
        assert result.exit_code != 0
        assert "--waiver-reason-code and --waiver-expires-at counts must match" in result.output

    def test_ops_closeout_rejects_invalid_waiver_expires_at(self):
        """CLI should fail with deterministic policy error for invalid waiver expiry format."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--waiver-reason-code",
                "github_run_stale",
                "--waiver-expires-at",
                "not-a-date",
            ],
        )
        assert result.exit_code != 0
        assert "Error resolving ops closeout policy" in result.output
        assert "expires_at" in result.output

    def test_ops_closeout_observe_mode_reports_missing_release_inputs_without_failing(self):
        """Observe mode should report missing release inputs in payload but exit successfully."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["ops", "closeout", "--json"])
            assert result.exit_code == 0
            payload = json.loads(result.output[result.output.find("{") :])
            assert payload["failed"] is True
            assert payload["status"] == "failed"
            assert "missing_release_version" in payload["reason_codes"]
            assert "missing_release_run_id" in payload["reason_codes"]

    def test_ops_closeout_resolve_latest_release_success(self, monkeypatch):
        """`--resolve-latest-release` should populate version/run-id and execute checks."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/repos/acme/repo/releases?per_page=100"):
                return httpx.Response(200, json=[{"tag_name": "v0.1.31", "draft": False}])
            if str(request.url).endswith(
                "/repos/acme/repo/actions/workflows/release.yml/runs?event=push&per_page=100"
            ):
                return httpx.Response(
                    200,
                    json={
                        "workflow_runs": [
                            {
                                "id": 333,
                                "head_branch": "v0.1.31",
                                "status": "completed",
                                "conclusion": "success",
                            }
                        ]
                    },
                )
            if str(request.url).endswith("/repos/acme/repo/actions/runs/333"):
                return httpx.Response(
                    200,
                    json={"status": "completed", "conclusion": "success"},
                )
            if str(request.url).endswith("/repos/acme/repo/releases/tags/v0.1.31"):
                return httpx.Response(
                    200,
                    json={
                        "assets": [
                            {"name": "pkg-0.1.31-py3-none-any.whl"},
                            {"name": "pkg-0.1.31.tar.gz"},
                        ]
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(200, json={"info": {"version": "0.1.31"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=200, text="ok")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--resolve-latest-release",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--pypi-base-url",
                "https://example.test",
                "--rtd-url",
                "https://example.test/rtd",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["failed"] is False
        assert payload["version"] == "0.1.31"
        assert payload["release_run_id"] == 333
        assert payload["resolution"]["attempted"] is True
        assert payload["resolution"]["resolved_version"] == "0.1.31"
        assert payload["resolution"]["resolved_run_id"] == 333
        assert payload["resolution"]["reason_codes"] == []

    def test_ops_closeout_resolve_latest_release_uses_explicit_version_for_run_lookup(
        self,
        monkeypatch,
    ):
        """When version is explicit and run id is missing, resolution should fetch run for that version."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/repos/acme/repo/releases?per_page=100"):
                return httpx.Response(
                    200,
                    json=[
                        {"tag_name": "v0.1.30", "draft": False},
                        {"tag_name": "v0.1.31", "draft": False},
                    ],
                )
            if str(request.url).endswith(
                "/repos/acme/repo/actions/workflows/release.yml/runs?event=push&per_page=100"
            ):
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
            if str(request.url).endswith("/repos/acme/repo/actions/runs/900"):
                return httpx.Response(
                    200,
                    json={"status": "completed", "conclusion": "success"},
                )
            if str(request.url).endswith("/repos/acme/repo/releases/tags/v0.1.30"):
                return httpx.Response(
                    200,
                    json={
                        "assets": [
                            {"name": "pkg-0.1.30-py3-none-any.whl"},
                            {"name": "pkg-0.1.30.tar.gz"},
                        ]
                    },
                )
            if str(request.url).endswith("/pypi/eu-ai-act-compliance-kit/json"):
                return httpx.Response(200, json={"info": {"version": "0.1.30"}})
            if str(request.url).endswith("/rtd"):
                return httpx.Response(status_code=200, text="ok")
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--resolve-latest-release",
                "--version",
                "0.1.30",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--pypi-base-url",
                "https://example.test",
                "--rtd-url",
                "https://example.test/rtd",
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["failed"] is False
        assert payload["version"] == "0.1.30"
        assert payload["release_run_id"] == 900
        assert payload["resolution"]["resolved_version"] == "0.1.30"
        assert payload["resolution"]["resolved_run_id"] == 900

    def test_ops_closeout_resolve_latest_release_enforce_fails_when_run_missing(self, monkeypatch):
        """Enforce mode should fail when auto-resolution cannot produce release run id."""
        runner = CliRunner()

        def handler(request):
            if str(request.url).endswith("/repos/acme/repo/releases?per_page=100"):
                return httpx.Response(200, json=[{"tag_name": "v0.1.31", "draft": False}])
            if str(request.url).endswith(
                "/repos/acme/repo/actions/workflows/release.yml/runs?event=push&per_page=100"
            ):
                return httpx.Response(200, json={"workflow_runs": []})
            return httpx.Response(status_code=404)

        transport = httpx.MockTransport(handler)
        original_client = httpx.Client

        def _fake_client(*args, **kwargs):
            return original_client(transport=transport)

        monkeypatch.setattr("eu_ai_act.ops_closeout.httpx.Client", _fake_client)

        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--resolve-latest-release",
                "--mode",
                "enforce",
                "--repo",
                "acme/repo",
                "--github-api-base-url",
                "https://example.test/api",
                "--json",
            ],
        )

        assert result.exit_code != 0
        decoder = json.JSONDecoder()
        payload, _ = decoder.raw_decode(result.output[result.output.find("{") :])
        assert payload["failed"] is True
        assert "latest_release_run_not_found" in payload["reason_codes"]
        assert "missing_release_run_id" in payload["reason_codes"]
        assert payload["resolution"]["attempted"] is True
        assert payload["resolution"]["resolved_version"] == "0.1.31"
        assert payload["resolution"]["resolved_run_id"] is None

    def test_ops_closeout_enforce_mode_fails_when_release_inputs_missing(self):
        """Enforce mode should exit non-zero with clear error when required release inputs are missing."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["ops", "closeout", "--mode", "enforce", "--json"])
            assert result.exit_code != 0
            decoder = json.JSONDecoder()
            payload, _ = decoder.raw_decode(result.output[result.output.find("{") :])
            assert payload["failed"] is True
            assert "missing_release_version" in payload["reason_codes"]
            assert "missing required release input(s) for enforce mode" in result.output

    def test_ops_closeout_invalid_freshness_threshold_fails(self):
        """`ops closeout` should fail fast for non-positive freshness thresholds."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "ops",
                "closeout",
                "--max-run-age-hours",
                "0",
            ],
        )

        assert result.exit_code != 0
        assert "--max-run-age-hours must be > 0" in result.output

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
        assert "security_summary" in show_payload
        assert show_payload["security_summary"]["framework"] == "owasp-llm-top-10"

        diff_result = runner.invoke(main, ["history", "diff", older_id, newer_id, "--json"])
        assert diff_result.exit_code == 0
        diff_payload = json.loads(diff_result.output[diff_result.output.find("{") :])
        assert "risk_tier_change" in diff_payload
        assert "summary_changes" in diff_payload
        assert "security_summary_change" in diff_payload
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
                "average_security_coverage_percentage",
                "security_control_status_distribution",
                "systems",
                "errors",
            ]:
                assert key in payload
            assert payload["valid_system_count"] == 1
            assert payload["invalid_descriptor_count"] == 0
            assert payload["systems"][0]["security_summary"]["framework"] == "owasp-llm-top-10"

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

    def test_collaboration_sync_list_update_summary_contract(self, monkeypatch, tmp_path):
        """`collaboration` commands should expose stable sync/list/update/summary JSON contracts."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        collab_path = tmp_path / ".eu_ai_act" / "collaboration_tasks.jsonl"
        monkeypatch.setenv("EU_AI_ACT_COLLABORATION_PATH", str(collab_path))

        sync_output = tmp_path / "sync.json"
        sync_result = runner.invoke(
            main,
            [
                "collaboration",
                "sync",
                str(system_yaml),
                "--owner-default",
                "alice",
                "--output",
                str(sync_output),
            ],
        )
        assert sync_result.exit_code == 0
        assert sync_output.exists()
        sync_payload = json.loads(sync_output.read_text(encoding="utf-8"))
        assert "generated_at" in sync_payload
        assert sync_payload["system_name"] == "Medical Imaging Diagnosis AI"
        assert sync_payload["collaboration_path"].endswith("collaboration_tasks.jsonl")
        assert "changes" in sync_payload
        assert "summary" in sync_payload
        assert sync_payload["summary"]["open_count"] >= 1
        assert sync_payload["tasks"]

        task_id = sync_payload["tasks"][0]["task_id"]

        update_result = runner.invoke(
            main,
            [
                "collaboration",
                "update",
                task_id,
                "--status",
                "in_review",
                "--note",
                "Triage started",
                "--note-author",
                "qa",
                "--json",
            ],
        )
        assert update_result.exit_code == 0
        update_payload = json.loads(update_result.output[update_result.output.find("{") :])
        assert update_payload["changed"] is True
        assert update_payload["updated_task"]["workflow_status"] == "in_review"

        list_result = runner.invoke(
            main,
            ["collaboration", "list", "--status", "in_review", "--json"],
        )
        assert list_result.exit_code == 0
        list_payload = json.loads(list_result.output[list_result.output.find("{") :])
        assert list_payload["count"] >= 1

        summary_result = runner.invoke(main, ["collaboration", "summary", "--json"])
        assert summary_result.exit_code == 0
        summary_payload = json.loads(summary_result.output[summary_result.output.find("{") :])
        assert "open_count" in summary_payload
        assert "in_review_count" in summary_payload
        assert "blocked_count" in summary_payload
        assert "done_count" in summary_payload
        assert summary_payload["in_review_count"] >= 1

    def test_collaboration_invalid_inputs_fail_deterministically(self, monkeypatch, tmp_path):
        """Collaboration CLI should fail with clear errors for invalid inputs."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "spam_filter.yaml"
        collab_path = tmp_path / ".eu_ai_act" / "collaboration_tasks.jsonl"
        monkeypatch.setenv("EU_AI_ACT_COLLABORATION_PATH", str(collab_path))

        sync_result = runner.invoke(main, ["collaboration", "sync", str(system_yaml), "--json"])
        assert sync_result.exit_code == 0

        no_update_flags = runner.invoke(
            main,
            ["collaboration", "update", "Spam Filter AI::Art. 69"],
        )
        assert no_update_flags.exit_code != 0
        assert "provide at least one of --status, --owner, or --note" in no_update_flags.output

        unknown_task = runner.invoke(
            main,
            ["collaboration", "update", "missing-task", "--status", "done"],
        )
        assert unknown_task.exit_code != 0
        assert "Task not found" in unknown_task.output

        invalid_limit = runner.invoke(main, ["collaboration", "list", "--limit", "0"])
        assert invalid_limit.exit_code != 0
        assert "limit must be >= 1" in invalid_limit.output

    def test_collaboration_gate_observe_json_contract(self, monkeypatch, tmp_path):
        """`collaboration gate --mode observe` should emit payload and keep zero exit."""
        runner = CliRunner()
        system_yaml = EXAMPLES_DIR / "medical_diagnosis.yaml"
        collab_path = tmp_path / ".eu_ai_act" / "collaboration_tasks.jsonl"
        monkeypatch.setenv("EU_AI_ACT_COLLABORATION_PATH", str(collab_path))

        sync_result = runner.invoke(main, ["collaboration", "sync", str(system_yaml), "--json"])
        assert sync_result.exit_code == 0

        result = runner.invoke(
            main,
            [
                "collaboration",
                "gate",
                "--mode",
                "observe",
                "--collab-path",
                str(collab_path),
                "--json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["mode"] == "observe"
        assert payload["failed"] is True
        assert "unassigned_actionable_threshold_exceeded" in payload["reason_codes"]
        assert "effective_policy" in payload
        assert "metrics" in payload
        assert payload["metrics"]["has_collaboration_data"] is True
        assert "stale_actionable_count" in payload["metrics"]
        assert "blocked_stale_count" in payload["metrics"]
        assert "review_stale_count" in payload["metrics"]
        assert payload["effective_policy"]["thresholds"]["stale_actionable_max"] is None
        assert payload["effective_policy"]["thresholds"]["blocked_stale_max"] is None
        assert payload["effective_policy"]["thresholds"]["review_stale_max"] is None
        assert payload["effective_policy"]["sla"]["stale_after_hours"] == 72.0
        assert payload["effective_policy"]["sla"]["blocked_stale_after_hours"] == 72.0
        assert payload["effective_policy"]["sla"]["review_stale_after_hours"] == 48.0
        assert payload["collaboration_path"] == str(collab_path)

    def test_collaboration_gate_enforce_missing_data_nonzero(self, tmp_path):
        """`collaboration gate --mode enforce` should fail when ledger data is missing."""
        runner = CliRunner()
        collab_path = tmp_path / ".eu_ai_act" / "collaboration_tasks.jsonl"

        result = runner.invoke(
            main,
            [
                "collaboration",
                "gate",
                "--mode",
                "enforce",
                "--collab-path",
                str(collab_path),
                "--json",
            ],
        )
        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["mode"] == "enforce"
        assert payload["failed"] is True
        assert payload["reason_codes"] == ["missing_collaboration_data"]

    def test_collaboration_gate_policy_file_and_cli_override_precedence(self, tmp_path):
        """CLI overrides should take precedence over collaboration policy file values."""
        runner = CliRunner()
        policy_file = tmp_path / "collaboration_gate_policy.yaml"
        policy_file.write_text(
            (
                "mode: enforce\n"
                "scope:\n"
                "  system: Medical Imaging Diagnosis AI\n"
                "window:\n"
                "  limit: 50\n"
                "thresholds:\n"
                "  blocked_max: 1\n"
                "  unassigned_actionable_max: 1\n"
                "  stale_actionable_max: 2\n"
                "  blocked_stale_max: 3\n"
                "  review_stale_max: 4\n"
                "sla:\n"
                "  stale_after_hours: 48\n"
                "  blocked_stale_after_hours: 24\n"
                "  review_stale_after_hours: 12\n"
            ),
            encoding="utf-8",
        )
        collab_path = tmp_path / ".eu_ai_act" / "collaboration_tasks.jsonl"

        result = runner.invoke(
            main,
            [
                "collaboration",
                "gate",
                "--policy",
                str(policy_file),
                "--mode",
                "observe",
                "--blocked-max",
                "0",
                "--stale-after-hours",
                "12",
                "--collab-path",
                str(collab_path),
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["mode"] == "observe"
        assert payload["effective_policy"]["window"]["limit"] == 50
        assert payload["effective_policy"]["scope"]["system"] == "Medical Imaging Diagnosis AI"
        assert payload["effective_policy"]["thresholds"]["blocked_max"] == 0
        assert payload["effective_policy"]["thresholds"]["unassigned_actionable_max"] == 1
        assert payload["effective_policy"]["thresholds"]["stale_actionable_max"] == 2
        assert payload["effective_policy"]["thresholds"]["blocked_stale_max"] == 3
        assert payload["effective_policy"]["thresholds"]["review_stale_max"] == 4
        assert payload["effective_policy"]["sla"]["stale_after_hours"] == 12.0
        assert payload["effective_policy"]["sla"]["blocked_stale_after_hours"] == 24.0
        assert payload["effective_policy"]["sla"]["review_stale_after_hours"] == 12.0

    def test_collaboration_gate_enforce_stale_threshold_nonzero(self, tmp_path):
        """Enforce mode should fail when stale actionable threshold is exceeded."""
        runner = CliRunner()
        collab_path = tmp_path / ".eu_ai_act" / "collaboration_tasks.jsonl"
        collab_path.parent.mkdir(parents=True, exist_ok=True)
        collab_path.write_text(
            (
                '{"task_id":"Medical Imaging Diagnosis AI::Art. 10","system_name":"Medical Imaging Diagnosis AI",'
                '"descriptor_path":"/tmp/system.yaml","requirement_id":"Art. 10","article":"Art. 10",'
                '"title":"Data governance","finding_status":"non_compliant","severity":"HIGH",'
                '"workflow_status":"open","owner":"alice","notes":[],"created_at":"2026-03-24T00:00:00+00:00",'
                '"updated_at":"2026-03-24T00:00:00+00:00"}\n'
            ),
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "collaboration",
                "gate",
                "--mode",
                "enforce",
                "--stale-actionable-max",
                "0",
                "--stale-after-hours",
                "1",
                "--collab-path",
                str(collab_path),
                "--json",
            ],
        )
        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert "stale_actionable_threshold_exceeded" in payload["reason_codes"]
        assert payload["decision_details"]["stale_actionable"]["violated"] is True

    def test_collaboration_gate_invalid_flags_fail(self):
        """Gate command should validate invalid threshold and limit values."""
        runner = CliRunner()

        invalid_cases = [
            (["--limit", "0"], "--limit must be >= 1"),
            (["--blocked-max", "-1"], "--blocked-max must be >= 0"),
            (["--unassigned-actionable-max", "-1"], "--unassigned-actionable-max must be >= 0"),
            (["--stale-actionable-max", "-1"], "--stale-actionable-max must be >= 0"),
            (["--blocked-stale-max", "-1"], "--blocked-stale-max must be >= 0"),
            (["--review-stale-max", "-1"], "--review-stale-max must be >= 0"),
            (["--stale-after-hours", "0"], "--stale-after-hours must be > 0"),
            (["--blocked-stale-after-hours", "0"], "--blocked-stale-after-hours must be > 0"),
            (["--review-stale-after-hours", "0"], "--review-stale-after-hours must be > 0"),
        ]
        for flags, expected_error in invalid_cases:
            result = runner.invoke(main, ["collaboration", "gate", *flags, "--json"])
            assert result.exit_code != 0
            output = result.output + getattr(result, "stderr", "")
            assert expected_error in output

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
        assert "security_mapping" in payload
        assert payload["security_mapping"]["framework"] == "owasp-llm-top-10"
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
        assert "security_mapping" in payload
        assert payload["security_mapping"]["framework"] == "owasp-llm-top-10"
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
        assert all("security_mapping" in item for item in payload["results"])

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

    def test_export_reconcile_emits_warning_when_log_write_fails(self, monkeypatch):
        """Reconcile should surface best-effort log-write warnings without changing outcome."""
        runner = CliRunner()

        monkeypatch.setattr(
            cli_module,
            "reconcile_export_push_records",
            lambda **_kwargs: {
                "generated_at": "2026-03-22T00:00:00+00:00",
                "target": "jira",
                "ledger_path": "/tmp/ledger.jsonl",
                "reconcile_log_path": "/tmp/reconcile.jsonl",
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
                "reconcile_log_warning": "Failed to write export reconcile log: disk full",
                "results": [{"record_index": 1, "status": "exists"}],
            },
        )

        result = runner.invoke(
            main,
            ["export", "reconcile", "--target", "jira", "--json"],
        )

        assert result.exit_code == 0
        output = result.output + getattr(result, "stderr", "")
        assert "Warning: Failed to write export reconcile log" in output

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

    def test_export_replay_json_contract_and_nonzero_on_failure(self, monkeypatch):
        """Replay should return payload contract and non-zero on failed/unreplayable counts."""
        runner = CliRunner()

        def _fake_replay(**_kwargs):
            return {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "target": "jira",
                "ops_path": "/tmp/export_ops_log.jsonl",
                "selected_count": 2,
                "replayed_count": 1,
                "failed_count": 1,
                "unreplayable_count": 0,
                "results": [],
            }

        monkeypatch.setattr(cli_module, "replay_export_push_failures", _fake_replay)

        result = runner.invoke(main, ["export", "replay", "--target", "jira", "--json"])
        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["selected_count"] == 2
        assert payload["replayed_count"] == 1
        assert payload["failed_count"] == 1

    def test_export_replay_dry_run_is_forwarded(self, monkeypatch):
        """Replay dry-run flag should be forwarded to replay runtime."""
        runner = CliRunner()
        captured: dict[str, object] = {}

        def _fake_replay(**kwargs):
            captured["dry_run"] = kwargs["dry_run"]
            return {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "target": "jira",
                "ops_path": "/tmp/export_ops_log.jsonl",
                "selected_count": 1,
                "replayed_count": 1,
                "failed_count": 0,
                "unreplayable_count": 0,
                "results": [
                    {
                        "status": "replayed",
                        "push_result": {"dry_run": True, "push_mode": "create"},
                    }
                ],
            }

        monkeypatch.setattr(cli_module, "replay_export_push_failures", _fake_replay)

        result = runner.invoke(
            main,
            ["export", "replay", "--target", "jira", "--dry-run", "--json"],
        )
        assert result.exit_code == 0
        assert captured["dry_run"] is True
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["results"][0]["push_result"]["dry_run"] is True

    def test_export_replay_invalid_flags_fail(self):
        """Replay should validate since-hours/limit/retry inputs deterministically."""
        runner = CliRunner()

        invalid_cases = [
            (["--limit", "0"], "--limit must be >= 1"),
            (["--since-hours", "-1"], "--since-hours must be >= 0"),
            (["--max-retries", "-1"], "--max-retries must be >= 0"),
            (["--retry-backoff-seconds", "0"], "--retry-backoff-seconds must be > 0"),
            (["--timeout-seconds", "0"], "--timeout-seconds must be > 0"),
        ]
        for flags, expected_error in invalid_cases:
            result = runner.invoke(main, ["export", "replay", "--target", "jira", *flags, "--json"])
            assert result.exit_code != 0
            output = result.output + getattr(result, "stderr", "")
            assert expected_error in output

    def test_export_rollup_json_contract_and_output_file(self, monkeypatch, tmp_path):
        """Rollup should support JSON payload contract and output file mode."""
        runner = CliRunner()

        def _fake_rollup(**_kwargs):
            return {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "window": {
                    "target": "jira",
                    "system_name": None,
                    "since_hours": None,
                    "limit": None,
                },
                "metrics": {
                    "total_attempts": 10,
                    "success_count": 8,
                    "failed_count": 2,
                    "skipped_duplicate_count": 1,
                    "success_rate": 80.0,
                    "latest_success_at": "2026-03-23T11:00:00+00:00",
                    "latest_failure_at": "2026-03-23T10:00:00+00:00",
                    "open_failures_count": 1,
                },
                "distributions": {
                    "by_target": {"jira": 10},
                    "by_push_mode": {"create": 7, "upsert": 3},
                    "by_operation": {"create": 7, "update": 2, "skip_duplicate": 1},
                },
                "systems_with_failures": ["System A"],
                "top_failure_reasons": [{"reason": "HTTP 503", "count": 2}],
                "ops_path": "/tmp/export_ops_log.jsonl",
                "idempotency_path": "/tmp/export_push_ledger.jsonl",
            }

        monkeypatch.setattr(cli_module, "summarize_export_ops_rollup", _fake_rollup)

        result = runner.invoke(main, ["export", "rollup", "--target", "jira", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["metrics"]["total_attempts"] == 10
        assert payload["distributions"]["by_operation"]["skip_duplicate"] == 1

        output_file = tmp_path / "rollup.json"
        file_result = runner.invoke(
            main,
            ["export", "rollup", "--target", "jira", "--output", str(output_file), "--json"],
        )
        assert file_result.exit_code == 0
        assert output_file.exists()
        file_payload = json.loads(output_file.read_text(encoding="utf-8"))
        assert file_payload["metrics"]["failed_count"] == 2

    def test_export_gate_observe_json_contract(self, monkeypatch):
        """`export gate --mode observe` should emit payload and keep zero exit."""
        runner = CliRunner()

        monkeypatch.setattr(
            cli_module,
            "summarize_export_ops_rollup",
            lambda **_kwargs: {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "metrics": {
                    "open_failures_count": 2,
                    "success_rate": 90.0,
                },
                "ops_path": "/tmp/export_ops_log.jsonl",
            },
        )
        monkeypatch.setattr(
            cli_module,
            "summarize_export_reconcile_log",
            lambda **_kwargs: {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "metrics": {
                    "drift_count": 1,
                    "has_reconcile_data": True,
                },
                "path": "/tmp/export_reconcile_log.jsonl",
            },
        )

        result = runner.invoke(
            main,
            ["export", "gate", "--target", "jira", "--mode", "observe", "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["mode"] == "observe"
        assert payload["failed"] is True
        assert "open_failures_threshold_exceeded" in payload["reason_codes"]
        assert "drift_threshold_exceeded" in payload["reason_codes"]
        assert "success_rate_below_threshold" in payload["reason_codes"]
        assert payload["effective_policy"]["window"]["since_hours"] == 24.0
        assert payload["effective_policy"]["window"]["limit"] == 200

    def test_export_gate_enforce_fails_when_reconcile_data_missing(self, monkeypatch):
        """Enforce mode should fail when reconcile data is missing."""
        runner = CliRunner()

        monkeypatch.setattr(
            cli_module,
            "summarize_export_ops_rollup",
            lambda **_kwargs: {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "metrics": {
                    "open_failures_count": 0,
                    "success_rate": 100.0,
                },
                "ops_path": "/tmp/export_ops_log.jsonl",
            },
        )
        monkeypatch.setattr(
            cli_module,
            "summarize_export_reconcile_log",
            lambda **_kwargs: {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "metrics": {
                    "drift_count": 0,
                    "has_reconcile_data": False,
                },
                "path": "/tmp/export_reconcile_log.jsonl",
            },
        )

        result = runner.invoke(
            main,
            ["export", "gate", "--target", "jira", "--mode", "enforce", "--json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["mode"] == "enforce"
        assert payload["failed"] is True
        assert payload["reason_codes"] == ["missing_reconcile_data"]

    def test_export_gate_policy_file_and_cli_override_precedence(self, tmp_path, monkeypatch):
        """CLI overrides should take precedence over policy file values."""
        runner = CliRunner()
        policy_file = tmp_path / "ops_gate_policy.yaml"
        policy_file.write_text(
            (
                "mode: enforce\n"
                "window:\n"
                "  since_hours: 12\n"
                "  limit: 50\n"
                "thresholds:\n"
                "  open_failures_max: 1\n"
                "  drift_max: 2\n"
                "  min_success_rate: 80.0\n"
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            cli_module,
            "summarize_export_ops_rollup",
            lambda **_kwargs: {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "metrics": {
                    "open_failures_count": 0,
                    "success_rate": 90.0,
                },
                "ops_path": "/tmp/export_ops_log.jsonl",
            },
        )
        monkeypatch.setattr(
            cli_module,
            "summarize_export_reconcile_log",
            lambda **_kwargs: {
                "generated_at": "2026-03-23T12:00:00+00:00",
                "metrics": {
                    "drift_count": 0,
                    "has_reconcile_data": True,
                },
                "path": "/tmp/export_reconcile_log.jsonl",
            },
        )

        result = runner.invoke(
            main,
            [
                "export",
                "gate",
                "--target",
                "jira",
                "--policy",
                str(policy_file),
                "--min-success-rate",
                "95",
                "--json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output[result.output.find("{") :])
        assert payload["mode"] == "enforce"
        assert payload["effective_policy"]["window"]["since_hours"] == 12.0
        assert payload["effective_policy"]["window"]["limit"] == 50
        assert payload["effective_policy"]["thresholds"]["min_success_rate"] == 95.0
        assert payload["reason_codes"] == ["success_rate_below_threshold"]

    def test_export_gate_invalid_flags_fail(self):
        """Gate command should validate invalid threshold/window values."""
        runner = CliRunner()

        invalid_cases = [
            (["--since-hours", "-1"], "--since-hours must be >= 0"),
            (["--limit", "0"], "--limit must be >= 1"),
            (["--open-failures-max", "-1"], "--open-failures-max must be >= 0"),
            (["--drift-max", "-1"], "--drift-max must be >= 0"),
            (["--min-success-rate", "101"], "--min-success-rate must be between 0 and 100"),
        ]
        for flags, expected_error in invalid_cases:
            result = runner.invoke(main, ["export", "gate", "--target", "jira", *flags, "--json"])
            assert result.exit_code != 0
            output = result.output + getattr(result, "stderr", "")
            assert expected_error in output
