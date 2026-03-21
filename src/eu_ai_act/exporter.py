"""Payload-first external export generation for compliance artifacts."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
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

    def __init__(self, *, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds

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
                "results": [],
            }

        if envelope.target == "jira":
            return self._push_jira(adapter_payload, actionable_count=actionable_count)
        if envelope.target == "servicenow":
            return self._push_servicenow(adapter_payload, actionable_count=actionable_count)
        raise ValueError(f"Unsupported export target: {envelope.target}")

    def _actionable_count(self, envelope: ExportEnvelope) -> int:
        return sum(1 for item in envelope.items if item.actionable)

    def _push_jira(
        self, adapter_payload: dict[str, Any], *, actionable_count: int
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
                "results": [],
            }

        base_url = _required_env("EU_AI_ACT_JIRA_BASE_URL").rstrip("/")
        user_email = _required_env("EU_AI_ACT_JIRA_EMAIL")
        api_token = _required_env("EU_AI_ACT_JIRA_API_TOKEN")
        project_key = _required_env("EU_AI_ACT_JIRA_PROJECT_KEY")
        endpoint = f"{base_url}/rest/api/3/issue"

        pushed_count = 0
        failed_count = 0
        results: list[dict[str, Any]] = []

        with httpx.Client(timeout=self.timeout_seconds, auth=(user_email, api_token)) as client:
            for issue in issues:
                if not isinstance(issue, dict):
                    raise ValueError("Invalid Jira issue payload item: expected object.")
                fields = issue.get("fields")
                if not isinstance(fields, dict):
                    raise ValueError("Invalid Jira issue payload item: missing 'fields' object.")
                fields = dict(fields)
                fields.setdefault("project", {"key": project_key})
                payload = {"fields": fields}

                try:
                    response = client.post(endpoint, json=payload)
                except httpx.HTTPError as exc:
                    raise RuntimeError(
                        f"Jira push failed with HTTP transport error: {exc}"
                    ) from exc

                if response.status_code in {200, 201}:
                    pushed_count += 1
                    response_json = self._safe_json(response)
                    results.append(
                        {
                            "status": "success",
                            "http_status": response.status_code,
                            "issue_key": response_json.get("key"),
                        }
                    )
                    continue

                failed_count += 1
                results.append(
                    {
                        "status": "failed",
                        "http_status": response.status_code,
                        "error": _trim_body_for_error(response.text),
                    }
                )

        if failed_count > 0:
            raise RuntimeError(
                f"Jira push failed for {failed_count} item(s). "
                f"Successful: {pushed_count}, Failed: {failed_count}."
            )

        return {
            "target": "jira",
            "dry_run": False,
            "attempted_actionable_count": actionable_count,
            "pushed_count": pushed_count,
            "failed_count": failed_count,
            "results": results,
        }

    def _push_servicenow(
        self, adapter_payload: dict[str, Any], *, actionable_count: int
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
                "results": [],
            }

        instance_url = _required_env("EU_AI_ACT_SERVICENOW_INSTANCE_URL").rstrip("/")
        username = _required_env("EU_AI_ACT_SERVICENOW_USERNAME")
        password = _required_env("EU_AI_ACT_SERVICENOW_PASSWORD")
        table_name = os.getenv("EU_AI_ACT_SERVICENOW_TABLE", "").strip() or adapter_payload.get(
            "table", "u_ai_act_compliance"
        )
        endpoint = f"{instance_url}/api/now/table/{table_name}"

        pushed_count = 0
        failed_count = 0
        results: list[dict[str, Any]] = []

        with httpx.Client(timeout=self.timeout_seconds, auth=(username, password)) as client:
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Invalid ServiceNow record payload item: expected object.")
                try:
                    response = client.post(endpoint, json=record)
                except httpx.HTTPError as exc:
                    raise RuntimeError(
                        f"ServiceNow push failed with HTTP transport error: {exc}"
                    ) from exc

                if response.status_code in {200, 201}:
                    pushed_count += 1
                    response_json = self._safe_json(response)
                    result_obj = response_json.get("result", {})
                    sys_id = result_obj.get("sys_id") if isinstance(result_obj, dict) else None
                    results.append(
                        {
                            "status": "success",
                            "http_status": response.status_code,
                            "sys_id": sys_id,
                        }
                    )
                    continue

                failed_count += 1
                results.append(
                    {
                        "status": "failed",
                        "http_status": response.status_code,
                        "error": _trim_body_for_error(response.text),
                    }
                )

        if failed_count > 0:
            raise RuntimeError(
                f"ServiceNow push failed for {failed_count} item(s). "
                f"Successful: {pushed_count}, Failed: {failed_count}."
            )

        return {
            "target": "servicenow",
            "dry_run": False,
            "attempted_actionable_count": actionable_count,
            "pushed_count": pushed_count,
            "failed_count": failed_count,
            "results": results,
        }

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
        return {}
