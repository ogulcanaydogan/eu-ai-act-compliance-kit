"""
Command-Line Interface for EU AI Act Compliance Kit

Provides CLI commands for risk classification, compliance checking,
checklist generation, and report generation.
"""

import json
import sys
from pathlib import Path
from typing import cast

import click
from click.core import ParameterSource
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table

from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.checklist import ChecklistGenerator
from eu_ai_act.classifier import RiskClassifier
from eu_ai_act.dashboard import DashboardGenerator
from eu_ai_act.exporter import (
    ExportGenerator,
    ExportPusher,
    ExportPushError,
    PushMode,
    ExportTarget,
    list_export_push_ledger_records,
    resolve_export_push_ledger_path,
    summarize_export_push_ledger,
)
from eu_ai_act.gpai import (
    GPAIAssessment,
    GPAIAssessor,
    GPAIModelInfo,
    load_gpai_model_info_from_file,
)
from eu_ai_act.history import (
    EventType,
    append_event,
    build_event,
    diff_events,
    get_event,
    list_events,
    resolve_history_path,
)
from eu_ai_act.reporter import ReportGenerator
from eu_ai_act.schema import (
    AISystemDescriptor,
    RiskTier,
    UseCaseDomain,
    load_system_descriptor_from_file,
)
from eu_ai_act.transparency import TransparencyChecker, TransparencyFinding

console = Console()


@click.group()
@click.version_option(package_name="eu-ai-act-compliance-kit")
def main() -> None:
    """
    EU AI Act Compliance Checker

    Automated compliance assessment tool for the EU AI Act (Regulation 2024/1689).
    Classifies AI systems by risk tier, generates compliance checklists, and produces
    audit-ready reports.

    Quick start:
      ai-act classify examples/medical_diagnosis.yaml
      ai-act check examples/medical_diagnosis.yaml
      ai-act report examples/medical_diagnosis.yaml --format html
    """
    pass


@main.command()
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON instead of human-readable format",
)
def classify(system_yaml: str, output_json: bool) -> None:
    """
    Classify an AI system into a risk tier.

    Analyzes the AI system descriptor and assigns it to one of four risk tiers:
    UNACCEPTABLE (prohibited), HIGH_RISK, LIMITED, or MINIMAL.

    Example:
      ai-act classify examples/medical_diagnosis.yaml
      ai-act classify my_system.yaml --json
    """
    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {system_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading system descriptor: {e}[/red]")
        sys.exit(1)

    classifier = RiskClassifier()

    with Progress(transient=True) as progress:
        progress.add_task("Classifying...", total=None)
        classification = classifier.classify(descriptor)

    if output_json:
        output = {
            "system_name": descriptor.name,
            "risk_tier": classification.tier.value,
            "confidence": classification.confidence,
            "reasoning": classification.reasoning,
            "contributing_factors": classification.contributing_factors,
            "articles_applicable": classification.articles_applicable,
        }
        click.echo(json.dumps(output, indent=2))
    else:
        # Color-code the risk tier
        tier_styles = {
            "unacceptable": "bold red",
            "high_risk": "bold orange1",
            "limited": "bold yellow",
            "minimal": "bold green",
        }
        style = tier_styles.get(classification.tier.value, "white")

        console.print(
            Panel(
                f"[{style}]{classification.tier.value.upper()}[/{style}]",
                title=f"Risk Classification: {descriptor.name}",
                border_style="blue",
            )
        )
        console.print(f"\n[cyan]Reasoning:[/cyan]\n{classification.reasoning}")
        console.print(f"\n[cyan]Confidence:[/cyan] {classification.confidence:.0%}")
        console.print("\n[cyan]Contributing Factors:[/cyan]")
        for factor in classification.contributing_factors:
            console.print(f"  • {factor}")

        console.print("\n[cyan]Applicable EU AI Act Articles:[/cyan]")
        for article in classification.articles_applicable:
            console.print(f"  • {article}")


@main.command()
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON instead of human-readable format",
)
def check(system_yaml: str, output_json: bool) -> None:
    """
    Perform full compliance check on an AI system.

    Analyzes the system against all applicable EU AI Act requirements based on
    its risk tier. Produces detailed findings for each requirement.

    Example:
      ai-act check examples/hiring_tool.yaml
      ai-act check my_system.yaml --json
    """
    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {system_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading system descriptor: {e}[/red]")
        sys.exit(1)

    checker = ComplianceChecker()
    classifier = RiskClassifier()
    transparency_checker = TransparencyChecker()
    gpai_assessor = GPAIAssessor()

    with Progress(transient=True) as progress:
        progress.add_task("Checking compliance...", total=None)
        report_result = checker.check(descriptor)
        articles_applicable = classifier.get_applicable_articles(report_result.risk_tier)
        transparency_findings = _collect_transparency_findings(transparency_checker, descriptor)
        gpai_assessment = gpai_assessor.assess(_build_gpai_model_info_from_descriptor(descriptor))
        gpai_summary = _build_gpai_summary(gpai_assessment, descriptor)

    history_warning = None
    try:
        history_event = build_event(
            event_type="check",
            system_name=descriptor.name,
            descriptor_path=str(Path(system_yaml).resolve()),
            risk_tier=report_result.risk_tier.value,
            summary=_history_summary(report_result),
            finding_statuses=_history_finding_statuses(report_result.findings),
        )
        append_event(history_event)
    except Exception as e:
        history_warning = str(e)

    if output_json:
        findings_payload = {
            finding_id: {
                "title": finding.requirement_title,
                "status": finding.status.value,
                "description": finding.description,
                "gap_analysis": finding.gap_analysis,
                "remediation_steps": finding.remediation_steps,
                "severity": finding.severity,
            }
            for finding_id, finding in report_result.findings.items()
        }

        output = {
            "system_name": descriptor.name,
            "risk_tier": report_result.risk_tier.value,
            "articles_applicable": articles_applicable,
            "status": "compliance_check_completed",
            "message": "Compliance assessment completed.",
            "summary": {
                "total_requirements": report_result.summary.total_requirements,
                "compliant_count": report_result.summary.compliant_count,
                "non_compliant_count": report_result.summary.non_compliant_count,
                "partial_count": report_result.summary.partial_count,
                "not_assessed_count": report_result.summary.not_assessed_count,
                "compliance_percentage": round(report_result.summary.compliance_percentage, 2),
            },
            "findings": findings_payload,
            "transparency": [
                _serialize_transparency_finding(finding) for finding in transparency_findings
            ],
            "gpai_summary": gpai_summary,
            "audit_trail": report_result.audit_trail,
            "generated_at": report_result.generated_at,
        }
        click.echo(json.dumps(output, indent=2))
    else:
        console.print(
            Panel(
                (
                    f"[bold]Compliance Check: {descriptor.name}[/bold]\n"
                    f"Risk Tier: {report_result.risk_tier.value.upper()}"
                ),
                title="Compliance Assessment",
                border_style="blue",
            )
        )
        summary_table = Table(title="Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", justify="right")
        summary_table.add_row("Total Requirements", str(report_result.summary.total_requirements))
        summary_table.add_row("Compliant", str(report_result.summary.compliant_count))
        summary_table.add_row("Non-compliant", str(report_result.summary.non_compliant_count))
        summary_table.add_row("Partial", str(report_result.summary.partial_count))
        summary_table.add_row("Not assessed", str(report_result.summary.not_assessed_count))
        summary_table.add_row(
            "Compliance %",
            f"{report_result.summary.compliance_percentage:.1f}",
        )
        console.print(summary_table)

        if report_result.findings:
            findings_table = Table(title="Findings")
            findings_table.add_column("Requirement")
            findings_table.add_column("Status")
            findings_table.add_column("Severity")
            findings_table.add_column("Gap")
            for finding in report_result.findings.values():
                findings_table.add_row(
                    finding.requirement_id,
                    finding.status.value,
                    finding.severity,
                    finding.gap_analysis or "-",
                )
            console.print(findings_table)

        if transparency_findings:
            transparency_table = Table(title="Transparency Findings")
            transparency_table.add_column("Requirement")
            transparency_table.add_column("Status")
            transparency_table.add_column("Severity")
            transparency_table.add_column("Gap")
            for transparency_finding in transparency_findings:
                transparency_table.add_row(
                    transparency_finding.requirement_id,
                    transparency_finding.status.value,
                    transparency_finding.severity,
                    transparency_finding.gap_analysis or "-",
                )
            console.print(transparency_table)

        gpai_table = Table(title="GPAI Summary")
        gpai_table.add_column("Metric", style="cyan")
        gpai_table.add_column("Value", justify="right")
        gpai_table.add_row("Applicable", "yes" if gpai_summary["applicable"] else "no")
        gpai_table.add_row(
            "Systemic Risk Flag", "yes" if gpai_summary["systemic_risk_flag"] else "no"
        )
        gpai_table.add_row("Total Findings", str(gpai_summary["total_findings"]))
        gpai_table.add_row("Actionable Gaps", str(gpai_summary["actionable_gaps"]))
        console.print(gpai_table)

    if history_warning:
        click.echo(f"Warning: failed to write history event: {history_warning}", err=True)


@main.command()
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option(
    "--format",
    type=click.Choice(["json", "md", "html"]),
    default="json",
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: stdout for json, system_name.format otherwise)",
)
def checklist(system_yaml: str, format: str, output: str | None) -> None:
    """
    Generate a compliance checklist for an AI system.

    Creates an actionable checklist based on the system's risk tier.
    Includes specific EU AI Act article references and implementation guidance.

    Example:
      ai-act checklist examples/medical_diagnosis.yaml --format md
      ai-act checklist my_system.yaml --format md -o checklist.md
    """
    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {system_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading system descriptor: {e}[/red]")
        sys.exit(1)

    checker = ComplianceChecker()
    checklist_generator = ChecklistGenerator()

    with Progress(transient=True) as progress:
        progress.add_task("Generating checklist...", total=None)
        compliance_report = checker.check(descriptor)
        checklist_result = checklist_generator.generate(
            descriptor=descriptor,
            tier=compliance_report.risk_tier,
            findings=compliance_report.findings,
            generated_at=compliance_report.generated_at,
        )

    if format == "json":
        checklist_content = checklist_result.to_json()
    elif format == "md":
        checklist_content = checklist_result.to_markdown()
    else:
        checklist_content = checklist_result.to_html()

    if output:
        output_path = Path(output)
        output_path.write_text(checklist_content)
        console.print(f"[green]Checklist saved to: {output_path}[/green]")
    else:
        click.echo(checklist_content)


@main.command()
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON instead of human-readable format",
)
def transparency(system_yaml: str, output_json: bool) -> None:
    """
    Evaluate transparency obligations (Art. 50 and GPAI-related disclosures).

    Example:
      ai-act transparency examples/chatbot.yaml
      ai-act transparency my_system.yaml --json
    """
    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {system_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading system descriptor: {e}[/red]")
        sys.exit(1)

    checker = TransparencyChecker()
    findings = _collect_transparency_findings(checker, descriptor)

    if output_json:
        payload = {
            "system_name": descriptor.name,
            "finding_count": len(findings),
            "findings": [_serialize_transparency_finding(finding) for finding in findings],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title=f"Transparency Findings: {descriptor.name}")
    table.add_column("Requirement")
    table.add_column("Status")
    table.add_column("Severity")
    table.add_column("Title")
    table.add_column("Gap")
    for finding in findings:
        table.add_row(
            finding.requirement_id,
            finding.status.value,
            finding.severity,
            finding.title,
            finding.gap_analysis or "-",
        )
    console.print(table)


@main.command()
@click.argument("model_yaml", type=click.Path(exists=True))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON instead of human-readable format",
)
def gpai(model_yaml: str, output_json: bool) -> None:
    """
    Evaluate GPAI model obligations (Art. 51-55) from a GPAI model descriptor.

    Example:
      ai-act gpai examples/gpai_model.yaml
      ai-act gpai examples/gpai_model.yaml --json
    """
    try:
        model_info = load_gpai_model_info_from_file(model_yaml)
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {model_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading GPAI model descriptor: {e}[/red]")
        sys.exit(1)

    assessor = GPAIAssessor()
    assessment = assessor.assess(model_info)

    if output_json:
        payload = {
            "model_name": model_info.model_name,
            "provider": model_info.provider,
            "systemic_risk_flag": assessment.systemic_risk_flag,
            "compliance_gaps": assessment.compliance_gaps,
            "recommendations": assessment.recommendations,
            "findings": [_serialize_gpai_finding(finding) for finding in assessment.findings],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    panel_body = (
        f"Model: {model_info.model_name}\n"
        f"Provider: {model_info.provider}\n"
        f"Systemic Risk Flag: {'YES' if assessment.systemic_risk_flag else 'NO'}\n"
        f"Compliance Gaps: {len(assessment.compliance_gaps)}"
    )
    console.print(Panel(panel_body, title="GPAI Assessment", border_style="blue"))

    findings_table = Table(title="GPAI Findings")
    findings_table.add_column("Requirement")
    findings_table.add_column("Status")
    findings_table.add_column("Severity")
    findings_table.add_column("Gap")
    for finding in assessment.findings:
        findings_table.add_row(
            finding.requirement_id,
            finding.status.value,
            finding.severity,
            finding.gap_analysis or "-",
        )
    console.print(findings_table)


@main.command()
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option(
    "--format",
    type=click.Choice(["json", "md", "html", "pdf"]),
    default="json",
    help="Report format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path",
)
def report(system_yaml: str, format: str, output: str | None) -> None:
    """
    Generate a compliance report for an AI system.

    Creates a comprehensive report in the specified format. Includes executive summary,
    detailed findings, and recommended actions.

    Example:
      ai-act report examples/medical_diagnosis.yaml --format html -o report.html
      ai-act report my_system.yaml --format md -o report.md
      ai-act report my_system.yaml --format pdf -o report.pdf
    """
    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {system_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading system descriptor: {e}[/red]")
        sys.exit(1)

    classifier = RiskClassifier()
    checker = ComplianceChecker()
    checklist_generator = ChecklistGenerator()
    report_generator = ReportGenerator()
    transparency_checker = TransparencyChecker()
    gpai_assessor = GPAIAssessor()

    with Progress(transient=True) as progress:
        progress.add_task("Generating report...", total=None)
        classification = classifier.classify(descriptor)
        compliance_report = checker.check(descriptor)
        transparency_findings = _collect_transparency_findings(transparency_checker, descriptor)
        gpai_assessment = gpai_assessor.assess(_build_gpai_model_info_from_descriptor(descriptor))
        checklist_result = checklist_generator.generate(
            descriptor=descriptor,
            tier=compliance_report.risk_tier,
            findings=compliance_report.findings,
            generated_at=compliance_report.generated_at,
        )
        if format == "pdf":
            if not output:
                console.print(
                    "[red]Error: --output/-o is required when --format pdf "
                    "(binary output is not written to stdout).[/red]"
                )
                sys.exit(1)
            try:
                report_bytes = report_generator.generate_pdf_report(
                    descriptor=descriptor,
                    classification=classification,
                    compliance_report=compliance_report,
                    transparency_findings=transparency_findings,
                    gpai_assessment=gpai_assessment,
                    checklist=checklist_result,
                )
            except Exception as e:
                console.print(f"Error generating PDF report: {e}", style="red", markup=False)
                sys.exit(1)
        else:
            report_content = report_generator.generate_report(
                descriptor=descriptor,
                classification=classification,
                compliance_report=compliance_report,
                transparency_findings=transparency_findings,
                gpai_assessment=gpai_assessment,
                checklist=checklist_result,
                format=format,
            )

    history_warning = None
    try:
        history_event = build_event(
            event_type="report",
            system_name=descriptor.name,
            descriptor_path=str(Path(system_yaml).resolve()),
            risk_tier=compliance_report.risk_tier.value,
            summary=_history_summary(compliance_report),
            finding_statuses=_history_finding_statuses(compliance_report.findings),
            report_format=format,
        )
        append_event(history_event)
    except Exception as e:
        history_warning = str(e)

    if format == "pdf":
        if output is None:
            console.print(
                "[red]Error: --output/-o is required when --format pdf "
                "(binary output is not written to stdout).[/red]"
            )
            sys.exit(1)
        output_path = Path(output)
        output_path.write_bytes(report_bytes)
        console.print(f"[green]PDF report saved to: {output_path}[/green]")
    elif output:
        output_path = Path(output)
        output_path.write_text(report_content)
        console.print(f"[green]Report saved to: {output_path}[/green]")
    else:
        click.echo(report_content)

    if history_warning:
        click.echo(f"Warning: failed to write history event: {history_warning}", err=True)


@main.command()
@click.argument("system_yaml", type=click.Path(exists=True))
def validate(system_yaml: str) -> None:
    """
    Validate an AI system descriptor against the schema.

    Checks that the YAML file conforms to the AISystemDescriptor schema.

    Example:
      ai-act validate examples/medical_diagnosis.yaml
    """
    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
        console.print("[green]✓ System descriptor is valid![/green]")
        console.print(f"\nSystem: {descriptor.name} v{descriptor.version}")
        console.print(f"Use cases: {len(descriptor.use_cases)}")
        console.print(f"Data practices: {len(descriptor.data_practices)}")
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {system_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print("[red]Validation failed:[/red]")
        console.print(f"  {e}")
        sys.exit(1)


@main.command()
@click.option(
    "--tier",
    type=click.Choice(["minimal", "limited", "high_risk", "unacceptable"]),
    help="Filter by risk tier",
)
def articles(tier: str | None) -> None:
    """
    Display EU AI Act articles and requirements.

    Lists applicable articles from EU AI Act (Regulation 2024/1689).
    Can filter by risk tier to see requirements for specific classifications.

    Example:
      ai-act articles
      ai-act articles --tier high_risk
    """
    classifier = RiskClassifier()
    tier_order = [RiskTier.MINIMAL, RiskTier.LIMITED, RiskTier.HIGH_RISK, RiskTier.UNACCEPTABLE]
    articles_data = {
        risk_tier.value: classifier.get_applicable_articles(risk_tier) for risk_tier in tier_order
    }

    if tier:
        articles_list = articles_data.get(tier, [])
        console.print(f"[bold]Articles for {tier.upper()} risk tier:[/bold]")
        for article in articles_list:
            console.print(f"  • {article}")
    else:
        console.print("[bold]EU AI Act Articles[/bold]\n")
        for risk_tier, articles_list in articles_data.items():
            console.print(f"\n{risk_tier.upper()}:")
            for article in articles_list:
                console.print(f"  • {article}")


@main.group()
def dashboard() -> None:
    """Generate multi-system compliance dashboards."""
    pass


@dashboard.command("build")
@click.argument("descriptor_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--recursive", is_flag=True, help="Recursively scan descriptor directory")
@click.option("--include-history", is_flag=True, help="Include optional history trend section")
@click.option("--history-path", type=click.Path(), help="Override history JSONL path")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Output directory for dashboard.json and dashboard.html (default: current working directory)",
)
def dashboard_build(
    descriptor_dir: str,
    recursive: bool,
    include_history: bool,
    history_path: str | None,
    output_dir: str | None,
) -> None:
    """Build JSON and static HTML dashboard artifacts from descriptor files."""
    generator = DashboardGenerator()
    output_root = Path(output_dir).resolve() if output_dir else Path.cwd()
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        payload = generator.build(
            descriptor_dir=descriptor_dir,
            recursive=recursive,
            include_history=include_history,
            history_path=history_path,
        )
    except Exception as e:
        console.print(f"[red]Error building dashboard: {e}[/red]")
        sys.exit(1)

    json_path = output_root / "dashboard.json"
    html_path = output_root / "dashboard.html"
    json_path.write_text(generator.to_json(payload))
    html_path.write_text(generator.render_html(payload))

    console.print(f"[green]Dashboard JSON saved to: {json_path}[/green]")
    console.print(f"[green]Dashboard HTML saved to: {html_path}[/green]")

    if payload["invalid_descriptor_count"] > 0:
        console.print(
            f"[yellow]Skipped {payload['invalid_descriptor_count']} invalid descriptor file(s). "
            "See dashboard 'errors' section for details.[/yellow]"
        )

    if payload["valid_system_count"] == 0:
        console.print(
            "[red]No valid system descriptors found. Dashboard build marked as failed.[/red]"
        )
        sys.exit(1)


@main.group()
def history() -> None:
    """Inspect persisted audit history events."""
    pass


@history.command("list")
@click.option("--system", "system_name", help="Filter by exact system name")
@click.option(
    "--event-type",
    type=click.Choice(["check", "report"]),
    help="Filter by event type",
)
@click.option("--limit", type=int, help="Return at most N newest events")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--history-path", type=click.Path(), help="Override history JSONL path")
def history_list(
    system_name: str | None,
    event_type: str | None,
    limit: int | None,
    output_json: bool,
    history_path: str | None,
) -> None:
    """List persisted history events."""
    try:
        event_type_filter = cast(EventType | None, event_type if event_type else None)
        events = list_events(
            history_path=history_path,
            system=system_name,
            event_type=event_type_filter,
            limit=limit,
        )
    except Exception as e:
        console.print(f"[red]Error loading history events: {e}[/red]")
        sys.exit(1)

    resolved_path = resolve_history_path(history_path)
    if output_json:
        payload = {
            "history_path": str(resolved_path),
            "count": len(events),
            "events": [event.to_dict() for event in events],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    if not events:
        console.print(f"[yellow]No history events found at {resolved_path}[/yellow]")
        return

    table = Table(title=f"History Events ({resolved_path})")
    table.add_column("Event ID")
    table.add_column("Type")
    table.add_column("System")
    table.add_column("Risk Tier")
    table.add_column("Generated At")
    for event in events:
        table.add_row(
            event.event_id,
            event.event_type,
            event.system_name,
            event.risk_tier,
            event.generated_at,
        )
    console.print(table)


@history.command("show")
@click.argument("event_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--history-path", type=click.Path(), help="Override history JSONL path")
def history_show(event_id: str, output_json: bool, history_path: str | None) -> None:
    """Show details for one history event."""
    try:
        event = get_event(event_id, history_path=history_path)
    except Exception as e:
        console.print(f"[red]Error loading history event: {e}[/red]")
        sys.exit(1)

    if output_json:
        click.echo(json.dumps(event.to_dict(), indent=2))
        return

    report_format = event.report_format or "-"
    console.print(
        Panel(
            (
                f"[bold]Event:[/bold] {event.event_id}\n"
                f"[bold]Type:[/bold] {event.event_type}\n"
                f"[bold]System:[/bold] {event.system_name}\n"
                f"[bold]Descriptor:[/bold] {event.descriptor_path}\n"
                f"[bold]Risk Tier:[/bold] {event.risk_tier}\n"
                f"[bold]Generated At:[/bold] {event.generated_at}\n"
                f"[bold]Report Format:[/bold] {report_format}"
            ),
            title="History Event",
            border_style="blue",
        )
    )

    summary_table = Table(title="Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", justify="right")
    for field_name, value in event.summary.items():
        summary_table.add_row(field_name, str(value))
    console.print(summary_table)

    findings_table = Table(title="Finding Statuses")
    findings_table.add_column("Requirement")
    findings_table.add_column("Status")
    if event.finding_statuses:
        for requirement_id, status in sorted(event.finding_statuses.items()):
            findings_table.add_row(requirement_id, status)
    else:
        findings_table.add_row("-", "No findings")
    console.print(findings_table)


@history.command("diff")
@click.argument("older_event_id")
@click.argument("newer_event_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--history-path", type=click.Path(), help="Override history JSONL path")
def history_diff(
    older_event_id: str,
    newer_event_id: str,
    output_json: bool,
    history_path: str | None,
) -> None:
    """Diff two history events."""
    try:
        payload = diff_events(
            older_event_id,
            newer_event_id,
            history_path=history_path,
        )
    except Exception as e:
        console.print(f"[red]Error computing history diff: {e}[/red]")
        sys.exit(1)

    if output_json:
        click.echo(json.dumps(payload, indent=2))
        return

    risk_tier = payload["risk_tier_change"]
    console.print(
        Panel(
            (
                f"[bold]Older Event:[/bold] {payload['older_event_id']}\n"
                f"[bold]Newer Event:[/bold] {payload['newer_event_id']}\n"
                f"[bold]Older Generated At:[/bold] {payload['older_generated_at']}\n"
                f"[bold]Newer Generated At:[/bold] {payload['newer_generated_at']}\n"
                f"[bold]Risk Tier:[/bold] {risk_tier['from']} -> {risk_tier['to']} "
                f"(changed={risk_tier['changed']})"
            ),
            title="History Diff",
            border_style="blue",
        )
    )

    summary_table = Table(title="Summary Changes")
    summary_table.add_column("Metric")
    summary_table.add_column("From", justify="right")
    summary_table.add_column("To", justify="right")
    summary_table.add_column("Delta", justify="right")
    for metric, change in payload["summary_changes"].items():
        summary_table.add_row(metric, str(change["from"]), str(change["to"]), str(change["delta"]))
    console.print(summary_table)

    if payload["finding_status_changes"]:
        status_table = Table(title="Finding Status Changes")
        status_table.add_column("Requirement")
        status_table.add_column("From")
        status_table.add_column("To")
        for item in payload["finding_status_changes"]:
            status_table.add_row(item["requirement_id"], item["from"], item["to"])
        console.print(status_table)
    else:
        console.print("[yellow]No finding status changes.[/yellow]")

    if payload["added_findings"]:
        added_table = Table(title="Added Findings")
        added_table.add_column("Requirement")
        added_table.add_column("Status")
        for item in payload["added_findings"]:
            added_table.add_row(item["requirement_id"], item["status"])
        console.print(added_table)
    else:
        console.print("[yellow]No added findings.[/yellow]")

    if payload["removed_findings"]:
        removed_table = Table(title="Removed Findings")
        removed_table.add_column("Requirement")
        removed_table.add_column("Status")
        for item in payload["removed_findings"]:
            removed_table.add_row(item["requirement_id"], item["status"])
        console.print(removed_table)
    else:
        console.print("[yellow]No removed findings.[/yellow]")


@main.group()
def export() -> None:
    """Generate payload-only external export artifacts."""
    pass


@export.command("check")
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow", "generic"]),
    required=True,
    help="Export target adapter",
)
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option(
    "--history-path",
    type=click.Path(),
    help="Optional history path accepted for contract compatibility",
)
@click.option(
    "--push",
    is_flag=True,
    help="Push payload to target API (supported: jira, servicenow)",
)
@click.option(
    "--push-mode",
    type=click.Choice(["create", "upsert"]),
    default="create",
    show_default=True,
    help="Push strategy: create-only or upsert (lookup then update/create).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not call remote APIs; return simulated push summary.",
)
@click.option(
    "--max-retries",
    type=int,
    default=3,
    show_default=True,
    help="Maximum retry attempts for retryable push failures (429/5xx/transport).",
)
@click.option(
    "--retry-backoff-seconds",
    type=float,
    default=1.0,
    show_default=True,
    help="Base backoff in seconds for exponential retry delay.",
)
@click.option(
    "--timeout-seconds",
    type=float,
    default=30.0,
    show_default=True,
    help="HTTP request timeout in seconds for live push calls.",
)
@click.option(
    "--idempotency-path",
    type=click.Path(),
    help="Override export push idempotency ledger path.",
)
@click.option(
    "--disable-idempotency",
    is_flag=True,
    help="Disable duplicate-skip idempotency checks for live push.",
)
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload (default behavior)")
@click.pass_context
def export_check(
    ctx: click.Context,
    system_yaml: str,
    target: str,
    output: str | None,
    history_path: str | None,
    push: bool,
    push_mode: str,
    dry_run: bool,
    max_retries: int,
    retry_backoff_seconds: float,
    timeout_seconds: float,
    idempotency_path: str | None,
    disable_idempotency: bool,
    output_json: bool,
) -> None:
    """Export canonical + target-specific payload from live compliance check."""
    _ = output_json  # JSON is the only export format in this phase.

    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
    except FileNotFoundError:
        console.print(f"[red]Error: File not found: {system_yaml}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading system descriptor: {e}[/red]")
        sys.exit(1)

    if history_path:
        # Validate path resolution early for deterministic CLI behavior.
        resolve_history_path(history_path)

    if max_retries < 0:
        console.print("[red]Error: --max-retries must be >= 0[/red]")
        sys.exit(1)
    if retry_backoff_seconds <= 0:
        console.print("[red]Error: --retry-backoff-seconds must be > 0[/red]")
        sys.exit(1)
    if timeout_seconds <= 0:
        console.print("[red]Error: --timeout-seconds must be > 0[/red]")
        sys.exit(1)
    if not push and ctx.get_parameter_source("push_mode") == ParameterSource.COMMANDLINE:
        console.print("[red]Error: --push-mode can only be used together with --push[/red]")
        sys.exit(1)

    checker = ComplianceChecker()
    exporter = ExportGenerator()
    resolved_idempotency_path = (
        str(resolve_export_push_ledger_path(idempotency_path)) if not disable_idempotency else None
    )
    pusher = ExportPusher(
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        idempotency_path=idempotency_path,
        idempotency_enabled=not disable_idempotency,
    )

    with Progress(transient=True) as progress:
        progress.add_task("Generating export payload...", total=None)
        compliance_report = checker.check(descriptor)
        payload = exporter.from_check(
            report=compliance_report,
            target=cast(ExportTarget, target),
            descriptor_path=str(Path(system_yaml).resolve()),
        )

    payload_dict = payload.to_dict()
    if push:
        try:
            push_result = pusher.push(
                payload,
                dry_run=dry_run,
                push_mode=cast(PushMode, push_mode),
            )
        except ExportPushError as e:
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        payload_dict["push_result"] = push_result
    elif dry_run:
        payload_dict["push_result"] = {
            "target": target,
            "dry_run": True,
            "push_mode": cast(PushMode, push_mode),
            "attempted_actionable_count": sum(1 for item in payload.items if item.actionable),
            "pushed_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "failed_count": 0,
            "skipped_duplicate_count": 0,
            "failure_reason": None,
            "max_retries": max_retries,
            "retry_backoff_seconds": retry_backoff_seconds,
            "timeout_seconds": timeout_seconds,
            "idempotency_enabled": not disable_idempotency,
            "idempotency_path": resolved_idempotency_path,
            "results": [],
            "message": "Dry-run requested without --push; no remote API call was made.",
        }

    payload_json = json.dumps(payload_dict, indent=2)
    _emit_export_output(payload_json, output)


@export.command("history")
@click.argument("event_id")
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow", "generic"]),
    required=True,
    help="Export target adapter",
)
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--history-path", type=click.Path(), help="Override history JSONL path")
@click.option(
    "--push",
    is_flag=True,
    help="Push payload to target API (supported: jira, servicenow)",
)
@click.option(
    "--push-mode",
    type=click.Choice(["create", "upsert"]),
    default="create",
    show_default=True,
    help="Push strategy: create-only or upsert (lookup then update/create).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not call remote APIs; return simulated push summary.",
)
@click.option(
    "--max-retries",
    type=int,
    default=3,
    show_default=True,
    help="Maximum retry attempts for retryable push failures (429/5xx/transport).",
)
@click.option(
    "--retry-backoff-seconds",
    type=float,
    default=1.0,
    show_default=True,
    help="Base backoff in seconds for exponential retry delay.",
)
@click.option(
    "--timeout-seconds",
    type=float,
    default=30.0,
    show_default=True,
    help="HTTP request timeout in seconds for live push calls.",
)
@click.option(
    "--idempotency-path",
    type=click.Path(),
    help="Override export push idempotency ledger path.",
)
@click.option(
    "--disable-idempotency",
    is_flag=True,
    help="Disable duplicate-skip idempotency checks for live push.",
)
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload (default behavior)")
@click.pass_context
def export_history(
    ctx: click.Context,
    event_id: str,
    target: str,
    output: str | None,
    history_path: str | None,
    push: bool,
    push_mode: str,
    dry_run: bool,
    max_retries: int,
    retry_backoff_seconds: float,
    timeout_seconds: float,
    idempotency_path: str | None,
    disable_idempotency: bool,
    output_json: bool,
) -> None:
    """Export canonical + target-specific payload from a persisted history event."""
    _ = output_json  # JSON is the only export format in this phase.

    try:
        event = get_event(event_id, history_path=history_path)
    except Exception as e:
        console.print(f"[red]Error loading history event: {e}[/red]")
        sys.exit(1)

    if max_retries < 0:
        console.print("[red]Error: --max-retries must be >= 0[/red]")
        sys.exit(1)
    if retry_backoff_seconds <= 0:
        console.print("[red]Error: --retry-backoff-seconds must be > 0[/red]")
        sys.exit(1)
    if timeout_seconds <= 0:
        console.print("[red]Error: --timeout-seconds must be > 0[/red]")
        sys.exit(1)
    if not push and ctx.get_parameter_source("push_mode") == ParameterSource.COMMANDLINE:
        console.print("[red]Error: --push-mode can only be used together with --push[/red]")
        sys.exit(1)

    exporter = ExportGenerator()
    resolved_idempotency_path = (
        str(resolve_export_push_ledger_path(idempotency_path)) if not disable_idempotency else None
    )
    pusher = ExportPusher(
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        idempotency_path=idempotency_path,
        idempotency_enabled=not disable_idempotency,
    )
    payload = exporter.from_history(
        event=event,
        target=cast(ExportTarget, target),
    )
    payload_dict = payload.to_dict()
    if push:
        try:
            push_result = pusher.push(
                payload,
                dry_run=dry_run,
                push_mode=cast(PushMode, push_mode),
            )
        except ExportPushError as e:
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        payload_dict["push_result"] = push_result
    elif dry_run:
        payload_dict["push_result"] = {
            "target": target,
            "dry_run": True,
            "push_mode": cast(PushMode, push_mode),
            "attempted_actionable_count": sum(1 for item in payload.items if item.actionable),
            "pushed_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "failed_count": 0,
            "skipped_duplicate_count": 0,
            "failure_reason": None,
            "max_retries": max_retries,
            "retry_backoff_seconds": retry_backoff_seconds,
            "timeout_seconds": timeout_seconds,
            "idempotency_enabled": not disable_idempotency,
            "idempotency_path": resolved_idempotency_path,
            "results": [],
            "message": "Dry-run requested without --push; no remote API call was made.",
        }

    payload_json = json.dumps(payload_dict, indent=2)
    _emit_export_output(payload_json, output)


@export.group("ledger")
def export_ledger() -> None:
    """Inspect persisted export push idempotency ledger records."""
    pass


@export_ledger.command("list")
@click.option("--idempotency-path", type=click.Path(), help="Override ledger path")
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow", "generic"]),
    help="Filter by target adapter",
)
@click.option("--system", "system_name", help="Filter by system name")
@click.option("--requirement-id", help="Filter by requirement id")
@click.option(
    "--limit",
    type=int,
    default=25,
    show_default=True,
    help="Maximum number of records to return",
)
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload")
def export_ledger_list(
    idempotency_path: str | None,
    target: str | None,
    system_name: str | None,
    requirement_id: str | None,
    limit: int,
    output_json: bool,
) -> None:
    """List export push ledger records."""
    if limit < 1:
        console.print("[red]Error: --limit must be >= 1[/red]")
        sys.exit(1)

    try:
        ledger_path, records = list_export_push_ledger_records(
            idempotency_path=idempotency_path,
            target=cast(ExportTarget | None, target),
            system_name=system_name,
            requirement_id=requirement_id,
            limit=limit,
        )
    except Exception as e:
        console.print(f"[red]Error reading export ledger: {e}[/red]")
        sys.exit(1)

    payload = {
        "path": str(ledger_path),
        "count": len(records),
        "filters": {
            "target": target,
            "system_name": system_name,
            "requirement_id": requirement_id,
            "limit": limit,
        },
        "records": records,
    }

    if output_json:
        click.echo(json.dumps(payload, indent=2))
        return

    console.print(
        Panel(
            (f"[bold]Ledger:[/bold] {payload['path']}\n" f"[bold]Count:[/bold] {payload['count']}"),
            title="Export Ledger Records",
            border_style="blue",
        )
    )
    if not records:
        console.print("[yellow]No records found for the selected filters.[/yellow]")
        return

    table = Table(title="Latest Export Ledger Records")
    table.add_column("Pushed At")
    table.add_column("Target")
    table.add_column("System")
    table.add_column("Requirement")
    table.add_column("Status")
    table.add_column("Remote Ref")
    for record in records:
        table.add_row(
            str(record.get("pushed_at") or ""),
            str(record.get("target") or ""),
            str(record.get("system_name") or ""),
            str(record.get("requirement_id") or ""),
            str(record.get("status") or ""),
            str(record.get("remote_ref") or ""),
        )
    console.print(table)


@export_ledger.command("stats")
@click.option("--idempotency-path", type=click.Path(), help="Override ledger path")
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload")
def export_ledger_stats(idempotency_path: str | None, output_json: bool) -> None:
    """Show aggregate statistics for export push ledger."""
    try:
        summary = summarize_export_push_ledger(idempotency_path=idempotency_path)
    except Exception as e:
        console.print(f"[red]Error reading export ledger stats: {e}[/red]")
        sys.exit(1)

    if output_json:
        click.echo(json.dumps(summary, indent=2))
        return

    console.print(
        Panel(
            (
                f"[bold]Ledger:[/bold] {summary['path']}\n"
                f"[bold]Total Records:[/bold] {summary['total_records']}\n"
                f"[bold]Unique Keys:[/bold] {summary['unique_idempotency_key_count']}\n"
                f"[bold]First Push:[/bold] {summary['first_pushed_at']}\n"
                f"[bold]Last Push:[/bold] {summary['last_pushed_at']}"
            ),
            title="Export Ledger Stats",
            border_style="green",
        )
    )

    target_table = Table(title="Target Distribution")
    target_table.add_column("Target")
    target_table.add_column("Count", justify="right")
    for key, value in summary["target_distribution"].items():
        target_table.add_row(key, str(value))
    console.print(target_table)

    status_table = Table(title="Status Distribution")
    status_table.add_column("Status")
    status_table.add_column("Count", justify="right")
    for key, value in summary["status_distribution"].items():
        status_table.add_row(key, str(value))
    console.print(status_table)


def _emit_export_output(payload_json: str, output: str | None) -> None:
    """Emit export payload either to stdout or to a file."""
    if output:
        output_path = Path(output)
        output_path.write_text(payload_json, encoding="utf-8")
        console.print(f"[green]Export payload saved to: {output_path}[/green]")
        return
    click.echo(payload_json)


def _collect_transparency_findings(
    checker: TransparencyChecker, descriptor: AISystemDescriptor
) -> list[TransparencyFinding]:
    """Collect all transparency findings for a descriptor."""
    findings = []
    findings.extend(checker.check_art50_disclosure(descriptor))
    findings.append(checker.check_deepfake_detection(descriptor))
    findings.extend(checker.check_gpai_obligations(descriptor))
    return findings


def _build_gpai_model_info_from_descriptor(descriptor: AISystemDescriptor) -> GPAIModelInfo:
    """Build best-effort GPAI model info from system descriptor signals."""
    text = " ".join(
        [
            descriptor.name,
            descriptor.description,
            descriptor.training_data_source,
            descriptor.incident_procedure or "",
            " ".join(use_case.description for use_case in descriptor.use_cases),
        ]
    ).lower()
    return GPAIModelInfo(
        model_name=descriptor.name,
        provider="unknown",
        training_compute_flops=None,
        model_params_billion=None,
        eu_monthly_users=None,
        supports_tool_use=any(
            keyword in text for keyword in ["tool use", "function calling", "agent"]
        ),
        autonomous_task_execution=any(
            use_case.autonomous_decision for use_case in descriptor.use_cases
        ),
        generates_synthetic_media=any(
            keyword in text
            for keyword in ["generated", "generative", "synthetic", "deepfake", "chatbot"]
        ),
        model_card_available="model card" in text or descriptor.documentation,
        training_data_documented=descriptor.documentation
        and len(descriptor.training_data_source.strip()) >= 20,
        systemic_risk_mitigation_plan=bool(
            descriptor.incident_procedure and descriptor.incident_procedure.strip()
        ),
        post_market_monitoring=descriptor.performance_monitoring,
    )


def _build_gpai_summary(assessment: GPAIAssessment, descriptor: AISystemDescriptor) -> dict:
    """Build compact GPAI summary payload for check/report outputs."""
    gpai_text = f"{descriptor.description} {descriptor.training_data_source}".lower()
    gpai_applicable = any(
        use_case.domain == UseCaseDomain.GENERAL_PURPOSE for use_case in descriptor.use_cases
    ) or any(
        keyword in gpai_text
        for keyword in [
            "general purpose",
            "foundation model",
            "large language",
            "multimodal",
            "broad training",
        ]
    )

    return {
        "applicable": gpai_applicable,
        "systemic_risk_flag": assessment.systemic_risk_flag,
        "total_findings": len(assessment.findings),
        "actionable_gaps": len(assessment.compliance_gaps),
    }


def _serialize_transparency_finding(finding: TransparencyFinding) -> dict:
    """Serialize transparency finding for JSON responses."""
    return {
        "requirement_id": finding.requirement_id,
        "status": finding.status.value,
        "severity": finding.severity,
        "title": finding.title,
        "description": finding.description,
        "gap_analysis": finding.gap_analysis,
        "recommendations": finding.recommendations,
    }


def _serialize_gpai_finding(finding) -> dict:
    """Serialize GPAI finding for JSON responses."""
    return {
        "requirement_id": finding.requirement_id,
        "status": finding.status.value,
        "severity": finding.severity,
        "title": finding.title,
        "description": finding.description,
        "gap_analysis": finding.gap_analysis,
        "recommendations": finding.recommendations,
    }


def _history_summary(report_result) -> dict:
    """Build compact summary payload for history events."""
    return {
        "total_requirements": report_result.summary.total_requirements,
        "compliant_count": report_result.summary.compliant_count,
        "non_compliant_count": report_result.summary.non_compliant_count,
        "partial_count": report_result.summary.partial_count,
        "not_assessed_count": report_result.summary.not_assessed_count,
        "compliance_percentage": round(report_result.summary.compliance_percentage, 2),
    }


def _history_finding_statuses(findings: dict) -> dict:
    """Build requirement-to-status map for history events."""
    return {requirement_id: finding.status.value for requirement_id, finding in findings.items()}


if __name__ == "__main__":
    main()
