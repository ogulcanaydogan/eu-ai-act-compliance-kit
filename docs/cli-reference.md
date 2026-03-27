# CLI Reference

## Global

```bash
ai-act --help
ai-act --version
```

## `handoff`

Runs a deterministic one-command GA handoff flow and writes a fixed artifact pack.

```bash
ai-act handoff <system.yaml>
ai-act handoff <system.yaml> --output-dir handoff_pack
ai-act handoff <system.yaml> --output-dir handoff_pack --json
```

Flow:

`validate -> classify --json -> check --json -> security-map --json -> checklist (json+md) -> report --format html -> collaboration sync+summary`

Artifacts written to `<output-dir>` (default: current working directory):

- `validate.json`
- `classify.json`
- `check.json`
- `security_map.json`
- `checklist.json`
- `checklist.md`
- `report.html`
- `collaboration_summary.json`
- `handoff_manifest.json`

Manifest includes:

- `generated_at`, `system_name`, `descriptor_path`, `status`
- `risk_tier`, `articles_applicable`
- `compliance_summary`, `security_summary`, `collaboration_summary`
- `artifacts`, `failed_step`, `error`

Failure contract:

- If any step fails, command exits non-zero.
- `handoff_manifest.json` is still written with `status=failed`, `failed_step`, and `error`.

## `classify`

Classifies a system descriptor into a risk tier.

```bash
ai-act classify <system.yaml>
ai-act classify <system.yaml> --json
```

Options:

- `--json`: machine-readable output

## `check`

Runs requirement-level compliance checks.

```bash
ai-act check <system.yaml>
ai-act check <system.yaml> --json
ai-act check <system.yaml> --json --security-gate observe
ai-act check <system.yaml> --json --security-gate enforce
ai-act check <system.yaml> --json --security-gate enforce --security-gate-profile strict
```

Options:

- `--json`: machine-readable output
- `--security-gate [observe|enforce]`: security gate mode (default: `observe`)
- `--security-gate-profile [strict|balanced|lenient]`: profile threshold set (default: `balanced`)

JSON includes `summary`, `findings`, `transparency`, `gpai_summary`, `security_summary`, `security_gate`, and `audit_trail`.
Each successful run also attempts a best-effort history append to `.eu_ai_act/history.jsonl`.
Default mode is observe-only. In `enforce` mode, command exits non-zero when profile thresholds are breached:

- `strict`: any `non_compliant`, `partial`, or `not_assessed`
- `balanced`: any `non_compliant`
- `lenient`: `non_compliant >= 2`

Tier-aware override: `lenient` is treated as `balanced` for `high_risk` and `unacceptable` systems.

## `security-map`

Maps compliance findings to OWASP LLM Top 10 controls.

```bash
ai-act security-map <system.yaml>
ai-act security-map <system.yaml> --json
ai-act security-map <system.yaml> --json -o security_map.json
```

Options:

- `--json`: machine-readable output
- `-o, --output PATH`: write JSON payload to file

## `checklist`

Generates checklist artifacts.

```bash
ai-act checklist <system.yaml> --format json
ai-act checklist <system.yaml> --format md -o checklist.md
ai-act checklist <system.yaml> --format html -o checklist.html
```

Options:

- `--format [json|md|html]`
- `-o, --output PATH`

## `report`

Renders report artifacts from classification + checker + transparency + GPAI + checklist context.

```bash
ai-act report <system.yaml> --format json
ai-act report <system.yaml> --format md -o report.md
ai-act report <system.yaml> --format html -o report.html
ai-act report <system.yaml> --format pdf -o report.pdf
```

Options:

- `--format [json|md|html|pdf]`
- `-o, --output PATH`

PDF notes:

- `--output/-o` is required for `--format pdf`
- install optional dependency: `pip install -e ".[reporting]"`

`report` runs also append a history event (best effort). History write failures emit warning output but do not fail the command.
Report payloads include non-breaking `security_mapping` output alongside compliance, transparency, and GPAI sections.

## `dashboard build`

Builds a multi-system dashboard by scanning descriptor files in a directory.

```bash
ai-act dashboard build <descriptor_dir>
ai-act dashboard build <descriptor_dir> --recursive
ai-act dashboard build <descriptor_dir> --include-history --history-path .eu_ai_act/history.jsonl
ai-act dashboard build <descriptor_dir> --output-dir dashboard_artifacts
```

Outputs:

- `<output-dir>/dashboard.json`
- `<output-dir>/dashboard.html`
- `dashboard.json` includes additive security fields:
  - system-level `security_summary`
  - top-level `average_security_coverage_percentage`
  - top-level `security_control_status_distribution`

Options:

- `--recursive`
- `--include-history`
- `--history-path PATH`
- `--output-dir PATH` (default: current working directory)

Error policy:

- Invalid descriptors are skipped and included in the dashboard `errors` section.
- Command exits `0` if at least one valid system is processed.
- Command exits `1` if no valid systems are found.

## `history`

Inspect persisted audit history events and diffs.

```bash
ai-act history list
ai-act history list --event-type check --limit 10 --json
ai-act history show <event_id>
ai-act history diff <older_event_id> <newer_event_id> --json
```

Options:

- `history list`
  - `--system <name>`
  - `--event-type [check|report]`
  - `--limit N`
  - `--json`
  - `--history-path PATH`
- `history show`
  - `--json`
  - `--history-path PATH`
- `history diff`
  - `--json`
  - `--history-path PATH`

History payload notes:

- event payloads may include additive `security_summary` snapshots
- diff payload includes additive `security_summary_change` metrics:
  - `coverage_percentage`
  - `non_compliant_count`
  - `partial_count`
  - `not_assessed_count`

Default history path is project-local `.eu_ai_act/history.jsonl`, resolved from the nearest parent directory containing `pyproject.toml`. If no project root is found, the current working directory is used.

## `collaboration`

Manages local-first team collaboration tasks derived from compliance findings.

```bash
ai-act collaboration sync <system.yaml> --json
ai-act collaboration list --json
ai-act collaboration update <task_id> --status in_review --note "triage started" --note-author alice --json
ai-act collaboration summary --json
ai-act collaboration gate --mode observe --json
ai-act collaboration gate --mode enforce --policy config/collaboration_gate_policy.yaml --json
```

Subcommands:

- `collaboration sync`
  - source: live `check` findings for descriptor
  - options:
    - `--owner-default TEXT` (applies only to newly created tasks)
    - `--collab-path PATH` (override ledger location)
    - `-o, --output PATH`
    - `--json`
- `collaboration list`
  - options:
    - `--system <name>`
    - `--owner <name>`
    - `--status [open|in_review|blocked|done]`
    - `--limit N` (must be `>= 1`)
    - `--collab-path PATH`
    - `-o, --output PATH`
    - `--json`
- `collaboration update`
  - options:
    - `--status [open|in_review|blocked|done]`
    - `--owner <name>`
    - `--note <text>`
    - `--note-author <name>` (requires `--note`; default author is `unknown`)
    - `--collab-path PATH`
    - `-o, --output PATH`
    - `--json`
  - validation:
    - at least one of `--status`, `--owner`, or `--note` is required
    - unknown task id returns non-zero with deterministic error
- `collaboration summary`
  - options:
    - `--system <name>`
    - `--owner <name>`
    - `--collab-path PATH`
    - `-o, --output PATH`
    - `--json`
- `collaboration gate`
  - options:
    - `--mode [observe|enforce]` (default from policy/defaults; observe never blocks)
    - `--policy PATH` (optional YAML policy file)
    - `--system <name>`
    - `--blocked-max N` (must be `>= 0`)
    - `--unassigned-actionable-max N` (must be `>= 0`)
    - `--stale-actionable-max N` (must be `>= 0`, threshold disabled when omitted)
    - `--blocked-stale-max N` (must be `>= 0`, threshold disabled when omitted)
    - `--review-stale-max N` (must be `>= 0`, threshold disabled when omitted)
    - `--stale-after-hours F` (must be `> 0`)
    - `--blocked-stale-after-hours F` (must be `> 0`)
    - `--review-stale-after-hours F` (must be `> 0`)
    - `--limit N` (must be `>= 1`)
    - `--collab-path PATH`
    - `-o, --output PATH`
    - `--json`
  - exit policy:
    - observe mode always exits `0` and reports `failed` in payload
    - enforce mode exits non-zero when policy violations are present
    - enforce mode with missing collaboration data fails with `missing_collaboration_data`
  - additive reason codes:
    - `stale_actionable_threshold_exceeded`
    - `blocked_stale_threshold_exceeded`
    - `review_stale_threshold_exceeded`
  - policy schema additions:
    - `thresholds.stale_actionable_max`
    - `thresholds.blocked_stale_max`
    - `thresholds.review_stale_max`
    - `sla.stale_after_hours`
    - `sla.blocked_stale_after_hours`
    - `sla.review_stale_after_hours`

Workflow semantics:

- task ledger is append-only JSONL: `.eu_ai_act/collaboration_tasks.jsonl`
- task id is deterministic: `system_name::requirement_id`
- actionable findings (`non_compliant|partial|not_assessed`) create/update tasks
- previously `done` tasks are reopened as `open` when finding becomes actionable again
- actionable resolution (`compliant`) auto-closes active tasks to `done`
- owner and notes are preserved across sync updates
- gate policy precedence is deterministic: `CLI flags > policy file > defaults`

## `export`

Builds payload-first external artifacts for integration targets.
Default behavior is still payload-only; live push is opt-in via `--push`.

```bash
ai-act export check <system.yaml> --target generic --json
ai-act export check <system.yaml> --target jira -o export_jira.json
ai-act export history <event_id> --target servicenow --history-path .eu_ai_act/history.jsonl --json
ai-act export check <system.yaml> --target jira --push --dry-run --json
ai-act export check <system.yaml> --target jira --push --push-mode upsert --json
ai-act export batch examples --target generic --json
ai-act export batch examples --target jira --push --push-mode upsert --json
ai-act export replay --target jira --limit 20 --json
ai-act export replay --target servicenow --since-hours 24 --dry-run --json
ai-act export rollup --target jira --since-hours 24 --json
ai-act export gate --target jira --mode observe --json
ai-act export gate --target servicenow --mode enforce --policy ops_policy.yaml --json
ai-act export reconcile --target jira --json
ai-act export ledger list --json
ai-act export ledger stats --json
```

Subcommands:

- `export check`
  - source: fresh compliance check for descriptor
  - options:
    - `--target [jira|servicenow|generic]` (required)
    - `-o, --output PATH`
    - `--history-path PATH` (accepted for contract compatibility)
    - `--push` (optional live push for `jira`/`servicenow`)
    - `--push-mode [create|upsert]` (default: `create`, requires `--push`)
    - `--dry-run` (simulated push summary, no network call)
    - `--max-retries INT` (default: `3`, must be `>= 0`)
    - `--retry-backoff-seconds FLOAT` (default: `1.0`, must be `> 0`)
    - `--timeout-seconds FLOAT` (default: `30.0`, must be `> 0`)
    - `--idempotency-path PATH` (override push ledger location)
    - `--disable-idempotency` (disable duplicate-skip ledger checks)
    - `--json` (JSON is default output shape)
- `export history`
  - source: existing history event (`event_id`)
  - options:
    - `--target [jira|servicenow|generic]` (required)
    - `-o, --output PATH`
    - `--history-path PATH`
    - `--push` (optional live push for `jira`/`servicenow`)
    - `--push-mode [create|upsert]` (default: `create`, requires `--push`)
    - `--dry-run` (simulated push summary, no network call)
    - `--max-retries INT` (default: `3`, must be `>= 0`)
    - `--retry-backoff-seconds FLOAT` (default: `1.0`, must be `> 0`)
    - `--timeout-seconds FLOAT` (default: `30.0`, must be `> 0`)
    - `--idempotency-path PATH` (override push ledger location)
    - `--disable-idempotency` (disable duplicate-skip ledger checks)
    - `--json` (JSON is default output shape)
- `export batch`
  - source: descriptor directory scan (`*.yaml|*.yml`, deterministic order)
  - options:
    - `--target [jira|servicenow|generic]` (required)
    - `--recursive` (scan nested directories)
    - `-o, --output PATH`
    - `--push` (optional live push for `jira`/`servicenow`)
    - `--push-mode [create|upsert]` (default: `create`, requires `--push`)
    - `--dry-run` (simulated push summaries, no network call)
    - `--max-retries INT` (default: `3`, must be `>= 0`)
    - `--retry-backoff-seconds FLOAT` (default: `1.0`, must be `> 0`)
    - `--timeout-seconds FLOAT` (default: `30.0`, must be `> 0`)
    - `--idempotency-path PATH` (override push ledger location)
    - `--disable-idempotency` (disable duplicate-skip ledger checks)
    - `--json` (JSON is default output shape)
- `export reconcile`
  - source: persisted push ledger records (`.eu_ai_act/export_push_ledger.jsonl`)
  - options:
    - `--target [jira|servicenow]` (required)
    - `--idempotency-path PATH` (override ledger location)
    - `--system <name>`
    - `--requirement-id <id>`
    - `--limit N` (default: `50`, must be `>= 1`)
    - `--max-retries INT` (default: `3`, must be `>= 0`)
    - `--retry-backoff-seconds FLOAT` (default: `1.0`, must be `> 0`)
    - `--timeout-seconds FLOAT` (default: `30.0`, must be `> 0`)
    - `--repair` (build repair plan for drifted records; no write by default)
    - `--apply` (execute remote repair updates; requires `--repair`)
    - `-o, --output PATH`
    - `--json` (JSON is default output shape)
- `export replay`
  - source: failed operation records from persistent ops log (`.eu_ai_act/export_ops_log.jsonl`)
  - options:
    - `--target [jira|servicenow]` (required)
    - `--since-hours FLOAT` (optional; must be `>= 0`)
    - `--system <name>`
    - `--requirement-id <id>`
    - `--limit N` (default: `25`, must be `>= 1`)
    - `--push-mode [create|upsert]` (default: `create`)
    - `--dry-run` (selection + replay simulation, no network call)
    - `--max-retries INT` (default: `3`, must be `>= 0`)
    - `--retry-backoff-seconds FLOAT` (default: `1.0`, must be `> 0`)
    - `--timeout-seconds FLOAT` (default: `30.0`, must be `> 0`)
    - `--idempotency-path PATH` (override push ledger location)
    - `--disable-idempotency`
    - `--ops-path PATH` (override ops log location)
    - `-o, --output PATH`
    - `--json` (JSON is default output shape)
- `export rollup`
  - source: persistent ops log + push ledger aggregation (read-only analytics)
  - options:
    - `--target [jira|servicenow|generic]` (optional filter)
    - `--system <name>`
    - `--since-hours FLOAT` (optional; must be `>= 0`)
    - `--limit N` (optional; must be `>= 1`)
    - `--ops-path PATH` (override ops log location)
    - `--idempotency-path PATH` (override ledger location)
    - `-o, --output PATH`
    - `--json` (JSON is default output shape)
- `export gate`
  - source: policy evaluation over rollup + reconcile summary windows
  - options:
    - `--target [jira|servicenow]` (required)
    - `--system <name>`
    - `--since-hours FLOAT` (optional; defaults to resolved policy window)
    - `--limit N` (optional; defaults to resolved policy window)
    - `--mode [observe|enforce]` (default: `observe`)
    - `--policy PATH` (optional YAML policy file)
    - `--open-failures-max INT` (default: `0`, must be `>= 0`)
    - `--drift-max INT` (default: `0`, must be `>= 0`)
    - `--min-success-rate FLOAT` (default: `95.0`, must be in `0..100`)
    - `--ops-path PATH` (override ops log location)
    - `--reconcile-log-path PATH` (override reconcile log location)
    - `-o, --output PATH`
    - `--json` (JSON is default output shape)
  - policy precedence:
    - CLI flags override policy file values
    - policy file values override built-in defaults
  - canonical policy:
    - repository default policy file: `config/export_ops_gate_policy.yaml`
    - action/CI consume the same policy source for governance consistency
  - enforce behavior:
    - exits non-zero when any threshold is violated
    - exits non-zero when reconcile data is missing (`missing_reconcile_data`)
  - observe behavior:
    - emits the same decision payload but always exits zero
- `export ledger list`
  - source: persisted push idempotency ledger (`.eu_ai_act/export_push_ledger.jsonl`)
  - options:
    - `--idempotency-path PATH` (override ledger location)
    - `--target [jira|servicenow|generic]`
    - `--system <name>`
    - `--requirement-id <id>`
    - `--limit N` (default: `25`, must be `>= 1`)
    - `--json`
- `export ledger stats`
  - source: persisted push idempotency ledger (`.eu_ai_act/export_push_ledger.jsonl`)
  - options:
    - `--idempotency-path PATH` (override ledger location)
    - `--json`

Output contract:

- top-level: `schema_version`, `generated_at`, `source_type`, `target`, `system_name`, `risk_tier`, `summary`, `items`
- additive top-level security block: `security_mapping` (`framework`, `summary`, `controls`)
- history-source extras: `event_id`, `event_type`, `descriptor_path`, `history_generated_at`
- item fields: `requirement_id`, `title`, `status`, `severity`, `article`, `gap_analysis`, `guidance`, `success_criteria`, `actionable`
- adapter payload emitted under `adapter_payload` (`generic`, `jira`, `servicenow`)
- when `--push` or `--dry-run` is used, output may include `push_result`
  - includes diagnostics: `push_mode`, `attempted_actionable_count`, `pushed_count`, `created_count`, `updated_count`, `failed_count`, `skipped_duplicate_count`, `failure_reason`, `max_retries`, `retry_backoff_seconds`, `timeout_seconds`, `idempotency_enabled`, `idempotency_path`
- `export batch` top-level contract:
  - `generated_at`, `scan_root`, `target`, `recursive`, `total_files`, `processed_count`, `success_count`, `failure_count`, `invalid_count`, `results`
  - successful `results[]` entries include additive `security_mapping`
- `export reconcile` top-level contract:
  - `generated_at`, `target`, `ledger_path`, `filters`, `repair_enabled`, `apply`, `checked_count`, `exists_count`, `in_sync_count`, `drift_count`, `missing_count`, `error_count`, `repair_planned_count`, `repair_applied_count`, `repair_failed_count`, `results`
- `export replay` top-level contract:
  - `generated_at`, `target`, `ops_path`, `selected_count`, `replayed_count`, `failed_count`, `unreplayable_count`, `results`
- `export rollup` top-level contract:
  - `generated_at`, `window`, `metrics`, `distributions`, `systems_with_failures`, `top_failure_reasons`, `ops_path`, `idempotency_path`
- `export gate` top-level contract:
  - `generated_at`, `target`, `system_name`, `mode`, `failed`, `reason_codes`, `effective_policy`, `rollup_metrics`, `reconcile_metrics`, `decision_details`, `ops_path`, `reconcile_log_path`

Push behavior policy:

- strict fail-fast: push aborts at the first actionable item that still fails after retries
- `--push-mode` is accepted only together with `--push`
- retries are attempted only for transport errors and HTTP `429`/`5xx`
- non-retryable `4xx` responses fail immediately
- in `create` mode with idempotency enabled, duplicate actionable items are skipped before remote API call
- in `upsert` mode, Jira/ServiceNow always perform lookup-first and then update existing records or create new ones
- `export check|history|batch --push` writes per-item operation events to `.eu_ai_act/export_ops_log.jsonl` (best-effort warning on write failure, command outcome unchanged)
- `export batch` continues processing after invalid descriptor/push failures and exits non-zero when any invalid/failure exists
- `export replay` dedupes failed records by `idempotency_key` (latest record wins), continues across records, and exits non-zero when any replay failure or unreplayable source exists
- `export reconcile` supports guarded repair:
  - `--repair` plans changes only (no write)
  - `--repair --apply` executes remote updates
- `export reconcile` exits non-zero when any of these are true:
  - `missing_count > 0`
  - `error_count > 0`
  - `drift_count > 0`
  - `repair_failed_count > 0`
- `export reconcile` writes append-only best-effort reconcile records to `.eu_ai_act/export_reconcile_log.jsonl` (warning-only on write failure)
- `export gate` evaluates multi-threshold policy:
  - `open_failures_count > open_failures_max`
  - `drift_count > drift_max`
  - `success_rate < min_success_rate`
  - enforce-only fail when reconcile data is missing
- CI rollout policy:
  - pull requests run export-ops gate in `observe`
  - push/tag pipelines run export-ops gate in `enforce`

Live push environment variables:

- Jira:
  - `EU_AI_ACT_JIRA_BASE_URL`
  - `EU_AI_ACT_JIRA_EMAIL`
  - `EU_AI_ACT_JIRA_API_TOKEN`
  - `EU_AI_ACT_JIRA_PROJECT_KEY`
- ServiceNow:
  - `EU_AI_ACT_SERVICENOW_INSTANCE_URL`
  - `EU_AI_ACT_SERVICENOW_USERNAME`
  - `EU_AI_ACT_SERVICENOW_PASSWORD`
  - `EU_AI_ACT_SERVICENOW_TABLE` (optional; default adapter table)
  - `EU_AI_ACT_SERVICENOW_IDEMPOTENCY_FIELD` (optional; default: `u_idempotency_key`)
- Ops log:
  - `EU_AI_ACT_EXPORT_OPS_LOG_PATH` (optional override for `.eu_ai_act/export_ops_log.jsonl`)
- Reconcile log:
  - `EU_AI_ACT_EXPORT_RECONCILE_LOG_PATH` (optional override for `.eu_ai_act/export_reconcile_log.jsonl`)

## `transparency`

Evaluates transparency obligations from system descriptors.

```bash
ai-act transparency <system.yaml>
ai-act transparency <system.yaml> --json
```

Options:

- `--json`

## `gpai`

Evaluates GPAI obligations from GPAI model descriptors.

```bash
ai-act gpai <model.yaml>
ai-act gpai <model.yaml> --json
```

Options:

- `--json`

## `validate`

Schema validation for AI system descriptors.

```bash
ai-act validate <system.yaml>
```

## `articles`

Prints article mappings by tier.

```bash
ai-act articles
ai-act articles --tier minimal
ai-act articles --tier limited
ai-act articles --tier high_risk
ai-act articles --tier unacceptable
```

Options:

- `--tier [minimal|limited|high_risk|unacceptable]`

## Exit Behavior

- Non-zero exits are used for invalid file/schema or command-level runtime failures.
- In CI gating, failure logic is implemented by the composite action policy.
