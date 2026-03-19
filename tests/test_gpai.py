"""Tests for GPAI assessment logic."""

from eu_ai_act.checker import ComplianceStatus
from eu_ai_act.gpai import GPAIAssessor, GPAIModelInfo


class TestGPAIAssessor:
    """Coverage for rule-based systemic-risk and obligation checks."""

    def test_systemic_risk_flagged_by_compute_threshold(self):
        """Models above compute threshold should set systemic risk flag."""
        model = GPAIModelInfo(
            model_name="XL Foundation",
            provider="ExampleAI",
            training_compute_flops=1.1e25,
            model_params_billion=20,
            eu_monthly_users=2_000_000,
            supports_tool_use=False,
            autonomous_task_execution=False,
            generates_synthetic_media=False,
            model_card_available=True,
            training_data_documented=True,
            systemic_risk_mitigation_plan=False,
            post_market_monitoring=False,
        )
        assessment = GPAIAssessor().assess(model)
        assert assessment.systemic_risk_flag is True
        art53 = next(f for f in assessment.findings if f.requirement_id == "Art. 53")
        assert art53.status in {ComplianceStatus.NON_COMPLIANT, ComplianceStatus.PARTIAL}

    def test_systemic_risk_flagged_by_capability_signal_combo(self):
        """At least two capability signals should trigger systemic risk."""
        model = GPAIModelInfo(
            model_name="Agentic Model",
            provider="ExampleAI",
            supports_tool_use=True,
            autonomous_task_execution=True,
            generates_synthetic_media=False,
            model_card_available=True,
            training_data_documented=True,
            systemic_risk_mitigation_plan=True,
            post_market_monitoring=True,
        )
        assessment = GPAIAssessor().assess(model)
        assert assessment.systemic_risk_flag is True

    def test_not_assessed_when_threshold_fields_missing(self):
        """Missing threshold fields should produce Art.53 not_assessed when no trigger exists."""
        model = GPAIModelInfo(
            model_name="Small Model",
            provider="ExampleAI",
            supports_tool_use=False,
            autonomous_task_execution=False,
            generates_synthetic_media=False,
            model_card_available=True,
            training_data_documented=True,
            systemic_risk_mitigation_plan=True,
            post_market_monitoring=True,
        )
        assessment = GPAIAssessor().assess(model)
        art53 = next(f for f in assessment.findings if f.requirement_id == "Art. 53")
        assert assessment.systemic_risk_flag is False
        assert art53.status == ComplianceStatus.NOT_ASSESSED
