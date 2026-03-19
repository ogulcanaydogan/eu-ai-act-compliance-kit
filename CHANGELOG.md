# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Tag-driven release workflow with staged publish (`TestPyPI -> PyPI`) and GitHub Release generation.
- PDF report generation support in `ai-act report --format pdf -o <path>`.

### Changed
- Pydantic v2 schema hardening (`ConfigDict`, `min_length`, UTC-aware timestamp defaults).
- `eu_ai_act.__version__` now resolves from installed package metadata with deterministic local fallback.

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
- MkDocs documentation set and launch material.
