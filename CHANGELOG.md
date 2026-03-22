# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- No unreleased changes yet.

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
