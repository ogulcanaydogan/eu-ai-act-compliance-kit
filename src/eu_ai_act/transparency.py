"""
Transparency obligations checker for EU AI Act Art. 50 and GPAI-related duties.
"""

from dataclasses import dataclass
from typing import List

from eu_ai_act.checker import ComplianceStatus
from eu_ai_act.schema import AISystemDescriptor, UseCaseDomain


@dataclass
class TransparencyFinding:
    """Finding for transparency and GPAI obligations."""

    requirement_id: str
    status: ComplianceStatus
    severity: str
    title: str
    description: str
    gap_analysis: str
    recommendations: List[str]


class TransparencyChecker:
    """Evaluates transparency obligations under Art. 50 and GPAI Articles 51-55."""

    GENERATED_CONTENT_KEYWORDS = [
        "generated",
        "generative",
        "synthetic",
        "chatbot",
        "text generation",
        "ai-generated",
        "ai generated",
    ]
    DEEPFAKE_KEYWORDS = ["deepfake", "face swap", "voice clone", "synthetic media"]
    DISCLOSURE_KEYWORDS = ["disclos", "inform", "transparent", "label", "notice", "ai-generated"]
    GPAI_SIGNAL_KEYWORDS = [
        "general purpose",
        "foundation model",
        "large language",
        "multimodal",
        "broad training",
    ]

    def check_art50_disclosure(self, descriptor: AISystemDescriptor) -> List[TransparencyFinding]:
        """
        Check Art. 50 disclosure obligations.

        Returns a single finding wrapped in a list for consistency with other
        transparency methods.
        """
        text = self._descriptor_text(descriptor)
        has_generated_content = self._contains_any(text, self.GENERATED_CONTENT_KEYWORDS)
        has_disclosure = self._contains_any(text, self.DISCLOSURE_KEYWORDS)

        if has_generated_content and has_disclosure:
            finding = TransparencyFinding(
                requirement_id="Art. 50",
                status=ComplianceStatus.COMPLIANT,
                severity="MEDIUM",
                title="AI-generated content disclosure",
                description="System appears to disclose AI-generated or synthetic content to users.",
                gap_analysis="",
                recommendations=[],
            )
        elif has_generated_content:
            finding = TransparencyFinding(
                requirement_id="Art. 50",
                status=ComplianceStatus.NON_COMPLIANT,
                severity="MEDIUM",
                title="AI-generated content disclosure",
                description="Generated or synthetic content was detected without clear disclosure evidence.",
                gap_analysis="User-facing disclosure for AI-generated content is missing or insufficient.",
                recommendations=[
                    "Add explicit user notices where generated content is shown.",
                    "Document disclosure language in policy and product copy.",
                ],
            )
        else:
            finding = TransparencyFinding(
                requirement_id="Art. 50",
                status=ComplianceStatus.NOT_ASSESSED,
                severity="LOW",
                title="AI-generated content disclosure",
                description="Unable to confirm Art. 50 applicability from provided descriptor signals.",
                gap_analysis="No clear generated-content signal was found.",
                recommendations=[
                    "Confirm whether the system outputs generated or synthetic content to users.",
                ],
            )

        return [finding]

    def check_deepfake_detection(self, descriptor: AISystemDescriptor) -> TransparencyFinding:
        """Check deepfake/synthetic media disclosure and detection obligations."""
        text = self._descriptor_text(descriptor)
        has_deepfake_signal = self._contains_any(text, self.DEEPFAKE_KEYWORDS)
        has_disclosure = self._contains_any(text, self.DISCLOSURE_KEYWORDS)

        if has_deepfake_signal and has_disclosure:
            return TransparencyFinding(
                requirement_id="Art. 50",
                status=ComplianceStatus.PARTIAL,
                severity="HIGH",
                title="Deepfake/synthetic media safeguards",
                description="Deepfake or synthetic media signals detected with partial disclosure evidence.",
                gap_analysis="Disclosure exists but robust detection/labeling controls are not fully evidenced.",
                recommendations=[
                    "Implement deterministic labeling for synthetic media outputs.",
                    "Define review and incident escalation for manipulated media misuse.",
                ],
            )
        if has_deepfake_signal:
            return TransparencyFinding(
                requirement_id="Art. 50",
                status=ComplianceStatus.NON_COMPLIANT,
                severity="HIGH",
                title="Deepfake/synthetic media safeguards",
                description="Deepfake or synthetic media usage detected without sufficient safeguards.",
                gap_analysis="Disclosure and control measures for manipulated media are missing.",
                recommendations=[
                    "Add visible disclosure for synthetic media.",
                    "Establish detection and abuse-reporting controls.",
                ],
            )

        return TransparencyFinding(
            requirement_id="Art. 50",
            status=ComplianceStatus.NOT_ASSESSED,
            severity="LOW",
            title="Deepfake/synthetic media safeguards",
            description="No deepfake signal found; requirement applicability not confirmed.",
            gap_analysis="No clear deepfake/synthetic media indicators in descriptor.",
            recommendations=[
                "Confirm whether deepfake or synthetic media capability exists in deployed features.",
            ],
        )

    def check_gpai_obligations(self, descriptor: AISystemDescriptor) -> List[TransparencyFinding]:
        """Check GPAI obligations (Art. 51-55) when GPAI signals are present."""
        if not self._is_gpai_signal(descriptor):
            return []

        findings: List[TransparencyFinding] = []
        text = self._descriptor_text(descriptor)
        has_model_card = "model card" in text
        has_systemic_risk_wording = "systemic risk" in text
        has_disclosure = self._contains_any(text, self.DISCLOSURE_KEYWORDS)

        # Art. 51 - training data documentation
        if descriptor.documentation and len(descriptor.training_data_source.strip()) >= 30:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 51",
                    status=ComplianceStatus.COMPLIANT,
                    severity="MEDIUM",
                    title="Training data documentation",
                    description="Training data documentation evidence is present.",
                    gap_analysis="",
                    recommendations=[],
                )
            )
        elif descriptor.documentation:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 51",
                    status=ComplianceStatus.PARTIAL,
                    severity="MEDIUM",
                    title="Training data documentation",
                    description="Documentation exists but training data detail appears incomplete.",
                    gap_analysis="Training data lineage and quality controls are only partially described.",
                    recommendations=[
                        "Add provenance, filtering, and quality governance details for training data.",
                    ],
                )
            )
        else:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 51",
                    status=ComplianceStatus.NON_COMPLIANT,
                    severity="HIGH",
                    title="Training data documentation",
                    description="No sufficient evidence of training data documentation.",
                    gap_analysis="Documentation controls are missing for GPAI obligations.",
                    recommendations=[
                        "Create training data documentation aligned with Art. 51 expectations.",
                    ],
                )
            )

        # Art. 52 - model card and capability documentation
        if has_model_card:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 52",
                    status=ComplianceStatus.COMPLIANT,
                    severity="MEDIUM",
                    title="Model card completeness",
                    description="Model card evidence is present.",
                    gap_analysis="",
                    recommendations=[],
                )
            )
        elif descriptor.documentation:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 52",
                    status=ComplianceStatus.PARTIAL,
                    severity="MEDIUM",
                    title="Model card completeness",
                    description="General documentation exists but explicit model card evidence is missing.",
                    gap_analysis="Model card artifacts are not explicitly referenced.",
                    recommendations=[
                        "Publish a model card covering intended use, limits, and known risks.",
                    ],
                )
            )
        else:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 52",
                    status=ComplianceStatus.NON_COMPLIANT,
                    severity="HIGH",
                    title="Model card completeness",
                    description="No model card/capability documentation evidence detected.",
                    gap_analysis="GPAI model card obligations are not met.",
                    recommendations=[
                        "Create and maintain a model card aligned with Art. 52.",
                    ],
                )
            )

        # Art. 53 - systemic risk evaluation signals
        if has_systemic_risk_wording and descriptor.performance_monitoring:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 53",
                    status=ComplianceStatus.PARTIAL,
                    severity="HIGH",
                    title="Systemic risk evaluation",
                    description="Some systemic risk consideration exists with monitoring signals.",
                    gap_analysis="Formal systemic risk evaluation methodology is not fully evidenced.",
                    recommendations=[
                        "Define explicit systemic risk scoring and governance workflow.",
                    ],
                )
            )
        else:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 53",
                    status=ComplianceStatus.NOT_ASSESSED,
                    severity="HIGH",
                    title="Systemic risk evaluation",
                    description="Insufficient evidence to confirm systemic risk assessment posture.",
                    gap_analysis="No explicit systemic risk evaluation artifacts were found.",
                    recommendations=[
                        "Add systemic risk assessment criteria and review cadence.",
                    ],
                )
            )

        # Art. 54 - mitigation controls
        if descriptor.incident_procedure and descriptor.performance_monitoring:
            status = ComplianceStatus.COMPLIANT
            gap = ""
            recommendations: List[str] = []
        elif descriptor.incident_procedure or descriptor.performance_monitoring:
            status = ComplianceStatus.PARTIAL
            gap = "Mitigation controls exist but are incomplete for GPAI lifecycle risks."
            recommendations = ["Complete incident + monitoring control coverage for GPAI risks."]
        else:
            status = ComplianceStatus.NON_COMPLIANT
            gap = "No clear mitigation controls were found for GPAI systemic risks."
            recommendations = ["Implement incident response and post-market monitoring controls."]

        findings.append(
            TransparencyFinding(
                requirement_id="Art. 54",
                status=status,
                severity="HIGH",
                title="Risk mitigation measures",
                description="GPAI mitigation and operational control maturity assessment.",
                gap_analysis=gap,
                recommendations=recommendations,
            )
        )

        # Art. 55 - downstream transparency
        if has_disclosure and descriptor.documentation:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 55",
                    status=ComplianceStatus.COMPLIANT,
                    severity="MEDIUM",
                    title="Downstream transparency information",
                    description="Transparency information for downstream users appears present.",
                    gap_analysis="",
                    recommendations=[],
                )
            )
        elif descriptor.documentation:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 55",
                    status=ComplianceStatus.PARTIAL,
                    severity="MEDIUM",
                    title="Downstream transparency information",
                    description="Documentation exists but downstream-facing transparency detail is incomplete.",
                    gap_analysis="Insufficient downstream transparency wording was found.",
                    recommendations=[
                        "Add explicit downstream transparency obligations and usage constraints.",
                    ],
                )
            )
        else:
            findings.append(
                TransparencyFinding(
                    requirement_id="Art. 55",
                    status=ComplianceStatus.NOT_ASSESSED,
                    severity="MEDIUM",
                    title="Downstream transparency information",
                    description="Unable to verify downstream transparency posture.",
                    gap_analysis="No explicit downstream transparency documentation found.",
                    recommendations=[
                        "Provide downstream transparency and acceptable-use documentation.",
                    ],
                )
            )

        return findings

    def _is_gpai_signal(self, descriptor: AISystemDescriptor) -> bool:
        """Detect whether descriptor suggests GPAI characteristics."""
        if any(use_case.domain == UseCaseDomain.GENERAL_PURPOSE for use_case in descriptor.use_cases):
            return True
        return self._contains_any(self._descriptor_text(descriptor), self.GPAI_SIGNAL_KEYWORDS)

    def _descriptor_text(self, descriptor: AISystemDescriptor) -> str:
        """Build normalized text corpus from descriptor."""
        incident = descriptor.incident_procedure or ""
        parts = [
            descriptor.name,
            descriptor.description,
            descriptor.training_data_source,
            incident,
            " ".join(use_case.description for use_case in descriptor.use_cases),
        ]
        return " ".join(parts).lower()

    def _contains_any(self, text: str, keywords: List[str]) -> bool:
        """Simple keyword-match helper."""
        return any(keyword in text for keyword in keywords)
