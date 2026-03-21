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

Builds payload-first external artifacts for integration targets without making network calls.

```bash
ai-act export check <system.yaml> --target generic --json
ai-act export check <system.yaml> --target jira -o export_jira.json
ai-act export history <event_id> --target servicenow --history-path .eu_ai_act/history.jsonl --json
```

Subcommands:

- `export check`
  - source: fresh compliance check for descriptor
  - options:
    - `--target [jira|servicenow|generic]` (required)
    - `-o, --output PATH`
    - `--history-path PATH` (accepted for contract compatibility)
    - `--json` (JSON is default output shape)
- `export history`
  - source: existing history event (`event_id`)
  - options:
    - `--target [jira|servicenow|generic]` (required)
    - `-o, --output PATH`
    - `--history-path PATH`
    - `--json` (JSON is default output shape)

Output contract:

- top-level: `schema_version`, `generated_at`, `source_type`, `target`, `system_name`, `risk_tier`, `summary`, `items`
- history-source extras: `event_id`, `event_type`, `descriptor_path`, `history_generated_at`
- item fields: `requirement_id`, `title`, `status`, `severity`, `article`, `gap_analysis`, `guidance`, `success_criteria`, `actionable`
- adapter payload emitted under `adapter_payload` (`generic`, `jira`, `servicenow`)

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
