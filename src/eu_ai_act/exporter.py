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

from eu_ai_act.checker import ComplianceReport
from eu_ai_act.history import HistoryEvent

ExportTarget = Literal["generic", "jira", "servicenow"]
SourceType = Literal["check", "history"]

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

    def from_check(self, *, report: ComplianceReport, target: ExportTarget) -> ExportEnvelope:
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

    def push(self, envelope: ExportEnvelope, *, dry_run: bool = False) -> dict[str, Any]:
        if envelope.target == "generic":
            raise ValueError("Live push is not supported for target 'generic'.")

        adapter_payload = envelope.adapter_payload
        if adapter_payload is None:
            adapter_payload = ExportGenerator()._build_adapter_payload(envelope)  # noqa: SLF001

        actionable_count = self._actionable_count(envelope)
        if dry_run:
            return {
                "target": envelope.target,
                "dry_run": True,
                "attempted_actionable_count": actionable_count,
                "pushed_count": 0,
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
            )
        if envelope.target == "servicenow":
            return self._push_servicenow(
                envelope,
                adapter_payload,
                actionable_count=actionable_count,
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
    ) -> dict[str, Any]:
        issues = adapter_payload.get("issues", [])
        if not isinstance(issues, list):
            raise ValueError("Invalid Jira adapter payload: 'issues' must be a list.")

        if not issues:
            return {
                "target": "jira",
                "dry_run": False,
                "attempted_actionable_count": actionable_count,
                "pushed_count": 0,
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
        endpoint = f"{base_url}/rest/api/3/issue"

        pushed_count = 0
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
                payload = {"fields": fields}

                idempotency_key = self._build_idempotency_key(envelope, actionable_item)
                if self.idempotency_enabled and idempotency_key in existing_idempotency_keys:
                    skipped_duplicate_count += 1
                    results.append(
                        {
                            "status": "skipped_duplicate",
                            "item_index": issue_index,
                            "requirement_id": actionable_item.requirement_id,
                            "idempotency_key": idempotency_key,
                        }
                    )
                    continue

                attempt_result = self._post_with_retry(
                    client=client,
                    endpoint=endpoint,
                    payload=payload,
                    target_name="jira",
                )

                if attempt_result["ok"]:
                    response = attempt_result["response"]
                    pushed_count += 1
                    response_json = self._safe_json(response)
                    results.append(
                        {
                            "status": "success",
                            "http_status": response.status_code,
                            "attempts": attempt_result["attempts"],
                            "retries_used": max(attempt_result["attempts"] - 1, 0),
                            "requirement_id": actionable_item.requirement_id,
                            "idempotency_key": idempotency_key,
                            "issue_key": response_json.get("key"),
                        }
                    )
                    if self.idempotency_enabled:
                        self._append_ledger_record(
                            self._build_ledger_record(
                                envelope,
                                actionable_item,
                                idempotency_key=idempotency_key,
                                remote_ref=response_json.get("key"),
                                http_status=response.status_code,
                            )
                        )
                        existing_idempotency_keys.add(idempotency_key)
                    continue

                failure_reason = attempt_result["failure_reason"]
                results.append(
                    {
                        "status": "failed",
                        "http_status": attempt_result["http_status"],
                        "attempts": attempt_result["attempts"],
                        "retries_used": max(attempt_result["attempts"] - 1, 0),
                        "failure_reason": failure_reason,
                        "item_index": issue_index,
                        "requirement_id": actionable_item.requirement_id,
                        "idempotency_key": idempotency_key,
                    }
                )
                push_result = {
                    "target": "jira",
                    "dry_run": False,
                    "attempted_actionable_count": actionable_count,
                    "pushed_count": pushed_count,
                    "failed_count": 1,
                    "skipped_duplicate_count": skipped_duplicate_count,
                    "failure_reason": failure_reason,
                    "max_retries": self.max_retries,
                    "retry_backoff_seconds": self.retry_backoff_seconds,
                    "timeout_seconds": self.timeout_seconds,
                    "idempotency_enabled": self.idempotency_enabled,
                    "idempotency_path": self._idempotency_path_display(),
                    "results": results,
                }
                raise ExportPushError(
                    f"Jira push aborted on item {issue_index}: {failure_reason}",
                    push_result=push_result,
                )

        return {
            "target": "jira",
            "dry_run": False,
            "attempted_actionable_count": actionable_count,
            "pushed_count": pushed_count,
            "failed_count": 0,
            "skipped_duplicate_count": skipped_duplicate_count,
            "failure_reason": None,
            "max_retries": self.max_retries,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "timeout_seconds": self.timeout_seconds,
            "idempotency_enabled": self.idempotency_enabled,
            "idempotency_path": self._idempotency_path_display(),
            "results": results,
        }

    def _push_servicenow(
        self,
        envelope: ExportEnvelope,
        adapter_payload: dict[str, Any],
        *,
        actionable_count: int,
    ) -> dict[str, Any]:
        records = adapter_payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError("Invalid ServiceNow adapter payload: 'records' must be a list.")

        if not records:
            return {
                "target": "servicenow",
                "dry_run": False,
                "attempted_actionable_count": actionable_count,
                "pushed_count": 0,
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
        endpoint = f"{instance_url}/api/now/table/{table_name}"

        pushed_count = 0
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
                if self.idempotency_enabled and idempotency_key in existing_idempotency_keys:
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

                attempt_result = self._post_with_retry(
                    client=client,
                    endpoint=endpoint,
                    payload=record,
                    target_name="servicenow",
                )

                if attempt_result["ok"]:
                    response = attempt_result["response"]
                    pushed_count += 1
                    response_json = self._safe_json(response)
                    result_obj = response_json.get("result", {})
                    sys_id = result_obj.get("sys_id") if isinstance(result_obj, dict) else None
                    results.append(
                        {
                            "status": "success",
                            "http_status": response.status_code,
                            "attempts": attempt_result["attempts"],
                            "retries_used": max(attempt_result["attempts"] - 1, 0),
                            "requirement_id": actionable_item.requirement_id,
                            "idempotency_key": idempotency_key,
                            "sys_id": sys_id,
                        }
                    )
                    if self.idempotency_enabled:
                        self._append_ledger_record(
                            self._build_ledger_record(
                                envelope,
                                actionable_item,
                                idempotency_key=idempotency_key,
                                remote_ref=sys_id,
                                http_status=response.status_code,
                            )
                        )
                        existing_idempotency_keys.add(idempotency_key)
                    continue

                failure_reason = attempt_result["failure_reason"]
                results.append(
                    {
                        "status": "failed",
                        "http_status": attempt_result["http_status"],
                        "attempts": attempt_result["attempts"],
                        "retries_used": max(attempt_result["attempts"] - 1, 0),
                        "failure_reason": failure_reason,
                        "item_index": record_index,
                        "requirement_id": actionable_item.requirement_id,
                        "idempotency_key": idempotency_key,
                    }
                )
                push_result = {
                    "target": "servicenow",
                    "dry_run": False,
                    "attempted_actionable_count": actionable_count,
                    "pushed_count": pushed_count,
                    "failed_count": 1,
                    "skipped_duplicate_count": skipped_duplicate_count,
                    "failure_reason": failure_reason,
                    "max_retries": self.max_retries,
                    "retry_backoff_seconds": self.retry_backoff_seconds,
                    "timeout_seconds": self.timeout_seconds,
                    "idempotency_enabled": self.idempotency_enabled,
                    "idempotency_path": self._idempotency_path_display(),
                    "results": results,
                }
                raise ExportPushError(
                    f"ServiceNow push aborted on item {record_index}: {failure_reason}",
                    push_result=push_result,
                )

        return {
            "target": "servicenow",
            "dry_run": False,
            "attempted_actionable_count": actionable_count,
            "pushed_count": pushed_count,
            "failed_count": 0,
            "skipped_duplicate_count": skipped_duplicate_count,
            "failure_reason": None,
            "max_retries": self.max_retries,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "timeout_seconds": self.timeout_seconds,
            "idempotency_enabled": self.idempotency_enabled,
            "idempotency_path": self._idempotency_path_display(),
            "results": results,
        }

    def _post_with_retry(
        self,
        *,
        client: httpx.Client,
        endpoint: str,
        payload: dict[str, Any],
        target_name: str,
    ) -> dict[str, Any]:
        attempts = 0
        while attempts <= self.max_retries:
            attempts += 1
            try:
                response = client.post(endpoint, json=payload)
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

            if response.status_code in {200, 201}:
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
