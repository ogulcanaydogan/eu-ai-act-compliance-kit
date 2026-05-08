"""Annex IV — Technical Documentation section checker.

Article 11 of the EU AI Act requires providers of high-risk AI systems to draw
up technical documentation *before* placing the system on the market. Annex IV
specifies the mandatory sections. This module models those sections and validates
whether a provided descriptor covers each one.

Reference: Regulation (EU) 2024/1689, Annex IV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnnexIVSection(str, Enum):
    """Enumeration of the eight mandatory sections of Annex IV."""

    GENERAL_DESCRIPTION = "1"
    DETAILED_DESIGN = "2"
    MONITORING_EVALUATION = "3"
    DATASETS = "4"
    RISK_MANAGEMENT = "5"
    CHANGES_AFTER_MARKET = "6"
    STANDARDS_APPLIED = "7"
    EU_DECLARATION = "8"


# Human-readable labels and expected evidence fields per section.
_SECTION_METADATA: dict[AnnexIVSection, dict[str, Any]] = {
    AnnexIVSection.GENERAL_DESCRIPTION: {
        "title": "General description of the AI system",
        "description": "Intended purpose, version info, hardware/software requirements, user interaction description.",
        "evidence_fields": ["intended_purpose", "version", "hardware_requirements"],
        "severity": "CRITICAL",
    },
    AnnexIVSection.DETAILED_DESIGN: {
        "title": "Detailed description of elements and development process",
        "description": "Architecture, training data specifications, design choices, and the development process.",
        "evidence_fields": ["architecture", "training_data", "design_choices"],
        "severity": "HIGH",
    },
    AnnexIVSection.MONITORING_EVALUATION: {
        "title": "Monitoring, functioning and control of the AI system",
        "description": "Capabilities, limitations, metrics, expected accuracy, robustness, and cybersecurity measures.",
        "evidence_fields": ["monitoring_plan", "performance_metrics", "robustness_measures"],
        "severity": "HIGH",
    },
    AnnexIVSection.DATASETS: {
        "title": "Data and data governance",
        "description": "Training, validation, and test datasets: provenance, selection criteria, preprocessing, bias mitigations.",
        "evidence_fields": ["dataset_provenance", "preprocessing_steps", "bias_analysis"],
        "severity": "HIGH",
    },
    AnnexIVSection.RISK_MANAGEMENT: {
        "title": "Risk management system",
        "description": "Identification and analysis of known and foreseeable risks; residual risk evaluation.",
        "evidence_fields": ["risk_register", "residual_risk_evaluation"],
        "severity": "CRITICAL",
    },
    AnnexIVSection.CHANGES_AFTER_MARKET: {
        "title": "Description of changes post-market placement",
        "description": "Logging of changes made after initial market placement and their impact assessments.",
        "evidence_fields": ["change_log", "post_market_impact_assessments"],
        "severity": "MEDIUM",
    },
    AnnexIVSection.STANDARDS_APPLIED: {
        "title": "Relevant standards and specifications applied",
        "description": "Harmonised standards or common specifications referenced; deviation justifications.",
        "evidence_fields": ["harmonised_standards", "deviation_justifications"],
        "severity": "MEDIUM",
    },
    AnnexIVSection.EU_DECLARATION: {
        "title": "EU declaration of conformity",
        "description": "Copy of the EU declaration of conformity per Art. 47; reference to the conformity assessment procedure used.",
        "evidence_fields": ["declaration_of_conformity", "conformity_assessment_procedure"],
        "severity": "HIGH",
    },
}


@dataclass
class AnnexIVFinding:
    """Coverage result for a single Annex IV section."""

    section: AnnexIVSection
    title: str
    severity: str
    covered: bool
    missing_fields: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "COVERED" if self.covered else "MISSING"


def check_annex_iv_completeness(technical_doc: dict[str, Any]) -> list[AnnexIVFinding]:
    """Evaluate an Annex IV technical documentation dict against all eight sections.

    Args:
        technical_doc: Flat dict mapping field names to their content. Any truthy
            value for a field is treated as evidence that the field is present.
            Missing or falsy values are flagged as gaps.

    Returns:
        List of :class:`AnnexIVFinding` — one per section, ordered by section number.
    """
    findings: list[AnnexIVFinding] = []
    for section, meta in _SECTION_METADATA.items():
        evidence_fields: list[str] = meta["evidence_fields"]
        missing = [f for f in evidence_fields if not technical_doc.get(f)]
        findings.append(
            AnnexIVFinding(
                section=section,
                title=meta["title"],
                severity=meta["severity"],
                covered=len(missing) == 0,
                missing_fields=missing,
            )
        )
    return findings


def annex_iv_coverage_summary(findings: list[AnnexIVFinding]) -> dict[str, Any]:
    """Return a dict suitable for inclusion in compliance reports."""
    covered = sum(1 for f in findings if f.covered)
    return {
        "total_sections": len(findings),
        "covered_sections": covered,
        "coverage_pct": round(100 * covered / len(findings)) if findings else 0,
        "critical_missing": [f.section.value for f in findings if not f.covered and f.severity == "CRITICAL"],
        "findings": [
            {
                "section": f.section.value,
                "title": f.title,
                "status": f.status,
                "severity": f.severity,
                "missing_fields": f.missing_fields,
            }
            for f in findings
        ],
    }
