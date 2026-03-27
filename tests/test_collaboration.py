"""Tests for collaboration task ledger sync/update/list flows."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from eu_ai_act.checker import (
    ComplianceFinding,
    ComplianceReport,
    ComplianceStatus,
    ComplianceSummary,
)
from eu_ai_act.collaboration import (
    list_collaboration_tasks,
    summarize_collaboration_gate_metrics,
    summarize_collaboration_tasks,
    sync_collaboration_tasks,
    update_collaboration_task,
)
from eu_ai_act.schema import RiskTier


def _make_report(
    *,
    system_name: str,
    findings: dict[str, ComplianceFinding],
    risk_tier: RiskTier = RiskTier.HIGH_RISK,
) -> ComplianceReport:
    return ComplianceReport(
        system_name=system_name,
        risk_tier=risk_tier,
        findings=findings,
        summary=ComplianceSummary(
            total_requirements=len(findings),
            compliant_count=sum(
                1 for finding in findings.values() if finding.status == ComplianceStatus.COMPLIANT
            ),
            non_compliant_count=sum(
                1
                for finding in findings.values()
                if finding.status == ComplianceStatus.NON_COMPLIANT
            ),
            partial_count=sum(
                1 for finding in findings.values() if finding.status == ComplianceStatus.PARTIAL
            ),
            not_assessed_count=sum(
                1
                for finding in findings.values()
                if finding.status == ComplianceStatus.NOT_ASSESSED
            ),
        ),
        audit_trail=[],
        generated_at="2026-03-24T10:00:00+00:00",
    )


def _finding(
    requirement_id: str, title: str, status: ComplianceStatus, severity: str
) -> ComplianceFinding:
    return ComplianceFinding(
        requirement_id=requirement_id,
        requirement_title=title,
        status=status,
        description=f"{title} description",
        gap_analysis="",
        remediation_steps=[],
        severity=severity,
    )


class TestCollaboration:
    def test_sync_create_reopen_and_auto_close(self, tmp_path):
        collab_path = tmp_path / "collaboration_tasks.jsonl"
        descriptor_path = tmp_path / "system.yaml"
        descriptor_path.write_text("name: mock\n", encoding="utf-8")

        initial_report = _make_report(
            system_name="System A",
            findings={
                "Art. 10": _finding(
                    "Art. 10", "Data governance", ComplianceStatus.NON_COMPLIANT, "HIGH"
                ),
                "Art. 11": _finding("Art. 11", "Documentation", ComplianceStatus.PARTIAL, "MEDIUM"),
            },
        )

        first_sync = sync_collaboration_tasks(
            report=initial_report,
            descriptor_path=str(descriptor_path),
            owner_default="alice",
            collab_path=collab_path,
            generated_at="2026-03-24T10:00:00+00:00",
        )
        assert first_sync["changes"]["created_count"] == 2
        assert first_sync["summary"]["open_count"] == 2
        assert first_sync["summary"]["done_count"] == 0

        art10_task_id = "System A::Art. 10"
        _, updated_task, changed = update_collaboration_task(
            task_id=art10_task_id,
            workflow_status="done",
            note_message="Reviewed by compliance team.",
            note_author="bob",
            collab_path=collab_path,
        )
        assert changed is True
        assert updated_task.workflow_status == "done"
        assert updated_task.owner == "alice"
        assert len(updated_task.notes) == 1

        second_report = _make_report(
            system_name="System A",
            findings={
                "Art. 10": _finding(
                    "Art. 10", "Data governance", ComplianceStatus.NON_COMPLIANT, "HIGH"
                ),
                "Art. 11": _finding(
                    "Art. 11", "Documentation", ComplianceStatus.COMPLIANT, "MEDIUM"
                ),
            },
        )
        second_sync = sync_collaboration_tasks(
            report=second_report,
            descriptor_path=str(descriptor_path),
            collab_path=collab_path,
            generated_at="2026-03-24T11:00:00+00:00",
        )
        assert second_sync["changes"]["created_count"] == 0
        assert second_sync["changes"]["reopened_count"] == 1
        assert second_sync["changes"]["auto_closed_count"] == 1
        assert second_sync["summary"]["open_count"] == 1
        assert second_sync["summary"]["done_count"] == 1

        _, tasks = list_collaboration_tasks(collab_path=collab_path)
        tasks_by_id = {task.task_id: task for task in tasks}
        assert tasks_by_id["System A::Art. 10"].workflow_status == "open"
        assert tasks_by_id["System A::Art. 10"].owner == "alice"
        assert len(tasks_by_id["System A::Art. 10"].notes) == 1
        assert tasks_by_id["System A::Art. 11"].workflow_status == "done"
        assert tasks_by_id["System A::Art. 11"].finding_status == "compliant"

    def test_list_summary_filters_and_limit(self, tmp_path):
        collab_path = tmp_path / "collaboration_tasks.jsonl"
        descriptor_path = tmp_path / "system.yaml"
        descriptor_path.write_text("name: mock\n", encoding="utf-8")

        sync_collaboration_tasks(
            report=_make_report(
                system_name="System A",
                findings={
                    "Art. 10": _finding(
                        "Art. 10", "Data governance", ComplianceStatus.NON_COMPLIANT, "HIGH"
                    ),
                    "Art. 43": _finding("Art. 43", "Conformity", ComplianceStatus.PARTIAL, "HIGH"),
                },
            ),
            descriptor_path=str(descriptor_path),
            owner_default="alice",
            collab_path=collab_path,
            generated_at="2026-03-24T10:00:00+00:00",
        )
        sync_collaboration_tasks(
            report=_make_report(
                system_name="System B",
                findings={
                    "Art. 50": _finding(
                        "Art. 50", "Disclosure", ComplianceStatus.NOT_ASSESSED, "MEDIUM"
                    ),
                },
                risk_tier=RiskTier.LIMITED,
            ),
            descriptor_path=str(descriptor_path),
            owner_default="carol",
            collab_path=collab_path,
            generated_at="2026-03-24T10:10:00+00:00",
        )
        update_collaboration_task(
            task_id="System A::Art. 10",
            workflow_status="in_review",
            collab_path=collab_path,
        )
        update_collaboration_task(
            task_id="System A::Art. 43",
            workflow_status="blocked",
            collab_path=collab_path,
        )

        _, in_review_tasks = list_collaboration_tasks(
            collab_path=collab_path,
            workflow_status="in_review",
        )
        assert len(in_review_tasks) == 1
        assert in_review_tasks[0].task_id == "System A::Art. 10"

        _, owner_tasks = list_collaboration_tasks(
            collab_path=collab_path,
            owner="alice",
            limit=1,
        )
        assert len(owner_tasks) == 1
        assert owner_tasks[0].owner == "alice"

        summary = summarize_collaboration_tasks(collab_path=collab_path, system_name="System A")
        assert summary["count"] == 2
        assert summary["in_review_count"] == 1
        assert summary["blocked_count"] == 1
        assert summary["open_count"] == 0

    def test_update_validation_errors(self, tmp_path):
        collab_path = tmp_path / "collaboration_tasks.jsonl"
        descriptor_path = tmp_path / "system.yaml"
        descriptor_path.write_text("name: mock\n", encoding="utf-8")
        sync_collaboration_tasks(
            report=_make_report(
                system_name="System A",
                findings={
                    "Art. 10": _finding(
                        "Art. 10", "Data governance", ComplianceStatus.NON_COMPLIANT, "HIGH"
                    )
                },
            ),
            descriptor_path=str(descriptor_path),
            collab_path=collab_path,
        )

        with pytest.raises(ValueError):
            update_collaboration_task(
                task_id="System A::Art. 10",
                note_author="alice",
                collab_path=collab_path,
            )

        with pytest.raises(KeyError):
            update_collaboration_task(
                task_id="missing-task-id",
                workflow_status="done",
                collab_path=collab_path,
            )

        with pytest.raises(ValueError):
            list_collaboration_tasks(collab_path=collab_path, limit=0)

    def test_gate_metrics_include_staleness_counts(self, tmp_path):
        collab_path = tmp_path / "collaboration_tasks.jsonl"
        entries = [
            {
                "task_id": "System A::Art. 10",
                "system_name": "System A",
                "descriptor_path": "/tmp/system.yaml",
                "requirement_id": "Art. 10",
                "article": "Art. 10",
                "title": "Data governance",
                "finding_status": "non_compliant",
                "severity": "HIGH",
                "workflow_status": "open",
                "owner": None,
                "notes": [],
                "created_at": "2026-03-24T08:00:00+00:00",
                "updated_at": "2026-03-24T08:00:00+00:00",
            },
            {
                "task_id": "System A::Art. 11",
                "system_name": "System A",
                "descriptor_path": "/tmp/system.yaml",
                "requirement_id": "Art. 11",
                "article": "Art. 11",
                "title": "Documentation",
                "finding_status": "partial",
                "severity": "MEDIUM",
                "workflow_status": "in_review",
                "owner": "alice",
                "notes": [],
                "created_at": "2026-03-24T11:00:00+00:00",
                "updated_at": "2026-03-24T11:00:00+00:00",
            },
            {
                "task_id": "System A::Art. 13",
                "system_name": "System A",
                "descriptor_path": "/tmp/system.yaml",
                "requirement_id": "Art. 13",
                "article": "Art. 13",
                "title": "Transparency",
                "finding_status": "not_assessed",
                "severity": "LOW",
                "workflow_status": "blocked",
                "owner": None,
                "notes": [],
                "created_at": "2026-03-24T09:30:00+00:00",
                "updated_at": "2026-03-24T09:30:00+00:00",
            },
        ]
        collab_path.write_text(
            "\n".join(json.dumps(entry, ensure_ascii=True) for entry in entries) + "\n",
            encoding="utf-8",
        )

        metrics = summarize_collaboration_gate_metrics(
            collab_path=collab_path,
            system_name="System A",
            stale_after_hours=2,
            blocked_stale_after_hours=1,
            reference_time=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
        )

        assert metrics["total_tasks"] == 3
        assert metrics["actionable_count"] == 3
        assert metrics["unassigned_actionable_count"] == 2
        assert metrics["stale_actionable_count"] == 2
        assert metrics["blocked_stale_count"] == 1
        assert metrics["stale_after_hours"] == 2.0
        assert metrics["blocked_stale_after_hours"] == 1.0
