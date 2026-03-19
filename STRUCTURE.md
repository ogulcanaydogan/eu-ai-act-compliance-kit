# Repository Structure

Current structure and implementation status for `eu-ai-act-compliance-kit`.

## Directory Layout

```text
eu-ai-act-compliance-kit/
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/eu_ai_act/
│   ├── __init__.py
│   ├── schema.py
│   ├── classifier.py
│   ├── checker.py
│   ├── checklist.py
│   ├── transparency.py
│   ├── gpai.py
│   ├── reporter.py
│   ├── articles.py
│   └── cli.py
├── tests/
│   ├── test_schema.py
│   ├── test_classifier.py
│   ├── test_checker.py
│   ├── test_checklist.py
│   ├── test_transparency.py
│   ├── test_gpai.py
│   ├── test_reporter.py
│   └── test_cli.py
├── examples/
│   ├── medical_diagnosis.yaml
│   ├── hiring_tool.yaml
│   ├── chatbot.yaml
│   ├── social_scoring.yaml
│   ├── spam_filter.yaml
│   ├── gpai_model.yaml
│   └── gpai_model_low_risk.yaml
├── docs/
│   ├── index.md
│   ├── installation.md
│   ├── quickstart.md
│   ├── cli-reference.md
│   ├── eu-ai-act-guide.md
│   ├── examples.md
│   ├── custom-systems.md
│   ├── api-reference.md
│   └── launch_post.md
├── mkdocs.yml
├── action.yml
├── pyproject.toml
├── README.md
├── ROADMAP.md
├── CONTRIBUTING.md
├── Dockerfile
└── LICENSE
```

## Module Responsibilities

- `schema.py`: Pydantic descriptor models and YAML loader
- `classifier.py`: risk tier classification and article applicability
- `checker.py`: requirement-level compliance findings and summary counts
- `checklist.py`: action-oriented checklist generation and JSON/MD/HTML export
- `transparency.py`: Art. 50 and disclosure-oriented findings
- `gpai.py`: GPAI assessment (`Art. 51-55`) and systemic-risk signaling
- `reporter.py`: reporter-centered JSON/MD/HTML rendering from shared payload
- `articles.py`: canonical article metadata and requirement mapping
- `cli.py`: command interface (`classify`, `check`, `checklist`, `transparency`, `gpai`, `report`, `validate`, `articles`)

## Current Product Status (March 19, 2026)

- Phase 1 complete: risk classification
- Phase 2 complete: checker, checklist, transparency, GPAI
- Phase 3 complete for JSON/Markdown/HTML/PDF reports
- Phase 4 complete: CI/CD hardening + composite action contract
- Phase 5 complete: docs site and launch material

## CI/CD and Action Contract

- Workflow: `.github/workflows/ci.yml`
  - strict: lint, type, test, build, docker, action smoke
  - advisory: docs, security
- Composite action: `action.yml`
  - outputs:
    - `risk_tier`, `compliance_percentage`, `report_path`, `articles_applicable`
    - `total_requirements`, `compliant_count`, `non_compliant_count`, `partial_count`, `not_assessed_count`
  - gate policy:
    - `unacceptable` always fails
    - `high_risk` fails if `fail_on_high_risk=true` and `non_compliant_count > 0`

## Notes

- The toolkit provides evidence-based technical compliance signals.
- It does not replace legal advice or formal conformity assessment.
