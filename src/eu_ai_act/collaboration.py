"""Local-first collaboration task ledger for compliance findings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from eu_ai_act.checker import ComplianceReport

WorkflowStatus = Literal["open", "in_review", "blocked", "done"]

_WORKFLOW_STATUSES: set[str] = {"open", "in_review", "blocked", "done"}
_OPEN_WORKFLOW_STATUSES: set[str] = {"open", "in_review", "blocked"}
_ACTIONABLE_FINDING_STATUSES: set[str] = {"non_compliant", "partial", "not_assessed"}
_ALLOWED_FINDING_STATUSES: set[str] = {"compliant", "non_compliant", "partial", "not_assessed"}
_ALLOWED_SEVERITIES: set[str] = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _find_project_root(start_path: Path) -> Path | None:
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def resolve_collaboration_path(
    collab_path: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> Path:
    """Resolve explicit or default collaboration ledger path."""
    current_dir = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    path_input: str | Path | None = collab_path

    if path_input is None:
        env_path = os.getenv("EU_AI_ACT_COLLABORATION_PATH")
        if env_path:
            path_input = env_path

    if path_input is not None:
        candidate = Path(path_input).expanduser()
        if not candidate.is_absolute():
            candidate = (current_dir / candidate).resolve()
        return candidate

    project_root = _find_project_root(current_dir)
    base_dir = project_root if project_root else current_dir
    return base_dir / ".eu_ai_act" / "collaboration_tasks.jsonl"


def _normalize_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return normalized


def _normalize_optional_non_empty_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_non_empty_str(value, field_name)


def _normalize_workflow_status(value: Any) -> WorkflowStatus:
    normalized = _normalize_non_empty_str(value, "workflow_status")
    if normalized not in _WORKFLOW_STATUSES:
        raise ValueError("workflow_status must be one of: open, in_review, blocked, done.")
    return normalized  # type: ignore[return-value]


def _normalize_finding_status(value: Any) -> str:
    normalized = _normalize_non_empty_str(value, "finding_status")
    if normalized not in _ALLOWED_FINDING_STATUSES:
        raise ValueError(
            "finding_status must be one of: compliant, non_compliant, partial, not_assessed."
        )
    return normalized


def _normalize_severity(value: Any) -> str:
    normalized = _normalize_non_empty_str(value, "severity").upper()
    if normalized not in _ALLOWED_SEVERITIES:
        raise ValueError("severity must be one of: CRITICAL, HIGH, MEDIUM, LOW.")
    return normalized


@dataclass(frozen=True)
class CollaborationNote:
    """Immutable note attached to a collaboration task."""

    timestamp: str
    author: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "author": self.author,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> CollaborationNote:
        if not isinstance(payload, dict):
            raise ValueError("notes entries must be objects.")
        return cls(
            timestamp=_normalize_non_empty_str(payload.get("timestamp"), "notes.timestamp"),
            author=_normalize_non_empty_str(payload.get("author"), "notes.author"),
            message=_normalize_non_empty_str(payload.get("message"), "notes.message"),
        )


@dataclass(frozen=True)
class CollaborationTask:
    """Current snapshot of a collaboration task."""

    task_id: str
    system_name: str
    descriptor_path: str
    requirement_id: str
    article: str
    title: str
    finding_status: str
    severity: str
    workflow_status: WorkflowStatus
    owner: str | None
    notes: list[CollaborationNote] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "system_name": self.system_name,
            "descriptor_path": self.descriptor_path,
            "requirement_id": self.requirement_id,
            "article": self.article,
            "title": self.title,
            "finding_status": self.finding_status,
            "severity": self.severity,
            "workflow_status": self.workflow_status,
            "owner": self.owner,
            "notes": [note.to_dict() for note in self.notes],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> CollaborationTask:
        if not isinstance(payload, dict):
            raise ValueError("Collaboration task payload must be an object.")

        notes_payload = payload.get("notes", [])
        if not isinstance(notes_payload, list):
            raise ValueError("notes must be an array.")

        return cls(
            task_id=_normalize_non_empty_str(payload.get("task_id"), "task_id"),
            system_name=_normalize_non_empty_str(payload.get("system_name"), "system_name"),
            descriptor_path=_normalize_non_empty_str(
                payload.get("descriptor_path"), "descriptor_path"
            ),
            requirement_id=_normalize_non_empty_str(
                payload.get("requirement_id"), "requirement_id"
            ),
            article=_normalize_non_empty_str(payload.get("article"), "article"),
            title=_normalize_non_empty_str(payload.get("title"), "title"),
            finding_status=_normalize_finding_status(payload.get("finding_status")),
            severity=_normalize_severity(payload.get("severity")),
            workflow_status=_normalize_workflow_status(payload.get("workflow_status")),
            owner=_normalize_optional_non_empty_str(payload.get("owner"), "owner"),
            notes=[CollaborationNote.from_dict(note) for note in notes_payload],
            created_at=_normalize_non_empty_str(payload.get("created_at"), "created_at"),
            updated_at=_normalize_non_empty_str(payload.get("updated_at"), "updated_at"),
        )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _read_task_snapshots(collaboration_path: Path) -> list[CollaborationTask]:
    if not collaboration_path.exists():
        return []

    snapshots: list[CollaborationTask] = []
    with collaboration_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload_line = line.strip()
            if not payload_line:
                continue
            try:
                payload = json.loads(payload_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in collaboration ledger at line {line_number}: {exc.msg}"
                ) from exc
            try:
                snapshots.append(CollaborationTask.from_dict(payload))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid collaboration task snapshot at line {line_number}: {exc}"
                ) from exc
    return snapshots


def _load_latest_tasks(collaboration_path: Path) -> dict[str, CollaborationTask]:
    latest: dict[str, CollaborationTask] = {}
    for task in _read_task_snapshots(collaboration_path):
        latest[task.task_id] = task
    return latest


def _append_task_snapshot(collaboration_path: Path, task: CollaborationTask) -> None:
    collaboration_path.parent.mkdir(parents=True, exist_ok=True)
    with collaboration_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(task.to_dict(), ensure_ascii=True) + "\n")


def _make_task_id(system_name: str, requirement_id: str) -> str:
    return f"{system_name.strip()}::{requirement_id.strip()}"


def _derive_article(requirement_id: str) -> str:
    return requirement_id


def _sort_tasks(tasks: list[CollaborationTask]) -> list[CollaborationTask]:
    return sorted(
        tasks,
        key=lambda task: (
            _parse_iso_datetime(task.updated_at) or datetime.min.replace(tzinfo=UTC),
            task.task_id,
        ),
        reverse=True,
    )


def _build_summary(tasks: list[CollaborationTask]) -> dict[str, int]:
    return {
        "open_count": sum(1 for task in tasks if task.workflow_status == "open"),
        "in_review_count": sum(1 for task in tasks if task.workflow_status == "in_review"),
        "blocked_count": sum(1 for task in tasks if task.workflow_status == "blocked"),
        "done_count": sum(1 for task in tasks if task.workflow_status == "done"),
    }


def sync_collaboration_tasks(
    *,
    report: ComplianceReport,
    descriptor_path: str,
    owner_default: str | None = None,
    collab_path: str | Path | None = None,
    cwd: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Sync collaboration tasks from a compliance report."""
    timestamp = generated_at or _utc_now_iso()
    descriptor_abs_path = str(Path(descriptor_path).resolve())
    collaboration_path = resolve_collaboration_path(collab_path, cwd=cwd)
    latest_tasks = _load_latest_tasks(collaboration_path)

    owner_default_value: str | None = None
    if owner_default is not None:
        owner_default_value = _normalize_non_empty_str(owner_default, "owner_default")

    changed_tasks: list[CollaborationTask] = []
    created_count = 0
    updated_count = 0
    reopened_count = 0
    auto_closed_count = 0

    for requirement_id, finding in sorted(report.findings.items()):
        task_id = _make_task_id(report.system_name, requirement_id)
        article = _derive_article(requirement_id)
        finding_status = finding.status.value
        severity = _normalize_severity(finding.severity)
        existing = latest_tasks.get(task_id)

        if finding_status in _ACTIONABLE_FINDING_STATUSES:
            if existing is None:
                task = CollaborationTask(
                    task_id=task_id,
                    system_name=report.system_name,
                    descriptor_path=descriptor_abs_path,
                    requirement_id=requirement_id,
                    article=article,
                    title=finding.requirement_title,
                    finding_status=finding_status,
                    severity=severity,
                    workflow_status="open",
                    owner=owner_default_value,
                    notes=[],
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                latest_tasks[task_id] = task
                changed_tasks.append(task)
                created_count += 1
                continue

            workflow_status = existing.workflow_status
            reopened = False
            if existing.workflow_status == "done":
                workflow_status = "open"
                reopened = True

            updated_task = replace(
                existing,
                descriptor_path=descriptor_abs_path,
                requirement_id=requirement_id,
                article=article,
                title=finding.requirement_title,
                finding_status=finding_status,
                severity=severity,
                workflow_status=workflow_status,
                updated_at=timestamp,
            )

            if updated_task.to_dict() != existing.to_dict():
                latest_tasks[task_id] = updated_task
                changed_tasks.append(updated_task)
                updated_count += 1
                if reopened:
                    reopened_count += 1
            continue

        # Compliant findings only auto-close existing open tasks.
        if existing is None:
            continue

        workflow_status = existing.workflow_status
        auto_closed = False
        if existing.workflow_status in _OPEN_WORKFLOW_STATUSES:
            workflow_status = "done"
            auto_closed = True

        updated_task = replace(
            existing,
            descriptor_path=descriptor_abs_path,
            requirement_id=requirement_id,
            article=article,
            title=finding.requirement_title,
            finding_status=finding_status,
            severity=severity,
            workflow_status=workflow_status,
            updated_at=timestamp,
        )
        if updated_task.to_dict() != existing.to_dict():
            latest_tasks[task_id] = updated_task
            changed_tasks.append(updated_task)
            updated_count += 1
            if auto_closed:
                auto_closed_count += 1

    for task in changed_tasks:
        _append_task_snapshot(collaboration_path, task)

    all_tasks = _sort_tasks(list(latest_tasks.values()))
    system_tasks = [task for task in all_tasks if task.system_name == report.system_name]

    return {
        "generated_at": timestamp,
        "collaboration_path": str(collaboration_path),
        "system_name": report.system_name,
        "descriptor_path": descriptor_abs_path,
        "total_tasks": len(all_tasks),
        "system_task_count": len(system_tasks),
        "changes": {
            "created_count": created_count,
            "updated_count": updated_count,
            "reopened_count": reopened_count,
            "auto_closed_count": auto_closed_count,
        },
        "summary": _build_summary(all_tasks),
        "tasks": [task.to_dict() for task in system_tasks],
    }


def list_collaboration_tasks(
    *,
    collab_path: str | Path | None = None,
    cwd: str | Path | None = None,
    system_name: str | None = None,
    owner: str | None = None,
    workflow_status: WorkflowStatus | None = None,
    limit: int | None = None,
) -> tuple[Path, list[CollaborationTask]]:
    """List latest task snapshots with deterministic filtering."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1.")

    if workflow_status is not None and workflow_status not in _WORKFLOW_STATUSES:
        raise ValueError("workflow_status must be one of: open, in_review, blocked, done.")

    normalized_owner: str | None = None
    if owner is not None:
        normalized_owner = _normalize_non_empty_str(owner, "owner")

    collaboration_path = resolve_collaboration_path(collab_path, cwd=cwd)
    tasks = _sort_tasks(list(_load_latest_tasks(collaboration_path).values()))

    if system_name is not None:
        tasks = [task for task in tasks if task.system_name == system_name]
    if normalized_owner is not None:
        tasks = [task for task in tasks if task.owner == normalized_owner]
    if workflow_status is not None:
        tasks = [task for task in tasks if task.workflow_status == workflow_status]
    if limit is not None:
        tasks = tasks[:limit]
    return collaboration_path, tasks


def summarize_collaboration_tasks(
    *,
    collab_path: str | Path | None = None,
    cwd: str | Path | None = None,
    system_name: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """Return collaboration summary metrics for filtered task set."""
    collaboration_path, tasks = list_collaboration_tasks(
        collab_path=collab_path,
        cwd=cwd,
        system_name=system_name,
        owner=owner,
    )
    return {
        "generated_at": _utc_now_iso(),
        "collaboration_path": str(collaboration_path),
        "count": len(tasks),
        **_build_summary(tasks),
    }


def summarize_collaboration_gate_metrics(
    *,
    collab_path: str | Path | None = None,
    cwd: str | Path | None = None,
    system_name: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Summarize collaboration metrics required by governance gate evaluation."""
    collaboration_path, tasks = list_collaboration_tasks(
        collab_path=collab_path,
        cwd=cwd,
        system_name=system_name,
        limit=limit,
    )
    status_summary = _build_summary(tasks)
    actionable_count = sum(
        1 for task in tasks if task.finding_status in _ACTIONABLE_FINDING_STATUSES
    )
    unassigned_actionable_count = sum(
        1
        for task in tasks
        if task.finding_status in _ACTIONABLE_FINDING_STATUSES and task.owner is None
    )
    return {
        "generated_at": _utc_now_iso(),
        "collaboration_path": str(collaboration_path),
        "total_tasks": len(tasks),
        "actionable_count": actionable_count,
        "unassigned_actionable_count": unassigned_actionable_count,
        "has_collaboration_data": len(tasks) > 0,
        **status_summary,
    }


def update_collaboration_task(
    *,
    task_id: str,
    workflow_status: WorkflowStatus | None = None,
    owner: str | None = None,
    note_message: str | None = None,
    note_author: str | None = None,
    collab_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> tuple[Path, CollaborationTask, bool]:
    """Update task status/owner/notes and append a new snapshot if changed."""
    normalized_task_id = _normalize_non_empty_str(task_id, "task_id")
    collaboration_path = resolve_collaboration_path(collab_path, cwd=cwd)
    latest_tasks = _load_latest_tasks(collaboration_path)
    existing = latest_tasks.get(normalized_task_id)
    if existing is None:
        raise KeyError(f"Task not found: {normalized_task_id}")

    changed = False
    timestamp = _utc_now_iso()
    task = existing

    if workflow_status is not None:
        normalized_status = _normalize_workflow_status(workflow_status)
        if normalized_status != task.workflow_status:
            task = replace(task, workflow_status=normalized_status)
            changed = True

    if owner is not None:
        normalized_owner = _normalize_non_empty_str(owner, "owner")
        if normalized_owner != task.owner:
            task = replace(task, owner=normalized_owner)
            changed = True

    if note_message is not None:
        normalized_message = _normalize_non_empty_str(note_message, "note")
        author_value = (
            _normalize_non_empty_str(note_author, "note_author")
            if note_author is not None
            else "unknown"
        )
        notes = [
            *task.notes,
            CollaborationNote(timestamp=timestamp, author=author_value, message=normalized_message),
        ]
        task = replace(task, notes=notes)
        changed = True
    elif note_author is not None:
        raise ValueError("--note-author requires --note.")

    if not changed:
        return collaboration_path, existing, False

    updated_task = replace(task, updated_at=timestamp)
    _append_task_snapshot(collaboration_path, updated_task)
    return collaboration_path, updated_task, True


__all__ = [
    "CollaborationNote",
    "CollaborationTask",
    "WorkflowStatus",
    "list_collaboration_tasks",
    "resolve_collaboration_path",
    "summarize_collaboration_gate_metrics",
    "summarize_collaboration_tasks",
    "sync_collaboration_tasks",
    "update_collaboration_task",
]
