"""Tests for Annex IV technical documentation coverage checker."""

import pytest
from eu_ai_act.annexes.annex_iv import (
    AnnexIVSection,
    AnnexIVFinding,
    check_annex_iv_completeness,
    annex_iv_coverage_summary,
)


def _full_doc() -> dict:
    return {
        "intended_purpose": "Fraud detection in online payments",
        "version": "1.0.0",
        "hardware_requirements": "x86-64, 16 GB RAM",
        "architecture": "Gradient-boosted trees + rule layer",
        "training_data": "Internal transaction logs 2020-2024",
        "design_choices": "Threshold calibrated for 1% FPR",
        "monitoring_plan": "Monthly drift report via Evidently",
        "performance_metrics": "AUC-ROC 0.95, F1 0.88",
        "robustness_measures": "Adversarial feature perturbation tests",
        "dataset_provenance": "Internal, GDPR Article 6(1)(b) lawful basis",
        "preprocessing_steps": "Normalisation, missing-value imputation",
        "bias_analysis": "Demographic parity gap < 2%",
        "risk_register": "FMEA table, 12 risks identified",
        "residual_risk_evaluation": "3 residual risks accepted by DPO",
        "change_log": "v1.0.1: retrained with Q1-2025 data",
        "post_market_impact_assessments": "Impact reassessment after each release",
        "harmonised_standards": "ISO/IEC 42001:2023",
        "deviation_justifications": "N/A — all requirements met",
        "declaration_of_conformity": "doc/eu-doc-conformity.pdf",
        "conformity_assessment_procedure": "Internal assessment per Art. 43(2)",
    }


def test_full_coverage():
    findings = check_annex_iv_completeness(_full_doc())
    assert all(f.covered for f in findings), [f for f in findings if not f.covered]
    summary = annex_iv_coverage_summary(findings)
    assert summary["coverage_pct"] == 100
    assert summary["critical_missing"] == []


def test_missing_section_detected():
    doc = _full_doc()
    del doc["risk_register"]
    del doc["residual_risk_evaluation"]
    findings = check_annex_iv_completeness(doc)
    risk_finding = next(f for f in findings if f.section == AnnexIVSection.RISK_MANAGEMENT)
    assert not risk_finding.covered
    assert "risk_register" in risk_finding.missing_fields
    assert risk_finding.severity == "CRITICAL"


def test_summary_critical_missing():
    doc = _full_doc()
    del doc["intended_purpose"]
    findings = check_annex_iv_completeness(doc)
    summary = annex_iv_coverage_summary(findings)
    assert AnnexIVSection.GENERAL_DESCRIPTION.value in summary["critical_missing"]
    assert summary["coverage_pct"] < 100


def test_empty_doc_all_missing():
    findings = check_annex_iv_completeness({})
    assert not any(f.covered for f in findings)
    summary = annex_iv_coverage_summary(findings)
    assert summary["coverage_pct"] == 0
    assert len(summary["critical_missing"]) > 0


def test_eight_sections_returned():
    findings = check_annex_iv_completeness(_full_doc())
    assert len(findings) == 8
    section_ids = {f.section for f in findings}
    assert section_ids == set(AnnexIVSection)
