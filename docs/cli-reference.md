# CLI Reference

## Global

```bash
ai-act --help
ai-act --version
```

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
```

Options:

- `--json`: machine-readable output

JSON includes `summary`, `findings`, `transparency`, `gpai_summary`, and `audit_trail`.
Each successful run also attempts a best-effort history append to `.eu_ai_act/history.jsonl`.

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

Default history path is project-local `.eu_ai_act/history.jsonl`, resolved from the nearest parent directory containing `pyproject.toml`. If no project root is found, the current working directory is used.

## `export`

Builds payload-first external artifacts for integration targets.
Default behavior is still payload-only; live push is opt-in via `--push`.

```bash
ai-act export check <system.yaml> --target generic --json
ai-act export check <system.yaml> --target jira -o export_jira.json
ai-act export history <event_id> --target servicenow --history-path .eu_ai_act/history.jsonl --json
ai-act export check <system.yaml> --target jira --push --dry-run --json
ai-act export check <system.yaml> --target jira --push --push-mode upsert --json
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
- history-source extras: `event_id`, `event_type`, `descriptor_path`, `history_generated_at`
- item fields: `requirement_id`, `title`, `status`, `severity`, `article`, `gap_analysis`, `guidance`, `success_criteria`, `actionable`
- adapter payload emitted under `adapter_payload` (`generic`, `jira`, `servicenow`)
- when `--push` or `--dry-run` is used, output may include `push_result`
  - includes diagnostics: `push_mode`, `attempted_actionable_count`, `pushed_count`, `created_count`, `updated_count`, `failed_count`, `skipped_duplicate_count`, `failure_reason`, `max_retries`, `retry_backoff_seconds`, `timeout_seconds`, `idempotency_enabled`, `idempotency_path`

Push behavior policy:

- strict fail-fast: push aborts at the first actionable item that still fails after retries
- `--push-mode` is accepted only together with `--push`
- retries are attempted only for transport errors and HTTP `429`/`5xx`
- non-retryable `4xx` responses fail immediately
- when idempotency is enabled, duplicate actionable items are skipped before remote API call
- in `upsert` mode, Jira/ServiceNow first perform remote lookup then update existing records or create new ones

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
