"""Contract tests for CI workflow structure."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ACTION_PATH = REPO_ROOT / "action.yml"


def _load_ci_jobs() -> dict:
    payload = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    return payload.get("jobs", {})


def _load_action_payload() -> dict:
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


def test_ci_contains_required_quickstart_smoke_job():
    """CI must include quickstart smoke job and execute smoke script."""
    jobs = _load_ci_jobs()
    assert "quickstart-smoke" in jobs

    quickstart_job = jobs["quickstart-smoke"]
    assert quickstart_job.get("name") == "Quickstart Smoke"

    steps = quickstart_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "./scripts/quickstart_smoke.sh" in joined_run


def test_all_checks_treats_quickstart_smoke_as_required():
    """All-checks gate must evaluate quickstart-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "quickstart-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.quickstart-smoke.result" in run_script


def test_ci_contains_examples_smoke_job():
    """CI must include examples-smoke job running validate/classify/check flows."""
    jobs = _load_ci_jobs()
    assert "examples-smoke" in jobs

    examples_job = jobs["examples-smoke"]
    assert examples_job.get("name") == "Examples Smoke"

    steps = examples_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert '"ai-act", "validate"' in joined_run
    assert '"ai-act", "classify"' in joined_run
    assert '"ai-act", "check"' in joined_run


def test_ci_test_job_enforces_coverage_floor():
    """CI test job should enforce minimum coverage threshold."""
    jobs = _load_ci_jobs()
    assert "test" in jobs

    test_steps = jobs["test"].get("steps", [])
    run_steps = [step.get("run", "") for step in test_steps if isinstance(step, dict)]
    joined_run = "\n".join(run_steps)
    assert "--cov-fail-under=80" in joined_run


def test_all_checks_treats_examples_smoke_as_required():
    """All-checks gate must evaluate examples-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "examples-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.examples-smoke.result" in run_script


def test_ci_contains_export_ops_gate_smoke_job():
    """CI must include export-ops-gate-smoke job validating observe-mode gate payload."""
    jobs = _load_ci_jobs()
    assert "export-ops-gate-smoke" in jobs

    gate_job = jobs["export-ops-gate-smoke"]
    assert gate_job.get("name") == "Export Ops Gate Smoke"

    steps = gate_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act export gate" in joined_run
    assert "--mode observe" in joined_run


def test_all_checks_treats_export_ops_gate_smoke_as_required():
    """All-checks gate must evaluate export-ops-gate-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "export-ops-gate-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.export-ops-gate-smoke.result" in run_script


def test_action_exposes_security_gate_input_and_outputs():
    """Composite action should expose non-breaking security gate controls and outputs."""
    action_payload = _load_action_payload()
    inputs = action_payload.get("inputs", {})
    outputs = action_payload.get("outputs", {})

    assert "security_gate_mode" in inputs
    assert inputs["security_gate_mode"].get("default") == "observe"
    assert "security_gate_profile" in inputs
    assert inputs["security_gate_profile"].get("default") == "balanced"

    assert "security_non_compliant_count" in outputs
    assert "security_partial_count" in outputs
    assert "security_not_assessed_count" in outputs
    assert "security_gate_failed" in outputs


def test_ci_action_smoke_exercises_security_gate_enforcement():
    """Action-smoke job must include explicit security gate enforcement scenario."""
    jobs = _load_ci_jobs()
    assert "action-smoke" in jobs

    action_smoke_steps = jobs["action-smoke"].get("steps", [])
    step_text = "\n".join(
        step.get("run", "") if isinstance(step, dict) else "" for step in action_smoke_steps
    )
    uses_payload = "\n".join(
        str(step) for step in action_smoke_steps if isinstance(step, dict) and "uses" in step
    )

    assert "steps.securitygate.outcome" in step_text
    assert "security_gate_mode" in uses_payload
    assert "security_gate_profile" in uses_payload
