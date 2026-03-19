"""
GPAI (General-Purpose AI) model obligation assessment.
"""

from dataclasses import dataclass

import yaml
from pydantic import BaseModel, Field

from eu_ai_act.checker import ComplianceStatus


@dataclass
class GPAIFinding:
    """Single GPAI compliance finding."""

    requirement_id: str
    status: ComplianceStatus
    severity: str
    title: str
    description: str
    gap_analysis: str
    recommendations: list[str]


class GPAIModelInfo(BaseModel):
    """Input model for GPAI-specific assessment."""

    model_name: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    training_compute_flops: float | None = None
    model_params_billion: float | None = None
    eu_monthly_users: int | None = None
    supports_tool_use: bool = False
    autonomous_task_execution: bool = False
    generates_synthetic_media: bool = False
    model_card_available: bool = False
    training_data_documented: bool = False
    systemic_risk_mitigation_plan: bool = False
    post_market_monitoring: bool = False


@dataclass
class GPAIAssessment:
    """Output model for GPAI obligation assessment."""

    systemic_risk_flag: bool
    findings: list[GPAIFinding]
    compliance_gaps: list[str]
    recommendations: list[str]


class GPAIAssessor:
    """Rule-based assessor for Art. 51-55 GPAI obligations."""

    COMPUTE_THRESHOLD = 1e25
    PARAMS_THRESHOLD_B = 30.0
    USERS_THRESHOLD = 10_000_000

    def assess(self, model_info: GPAIModelInfo) -> GPAIAssessment:
        """Assess a GPAI model against Articles 51-55 obligations."""
        systemic_risk_flag = self._is_systemic_risk(model_info)
        threshold_data_missing = model_info.training_compute_flops is None and (
            model_info.model_params_billion is None or model_info.eu_monthly_users is None
        )

        findings: list[GPAIFinding] = [
            self._assess_art51(model_info),
            self._assess_art52(model_info),
            self._assess_art53(model_info, systemic_risk_flag, threshold_data_missing),
            self._assess_art54(model_info, systemic_risk_flag),
            self._assess_art55(model_info),
        ]

        compliance_gaps = [
            f"[{finding.requirement_id}] {finding.gap_analysis}"
            for finding in findings
            if finding.status
            in {
                ComplianceStatus.NON_COMPLIANT,
                ComplianceStatus.PARTIAL,
                ComplianceStatus.NOT_ASSESSED,
            }
            and finding.gap_analysis
        ]
        recommendations: list[str] = []
        for finding in findings:
            recommendations.extend(finding.recommendations)
        recommendations = list(dict.fromkeys(recommendations))

        return GPAIAssessment(
            systemic_risk_flag=systemic_risk_flag,
            findings=findings,
            compliance_gaps=compliance_gaps,
            recommendations=recommendations,
        )

    def _is_systemic_risk(self, model_info: GPAIModelInfo) -> bool:
        """Apply deterministic systemic-risk rules."""
        if (
            model_info.training_compute_flops is not None
            and model_info.training_compute_flops >= self.COMPUTE_THRESHOLD
        ):
            return True

        if (
            model_info.model_params_billion is not None
            and model_info.model_params_billion >= self.PARAMS_THRESHOLD_B
            and model_info.eu_monthly_users is not None
            and model_info.eu_monthly_users >= self.USERS_THRESHOLD
        ):
            return True

        signals = sum(
            [
                1 if model_info.supports_tool_use else 0,
                1 if model_info.autonomous_task_execution else 0,
                1 if model_info.generates_synthetic_media else 0,
            ]
        )
        if signals >= 2:
            return True

        return False

    def _assess_art51(self, model_info: GPAIModelInfo) -> GPAIFinding:
        """Art. 51 - training data documentation."""
        if model_info.training_data_documented:
            status = ComplianceStatus.COMPLIANT
            gap = ""
            recommendations: list[str] = []
        else:
            status = ComplianceStatus.NON_COMPLIANT
            gap = "Training data documentation evidence is missing."
            recommendations = [
                "Document training data provenance, quality controls, and filtering steps."
            ]

        return GPAIFinding(
            requirement_id="Art. 51",
            status=status,
            severity="MEDIUM",
            title="Training data documentation",
            description="Assess whether training data documentation obligations are met.",
            gap_analysis=gap,
            recommendations=recommendations,
        )

    def _assess_art52(self, model_info: GPAIModelInfo) -> GPAIFinding:
        """Art. 52 - model card/capability documentation."""
        if model_info.model_card_available:
            status = ComplianceStatus.COMPLIANT
            gap = ""
            recommendations: list[str] = []
        else:
            status = ComplianceStatus.NON_COMPLIANT
            gap = "Model card or equivalent capability documentation is missing."
            recommendations = ["Publish and maintain a model card for downstream stakeholders."]

        return GPAIFinding(
            requirement_id="Art. 52",
            status=status,
            severity="MEDIUM",
            title="Model card completeness",
            description="Assess model card and capability disclosure requirements.",
            gap_analysis=gap,
            recommendations=recommendations,
        )

    def _assess_art53(
        self,
        model_info: GPAIModelInfo,
        systemic_risk_flag: bool,
        threshold_data_missing: bool,
    ) -> GPAIFinding:
        """Art. 53 - systemic risk assessment."""
        if threshold_data_missing and not systemic_risk_flag:
            status = ComplianceStatus.NOT_ASSESSED
            gap = "Systemic-risk threshold evidence is incomplete."
            recommendations = [
                "Provide compute, model size, and user-scale metrics for systemic risk determination.",
            ]
        elif systemic_risk_flag:
            if model_info.systemic_risk_mitigation_plan:
                status = ComplianceStatus.PARTIAL
                gap = "Systemic risk is flagged; mitigation exists but requires continuous validation."
                recommendations = [
                    "Operationalize periodic systemic-risk stress testing and governance review.",
                ]
            else:
                status = ComplianceStatus.NON_COMPLIANT
                gap = "Systemic risk is flagged without a mitigation plan."
                recommendations = ["Create and approve a systemic-risk mitigation plan."]
        else:
            status = ComplianceStatus.COMPLIANT
            gap = ""
            recommendations = []

        return GPAIFinding(
            requirement_id="Art. 53",
            status=status,
            severity="HIGH",
            title="Systemic risk assessment",
            description="Assess whether systemic-risk obligations are satisfied.",
            gap_analysis=gap,
            recommendations=recommendations,
        )

    def _assess_art54(self, model_info: GPAIModelInfo, systemic_risk_flag: bool) -> GPAIFinding:
        """Art. 54 - mitigation and monitoring."""
        if model_info.systemic_risk_mitigation_plan and model_info.post_market_monitoring:
            status = ComplianceStatus.COMPLIANT
            gap = ""
            recommendations: list[str] = []
        elif model_info.systemic_risk_mitigation_plan or model_info.post_market_monitoring:
            status = ComplianceStatus.PARTIAL
            gap = "Mitigation and post-market monitoring controls are partially implemented."
            recommendations = [
                "Complete both mitigation planning and post-market monitoring controls."
            ]
        elif systemic_risk_flag:
            status = ComplianceStatus.NON_COMPLIANT
            gap = "Systemic-risk model lacks mitigation and post-market monitoring controls."
            recommendations = [
                "Implement mitigation plan and post-market monitoring before deployment."
            ]
        else:
            status = ComplianceStatus.NOT_ASSESSED
            gap = "Insufficient mitigation/monitoring evidence for GPAI obligations."
            recommendations = ["Provide mitigation and monitoring artifacts."]

        return GPAIFinding(
            requirement_id="Art. 54",
            status=status,
            severity="HIGH",
            title="Risk mitigation measures",
            description="Assess mitigation and post-market monitoring obligations.",
            gap_analysis=gap,
            recommendations=recommendations,
        )

    def _assess_art55(self, model_info: GPAIModelInfo) -> GPAIFinding:
        """Art. 55 - downstream transparency for deployers."""
        if model_info.model_card_available and model_info.training_data_documented:
            status = ComplianceStatus.COMPLIANT
            gap = ""
            recommendations: list[str] = []
        elif model_info.model_card_available or model_info.training_data_documented:
            status = ComplianceStatus.PARTIAL
            gap = "Only part of downstream transparency information is available."
            recommendations = [
                "Provide both model card and training data transparency package for downstream users.",
            ]
        else:
            status = ComplianceStatus.NOT_ASSESSED
            gap = "Downstream transparency package is not evident."
            recommendations = ["Publish downstream transparency documentation for deployers."]

        return GPAIFinding(
            requirement_id="Art. 55",
            status=status,
            severity="MEDIUM",
            title="Downstream transparency information",
            description="Assess transparency information availability for downstream deployers.",
            gap_analysis=gap,
            recommendations=recommendations,
        )


def load_gpai_model_info_from_yaml(yaml_content: str) -> GPAIModelInfo:
    """Load GPAI model info from YAML string."""
    data = yaml.safe_load(yaml_content)
    return GPAIModelInfo(**data)


def load_gpai_model_info_from_file(filepath: str) -> GPAIModelInfo:
    """Load GPAI model info from YAML file."""
    with open(filepath, encoding="utf-8") as file:
        return load_gpai_model_info_from_yaml(file.read())
