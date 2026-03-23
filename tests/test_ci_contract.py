"""Contract tests for CI workflow structure."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_ci_jobs() -> dict:
    payload = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    return payload.get("jobs", {})


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
