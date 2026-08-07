[![CI](https://img.shields.io/github/actions/workflow/status/ogulcanaydogan/eu-ai-act-compliance-kit/ci.yml?branch=main&label=ci)](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/actions/workflow/status/ogulcanaydogan/eu-ai-act-compliance-kit/release.yml?branch=main&label=release)](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/workflows/release.yml)
[![PyPI](https://img.shields.io/pypi/v/eu-ai-act-compliance-kit)](https://pypi.org/project/eu-ai-act-compliance-kit/)
[![Docs](https://readthedocs.org/projects/eu-ai-act-compliance-kit/badge/?version=latest)](https://eu-ai-act-compliance-kit.readthedocs.io)
[![Python](https://img.shields.io/pypi/pyversions/eu-ai-act-compliance-kit)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

# EU AI Act Compliance Kit

Open-source toolkit to operationalize **EU AI Act (Regulation 2024/1689)** obligations.  
It classifies AI systems by risk tier, evaluates compliance evidence, generates actionable checklists, and produces audit-ready reports.

## Why This Exists

Teams building AI for EU markets need a practical path from policy text to engineering controls. This project provides that path:

- **Risk classification** (`unacceptable`, `high_risk`, `limited`, `minimal`)
- **Evidence-based compliance checks** (status model: `compliant`, `partial`, `non_compliant`, `not_assessed`)
- **Checklist and remediation workflow** tied to article-level obligations
- **Team collaboration workflow** with local task assignment, review states, notes, and summaries
- **Auditable reporting** in `json`, `md`, `html`, `pdf`
- **CI/CD + pre-push gates** aligned with deterministic fail policy
- **History and dashboard artifacts** for trend visibility across systems

## End-to-End Pipeline

```mermaid
flowchart LR
    A["AI System Descriptor (YAML)"] --> B["validate"]
    B --> C["classify --json"]
    C --> D["check --json"]
    D --> E["checklist"]
    D --> J["collaboration sync/list/update/summary/gate"]
    D --> F["report (json|md|html|pdf)"]
    D --> G["history append (JSONL)"]
    C --> H["articles"]
    D --> I["dashboard build"]
    G --> I
```

## CI/CD and Action Gate Flow

```mermaid
flowchart LR
    A["PR / Push"] --> B["GitHub Action: classify + check + report"]
    B --> C{"risk_tier == unacceptable?"}
    C -- "yes" --> Z["Fail"]
    C -- "no" --> D{"risk_tier == high_risk\nAND non_compliant_count > 0\nAND fail_on_high_risk=true?"}
    D -- "yes" --> Z
    D -- "no" --> S{"security_gate_mode == enforce\nAND security_gate_failed == true?"}
    S -- "yes" --> Z
    S -- "no" --> X{"export_ops_gate_mode == enforce\nAND export_ops_gate_failed == true?"}
    X -- "yes" --> Z
    X -- "no" --> Y{"collaboration_gate_mode == enforce\nAND collaboration_gate_failed == true?"}
    Y -- "yes" --> Z
    Y -- "no" --> E["Pass"]
    B --> F["Outputs: compliance %, counts, report path"]
```

## Quick Start

### Install

```bash
pip install eu-ai-act-compliance-kit
# or
pip install -e .
```

For PDF export support:

```bash
pip install -e ".[reporting]"
```

### Run

```bash
ai-act handoff examples/medical_diagnosis.yaml --output-dir handoff_pack --json
ai-act handoff examples/medical_diagnosis.yaml --output-dir handoff_pack --governance --governance-mode observe --json
ai-act handoff examples/medical_diagnosis.yaml --output-dir handoff_pack --governance --governance-policy config/governance_handoff_policy.yaml --json
ai-act ops closeout --version 0.1.31 --release-run-id 23718807136 --json
ai-act ops closeout --policy config/ops_closeout_policy.yaml --json
ai-act ops closeout --policy config/ops_closeout_policy.yaml --resolve-latest-release --json
ai-act ops closeout --policy config/ops_closeout_policy.yaml --max-run-age-hours 24 --max-release-age-hours 24 --max-rtd-age-hours 24 --json
ai-act ops closeout --version 0.1.31 --release-run-id 23718807136 --max-run-age-hours 1 --max-release-age-hours 1 --max-rtd-age-hours 1 --waiver-reason-code github_run_stale --waiver-expires-at 2099-01-01T00:00:00Z --json
ai-act ops closeout --policy config/ops_closeout_policy.yaml --resolve-latest-release --escalation-pack --json
ai-act validate examples/medical_diagnosis.yaml
ai-act classify examples/medical_diagnosis.yaml --json
ai-act check examples/medical_diagnosis.yaml --json
ai-act security-map examples/medical_diagnosis.yaml --json
ai-act checklist examples/medical_diagnosis.yaml --format md -o checklist.md
ai-act report examples/medical_diagnosis.yaml --format html -o report.html
ai-act export check examples/medical_diagnosis.yaml --target generic --json
```

## CLI Surface

- `ai-act handoff <system.yaml> [--output-dir PATH] [--json] [--governance] [--governance-mode observe|enforce] [--governance-policy PATH] [--export-target jira|servicenow]`
- `ai-act ops closeout [--version <semver>] [--release-run-id <id>] [--mode observe|enforce] [--policy PATH] [--resolve-latest-release] [--repo owner/name] [--pypi-project NAME] [--rtd-url URL] [--max-run-age-hours H] [--max-release-age-hours H] [--max-rtd-age-hours H] [--waiver-reason-code CODE --waiver-expires-at ISO8601_UTC] [--escalation-pack] [--output-dir PATH] [--json]`
- `ai-act classify <system.yaml> [--json]`
- `ai-act check <system.yaml> [--json] [--security-gate observe|enforce] [--security-gate-profile strict|balanced|lenient]`
- `ai-act security-map <system.yaml> [--json] [--output PATH]`
- `ai-act checklist <system.yaml> [--format json|md|html]`
- `ai-act transparency <system.yaml> [--json]`
- `ai-act gpai <model.yaml> [--json]`
- `ai-act report <system.yaml> [--format json|md|html|pdf]`
- `ai-act validate <system.yaml>`
- `ai-act articles [--tier minimal|limited|high_risk|unacceptable]`
- `ai-act history list|show|diff`
- `ai-act collaboration sync|list|update|summary|gate`
- `ai-act dashboard build <descriptor_dir> [--recursive] [--include-history]`
- `ai-act export check <system.yaml> --target jira|servicenow|generic [--output PATH] [--history-path PATH] [--json] [--push] [--push-mode create|upsert] [--dry-run] [--idempotency-path PATH] [--disable-idempotency]`
- `ai-act export history <event_id> --target jira|servicenow|generic [--output PATH] [--history-path PATH] [--json] [--push] [--push-mode create|upsert] [--dry-run] [--idempotency-path PATH] [--disable-idempotency]`
- `ai-act export batch <descriptor_dir> --target jira|servicenow|generic [--recursive] [--output PATH] [--json] [--push] [--push-mode create|upsert] [--dry-run] [--idempotency-path PATH] [--disable-idempotency]`
- `ai-act export replay --target jira|servicenow [--since-hours N] [--system NAME] [--requirement-id ID] [--limit N] [--push-mode create|upsert] [--dry-run] [--max-retries N] [--retry-backoff-seconds F] [--timeout-seconds F] [--idempotency-path PATH] [--disable-idempotency] [--ops-path PATH] [--output PATH] [--json]`
- `ai-act export rollup [--target jira|servicenow|generic] [--system NAME] [--since-hours N] [--limit N] [--ops-path PATH] [--idempotency-path PATH] [--output PATH] [--json]`
- `ai-act export gate --target jira|servicenow [--system NAME] [--since-hours N] [--limit N] [--mode observe|enforce] [--policy PATH] [--open-failures-max N] [--drift-max N] [--min-success-rate F] [--ops-path PATH] [--reconcile-log-path PATH] [--output PATH] [--json]`
- `ai-act export reconcile --target jira|servicenow [--idempotency-path PATH] [--system NAME] [--requirement-id ID] [--limit N] [--output PATH] [--json]`
- `ai-act export ledger list [--idempotency-path PATH] [--target jira|servicenow|generic] [--system NAME] [--requirement-id ID] [--limit N] [--json]`
- `ai-act export ledger stats [--idempotency-path PATH] [--json]`

Full reference: [docs/cli-reference.md](docs/cli-reference.md)

## Security Ops Signals (Observe-by-Default)

- `ai-act check --json` includes `security_summary`.
- `ai-act check --json` includes additive `security_gate`.
- `ai-act check --security-gate enforce` applies profile thresholds (`strict|balanced|lenient`) with tier-aware override for `lenient` on `high_risk|unacceptable`.
- `dashboard.json` includes system-level `security_summary` and top-level security aggregates.
- `history` events can persist `security_summary`; `history diff` includes security delta metrics.
- `export check|history|batch` payloads include additive top-level `security_mapping`.
- Security policy remains backward-compatible: default mode is `observe`, default profile is `balanced`.
- Export operations governance supports policy-based gate evaluation via `ai-act export gate` (default `observe`, optional `enforce`).
- Action + CI rollout now uses a shared export-ops policy file with tiered mode:
  - pull requests: `observe`
  - main/tag flows: `enforce`
- Ops closeout governance supports policy-driven execution via `ai-act ops closeout --policy ...`:
  - pull requests: `observe`
  - main/tag flows: `enforce`
  - optional time-bounded waivers suppress matching reason codes until expiry.
  - optional escalation pack emits deterministic escalation artifacts (`ops_closeout_escalation.json`, `ops_closeout_escalation.md`).

## Example Systems

- `examples/medical_diagnosis.yaml` (high risk)
- `examples/hiring_tool.yaml` (high risk)
- `examples/social_scoring.yaml` (unacceptable)
- `examples/chatbot.yaml` (minimal)
- `examples/spam_filter.yaml` (minimal)
- `examples/public_benefits_triage.yaml` (high risk with expected compliance gaps)
- `examples/synthetic_media_campaign_assistant.yaml` (limited/transparency-heavy)
- `examples/gpai_model.yaml` / `examples/gpai_model_low_risk.yaml` / `examples/gpai_model_unknown_thresholds.yaml`

## GitHub Action Contract

Action entrypoint: [`action.yml`](action.yml)

Outputs:

- `risk_tier`
- `compliance_percentage`
- `report_path`
- `articles_applicable`
- `total_requirements`
- `compliant_count`
- `non_compliant_count`
- `partial_count`
- `not_assessed_count`
- `security_non_compliant_count`
- `security_partial_count`
- `security_not_assessed_count`
- `security_gate_failed`
- `export_ops_gate_failed`
- `export_ops_gate_reason_codes`
- `export_ops_open_failures_count`
- `export_ops_drift_count`
- `export_ops_success_rate`
- `collaboration_open_count`
- `collaboration_in_review_count`
- `collaboration_blocked_count`
- `collaboration_done_count`
- `collaboration_unassigned_actionable_count`
- `collaboration_stale_actionable_count`
- `collaboration_blocked_stale_count`
- `collaboration_review_stale_count`
- `collaboration_gate_failed`
- `collaboration_gate_reason_codes`
- `ops_closeout_failed`
- `ops_closeout_reason_codes`
- `ops_closeout_failed_checks`
- `ops_closeout_freshness_reason_codes`
- `ops_closeout_run_age_hours`
- `ops_closeout_release_age_hours`
- `ops_closeout_rtd_age_hours`
- `ops_closeout_waived_reason_codes`
- `ops_closeout_expired_waiver_reason_codes`
- `ops_closeout_escalation_required`
- `ops_closeout_escalation_reason_codes`

Fail policy:

- `unacceptable` always fails
- `high_risk` fails only when `fail_on_high_risk=true` and `non_compliant_count > 0`
- security gate fails only when `security_gate_mode=enforce` and action-evaluated `security_gate_failed=true`
- export-ops gate fails only when `export_ops_gate_mode=enforce` and action-evaluated export governance result is failed
- collaboration gate fails only when `collaboration_gate_mode=enforce` and action-evaluated collaboration governance result is failed
- ops-closeout gate fails only when `ops_closeout_enabled=true`, `ops_closeout_mode=enforce`, and action-evaluated ops closeout result is failed

## Open-Core Boundary

Everything in this repository is open source under Apache-2.0:

- Core compliance engine (classification/checker/checklist/transparency/gpai)
- CLI + report generation + local history/dashboard
- Documentation, examples, and CI integration

Enterprise policy packs, jurisdiction overlays, and hosted multi-tenant operation
are kept out of scope here to keep the open-source core focused.

## Development

```bash
pip install -e ".[dev,docs]"
pytest -q
mkdocs build --strict
```

## First Contribution Path

```bash
pip install -e ".[dev,docs]"
./scripts/quickstart_smoke.sh
pre-commit install --hook-type pre-push
pre-commit run --hook-stage pre-push --all-files
```

If all checks pass, pick a small docs or test issue, open a focused PR, and
include command outputs in the PR description.

Local pre-push gate:

```bash
pre-commit install --hook-type pre-push
pre-commit run --hook-stage pre-push --all-files
```

## Documentation

- [Documentation Home](docs/index.md)
- [Installation](docs/installation.md)
- [Quickstart](docs/quickstart.md)
- [CLI Reference](docs/cli-reference.md)
- [API Reference](docs/api-reference.md)
- [Custom Systems](docs/custom-systems.md)
- [Examples](docs/examples.md)
- [Adoption Evidence Template](docs/adoption_evidence_template.md)

## Project Status

Stable and in active maintenance. The core compliance engine, CLI, reporting, and
GitHub Action are feature-complete for the v0.1.x line and covered by 350+ tests on
Python 3.11-3.13. Release history is in [CHANGELOG.md](CHANGELOG.md); planned work is
tracked in [ROADMAP.md](ROADMAP.md); contribution setup is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Maintenance Playbook

- Run local maintenance gate before release or policy updates:
  - `uv run pytest -q`
  - `uv run mypy src/eu_ai_act`
  - `uv run mkdocs build --strict`
  - `uv run --with bandit bandit -r src/eu_ai_act`
- Use `ai-act ops closeout --policy config/ops_closeout_policy.yaml --resolve-latest-release --escalation-pack --json` for deterministic closeout evidence.
- Keep governance policies centralized in `config/*.yaml`; prefer policy files over ad-hoc flag mixes for repeatable operations.

## Disclaimer

This project provides technical compliance signals and engineering guidance. It is not legal advice.

## License

Apache License 2.0. See [LICENSE](LICENSE).
