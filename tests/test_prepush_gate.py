"""Tests for local pre-push descriptor gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prepush_gate.py"
MODULE_NAME = "scripts.prepush_gate"


def _load_gate_module():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load prepush gate module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


prepush_gate = _load_gate_module()


VALID_DESCRIPTOR_YAML = """
name: "Gate Test System"
description: "A valid descriptor used in pre-push gate unit tests."
use_cases:
  - domain: general_purpose
    description: "Provides drafting support for support staff."
    autonomous_decision: false
    impacts_fundamental_rights: false
data_practices:
  - type: personal
    retention_period: 30
    sharing_third_parties: false
    explicit_consent: true
human_oversight:
  oversight_mechanism: "approval_required"
  fallback_procedure: "Escalate to human on uncertainty."
  review_frequency: "per_decision"
  human_authority: true
training_data_source: "Curated internal support data with manual quality checks."
documentation: true
performance_monitoring: true
"""


def _write_descriptor(path: Path) -> Path:
    path.write_text(VALID_DESCRIPTOR_YAML, encoding="utf-8")
    return path


def _cp(returncode: int, stdout: str = "", stderr: str = ""):
    return prepush_gate.subprocess.CompletedProcess(
        args=["mock"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestPrepushGate:
    def test_descriptor_detection_valid_irrelevant_and_malformed(self, tmp_path):
        valid = _write_descriptor(tmp_path / "valid_system.yaml")

        unrelated = tmp_path / "workflow.yaml"
        unrelated.write_text(
            "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
            encoding="utf-8",
        )

        malformed = tmp_path / "broken_system.yaml"
        malformed.write_text(
            (
                "name: broken\n"
                "description: \"Broken descriptor for gate test\"\n"
                "use_cases:\n"
                "  - domain: general_purpose\n"
                "    description: \"valid looking\"\n"
                "data_practices:\n"
                "  - type: personal\n"
                "human_oversight:\n"
                "  oversight_mechanism: approval_required\n"
                "training_data_source: \"synthetic\"\n"
                "documentation: true\n"
                "performance_monitoring: true\n"
                ":\n"
            ),
            encoding="utf-8",
        )

        assert prepush_gate.is_descriptor_candidate(valid) is True
        assert prepush_gate.is_descriptor_candidate(unrelated) is False
        assert prepush_gate.is_descriptor_candidate(malformed) is True

    def test_policy_fail_for_unacceptable(self, tmp_path):
        descriptor = _write_descriptor(tmp_path / "system.yaml")

        def _runner(step, _descriptor, _repo_root):
            if step == "validate":
                return _cp(0, "ok")
            if step == "classify":
                return _cp(0, json.dumps({"risk_tier": "unacceptable"}))
            if step == "check":
                return _cp(0, json.dumps({"summary": {"non_compliant_count": 0}}))
            raise AssertionError(f"Unexpected step: {step}")

        exit_code = prepush_gate.run_gate([str(descriptor)], command_runner=_runner, repo_root=tmp_path)
        assert exit_code == 1

    def test_policy_fail_for_high_risk_with_non_compliant(self, tmp_path):
        descriptor = _write_descriptor(tmp_path / "system.yaml")

        def _runner(step, _descriptor, _repo_root):
            if step == "validate":
                return _cp(0, "ok")
            if step == "classify":
                return _cp(0, json.dumps({"risk_tier": "high_risk"}))
            if step == "check":
                return _cp(0, json.dumps({"summary": {"non_compliant_count": 2}}))
            raise AssertionError(f"Unexpected step: {step}")

        exit_code = prepush_gate.run_gate([str(descriptor)], command_runner=_runner, repo_root=tmp_path)
        assert exit_code == 1

    def test_policy_pass_for_non_blocking_cases(self, tmp_path):
        descriptor = _write_descriptor(tmp_path / "system.yaml")

        cases = [
            ("high_risk", 0),
            ("limited", 3),
            ("minimal", 1),
        ]

        for risk_tier, non_compliant_count in cases:
            def _runner(step, _descriptor, _repo_root, tier=risk_tier, nc=non_compliant_count):
                if step == "validate":
                    return _cp(0, "ok")
                if step == "classify":
                    return _cp(0, json.dumps({"risk_tier": tier}))
                if step == "check":
                    return _cp(0, json.dumps({"summary": {"non_compliant_count": nc}}))
                raise AssertionError(f"Unexpected step: {step}")

            exit_code = prepush_gate.run_gate(
                [str(descriptor)],
                command_runner=_runner,
                repo_root=tmp_path,
            )
            assert exit_code == 0

    def test_no_descriptor_changed_passes(self, tmp_path, capsys):
        readme = tmp_path / "notes.txt"
        readme.write_text("plain text", encoding="utf-8")
        config = tmp_path / "config.yaml"
        config.write_text("name: build\njobs: []\n", encoding="utf-8")

        def _runner(*_args, **_kwargs):
            raise AssertionError("Runner should not be called when no descriptor exists")

        exit_code = prepush_gate.run_gate(
            [str(readme), str(config)],
            command_runner=_runner,
            repo_root=tmp_path,
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "No changed AI descriptors detected" in captured.out

    def test_parse_or_runtime_errors_fail_with_reason(self, tmp_path, capsys):
        descriptor = _write_descriptor(tmp_path / "system.yaml")

        def _runtime_error_runner(step, _descriptor, _repo_root):
            if step == "validate":
                return _cp(1, stderr="Validation failed: malformed descriptor")
            raise AssertionError("validate should fail first")

        runtime_exit_code = prepush_gate.run_gate(
            [str(descriptor)],
            command_runner=_runtime_error_runner,
            repo_root=tmp_path,
        )
        runtime_output = capsys.readouterr().out
        assert runtime_exit_code == 1
        assert "validate failed" in runtime_output

        def _parse_error_runner(step, _descriptor, _repo_root):
            if step == "validate":
                return _cp(0, "ok")
            if step == "classify":
                return _cp(0, "not-json-output")
            raise AssertionError("classify parse should fail before check")

        parse_exit_code = prepush_gate.run_gate(
            [str(descriptor)],
            command_runner=_parse_error_runner,
            repo_root=tmp_path,
        )
        parse_output = capsys.readouterr().out
        assert parse_exit_code == 1
        assert "failed to parse classify JSON" in parse_output
