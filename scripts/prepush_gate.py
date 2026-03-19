#!/usr/bin/env python3
"""Pre-push compliance gate for changed AI system descriptors."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import yaml


DESCRIPTOR_KEYS = {
    "name",
    "description",
    "use_cases",
    "data_practices",
    "human_oversight",
    "training_data_source",
}
DESCRIPTOR_HINT_KEYS = (
    "use_cases:",
    "data_practices:",
    "human_oversight:",
    "training_data_source:",
)


@dataclass(frozen=True)
class GateEvaluation:
    """Result of running the local gate for one descriptor."""

    path: Path
    passed: bool
    risk_tier: str | None
    non_compliant_count: int | None
    reason: str


CommandRunner = Callable[[str, Path, Path], subprocess.CompletedProcess[str]]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(raw_path: str, repo_root: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _is_yaml_file(path: Path) -> bool:
    return path.suffix.lower() in {".yaml", ".yml"}


def _text_looks_like_descriptor(text: str) -> bool:
    return sum(1 for marker in DESCRIPTOR_HINT_KEYS if marker in text) >= 2


def is_descriptor_candidate(path: Path) -> bool:
    """Return True when file looks like an AI system descriptor YAML."""
    if not path.exists() or not path.is_file() or not _is_yaml_file(path):
        return False

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return False

    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError:
        return _text_looks_like_descriptor(raw_text)

    if not isinstance(payload, dict):
        return False

    return DESCRIPTOR_KEYS.issubset(payload.keys())


def _pythonpath_with_src(repo_root: Path) -> str:
    src_path = str(repo_root / "src")
    current = os.environ.get("PYTHONPATH", "")
    if not current:
        return src_path
    return f"{src_path}{os.pathsep}{current}"


def run_cli_command(step: str, descriptor_path: Path, repo_root: Path) -> subprocess.CompletedProcess[str]:
    """Run one CLI step for a descriptor and capture output."""
    args = [sys.executable, "-m", "eu_ai_act.cli", step, str(descriptor_path)]
    if step in {"classify", "check"}:
        args.append("--json")

    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath_with_src(repo_root)
    return subprocess.run(args, cwd=repo_root, capture_output=True, text=True, env=env, check=False)


def _extract_json_payload(command_output: str) -> dict:
    json_start = command_output.find("{")
    if json_start < 0:
        raise ValueError("no JSON object found in command output")
    try:
        return json.loads(command_output[json_start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON output: {exc}") from exc


def _policy_failure_reason(risk_tier: str, non_compliant_count: int) -> str | None:
    if risk_tier == "unacceptable":
        return "risk_tier is unacceptable (always fail)"
    if risk_tier == "high_risk" and non_compliant_count > 0:
        return (
            "risk_tier is high_risk and non_compliant_count > 0 "
            "(fails when fail_on_high_risk=true)"
        )
    return None


def _best_command_error_output(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or "").strip() or (result.stdout or "").strip()
    if output:
        return output
    return "no output captured"


def _relative_display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def evaluate_descriptor(
    descriptor_path: Path,
    repo_root: Path,
    command_runner: CommandRunner,
) -> GateEvaluation:
    """Run validate -> classify -> check for a descriptor and apply gate policy."""
    validate_result = command_runner("validate", descriptor_path, repo_root)
    if validate_result.returncode != 0:
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=None,
            non_compliant_count=None,
            reason=f"validate failed: {_best_command_error_output(validate_result)}",
        )

    classify_result = command_runner("classify", descriptor_path, repo_root)
    if classify_result.returncode != 0:
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=None,
            non_compliant_count=None,
            reason=f"classify failed: {_best_command_error_output(classify_result)}",
        )

    try:
        classify_payload = _extract_json_payload(classify_result.stdout)
    except ValueError as exc:
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=None,
            non_compliant_count=None,
            reason=f"failed to parse classify JSON: {exc}",
        )

    risk_tier = classify_payload.get("risk_tier")
    if not isinstance(risk_tier, str) or not risk_tier:
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=None,
            non_compliant_count=None,
            reason="classify JSON missing string field 'risk_tier'",
        )

    check_result = command_runner("check", descriptor_path, repo_root)
    if check_result.returncode != 0:
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=risk_tier,
            non_compliant_count=None,
            reason=f"check failed: {_best_command_error_output(check_result)}",
        )

    try:
        check_payload = _extract_json_payload(check_result.stdout)
    except ValueError as exc:
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=risk_tier,
            non_compliant_count=None,
            reason=f"failed to parse check JSON: {exc}",
        )

    summary = check_payload.get("summary")
    if not isinstance(summary, dict):
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=risk_tier,
            non_compliant_count=None,
            reason="check JSON missing 'summary' object",
        )

    non_compliant_count = summary.get("non_compliant_count")
    if not isinstance(non_compliant_count, int):
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=risk_tier,
            non_compliant_count=None,
            reason="check summary missing integer 'non_compliant_count'",
        )

    failure_reason = _policy_failure_reason(risk_tier, non_compliant_count)
    if failure_reason:
        return GateEvaluation(
            path=descriptor_path,
            passed=False,
            risk_tier=risk_tier,
            non_compliant_count=non_compliant_count,
            reason=failure_reason,
        )

    return GateEvaluation(
        path=descriptor_path,
        passed=True,
        risk_tier=risk_tier,
        non_compliant_count=non_compliant_count,
        reason="pass",
    )


def _descriptor_candidates(changed_files: Iterable[str], repo_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for raw in changed_files:
        resolved = _resolve_path(raw, repo_root)
        if not _is_yaml_file(resolved):
            continue
        if is_descriptor_candidate(resolved):
            candidates.append(resolved)
    return sorted(set(candidates))


def run_gate(
    changed_files: Sequence[str],
    command_runner: CommandRunner = run_cli_command,
    repo_root: Path | None = None,
) -> int:
    """Run local pre-push gate for changed files and return process exit code."""
    resolved_repo_root = repo_root or _repo_root()
    descriptors = _descriptor_candidates(changed_files, resolved_repo_root)

    if not descriptors:
        print("No changed AI descriptors detected; skipping pre-push compliance gate.")
        return 0

    print(f"Running AI descriptor pre-push gate for {len(descriptors)} file(s).")
    has_failure = False
    for descriptor_path in descriptors:
        evaluation = evaluate_descriptor(descriptor_path, resolved_repo_root, command_runner)
        display_path = _relative_display_path(descriptor_path, resolved_repo_root)
        if evaluation.passed:
            print(
                f"[PASS] {display_path} | "
                f"risk_tier={evaluation.risk_tier} "
                f"non_compliant_count={evaluation.non_compliant_count}"
            )
            continue

        has_failure = True
        print(
            f"[FAIL] {display_path} | "
            f"risk_tier={evaluation.risk_tier or '-'} "
            f"non_compliant_count={evaluation.non_compliant_count if evaluation.non_compliant_count is not None else '-'}"
        )
        print(f"       reason: {evaluation.reason}")

    return 1 if has_failure else 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used by pre-commit pre-push hook."""
    args = list(sys.argv[1:] if argv is None else argv)
    return run_gate(args)


if __name__ == "__main__":
    raise SystemExit(main())
