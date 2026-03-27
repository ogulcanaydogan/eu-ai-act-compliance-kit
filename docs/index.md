# EU AI Act Compliance Kit

Deterministic compliance toolkit for the EU AI Act (Regulation 2024/1689).
It classifies AI systems by risk tier, evaluates requirement-level compliance,
checks transparency and GPAI obligations, and renders audit-oriented reports.

## What You Can Do

- Classify AI systems into `unacceptable`, `high_risk`, `limited`, or `minimal`
- Run requirement checks for key articles (`Art. 5`, `Art. 10`, `Art. 11`, `Art. 13`, `Art. 14`, `Art. 15`, `Art. 43`, `Art. 50`)
- Generate action-focused checklists (JSON, Markdown, HTML)
- Produce compliance reports (JSON, Markdown, HTML, PDF)
- Generate payload-first external export artifacts (`generic`, `jira`, `servicenow`)
- Evaluate export operational posture with policy-based gating (`export gate`)
- Manage collaboration tasks with local-first assignment/review workflow and governance gating (`collaboration`, `collaboration gate`)
- Map compliance findings to OWASP LLM Top 10 controls (`security-map`)
- Assess transparency obligations and GPAI signals (`Art. 50`, `Art. 51-55`)
- Integrate checks into CI/CD using the repository's composite GitHub Action

## Current Delivery Status (March 24, 2026)

- Phase 1: Risk classification complete
- Phase 2: Compliance checker, checklist, transparency, GPAI complete
- Phase 3: Reporter-centered JSON/MD/HTML/PDF complete
- Phase 4: CI/CD hardening complete
- Phase 5: Documentation and launch artifacts complete
- Phase 6: PDF reporting enablement complete
- Phase 7: Pydantic v2 hardening complete
- Phase 8: Release-readiness pipeline complete
- Phase 9: Developer pre-push gate complete
- Phase 10: Audit history tracking (JSONL) complete
- Phase 11: Multi-system dashboard core (JSON + static HTML) complete
- Phase 12: Launch closure complete (RTD live, package channels live, evidence finalized)
- Phase 13: Adoption hardening complete (quickstart reliability + onboarding)
- Phase 14: External export core completed (payload-first, no live API push)
- Phase 15: CI/release runtime hardening complete (action runtime upgrades + security gate stabilization)
- Phase 16: Live export push completed (strict fail-fast, deterministic retries/backoff, optional `--push`)
- Phase 17: Export push production hardening completed (create-only idempotency ledger + duplicate-safe push)
- Phase 18: Export operator observability + upsert push completed (`export ledger list|stats` and lookup-first `--push-mode create|upsert`)
- Phase 19: Export ops hardening completed (`export batch` + `export reconcile` for multi-system operations)
- Phase 20: Quality and coverage hardening completed (example matrix + CI/test contract gates)
- Phase 21: Export V3 reliability completed (reconcile drift detection + guarded repair with explicit `--apply`)
- Phase 22: Export V4 ops completed (persistent ops log + replay/rollup operational flows)
- Phase 23: OWASP security mapping core completed (`security-map` command + `check/report` integration)
- Phase 24: Security ops integration completed (additive security snapshots in dashboard/history/export, observe-only gate policy)
- Phase 25: Enforceable security gate completed (observe-by-default + optional enforce mode in `check` and action gate surfaces)
- Phase 26: Security gate V2 completed (profile-based thresholds + tier-aware evaluation in CLI/action/CI)
- Phase 27: Export ops governance completed (`export gate`, reconcile log continuity, observe-first CI smoke)
- Phase 28: Export ops governance enforce rollout completed (shared policy file + PR observe/main-tag enforce across action and CI)
- Phase 29: Team collaboration core completed (local-first ledger + collaboration CLI + observe-only action/CI signals)
- Phase 30: Collaboration governance completed (`collaboration gate`, policy file precedence, PR-observe/main-tag enforce rollout in action/CI)
- Phase 31: Collaboration governance V2 completed (SLA/staleness-aware thresholds, additive gate metrics, PR-observe/main-tag enforce retained)

## End-to-End Flow

1. Provide a system descriptor (`*.yaml`) compliant with the schema.
2. Run `ai-act classify` to identify risk tier and applicable articles.
3. Run `ai-act check --json` for requirement findings and summary counts.
4. Generate checklist items for non-compliant/partial/not-assessed findings.
5. Generate a report via `ai-act report --format json|md|html|pdf`.
6. In CI, enforce gate policy through the composite action outputs.

For PDF generation, install reporting extras: `pip install -e ".[reporting]"`.

## Documentation Map

- [Installation](installation.md)
- [Quickstart](quickstart.md)
- [CLI Reference](cli-reference.md)
- [EU AI Act Guide](eu-ai-act-guide.md)
- [Examples](examples.md)
- [Custom System Descriptors](custom-systems.md)
- [API Reference](api-reference.md)
- [Launch Post Draft](launch_post.md)
- [Launch Evidence Pack (v0.1.0)](launch_evidence_v0_1_0.md)
- [Adoption Evidence Update Template](adoption_evidence_template.md)

## Legal Note

This toolkit provides technical, evidence-based compliance signals and does not
replace legal advice. Final regulatory interpretation and conformity decisions
should be made with qualified legal counsel.
