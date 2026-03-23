"""Contract tests for repository example descriptors."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from eu_ai_act.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


def _invoke_json(runner: CliRunner, args: list[str]) -> dict:
    """Invoke CLI command and parse JSON output."""
    result = runner.invoke(main, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_all_system_examples_validate_and_check_contract():
    """All system descriptor examples should validate and support classify/check contracts."""
    runner = CliRunner()
    system_examples = sorted(
        path for path in EXAMPLES_DIR.glob("*.yaml") if not path.name.startswith("gpai_model")
    )
    assert system_examples, "No system descriptor examples found"

    for descriptor in system_examples:
        validate_result = runner.invoke(main, ["validate", str(descriptor)])
        assert validate_result.exit_code == 0, f"{descriptor.name}: {validate_result.output}"

        classify_payload = _invoke_json(runner, ["classify", str(descriptor), "--json"])
        for key in ("system_name", "risk_tier", "articles_applicable", "confidence", "reasoning"):
            assert key in classify_payload, f"{descriptor.name}: missing classify key '{key}'"

        check_payload = _invoke_json(runner, ["check", str(descriptor), "--json"])
        assert "summary" in check_payload, f"{descriptor.name}: missing check summary"
        assert isinstance(
            check_payload["summary"], dict
        ), f"{descriptor.name}: invalid summary type"
        for key in (
            "total_requirements",
            "compliant_count",
            "non_compliant_count",
            "partial_count",
            "not_assessed_count",
            "compliance_percentage",
        ):
            assert (
                key in check_payload["summary"]
            ), f"{descriptor.name}: missing summary key '{key}'"


def test_phase20_new_system_examples_expected_contract():
    """New Phase 20 examples should satisfy explicit tier/article/summary expectations."""
    runner = CliRunner()

    cases = [
        {
            "file": "public_benefits_triage.yaml",
            "expected_tier": "high_risk",
            "required_article": "Art. 10",
            "summary_metric": "non_compliant_count",
            "min_value": 1,
        },
        {
            "file": "synthetic_media_campaign_assistant.yaml",
            "expected_tier": "limited",
            "required_article": "Art. 50",
            "summary_metric": "non_compliant_count",
            "min_value": 1,
        },
    ]

    for case in cases:
        descriptor = EXAMPLES_DIR / case["file"]
        classify_payload = _invoke_json(runner, ["classify", str(descriptor), "--json"])
        assert classify_payload["risk_tier"] == case["expected_tier"]
        assert case["required_article"] in classify_payload["articles_applicable"]

        check_payload = _invoke_json(runner, ["check", str(descriptor), "--json"])
        assert check_payload["summary"][case["summary_metric"]] >= case["min_value"]

    transparency_check = _invoke_json(
        runner,
        ["check", str(EXAMPLES_DIR / "synthetic_media_campaign_assistant.yaml"), "--json"],
    )
    assert transparency_check["findings"]["Art. 50"]["status"] == "non_compliant"


def test_all_gpai_examples_support_gpai_contract():
    """All GPAI example files should parse and produce deterministic GPAI payloads."""
    runner = CliRunner()
    gpai_examples = sorted(EXAMPLES_DIR.glob("gpai_model*.yaml"))
    assert gpai_examples, "No GPAI model examples found"

    for model in gpai_examples:
        payload = _invoke_json(runner, ["gpai", str(model), "--json"])
        for key in (
            "model_name",
            "provider",
            "systemic_risk_flag",
            "compliance_gaps",
            "recommendations",
            "findings",
        ):
            assert key in payload, f"{model.name}: missing gpai key '{key}'"


def test_gpai_unknown_thresholds_example_returns_art53_not_assessed():
    """Unknown threshold GPAI example should produce Art.53 not_assessed outcome."""
    runner = CliRunner()
    payload = _invoke_json(
        runner,
        ["gpai", str(EXAMPLES_DIR / "gpai_model_unknown_thresholds.yaml"), "--json"],
    )

    assert payload["systemic_risk_flag"] is False
    art53 = next(f for f in payload["findings"] if f["requirement_id"] == "Art. 53")
    assert art53["status"] == "not_assessed"
