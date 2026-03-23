"""Multi-system dashboard generation for descriptor directories."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.classifier import RiskClassifier
from eu_ai_act.history import list_events
from eu_ai_act.schema import RiskTier, load_system_descriptor_from_file
from eu_ai_act.security_mapping import SecurityMapper


def _utc_now_iso() -> str:
    """Return timezone-aware UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


class DashboardGenerator:
    """Builds multi-system dashboard payloads and static HTML output."""

    def __init__(self) -> None:
        self.classifier = RiskClassifier()
        self.checker = ComplianceChecker()
        self.security_mapper = SecurityMapper()

    def build(
        self,
        descriptor_dir: str | Path,
        *,
        recursive: bool = False,
        include_history: bool = False,
        history_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Build dashboard payload from descriptors in a directory."""
        scan_root = Path(descriptor_dir).expanduser().resolve()
        if not scan_root.exists() or not scan_root.is_dir():
            raise ValueError(f"Descriptor directory does not exist: {scan_root}")

        descriptor_files = self._discover_descriptor_files(scan_root, recursive=recursive)
        systems: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        risk_tier_distribution = {tier.value: 0 for tier in RiskTier}

        for descriptor_file in descriptor_files:
            try:
                descriptor = load_system_descriptor_from_file(str(descriptor_file))
                classification = self.classifier.classify(descriptor)
                compliance_report = self.checker.check(descriptor)
                security_mapping = self.security_mapper.map_from_compliance(compliance_report)
            except Exception as exc:
                errors.append(
                    {
                        "file": str(descriptor_file),
                        "error": str(exc),
                    }
                )
                continue

            summary = compliance_report.summary
            security_summary = {
                "framework": security_mapping.framework,
                **security_mapping.summary.to_dict(),
            }
            system_row = {
                "system_name": descriptor.name,
                "descriptor_path": str(descriptor_file),
                "risk_tier": classification.tier.value,
                "compliance_percentage": round(summary.compliance_percentage, 2),
                "total_requirements": summary.total_requirements,
                "non_compliant_count": summary.non_compliant_count,
                "partial_count": summary.partial_count,
                "not_assessed_count": summary.not_assessed_count,
                "security_summary": security_summary,
                "generated_at": compliance_report.generated_at,
            }
            systems.append(system_row)
            risk_tier_distribution[classification.tier.value] += 1

        systems = sorted(systems, key=lambda row: (row["system_name"], row["descriptor_path"]))
        errors = sorted(errors, key=lambda row: row["file"])
        average_compliance = (
            round(sum(row["compliance_percentage"] for row in systems) / len(systems), 2)
            if systems
            else 0.0
        )
        average_security_coverage = (
            round(
                sum(row["security_summary"]["coverage_percentage"] for row in systems) / len(systems),
                2,
            )
            if systems
            else 0.0
        )
        security_control_status_distribution = {
            "compliant": sum(row["security_summary"]["compliant_count"] for row in systems),
            "non_compliant": sum(row["security_summary"]["non_compliant_count"] for row in systems),
            "partial": sum(row["security_summary"]["partial_count"] for row in systems),
            "not_assessed": sum(row["security_summary"]["not_assessed_count"] for row in systems),
        }

        payload: dict[str, Any] = {
            "generated_at": _utc_now_iso(),
            "scan_root": str(scan_root),
            "scanned_file_count": len(descriptor_files),
            "valid_system_count": len(systems),
            "invalid_descriptor_count": len(errors),
            "risk_tier_distribution": risk_tier_distribution,
            "average_compliance_percentage": average_compliance,
            "average_security_coverage_percentage": average_security_coverage,
            "security_control_status_distribution": security_control_status_distribution,
            "systems": systems,
            "errors": errors,
        }

        if include_history:
            payload["history_trends"] = self._build_history_trends(
                systems=systems,
                history_path=history_path,
            )

        return payload

    def render_html(self, payload: dict[str, Any]) -> str:
        """Render dashboard payload as static HTML."""
        cards = self._render_cards(payload)
        systems_rows = self._render_system_rows(payload.get("systems", []))
        errors_rows = self._render_error_rows(payload.get("errors", []))
        security_overview = self._render_security_overview(
            payload.get("average_security_coverage_percentage", 0.0),
            payload.get("security_control_status_distribution", {}),
        )
        history_section = self._render_history_section(payload.get("history_trends"))

        return (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "  <title>EU AI Act Multi-System Dashboard</title>\n"
            "  <style>\n"
            "    body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 24px; color: #1c2434; }\n"
            "    h1, h2 { margin-bottom: 8px; }\n"
            "    .meta { color: #4b5b76; margin-bottom: 20px; }\n"
            "    .cards { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 12px; margin-bottom: 24px; }\n"
            "    .card { border: 1px solid #d9e1ec; border-radius: 8px; padding: 10px 12px; background: #f8fbff; }\n"
            "    .card-title { font-size: 12px; color: #5a6a85; margin-bottom: 6px; }\n"
            "    .card-value { font-size: 20px; font-weight: 700; }\n"
            "    table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }\n"
            "    th, td { border: 1px solid #d9e1ec; padding: 8px; text-align: left; font-size: 14px; }\n"
            "    th { background: #eef3fb; }\n"
            "    .empty { color: #687a98; font-style: italic; margin-bottom: 18px; }\n"
            "    .risk-grid { margin-bottom: 20px; }\n"
            "    .risk-grid span { display: inline-block; margin-right: 12px; font-size: 14px; }\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            "  <h1>EU AI Act Multi-System Dashboard</h1>\n"
            f"  <p class=\"meta\">Generated at: {html.escape(str(payload.get('generated_at', '-')))} | "
            f"Scan root: {html.escape(str(payload.get('scan_root', '-')))}</p>\n"
            f"{cards}\n"
            "  <h2>Risk Tier Distribution</h2>\n"
            f"  {self._render_risk_distribution(payload.get('risk_tier_distribution', {}))}\n"
            "  <h2>Security Mapping Overview</h2>\n"
            f"  {security_overview}\n"
            "  <h2>Systems</h2>\n"
            f"{systems_rows}\n"
            "  <h2>Invalid Descriptors</h2>\n"
            f"{errors_rows}\n"
            f"{history_section}\n"
            "</body>\n"
            "</html>\n"
        )

    @staticmethod
    def to_json(payload: dict[str, Any]) -> str:
        """Serialize dashboard payload as JSON string."""
        return json.dumps(payload, indent=2)

    def _discover_descriptor_files(self, scan_root: Path, *, recursive: bool) -> list[Path]:
        patterns = ("*.yaml", "*.yml")
        files: list[Path] = []
        for pattern in patterns:
            if recursive:
                files.extend(scan_root.rglob(pattern))
            else:
                files.extend(scan_root.glob(pattern))
        unique_files = {path.resolve() for path in files if path.is_file()}
        return sorted(unique_files)

    def _build_history_trends(
        self,
        *,
        systems: list[dict[str, Any]],
        history_path: str | Path | None,
    ) -> list[dict[str, Any]]:
        if not systems:
            return []

        system_names = {row["system_name"] for row in systems}
        events = list_events(history_path=history_path)
        trends: list[dict[str, Any]] = []

        for system_name in sorted(system_names):
            system_events = [
                event
                for event in events
                if event.system_name == system_name and event.event_type in {"check", "report"}
            ]
            if not system_events:
                continue

            latest = system_events[0]
            previous = system_events[1] if len(system_events) > 1 else None

            trend: dict[str, Any] = {
                "system_name": system_name,
                "event_count": len(system_events),
                "latest_event_id": latest.event_id,
                "latest_event_type": latest.event_type,
                "latest_generated_at": latest.generated_at,
                "latest_risk_tier": latest.risk_tier,
                "latest_compliance_percentage": latest.summary["compliance_percentage"],
            }
            if previous:
                trend["previous_event_id"] = previous.event_id
                trend["previous_generated_at"] = previous.generated_at
                trend["previous_risk_tier"] = previous.risk_tier
                trend["previous_compliance_percentage"] = previous.summary["compliance_percentage"]
                trend["compliance_percentage_delta"] = round(
                    latest.summary["compliance_percentage"]
                    - previous.summary["compliance_percentage"],
                    2,
                )
                trend["non_compliant_count_delta"] = (
                    latest.summary["non_compliant_count"] - previous.summary["non_compliant_count"]
                )
            trends.append(trend)

        return trends

    def _render_cards(self, payload: dict[str, Any]) -> str:
        cards = [
            ("Scanned Files", payload.get("scanned_file_count", 0)),
            ("Valid Systems", payload.get("valid_system_count", 0)),
            ("Invalid Descriptors", payload.get("invalid_descriptor_count", 0)),
            ("Avg Compliance %", payload.get("average_compliance_percentage", 0.0)),
            ("Generated At", payload.get("generated_at", "-")),
        ]
        card_html = []
        for title, value in cards:
            card_html.append(
                '    <div class="card">'
                f'<div class="card-title">{html.escape(str(title))}</div>'
                f'<div class="card-value">{html.escape(str(value))}</div>'
                "</div>"
            )
        return '  <div class="cards">\n' + "\n".join(card_html) + "\n  </div>"

    def _render_risk_distribution(self, distribution: dict[str, Any]) -> str:
        if not distribution:
            return '<p class="empty">No risk distribution data available.</p>'
        labels = ["unacceptable", "high_risk", "limited", "minimal"]
        items = [
            f"<span><strong>{html.escape(label)}:</strong> {html.escape(str(distribution.get(label, 0)))}</span>"
            for label in labels
        ]
        return '<div class="risk-grid">' + "".join(items) + "</div>"

    def _render_security_overview(
        self,
        average_coverage: float,
        distribution: dict[str, Any],
    ) -> str:
        labels = ["compliant", "non_compliant", "partial", "not_assessed"]
        items = [
            "<span><strong>Avg Coverage:</strong> "
            f"{html.escape(str(round(average_coverage, 2)))}%</span>"
        ]
        items.extend(
            (
                f"<span><strong>{html.escape(label)}:</strong> "
                f"{html.escape(str(distribution.get(label, 0)))}</span>"
            )
            for label in labels
        )
        return '<div class="risk-grid">' + "".join(items) + "</div>"

    def _render_system_rows(self, systems: list[dict[str, Any]]) -> str:
        if not systems:
            return '<p class="empty">No valid systems detected.</p>'

        rows = []
        for row in systems:
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(row['system_name']))}</td>"
                f"<td>{html.escape(str(row['descriptor_path']))}</td>"
                f"<td>{html.escape(str(row['risk_tier']))}</td>"
                f"<td>{html.escape(str(row['compliance_percentage']))}</td>"
                f"<td>{html.escape(str(row['total_requirements']))}</td>"
                f"<td>{html.escape(str(row['non_compliant_count']))}</td>"
                f"<td>{html.escape(str(row['partial_count']))}</td>"
                f"<td>{html.escape(str(row['not_assessed_count']))}</td>"
                f"<td>{html.escape(str(row['generated_at']))}</td>"
                "</tr>"
            )
        return (
            "<table>\n"
            "  <thead><tr>"
            "<th>System</th><th>Descriptor</th><th>Risk Tier</th><th>Compliance %</th>"
            "<th>Total</th><th>Non-compliant</th><th>Partial</th><th>Not assessed</th><th>Generated At</th>"
            "</tr></thead>\n"
            "  <tbody>\n"
            f"{''.join(rows)}\n"
            "  </tbody>\n"
            "</table>"
        )

    def _render_error_rows(self, errors: list[dict[str, str]]) -> str:
        if not errors:
            return '<p class="empty">No invalid descriptor files.</p>'

        rows = []
        for row in errors:
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(row['file']))}</td>"
                f"<td>{html.escape(str(row['error']))}</td>"
                "</tr>"
            )
        return (
            "<table>\n"
            "  <thead><tr><th>File</th><th>Error</th></tr></thead>\n"
            "  <tbody>\n"
            f"{''.join(rows)}\n"
            "  </tbody>\n"
            "</table>"
        )

    def _render_history_section(self, history_trends: list[dict[str, Any]] | None) -> str:
        if history_trends is None:
            return ""

        if not history_trends:
            return '<h2>History Trends</h2><p class="empty">No history trends available.</p>'

        rows = []
        for row in history_trends:
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('system_name', '-')))}</td>"
                f"<td>{html.escape(str(row.get('event_count', '-')))}</td>"
                f"<td>{html.escape(str(row.get('latest_generated_at', '-')))}</td>"
                f"<td>{html.escape(str(row.get('latest_risk_tier', '-')))}</td>"
                f"<td>{html.escape(str(row.get('latest_compliance_percentage', '-')))}</td>"
                f"<td>{html.escape(str(row.get('compliance_percentage_delta', '-')))}</td>"
                "</tr>"
            )
        return (
            "<h2>History Trends</h2>"
            "<table>\n"
            "  <thead><tr>"
            "<th>System</th><th>Events</th><th>Latest At</th><th>Latest Risk</th>"
            "<th>Latest Compliance %</th><th>Compliance Delta</th>"
            "</tr></thead>\n"
            "  <tbody>\n"
            f"{''.join(rows)}\n"
            "  </tbody>\n"
            "</table>"
        )
