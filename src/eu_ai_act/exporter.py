"""Payload-first external export generation for compliance artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from eu_ai_act.checker import ComplianceChecker, ComplianceReport
from eu_ai_act.history import HistoryEvent
from eu_ai_act.schema import load_system_descriptor_from_file

ExportTarget = Literal["generic", "jira", "servicenow"]
SourceType = Literal["check", "history"]
PushMode = Literal["create", "upsert"]

_STATUS_NORMALIZATION_MAP: dict[str, str] = {
    "compliant": "compliant",
    "non_compliant": "non_compliant",
    "noncompliant": "non_compliant",
    "partial": "partial",
    "not_assessed": "not_assessed",
    "notassessed": "not_assessed",
}

_ACTIONABLE_STATUSES = {"non_compliant", "partial", "not_assessed"}
_ALLOWED_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
_DESCRIPTOR_SUFFIXES = {".yaml", ".yml"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _find_project_root(start_path: Path) -> Path | None:
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def resolve_export_push_ledger_path(
    idempotency_path: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> Path:
    """Resolve explicit or default idempotency ledger path."""
    current_dir = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    path_input: str | Path | None = idempotency_path

    if path_input is None:
        env_path = os.getenv("EU_AI_ACT_EXPORT_PUSH_LEDGER_PATH")
        if env_path:
            path_input = env_path

    if path_input is not None:
        candidate = Path(path_input).expanduser()
        if not candidate.is_absolute():
            candidate = (current_dir / candidate).resolve()
        return candidate

    project_root = _find_project_root(current_dir)
    base_dir = project_root if project_root else current_dir
    return base_dir / ".eu_ai_act" / "export_push_ledger.jsonl"


def _read_export_push_ledger_records(ledger_path: Path) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload_line = line.strip()
            if not payload_line:
                continue
            try:
                record = json.loads(payload_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in export push ledger at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid export push ledger record at line {line_number}: expected object."
                )
            records.append(record)
    return records


def list_export_push_ledger_records(
    *,
    idempotency_path: str | Path | None = None,
    cwd: str | Path | None = None,
    target: ExportTarget | None = None,
    system_name: str | None = None,
    requirement_id: str | None = None,
    limit: int | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """List export push ledger records with deterministic filtering."""
    ledger_path = resolve_export_push_ledger_path(idempotency_path, cwd=cwd)
    records = _read_export_push_ledger_records(ledger_path)

    if target:
        records = [record for record in records if record.get("target") == target]
    if system_name:
        records = [record for record in records if record.get("system_name") == system_name]
    if requirement_id:
        records = [record for record in records if record.get("requirement_id") == requirement_id]

    records.sort(
        key=lambda record: str(record.get("pushed_at") or ""),
        reverse=True,
    )
    if limit is not None:
        records = records[:limit]
    return ledger_path, records


def summarize_export_push_ledger(
    *,
    idempotency_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Build aggregate statistics for export push ledger records."""
    ledger_path, records = list_export_push_ledger_records(
        idempotency_path=idempotency_path,
        cwd=cwd,
    )
    target_distribution: dict[str, int] = {}
    status_distribution: dict[str, int] = {}
    system_distribution: dict[str, int] = {}
    requirement_distribution: dict[str, int] = {}
    idempotency_keys: set[str] = set()

    for record in records:
        target_key = str(record.get("target") or "unknown")
        status_key = str(record.get("status") or "unknown")
        system_key = str(record.get("system_name") or "unknown")
        requirement_key = str(record.get("requirement_id") or "unknown")
        idempotency_key = record.get("idempotency_key")

        target_distribution[target_key] = target_distribution.get(target_key, 0) + 1
        status_distribution[status_key] = status_distribution.get(status_key, 0) + 1
        system_distribution[system_key] = system_distribution.get(system_key, 0) + 1
        requirement_distribution[requirement_key] = (
            requirement_distribution.get(requirement_key, 0) + 1
        )
        if isinstance(idempotency_key, str) and idempotency_key:
            idempotency_keys.add(idempotency_key)

    pushed_values = [str(record.get("pushed_at")) for record in records if record.get("pushed_at")]
    first_pushed_at = min(pushed_values) if pushed_values else None
    last_pushed_at = max(pushed_values) if pushed_values else None

    return {
        "path": str(ledger_path),
        "total_records": len(records),
        "unique_idempotency_key_count": len(idempotency_keys),
        "target_distribution": dict(sorted(target_distribution.items())),
        "status_distribution": dict(sorted(status_distribution.items())),
        "system_distribution": dict(sorted(system_distribution.items())),
        "requirement_distribution": dict(sorted(requirement_distribution.items())),
        "first_pushed_at": first_pushed_at,
        "last_pushed_at": last_pushed_at,
    }


def discover_descriptor_files(
    descriptor_dir: str | Path,
    *,
    recursive: bool = False,
) -> list[Path]:
    """Discover descriptor YAML files in deterministic order."""
    scan_root = Path(descriptor_dir).expanduser().resolve()
    if not scan_root.exists():
        raise ValueError(f"Descriptor directory not found: {scan_root}")
    if not scan_root.is_dir():
        raise ValueError(f"Descriptor path is not a directory: {scan_root}")

    glob_pattern = "**/*" if recursive else "*"
    descriptor_files = [
        file_path.resolve()
        for file_path in scan_root.glob(glob_pattern)
        if file_path.is_file() and file_path.suffix.lower() in _DESCRIPTOR_SUFFIXES
    ]
    descriptor_files.sort(key=lambda file_path: str(file_path))
    return descriptor_files


def build_simulated_push_result(
    *,
    target: str,
    push_mode: PushMode,
    actionable_count: int,
    max_retries: int,
    retry_backoff_seconds: float,
    timeout_seconds: float,
    idempotency_enabled: bool,
    idempotency_path: str | None,
    message: str,
) -> dict[str, Any]:
    """Build deterministic dry-run push summary payload."""
    return {
        "target": target,
        "dry_run": True,
        "push_mode": push_mode,
        "attempted_actionable_count": actionable_count,
        "pushed_count": 0,
        "created_count": 0,
        "updated_count": 0,
        "failed_count": 0,
        "skipped_duplicate_count": 0,
        "failure_reason": None,
        "max_retries": max_retries,
        "retry_backoff_seconds": retry_backoff_seconds,
        "timeout_seconds": timeout_seconds,
        "idempotency_enabled": idempotency_enabled,
        "idempotency_path": idempotency_path,
        "results": [],
        "message": message,
    }


def run_export_batch(
    *,
    descriptor_dir: str | Path,
    target: ExportTarget,
    recursive: bool = False,
    push: bool = False,
    push_mode: PushMode = "create",
    dry_run: bool = False,
    max_retries: int = 3,
    retry_backoff_seconds: float = 1.0,
    timeout_seconds: float = 30.0,
    idempotency_path: str | Path | None = None,
    idempotency_enabled: bool = True,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Run export generation for all descriptors in a directory."""
    if push and target == "generic":
        raise ValueError("Live push is not supported for target 'generic'.")

    scan_root = Path(descriptor_dir).expanduser().resolve()
    descriptor_files = discover_descriptor_files(scan_root, recursive=recursive)
    checker = ComplianceChecker()
    exporter = ExportGenerator()
    pusher = ExportPusher(
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        idempotency_path=idempotency_path,
        idempotency_enabled=idempotency_enabled,
        cwd=cwd,
    )
    resolved_idempotency_path = (
        str(resolve_export_push_ledger_path(idempotency_path, cwd=cwd))
        if idempotency_enabled
        else None
    )

    processed_count = 0
    success_count = 0
    failure_count = 0
    invalid_count = 0
    results: list[dict[str, Any]] = []

    for descriptor_file in descriptor_files:
        descriptor_path = str(descriptor_file)
        try:
            descriptor = load_system_descriptor_from_file(descriptor_path)
        except Exception as exc:
            invalid_count += 1
            results.append(
                {
                    "descriptor_path": descriptor_path,
                    "status": "invalid_descriptor",
                    "error": str(exc),
                }
            )
            continue

        processed_count += 1
        report = checker.check(descriptor)
        envelope = exporter.from_check(
            report=report,
            target=target,
            descriptor_path=descriptor_path,
        )
        result_entry: dict[str, Any] = {
            "descriptor_path": descriptor_path,
            "system_name": report.system_name,
            "risk_tier": report.risk_tier.value,
            "summary": _summary_from_compliance(report),
            "status": "success",
        }

        if push:
            try:
                result_entry["push_result"] = pusher.push(
                    envelope,
                    dry_run=dry_run,
                    push_mode=push_mode,
                )
            except ExportPushError as exc:
                failure_count += 1
                result_entry["status"] = "failed"
                result_entry["error"] = str(exc)
                result_entry["push_result"] = exc.push_result
                results.append(result_entry)
                continue
            except Exception as exc:
                failure_count += 1
                result_entry["status"] = "failed"
                result_entry["error"] = str(exc)
                results.append(result_entry)
                continue
        elif dry_run:
            result_entry["push_result"] = build_simulated_push_result(
                target=target,
                push_mode=push_mode,
                actionable_count=sum(1 for item in envelope.items if item.actionable),
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                timeout_seconds=timeout_seconds,
                idempotency_enabled=idempotency_enabled,
                idempotency_path=resolved_idempotency_path,
                message="Dry-run requested without --push; no remote API call was made.",
            )

        success_count += 1
        results.append(result_entry)

    return {
        "generated_at": _utc_now_iso(),
        "scan_root": str(scan_root),
        "target": target,
        "recursive": recursive,
        "total_files": len(descriptor_files),
        "processed_count": processed_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "invalid_count": invalid_count,
        "results": results,
    }


def reconcile_export_push_records(
    *,
    target: ExportTarget,
    idempotency_path: str | Path | None = None,
    system_name: str | None = None,
    requirement_id: str | None = None,
    limit: int | None = None,
    max_retries: int = 3,
    retry_backoff_seconds: float = 1.0,
    timeout_seconds: float = 30.0,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Reconcile ledger entries against remote target existence/status."""
    if target == "generic":
        raise ValueError("Reconcile is not supported for target 'generic'.")
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1.")

    ledger_path, records = list_export_push_ledger_records(
        idempotency_path=idempotency_path,
        cwd=cwd,
        target=target,
        system_name=system_name,
        requirement_id=requirement_id,
        limit=limit,
    )

    pusher = ExportPusher(
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        idempotency_enabled=False,
        cwd=cwd,
    )

    exists_count = 0
    missing_count = 0
    error_count = 0
    results: list[dict[str, Any]] = []

    if target == "jira":
        base_url = _required_env("EU_AI_ACT_JIRA_BASE_URL").rstrip("/")
        user_email = _required_env("EU_AI_ACT_JIRA_EMAIL")
        api_token = _required_env("EU_AI_ACT_JIRA_API_TOKEN")
        endpoint_template = f"{base_url}/rest/api/3/issue/{{remote_ref}}"
        auth = (user_email, api_token)
    else:
        instance_url = _required_env("EU_AI_ACT_SERVICENOW_INSTANCE_URL").rstrip("/")
        username = _required_env("EU_AI_ACT_SERVICENOW_USERNAME")
        password = _required_env("EU_AI_ACT_SERVICENOW_PASSWORD")
        table_name = os.getenv("EU_AI_ACT_SERVICENOW_TABLE", "").strip() or "u_ai_act_compliance"
        endpoint_template = f"{instance_url}/api/now/table/{table_name}/{{remote_ref}}"
        auth = (username, password)

    with httpx.Client(timeout=timeout_seconds, auth=auth) as client:
        for index, record in enumerate(records, start=1):
            remote_ref_raw = record.get("remote_ref")
            remote_ref = str(remote_ref_raw).strip() if remote_ref_raw is not None else ""
            result_entry = {
                "record_index": index,
                "status": "exists",
                "idempotency_key": record.get("idempotency_key"),
                "descriptor_path": record.get("descriptor_path"),
                "system_name": record.get("system_name"),
                "requirement_id": record.get("requirement_id"),
                "remote_ref": remote_ref_raw,
            }

            if not remote_ref:
                error_count += 1
                result_entry["status"] = "check_error"
                result_entry["failure_reason"] = "Ledger record missing remote_ref."
                result_entry["attempts"] = 0
                result_entry["retries_used"] = 0
                result_entry["http_status"] = None
                results.append(result_entry)
                continue

            attempt = pusher._request_with_retry(
                client=client,
                method="GET",
                endpoint=endpoint_template.format(remote_ref=remote_ref),
                target_name=target,
                success_status_codes={200},
            )

            if attempt["ok"]:
                response = attempt["response"]
                exists_count += 1
                result_entry["status"] = "exists"
                result_entry["http_status"] = response.status_code
                result_entry["attempts"] = attempt["attempts"]
                result_entry["retries_used"] = max(attempt["attempts"] - 1, 0)
                results.append(result_entry)
                continue

            http_status = attempt["http_status"]
            result_entry["http_status"] = http_status
            result_entry["attempts"] = attempt["attempts"]
            result_entry["retries_used"] = max(attempt["attempts"] - 1, 0)
            result_entry["failure_reason"] = attempt["failure_reason"]
            if http_status == 404:
                missing_count += 1
                result_entry["status"] = "missing"
            else:
                error_count += 1
                result_entry["status"] = "check_error"
            results.append(result_entry)

    return {
        "generated_at": _utc_now_iso(),
        "target": target,
        "ledger_path": str(ledger_path),
        "filters": {
            "system_name": system_name,
            "requirement_id": requirement_id,
            "limit": limit,
        },
        "checked_count": len(records),
        "exists_count": exists_count,
        "missing_count": missing_count,
        "error_count": error_count,
        "results": results,
    }


def _normalize_status(status: str) -> str:
    normalized_key = status.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_key not in _STATUS_NORMALIZATION_MAP:
        raise ValueError(f"Unsupported status value: {status}")
    return _STATUS_NORMALIZATION_MAP[normalized_key]


def _is_actionable(status: str) -> bool:
    return status in _ACTIONABLE_STATUSES


def _severity_from_status(status: str) -> str:
    if status == "non_compliant":
        return "HIGH"
    if status in {"partial", "not_assessed"}:
        return "MEDIUM"
    return "LOW"


def _normalize_severity(severity: str | None, status: str) -> str:
    if severity is None:
        return _severity_from_status(status)
    normalized = severity.strip().upper()
    if not normalized:
        return _severity_from_status(status)
    return normalized if normalized in _ALLOWED_SEVERITIES else _severity_from_status(status)


def _extract_article(requirement_id: str) -> str:
    match = re.search(r"Art\.\s*(\d+)", requirement_id, flags=re.IGNORECASE)
    if not match:
        return requirement_id
    return f"Art. {int(match.group(1))}"


def _success_criteria_for_status(status: str) -> str:
    if status == "compliant":
        return "Maintain current controls and keep evidence up to date."
    if status == "partial":
        return "Close remaining gaps and reach compliant status in the next assessment."
    if status == "non_compliant":
        return "Implement missing controls and re-run compliance checks until status is compliant."
    return "Provide sufficient evidence to replace not_assessed with a definitive status."


def _guidance_from_steps(remediation_steps: list[str]) -> str:
    if remediation_steps:
        return " ".join(step.strip() for step in remediation_steps if step.strip())
    return "No remediation guidance captured in source finding."


def _summary_from_compliance(report: ComplianceReport) -> dict[str, Any]:
    return {
        "total_requirements": report.summary.total_requirements,
        "compliant_count": report.summary.compliant_count,
        "non_compliant_count": report.summary.non_compliant_count,
        "partial_count": report.summary.partial_count,
        "not_assessed_count": report.summary.not_assessed_count,
        "compliance_percentage": round(report.summary.compliance_percentage, 2),
    }


@dataclass
class ExportItem:
    """Canonical export item used by all target adapters."""

    requirement_id: str
    title: str
    status: str
    severity: str
    article: str
    gap_analysis: str
    guidance: str
    success_criteria: str
    actionable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "title": self.title,
            "status": self.status,
            "severity": self.severity,
            "article": self.article,
            "gap_analysis": self.gap_analysis,
            "guidance": self.guidance,
            "success_criteria": self.success_criteria,
            "actionable": self.actionable,
        }


@dataclass
class ExportEnvelope:
    """Canonical export envelope contract for external payload generation."""

    schema_version: str
    generated_at: str
    source_type: SourceType
    target: ExportTarget
    system_name: str
    risk_tier: str
    summary: dict[str, Any]
    items: list[ExportItem]
    event_id: str | None = None
    event_type: str | None = None
    descriptor_path: str | None = None
    history_generated_at: str | None = None
    adapter_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "source_type": self.source_type,
            "target": self.target,
            "system_name": self.system_name,
            "risk_tier": self.risk_tier,
            "summary": dict(self.summary),
            "items": [item.to_dict() for item in self.items],
        }
        if self.event_id is not None:
            payload["event_id"] = self.event_id
        if self.event_type is not None:
            payload["event_type"] = self.event_type
        if self.descriptor_path is not None:
            payload["descriptor_path"] = self.descriptor_path
        if self.history_generated_at is not None:
            payload["history_generated_at"] = self.history_generated_at
        if self.adapter_payload is not None:
            payload["adapter_payload"] = self.adapter_payload
        return payload


class ExportGenerator:
    """Build deterministic export payloads from check and history sources."""

    schema_version = "1.0"

    def from_check(
        self,
        *,
        report: ComplianceReport,
        target: ExportTarget,
        descriptor_path: str | None = None,
    ) -> ExportEnvelope:
        items = [
            self._item_from_check_finding(requirement_id, finding)
            for requirement_id, finding in sorted(report.findings.items(), key=lambda row: row[0])
        ]

        envelope = ExportEnvelope(
            schema_version=self.schema_version,
            generated_at=_utc_now_iso(),
            source_type="check",
            target=target,
            system_name=report.system_name,
            risk_tier=report.risk_tier.value,
            summary=_summary_from_compliance(report),
            items=items,
            descriptor_path=descriptor_path,
        )
        envelope.adapter_payload = self._build_adapter_payload(envelope)
        return envelope

    def from_history(self, *, event: HistoryEvent, target: ExportTarget) -> ExportEnvelope:
        items = [
            self._item_from_history_status(requirement_id, status)
            for requirement_id, status in sorted(
                event.finding_statuses.items(), key=lambda row: row[0]
            )
        ]

        envelope = ExportEnvelope(
            schema_version=self.schema_version,
            generated_at=_utc_now_iso(),
            source_type="history",
            target=target,
            system_name=event.system_name,
            risk_tier=event.risk_tier,
            summary=dict(event.summary),
            items=items,
            event_id=event.event_id,
            event_type=event.event_type,
            descriptor_path=event.descriptor_path,
            history_generated_at=event.generated_at,
        )
        envelope.adapter_payload = self._build_adapter_payload(envelope)
        return envelope

    def to_json(self, envelope: ExportEnvelope) -> str:
        return json.dumps(envelope.to_dict(), indent=2)

    def _item_from_check_finding(self, requirement_id: str, finding) -> ExportItem:
        status = _normalize_status(finding.status.value)
        return ExportItem(
            requirement_id=requirement_id,
            title=finding.requirement_title,
            status=status,
            severity=_normalize_severity(finding.severity, status),
            article=_extract_article(requirement_id),
            gap_analysis=finding.gap_analysis,
            guidance=_guidance_from_steps(finding.remediation_steps),
            success_criteria=_success_criteria_for_status(status),
            actionable=_is_actionable(status),
        )

    def _item_from_history_status(self, requirement_id: str, raw_status: str) -> ExportItem:
        status = _normalize_status(raw_status)
        return ExportItem(
            requirement_id=requirement_id,
            title=f"{requirement_id} compliance status snapshot",
            status=status,
            severity=_severity_from_status(status),
            article=_extract_article(requirement_id),
            gap_analysis="Derived from history event snapshot; detailed gap analysis unavailable.",
            guidance="Run `ai-act check <system.yaml> --json` for requirement-level remediation detail.",
            success_criteria=_success_criteria_for_status(status),
            actionable=_is_actionable(status),
        )

    def _build_adapter_payload(self, envelope: ExportEnvelope) -> dict[str, Any]:
        if envelope.target == "generic":
            return {
                "format": "generic/v1",
                "records": [item.to_dict() for item in envelope.items],
            }
        if envelope.target == "jira":
            return self._build_jira_payload(envelope)
        if envelope.target == "servicenow":
            return self._build_servicenow_payload(envelope)
        raise ValueError(f"Unsupported export target: {envelope.target}")

    def _build_jira_payload(self, envelope: ExportEnvelope) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for item in envelope.items:
            if not item.actionable:
                continue
            issues.append(
                {
                    "fields": {
                        "issuetype": {"name": "Task"},
                        "summary": f"[EU AI Act] {item.article} {item.title}",
                        "description": self._build_issue_description(envelope, item),
                        "labels": [
                            "eu-ai-act",
                            f"risk-{envelope.risk_tier}",
                            f"status-{item.status}",
                            f"article-{item.article.lower().replace(' ', '')}",
                        ],
                        "priority": {"name": self._jira_priority(item.severity)},
                    }
                }
            )

        return {
            "format": "jira/issues/v1",
            "issues": issues,
            "actionable_count": len(issues),
            "skipped_compliant_count": len(envelope.items) - len(issues),
        }

    def _build_servicenow_payload(self, envelope: ExportEnvelope) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        for item in envelope.items:
            if not item.actionable:
                continue
            records.append(
                {
                    "short_description": f"[EU AI Act] {item.article} {item.title}",
                    "description": self._build_issue_description(envelope, item),
                    "category": "compliance",
                    "subcategory": "eu_ai_act",
                    "severity": self._servicenow_severity(item.severity),
                    "u_requirement_id": item.requirement_id,
                    "u_status": item.status,
                    "u_risk_tier": envelope.risk_tier,
                }
            )

        return {
            "format": "servicenow/records/v1",
            "table": "u_ai_act_compliance",
            "records": records,
            "actionable_count": len(records),
            "skipped_compliant_count": len(envelope.items) - len(records),
        }

    def _build_issue_description(self, envelope: ExportEnvelope, item: ExportItem) -> str:
        return (
            f"System: {envelope.system_name}\n"
            f"Risk Tier: {envelope.risk_tier}\n"
            f"Requirement: {item.requirement_id}\n"
            f"Article: {item.article}\n"
            f"Status: {item.status}\n"
            f"Severity: {item.severity}\n"
            f"Gap Analysis: {item.gap_analysis or 'n/a'}\n"
            f"Guidance: {item.guidance or 'n/a'}\n"
            f"Success Criteria: {item.success_criteria or 'n/a'}"
        )

    def _jira_priority(self, severity: str) -> str:
        mapping = {
            "CRITICAL": "Highest",
            "HIGH": "High",
            "MEDIUM": "Medium",
            "LOW": "Low",
        }
        return mapping.get(severity, "Medium")

    def _servicenow_severity(self, severity: str) -> str:
        mapping = {
            "CRITICAL": "1",
            "HIGH": "2",
            "MEDIUM": "3",
            "LOW": "4",
        }
        return mapping.get(severity, "3")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _trim_body_for_error(body: str, *, max_len: int = 300) -> str:
    compact = " ".join(body.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


class ExportPusher:
    """Optional live push helper for target systems."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        idempotency_path: str | Path | None = None,
        idempotency_enabled: bool = True,
        cwd: str | Path | None = None,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0.")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0.")
        if retry_backoff_seconds <= 0:
            raise ValueError("retry_backoff_seconds must be > 0.")

        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.idempotency_enabled = idempotency_enabled
        self.idempotency_path = (
            resolve_export_push_ledger_path(idempotency_path, cwd=cwd)
            if idempotency_enabled
            else None
        )

    def push(
        self,
        envelope: ExportEnvelope,
        *,
        dry_run: bool = False,
        push_mode: PushMode = "create",
    ) -> dict[str, Any]:
        if envelope.target == "generic":
            raise ValueError("Live push is not supported for target 'generic'.")
        if push_mode not in {"create", "upsert"}:
            raise ValueError("Unsupported push mode. Expected one of: create, upsert.")

        adapter_payload = envelope.adapter_payload
        if adapter_payload is None:
            adapter_payload = ExportGenerator()._build_adapter_payload(envelope)  # noqa: SLF001

        actionable_count = self._actionable_count(envelope)
        if dry_run:
            return {
                "target": envelope.target,
                "dry_run": True,
                "push_mode": push_mode,
                "attempted_actionable_count": actionable_count,
                "pushed_count": 0,
                "created_count": 0,
                "updated_count": 0,
                "failed_count": 0,
                "skipped_duplicate_count": 0,
                "failure_reason": None,
                "max_retries": self.max_retries,
                "retry_backoff_seconds": self.retry_backoff_seconds,
                "timeout_seconds": self.timeout_seconds,
                "idempotency_enabled": self.idempotency_enabled,
                "idempotency_path": self._idempotency_path_display(),
                "results": [],
            }

        if envelope.target == "jira":
            return self._push_jira(
                envelope,
                adapter_payload,
                actionable_count=actionable_count,
                push_mode=push_mode,
            )
        if envelope.target == "servicenow":
            return self._push_servicenow(
                envelope,
                adapter_payload,
                actionable_count=actionable_count,
                push_mode=push_mode,
            )
        raise ValueError(f"Unsupported export target: {envelope.target}")

    def _actionable_count(self, envelope: ExportEnvelope) -> int:
        return sum(1 for item in envelope.items if item.actionable)

    def _push_jira(
        self,
        envelope: ExportEnvelope,
        adapter_payload: dict[str, Any],
        *,
        actionable_count: int,
        push_mode: PushMode,
    ) -> dict[str, Any]:
        issues = adapter_payload.get("issues", [])
        if not isinstance(issues, list):
            raise ValueError("Invalid Jira adapter payload: 'issues' must be a list.")

        if not issues:
            return {
                "target": "jira",
                "dry_run": False,
                "push_mode": push_mode,
                "attempted_actionable_count": actionable_count,
                "pushed_count": 0,
                "created_count": 0,
                "updated_count": 0,
                "failed_count": 0,
                "skipped_duplicate_count": 0,
                "failure_reason": None,
                "max_retries": self.max_retries,
                "retry_backoff_seconds": self.retry_backoff_seconds,
                "timeout_seconds": self.timeout_seconds,
                "idempotency_enabled": self.idempotency_enabled,
                "idempotency_path": self._idempotency_path_display(),
                "results": [],
            }

        actionable_items = [item for item in envelope.items if item.actionable]
        if len(actionable_items) != len(issues):
            raise ValueError(
                "Jira adapter payload/actionable item mismatch; regenerate export payload."
            )

        existing_idempotency_keys = self._load_existing_idempotency_keys()
        base_url = _required_env("EU_AI_ACT_JIRA_BASE_URL").rstrip("/")
        user_email = _required_env("EU_AI_ACT_JIRA_EMAIL")
        api_token = _required_env("EU_AI_ACT_JIRA_API_TOKEN")
        project_key = _required_env("EU_AI_ACT_JIRA_PROJECT_KEY")
        create_endpoint = f"{base_url}/rest/api/3/issue"
        search_endpoint = f"{base_url}/rest/api/3/search"

        pushed_count = 0
        created_count = 0
        updated_count = 0
        skipped_duplicate_count = 0
        results: list[dict[str, Any]] = []

        with httpx.Client(timeout=self.timeout_seconds, auth=(user_email, api_token)) as client:
            for issue_index, (issue, actionable_item) in enumerate(
                zip(issues, actionable_items, strict=True),
                start=1,
            ):
                if not isinstance(issue, dict):
                    raise ValueError("Invalid Jira issue payload item: expected object.")
                fields = issue.get("fields")
                if not isinstance(fields, dict):
                    raise ValueError("Invalid Jira issue payload item: missing 'fields' object.")
                fields = dict(fields)
                fields.setdefault("project", {"key": project_key})

                idempotency_key = self._build_idempotency_key(envelope, actionable_item)
                idempotency_label = self._jira_idempotency_label(idempotency_key)
                fields["labels"] = self._jira_labels_with_idempotency_label(
                    fields.get("labels"),
                    idempotency_label,
                )
                payload = {"fields": fields}

                if (
                    push_mode == "create"
                    and self.idempotency_enabled
                    and idempotency_key in existing_idempotency_keys
                ):
                    skipped_duplicate_count += 1
                    results.append(
                        {
                            "status": "skipped_duplicate",
                            "item_index": issue_index,
                            "requirement_id": actionable_item.requirement_id,
                            "idempotency_key": idempotency_key,
                            "idempotency_label": idempotency_label,
                        }
                    )
                    continue

                operation = "created"
                issue_key: str | None = None
                if push_mode == "upsert":
                    lookup_result = self._request_with_retry(
                        client=client,
                        method="GET",
                        endpoint=search_endpoint,
                        params={
                            "jql": f'project = {project_key} AND labels = "{idempotency_label}"',
                            "maxResults": "1",
                            "fields": "key",
                        },
                        target_name="jira",
                        success_status_codes={200},
                    )
                    if not lookup_result["ok"]:
                        failure_reason = lookup_result["failure_reason"]
                        results.append(
                            {
                                "status": "failed",
                                "operation": "lookup",
                                "http_status": lookup_result["http_status"],
                                "attempts": lookup_result["attempts"],
                                "retries_used": max(lookup_result["attempts"] - 1, 0),
                                "failure_reason": failure_reason,
                                "item_index": issue_index,
                                "requirement_id": actionable_item.requirement_id,
                                "idempotency_key": idempotency_key,
                                "idempotency_label": idempotency_label,
                            }
                        )
                        push_result = self._build_push_result(
                            target="jira",
                            push_mode=push_mode,
                            dry_run=False,
                            actionable_count=actionable_count,
                            pushed_count=pushed_count,
                            created_count=created_count,
                            updated_count=updated_count,
                            failed_count=1,
                            skipped_duplicate_count=skipped_duplicate_count,
                            failure_reason=failure_reason,
                            results=results,
                        )
                        raise ExportPushError(
                            f"Jira push aborted on item {issue_index}: {failure_reason}",
                            push_result=push_result,
                        )

                    issue_key = self._extract_jira_issue_key(lookup_result["response"])
                    if issue_key:
                        operation = "updated"

                endpoint = create_endpoint
                method = "POST"
                success_status_codes = {200, 201}
                if operation == "updated":
                    endpoint = f"{base_url}/rest/api/3/issue/{issue_key}"
                    method = "PUT"
                    success_status_codes = {200, 204}

                attempt_result = self._request_with_retry(
                    client=client,
                    method=method,
                    endpoint=endpoint,
                    payload=payload,
                    target_name="jira",
                    success_status_codes=success_status_codes,
                )

                if attempt_result["ok"]:
                    response = attempt_result["response"]
                    pushed_count += 1
                    response_json = self._safe_json(response) if operation == "created" else {}
                    if operation == "created":
                        created_count += 1
                        issue_key = response_json.get("key")
                    else:
                        updated_count += 1
                    success_entry = {
                        "status": "success",
                        "operation": operation,
                        "http_status": response.status_code,
                        "attempts": attempt_result["attempts"],
                        "retries_used": max(attempt_result["attempts"] - 1, 0),
                        "requirement_id": actionable_item.requirement_id,
                        "idempotency_key": idempotency_key,
                        "idempotency_label": idempotency_label,
                        "issue_key": issue_key,
                    }
                    if self.idempotency_enabled:
                        ledger_error = self._record_idempotency_success(
                            envelope=envelope,
                            item=actionable_item,
                            existing_idempotency_keys=existing_idempotency_keys,
                            idempotency_key=idempotency_key,
                            remote_ref=issue_key,
                            http_status=response.status_code,
                        )
                        success_entry["ledger_recorded"] = ledger_error is None
                        if ledger_error is not None:
                            success_entry["ledger_error"] = ledger_error
                    results.append(success_entry)
                    continue

                failure_reason = attempt_result["failure_reason"]
                results.append(
                    {
                        "status": "failed",
                        "operation": operation,
                        "http_status": attempt_result["http_status"],
                        "attempts": attempt_result["attempts"],
                        "retries_used": max(attempt_result["attempts"] - 1, 0),
                        "failure_reason": failure_reason,
                        "item_index": issue_index,
                        "requirement_id": actionable_item.requirement_id,
                        "idempotency_key": idempotency_key,
                        "idempotency_label": idempotency_label,
                    }
                )
                push_result = self._build_push_result(
                    target="jira",
                    push_mode=push_mode,
                    dry_run=False,
                    actionable_count=actionable_count,
                    pushed_count=pushed_count,
                    created_count=created_count,
                    updated_count=updated_count,
                    failed_count=1,
                    skipped_duplicate_count=skipped_duplicate_count,
                    failure_reason=failure_reason,
                    results=results,
                )
                raise ExportPushError(
                    f"Jira push aborted on item {issue_index}: {failure_reason}",
                    push_result=push_result,
                )

        return self._build_push_result(
            target="jira",
            push_mode=push_mode,
            dry_run=False,
            actionable_count=actionable_count,
            pushed_count=pushed_count,
            created_count=created_count,
            updated_count=updated_count,
            failed_count=0,
            skipped_duplicate_count=skipped_duplicate_count,
            failure_reason=None,
            results=results,
        )

    def _push_servicenow(
        self,
        envelope: ExportEnvelope,
        adapter_payload: dict[str, Any],
        *,
        actionable_count: int,
        push_mode: PushMode,
    ) -> dict[str, Any]:
        records = adapter_payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError("Invalid ServiceNow adapter payload: 'records' must be a list.")

        if not records:
            return {
                "target": "servicenow",
                "dry_run": False,
                "push_mode": push_mode,
                "attempted_actionable_count": actionable_count,
                "pushed_count": 0,
                "created_count": 0,
                "updated_count": 0,
                "failed_count": 0,
                "skipped_duplicate_count": 0,
                "failure_reason": None,
                "max_retries": self.max_retries,
                "retry_backoff_seconds": self.retry_backoff_seconds,
                "timeout_seconds": self.timeout_seconds,
                "idempotency_enabled": self.idempotency_enabled,
                "idempotency_path": self._idempotency_path_display(),
                "results": [],
            }

        actionable_items = [item for item in envelope.items if item.actionable]
        if len(actionable_items) != len(records):
            raise ValueError(
                "ServiceNow adapter payload/actionable item mismatch; regenerate export payload."
            )

        existing_idempotency_keys = self._load_existing_idempotency_keys()
        instance_url = _required_env("EU_AI_ACT_SERVICENOW_INSTANCE_URL").rstrip("/")
        username = _required_env("EU_AI_ACT_SERVICENOW_USERNAME")
        password = _required_env("EU_AI_ACT_SERVICENOW_PASSWORD")
        table_name = os.getenv("EU_AI_ACT_SERVICENOW_TABLE", "").strip() or adapter_payload.get(
            "table", "u_ai_act_compliance"
        )
        idempotency_field = (
            os.getenv("EU_AI_ACT_SERVICENOW_IDEMPOTENCY_FIELD", "").strip() or "u_idempotency_key"
        )
        endpoint = f"{instance_url}/api/now/table/{table_name}"

        pushed_count = 0
        created_count = 0
        updated_count = 0
        skipped_duplicate_count = 0
        results: list[dict[str, Any]] = []

        with httpx.Client(timeout=self.timeout_seconds, auth=(username, password)) as client:
            for record_index, (record, actionable_item) in enumerate(
                zip(records, actionable_items, strict=True),
                start=1,
            ):
                if not isinstance(record, dict):
                    raise ValueError("Invalid ServiceNow record payload item: expected object.")

                idempotency_key = self._build_idempotency_key(envelope, actionable_item)
                record_payload = dict(record)
                record_payload[idempotency_field] = idempotency_key
                if (
                    push_mode == "create"
                    and self.idempotency_enabled
                    and idempotency_key in existing_idempotency_keys
                ):
                    skipped_duplicate_count += 1
                    results.append(
                        {
                            "status": "skipped_duplicate",
                            "item_index": record_index,
                            "requirement_id": actionable_item.requirement_id,
                            "idempotency_key": idempotency_key,
                        }
                    )
                    continue

                operation = "created"
                sys_id: str | None = None
                if push_mode == "upsert":
                    lookup_result = self._request_with_retry(
                        client=client,
                        method="GET",
                        endpoint=endpoint,
                        params={
                            "sysparm_query": f"{idempotency_field}={idempotency_key}",
                            "sysparm_limit": "1",
                        },
                        target_name="servicenow",
                        success_status_codes={200},
                    )
                    if not lookup_result["ok"]:
                        failure_reason = lookup_result["failure_reason"]
                        results.append(
                            {
                                "status": "failed",
                                "operation": "lookup",
                                "http_status": lookup_result["http_status"],
                                "attempts": lookup_result["attempts"],
                                "retries_used": max(lookup_result["attempts"] - 1, 0),
                                "failure_reason": failure_reason,
                                "item_index": record_index,
                                "requirement_id": actionable_item.requirement_id,
                                "idempotency_key": idempotency_key,
                            }
                        )
                        push_result = self._build_push_result(
                            target="servicenow",
                            push_mode=push_mode,
                            dry_run=False,
                            actionable_count=actionable_count,
                            pushed_count=pushed_count,
                            created_count=created_count,
                            updated_count=updated_count,
                            failed_count=1,
                            skipped_duplicate_count=skipped_duplicate_count,
                            failure_reason=failure_reason,
                            results=results,
                        )
                        raise ExportPushError(
                            f"ServiceNow push aborted on item {record_index}: {failure_reason}",
                            push_result=push_result,
                        )

                    sys_id = self._extract_servicenow_sys_id_from_lookup(lookup_result["response"])
                    if sys_id:
                        operation = "updated"

                method = "POST"
                call_endpoint = endpoint
                success_status_codes = {200, 201}
                if operation == "updated":
                    method = "PATCH"
                    call_endpoint = f"{endpoint}/{sys_id}"
                    success_status_codes = {200}

                attempt_result = self._request_with_retry(
                    client=client,
                    method=method,
                    endpoint=call_endpoint,
                    payload=record_payload,
                    target_name="servicenow",
                    success_status_codes=success_status_codes,
                )

                if attempt_result["ok"]:
                    response = attempt_result["response"]
                    pushed_count += 1
                    response_json = self._safe_json(response)
                    if operation == "created":
                        created_count += 1
                        result_obj = response_json.get("result", {})
                        parsed_sys_id = (
                            result_obj.get("sys_id") if isinstance(result_obj, dict) else None
                        )
                        if isinstance(parsed_sys_id, str) and parsed_sys_id:
                            sys_id = parsed_sys_id
                    else:
                        updated_count += 1
                    success_entry = {
                        "status": "success",
                        "operation": operation,
                        "http_status": response.status_code,
                        "attempts": attempt_result["attempts"],
                        "retries_used": max(attempt_result["attempts"] - 1, 0),
                        "requirement_id": actionable_item.requirement_id,
                        "idempotency_key": idempotency_key,
                        "sys_id": sys_id,
                    }
                    if self.idempotency_enabled:
                        ledger_error = self._record_idempotency_success(
                            envelope=envelope,
                            item=actionable_item,
                            existing_idempotency_keys=existing_idempotency_keys,
                            idempotency_key=idempotency_key,
                            remote_ref=sys_id,
                            http_status=response.status_code,
                        )
                        success_entry["ledger_recorded"] = ledger_error is None
                        if ledger_error is not None:
                            success_entry["ledger_error"] = ledger_error
                    results.append(success_entry)
                    continue

                failure_reason = attempt_result["failure_reason"]
                results.append(
                    {
                        "status": "failed",
                        "operation": operation,
                        "http_status": attempt_result["http_status"],
                        "attempts": attempt_result["attempts"],
                        "retries_used": max(attempt_result["attempts"] - 1, 0),
                        "failure_reason": failure_reason,
                        "item_index": record_index,
                        "requirement_id": actionable_item.requirement_id,
                        "idempotency_key": idempotency_key,
                    }
                )
                push_result = self._build_push_result(
                    target="servicenow",
                    push_mode=push_mode,
                    dry_run=False,
                    actionable_count=actionable_count,
                    pushed_count=pushed_count,
                    created_count=created_count,
                    updated_count=updated_count,
                    failed_count=1,
                    skipped_duplicate_count=skipped_duplicate_count,
                    failure_reason=failure_reason,
                    results=results,
                )
                raise ExportPushError(
                    f"ServiceNow push aborted on item {record_index}: {failure_reason}",
                    push_result=push_result,
                )

        return self._build_push_result(
            target="servicenow",
            push_mode=push_mode,
            dry_run=False,
            actionable_count=actionable_count,
            pushed_count=pushed_count,
            created_count=created_count,
            updated_count=updated_count,
            failed_count=0,
            skipped_duplicate_count=skipped_duplicate_count,
            failure_reason=None,
            results=results,
        )

    def _request_with_retry(
        self,
        *,
        client: httpx.Client,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        target_name: str,
        success_status_codes: set[int] | tuple[int, ...] = (200, 201),
    ) -> dict[str, Any]:
        attempts = 0
        while attempts <= self.max_retries:
            attempts += 1
            try:
                response = client.request(method, endpoint, json=payload, params=params)
            except httpx.HTTPError as exc:
                failure_reason = f"HTTP transport error: {exc}"
                if attempts <= self.max_retries:
                    self._sleep_before_retry(attempts)
                    continue
                return {
                    "ok": False,
                    "attempts": attempts,
                    "http_status": None,
                    "failure_reason": failure_reason,
                }

            if response.status_code in success_status_codes:
                return {"ok": True, "attempts": attempts, "response": response}

            if self._is_retryable_status(response.status_code) and attempts <= self.max_retries:
                self._sleep_before_retry(attempts)
                continue

            failure_reason = (
                f"{target_name} API returned HTTP {response.status_code}: "
                f"{_trim_body_for_error(response.text)}"
            )
            return {
                "ok": False,
                "attempts": attempts,
                "http_status": response.status_code,
                "failure_reason": failure_reason,
            }

        return {
            "ok": False,
            "attempts": attempts,
            "http_status": None,
            "failure_reason": f"{target_name} push failed for unknown retry loop reason.",
        }

    def _build_push_result(
        self,
        *,
        target: str,
        push_mode: PushMode,
        dry_run: bool,
        actionable_count: int,
        pushed_count: int,
        created_count: int,
        updated_count: int,
        failed_count: int,
        skipped_duplicate_count: int,
        failure_reason: str | None,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "target": target,
            "dry_run": dry_run,
            "push_mode": push_mode,
            "attempted_actionable_count": actionable_count,
            "pushed_count": pushed_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "failed_count": failed_count,
            "skipped_duplicate_count": skipped_duplicate_count,
            "failure_reason": failure_reason,
            "max_retries": self.max_retries,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "timeout_seconds": self.timeout_seconds,
            "idempotency_enabled": self.idempotency_enabled,
            "idempotency_path": self._idempotency_path_display(),
            "results": results,
        }

    def _jira_idempotency_label(self, idempotency_key: str) -> str:
        return f"eu-ai-act-idem-{idempotency_key[:12]}"

    def _jira_labels_with_idempotency_label(
        self,
        labels: Any,
        idempotency_label: str,
    ) -> list[str]:
        normalized_labels: list[str] = []
        if isinstance(labels, list):
            normalized_labels = [str(label) for label in labels if str(label).strip()]
        if idempotency_label not in normalized_labels:
            normalized_labels.append(idempotency_label)
        return normalized_labels

    def _extract_jira_issue_key(self, response: httpx.Response) -> str | None:
        response_json = self._safe_json(response)
        issues = response_json.get("issues")
        if isinstance(issues, list) and issues:
            first_issue = issues[0]
            if isinstance(first_issue, dict):
                issue_key = first_issue.get("key")
                if isinstance(issue_key, str) and issue_key:
                    return issue_key
        return None

    def _extract_servicenow_sys_id_from_lookup(self, response: httpx.Response) -> str | None:
        response_json = self._safe_json(response)
        result_obj = response_json.get("result")
        if isinstance(result_obj, list) and result_obj:
            first = result_obj[0]
            if isinstance(first, dict):
                sys_id = first.get("sys_id")
                if isinstance(sys_id, str) and sys_id:
                    return sys_id
        return None

    def _sleep_before_retry(self, attempts: int) -> None:
        delay_seconds = self.retry_backoff_seconds * (2 ** (attempts - 1))
        time.sleep(delay_seconds)

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code <= 599

    def _idempotency_path_display(self) -> str | None:
        return str(self.idempotency_path) if self.idempotency_path else None

    def _load_existing_idempotency_keys(self) -> set[str]:
        if not self.idempotency_enabled or self.idempotency_path is None:
            return set()
        if not self.idempotency_path.exists():
            return set()

        keys: set[str] = set()
        with self.idempotency_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                payload_line = line.strip()
                if not payload_line:
                    continue
                try:
                    record = json.loads(payload_line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in export push ledger at line {line_number}: {exc.msg}"
                    ) from exc
                key = record.get("idempotency_key") if isinstance(record, dict) else None
                if not isinstance(key, str) or not key:
                    raise ValueError(
                        f"Invalid export push ledger record at line {line_number}: "
                        "missing 'idempotency_key'."
                    )
                keys.add(key)
        return keys

    def _build_idempotency_key(self, envelope: ExportEnvelope, item: ExportItem) -> str:
        source_ref = envelope.descriptor_path or envelope.event_id or "unknown"
        material = {
            "target": envelope.target,
            "source_type": envelope.source_type,
            "system_name": envelope.system_name,
            "source_ref": source_ref,
            "requirement_id": item.requirement_id,
            "status": item.status,
            "article": item.article,
        }
        encoded = json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _build_ledger_record(
        self,
        envelope: ExportEnvelope,
        item: ExportItem,
        *,
        idempotency_key: str,
        remote_ref: str | None,
        http_status: int,
    ) -> dict[str, Any]:
        return {
            "idempotency_key": idempotency_key,
            "target": envelope.target,
            "source_type": envelope.source_type,
            "system_name": envelope.system_name,
            "descriptor_path": envelope.descriptor_path,
            "event_id": envelope.event_id,
            "requirement_id": item.requirement_id,
            "status": item.status,
            "article": item.article,
            "remote_ref": remote_ref,
            "http_status": http_status,
            "pushed_at": _utc_now_iso(),
        }

    def _record_idempotency_success(
        self,
        *,
        envelope: ExportEnvelope,
        item: ExportItem,
        existing_idempotency_keys: set[str],
        idempotency_key: str,
        remote_ref: str | None,
        http_status: int,
    ) -> str | None:
        """Persist idempotency record after successful remote create.

        Remote creates are authoritative: if local ledger write fails, we keep command success
        and return a warning string instead of converting the whole push into a failure.
        """
        try:
            self._append_ledger_record(
                self._build_ledger_record(
                    envelope,
                    item,
                    idempotency_key=idempotency_key,
                    remote_ref=remote_ref,
                    http_status=http_status,
                )
            )
            existing_idempotency_keys.add(idempotency_key)
            return None
        except Exception as exc:
            existing_idempotency_keys.add(idempotency_key)
            return f"Failed to write idempotency ledger after successful remote create: {exc}"

    def _append_ledger_record(self, record: dict[str, Any]) -> None:
        if not self.idempotency_enabled or self.idempotency_path is None:
            return
        self.idempotency_path.parent.mkdir(parents=True, exist_ok=True)
        with self.idempotency_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
        return {}


class ExportPushError(RuntimeError):
    """Raised when live push fails in strict fail-fast mode."""

    def __init__(self, message: str, *, push_result: dict[str, Any]):
        super().__init__(message)
        self.push_result = push_result
