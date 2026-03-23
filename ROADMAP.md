# ROADMAP — eu-ai-act-compliance-kit

## Vision
Automated compliance toolkit for the EU AI Act (Regulation 2024/1689). Classifies AI systems by risk tier, generates compliance checklists, and produces audit-ready reports. The first open-source tool that makes EU AI Act compliance accessible to every AI team.

## Status Snapshot (March 23, 2026)
- Phase 1 completed
- Phase 2 completed
- Phase 3 JSON/Markdown/HTML/PDF completed
- Phase 4 CI/CD hardening completed
- Phase 5 documentation and launch materials completed
- Phase 6 PDF reporting completed
- Phase 7 Pydantic v2 hardening completed
- Phase 8 release-readiness pipeline completed
- Phase 9 developer pre-push gate completed
- Phase 10 audit history tracking completed
- Phase 11 multi-system dashboard core completed
- Phase 12 launch closure completed (v0.1.0 evidence finalized)
- Phase 13 completed (post-launch adoption hardening)
- Phase 14 completed (external export core, payload-first)
- Phase 15 completed (CI/release runtime hardening and security gate stabilization)
- Phase 16 completed (live export push with strict fail-fast and retry/backoff tuning)
- Phase 17 completed (create-only export push idempotency and duplicate-safe runtime hardening)
- Phase 18 completed (export operator observability + lookup-first push upsert mode)
- Phase 19 completed (batch export orchestration + reconcile checks for live push operations)
- Phase 20 completed (quality and coverage hardening for examples, tests, and CI gates)

## Phase 1: Risk Classification Engine (Weeks 1-2) ✅ Completed

### 1.1 Project Initialization
- [ ] Set up Python project structure with pyproject.toml
  - File: `pyproject.toml`
  - Dependencies: click>=8.1.0, rich>=13.0.0, pydantic>=2.0.0, jinja2>=3.1.0, pyyaml>=6.0
  - Python 3.11+
  - Entry point: `ai-act = eu_ai_act.cli:main`
  - Acceptance Criteria:
    - `pip install -e .` completes without errors
    - `ai-act --help` displays main CLI help
    - Package discoverable as `import eu_ai_act`

### 1.2 AI System Descriptor Schema
- [ ] Implement Pydantic models for AI system description
  - File: `src/eu_ai_act/schema.py`
  - Models required:
    - `RiskTier` enum: UNACCEPTABLE, HIGH_RISK, LIMITED, MINIMAL
    - `UseCaseDomain` enum: BIOMETRIC, CRITICAL_INFRASTRUCTURE, LAW_ENFORCEMENT, EMPLOYMENT, CREDIT_SCORING, EDUCATION, GENERAL_PURPOSE, OTHER
    - `AISystemDescriptor`: top-level model with name, version, description, use_cases, data_practices, human_oversight, training_data_source
    - `UseCase`: domain, description, autonomous_decision, impacts_fundamental_rights
    - `DataPractice`: type (personal/sensitive), retention_period, sharing_third_parties, explicit_consent
    - `HumanOversight`: oversight_mechanism, fallback_procedure, review_frequency, human_authority
  - Full type hints and docstrings for all models
  - YAML schema validation
  - Acceptance Criteria:
    - Can validate valid AI system YAML files
    - Rejects invalid schemas with clear error messages
    - All Pydantic models have __doc__ strings
    - JSON schema exportable from models

### 1.3 Risk Classification Engine
- [ ] Implement RiskClassifier with decision tree logic
  - File: `src/eu_ai_act/classifier.py`
  - Class: `RiskClassifier` with method `classify(descriptor: AISystemDescriptor) -> RiskClassification`
  - `RiskClassification` dataclass containing:
    - tier: RiskTier
    - reasoning: str (explanation of classification)
    - articles_applicable: List[str]
    - confidence: float (0.0-1.0)
  - Decision tree rules:
    - **Unacceptable Risk (Art. 5)**: Social scoring, real-time biometric identification without safeguards, AI that manipulates behavior to circumvent free will
    - **High-Risk (Art. 6, Annex III)**: Biometric ID, critical infrastructure, employment/HR, education, credit/insurance, law enforcement, migration/asylum
    - **Limited Risk (Art. 50)**: Transparency obligations only (deep fakes, GPAI disclosure)
    - **Minimal Risk**: Spam filters, accessibility tools, minor chatbots
  - Acceptance Criteria:
    - Correctly classifies all 10 test scenarios (see test fixtures)
    - Provides clear reasoning for each classification
    - Generates list of applicable EU AI Act articles

### 1.4 EU AI Act Articles Database
- [ ] Build comprehensive articles reference database
  - File: `src/eu_ai_act/articles.py`
  - Data structure: `Article` class with id, title, summary, requirements by risk tier, deadline
  - Articles to include:
    - Art. 5: Prohibited practices
    - Art. 6: Definition of high-risk AI
    - Art. 10: Data governance and quality
    - Art. 11: Documentation and record-keeping
    - Art. 13: Transparency obligations
    - Art. 14: Human oversight
    - Art. 15: Accuracy, robustness, cybersecurity
    - Art. 50: Transparency for limited-risk AI
    - Art. 51-55: GPAI model obligations
    - Art. 43: Conformity assessment procedures
  - Provide `get_requirements(tier: RiskTier) -> Dict[str, List[str]]`
  - Acceptance Criteria:
    - All articles have complete, accurate summaries
    - Requirements clearly differentiate by risk tier
    - Lookup methods return correct requirements for any combination

### 1.5 Sample AI System Descriptors
- [ ] Create diverse example systems
  - File: `examples/medical_diagnosis.yaml`
    - High-risk medical imaging AI
    - Demonstrates: critical infrastructure, explainability requirements, human oversight
  - File: `examples/hiring_tool.yaml`
    - High-risk employment AI
    - Demonstrates: bias detection, data governance, documentation
  - File: `examples/chatbot.yaml`
    - Minimal-risk conversational AI
    - Demonstrates: limited transparency obligations only
  - File: `examples/social_scoring.yaml`
    - Unacceptable-risk system (social credit)
    - Demonstrates: Art. 5 prohibited practices
  - File: `examples/spam_filter.yaml`
    - Minimal-risk spam detection
    - Demonstrates: basic transparency only
  - Acceptance Criteria:
    - All examples validate against AISystemDescriptor schema
    - Each covers different risk tier
    - Each includes realistic documentation

## Phase 2: Compliance Checker Engine (Weeks 2-3) ✅ Completed

### 2.1 Compliance Checker Core
- [ ] Build compliance assessment engine
  - File: `src/eu_ai_act/checker.py`
  - Class: `ComplianceChecker` with method `check(descriptor: AISystemDescriptor) -> ComplianceReport`
  - Check all requirements applicable to risk tier
  - For each requirement, assess status:
    - COMPLIANT: Requirement fully met
    - NON_COMPLIANT: Requirement not met
    - PARTIAL: Partially implemented
    - NOT_ASSESSED: Insufficient information
  - Return `ComplianceReport` containing:
    - system_name, risk_tier
    - findings: Dict[str, ComplianceFinding]
    - summary: ComplianceSummary (total, compliant_count, non_compliant_count)
    - audit_trail: List[str] (timestamped checks)
  - Acceptance Criteria:
    - Produces correct findings for all 5 example systems
    - Findings explain specific gaps with article references
    - Report generation takes <2 seconds for typical system

### 2.2 Checklist Generator
- [ ] Create actionable compliance checklist
  - File: `src/eu_ai_act/checklist.py`
  - Class: `ChecklistGenerator` with method `generate(descriptor: AISystemDescriptor, tier: RiskTier) -> ComplianceChecklist`
  - Checklist structure:
    - For each applicable article: list of specific action items
    - Include: article reference, deadline (from EU AI Act timeline), severity (CRITICAL/HIGH/MEDIUM/LOW)
    - Suggest implementation approaches
  - Support export to: JSON, Markdown, HTML
  - Acceptance Criteria:
    - High-risk system checklist includes all mandatory requirements
    - Checklists are actionable (specific, measurable)
    - Deadlines align with EU AI Act timeline (6-24 months from implementation date)

### 2.3 Transparency Obligations Checker
- [ ] Implement Art. 50 and GPAI transparency requirements
  - File: `src/eu_ai_act/transparency.py`
  - Class: `TransparencyChecker` with methods:
    - `check_art50_disclosure(descriptor: AISystemDescriptor) -> List[TransparencyFinding]`
    - `check_gpai_obligations(descriptor: AISystemDescriptor) -> List[TransparencyFinding]`
    - `check_deepfake_detection(descriptor: AISystemDescriptor) -> TransparencyFinding`
  - Art. 50: Disclosure requirements for AI-generated content (deepfakes, synthetic media)
  - GPAI (Art. 51-55): Model cards, training data documentation, systemic risk assessment
  - Check: model documentation, training data transparency, risk classification
  - Acceptance Criteria:
    - Correctly identifies transparency gaps in examples
    - Produces specific recommendations per Article
    - Covers both Art. 50 (limited risk) and GPAI obligations

### 2.4 GPAI Model Assessment
- [ ] Build general-purpose AI model obligation checker
  - File: `src/eu_ai_act/gpai.py`
  - Class: `GPAIAssessor` with method `assess(model_info: GPAIModelInfo) -> GPAIAssessment`
  - Check requirements:
    - Training data documentation (Art. 51)
    - Model card completeness (Art. 52)
    - Systemic risk indicators (Art. 52-53)
    - Risk mitigation measures (Art. 54)
  - Identify if model triggers "systemic risk" (Art. 52): high compute, capability, market footprint
  - Return assessment with: compliance_gaps, systemic_risk_flag, recommendations
  - Acceptance Criteria:
    - Correctly flags large models as systemic risk
    - Identifies documentation gaps
    - Provides remediation steps for each gap

## Phase 3: Reporting & CLI Interface (Weeks 3-4) ✅ Completed

### 3.1 Report Generator
- [ ] Build multi-format report generation
  - File: `src/eu_ai_act/reporter.py`
  - Class: `ReportGenerator` supporting formats:
    - **JSON**: Machine-readable, includes all findings with metadata
    - **HTML**: Executive summary with traffic light indicators (red/yellow/green for compliance status)
    - **Markdown**: GitHub-friendly summary with checklist
    - **PDF**: Audit-ready binary report
  - Report contents:
    - Executive summary (risk tier, compliance %age)
    - Classification reasoning
    - Detailed findings per article
    - Recommended actions with priorities
    - Audit trail (checks performed, timestamp)
  - Acceptance Criteria:
    - Current release formats valid (JSON parseable, HTML displays correctly, Markdown readable, PDF readable)
    - Reports contain all required elements
    - Generated reports include timestamp, system info, article references

### 3.2 Command-Line Interface
- [ ] Build comprehensive CLI using Click
  - File: `src/eu_ai_act/cli.py`
  - Commands:
    - `ai-act classify <system.yaml>`: Show risk classification
    - `ai-act check <system.yaml>`: Full compliance check
    - `ai-act checklist <system.yaml>`: Generate actionable checklist
    - `ai-act report <system.yaml> --format {html,json,md} --output <path>`: Generate report
    - `ai-act transparency <system.yaml> [--json]`: Evaluate Art. 50 and related disclosure signals
    - `ai-act gpai <model.yaml> [--json]`: Evaluate GPAI model obligations
    - `ai-act validate <system.yaml>`: Validate system descriptor schema
    - `ai-act articles [--tier {minimal,limited,high_risk,unacceptable}]`: List applicable articles
  - Command options: `--json`, `--format`, and `--output` where applicable
  - All commands return appropriate exit codes
  - Acceptance Criteria:
    - All commands execute end-to-end without errors
    - Help text clear and informative
    - Examples in help text
    - JSON output for programmatic use

### 3.3 Test Suite
- [ ] Comprehensive test coverage
  - File: `tests/test_schema.py` — Schema validation tests
  - File: `tests/test_classifier.py` — Risk classification tests
  - File: `tests/test_checker.py` — Compliance checking tests
  - File: `tests/test_reporter.py` — Report generation tests
  - File: `tests/test_cli.py` — CLI integration tests
  - Test fixtures in `tests/fixtures/`:
    - `valid_systems.yaml`: All 5 example systems for positive tests
    - `invalid_systems.yaml`: Malformed systems for negative tests
    - `test_scenarios.json`: 10 specific test cases with expected results
  - Acceptance Criteria:
    - >80% code coverage
    - All tests pass on Python 3.11+
    - Tests run in <30 seconds
    - Fixtures cover edge cases (missing fields, invalid values)

## Phase 4: CI/CD Integration (Week 4) ✅ Completed

### 4.1 GitHub Action
- [ ] Create reusable GitHub Action for CI/CD
  - File: `action.yml`
  - Inputs: system_yaml, fail_on_high_risk (boolean), report_format, report_path
  - Runs compliance check in pipeline
  - Outputs:
    - risk_tier, compliance_percentage, report_path, articles_applicable
    - total_requirements, compliant_count, non_compliant_count, partial_count, not_assessed_count
  - Posts PR comment with compliance summary and traffic light indicator
  - Fails build deterministically:
    - `unacceptable` always fails
    - `high_risk` fails when `fail_on_high_risk=true` and `non_compliant_count > 0`
  - Acceptance Criteria:
    - Works in test workflow without errors
    - PR comment formatting is clear
    - Correctly fails builds on high-risk non-compliance

### 4.2 Docker Image
- [ ] Build containerized tool
  - File: `Dockerfile`
  - Base: python:3.11-slim
  - Entry point: ai-act CLI
  - Acceptance Criteria:
    - `docker run eu-ai-act-compliance-kit check system.yaml` executes successfully
    - Image size <500MB
    - Includes all dependencies

### 4.3 GitHub Actions CI Pipeline
- [ ] Set up automated testing and building
  - File: `.github/workflows/ci.yml`
  - Triggers: push, pull_request
  - Jobs:
    - Lint (ruff, black)
    - Test (pytest with coverage)
    - Build Docker image
    - Type check (mypy)
  - Publishes coverage to Codecov
  - Acceptance Criteria:
    - All jobs pass on main branch
    - Coverage report generated and posted
    - Docker image published to registry

## Phase 5: Documentation & Launch (Week 4-5) ✅ Completed

### 5.1 README.md
- [x] Professional README with quickstart
  - File: `README.md`
  - Includes:
    - EU AI Act context and compliance requirement
    - Feature list (classification, checking, reporting, CI/CD)
    - Quick start with code examples
    - Installation instructions
    - CLI usage examples
    - Architecture diagram (text-based)
    - Contributing guidelines
    - License notice
  - Badges: build status, coverage, license, Python version
  - Acceptance Criteria:
    - Users can clone and run within 5 minutes
    - All CLI commands documented with examples

### 5.2 Documentation Site
- [x] Create mkdocs documentation
  - File: `docs/index.md` — Overview and architecture
  - File: `docs/installation.md` — Installation and setup
  - File: `docs/quickstart.md` — Step-by-step tutorial
  - File: `docs/cli-reference.md` — Complete CLI command reference
  - File: `docs/eu-ai-act-guide.md` — EU AI Act articles explained
  - File: `docs/examples.md` — Detailed walkthroughs of example systems
  - File: `docs/custom-systems.md` — How to write custom system descriptors
  - File: `docs/api-reference.md` — Python library API documentation
  - mkdocs.yml configuration
  - Acceptance Criteria:
    - Site builds without errors
    - All major features documented
    - Examples are runnable/testable

### 5.3 Contributing Guide
- [x] Establish contribution framework
  - File: `CONTRIBUTING.md`
  - Covers: development setup, testing, PR requirements, code style, commit conventions
  - Development instructions (running tests locally, building docs)
  - Acceptance Criteria:
    - New contributors can follow guide to set up dev environment

### 5.4 Launch Materials
- [x] Create launch content
  - File: `docs/launch_post.md` — Medium/blog article draft
  - Content: Why EU AI Act compliance matters, how toolkit helps, feature overview, getting started
  - Acceptance Criteria:
    - ~1500 words, ready for publication
    - Includes code examples from repo

## Phase 6-12: Post-Launch Delivery Stream ✅ Completed

- Phase 6: Reporter PDF engine and CLI `report --format pdf` support enabled
- Phase 7: Pydantic v2 hardening and timezone-aware defaults delivered
- Phase 8: Tag-driven release readiness with package metadata alignment delivered
- Phase 9: Developer workflow gate (`pre-commit` pre-push targeted checks) delivered
- Phase 10: Audit history tracking core (`.eu_ai_act/history.jsonl`) delivered
- Phase 11: Multi-system dashboard build (JSON + static HTML) delivered
- Phase 12: Public launch closure delivered (RTD live, package channels live, release evidence)

## Phase 13: Adoption Hardening ✅ Completed

- One-command quickstart smoke script added for repeatable local validation.
- CI includes a required quickstart smoke gate to protect contributor baseline flow.
- Onboarding docs include a first-contribution path and repeatable evidence update template.

## Phase 14: External Export Core ✅ Completed

- Payload-first external export engine delivered (no live network push).
- Export sources delivered: check result and history event.
- Target adapters delivered: generic, Jira payload, ServiceNow payload.
- CLI surface delivered: `ai-act export check` and `ai-act export history`.
- Existing CLI/Python API contracts preserved.

## Phase 15: CI/Release Runtime Hardening ✅ Completed

- GitHub Actions runtime upgrades completed for CI and release workflows.
- Security gate stabilized by removing assert-based control flow in CLI PDF output handling.
- Required checks preserved with deterministic pass/fail behavior.

## Phase 16: Live Export Push ✅ Completed

- Live push path completed for `ai-act export` with payload-only default behavior preserved.
- Targets enabled for push: Jira and ServiceNow (`generic` remains payload-only).
- Strict fail-fast behavior finalized: abort on first actionable item that fails after retries.
- Deterministic retry policy delivered:
  - defaults: `max_retries=3`, `retry_backoff_seconds=1.0`, `timeout_seconds=30.0`
  - retry only for transport errors and HTTP `429`/`5xx`
  - non-retryable `4xx` fails immediately
- CLI tuning options delivered on both `export check` and `export history`:
  - `--max-retries`
  - `--retry-backoff-seconds`
  - `--timeout-seconds`
- `--dry-run` contract kept deterministic with no network calls and explicit `push_result` diagnostics.

## Phase 17: Export Push Production Hardening ✅ Completed

- Added project-local append-only idempotency ledger: `.eu_ai_act/export_push_ledger.jsonl`.
- Duplicate actionable items are skipped before remote call when idempotency key already exists.
- Strict fail-fast behavior and existing retry policy preserved (`429`/`5xx`/transport only).
- Export CLI extended with idempotency controls:
  - `--idempotency-path`
  - `--disable-idempotency`
- Check-source payloads now include `descriptor_path` so idempotency keys remain stable and source-specific.
- Ledger write failures after successful remote create now surface diagnostics (`ledger_recorded`, `ledger_error`) without turning the command into a false negative.
- Create-only push scope preserved (no update/upsert in this phase).

## Phase 18: Export Operator Observability + Upsert Push ✅ Completed

- Added CLI operator commands for idempotency ledger introspection:
  - `ai-act export ledger list`
  - `ai-act export ledger stats`
- Added deterministic filter contract for ledger listing:
  - target/system/requirement filters
  - stable `limit` behavior and JSON output
- Added aggregate ledger analytics contract:
  - total records
  - target/status/system/requirement distributions
  - first/last push timestamps
- Added controlled upsert push behavior behind optional mode flag:
  - `--push-mode create|upsert` (default `create`)
  - `create` keeps duplicate-skip create-only behavior
  - `upsert` performs lookup-first create/update for Jira and ServiceNow (no ledger-first skip)
- Preserved non-breaking behavior for existing `export check|history` commands.
- Strengthened test coverage for upsert retry and fail-fast behavior in lookup/create/update paths.

## Phase 19: Export Ops Hardening ✅ Completed

- Delivered directory-driven batch export orchestration:
  - `ai-act export batch <descriptor_dir>`
  - deterministic descriptor scan with continue-on-error aggregation
  - optional push path (`--push`, `--push-mode create|upsert`, retry tuning, idempotency controls)
- Delivered ledger-to-remote reconcile checks:
  - `ai-act export reconcile --target jira|servicenow`
  - existence/status verification for ledger `remote_ref` values
  - classify outcomes as `exists`, `missing`, `check_error`
- Preserved strict operational contracts:
  - batch continues across systems and returns non-zero when any invalid/push failure exists
  - reconcile remains read-only and returns non-zero when `missing_count` or `error_count` is non-zero

## Phase 20: Quality & Coverage Hardening ✅ Completed

- Expanded example matrix with additional high-risk, transparency-heavy, and GPAI-uncertain scenarios.
- Added example contract tests for schema + classify/check (`system` examples) and GPAI assessment (`gpai_model*` examples).
- Strengthened quickstart reliability checks by running smoke coverage across more than one descriptor profile.
- Added CI `examples-smoke` required job and enforced coverage floor (`--cov-fail-under=80`).

## Timeline Summary (Historical Plan)
- **Week 1-2**: Risk Classification Engine (Phases 1.1-1.5)
- **Week 2-3**: Compliance Checker Engine (Phase 2)
- **Week 3-4**: Reporting & CLI (Phase 3)
- **Week 4**: CI/CD Integration (Phase 4)
- **Week 4-5**: Documentation & Launch (Phase 5)

## Success Metrics
- [ ] All phases 1-3 complete with >80% test coverage
- [ ] All 5 example systems correctly classified and assessed
- [ ] CLI executes all commands without errors
- [ ] Generated reports are audit-ready and legally compliant
- [ ] Documentation enables new developers to contribute
- [ ] GitHub Action successfully integrates into CI/CD pipelines
- [ ] Tool becomes usable by non-technical compliance teams

## Known Constraints & Limitations
- Initial version covers EU AI Act (2024/1689) only — future versions may support other frameworks
- Risk classification based on rule-based system (not ML-based) for interpretability
- Human oversight assessment relies on provided documentation (cannot verify actual practices)
- Reports serve as guidance only — professional legal review still required for official compliance

## Future Enhancements (Post-Launch)
- Integration with Git hooks for continuous compliance
- Dashboard for managing multiple systems
- AI-powered documentation generation
- Integration with OWASP frameworks for security assessment
- Audit trail and change history tracking
- Team collaboration features
- Export to external compliance tools (ServiceNow, Jira, etc.)
