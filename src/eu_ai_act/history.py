"""Audit history storage and diff utilities."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

EventType = Literal["check", "report"]

SUMMARY_FIELDS = (
    "total_requirements",
    "compliant_count",
    "non_compliant_count",
    "partial_count",
    "not_assessed_count",
    "compliance_percentage",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Summary field '{field_name}' must be an integer.")
    return int(value)


def _normalize_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Summary field '{field_name}' must be numeric.")
    return float(value)


def _normalize_summary(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        raise ValueError("Summary must be an object.")

    normalized: dict[str, Any] = {}
    for field_name in SUMMARY_FIELDS:
        if field_name not in summary:
            raise ValueError(f"Summary is missing required field '{field_name}'.")
        if field_name == "compliance_percentage":
            normalized[field_name] = _normalize_float(summary[field_name], field_name)
        else:
            normalized[field_name] = _normalize_int(summary[field_name], field_name)
    return normalized


def _normalize_finding_statuses(finding_statuses: Any) -> dict[str, str]:
    if not isinstance(finding_statuses, dict):
        raise ValueError("Finding statuses must be an object.")

    normalized: dict[str, str] = {}
    for requirement_id, status in finding_statuses.items():
        if not isinstance(requirement_id, str) or not requirement_id:
            raise ValueError("Finding status keys must be non-empty strings.")
        if not isinstance(status, str) or not status:
            raise ValueError("Finding status values must be non-empty strings.")
        normalized[requirement_id] = status
    return normalized


@dataclass(frozen=True)
class HistoryEvent:
    """Serializable event model persisted to JSONL history."""

    event_id: str
    event_type: EventType
    generated_at: str
    system_name: str
    descriptor_path: str
    risk_tier: str
    summary: dict[str, Any]
    finding_statuses: dict[str, str]
    report_format: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "generated_at": self.generated_at,
            "system_name": self.system_name,
            "descriptor_path": self.descriptor_path,
            "risk_tier": self.risk_tier,
            "summary": dict(self.summary),
            "finding_statuses": dict(self.finding_statuses),
        }
        if self.report_format:
            payload["report_format"] = self.report_format
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HistoryEvent:
        if not isinstance(payload, dict):
            raise ValueError("History event payload must be an object.")

        event_type = payload.get("event_type")
        if event_type not in {"check", "report"}:
            raise ValueError("event_type must be 'check' or 'report'.")

        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id must be a non-empty string.")

        generated_at = payload.get("generated_at")
        if not isinstance(generated_at, str) or not generated_at:
            raise ValueError("generated_at must be a non-empty string.")

        system_name = payload.get("system_name")
        if not isinstance(system_name, str) or not system_name:
            raise ValueError("system_name must be a non-empty string.")

        descriptor_path = payload.get("descriptor_path")
        if not isinstance(descriptor_path, str) or not descriptor_path:
            raise ValueError("descriptor_path must be a non-empty string.")

        risk_tier = payload.get("risk_tier")
        if not isinstance(risk_tier, str) or not risk_tier:
            raise ValueError("risk_tier must be a non-empty string.")

        summary = _normalize_summary(payload.get("summary"))
        finding_statuses = _normalize_finding_statuses(payload.get("finding_statuses"))

        report_format = payload.get("report_format")
        if report_format is not None and (not isinstance(report_format, str) or not report_format):
            raise ValueError("report_format must be null or a non-empty string.")

        return cls(
            event_id=event_id,
            event_type=event_type,
            generated_at=generated_at,
            system_name=system_name,
            descriptor_path=descriptor_path,
            risk_tier=risk_tier,
            summary=summary,
            finding_statuses=finding_statuses,
            report_format=report_format,
        )


def build_event(
    *,
    event_type: EventType,
    system_name: str,
    descriptor_path: str,
    risk_tier: str,
    summary: dict[str, Any],
    finding_statuses: dict[str, str],
    report_format: str | None = None,
    generated_at: str | None = None,
) -> HistoryEvent:
    """Build and validate a new history event with generated event_id/timestamp."""
    payload: dict[str, Any] = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "generated_at": generated_at or _utc_now_iso(),
        "system_name": system_name,
        "descriptor_path": descriptor_path,
        "risk_tier": risk_tier,
        "summary": summary,
        "finding_statuses": finding_statuses,
        "report_format": report_format,
    }
    return HistoryEvent.from_dict(payload)


def _find_project_root(start_path: Path) -> Path | None:
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def resolve_history_path(
    history_path: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> Path:
    """Resolve explicit or default history path."""
    current_dir = Path(cwd).resolve() if cwd else Path.cwd().resolve()

    path_input: str | Path | None = history_path
    if path_input is None:
        env_path = os.getenv("EU_AI_ACT_HISTORY_PATH")
        if env_path:
            path_input = env_path

    if path_input is not None:
        candidate = Path(path_input).expanduser()
        if not candidate.is_absolute():
            candidate = (current_dir / candidate).resolve()
        return candidate

    project_root = _find_project_root(current_dir)
    base_dir = project_root if project_root else current_dir
    return base_dir / ".eu_ai_act" / "history.jsonl"


def _load_events(history_file: Path) -> list[HistoryEvent]:
    if not history_file.exists():
        return []

    events: list[HistoryEvent] = []
    with history_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload_line = line.strip()
            if not payload_line:
                continue
            try:
                payload = json.loads(payload_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in history file at line {line_number}: {exc.msg}"
                ) from exc
            try:
                events.append(HistoryEvent.from_dict(payload))
            except ValueError as exc:
                raise ValueError(f"Invalid history event at line {line_number}: {exc}") from exc
    return events


def append_event(
    event: HistoryEvent,
    *,
    history_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> HistoryEvent:
    """Append a validated history event to JSONL storage."""
    history_file = resolve_history_path(history_path, cwd=cwd)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with history_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
    return event


def list_events(
    *,
    history_path: str | Path | None = None,
    cwd: str | Path | None = None,
    system: str | None = None,
    event_type: EventType | None = None,
    limit: int | None = None,
) -> list[HistoryEvent]:
    """List history events ordered newest-first with optional filtering."""
    if limit is not None and limit <= 0:
        raise ValueError("limit must be a positive integer.")

    history_file = resolve_history_path(history_path, cwd=cwd)
    events = _load_events(history_file)
    filtered: Iterable[HistoryEvent] = events

    if system:
        filtered = (event for event in filtered if event.system_name == system)
    if event_type:
        filtered = (event for event in filtered if event.event_type == event_type)

    ordered = list(filtered)[::-1]
    if limit is not None:
        return ordered[:limit]
    return ordered


def get_event(
    event_id: str,
    *,
    history_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> HistoryEvent:
    """Fetch one event by event_id."""
    history_file = resolve_history_path(history_path, cwd=cwd)
    for event in reversed(_load_events(history_file)):
        if event.event_id == event_id:
            return event
    raise KeyError(f"History event not found: {event_id}")


def diff_events(
    older_event_id: str,
    newer_event_id: str,
    *,
    history_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Compute deterministic diff between two events."""
    history_file = resolve_history_path(history_path, cwd=cwd)
    events = _load_events(history_file)
    index = {event.event_id: event for event in events}

    if older_event_id not in index:
        raise KeyError(f"History event not found: {older_event_id}")
    if newer_event_id not in index:
        raise KeyError(f"History event not found: {newer_event_id}")

    older = index[older_event_id]
    newer = index[newer_event_id]

    summary_changes: dict[str, dict[str, Any]] = {}
    for field_name in SUMMARY_FIELDS:
        older_value = older.summary[field_name]
        newer_value = newer.summary[field_name]
        summary_changes[field_name] = {
            "from": older_value,
            "to": newer_value,
            "delta": round(newer_value - older_value, 2),
        }

    older_requirements = set(older.finding_statuses)
    newer_requirements = set(newer.finding_statuses)

    changed_requirements = sorted(
        requirement_id
        for requirement_id in (older_requirements & newer_requirements)
        if older.finding_statuses[requirement_id] != newer.finding_statuses[requirement_id]
    )

    finding_status_changes = [
        {
            "requirement_id": requirement_id,
            "from": older.finding_statuses[requirement_id],
            "to": newer.finding_statuses[requirement_id],
        }
        for requirement_id in changed_requirements
    ]

    added_findings = [
        {
            "requirement_id": requirement_id,
            "status": newer.finding_statuses[requirement_id],
        }
        for requirement_id in sorted(newer_requirements - older_requirements)
    ]

    removed_findings = [
        {
            "requirement_id": requirement_id,
            "status": older.finding_statuses[requirement_id],
        }
        for requirement_id in sorted(older_requirements - newer_requirements)
    ]

    return {
        "older_event_id": older.event_id,
        "newer_event_id": newer.event_id,
        "older_generated_at": older.generated_at,
        "newer_generated_at": newer.generated_at,
        "older_system_name": older.system_name,
        "newer_system_name": newer.system_name,
        "risk_tier_change": {
            "from": older.risk_tier,
            "to": newer.risk_tier,
            "changed": older.risk_tier != newer.risk_tier,
        },
        "summary_changes": summary_changes,
        "finding_status_changes": finding_status_changes,
        "added_findings": added_findings,
        "removed_findings": removed_findings,
    }
