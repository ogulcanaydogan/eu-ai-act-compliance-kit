"""
Compliance Checklist Generator

Generates actionable checklists based on AI system risk tier and applicable
EU AI Act requirements.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from eu_ai_act.checker import ComplianceFinding, ComplianceStatus
from eu_ai_act.schema import AISystemDescriptor, RiskTier


@dataclass
class ChecklistItem:
    """
    Single item in a compliance checklist.

    Attributes:
        id: Unique identifier
        title: Action to take
        article: Related EU AI Act article
        severity: CRITICAL, HIGH, MEDIUM, LOW
        deadline_months: Months from now to complete
        status: Checklist status aligned with compliance status
        description: Detailed description
        guidance: How to implement
        success_criteria: How to verify completion
        gap_analysis: Reported compliance gap for the item
    """

    id: str
    title: str
    article: str
    severity: str
    deadline_months: int
    status: str
    description: str
    guidance: str
    success_criteria: str
    gap_analysis: str = ""


@dataclass
class ChecklistSummary:
    """Summary metrics for checklist generation."""

    total_requirements: int
    compliant_count: int
    non_compliant_count: int
    partial_count: int
    not_assessed_count: int
    actionable_count: int
    compliance_percentage: float


@dataclass
class ComplianceChecklist:
    """
    Complete compliance checklist for an AI system.

    Attributes:
        system_name: Name of the system
        risk_tier: Assigned risk tier
        generated_at: Checklist generation timestamp
        items: List of checklist items
        total_items: Total number of actionable items
        estimated_completion_hours: Estimated effort to complete
        summary: Summary metrics from findings
    """

    system_name: str
    risk_tier: RiskTier
    generated_at: str
    items: list[ChecklistItem]
    total_items: int
    estimated_completion_hours: float
    summary: ChecklistSummary

    def to_json(self) -> str:
        """Export checklist as JSON."""
        data = {
            # Backward-compatible keys
            "system": self.system_name,
            "risk_tier": self.risk_tier.value,
            "checklist": "generated",
            # Expanded payload
            "system_name": self.system_name,
            "generated_at": self.generated_at,
            "total_items": self.total_items,
            "estimated_hours": self.estimated_completion_hours,
            "compliant_count": self.summary.compliant_count,
            "summary": {
                "total_requirements": self.summary.total_requirements,
                "compliant_count": self.summary.compliant_count,
                "non_compliant_count": self.summary.non_compliant_count,
                "partial_count": self.summary.partial_count,
                "not_assessed_count": self.summary.not_assessed_count,
                "actionable_count": self.summary.actionable_count,
                "compliance_percentage": round(self.summary.compliance_percentage, 2),
            },
            "items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "article": item.article,
                    "severity": item.severity,
                    "deadline_months": item.deadline_months,
                    "status": item.status,
                    "description": item.description,
                    "guidance": item.guidance,
                    "success_criteria": item.success_criteria,
                    "gap_analysis": item.gap_analysis,
                }
                for item in self.items
            ],
        }
        return json.dumps(data, indent=2)

    def to_markdown(self) -> str:
        """Export checklist as Markdown."""
        md = f"# Compliance Checklist: {self.system_name}\n\n"
        md += f"**Risk Tier:** {self.risk_tier.value.upper()}\n"
        md += f"**Generated:** {self.generated_at}\n"
        md += f"**Total Requirements:** {self.summary.total_requirements}\n"
        md += f"**Compliant (Not Listed):** {self.summary.compliant_count}\n"
        md += f"**Actionable Tasks:** {self.total_items}\n"
        md += f"**Estimated Effort:** {self.estimated_completion_hours} hours\n\n"

        if not self.items:
            md += "## Action Items\n\n"
            md += "No actionable checklist items identified.\n"
            return md

        md += "## Tasks by Severity\n\n"
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            severity_items = [item for item in self.items if item.severity == severity]
            if severity_items:
                md += f"### {severity} Priority ({len(severity_items)} items)\n\n"
                for item in severity_items:
                    md += f"- [ ] **{item.title}** ({item.article})\n"
                    md += (
                        f"      *Status: {item.status} | Deadline: {item.deadline_months} months*\n"
                    )
                    if item.gap_analysis:
                        md += f"      Gap: {item.gap_analysis}\n"
                    md += f"      {item.description}\n"
                    md += f"      Guidance: {item.guidance}\n"
                    md += f"      Success Criteria: {item.success_criteria}\n\n"

        return md

    def to_html(self) -> str:
        """Export checklist as HTML."""
        severity_color = {
            "CRITICAL": "#b71c1c",
            "HIGH": "#e65100",
            "MEDIUM": "#f9a825",
            "LOW": "#2e7d32",
        }
        rows = []
        for item in self.items:
            rows.append(f"""
                <tr>
                    <td>{item.id}</td>
                    <td>{item.title}</td>
                    <td>{item.article}</td>
                    <td style="color:{severity_color.get(item.severity, '#333')};font-weight:bold;">{item.severity}</td>
                    <td>{item.status}</td>
                    <td>{item.deadline_months}</td>
                    <td>{item.gap_analysis or '-'}</td>
                </tr>
                """)

        body = f"""
            <p><strong>Generated:</strong> {self.generated_at}</p>
            <p><strong>Risk Tier:</strong> {self.risk_tier.value.upper()}</p>
            <p><strong>Total Requirements:</strong> {self.summary.total_requirements}</p>
            <p><strong>Compliant (Not Listed):</strong> {self.summary.compliant_count}</p>
            <p><strong>Actionable Tasks:</strong> {self.total_items}</p>
            """
        if rows:
            body += (
                """
                <table border="1" cellspacing="0" cellpadding="8">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Title</th>
                            <th>Article</th>
                            <th>Severity</th>
                            <th>Status</th>
                            <th>Deadline (months)</th>
                            <th>Gap</th>
                        </tr>
                    </thead>
                    <tbody>
                """
                + "".join(rows)
                + """
                    </tbody>
                </table>
                """
            )
        else:
            body += "<p>No actionable checklist items identified.</p>"

        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Compliance Checklist: {self.system_name}</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body>
    <h1>Compliance Checklist: {self.system_name}</h1>
    {body}
</body>
</html>
"""


class ChecklistGenerator:
    """
    Generates compliance checklists for AI systems.

    Creates actionable, prioritized checklists based on risk tier and specific
    gaps identified in the system descriptor.
    """

    ACTIONABLE_STATUSES = {
        ComplianceStatus.NON_COMPLIANT,
        ComplianceStatus.PARTIAL,
        ComplianceStatus.NOT_ASSESSED,
    }
    DEADLINE_BY_ARTICLE = {
        "Art. 5": 0,
        "Art. 50": 6,
        "Art. 10": 24,
        "Art. 11": 24,
        "Art. 13": 24,
        "Art. 14": 24,
        "Art. 15": 24,
        "Art. 43": 24,
    }
    TIER_ARTICLES = {
        RiskTier.UNACCEPTABLE: ["Art. 5"],
        RiskTier.HIGH_RISK: ["Art. 10", "Art. 11", "Art. 13", "Art. 14", "Art. 15", "Art. 43"],
        RiskTier.LIMITED: ["Art. 50"],
        RiskTier.MINIMAL: [],
    }
    TEMPLATE_BY_ARTICLE: dict[str, dict[str, str]] = {
        "Art. 5": {
            "title": "Remove prohibited AI practice from deployment path",
            "severity": "CRITICAL",
            "description": "The current use case is prohibited under the EU AI Act and cannot be deployed.",
            "guidance": "Disable release and redesign the use case to remove prohibited behaviors.",
            "success_criteria": "System no longer qualifies as prohibited during reassessment.",
        },
        "Art. 10": {
            "title": "Establish high-risk data governance controls",
            "severity": "HIGH",
            "description": "Implement data quality, consent, and governance controls for high-risk AI data flows.",
            "guidance": "Define documented controls for data sourcing, consent, anonymization, and quality monitoring.",
            "success_criteria": "Governance controls are documented and verified in audit artifacts.",
        },
        "Art. 11": {
            "title": "Complete technical documentation package",
            "severity": "HIGH",
            "description": "Maintain up-to-date technical documentation and traceable records.",
            "guidance": "Create a versioned technical file covering architecture, data, evaluation, and controls.",
            "success_criteria": "Technical documentation exists and is referenced in release process.",
        },
        "Art. 13": {
            "title": "Implement transparency disclosures",
            "severity": "HIGH",
            "description": "Provide clear information on model purpose, limitations, and operational boundaries.",
            "guidance": "Publish user/deployer disclosures and include them in onboarding and operations.",
            "success_criteria": "Disclosure content is accessible, reviewed, and linked to the deployed system.",
        },
        "Art. 14": {
            "title": "Strengthen human oversight controls",
            "severity": "CRITICAL",
            "description": "Ensure humans can intervene, override, and supervise system outcomes.",
            "guidance": "Document intervention points, escalation flow, and reviewer accountability.",
            "success_criteria": "Human override and oversight workflow is tested and auditable.",
        },
        "Art. 15": {
            "title": "Operationalize robustness and incident response",
            "severity": "HIGH",
            "description": "Define measurable performance thresholds, resilience controls, and incident handling.",
            "guidance": "Implement continuous monitoring, alerting, and incident response ownership.",
            "success_criteria": "Monitoring dashboards and incident procedures are active and reviewed.",
        },
        "Art. 43": {
            "title": "Prepare conformity assessment evidence",
            "severity": "HIGH",
            "description": "Gather and maintain conformity assessment evidence before market placement.",
            "guidance": "Document conformity pathway and compile evidence for internal/external assessment.",
            "success_criteria": "Conformity assessment records are complete and accessible for audit.",
        },
        "Art. 50": {
            "title": "Add AI-generated content disclosure",
            "severity": "MEDIUM",
            "description": "Users must be informed when content is AI-generated or synthetic.",
            "guidance": "Add clear disclosures in UX and policy documents for generated outputs.",
            "success_criteria": "Disclosure is visible to users and validated in product QA.",
        },
    }

    def generate(
        self,
        descriptor: AISystemDescriptor,
        tier: RiskTier,
        findings: dict[str, ComplianceFinding] | None = None,
        generated_at: str | None = None,
    ) -> ComplianceChecklist:
        """
        Generate a compliance checklist for an AI system.

        Args:
            descriptor: AI system descriptor
            tier: Risk tier classification
            findings: Optional compliance findings from ComplianceChecker
            generated_at: Optional timestamp for deterministic rendering

        Returns:
            ComplianceChecklist with actionable items
        """
        if findings:
            summary = self._summarize_findings(findings)
            items = self._build_actionable_items_from_findings(tier, findings)
        else:
            items = self._build_default_items_for_tier(tier)
            summary = ChecklistSummary(
                total_requirements=len(items),
                compliant_count=0,
                non_compliant_count=0,
                partial_count=0,
                not_assessed_count=len(items),
                actionable_count=len(items),
                compliance_percentage=0.0,
            )

        checklist_generated_at = generated_at or self._utc_now()

        return ComplianceChecklist(
            system_name=descriptor.name,
            risk_tier=tier,
            generated_at=checklist_generated_at,
            items=items,
            total_items=len(items),
            estimated_completion_hours=round(len(items) * 2.0, 1),
            summary=summary,
        )

    def _build_actionable_items_from_findings(
        self,
        tier: RiskTier,
        findings: dict[str, ComplianceFinding],
    ) -> list[ChecklistItem]:
        """Build actionable checklist items from checker findings."""
        ordered_articles = self.TIER_ARTICLES.get(tier, [])
        remaining_articles = [article for article in findings if article not in ordered_articles]
        articles_to_check = ordered_articles + sorted(remaining_articles)

        items: list[ChecklistItem] = []
        counter = 1
        for article in articles_to_check:
            finding = findings.get(article)
            if not finding or finding.status not in self.ACTIONABLE_STATUSES:
                continue
            template = self._get_template(article)
            guidance_parts = [template["guidance"]] + finding.remediation_steps
            guidance = " ".join(part for part in guidance_parts if part).strip()
            items.append(
                ChecklistItem(
                    id=f"T{counter:03d}",
                    title=template["title"],
                    article=article,
                    severity=finding.severity or template["severity"],
                    deadline_months=self._deadline_for_article(article),
                    status=finding.status.value,
                    description=finding.description or template["description"],
                    guidance=guidance,
                    success_criteria=template["success_criteria"],
                    gap_analysis=finding.gap_analysis,
                )
            )
            counter += 1
        return items

    def _build_default_items_for_tier(self, tier: RiskTier) -> list[ChecklistItem]:
        """Build default tier-based checklist tasks when findings are unavailable."""
        articles = self.TIER_ARTICLES.get(tier, [])
        items: list[ChecklistItem] = []
        for index, article in enumerate(articles, start=1):
            template = self._get_template(article)
            items.append(
                ChecklistItem(
                    id=f"T{index:03d}",
                    title=template["title"],
                    article=article,
                    severity=template["severity"],
                    deadline_months=self._deadline_for_article(article),
                    status=ComplianceStatus.NOT_ASSESSED.value,
                    description=template["description"],
                    guidance=template["guidance"],
                    success_criteria=template["success_criteria"],
                    gap_analysis="Checklist generated from tier defaults; explicit finding not available.",
                )
            )
        return items

    def _summarize_findings(self, findings: dict[str, ComplianceFinding]) -> ChecklistSummary:
        """Compute summary metrics from checker findings."""
        compliant_count = sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.COMPLIANT
        )
        non_compliant_count = sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.NON_COMPLIANT
        )
        partial_count = sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.PARTIAL
        )
        not_assessed_count = sum(
            1 for finding in findings.values() if finding.status == ComplianceStatus.NOT_ASSESSED
        )
        total_requirements = len(findings)
        actionable_count = non_compliant_count + partial_count + not_assessed_count
        if total_requirements == 0:
            compliance_percentage = 0.0
        else:
            compliance_percentage = (
                (compliant_count + (partial_count * 0.5)) / total_requirements * 100
            )
        return ChecklistSummary(
            total_requirements=total_requirements,
            compliant_count=compliant_count,
            non_compliant_count=non_compliant_count,
            partial_count=partial_count,
            not_assessed_count=not_assessed_count,
            actionable_count=actionable_count,
            compliance_percentage=compliance_percentage,
        )

    def _get_template(self, article: str) -> dict[str, str]:
        """Return template for an article with a safe generic fallback."""
        return self.TEMPLATE_BY_ARTICLE.get(
            article,
            {
                "title": f"Address {article} compliance gap",
                "severity": "MEDIUM",
                "description": f"Resolve outstanding obligations for {article}.",
                "guidance": "Document controls and close identified implementation gaps.",
                "success_criteria": "Requirement is reassessed as compliant.",
            },
        )

    def _deadline_for_article(self, article: str) -> int:
        """Return default deadline in months for article task completion."""
        return self.DEADLINE_BY_ARTICLE.get(article, 24)

    def _utc_now(self) -> str:
        """Return ISO-8601 UTC timestamp."""
        return datetime.now(UTC).isoformat(timespec="seconds")
