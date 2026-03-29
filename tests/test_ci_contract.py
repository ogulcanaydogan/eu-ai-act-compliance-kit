"""Contract tests for CI workflow structure."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ACTION_PATH = REPO_ROOT / "action.yml"
OPS_CLOSEOUT_DAILY_WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "ops-closeout-daily.yml"
)


def _load_ci_jobs() -> dict:
    payload = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    return payload.get("jobs", {})


def _load_action_payload() -> dict:
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


def _load_ops_closeout_daily_payload() -> dict:
    return yaml.safe_load(OPS_CLOSEOUT_DAILY_WORKFLOW_PATH.read_text(encoding="utf-8"))


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


def test_ci_contains_handoff_smoke_job():
    """CI must include handoff-smoke job validating GA handoff artifact contract."""
    jobs = _load_ci_jobs()
    assert "handoff-smoke" in jobs

    handoff_job = jobs["handoff-smoke"]
    assert handoff_job.get("name") == "Handoff Smoke"

    steps = handoff_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act handoff" in joined_run
    assert "handoff_manifest.json" in joined_run
    assert "security_map.json" in joined_run


def test_ci_contains_handoff_governance_rollout_smoke_job():
    """CI must include handoff-governance rollout smoke with PR observe/main-tag enforce."""
    jobs = _load_ci_jobs()
    assert "handoff-governance-rollout-smoke" in jobs

    handoff_job = jobs["handoff-governance-rollout-smoke"]
    assert handoff_job.get("name") == "Handoff Governance Rollout Smoke"

    steps = handoff_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act handoff" in joined_run
    assert "--governance" in joined_run
    assert "--governance-policy config/governance_handoff_policy.yaml" in joined_run
    assert "governance_gate.json" in joined_run
    assert "GATE_MODE" in joined_run
    assert "github.event_name" in joined_run


def test_ci_contains_ops_closeout_rollout_smoke_job():
    """CI must include ops-closeout-rollout-smoke job with PR observe/main-tag enforce."""
    jobs = _load_ci_jobs()
    assert "ops-closeout-rollout-smoke" in jobs

    closeout_job = jobs["ops-closeout-rollout-smoke"]
    assert closeout_job.get("name") == "Ops Closeout Rollout Smoke"

    steps = closeout_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act ops closeout" in joined_run
    assert "--policy config/ops_closeout_policy.yaml" in joined_run
    assert '--mode "$GATE_MODE"' in joined_run
    assert "--max-run-age-hours 1" in joined_run
    assert "--max-release-age-hours 1" in joined_run
    assert "--max-rtd-age-hours 1" in joined_run
    assert "--waiver-reason-code github_run_stale" in joined_run
    assert "--waiver-reason-code github_release_stale" in joined_run
    assert "--waiver-reason-code rtd_stale_or_unknown" in joined_run
    assert "--waiver-expires-at 2099-01-01T00:00:00Z" in joined_run
    assert "ops_closeout_manifest.json" in joined_run
    assert "ops_closeout_checks.json" in joined_run
    assert "ops_closeout_evidence.md" in joined_run


def test_ci_test_job_enforces_coverage_floor():
    """CI test job should enforce minimum coverage threshold."""
    jobs = _load_ci_jobs()
    assert "test" in jobs

    test_steps = jobs["test"].get("steps", [])
    run_steps = [step.get("run", "") for step in test_steps if isinstance(step, dict)]
    joined_run = "\n".join(run_steps)
    assert "--cov-fail-under=80" in joined_run


def test_ci_contains_compat_smoke_job_with_python_matrix():
    """CI must include compat-smoke job for Python 3.11/3.12/3.13 handoff/governance smoke."""
    jobs = _load_ci_jobs()
    assert "compat-smoke" in jobs

    compat_job = jobs["compat-smoke"]
    assert compat_job.get("name") == "Compat Smoke (Python ${{ matrix.python-version }})"
    matrix = compat_job.get("strategy", {}).get("matrix", {})
    assert matrix.get("python-version") == ["3.11", "3.12", "3.13"]

    steps = compat_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act --help" in joined_run
    assert "ai-act --version" in joined_run
    assert "ai-act handoff" in joined_run
    assert "--governance" in joined_run
    assert "--governance-mode observe" in joined_run
    assert "governance_gate.json" in joined_run


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


def test_all_checks_treats_compat_smoke_as_required():
    """All-checks gate must evaluate compat-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "compat-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.compat-smoke.result" in run_script


def test_all_checks_treats_handoff_smoke_as_required():
    """All-checks gate must evaluate handoff-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "handoff-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.handoff-smoke.result" in run_script


def test_all_checks_treats_handoff_governance_rollout_smoke_as_required():
    """All-checks gate must evaluate handoff-governance-rollout-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "handoff-governance-rollout-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.handoff-governance-rollout-smoke.result" in run_script


def test_all_checks_treats_ops_closeout_rollout_smoke_as_required():
    """All-checks gate must evaluate ops-closeout-rollout-smoke as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "ops-closeout-rollout-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.ops-closeout-rollout-smoke.result" in run_script


def test_ci_contains_export_ops_gate_smoke_job():
    """CI must include export-ops-gate-smoke job with tiered mode rollout and policy file."""
    jobs = _load_ci_jobs()
    assert "export-ops-gate-smoke" in jobs

    gate_job = jobs["export-ops-gate-smoke"]
    assert gate_job.get("name") == "Export Ops Gate Smoke"

    steps = gate_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act export gate" in joined_run
    assert '--mode "$GATE_MODE"' in joined_run
    assert "--policy config/export_ops_gate_policy.yaml" in joined_run

    step_payload = "\n".join(str(step) for step in steps if isinstance(step, dict))
    assert "github.event_name == 'pull_request' && 'observe' || 'enforce'" in step_payload


def test_ci_contains_collaboration_smoke_job():
    """CI must include collaboration-smoke job for team workflow contracts."""
    jobs = _load_ci_jobs()
    assert "collaboration-smoke" in jobs

    collaboration_job = jobs["collaboration-smoke"]
    assert collaboration_job.get("name") == "Collaboration Smoke"

    steps = collaboration_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act collaboration sync" in joined_run
    assert "ai-act collaboration update" in joined_run
    assert "ai-act collaboration list" in joined_run
    assert "ai-act collaboration summary" in joined_run


def test_ci_contains_collaboration_gate_smoke_job():
    """CI must include collaboration-gate-smoke job with PR observe / main-tag enforce rollout."""
    jobs = _load_ci_jobs()
    assert "collaboration-gate-smoke" in jobs

    gate_job = jobs["collaboration-gate-smoke"]
    assert gate_job.get("name") == "Collaboration Gate Smoke"

    steps = gate_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act collaboration gate" in joined_run
    assert "--policy config/collaboration_gate_policy.yaml" in joined_run
    assert "--stale-actionable-max 9999" in joined_run
    assert "--blocked-stale-max 9999" in joined_run
    assert "--review-stale-max 9999" in joined_run
    assert "--stale-after-hours 1" in joined_run
    assert "--blocked-stale-after-hours 1" in joined_run
    assert "--review-stale-after-hours 1" in joined_run
    assert (
        'if [[ "${{ github.event_name }}" != "pull_request" && "$IS_MAIN_OR_TAG" == "true" ]]; then'
        in joined_run
    )


def test_all_checks_treats_collaboration_smoke_as_required():
    """All-checks gate must evaluate collaboration-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "collaboration-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.collaboration-smoke.result" in run_script


def test_all_checks_treats_collaboration_gate_smoke_as_required():
    """All-checks gate must evaluate collaboration-gate-smoke result as required."""
    jobs = _load_ci_jobs()
    assert "all-checks" in jobs

    all_checks_job = jobs["all-checks"]
    needs = all_checks_job.get("needs", [])
    assert "collaboration-gate-smoke" in needs

    check_status_step = next(
        step for step in all_checks_job.get("steps", []) if step.get("name") == "Check status"
    )
    run_script = check_status_step.get("run", "")
    assert "needs.collaboration-gate-smoke.result" in run_script


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
    """Composite action should expose additive security and export-ops gate controls/outputs."""
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

    assert "export_ops_gate_mode" in inputs
    assert inputs["export_ops_gate_mode"].get("default") == "observe"
    assert "export_ops_gate_target" in inputs
    assert inputs["export_ops_gate_target"].get("default") == "jira"
    assert "export_ops_gate_policy_path" in inputs
    assert (
        inputs["export_ops_gate_policy_path"].get("default") == "config/export_ops_gate_policy.yaml"
    )
    assert "export_ops_ops_path" in inputs
    assert "export_ops_reconcile_log_path" in inputs

    assert "export_ops_gate_failed" in outputs
    assert "export_ops_gate_reason_codes" in outputs
    assert "export_ops_open_failures_count" in outputs
    assert "export_ops_drift_count" in outputs
    assert "export_ops_success_rate" in outputs
    assert "export_ops_gate_exit_code" in outputs
    assert "collaboration_path" in inputs
    assert inputs["collaboration_path"].get("default") == ".eu_ai_act/collaboration_tasks.jsonl"
    assert "collaboration_gate_mode" in inputs
    assert inputs["collaboration_gate_mode"].get("default") == "observe"
    assert "collaboration_gate_policy_path" in inputs
    assert (
        inputs["collaboration_gate_policy_path"].get("default")
        == "config/collaboration_gate_policy.yaml"
    )
    assert "handoff_governance_enabled" in inputs
    assert inputs["handoff_governance_enabled"].get("default") == "false"
    assert "handoff_governance_mode" in inputs
    assert inputs["handoff_governance_mode"].get("default") == "observe"
    assert "handoff_governance_policy_path" in inputs
    assert (
        inputs["handoff_governance_policy_path"].get("default")
        == "config/governance_handoff_policy.yaml"
    )
    assert "handoff_governance_export_target" in inputs
    assert "ops_closeout_enabled" in inputs
    assert inputs["ops_closeout_enabled"].get("default") == "false"
    assert "ops_closeout_mode" in inputs
    assert inputs["ops_closeout_mode"].get("default") == "observe"
    assert "ops_closeout_policy_path" in inputs
    assert inputs["ops_closeout_policy_path"].get("default") == "config/ops_closeout_policy.yaml"
    assert "ops_closeout_version" in inputs
    assert "ops_closeout_release_run_id" in inputs
    assert "ops_closeout_repo" in inputs
    assert "ops_closeout_pypi_project" in inputs
    assert "ops_closeout_rtd_url" in inputs
    assert "collaboration_open_count" in outputs
    assert "collaboration_in_review_count" in outputs
    assert "collaboration_blocked_count" in outputs
    assert "collaboration_done_count" in outputs
    assert "collaboration_unassigned_actionable_count" in outputs
    assert "collaboration_stale_actionable_count" in outputs
    assert "collaboration_blocked_stale_count" in outputs
    assert "collaboration_review_stale_count" in outputs
    assert "collaboration_gate_failed" in outputs
    assert "collaboration_gate_reason_codes" in outputs
    assert "handoff_governance_failed" in outputs
    assert "handoff_governance_reason_codes" in outputs
    assert "handoff_governance_failed_gates" in outputs
    assert "ops_closeout_failed" in outputs
    assert "ops_closeout_reason_codes" in outputs
    assert "ops_closeout_failed_checks" in outputs
    assert "ops_closeout_freshness_reason_codes" in outputs
    assert "ops_closeout_run_age_hours" in outputs
    assert "ops_closeout_release_age_hours" in outputs
    assert "ops_closeout_rtd_age_hours" in outputs
    assert "ops_closeout_waived_reason_codes" in outputs
    assert "ops_closeout_expired_waiver_reason_codes" in outputs


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
    assert "export_ops_gate_mode" in uses_payload
    assert "collaboration_open_count" in step_text
    assert "collaboration_review_stale_count" in step_text
    assert "handoff_governance_failed" in step_text
    assert "steps.collaborationgate.outcome" in step_text
    assert "collaboration_gate_mode" in uses_payload
    assert "collaboration_gate_policy_path" in uses_payload
    assert "handoff_governance_enabled" in uses_payload
    assert "handoff_governance_mode" in uses_payload
    assert "handoff_governance_policy_path" in uses_payload


def test_ops_closeout_daily_workflow_contract():
    """Daily ops closeout workflow must schedule at 09:00 UTC and run closeout automation."""
    payload = _load_ops_closeout_daily_payload()

    on_payload = payload.get("on", payload.get(True, {}))
    assert isinstance(on_payload, dict)
    schedule_payload = on_payload.get("schedule", [])
    assert isinstance(schedule_payload, list)
    assert any(item.get("cron") == "0 9 * * *" for item in schedule_payload if isinstance(item, dict))

    workflow_dispatch = on_payload.get("workflow_dispatch", {})
    assert isinstance(workflow_dispatch, dict)
    dispatch_inputs = workflow_dispatch.get("inputs", {})
    assert "mode" in dispatch_inputs
    assert dispatch_inputs["mode"].get("default") == "observe"
    assert "release_version" in dispatch_inputs
    assert "release_run_id" in dispatch_inputs

    jobs = payload.get("jobs", {})
    assert "ops-closeout-daily" in jobs
    daily_job = jobs["ops-closeout-daily"]
    assert daily_job.get("name") == "Ops Closeout Daily"

    steps = daily_job.get("steps", [])
    run_blocks = [step.get("run", "") for step in steps if isinstance(step, dict)]
    joined_run = "\n".join(run_blocks)
    assert "ai-act ops closeout" in joined_run
    assert "--policy config/ops_closeout_policy.yaml" in joined_run
    assert "--resolve-latest-release" in joined_run
    assert "--mode \"$MODE\"" in joined_run
    assert "ops_closeout_manifest.json" in joined_run

    uses_payload = "\n".join(
        str(step)
        for step in steps
        if isinstance(step, dict) and "uses" in step
    )
    assert "actions/upload-artifact@v4" in uses_payload
