"""Tests for ComplianceChecklist.to_html rendering (populated + empty + fallbacks)."""

from eu_ai_act.checklist import ChecklistItem, ChecklistSummary, ComplianceChecklist
from eu_ai_act.schema import RiskTier


def _item(item_id: str, severity: str, gap: str = "") -> ChecklistItem:
    return ChecklistItem(
        id=item_id,
        title=f"Do {item_id}",
        article="Art. 43",
        severity=severity,
        deadline_months=6,
        status="non_compliant",
        description="desc",
        guidance="guide",
        success_criteria="criteria",
        gap_analysis=gap,
    )


def _checklist(items: list[ChecklistItem]) -> ComplianceChecklist:
    return ComplianceChecklist(
        system_name="Test System",
        risk_tier=RiskTier.HIGH_RISK,
        generated_at="2026-01-01T00:00:00Z",
        items=items,
        total_items=len(items),
        estimated_completion_hours=12.0,
        summary=ChecklistSummary(
            total_requirements=10,
            compliant_count=8,
            non_compliant_count=len(items),
            partial_count=0,
            not_assessed_count=0,
            actionable_count=len(items),
            compliance_percentage=80.0,
        ),
    )


def test_to_html_renders_rows_for_items() -> None:
    html = _checklist(
        [_item("REQ-1", "CRITICAL", gap="missing docs"), _item("REQ-2", "UNKNOWN")]
    ).to_html()

    assert "<!DOCTYPE html>" in html
    assert "Test System" in html
    assert "HIGH_RISK" in html
    assert "REQ-1" in html and "REQ-2" in html
    assert "#b71c1c" in html  # CRITICAL severity color
    assert "#333" in html  # fallback color for an unknown severity
    assert "missing docs" in html
    assert "<table" in html


def test_to_html_renders_gap_placeholder_when_gap_empty() -> None:
    html = _checklist([_item("REQ-1", "HIGH")]).to_html()

    # gap_analysis is "" -> rendered as a "-" placeholder cell.
    assert "<td>-</td>" in html


def test_to_html_empty_checklist_shows_no_items_message() -> None:
    html = _checklist([]).to_html()

    assert "No actionable checklist items identified." in html
    assert "<table" not in html
