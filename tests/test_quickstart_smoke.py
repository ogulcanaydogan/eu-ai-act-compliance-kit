"""Tests for the quickstart smoke script."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "quickstart_smoke.sh"
EXAMPLES_DIR = REPO_ROOT / "examples"


def _wrapper_env(tmp_path: Path) -> dict[str, str]:
    """Create a PATH wrapper so the script can resolve `ai-act` deterministically."""
    wrapper = tmp_path / "ai-act"
    wrapper.write_text(
        f"#!/usr/bin/env bash\n\"{sys.executable}\" -m eu_ai_act.cli \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env.get('PATH', '')}"
    env["PYTHON_BIN"] = sys.executable
    return env


def test_quickstart_smoke_success_generates_expected_outputs(tmp_path):
    """Smoke script should succeed for a valid descriptor and produce expected files."""
    output_dir = tmp_path / "out"
    env = _wrapper_env(tmp_path)

    result = subprocess.run(
        [str(SCRIPT_PATH), str(EXAMPLES_DIR / "medical_diagnosis.yaml"), str(output_dir)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "[quickstart-smoke] success:" in result.stdout

    classify_path = output_dir / "classify.json"
    check_path = output_dir / "check.json"
    report_path = output_dir / "report.json"
    report_html_path = output_dir / "report.html"

    assert classify_path.exists()
    assert check_path.exists()
    assert report_path.exists()
    assert report_html_path.exists()
    assert report_html_path.stat().st_size > 0

    classify = json.loads(classify_path.read_text(encoding="utf-8"))
    check = json.loads(check_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert "system_name" in classify
    assert "risk_tier" in classify
    assert "summary" in check
    assert "compliance_summary" in report


def test_quickstart_smoke_invalid_descriptor_fails_with_clear_error(tmp_path):
    """Smoke script should fail deterministically when descriptor path is invalid."""
    env = _wrapper_env(tmp_path)
    missing_descriptor = tmp_path / "missing.yaml"

    result = subprocess.run(
        [str(SCRIPT_PATH), str(missing_descriptor), str(tmp_path / "out")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    stderr = result.stderr.strip()
    assert "Descriptor not found" in stderr
