# Launch Post Draft: Practical EU AI Act Readiness for Engineering Teams

## Why We Built This

The EU AI Act changes how AI systems are designed, shipped, and governed in
production environments. For most teams, the problem is not reading the text of
the regulation. The hard part is translating legal obligations into repeatable
engineering workflows with clear evidence and predictable release gates.

EU AI Act Compliance Kit was built to solve that translation layer.

It does three practical things:

1. Classifies an AI system by risk tier with deterministic logic.
2. Evaluates requirement-level compliance signals with explicit statuses.
3. Produces implementation artifacts teams can act on: checklist items, reports,
   and CI/CD gate outputs.

This is not a legal opinion engine. It is an engineering control plane for
compliance work.

## The Core Problem in Most Teams

Most compliance programs fail at handoff points:

- Policy teams define requirements in prose.
- Engineering teams need concrete controls and measurable outcomes.
- Audit teams require traceable evidence, timestamps, and change history.

Without a common structure, the result is fragmented spreadsheets, ad hoc
reviews, and release-time surprises.

The toolkit standardizes the flow around a single descriptor format and a
repeatable command set.

## What the Toolkit Covers

### 1) Risk Classification

Given a YAML descriptor, the classifier assigns one of four tiers:

- `unacceptable`
- `high_risk`
- `limited`
- `minimal`

The output includes reasoning, confidence, and applicable article references.
This gives teams a concrete starting point before implementation and legal
review cycles.

### 2) Compliance Checker

For the active article set (`Art. 5`, `Art. 10`, `Art. 11`, `Art. 13`,
`Art. 14`, `Art. 15`, `Art. 43`, `Art. 50`), the checker returns requirement
findings with statuses:

- `compliant`
- `non_compliant`
- `partial`
- `not_assessed`

The status model is intentionally conservative. Missing evidence is not assumed
compliant. This keeps false confidence low and forces evidence collection to be
explicit.

### 3) Checklist Generation

Checklist output is action-focused. Only actionable statuses become work items:

- `non_compliant`
- `partial`
- `not_assessed`

Each item includes identifier, article, severity, deadline months, guidance,
success criteria, and gap analysis. Teams can map these directly into delivery
or governance backlogs.

### 4) Reporting

Reports are rendered from a shared payload in:

- JSON
- Markdown
- HTML

Sections include executive summary, compliance summary, compliance findings,
transparency findings, GPAI assessment, recommended actions, and audit trail.

### 5) Transparency and GPAI Signals

The toolkit includes rule-based modules for:

- Art. 50 transparency/disclosure indicators
- Deepfake/synthetic media indicators
- GPAI obligation checks for Art. 51-55

GPAI systemic risk uses deterministic thresholds and conservative handling of
missing evidence.

## CI/CD as the Control Surface

A compliance check that does not run in CI is usually too late.

The included composite GitHub Action runs classify/check/report and exposes
stable outputs for pipeline logic:

- `risk_tier`
- `compliance_percentage`
- `total_requirements`
- `compliant_count`
- `non_compliant_count`
- `partial_count`
- `not_assessed_count`
- `articles_applicable`
- `report_path`

Gate behavior is explicit:

- `unacceptable` always fails
- `high_risk` fails when `fail_on_high_risk=true` and `non_compliant_count > 0`

This policy keeps the action strict where it matters most while still allowing
teams to adopt staged rollout models.

## A Minimal End-to-End Workflow

```bash
ai-act validate my_system.yaml
ai-act classify my_system.yaml --json
ai-act check my_system.yaml --json
ai-act checklist my_system.yaml --format md -o checklist.md
ai-act report my_system.yaml --format html -o report.html
```

In practice, this sequence provides:

- A deterministic classification decision
- Requirement-level findings and count metrics
- A backlog-ready checklist
- An auditable report artifact

## Why This Matters for Launch Readiness

Shipping AI in regulated contexts demands more than model quality metrics.
Engineering organizations need a reproducible method for proving that they asked
and answered the right compliance questions at the right points in the delivery
process.

This toolkit is designed for that operational layer:

- Explicit inputs (descriptor files)
- Deterministic rules
- Machine-readable outputs
- Human-readable artifacts
- CI gate compatibility

## Current Scope and Honest Boundaries

What it does now:

- Rule-based risk and requirement evaluation
- Transparency and GPAI signal checks
- Action-oriented checklist output
- JSON/Markdown/HTML/PDF reporting
- CI/CD integration with deterministic gate policy

What it is not:

- A substitute for legal counsel
- A guarantee of legal compliance

## Who Should Use It

- AI platform teams building release gates
- Compliance engineering teams building evidence pipelines
- Security/governance teams standardizing AI controls
- Product teams needing structured readiness checks before launch

## Getting Started in One Session

1. Clone the repository.
2. Run one example (`medical_diagnosis.yaml` for high-risk, `spam_filter.yaml`
   for minimal risk).
3. Integrate the composite action in a non-blocking mode first.
4. Move to blocking mode using the default fail policy once evidence quality is
   stable.
5. Pair technical outputs with legal review for sign-off.

## Closing

Regulatory alignment is no longer a side process for AI systems. It is part of
production engineering.

EU AI Act Compliance Kit gives teams a deterministic baseline they can run,
inspect, test, and integrate into release workflows today.

Repository: https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit
Documentation: https://eu-ai-act-compliance-kit.readthedocs.io
