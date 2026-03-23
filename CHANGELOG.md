# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- No changes yet.

## [0.1.17] - 2026-03-23

### Added
- Security Gate V2 profile support in evaluator and CLI/action contracts:
  - profiles: `strict`, `balanced`, `lenient`
  - new CLI flag: `--security-gate-profile`
  - additive `security_gate` payload fields: `profile`, `effective_profile`, `partial_count`, `not_assessed_count`
- Composite action additive input:
  - `security_gate_profile` (default: `balanced`)
- Composite action additive outputs:
  - `security_partial_count`
  - `security_not_assessed_count`

### Changed
- Security gate policy is now tier-aware:
  - `lenient` profile is treated as `balanced` for `high_risk` and `unacceptable` systems.
- Composite action gate decision now reuses evaluator output instead of duplicating threshold logic.
- CI action-smoke now exercises explicit profile-aware security gate settings.
- Phase 26 status synchronized as completed across README, docs index, and roadmap snapshot.

### Tests
- Extended `tests/test_security_gate.py` for strict/balanced/lenient thresholds and tier-aware override behavior.
- Extended `tests/test_cli.py` for profile-aware CLI contract and tier-aware enforce behavior.
- Extended `tests/test_ci_contract.py` for action profile input/additive output and CI action-smoke profile usage.

## [0.1.16] - 2026-03-23

### Added
- New deterministic security gate evaluator (`security_gate.py`) with:
  - `observe` mode (default, no blocking)
  - `enforce` mode (fails when `security_summary.non_compliant_count > 0`)
- `ai-act check` now supports `--security-gate observe|enforce`.
- `ai-act check --json` now includes additive `security_gate` payload (`mode`, `failed`, `reason`, `non_compliant_count`).
- Composite GitHub Action now supports `security_gate_mode` input (`observe|enforce`).
- Composite action additive outputs:
  - `security_non_compliant_count`
  - `security_gate_failed`

### Changed
- Action gate policy now optionally enforces security controls when `security_gate_mode=enforce`.
- CI action-smoke now validates explicit security-gate enforcement behavior.
- Phase 25 status synchronized as completed across README, docs index, and roadmap snapshot.

### Tests
- Added `tests/test_security_gate.py` for evaluator mode/threshold/validation behavior.
- Extended `tests/test_cli.py` for `--security-gate` contract and non-zero enforce behavior.
- Extended `tests/test_ci_contract.py` for action input/output and action-smoke security-gate assertions.

## [0.1.15] - 2026-03-23

### Added
- Dashboard security ops visibility:
  - system-level `security_summary`
  - top-level `average_security_coverage_percentage`
  - top-level `security_control_status_distribution`
- History event payload now supports additive `security_summary` snapshots.
- Export payloads now include additive top-level `security_mapping` in:
  - `export check`
  - `export history`
  - `export batch` result entries

### Changed
- `history diff` now includes additive `security_summary_change` deltas (`coverage_percentage`, `non_compliant_count`, `partial_count`, `not_assessed_count`).
- Dashboard HTML now includes a new `Security Mapping Overview` section.
- Phase 24 status synchronized as completed across README, docs index, and roadmap snapshot.
- Security mapping remains observe-only for CI gate policy in this phase.

### Tests
- Added/extended history, dashboard, exporter, and CLI contract coverage for new security ops payload fields.

## [0.1.14] - 2026-03-23

### Added
- New OWASP LLM Top 10 mapping runtime (`security_mapping.py`) with deterministic control-level status derivation and summary metrics.
- New CLI command: `ai-act security-map <system.yaml> [--json] [--output PATH]`.

### Changed
- `ai-act check --json` now includes non-breaking `security_summary`.
- Report payload/renderers now include non-breaking `security_mapping` in JSON and a new `Security Mapping (OWASP LLM Top 10)` section in Markdown/HTML.
- Phase 23 status synchronized as completed across README, docs index, and roadmap snapshot.

### Tests
- Added `tests/test_security_mapping.py` coverage for deterministic status derivation and summary counts.
- Extended CLI/reporter contract tests for `security-map`, `check --json security_summary`, and report security mapping sections.

## [0.1.13] - 2026-03-23

### Added
- Persistent export operations log (`.eu_ai_act/export_ops_log.jsonl`) for per-item push attempt tracking in `export check|history|batch --push` flows.
- New CLI command: `ai-act export replay` for deterministic replay of failed push operations from ops log.
- New CLI command: `ai-act export rollup` for read-only operational metrics/distributions from ops log + push ledger.

### Changed
- Export push flows now surface best-effort ops-log write warnings without changing command success/failure behavior.
- Phase 22 status synchronized as completed across README, docs index, and roadmap snapshot.

### Tests
- Added exporter coverage for ops log parse errors, replay dedupe/unreplayable paths, rollup aggregation, and best-effort ops-log warning behavior.
- Added CLI coverage for replay/rollup contracts, output mode, dry-run forwarding, and flag validation paths.

## [0.1.12] - 2026-03-23

### Added
- Reconcile drift detection contract for export ledger checks:
  - result-level `expected_status`, `remote_status`, `drift_status`
  - top-level `in_sync_count`, `drift_count`
- Guarded reconcile repair controls:
  - `ai-act export reconcile --repair`
  - `ai-act export reconcile --repair --apply`

### Changed
- Reconcile exit policy hardened to fail when drift or repair failures exist.
- Phase 21 status synchronized as completed across README, docs index, and roadmap snapshot.

### Tests
- Added exporter coverage for drift parity, repair planning, apply retries, and partial repair failures.
- Added CLI coverage for `--repair/--apply` flag contract and non-zero drift behavior.

## [0.1.11] - 2026-03-23

### Added
- New example descriptors:
  - `examples/public_benefits_triage.yaml`
  - `examples/synthetic_media_campaign_assistant.yaml`
  - `examples/gpai_model_unknown_thresholds.yaml`
- New example contract test suite for system and GPAI example matrices.
- New required CI `examples-smoke` job for deterministic example validation/classify/check coverage.

### Changed
- Coverage gate hardened to enforce a minimum threshold of `80%` in CI.
- Quickstart smoke tests now cover multiple descriptor profiles.
- Phase 20 status synchronized as completed across README, docs index, and roadmap snapshot.

### Tests
- Added contracts for:
  - all system example descriptor validate/classify/check JSON shapes
  - explicit expectations for new high-risk and transparency-heavy examples
  - GPAI unknown-threshold `Art. 53 = not_assessed` behavior

## [0.1.10] - 2026-03-23

### Changed
- Phase 19 status synchronized as completed across README, docs index, and roadmap snapshot.
- Phase 19 roadmap section finalized as completed with delivery-oriented wording.

## [0.1.9] - 2026-03-22

### Added
- New export operations CLI commands:
  - `ai-act export batch`
  - `ai-act export reconcile`

### Changed
- Phase 19 status synchronized as in progress across README, docs index, and roadmap snapshot.
- Export docs expanded with batch/reconcile contracts and non-zero exit behavior.

### Tests
- Added exporter runtime coverage for:
  - mixed valid/invalid batch processing with continue policy
  - batch push continue-on-failure aggregation
  - reconcile classification (`exists`, `missing`, `check_error`)
  - reconcile retry (`5xx`) and non-retryable (`4xx`) behavior
- Added CLI coverage for:
  - `export batch` contract, generic push rejection, and non-zero aggregate behavior
  - `export reconcile` contract, output file mode, and limit validation

## [0.1.8] - 2026-03-22

### Changed
- Phase 18 status synchronized as completed across README, docs index, and roadmap snapshot.
- Export push policy docs clarified:
  - duplicate-skip applies to `create` mode with idempotency enabled
  - `upsert` mode is always lookup-first create/update for Jira and ServiceNow

### Tests
- Added Jira upsert runtime coverage for:
  - retryable lookup failure recovery (`5xx` -> success update)
  - create-path retry exhaustion fail-fast
  - update-path non-retryable `4xx` immediate fail
- Added ServiceNow upsert runtime coverage for:
  - retryable lookup failure recovery (`5xx` -> success update)
  - create-path retry exhaustion fail-fast
  - update-path non-retryable `4xx` immediate fail
- Added CLI contract coverage for explicit `--push-mode create` forwarding and `--push --dry-run --push-mode upsert`.

## [0.1.7] - 2026-03-22

### Added
- New export ledger CLI surface:
  - `ai-act export ledger list`
  - `ai-act export ledger stats`
- Exporter-side ledger query helpers for deterministic list filtering and aggregate summaries.
- Export push mode selection for live targets:
  - `--push-mode create|upsert` on `export check` and `export history`
- Jira and ServiceNow lookup-first upsert runtime for `--push-mode upsert` (create-only default preserved).

### Changed
- Roadmap/docs/readme status synchronized to mark Phase 17 as completed after `v0.1.6`.
- Roadmap/docs/readme status synchronized to keep Phase 18 in progress with upsert kickoff scope.
- `push_result` contract extended with `push_mode`, `created_count`, and `updated_count`.
- ServiceNow upsert lookup field is now configurable via `EU_AI_ACT_SERVICENOW_IDEMPOTENCY_FIELD` (default: `u_idempotency_key`).

### Tests
- Added unit coverage for ledger list/summary helpers, including invalid JSON error handling.
- Added CLI coverage for `export ledger list|stats` JSON contracts and invalid `--limit` handling.
- Added exporter coverage for Jira/ServiceNow upsert create and update paths, including lookup failure handling.
- Added CLI coverage for `--push-mode` validation and forwarding behavior.

## [0.1.6] - 2026-03-22

### Added
- Export push idempotency controls:
  - `--idempotency-path`
  - `--disable-idempotency`

### Changed
- Export live push now supports deterministic duplicate-skip via project-local idempotency ledger (`.eu_ai_act/export_push_ledger.jsonl`).
- `push_result` contract extended with `skipped_duplicate_count`, `idempotency_enabled`, and `idempotency_path`.
- Check-source export payloads now preserve `descriptor_path`, so idempotency keys stay unique across different descriptor files.
- Roadmap/docs status synchronized to start Phase 17 as in progress.

### Fixed
- Live push no longer fails after a successful remote create when local idempotency ledger append fails; result entries now return `ledger_recorded`/`ledger_error` diagnostics.

### Tests
- Added exporter unit coverage for duplicate skip, idempotency disable path, and dry-run no-ledger-write behavior.
- Added exporter unit coverage for descriptor-identity idempotency and post-success ledger-write failure handling.
- Added CLI contract coverage for idempotency flags and extended `push_result` assertions.

## [0.1.5] - 2026-03-21

### Added
- Export push reliability tuning flags for both export commands:
  - `--max-retries`
  - `--retry-backoff-seconds`
  - `--timeout-seconds`

### Changed
- Phase 16 status synchronized to completed across roadmap/readme/docs status surfaces.
- Live export push hardening finalized with strict fail-fast plus deterministic retry/backoff policy for transport errors and HTTP `429`/`5xx`.

### Tests
- Added retry contract coverage for export push (`429`, `5xx`, transport error, retry exhaustion, and non-retryable `4xx`).
- Added CLI contract tests for export push tuning flags and fail-fast error reporting paths.

## [0.1.4] - 2026-03-21

### Added
- Optional live push path for `ai-act export check` and `ai-act export history` via `--push` (targets: Jira, ServiceNow).
- Safe `--dry-run` mode for export commands to emit deterministic simulated push summaries without network calls.

### Changed
- Roadmap/docs status synchronized to keep Phase 16 kickoff as in progress.

## [0.1.3] - 2026-03-21

### Fixed
- CI security gate no longer flags `assert` usage in CLI PDF output handling (Bandit-safe runtime guard).

### Changed
- GitHub workflow runtime hardening completed:
  - `actions/checkout` upgraded to `v6`
  - `actions/setup-python` upgraded to `v6`
  - `actions/upload-artifact` upgraded to `v7`
  - `actions/download-artifact` upgraded to `v8`
- Release workflow now creates/updates GitHub releases through `gh` CLI flow instead of Node action dependency.
- Phase 15 status synchronized as completed across README, docs index, and roadmap snapshot.

## [0.1.2] - 2026-03-21

### Fixed
- CLI `--version` now uses deterministic package metadata lookup and no longer fails in editable/local environments.

### Changed
- Phase 14 status finalized to completed across README, docs index, and roadmap snapshot.

## [0.1.1] - 2026-03-21

### Added
- External export core module for payload-first integrations (`generic`, `jira`, `servicenow`).
- New CLI commands:
  - `ai-act export check <system.yaml> --target ...`
  - `ai-act export history <event_id> --target ...`
- Export contract tests and CLI smoke tests for export flows.

### Changed
- README, docs CLI reference, docs index, and roadmap synchronized for Phase 14 export scope.

## [0.1.0] - 2026-03-19

### Added
- Initial public release of EU AI Act Compliance Kit.
- Risk classification engine (`unacceptable`, `high_risk`, `limited`, `minimal`).
- Compliance checker with requirement findings, summary counts, and audit trail.
- Action-oriented checklist generation with JSON/Markdown/HTML export.
- Reporter-centered report generation (JSON/Markdown/HTML/PDF).
- Transparency and GPAI assessment modules.
- CLI commands: `classify`, `check`, `checklist`, `report`, `transparency`, `gpai`, `validate`, `articles`.
- Composite GitHub Action for CI gating.
- Tag-driven release workflow with staged publish (`TestPyPI -> PyPI`) and GitHub Release generation.
- MkDocs documentation set and launch material.

### Changed
- Pydantic v2 schema hardening (`ConfigDict`, `min_length`, UTC-aware timestamp defaults).
- `eu_ai_act.__version__` now resolves from installed package metadata with deterministic local fallback.
