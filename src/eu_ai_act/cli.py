"""
Command-Line Interface for EU AI Act Compliance Kit

Provides CLI commands for risk classification, compliance checking,
checklist generation, and report generation.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click
import yaml
from click.core import ParameterSource
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table

from eu_ai_act.checker import ComplianceChecker
from eu_ai_act.checklist import ChecklistGenerator
from eu_ai_act.classifier import RiskClassifier
from eu_ai_act.collaboration import (
    WorkflowStatus,
    list_collaboration_tasks,
    summarize_collaboration_gate_metrics,
    summarize_collaboration_tasks,
    sync_collaboration_tasks,
    update_collaboration_task,
)
from eu_ai_act.collaboration_gate import (
    CollaborationGateEvaluator,
    resolve_collaboration_gate_policy,
)
from eu_ai_act.dashboard import DashboardGenerator
from eu_ai_act.export_ops_gate import (
    ExportOpsGateEvaluator,
    resolve_export_ops_gate_policy,
)
from eu_ai_act.exporter import (
    ExportGenerator,
    ExportPusher,
    ExportPushError,
    ExportTarget,
    PushMode,
    build_simulated_push_result,
    list_export_push_ledger_records,
    reconcile_export_push_records,
    replay_export_push_failures,
    resolve_export_push_ledger_path,
    run_export_batch,
    summarize_export_ops_rollup,
    summarize_export_push_ledger,
    summarize_export_reconcile_log,
)
from eu_ai_act.governance_handoff import (
    build_governance_decision,
    resolve_governance_handoff_policy,
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
from eu_ai_act.ops_closeout import (
    OpsCloseoutCheck,
    OpsCloseoutEvaluator,
    build_ops_closeout_escalation_decision,
    resolve_latest_release_inputs,
    resolve_ops_closeout_policy,
)
from eu_ai_act.reporter import ReportGenerator
from eu_ai_act.schema import (
    AISystemDescriptor,
    RiskTier,
    UseCaseDomain,
    load_system_descriptor_from_file,
)
from eu_ai_act.security_gate import SecurityGateEvaluator
from eu_ai_act.security_mapping import SecurityMapper
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
@click.option(
    "--security-gate",
    "security_gate_mode",
    type=click.Choice(["observe", "enforce"], case_sensitive=False),
    default="observe",
    show_default=True,
    help="Security gate mode. observe never blocks, enforce applies profile thresholds.",
)
@click.option(
    "--security-gate-profile",
    type=click.Choice(["strict", "balanced", "lenient"], case_sensitive=False),
    default="balanced",
    show_default=True,
    help="Security gate profile. Used when --security-gate=enforce.",
)
def check(
    system_yaml: str,
    output_json: bool,
    security_gate_mode: str,
    security_gate_profile: str,
) -> None:
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
    security_mapper = SecurityMapper()
    security_gate_evaluator = SecurityGateEvaluator()

    with Progress(transient=True) as progress:
        progress.add_task("Checking compliance...", total=None)
        report_result = checker.check(descriptor)
        articles_applicable = classifier.get_applicable_articles(report_result.risk_tier)
        transparency_findings = _collect_transparency_findings(transparency_checker, descriptor)
        gpai_assessment = gpai_assessor.assess(_build_gpai_model_info_from_descriptor(descriptor))
        gpai_summary = _build_gpai_summary(gpai_assessment, descriptor)
        security_mapping = security_mapper.map_from_compliance(report_result)

    security_summary_payload = {
        "framework": security_mapping.framework,
        **security_mapping.summary.to_dict(),
    }
    security_gate_result = security_gate_evaluator.evaluate(
        security_summary=security_summary_payload,
        mode=security_gate_mode,
        profile=security_gate_profile,
        risk_tier=report_result.risk_tier.value,
    )

    history_warning = None
    try:
        history_event = build_event(
            event_type="check",
            system_name=descriptor.name,
            descriptor_path=str(Path(system_yaml).resolve()),
            risk_tier=report_result.risk_tier.value,
            summary=_history_summary(report_result),
            finding_statuses=_history_finding_statuses(report_result.findings),
            security_summary=_history_security_summary(security_mapping),
        )
        append_event(history_event)
    except Exception as e:
        history_warning = str(e)

    if output_json:
        output = _build_check_output_payload(
            descriptor=descriptor,
            report_result=report_result,
            articles_applicable=articles_applicable,
            transparency_findings=transparency_findings,
            gpai_summary=gpai_summary,
            security_summary_payload=security_summary_payload,
            security_gate_result=security_gate_result,
        )
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

        security_table = Table(title="Security Mapping (OWASP LLM Top 10)")
        security_table.add_column("Metric", style="cyan")
        security_table.add_column("Value", justify="right")
        security_table.add_row("Total Controls", str(security_mapping.summary.total_controls))
        security_table.add_row("Compliant", str(security_mapping.summary.compliant_count))
        security_table.add_row("Non-compliant", str(security_mapping.summary.non_compliant_count))
        security_table.add_row("Partial", str(security_mapping.summary.partial_count))
        security_table.add_row("Not Assessed", str(security_mapping.summary.not_assessed_count))
        security_table.add_row(
            "Coverage %",
            f"{security_mapping.summary.coverage_percentage:.1f}",
        )
        console.print(security_table)

        gate_table = Table(title="Security Gate")
        gate_table.add_column("Metric", style="cyan")
        gate_table.add_column("Value", justify="right")
        gate_table.add_row("Mode", security_gate_result.mode)
        gate_table.add_row("Profile", security_gate_result.profile)
        gate_table.add_row("Effective Profile", security_gate_result.effective_profile)
        gate_table.add_row("Failed", "yes" if security_gate_result.failed else "no")
        gate_table.add_row("Reason", security_gate_result.reason)
        gate_table.add_row("Non-compliant Controls", str(security_gate_result.non_compliant_count))
        gate_table.add_row("Partial Controls", str(security_gate_result.partial_count))
        gate_table.add_row("Not Assessed Controls", str(security_gate_result.not_assessed_count))
        console.print(gate_table)

    if history_warning:
        click.echo(f"Warning: failed to write history event: {history_warning}", err=True)

    if security_gate_result.failed:
        if not output_json:
            click.echo(
                (
                    "Security gate enforcement failed: "
                    f"mode={security_gate_result.mode}, "
                    f"profile={security_gate_result.profile}, "
                    f"effective_profile={security_gate_result.effective_profile}, "
                    f"reason={security_gate_result.reason}."
                ),
                err=True,
            )
        sys.exit(1)


@main.command("security-map")
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON instead of human-readable format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (writes JSON payload)",
)
def security_map(system_yaml: str, output_json: bool, output: str | None) -> None:
    """
    Map compliance findings to OWASP LLM Top 10 controls.

    Example:
      ai-act security-map examples/medical_diagnosis.yaml --json
      ai-act security-map examples/hiring_tool.yaml --json -o security_map.json
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
    security_mapper = SecurityMapper()

    with Progress(transient=True) as progress:
        progress.add_task("Building security mapping...", total=None)
        report_result = checker.check(descriptor)
        security_mapping = security_mapper.map_from_compliance(report_result)

    payload = {
        "system_name": descriptor.name,
        "risk_tier": report_result.risk_tier.value,
        "generated_at": security_mapping.generated_at,
        "framework": security_mapping.framework,
        "summary": security_mapping.summary.to_dict(),
        "controls": [control.to_dict() for control in security_mapping.controls],
    }

    payload_json = json.dumps(payload, indent=2)
    if output:
        output_path = Path(output)
        output_path.write_text(payload_json, encoding="utf-8")
        console.print(f"[green]Security mapping saved to: {output_path}[/green]")
        return

    if output_json:
        click.echo(payload_json)
        return

    table = Table(title=f"Security Mapping (OWASP LLM Top 10): {descriptor.name}")
    table.add_column("Control")
    table.add_column("Status")
    table.add_column("Severity")
    table.add_column("Linked Requirements")
    for control in security_mapping.controls:
        table.add_row(
            control.control_id,
            control.status.value,
            control.severity,
            ", ".join(control.linked_requirements),
        )
    console.print(table)


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
    security_mapper = SecurityMapper()

    with Progress(transient=True) as progress:
        progress.add_task("Generating report...", total=None)
        classification = classifier.classify(descriptor)
        compliance_report = checker.check(descriptor)
        transparency_findings = _collect_transparency_findings(transparency_checker, descriptor)
        gpai_assessment = gpai_assessor.assess(_build_gpai_model_info_from_descriptor(descriptor))
        security_mapping = security_mapper.map_from_compliance(compliance_report)
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
            security_summary=_history_security_summary(security_mapping),
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
@click.argument("system_yaml", type=click.Path())
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Output directory for handoff artifacts (default: current working directory)",
)
@click.option(
    "--governance",
    is_flag=True,
    help="Evaluate governance gates and emit governance_gate.json artifact.",
)
@click.option(
    "--governance-mode",
    type=click.Choice(["observe", "enforce"]),
    default="observe",
    show_default=True,
    help="Governance mode. enforce returns non-zero when governance gate fails.",
)
@click.option(
    "--export-target",
    type=click.Choice(["jira", "servicenow"]),
    help="Optional export target to include export-ops governance in handoff output.",
)
@click.option(
    "--governance-policy",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional governance policy YAML path (precedence: CLI flags > policy > defaults).",
)
@click.option("--json", "output_json", is_flag=True, help="Output handoff manifest as JSON")
def handoff(
    system_yaml: str,
    output_dir: str | None,
    governance: bool,
    governance_mode: str,
    export_target: str | None,
    governance_policy: str | None,
    output_json: bool,
) -> None:
    """
    Run one-command GA handoff flow and write deterministic artifacts.

    Flow:
      validate -> classify --json -> check --json -> security-map --json
      -> checklist (json+md) -> report --format html -> collaboration sync+summary
    """
    if export_target is not None and not governance:
        console.print("[red]Error: --export-target requires --governance[/red]")
        sys.exit(1)
    if governance_policy is not None and not governance:
        console.print("[red]Error: --governance-policy requires --governance[/red]")
        sys.exit(1)

    output_root = Path(output_dir).resolve() if output_dir else Path.cwd().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    descriptor_abs_path = str(Path(system_yaml).resolve())
    manifest: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "system_name": None,
        "descriptor_path": descriptor_abs_path,
        "status": "failed",
        "risk_tier": None,
        "articles_applicable": [],
        "compliance_summary": None,
        "security_summary": None,
        "collaboration_summary": None,
        "governance_summary": None,
        "governance_failed": False,
        "governance_reason_codes": [],
        "artifacts": {},
        "failed_step": None,
        "error": None,
    }
    governance_enforced_failure = False
    governance_policy_payload: dict[str, object] = {}

    classifier = RiskClassifier()
    checker = ComplianceChecker()
    checklist_generator = ChecklistGenerator()
    report_generator = ReportGenerator()
    transparency_checker = TransparencyChecker()
    gpai_assessor = GPAIAssessor()
    security_mapper = SecurityMapper()
    security_gate_evaluator = SecurityGateEvaluator()

    current_step = "setup"
    try:
        if governance:
            current_step = "governance_policy"
            governance_policy_payload = _load_governance_handoff_policy_file(governance_policy)

        current_step = "validate"
        descriptor = load_system_descriptor_from_file(system_yaml)
        manifest["system_name"] = descriptor.name
        validate_payload = {
            "system_name": descriptor.name,
            "version": descriptor.version,
            "valid": True,
            "use_case_count": len(descriptor.use_cases),
            "data_practice_count": len(descriptor.data_practices),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        validate_path = output_root / "validate.json"
        validate_path.write_text(json.dumps(validate_payload, indent=2), encoding="utf-8")
        cast(dict[str, str], manifest["artifacts"])["validate.json"] = str(validate_path)

        current_step = "classify"
        classification = classifier.classify(descriptor)
        classify_payload = {
            "system_name": descriptor.name,
            "risk_tier": classification.tier.value,
            "confidence": classification.confidence,
            "reasoning": classification.reasoning,
            "contributing_factors": classification.contributing_factors,
            "articles_applicable": classification.articles_applicable,
        }
        classify_path = output_root / "classify.json"
        classify_path.write_text(json.dumps(classify_payload, indent=2), encoding="utf-8")
        cast(dict[str, str], manifest["artifacts"])["classify.json"] = str(classify_path)

        current_step = "check"
        compliance_report = checker.check(descriptor)
        articles_applicable = classifier.get_applicable_articles(compliance_report.risk_tier)
        transparency_findings = _collect_transparency_findings(transparency_checker, descriptor)
        gpai_assessment = gpai_assessor.assess(_build_gpai_model_info_from_descriptor(descriptor))
        gpai_summary = _build_gpai_summary(gpai_assessment, descriptor)
        security_mapping = security_mapper.map_from_compliance(compliance_report)
        security_summary_payload = {
            "framework": security_mapping.framework,
            **security_mapping.summary.to_dict(),
        }
        security_gate_result = security_gate_evaluator.evaluate(
            security_summary=security_summary_payload,
            mode="observe",
            profile="balanced",
            risk_tier=compliance_report.risk_tier.value,
        )

        check_payload = _build_check_output_payload(
            descriptor=descriptor,
            report_result=compliance_report,
            articles_applicable=articles_applicable,
            transparency_findings=transparency_findings,
            gpai_summary=gpai_summary,
            security_summary_payload=security_summary_payload,
            security_gate_result=security_gate_result,
        )
        check_path = output_root / "check.json"
        check_path.write_text(json.dumps(check_payload, indent=2), encoding="utf-8")
        cast(dict[str, str], manifest["artifacts"])["check.json"] = str(check_path)
        manifest["risk_tier"] = compliance_report.risk_tier.value
        manifest["articles_applicable"] = articles_applicable
        manifest["compliance_summary"] = check_payload["summary"]
        manifest["security_summary"] = security_summary_payload
        check_summary_payload = cast(dict[str, object], check_payload["summary"])
        current_run_actionable_count = (
            cast(int, check_summary_payload["non_compliant_count"])
            + cast(int, check_summary_payload["partial_count"])
            + cast(int, check_summary_payload["not_assessed_count"])
        )

        current_step = "security_map"
        security_map_payload = {
            "system_name": descriptor.name,
            "risk_tier": compliance_report.risk_tier.value,
            "generated_at": security_mapping.generated_at,
            "framework": security_mapping.framework,
            "summary": security_mapping.summary.to_dict(),
            "controls": [control.to_dict() for control in security_mapping.controls],
        }
        security_map_path = output_root / "security_map.json"
        security_map_path.write_text(json.dumps(security_map_payload, indent=2), encoding="utf-8")
        cast(dict[str, str], manifest["artifacts"])["security_map.json"] = str(security_map_path)

        current_step = "checklist"
        checklist_result = checklist_generator.generate(
            descriptor=descriptor,
            tier=compliance_report.risk_tier,
            findings=compliance_report.findings,
            generated_at=compliance_report.generated_at,
        )
        checklist_json_path = output_root / "checklist.json"
        checklist_md_path = output_root / "checklist.md"
        checklist_json_path.write_text(checklist_result.to_json(), encoding="utf-8")
        checklist_md_path.write_text(checklist_result.to_markdown(), encoding="utf-8")
        cast(dict[str, str], manifest["artifacts"])["checklist.json"] = str(checklist_json_path)
        cast(dict[str, str], manifest["artifacts"])["checklist.md"] = str(checklist_md_path)

        current_step = "report_html"
        report_html = report_generator.generate_report(
            descriptor=descriptor,
            classification=classification,
            compliance_report=compliance_report,
            transparency_findings=transparency_findings,
            gpai_assessment=gpai_assessment,
            checklist=checklist_result,
            format="html",
        )
        report_html_path = output_root / "report.html"
        report_html_path.write_text(report_html, encoding="utf-8")
        cast(dict[str, str], manifest["artifacts"])["report.html"] = str(report_html_path)

        current_step = "collaboration"
        sync_payload = sync_collaboration_tasks(
            report=compliance_report,
            descriptor_path=system_yaml,
        )
        summary_payload = summarize_collaboration_tasks(system_name=descriptor.name)
        collaboration_summary_payload = {
            **summary_payload,
            "sync_changes": sync_payload["changes"],
            "system_task_count": sync_payload["system_task_count"],
        }
        collaboration_summary_path = output_root / "collaboration_summary.json"
        collaboration_summary_path.write_text(
            json.dumps(collaboration_summary_payload, indent=2),
            encoding="utf-8",
        )
        cast(dict[str, str], manifest["artifacts"])["collaboration_summary.json"] = str(
            collaboration_summary_path
        )
        manifest["collaboration_summary"] = {
            "count": summary_payload["count"],
            "open_count": summary_payload["open_count"],
            "in_review_count": summary_payload["in_review_count"],
            "blocked_count": summary_payload["blocked_count"],
            "done_count": summary_payload["done_count"],
            "system_task_count": sync_payload["system_task_count"],
        }

        if governance:
            current_step = "governance"
            ctx = click.get_current_context()
            governance_mode_override: str | None = None
            if ctx.get_parameter_source("governance_mode") == ParameterSource.COMMANDLINE:
                governance_mode_override = governance_mode
            export_target_override: str | None = None
            if export_target is not None and (
                ctx.get_parameter_source("export_target") == ParameterSource.COMMANDLINE
            ):
                export_target_override = export_target

            governance_policy_resolved = resolve_governance_handoff_policy(
                policy_payload=governance_policy_payload,
                mode=governance_mode_override,
                export_target=export_target_override,
            )

            security_gate_payload: dict[str, object] | None = None
            if governance_policy_resolved.security_enabled:
                governance_security_gate_result = security_gate_evaluator.evaluate(
                    security_summary=security_summary_payload,
                    mode=governance_policy_resolved.mode,
                    profile=governance_policy_resolved.security_profile,
                    risk_tier=compliance_report.risk_tier.value,
                )
                security_gate_payload = governance_security_gate_result.to_dict()

            collaboration_gate_payload: dict[str, object] | None = None
            if governance_policy_resolved.collaboration_enabled:
                collaboration_policy = resolve_collaboration_gate_policy(
                    policy_payload=governance_policy_resolved.collaboration_policy,
                    mode=governance_policy_resolved.mode,
                    system_name=descriptor.name,
                )
                collaboration_metrics = summarize_collaboration_gate_metrics(
                    system_name=descriptor.name,
                    limit=collaboration_policy.limit,
                    stale_after_hours=collaboration_policy.stale_after_hours,
                    blocked_stale_after_hours=collaboration_policy.blocked_stale_after_hours,
                    review_stale_after_hours=collaboration_policy.review_stale_after_hours,
                )
                if current_run_actionable_count == 0 and not bool(
                    collaboration_metrics.get("has_collaboration_data", False)
                ):
                    # No actionable findings in the current handoff run should not be treated as
                    # missing collaboration data in enforce mode.
                    collaboration_metrics["has_collaboration_data"] = True
                collaboration_gate_result = CollaborationGateEvaluator().evaluate(
                    policy=collaboration_policy,
                    metrics=collaboration_metrics,
                )
                collaboration_gate_payload = {
                    "mode": collaboration_gate_result.mode,
                    "failed": collaboration_gate_result.failed,
                    "reason_codes": collaboration_gate_result.reason_codes,
                    "effective_policy": collaboration_policy.to_dict(),
                    "metrics": collaboration_metrics,
                    "decision_details": collaboration_gate_result.decision_details,
                }

            export_gate_payload: dict[str, object] | None = None
            if governance_policy_resolved.export_ops_enabled:
                resolved_export_target = governance_policy_resolved.export_target
                if resolved_export_target is None:
                    raise ValueError(
                        "Export ops governance gate is enabled but export target is missing."
                    )
                export_policy = resolve_export_ops_gate_policy(
                    policy_payload=governance_policy_resolved.export_ops_policy,
                    mode=governance_policy_resolved.mode,
                )
                export_rollup_payload = summarize_export_ops_rollup(
                    target=cast(ExportTarget, resolved_export_target),
                    system_name=descriptor.name,
                    since_hours=export_policy.since_hours,
                    limit=export_policy.limit,
                )
                export_reconcile_payload = summarize_export_reconcile_log(
                    target=cast(ExportTarget, resolved_export_target),
                    system_name=descriptor.name,
                    since_hours=export_policy.since_hours,
                    limit=export_policy.limit,
                )
                export_gate_result = ExportOpsGateEvaluator().evaluate(
                    policy=export_policy,
                    rollup_metrics=cast(dict, export_rollup_payload.get("metrics", {})),
                    reconcile_metrics=cast(dict, export_reconcile_payload.get("metrics", {})),
                )
                export_gate_payload = {
                    "mode": export_gate_result.mode,
                    "failed": export_gate_result.failed,
                    "reason_codes": export_gate_result.reason_codes,
                    "effective_policy": export_policy.to_dict(),
                    "rollup_metrics": export_rollup_payload.get("metrics", {}),
                    "reconcile_metrics": export_reconcile_payload.get("metrics", {}),
                    "decision_details": export_gate_result.decision_details,
                    "ops_path": export_rollup_payload.get("ops_path"),
                    "reconcile_log_path": export_reconcile_payload.get("path"),
                }

            governance_decision = build_governance_decision(
                mode=governance_policy_resolved.mode,
                security_gate=security_gate_payload,
                collaboration_gate=collaboration_gate_payload,
                export_ops_gate=export_gate_payload,
            )
            governance_payload = {
                "generated_at": datetime.now(UTC).isoformat(),
                "system_name": descriptor.name,
                "mode": governance_decision.mode,
                "failed": governance_decision.failed,
                "reason_codes": governance_decision.reason_codes,
                "evaluated_gates": governance_decision.evaluated_gates,
                "failed_gates": governance_decision.failed_gates,
                "security_gate": security_gate_payload,
                "collaboration_gate": collaboration_gate_payload,
                "export_ops_gate": export_gate_payload,
                "export_target": governance_policy_resolved.export_target,
                "effective_policy": governance_policy_resolved.to_dict(),
            }
            governance_path = output_root / "governance_gate.json"
            governance_path.write_text(json.dumps(governance_payload, indent=2), encoding="utf-8")
            cast(dict[str, str], manifest["artifacts"])["governance_gate.json"] = str(
                governance_path
            )
            manifest["governance_summary"] = {
                "mode": governance_payload["mode"],
                "failed": governance_payload["failed"],
                "reason_codes": governance_payload["reason_codes"],
                "evaluated_gates": governance_payload["evaluated_gates"],
                "failed_gates": governance_payload["failed_gates"],
            }
            manifest["governance_failed"] = governance_payload["failed"]
            manifest["governance_reason_codes"] = governance_payload["reason_codes"]
            governance_enforced_failure = (
                governance_policy_resolved.mode == "enforce" and governance_decision.failed
            )

        manifest["status"] = "success"
    except Exception as e:
        if manifest.get("system_name") is None:
            manifest["system_name"] = Path(system_yaml).stem
        manifest["status"] = "failed"
        manifest["failed_step"] = current_step
        manifest["error"] = str(e)

    manifest_path = output_root / "handoff_manifest.json"
    cast(dict[str, str], manifest["artifacts"])["handoff_manifest.json"] = str(manifest_path)
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception as exc:
        click.echo(f"Warning: failed to write handoff manifest: {exc}", err=True)

    if output_json:
        click.echo(json.dumps(manifest, indent=2))
    else:
        if manifest["status"] == "success":
            console.print(
                Panel(
                    (
                        f"[bold]System:[/bold] {manifest['system_name']}\n"
                        f"[bold]Risk Tier:[/bold] {manifest['risk_tier']}\n"
                        f"[bold]Output Dir:[/bold] {output_root}\n"
                        f"[bold]Artifacts:[/bold] {len(cast(dict[str, str], manifest['artifacts']))}\n"
                        f"[bold]Governance Enabled:[/bold] {'yes' if governance else 'no'}"
                    ),
                    title="GA Handoff Completed",
                    border_style="green",
                )
            )
        else:
            console.print(
                f"[red]Handoff failed at step '{manifest['failed_step']}': {manifest['error']}[/red]"
            )
            console.print(f"[yellow]Manifest saved to: {manifest_path}[/yellow]")

    if manifest["status"] != "success":
        sys.exit(1)
    if governance_enforced_failure:
        if not output_json:
            console.print(
                "[red]Handoff governance enforce mode failed. "
                "See governance_reason_codes in handoff_manifest.json.[/red]"
            )
        sys.exit(1)


@main.group()
def ops() -> None:
    """Run operational closeout and evidence automation commands."""
    pass


@ops.command("closeout")
@click.option(
    "--version",
    "release_version",
    help="Target release version (for example: 0.1.29).",
)
@click.option(
    "--release-run-id",
    type=int,
    help="GitHub Actions run id expected to be successful.",
)
@click.option(
    "--mode",
    type=click.Choice(["observe", "enforce"]),
    help=(
        "Closeout mode override. If omitted, policy/defaults are used "
        "(default behavior is observe)."
    ),
)
@click.option(
    "--repo",
    help="GitHub repository owner/name used for run and release checks.",
)
@click.option(
    "--pypi-project",
    help="PyPI project name for version validation.",
)
@click.option(
    "--rtd-url",
    help="Read the Docs URL expected to return HTTP 200.",
)
@click.option(
    "--max-run-age-hours",
    type=float,
    help="Optional freshness threshold for GitHub run age in hours.",
)
@click.option(
    "--max-release-age-hours",
    type=float,
    help="Optional freshness threshold for GitHub release age in hours.",
)
@click.option(
    "--max-rtd-age-hours",
    type=float,
    help="Optional freshness threshold for RTD last-modified age in hours.",
)
@click.option(
    "--policy",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional YAML policy file (precedence: CLI flags > policy file > defaults).",
)
@click.option(
    "--resolve-latest-release",
    is_flag=True,
    help=(
        "Resolve missing release version/run id from latest GitHub semver release and latest "
        "successful release workflow run."
    ),
)
@click.option(
    "--waiver-reason-code",
    "waiver_reason_codes",
    multiple=True,
    help="Optional waiver reason code override (repeatable, paired with --waiver-expires-at).",
)
@click.option(
    "--waiver-expires-at",
    "waiver_expires_at_values",
    multiple=True,
    help="Optional waiver expiry override as ISO8601 UTC datetime (repeatable).",
)
@click.option(
    "--escalation-pack",
    "escalation_pack",
    is_flag=True,
    default=None,
    help="Enable deterministic escalation artifact pack output (policy default preserved when omitted).",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Directory where closeout artifacts will be written (default: current working directory).",
)
@click.option(
    "--github-api-base-url",
    default="https://api.github.com",
    show_default=True,
    help="GitHub API base URL (advanced override, useful for smoke fixtures).",
)
@click.option(
    "--pypi-base-url",
    default="https://pypi.org",
    show_default=True,
    help="PyPI base URL (advanced override, useful for smoke fixtures).",
)
@click.option(
    "--timeout-seconds",
    type=float,
    default=20.0,
    show_default=True,
    help="HTTP timeout in seconds for each closeout check.",
)
@click.option("--json", "output_json", is_flag=True, help="Output manifest as JSON")
@click.pass_context
def ops_closeout(
    ctx: click.Context,
    release_version: str | None,
    release_run_id: int | None,
    mode: str | None,
    repo: str | None,
    pypi_project: str | None,
    rtd_url: str | None,
    max_run_age_hours: float | None,
    max_release_age_hours: float | None,
    max_rtd_age_hours: float | None,
    policy: str | None,
    resolve_latest_release: bool,
    waiver_reason_codes: tuple[str, ...],
    waiver_expires_at_values: tuple[str, ...],
    escalation_pack: bool | None,
    output_dir: str | None,
    github_api_base_url: str,
    pypi_base_url: str,
    timeout_seconds: float,
    output_json: bool,
) -> None:
    """Generate deterministic ops closeout evidence for run/release/PyPI/RTD."""
    if timeout_seconds <= 0:
        console.print("[red]Error: --timeout-seconds must be > 0[/red]")
        sys.exit(1)
    if release_run_id is not None and release_run_id < 1:
        console.print("[red]Error: --release-run-id must be >= 1[/red]")
        sys.exit(1)
    if max_run_age_hours is not None and max_run_age_hours <= 0:
        console.print("[red]Error: --max-run-age-hours must be > 0[/red]")
        sys.exit(1)
    if max_release_age_hours is not None and max_release_age_hours <= 0:
        console.print("[red]Error: --max-release-age-hours must be > 0[/red]")
        sys.exit(1)
    if max_rtd_age_hours is not None and max_rtd_age_hours <= 0:
        console.print("[red]Error: --max-rtd-age-hours must be > 0[/red]")
        sys.exit(1)
    if len(waiver_reason_codes) != len(waiver_expires_at_values):
        console.print(
            "[red]Error: --waiver-reason-code and --waiver-expires-at counts must match[/red]"
        )
        sys.exit(1)

    try:
        policy_payload = _load_ops_closeout_policy_file(policy)
        release_version_override = (
            release_version
            if ctx.get_parameter_source("release_version") == ParameterSource.COMMANDLINE
            else None
        )
        release_run_id_override = (
            release_run_id
            if ctx.get_parameter_source("release_run_id") == ParameterSource.COMMANDLINE
            else None
        )
        mode_override = (
            mode if ctx.get_parameter_source("mode") == ParameterSource.COMMANDLINE else None
        )
        repo_override = (
            repo if ctx.get_parameter_source("repo") == ParameterSource.COMMANDLINE else None
        )
        pypi_project_override = (
            pypi_project
            if ctx.get_parameter_source("pypi_project") == ParameterSource.COMMANDLINE
            else None
        )
        rtd_url_override = (
            rtd_url if ctx.get_parameter_source("rtd_url") == ParameterSource.COMMANDLINE else None
        )
        max_run_age_hours_override = (
            max_run_age_hours
            if ctx.get_parameter_source("max_run_age_hours") == ParameterSource.COMMANDLINE
            else None
        )
        max_release_age_hours_override = (
            max_release_age_hours
            if ctx.get_parameter_source("max_release_age_hours") == ParameterSource.COMMANDLINE
            else None
        )
        max_rtd_age_hours_override = (
            max_rtd_age_hours
            if ctx.get_parameter_source("max_rtd_age_hours") == ParameterSource.COMMANDLINE
            else None
        )
        resolve_latest_release_override = (
            resolve_latest_release
            if ctx.get_parameter_source("resolve_latest_release") == ParameterSource.COMMANDLINE
            else None
        )
        escalation_pack_override = (
            escalation_pack
            if ctx.get_parameter_source("escalation_pack") == ParameterSource.COMMANDLINE
            else None
        )
        waiver_reason_codes_from_cli = (
            ctx.get_parameter_source("waiver_reason_codes") == ParameterSource.COMMANDLINE
        )
        waiver_expires_from_cli = (
            ctx.get_parameter_source("waiver_expires_at_values") == ParameterSource.COMMANDLINE
        )
        waiver_overrides: list[dict[str, str | None]] | None = None
        if waiver_reason_codes_from_cli or waiver_expires_from_cli:
            waiver_overrides = [
                {
                    "reason_code": reason_code,
                    "expires_at": expires_at,
                    "note": None,
                }
                for reason_code, expires_at in zip(
                    waiver_reason_codes,
                    waiver_expires_at_values,
                    strict=False,
                )
            ]
        resolved_policy = resolve_ops_closeout_policy(
            policy_payload=policy_payload,
            mode=mode_override,
            release_version=release_version_override,
            release_run_id=release_run_id_override,
            repo=repo_override,
            pypi_project=pypi_project_override,
            rtd_url=rtd_url_override,
            max_run_age_hours=max_run_age_hours_override,
            max_release_age_hours=max_release_age_hours_override,
            max_rtd_age_hours=max_rtd_age_hours_override,
            resolve_latest_release=resolve_latest_release_override,
            waivers=waiver_overrides,
            escalation_enabled=escalation_pack_override,
        )
    except Exception as e:
        console.print(f"[red]Error resolving ops closeout policy: {e}[/red]")
        sys.exit(1)

    output_root = Path(output_dir).resolve() if output_dir else Path.cwd().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(UTC).isoformat()
    effective_release_version = resolved_policy.release_version
    effective_release_run_id = resolved_policy.release_run_id
    resolution_reason_codes: list[str] = []
    resolution_source = "explicit_inputs"
    resolution_attempted = False
    if resolved_policy.resolve_latest_release and (
        effective_release_version is None or effective_release_run_id is None
    ):
        resolution_attempted = True
        try:
            release_resolution = resolve_latest_release_inputs(
                repo=resolved_policy.repo,
                preferred_version=effective_release_version,
                github_api_base_url=github_api_base_url.strip(),
                timeout_seconds=timeout_seconds,
            )
            resolution_source = release_resolution.resolution_source
            resolution_reason_codes = list(release_resolution.reason_codes)
            if effective_release_version is None:
                effective_release_version = release_resolution.resolved_version
            if effective_release_run_id is None:
                effective_release_run_id = release_resolution.resolved_run_id
        except Exception:
            resolution_source = "github_release_workflow_runs_api"
            resolution_reason_codes = ["release_resolution_failed"]

    resolution_payload = {
        "attempted": resolution_attempted,
        "resolved_version": effective_release_version,
        "resolved_run_id": effective_release_run_id,
        "resolution_source": resolution_source,
        "reason_codes": list(resolution_reason_codes),
    }
    run_context_payload = {
        "generated_at": generated_at,
        "version": effective_release_version,
        "release_run_id": effective_release_run_id,
        "repo": resolved_policy.repo,
        "pypi_project": resolved_policy.pypi_project,
        "rtd_url": resolved_policy.rtd_url,
        "resolution": resolution_payload,
    }

    missing_reason_codes: list[str] = []
    if effective_release_version is None:
        missing_reason_codes.append("missing_release_version")
    if effective_release_run_id is None:
        missing_reason_codes.append("missing_release_run_id")

    checks: list[OpsCloseoutCheck]
    failed: bool
    reason_codes: list[str]
    failed_checks: list[str]
    passed_checks: list[str]
    freshness_metrics: dict[str, float | None]
    freshness_thresholds: dict[str, float | None]
    freshness_reason_codes: list[str]
    waiver_summary: dict[str, int]
    waived_reason_codes: list[str]
    expired_waiver_reason_codes: list[str]
    effective_reason_codes: list[str]

    if missing_reason_codes:
        missing_details = ", ".join(
            reason_code.removeprefix("missing_") for reason_code in missing_reason_codes
        )
        checks = [
            OpsCloseoutCheck(
                name="required_inputs",
                url="n/a",
                ok=False,
                http_status=None,
                details=f"missing={missing_details}",
            )
        ]
        failed = True
        reason_codes = list(dict.fromkeys([*resolution_reason_codes, *missing_reason_codes]))
        failed_checks = ["required_inputs"]
        passed_checks = []
        freshness_metrics = {
            "run_age_hours": None,
            "release_age_hours": None,
            "rtd_age_hours": None,
        }
        freshness_thresholds = {
            "max_run_age_hours": resolved_policy.max_run_age_hours,
            "max_release_age_hours": resolved_policy.max_release_age_hours,
            "max_rtd_age_hours": resolved_policy.max_rtd_age_hours,
        }
        freshness_reason_codes = []
        waiver_summary = {
            "configured_count": len(resolved_policy.waivers),
            "matched_count": 0,
            "waived_count": 0,
            "expired_count": 0,
        }
        waived_reason_codes = []
        expired_waiver_reason_codes = []
        effective_reason_codes = list(reason_codes)
    else:
        try:
            closeout_result = OpsCloseoutEvaluator().evaluate(
                mode=resolved_policy.mode,
                version=effective_release_version or "",
                release_run_id=cast(int, effective_release_run_id),
                repo=resolved_policy.repo,
                pypi_project=resolved_policy.pypi_project,
                rtd_url=resolved_policy.rtd_url,
                github_api_base_url=github_api_base_url.strip(),
                pypi_base_url=pypi_base_url.strip(),
                timeout_seconds=timeout_seconds,
                max_run_age_hours=resolved_policy.max_run_age_hours,
                max_release_age_hours=resolved_policy.max_release_age_hours,
                max_rtd_age_hours=resolved_policy.max_rtd_age_hours,
                waivers=resolved_policy.waivers,
            )
        except Exception as e:
            console.print(f"[red]Error running ops closeout checks: {e}[/red]")
            sys.exit(1)
        checks = closeout_result.checks
        failed = closeout_result.failed
        reason_codes = closeout_result.reason_codes
        failed_checks = closeout_result.failed_checks
        passed_checks = closeout_result.passed_checks
        freshness_metrics = closeout_result.freshness_metrics
        freshness_thresholds = closeout_result.freshness_thresholds
        freshness_reason_codes = closeout_result.freshness_reason_codes
        waiver_summary = closeout_result.waiver_summary
        waived_reason_codes = closeout_result.waived_reason_codes
        expired_waiver_reason_codes = closeout_result.expired_waiver_reason_codes
        effective_reason_codes = closeout_result.effective_reason_codes

    checks_payload = {
        "generated_at": generated_at,
        "mode": resolved_policy.mode,
        "version": effective_release_version,
        "release_run_id": effective_release_run_id,
        "repo": resolved_policy.repo,
        "pypi_project": resolved_policy.pypi_project,
        "rtd_url": resolved_policy.rtd_url,
        "resolution": resolution_payload,
        "freshness_metrics": freshness_metrics,
        "freshness_thresholds": freshness_thresholds,
        "freshness_reason_codes": freshness_reason_codes,
        "waiver_summary": waiver_summary,
        "waived_reason_codes": waived_reason_codes,
        "expired_waiver_reason_codes": expired_waiver_reason_codes,
        "effective_reason_codes": effective_reason_codes,
        "escalation_enabled": resolved_policy.escalation_enabled,
        "checks": [check.to_dict() for check in checks],
    }

    escalation_payload = build_ops_closeout_escalation_decision(
        mode=resolved_policy.mode,
        failed_checks=failed_checks,
        effective_reason_codes=effective_reason_codes,
        run_context=run_context_payload,
    ).to_dict()
    checks_payload["escalation"] = escalation_payload

    checks_path = output_root / "ops_closeout_checks.json"
    evidence_path = output_root / "ops_closeout_evidence.md"
    manifest_path = output_root / "ops_closeout_manifest.json"
    escalation_json_path = output_root / "ops_closeout_escalation.json"
    escalation_md_path = output_root / "ops_closeout_escalation.md"

    manifest_payload = {
        "generated_at": generated_at,
        "mode": resolved_policy.mode,
        "status": "failed" if failed else "success",
        "failed": failed,
        "version": effective_release_version,
        "release_run_id": effective_release_run_id,
        "repo": resolved_policy.repo,
        "pypi_project": resolved_policy.pypi_project,
        "rtd_url": resolved_policy.rtd_url,
        "resolution": resolution_payload,
        "reason_codes": reason_codes,
        "failed_checks": failed_checks,
        "passed_checks": passed_checks,
        "freshness_metrics": freshness_metrics,
        "freshness_thresholds": freshness_thresholds,
        "freshness_reason_codes": freshness_reason_codes,
        "waiver_summary": waiver_summary,
        "waived_reason_codes": waived_reason_codes,
        "expired_waiver_reason_codes": expired_waiver_reason_codes,
        "effective_reason_codes": effective_reason_codes,
        "escalation_enabled": resolved_policy.escalation_enabled,
        "escalation_required": escalation_payload["escalation_required"],
        "escalation_reason_codes": escalation_payload["escalation_reason_codes"],
        "escalation": escalation_payload,
        "effective_policy": resolved_policy.to_dict(),
        "artifacts": {
            "ops_closeout_checks.json": str(checks_path),
            "ops_closeout_manifest.json": str(manifest_path),
            "ops_closeout_evidence.md": str(evidence_path),
        },
    }
    if resolved_policy.escalation_enabled:
        manifest_payload["artifacts"]["ops_closeout_escalation.json"] = str(escalation_json_path)
        manifest_payload["artifacts"]["ops_closeout_escalation.md"] = str(escalation_md_path)

    try:
        checks_path.write_text(json.dumps(checks_payload, indent=2), encoding="utf-8")
        evidence_path.write_text(
            _render_ops_closeout_evidence_markdown(
                generated_at=generated_at,
                version=effective_release_version or "missing",
                repo=resolved_policy.repo,
                mode=resolved_policy.mode,
                checks=checks,
                failed=failed,
                reason_codes=reason_codes,
                resolution=resolution_payload,
                freshness_metrics=freshness_metrics,
                freshness_thresholds=freshness_thresholds,
                freshness_reason_codes=freshness_reason_codes,
                waiver_summary=waiver_summary,
                waived_reason_codes=waived_reason_codes,
                expired_waiver_reason_codes=expired_waiver_reason_codes,
                effective_reason_codes=effective_reason_codes,
            ),
            encoding="utf-8",
        )
        if resolved_policy.escalation_enabled:
            escalation_json_path.write_text(
                json.dumps(escalation_payload, indent=2),
                encoding="utf-8",
            )
            escalation_md_path.write_text(
                _render_ops_closeout_escalation_markdown(escalation_payload=escalation_payload),
                encoding="utf-8",
            )
        manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
    except Exception as e:
        click.echo(f"Error: failed to write ops closeout artifacts: {e}", err=True)
        sys.exit(1)

    if output_json:
        click.echo(json.dumps(manifest_payload, indent=2))
    else:
        console.print(
            Panel(
                (
                    f"[bold]Mode:[/bold] {resolved_policy.mode}\n"
                    f"[bold]Status:[/bold] {'FAILED' if failed else 'SUCCESS'}\n"
                    f"[bold]Version:[/bold] {effective_release_version or 'missing'}\n"
                    f"[bold]Release Run ID:[/bold] {effective_release_run_id or 'missing'}\n"
                    f"[bold]Resolution Source:[/bold] {resolution_source}\n"
                    f"[bold]Output Dir:[/bold] {output_root}\n"
                    f"[bold]Failed Checks:[/bold] {len(failed_checks)}"
                ),
                title="Ops Closeout",
                border_style="blue",
            )
        )
        if failed:
            console.print(f"[yellow]Reason Codes:[/yellow] {', '.join(reason_codes)}")
        if freshness_reason_codes:
            console.print(
                f"[yellow]Freshness Reasons:[/yellow] {', '.join(freshness_reason_codes)}"
            )
        if waived_reason_codes:
            console.print(f"[green]Waived Reasons:[/green] {', '.join(waived_reason_codes)}")
        if expired_waiver_reason_codes:
            console.print(
                "[yellow]Expired Waiver Reasons:[/yellow] "
                f"{', '.join(expired_waiver_reason_codes)}"
            )
        if resolved_policy.escalation_enabled:
            console.print(
                "[bold]Escalation Required:[/bold] "
                f"{str(bool(escalation_payload['escalation_required'])).lower()}"
            )
            if escalation_payload["escalation_reason_codes"]:
                console.print(
                    "[yellow]Escalation Reasons:[/yellow] "
                    f"{', '.join(cast(list[str], escalation_payload['escalation_reason_codes']))}"
                )

    if resolved_policy.mode == "enforce" and failed:
        if missing_reason_codes:
            click.echo(
                "Error: missing required release input(s) for enforce mode: "
                f"{', '.join(missing_reason_codes)}",
                err=True,
            )
        sys.exit(1)


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
def collaboration() -> None:
    """Manage local-first collaboration workflow for compliance tasks."""
    pass


@collaboration.command("sync")
@click.argument("system_yaml", type=click.Path(exists=True))
@click.option("--owner-default", help="Default owner applied to newly created tasks")
@click.option("--collab-path", type=click.Path(), help="Override collaboration ledger JSONL path")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def collaboration_sync(
    system_yaml: str,
    owner_default: str | None,
    collab_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Sync collaboration tasks from current compliance findings."""
    try:
        descriptor = load_system_descriptor_from_file(system_yaml)
        report = ComplianceChecker().check(descriptor)
        payload = sync_collaboration_tasks(
            report=report,
            descriptor_path=system_yaml,
            owner_default=owner_default,
            collab_path=collab_path,
        )
    except Exception as e:
        console.print(f"[red]Error syncing collaboration tasks: {e}[/red]")
        sys.exit(1)

    payload_json = json.dumps(payload, indent=2)
    if output or output_json:
        _emit_export_output(payload_json, output)
        return

    summary = payload["summary"]
    changes = payload["changes"]
    console.print(
        Panel(
            (
                f"[bold]System:[/bold] {payload['system_name']}\n"
                f"[bold]Ledger:[/bold] {payload['collaboration_path']}\n"
                f"[bold]Total Tasks:[/bold] {payload['total_tasks']}\n"
                f"[bold]System Tasks:[/bold] {payload['system_task_count']}"
            ),
            title="Collaboration Sync",
            border_style="blue",
        )
    )
    table = Table(title="Changes and Workflow Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("created_count", str(changes["created_count"]))
    table.add_row("updated_count", str(changes["updated_count"]))
    table.add_row("reopened_count", str(changes["reopened_count"]))
    table.add_row("auto_closed_count", str(changes["auto_closed_count"]))
    table.add_row("open_count", str(summary["open_count"]))
    table.add_row("in_review_count", str(summary["in_review_count"]))
    table.add_row("blocked_count", str(summary["blocked_count"]))
    table.add_row("done_count", str(summary["done_count"]))
    console.print(table)


@collaboration.command("list")
@click.option("--system", "system_name", help="Filter by exact system name")
@click.option("--owner", help="Filter by exact owner")
@click.option(
    "--status",
    "workflow_status",
    type=click.Choice(["open", "in_review", "blocked", "done"]),
    help="Filter by workflow status",
)
@click.option("--limit", type=int, help="Return at most N newest tasks")
@click.option("--collab-path", type=click.Path(), help="Override collaboration ledger JSONL path")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def collaboration_list(
    system_name: str | None,
    owner: str | None,
    workflow_status: str | None,
    limit: int | None,
    collab_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """List latest collaboration task snapshots."""
    try:
        resolved_path, tasks = list_collaboration_tasks(
            collab_path=collab_path,
            system_name=system_name,
            owner=owner,
            workflow_status=cast(WorkflowStatus | None, workflow_status),
            limit=limit,
        )
    except Exception as e:
        console.print(f"[red]Error listing collaboration tasks: {e}[/red]")
        sys.exit(1)

    payload = {
        "collaboration_path": str(resolved_path),
        "count": len(tasks),
        "tasks": [task.to_dict() for task in tasks],
    }
    payload_json = json.dumps(payload, indent=2)
    if output or output_json:
        _emit_export_output(payload_json, output)
        return

    if not tasks:
        console.print(f"[yellow]No collaboration tasks found at {resolved_path}[/yellow]")
        return

    table = Table(title=f"Collaboration Tasks ({resolved_path})")
    table.add_column("Task ID")
    table.add_column("System")
    table.add_column("Requirement")
    table.add_column("Workflow")
    table.add_column("Finding")
    table.add_column("Owner")
    table.add_column("Updated At")
    for task in tasks:
        table.add_row(
            task.task_id,
            task.system_name,
            task.requirement_id,
            task.workflow_status,
            task.finding_status,
            task.owner or "-",
            task.updated_at,
        )
    console.print(table)


@collaboration.command("update")
@click.argument("task_id")
@click.option(
    "--status",
    "workflow_status",
    type=click.Choice(["open", "in_review", "blocked", "done"]),
    help="Set workflow status",
)
@click.option("--owner", help="Set owner")
@click.option("--note", help="Append note message")
@click.option("--note-author", help="Author for appended note (default: unknown)")
@click.option("--collab-path", type=click.Path(), help="Override collaboration ledger JSONL path")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def collaboration_update(
    task_id: str,
    workflow_status: str | None,
    owner: str | None,
    note: str | None,
    note_author: str | None,
    collab_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Update workflow status/owner/notes for one collaboration task."""
    if workflow_status is None and owner is None and note is None:
        console.print("[red]Error: provide at least one of --status, --owner, or --note[/red]")
        sys.exit(1)

    try:
        resolved_path, task, changed = update_collaboration_task(
            task_id=task_id,
            workflow_status=cast(WorkflowStatus | None, workflow_status),
            owner=owner,
            note_message=note,
            note_author=note_author,
            collab_path=collab_path,
        )
    except Exception as e:
        console.print(f"[red]Error updating collaboration task: {e}[/red]")
        sys.exit(1)

    payload = {
        "collaboration_path": str(resolved_path),
        "changed": changed,
        "updated_task": task.to_dict(),
    }
    payload_json = json.dumps(payload, indent=2)
    if output or output_json:
        _emit_export_output(payload_json, output)
        return

    console.print(
        Panel(
            (
                f"[bold]Task:[/bold] {task.task_id}\n"
                f"[bold]System:[/bold] {task.system_name}\n"
                f"[bold]Workflow:[/bold] {task.workflow_status}\n"
                f"[bold]Owner:[/bold] {task.owner or '-'}\n"
                f"[bold]Changed:[/bold] {'yes' if changed else 'no'}"
            ),
            title="Collaboration Task Updated",
            border_style="green",
        )
    )


@collaboration.command("summary")
@click.option("--system", "system_name", help="Filter by exact system name")
@click.option("--owner", help="Filter by exact owner")
@click.option("--collab-path", type=click.Path(), help="Override collaboration ledger JSONL path")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def collaboration_summary(
    system_name: str | None,
    owner: str | None,
    collab_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Summarize collaboration workflow status counts."""
    try:
        payload = summarize_collaboration_tasks(
            collab_path=collab_path,
            system_name=system_name,
            owner=owner,
        )
    except Exception as e:
        console.print(f"[red]Error summarizing collaboration tasks: {e}[/red]")
        sys.exit(1)

    payload_json = json.dumps(payload, indent=2)
    if output or output_json:
        _emit_export_output(payload_json, output)
        return

    console.print(
        Panel(
            (
                f"[bold]Ledger:[/bold] {payload['collaboration_path']}\n"
                f"[bold]Task Count:[/bold] {payload['count']}\n"
                f"[bold]Open:[/bold] {payload['open_count']}\n"
                f"[bold]In Review:[/bold] {payload['in_review_count']}\n"
                f"[bold]Blocked:[/bold] {payload['blocked_count']}\n"
                f"[bold]Done:[/bold] {payload['done_count']}"
            ),
            title="Collaboration Summary",
            border_style="blue",
        )
    )


@collaboration.command("gate")
@click.option(
    "--mode",
    type=click.Choice(["observe", "enforce"]),
    help="Gate mode. observe never blocks; enforce fails on threshold violations.",
)
@click.option(
    "--policy",
    "policy_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional YAML policy file.",
)
@click.option("--system", "system_name", help="Filter metrics to an exact system name")
@click.option("--blocked-max", type=int, help="Maximum allowed blocked tasks")
@click.option(
    "--unassigned-actionable-max",
    type=int,
    help="Maximum allowed unassigned actionable tasks",
)
@click.option(
    "--stale-actionable-max",
    type=int,
    help="Maximum allowed stale actionable tasks (threshold disabled if omitted)",
)
@click.option(
    "--blocked-stale-max",
    type=int,
    help="Maximum allowed blocked stale tasks (threshold disabled if omitted)",
)
@click.option(
    "--review-stale-max",
    type=int,
    help="Maximum allowed in-review stale tasks (threshold disabled if omitted)",
)
@click.option(
    "--stale-after-hours",
    type=float,
    help="Hours after which actionable tasks are considered stale",
)
@click.option(
    "--blocked-stale-after-hours",
    type=float,
    help="Hours after which blocked tasks are considered stale",
)
@click.option(
    "--review-stale-after-hours",
    type=float,
    help="Hours after which in-review tasks are considered stale",
)
@click.option("--limit", type=int, help="Maximum number of recent tasks considered")
@click.option("--collab-path", type=click.Path(), help="Override collaboration ledger JSONL path")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload (default behavior)")
def collaboration_gate(
    mode: str | None,
    policy_path: str | None,
    system_name: str | None,
    blocked_max: int | None,
    unassigned_actionable_max: int | None,
    stale_actionable_max: int | None,
    blocked_stale_max: int | None,
    review_stale_max: int | None,
    stale_after_hours: float | None,
    blocked_stale_after_hours: float | None,
    review_stale_after_hours: float | None,
    limit: int | None,
    collab_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Evaluate collaboration workflow metrics against governance policy."""
    _ = output_json

    if limit is not None and limit < 1:
        console.print("[red]Error: --limit must be >= 1[/red]")
        sys.exit(1)
    if blocked_max is not None and blocked_max < 0:
        console.print("[red]Error: --blocked-max must be >= 0[/red]")
        sys.exit(1)
    if unassigned_actionable_max is not None and unassigned_actionable_max < 0:
        console.print("[red]Error: --unassigned-actionable-max must be >= 0[/red]")
        sys.exit(1)
    if stale_actionable_max is not None and stale_actionable_max < 0:
        console.print("[red]Error: --stale-actionable-max must be >= 0[/red]")
        sys.exit(1)
    if blocked_stale_max is not None and blocked_stale_max < 0:
        console.print("[red]Error: --blocked-stale-max must be >= 0[/red]")
        sys.exit(1)
    if review_stale_max is not None and review_stale_max < 0:
        console.print("[red]Error: --review-stale-max must be >= 0[/red]")
        sys.exit(1)
    if stale_after_hours is not None and stale_after_hours <= 0:
        console.print("[red]Error: --stale-after-hours must be > 0[/red]")
        sys.exit(1)
    if blocked_stale_after_hours is not None and blocked_stale_after_hours <= 0:
        console.print("[red]Error: --blocked-stale-after-hours must be > 0[/red]")
        sys.exit(1)
    if review_stale_after_hours is not None and review_stale_after_hours <= 0:
        console.print("[red]Error: --review-stale-after-hours must be > 0[/red]")
        sys.exit(1)

    try:
        policy_payload = _load_collaboration_gate_policy_file(policy_path)
        resolved_policy = resolve_collaboration_gate_policy(
            policy_payload=policy_payload,
            mode=mode,
            system_name=system_name,
            limit=limit,
            blocked_max=blocked_max,
            unassigned_actionable_max=unassigned_actionable_max,
            stale_actionable_max=stale_actionable_max,
            blocked_stale_max=blocked_stale_max,
            review_stale_max=review_stale_max,
            stale_after_hours=stale_after_hours,
            blocked_stale_after_hours=blocked_stale_after_hours,
            review_stale_after_hours=review_stale_after_hours,
        )
        metrics = summarize_collaboration_gate_metrics(
            collab_path=collab_path,
            system_name=resolved_policy.system_name,
            limit=resolved_policy.limit,
            stale_after_hours=resolved_policy.stale_after_hours,
            blocked_stale_after_hours=resolved_policy.blocked_stale_after_hours,
            review_stale_after_hours=resolved_policy.review_stale_after_hours,
        )
        gate_result = CollaborationGateEvaluator().evaluate(
            policy=resolved_policy,
            metrics=metrics,
        )
    except Exception as e:
        console.print(f"[red]Error running collaboration gate: {e}[/red]")
        sys.exit(1)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": gate_result.mode,
        "failed": gate_result.failed,
        "reason_codes": gate_result.reason_codes,
        "effective_policy": resolved_policy.to_dict(),
        "metrics": metrics,
        "decision_details": gate_result.decision_details,
        "collaboration_path": metrics.get("collaboration_path"),
    }
    payload_json = json.dumps(payload, indent=2)
    _emit_export_output(payload_json, output)

    if resolved_policy.mode == "enforce" and gate_result.failed:
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

    if event.security_summary:
        security_table = Table(title="Security Summary")
        security_table.add_column("Metric", style="cyan")
        security_table.add_column("Value", justify="right")
        framework = event.security_summary.get("framework", "owasp-llm-top-10")
        security_table.add_row("framework", str(framework))
        for field_name in [
            "total_controls",
            "compliant_count",
            "non_compliant_count",
            "partial_count",
            "not_assessed_count",
            "coverage_percentage",
        ]:
            security_table.add_row(field_name, str(event.security_summary.get(field_name, "-")))
        console.print(security_table)
    else:
        console.print("[yellow]No security summary snapshot in this history event.[/yellow]")

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

    security_change = payload.get("security_summary_change", {})
    security_table = Table(title="Security Summary Changes")
    security_table.add_column("Metric")
    security_table.add_column("From", justify="right")
    security_table.add_column("To", justify="right")
    security_table.add_column("Delta", justify="right")
    for metric in [
        "coverage_percentage",
        "non_compliant_count",
        "partial_count",
        "not_assessed_count",
    ]:
        change = security_change.get(metric, {"from": "-", "to": "-", "delta": "-"})
        security_table.add_row(
            metric,
            str(change.get("from", "-")),
            str(change.get("to", "-")),
            str(change.get("delta", "-")),
        )
    console.print(security_table)

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
            _emit_ops_log_warning(push_result)
        except ExportPushError as e:
            _emit_ops_log_warning(e.push_result)
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        payload_dict["push_result"] = push_result
    elif dry_run:
        payload_dict["push_result"] = build_simulated_push_result(
            target=target,
            push_mode=cast(PushMode, push_mode),
            actionable_count=sum(1 for item in payload.items if item.actionable),
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            timeout_seconds=timeout_seconds,
            idempotency_enabled=not disable_idempotency,
            idempotency_path=resolved_idempotency_path,
            message="Dry-run requested without --push; no remote API call was made.",
        )

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
            _emit_ops_log_warning(push_result)
        except ExportPushError as e:
            _emit_ops_log_warning(e.push_result)
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error pushing export payload: {e}[/red]")
            sys.exit(1)
        payload_dict["push_result"] = push_result
    elif dry_run:
        payload_dict["push_result"] = build_simulated_push_result(
            target=target,
            push_mode=cast(PushMode, push_mode),
            actionable_count=sum(1 for item in payload.items if item.actionable),
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            timeout_seconds=timeout_seconds,
            idempotency_enabled=not disable_idempotency,
            idempotency_path=resolved_idempotency_path,
            message="Dry-run requested without --push; no remote API call was made.",
        )

    payload_json = json.dumps(payload_dict, indent=2)
    _emit_export_output(payload_json, output)


@export.command("batch")
@click.argument("descriptor_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow", "generic"]),
    required=True,
    help="Export target adapter",
)
@click.option("--recursive", is_flag=True, help="Recursively scan descriptor directory")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
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
def export_batch(
    ctx: click.Context,
    descriptor_dir: str,
    target: str,
    recursive: bool,
    output: str | None,
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
    """Export payloads in batch from a descriptor directory."""
    _ = output_json

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
    if push and target == "generic":
        console.print("[red]Error: Live push is not supported for target 'generic'[/red]")
        sys.exit(1)

    try:
        payload = run_export_batch(
            descriptor_dir=descriptor_dir,
            target=cast(ExportTarget, target),
            recursive=recursive,
            push=push,
            push_mode=cast(PushMode, push_mode),
            dry_run=dry_run,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            timeout_seconds=timeout_seconds,
            idempotency_path=idempotency_path,
            idempotency_enabled=not disable_idempotency,
        )
    except Exception as e:
        console.print(f"[red]Error running export batch: {e}[/red]")
        sys.exit(1)

    payload_json = json.dumps(payload, indent=2)
    _emit_export_output(payload_json, output)
    for warning in payload.get("ops_log_warnings", []):
        if isinstance(warning, str) and warning.strip():
            click.echo(f"Warning: {warning}", err=True)

    if (
        payload["invalid_count"] > 0
        or payload["failure_count"] > 0
        or payload["success_count"] == 0
    ):
        sys.exit(1)


@export.command("replay")
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow"]),
    required=True,
    help="Export target adapter",
)
@click.option(
    "--since-hours",
    type=float,
    help="Only replay failed records generated within the last N hours.",
)
@click.option("--system", "system_name", help="Filter by system name")
@click.option("--requirement-id", help="Filter by requirement id")
@click.option(
    "--limit",
    type=int,
    default=25,
    show_default=True,
    help="Maximum number of failed records to replay after dedupe.",
)
@click.option(
    "--push-mode",
    type=click.Choice(["create", "upsert"]),
    default="create",
    show_default=True,
    help="Push strategy for replayed records.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not call remote APIs; replay selection is still computed.",
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
    help="Disable duplicate-skip idempotency checks for live push replay.",
)
@click.option("--ops-path", type=click.Path(), help="Override export operations log path")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload (default behavior)")
def export_replay(
    target: str,
    since_hours: float | None,
    system_name: str | None,
    requirement_id: str | None,
    limit: int,
    push_mode: str,
    dry_run: bool,
    max_retries: int,
    retry_backoff_seconds: float,
    timeout_seconds: float,
    idempotency_path: str | None,
    disable_idempotency: bool,
    ops_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Replay failed export push records from persistent ops log."""
    _ = output_json

    if limit < 1:
        console.print("[red]Error: --limit must be >= 1[/red]")
        sys.exit(1)
    if since_hours is not None and since_hours < 0:
        console.print("[red]Error: --since-hours must be >= 0[/red]")
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

    try:
        payload = replay_export_push_failures(
            target=cast(ExportTarget, target),
            ops_path=ops_path,
            system_name=system_name,
            requirement_id=requirement_id,
            since_hours=since_hours,
            limit=limit,
            push_mode=cast(PushMode, push_mode),
            dry_run=dry_run,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            timeout_seconds=timeout_seconds,
            idempotency_path=idempotency_path,
            idempotency_enabled=not disable_idempotency,
        )
    except Exception as e:
        console.print(f"[red]Error running export replay: {e}[/red]")
        sys.exit(1)

    payload_json = json.dumps(payload, indent=2)
    _emit_export_output(payload_json, output)

    for result in payload.get("results", []):
        if isinstance(result, dict) and isinstance(result.get("ops_log_warning"), str):
            click.echo(f"Warning: {result['ops_log_warning']}", err=True)

    if payload.get("failed_count", 0) > 0 or payload.get("unreplayable_count", 0) > 0:
        sys.exit(1)


@export.command("rollup")
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow", "generic"]),
    help="Optional target filter",
)
@click.option("--system", "system_name", help="Filter by system name")
@click.option(
    "--since-hours",
    type=float,
    help="Only include ops generated within the last N hours.",
)
@click.option(
    "--limit",
    type=int,
    help="Maximum number of recent operation records to include before aggregation.",
)
@click.option("--ops-path", type=click.Path(), help="Override export operations log path")
@click.option("--idempotency-path", type=click.Path(), help="Override ledger path")
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload (default behavior)")
def export_rollup(
    target: str | None,
    system_name: str | None,
    since_hours: float | None,
    limit: int | None,
    ops_path: str | None,
    idempotency_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Summarize export operations from ops log + idempotency ledger."""
    _ = output_json

    if since_hours is not None and since_hours < 0:
        console.print("[red]Error: --since-hours must be >= 0[/red]")
        sys.exit(1)
    if limit is not None and limit < 1:
        console.print("[red]Error: --limit must be >= 1[/red]")
        sys.exit(1)

    try:
        payload = summarize_export_ops_rollup(
            ops_path=ops_path,
            idempotency_path=idempotency_path,
            target=cast(ExportTarget | None, target),
            system_name=system_name,
            since_hours=since_hours,
            limit=limit,
        )
    except Exception as e:
        console.print(f"[red]Error running export rollup: {e}[/red]")
        sys.exit(1)

    payload_json = json.dumps(payload, indent=2)
    _emit_export_output(payload_json, output)


@export.command("gate")
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow"]),
    required=True,
    help="Export target adapter",
)
@click.option("--system", "system_name", help="Filter by system name")
@click.option(
    "--since-hours",
    type=float,
    help="Window size in hours (default from policy/defaults).",
)
@click.option(
    "--limit",
    type=int,
    help="Maximum number of recent records considered for policy evaluation.",
)
@click.option(
    "--mode",
    type=click.Choice(["observe", "enforce"]),
    help="Gate mode. observe never changes exit code; enforce fails on policy violations.",
)
@click.option(
    "--policy",
    "policy_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional YAML policy file.",
)
@click.option(
    "--open-failures-max",
    type=int,
    help="Maximum allowed open failures before gate violation.",
)
@click.option(
    "--drift-max",
    type=int,
    help="Maximum allowed drift count before gate violation.",
)
@click.option(
    "--min-success-rate",
    type=float,
    help="Minimum success rate percentage (0-100).",
)
@click.option("--ops-path", type=click.Path(), help="Override export operations log path")
@click.option(
    "--reconcile-log-path",
    type=click.Path(),
    help="Override export reconcile log path",
)
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload (default behavior)")
def export_gate(
    target: str,
    system_name: str | None,
    since_hours: float | None,
    limit: int | None,
    mode: str | None,
    policy_path: str | None,
    open_failures_max: int | None,
    drift_max: int | None,
    min_success_rate: float | None,
    ops_path: str | None,
    reconcile_log_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Evaluate export operational metrics against policy thresholds."""
    _ = output_json

    if since_hours is not None and since_hours < 0:
        console.print("[red]Error: --since-hours must be >= 0[/red]")
        sys.exit(1)
    if limit is not None and limit < 1:
        console.print("[red]Error: --limit must be >= 1[/red]")
        sys.exit(1)
    if open_failures_max is not None and open_failures_max < 0:
        console.print("[red]Error: --open-failures-max must be >= 0[/red]")
        sys.exit(1)
    if drift_max is not None and drift_max < 0:
        console.print("[red]Error: --drift-max must be >= 0[/red]")
        sys.exit(1)
    if min_success_rate is not None and not (0 <= min_success_rate <= 100):
        console.print("[red]Error: --min-success-rate must be between 0 and 100[/red]")
        sys.exit(1)

    try:
        policy_payload = _load_export_gate_policy_file(policy_path)
        resolved_policy = resolve_export_ops_gate_policy(
            policy_payload=policy_payload,
            mode=mode,
            since_hours=since_hours,
            limit=limit,
            open_failures_max=open_failures_max,
            drift_max=drift_max,
            min_success_rate=min_success_rate,
        )
        rollup_payload = summarize_export_ops_rollup(
            ops_path=ops_path,
            target=cast(ExportTarget, target),
            system_name=system_name,
            since_hours=resolved_policy.since_hours,
            limit=resolved_policy.limit,
        )
        reconcile_payload = summarize_export_reconcile_log(
            reconcile_log_path=reconcile_log_path,
            target=cast(ExportTarget, target),
            system_name=system_name,
            since_hours=resolved_policy.since_hours,
            limit=resolved_policy.limit,
        )
        gate_result = ExportOpsGateEvaluator().evaluate(
            policy=resolved_policy,
            rollup_metrics=cast(dict, rollup_payload.get("metrics", {})),
            reconcile_metrics=cast(dict, reconcile_payload.get("metrics", {})),
        )
    except Exception as e:
        console.print(f"[red]Error running export gate: {e}[/red]")
        sys.exit(1)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "target": target,
        "system_name": system_name,
        "mode": gate_result.mode,
        "failed": gate_result.failed,
        "reason_codes": gate_result.reason_codes,
        "effective_policy": resolved_policy.to_dict(),
        "rollup_metrics": rollup_payload.get("metrics", {}),
        "reconcile_metrics": reconcile_payload.get("metrics", {}),
        "decision_details": gate_result.decision_details,
        "ops_path": rollup_payload.get("ops_path"),
        "reconcile_log_path": reconcile_payload.get("path"),
    }
    payload_json = json.dumps(payload, indent=2)
    _emit_export_output(payload_json, output)

    if resolved_policy.mode == "enforce" and gate_result.failed:
        sys.exit(1)


@export.command("reconcile")
@click.option(
    "--target",
    type=click.Choice(["jira", "servicenow"]),
    required=True,
    help="Export target adapter",
)
@click.option("--idempotency-path", type=click.Path(), help="Override ledger path")
@click.option("--system", "system_name", help="Filter by system name")
@click.option("--requirement-id", help="Filter by requirement id")
@click.option(
    "--limit",
    type=int,
    default=50,
    show_default=True,
    help="Maximum number of ledger records to reconcile",
)
@click.option(
    "--max-retries",
    type=int,
    default=3,
    show_default=True,
    help="Maximum retry attempts for retryable reconcile checks (429/5xx/transport).",
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
    help="HTTP request timeout in seconds for reconcile calls.",
)
@click.option(
    "--repair",
    is_flag=True,
    help="Generate repair plan for drifted records without remote writes.",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Apply repair plan updates to remote records (requires --repair).",
)
@click.option(
    "--reconcile-log-path",
    type=click.Path(),
    help="Override export reconcile log path.",
)
@click.option("--output", "-o", type=click.Path(), help="Write JSON payload to a file")
@click.option("--json", "output_json", is_flag=True, help="Output JSON payload (default behavior)")
def export_reconcile(
    target: str,
    idempotency_path: str | None,
    system_name: str | None,
    requirement_id: str | None,
    limit: int,
    max_retries: int,
    retry_backoff_seconds: float,
    timeout_seconds: float,
    repair: bool,
    apply: bool,
    reconcile_log_path: str | None,
    output: str | None,
    output_json: bool,
) -> None:
    """Reconcile ledger push records against remote target status."""
    _ = output_json

    if limit < 1:
        console.print("[red]Error: --limit must be >= 1[/red]")
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
    if apply and not repair:
        console.print("[red]Error: --apply can only be used together with --repair[/red]")
        sys.exit(1)

    try:
        payload = reconcile_export_push_records(
            target=cast(ExportTarget, target),
            idempotency_path=idempotency_path,
            system_name=system_name,
            requirement_id=requirement_id,
            limit=limit,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            timeout_seconds=timeout_seconds,
            repair_enabled=repair,
            apply=apply,
            reconcile_log_path=reconcile_log_path,
        )
    except Exception as e:
        console.print(f"[red]Error running export reconcile: {e}[/red]")
        sys.exit(1)

    payload_json = json.dumps(payload, indent=2)
    _emit_export_output(payload_json, output)
    _emit_reconcile_log_warning(payload)

    if (
        payload.get("missing_count", 0) > 0
        or payload.get("error_count", 0) > 0
        or payload.get("drift_count", 0) > 0
        or payload.get("repair_failed_count", 0) > 0
    ):
        sys.exit(1)


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


def _render_ops_closeout_evidence_markdown(
    *,
    generated_at: str,
    version: str,
    repo: str,
    mode: str,
    checks: list[OpsCloseoutCheck],
    failed: bool,
    reason_codes: list[str],
    resolution: dict[str, Any],
    freshness_metrics: dict[str, float | None],
    freshness_thresholds: dict[str, float | None],
    freshness_reason_codes: list[str],
    waiver_summary: dict[str, int],
    waived_reason_codes: list[str],
    expired_waiver_reason_codes: list[str],
    effective_reason_codes: list[str],
) -> str:
    """Render closeout evidence markdown from deterministic check payload."""
    lines = [
        "# Ops Closeout Evidence",
        "",
        f"- Generated at: {generated_at}",
        f"- Repository: {repo}",
        f"- Version: {version}",
        f"- Mode: {mode}",
        f"- Status: {'failed' if failed else 'success'}",
        f"- Reason codes: {', '.join(reason_codes) if reason_codes else 'none'}",
        f"- Effective reason codes: {', '.join(effective_reason_codes) if effective_reason_codes else 'none'}",
        f"- Resolution source: {resolution.get('resolution_source', 'none')}",
        f"- Resolution attempted: {str(bool(resolution.get('attempted', False))).lower()}",
        "- Resolution reason codes: "
        f"{', '.join(cast(list[str], resolution.get('reason_codes', []))) if resolution.get('reason_codes') else 'none'}",
        f"- Freshness reason codes: {', '.join(freshness_reason_codes) if freshness_reason_codes else 'none'}",
        f"- Waived reason codes: {', '.join(waived_reason_codes) if waived_reason_codes else 'none'}",
        "- Expired waiver reason codes: "
        f"{', '.join(expired_waiver_reason_codes) if expired_waiver_reason_codes else 'none'}",
        "",
        "## Checks",
    ]
    for check in checks:
        lines.extend(
            [
                f"- `{check.name}`: {'PASS' if check.ok else 'FAIL'}",
                f"  - url: {check.url}",
                f"  - http_status: {check.http_status}",
                f"  - details: {check.details}",
            ]
        )
    lines.extend(
        [
            "",
            "## Freshness",
            f"- run_age_hours: {freshness_metrics.get('run_age_hours')}",
            f"- release_age_hours: {freshness_metrics.get('release_age_hours')}",
            f"- rtd_age_hours: {freshness_metrics.get('rtd_age_hours')}",
            f"- max_run_age_hours: {freshness_thresholds.get('max_run_age_hours')}",
            f"- max_release_age_hours: {freshness_thresholds.get('max_release_age_hours')}",
            f"- max_rtd_age_hours: {freshness_thresholds.get('max_rtd_age_hours')}",
            "",
            "## Waivers",
            f"- configured_count: {waiver_summary.get('configured_count', 0)}",
            f"- matched_count: {waiver_summary.get('matched_count', 0)}",
            f"- waived_count: {waiver_summary.get('waived_count', 0)}",
            f"- expired_count: {waiver_summary.get('expired_count', 0)}",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def _render_ops_closeout_escalation_markdown(*, escalation_payload: dict[str, Any]) -> str:
    """Render deterministic escalation markdown payload."""
    run_context = escalation_payload.get("run_context", {})
    if not isinstance(run_context, dict):
        run_context = {}

    lines = [
        "# Ops Closeout Escalation Pack",
        "",
        f"- Escalation required: {str(bool(escalation_payload.get('escalation_required', False))).lower()}",
        "- Escalation reason codes: "
        f"{', '.join(cast(list[str], escalation_payload.get('escalation_reason_codes', []))) if escalation_payload.get('escalation_reason_codes') else 'none'}",
        "- Failed checks: "
        f"{', '.join(cast(list[str], escalation_payload.get('failed_checks', []))) if escalation_payload.get('failed_checks') else 'none'}",
        "- Effective reason codes: "
        f"{', '.join(cast(list[str], escalation_payload.get('effective_reason_codes', []))) if escalation_payload.get('effective_reason_codes') else 'none'}",
        f"- Mode: {escalation_payload.get('mode', 'observe')}",
        "",
        "## Run Context",
        f"- generated_at: {run_context.get('generated_at', 'unknown')}",
        f"- version: {run_context.get('version', 'unknown')}",
        f"- release_run_id: {run_context.get('release_run_id', 'unknown')}",
        f"- repo: {run_context.get('repo', 'unknown')}",
        f"- pypi_project: {run_context.get('pypi_project', 'unknown')}",
        f"- rtd_url: {run_context.get('rtd_url', 'unknown')}",
    ]
    lines.append("")
    return "\n".join(lines)


def _emit_export_output(payload_json: str, output: str | None) -> None:
    """Emit export payload either to stdout or to a file."""
    if output:
        output_path = Path(output)
        output_path.write_text(payload_json, encoding="utf-8")
        console.print(f"[green]Export payload saved to: {output_path}[/green]")
        return
    click.echo(payload_json)


def _build_check_output_payload(
    *,
    descriptor: AISystemDescriptor,
    report_result,
    articles_applicable: list[str],
    transparency_findings: list[TransparencyFinding],
    gpai_summary: dict[str, object],
    security_summary_payload: dict[str, object],
    security_gate_result,
) -> dict[str, object]:
    """Build canonical `check --json` payload."""
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

    return {
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
        "security_summary": {**security_summary_payload},
        "security_gate": security_gate_result.to_dict(),
        "audit_trail": report_result.audit_trail,
        "generated_at": report_result.generated_at,
    }


def _load_ops_closeout_policy_file(policy_path: str | None) -> dict[str, object]:
    if policy_path is None:
        return {}
    try:
        parsed = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Unable to read ops closeout policy file: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("Ops closeout policy file must contain a YAML object at top level.")
    return {str(key): value for key, value in parsed.items()}


def _load_export_gate_policy_file(policy_path: str | None) -> dict[str, object]:
    if policy_path is None:
        return {}
    try:
        parsed = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Unable to read policy file: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("Policy file must contain a YAML object at top level.")
    return {str(key): value for key, value in parsed.items()}


def _load_collaboration_gate_policy_file(policy_path: str | None) -> dict[str, object]:
    if policy_path is None:
        return {}
    try:
        parsed = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Unable to read policy file: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("Policy file must contain a YAML object at top level.")
    return {str(key): value for key, value in parsed.items()}


def _load_governance_handoff_policy_file(policy_path: str | None) -> dict[str, object]:
    if policy_path is None:
        return {}
    try:
        parsed = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Unable to read governance policy file: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("Governance policy file must contain a YAML object at top level.")
    return {str(key): value for key, value in parsed.items()}


def _emit_ops_log_warning(push_result: dict | None) -> None:
    """Emit best-effort export ops-log warning without changing command outcome."""
    if not isinstance(push_result, dict):
        return
    warning = push_result.get("ops_log_warning")
    if isinstance(warning, str) and warning.strip():
        click.echo(f"Warning: {warning}", err=True)


def _emit_reconcile_log_warning(payload: dict | None) -> None:
    """Emit best-effort reconcile-log warning without changing command outcome."""
    if not isinstance(payload, dict):
        return
    warning = payload.get("reconcile_log_warning")
    if isinstance(warning, str) and warning.strip():
        click.echo(f"Warning: {warning}", err=True)


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


def _history_security_summary(security_mapping) -> dict:
    """Build compact security summary payload for history snapshots."""
    return {
        "framework": security_mapping.framework,
        **security_mapping.summary.to_dict(),
    }


def _history_finding_statuses(findings: dict) -> dict:
    """Build requirement-to-status map for history events."""
    return {requirement_id: finding.status.value for requirement_id, finding in findings.items()}


if __name__ == "__main__":
    main()
