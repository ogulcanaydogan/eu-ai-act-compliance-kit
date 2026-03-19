[![CI](https://img.shields.io/github/actions/workflow/status/ogulcanaydogan/eu-ai-act-compliance-kit/ci.yml?branch=main&label=tests)](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions)
[![Coverage](https://img.shields.io/codecov/c/github/ogulcanaydogan/eu-ai-act-compliance-kit)](https://codecov.io/gh/ogulcanaydogan/eu-ai-act-compliance-kit)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# EU AI Act Compliance Kit

Automated compliance assessment tool for the **EU AI Act** (Regulation 2024/1689). Classifies AI systems by risk tier, generates compliance checklists, and produces audit-ready reports. The first open-source toolkit that makes EU AI Act compliance accessible to every AI team.

## What It Does

The EU AI Act imposes comprehensive compliance obligations on AI systems, with requirements varying by risk classification. This toolkit automates the first critical step: **classifying your AI system into the correct risk tier**, then guiding you through the specific requirements.

- **Risk Classification**: Automatically categorizes AI systems as UNACCEPTABLE, HIGH-RISK, LIMITED, or MINIMAL
- **Compliance Checking**: Analyzes your system against applicable EU AI Act articles
- **Checklist Generation**: Creates actionable compliance checklists with article references and deadlines
- **Report Generation**: Produces audit-ready reports in JSON, HTML, or Markdown
- **CI/CD Integration**: GitHub Action for automatic compliance checks in your pipeline

## Why This Matters

The EU AI Act is now enforceable. Organizations deploying AI systems in the EU must:
- Classify systems by risk tier within defined timelines
- Implement tier-specific safeguards (data governance, documentation, transparency, human oversight)
- Maintain audit trails and comply with conformity assessment procedures
- Face fines up to €30M or 6% of global annual revenue for violations

This toolkit helps you **get compliant efficiently** without requiring external consultants for initial assessment.

## Quick Start

### Installation

```bash
# Install from PyPI
pip install eu-ai-act-compliance-kit

# Or install from source
git clone https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit.git
cd eu-ai-act-compliance-kit
pip install -e .
```

Release workflow:
- Tag format: `vX.Y.Z` (example: `v0.1.1`)
- Pipeline: QA/build -> TestPyPI publish -> TestPyPI smoke -> gated PyPI publish -> GitHub Release

### Basic Usage

Describe your AI system in YAML:

```yaml
# my_system.yaml
name: "Medical Diagnosis AI"
version: "1.0.0"
description: "AI system that analyzes medical images to detect abnormalities..."

use_cases:
  - domain: healthcare
    description: "Analyzes CT/MRI scans for tumor detection"
    autonomous_decision: false
    impacts_fundamental_rights: true

data_practices:
  - type: "sensitive_health"
    retention_period: 2555
    sharing_third_parties: false
    explicit_consent: true

human_oversight:
  oversight_mechanism: "approval_required"
  fallback_procedure: "Senior radiologist manual review"
  review_frequency: "per_decision"
  human_authority: true

training_data_source: "500,000+ de-identified medical images from hospital network"
documentation: true
performance_monitoring: true
```

Then classify and check compliance:

```bash
# Classify your system
ai-act classify my_system.yaml

# Output:
# Risk Tier: HIGH_RISK (confidence: 90%)
# Reasoning: System is classified as high-risk because it processes sensitive health data,
# makes decisions affecting fundamental rights, and operates in healthcare domain...
# Applicable EU AI Act Articles:
#   • Art. 6 (Definition of high-risk AI)
#   • Art. 10 (Data governance)
#   • Art. 11 (Documentation and record-keeping)
#   • Art. 13 (Transparency and information to users)
#   • Art. 14 (Human oversight)
#   • Art. 15 (Accuracy, robustness, cybersecurity)

# Run full compliance check
ai-act check my_system.yaml

# Generate HTML compliance report
ai-act report my_system.yaml --format html -o compliance_report.html

# Create markdown checklist
ai-act checklist my_system.yaml --format md -o checklist.md
```

## CLI Commands

### `ai-act classify <system.yaml>`
Classifies an AI system into a risk tier.
```bash
ai-act classify examples/medical_diagnosis.yaml
ai-act classify my_system.yaml --json  # Machine-readable output
```

### `ai-act check <system.yaml>`
Performs full compliance assessment against applicable requirements.
```bash
ai-act check examples/hiring_tool.yaml
ai-act check my_system.yaml --json
```

### `ai-act checklist <system.yaml>`
Generates actionable compliance checklist based on risk tier.
```bash
ai-act checklist examples/medical_diagnosis.yaml --format md -o checklist.md
ai-act checklist my_system.yaml --format html -o checklist.html
```

### `ai-act report <system.yaml>`
Creates a comprehensive compliance report with compliance findings, transparency findings, GPAI assessment, recommended actions, and audit trail.
Supported formats are `json`, `md`, `html`, and `pdf`.
```bash
ai-act report examples/hiring_tool.yaml --format html -o report.html
ai-act report my_system.yaml --format json
ai-act report my_system.yaml --format md -o report.md
ai-act report my_system.yaml --format pdf -o report.pdf
```
For PDF generation, install reporting extras:
```bash
pip install -e ".[reporting]"
```

### `ai-act dashboard build <descriptor_dir>`
Builds a multi-system dashboard from a descriptor directory and writes static artifacts.
```bash
ai-act dashboard build examples --output-dir dashboard_artifacts
ai-act dashboard build examples --recursive --include-history
```
Default artifacts:
- `<output-dir>/dashboard.json`
- `<output-dir>/dashboard.html`

Behavior:
- Invalid descriptors are skipped and captured in the `errors` section.
- Build succeeds when at least one valid system is processed.
- Build fails (`exit 1`) when no valid system is found.

### `ai-act history {list|show|diff}`
Inspects persisted audit history for `check` and `report` runs.
```bash
ai-act history list --json
ai-act history show <event_id> --json
ai-act history diff <older_event_id> <newer_event_id> --json
```
Default history path is project-local `.eu_ai_act/history.jsonl` (resolved from nearest `pyproject.toml`).
If history write fails during `check` or `report`, the command continues and emits a warning.

### `ai-act transparency <system.yaml>`
Evaluates Art. 50 transparency obligations and disclosure signals.
```bash
ai-act transparency examples/chatbot.yaml
ai-act transparency my_system.yaml --json
```

### `ai-act gpai <model.yaml>`
Evaluates GPAI obligations for model descriptors (Art. 51-55).
```bash
ai-act gpai examples/gpai_model.yaml
ai-act gpai examples/gpai_model_low_risk.yaml --json
```

### `ai-act validate <system.yaml>`
Validates system descriptor against schema.
```bash
ai-act validate my_system.yaml
```

### `ai-act articles [--tier {minimal,limited,high_risk,unacceptable}]`
Lists applicable EU AI Act articles.
```bash
ai-act articles  # Show all articles
ai-act articles --tier high_risk  # Show high-risk requirements only
```

## Example Systems

The repository includes complete example systems demonstrating different risk tiers:

- **`examples/medical_diagnosis.yaml`** — HIGH-RISK: Medical imaging AI
- **`examples/hiring_tool.yaml`** — HIGH-RISK: Resume screening system
- **`examples/chatbot.yaml`** — MINIMAL: Customer support chatbot
- **`examples/social_scoring.yaml`** — UNACCEPTABLE: Social credit system (prohibited)
- **`examples/spam_filter.yaml`** — MINIMAL: Email spam detection

Try them:
```bash
ai-act classify examples/medical_diagnosis.yaml
ai-act check examples/hiring_tool.yaml
ai-act report examples/chatbot.yaml --format html
```

## Architecture

```
eu-ai-act-compliance-kit/
├── src/eu_ai_act/
│   ├── schema.py           # Pydantic models for AI system descriptor
│   ├── classifier.py       # Risk tier classification engine
│   ├── checker.py          # Compliance requirement checking
│   ├── checklist.py        # Checklist generation
│   ├── articles.py         # Article mappings and requirements database
│   ├── transparency.py     # Art. 50 transparency finding engine
│   ├── gpai.py             # GPAI obligation assessment
│   ├── dashboard.py        # Multi-system dashboard payload + static HTML renderer
│   ├── history.py          # Persistent audit history storage and diffs
│   ├── reporter.py         # Central report renderer (JSON, Markdown, HTML)
│   └── cli.py              # Click CLI interface
├── tests/                  # Test suite with >80% coverage
├── examples/               # Sample AI system descriptors
├── docs/                   # Documentation and guides
├── .github/workflows/      # CI/CD workflows
└── ROADMAP.md              # Detailed development roadmap
```

## Development Setup

### Install dev dependencies
```bash
pip install -e ".[dev]"
```

### Run tests
```bash
pytest tests/ -v --cov
```

### Format code
```bash
black src/
ruff check src/ --fix
```

### Type check
```bash
mypy src/eu_ai_act/
```

### Build documentation
```bash
pip install -e ".[docs]"
mkdocs build --strict
mkdocs serve
```

## EU AI Act Compliance Framework

This toolkit maps to key articles from Regulation 2024/1689:

### Risk Tiers

| Tier | Definition | Key Articles | Examples |
|------|-----------|-------------|----------|
| **UNACCEPTABLE** | Prohibited practices posing unacceptable risk | Art. 5 | Social credit systems, biometric identification surveillance |
| **HIGH-RISK** | Significant impact on fundamental rights | Art. 6, 10-15, 43 | Medical diagnosis, hiring, credit scoring, law enforcement |
| **LIMITED** | Transparency obligations only | Art. 50 | AI-generated content disclosure, deepfake detection |
| **MINIMAL** | General compliance framework | Art. 69 | Spam filters, basic chatbots, accessibility tools |

### Key Requirements by Tier

**HIGH-RISK** systems must comply with:
- **Data Governance** (Art. 10): Quality data collection, processing standards, bias mitigation
- **Documentation** (Art. 11): Technical documentation, training records, decision logs
- **Transparency** (Art. 13): Users informed they're interacting with AI, decision explanations
- **Human Oversight** (Art. 14): Meaningful human review, override capability, monitoring
- **Accuracy & Security** (Art. 15): Performance monitoring, cybersecurity, robustness testing
- **Conformity Assessment** (Art. 43): Third-party review, certification procedures
- **Incident Reporting** (Art. 62): Serious incident notification to authorities

## Python Library Usage

Use the toolkit programmatically in your Python projects:

```python
from eu_ai_act.schema import load_system_descriptor_from_file
from eu_ai_act.classifier import RiskClassifier

# Load system descriptor
descriptor = load_system_descriptor_from_file("my_system.yaml")

# Classify
classifier = RiskClassifier()
classification = classifier.classify(descriptor)

print(f"Risk Tier: {classification.tier.value}")
print(f"Confidence: {classification.confidence:.0%}")
print(f"Applicable Articles: {', '.join(classification.articles_applicable)}")

# Check which articles apply
articles = classifier.get_applicable_articles(classification.tier)
for article in articles:
    print(f"  • {article}")
```

## GitHub Actions Integration

Use the compliance kit in your CI/CD pipeline:

```yaml
# .github/workflows/ai-compliance.yml
name: AI Compliance Check

on: [push, pull_request]

jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check AI System Compliance
        uses: ogulcanaydogan/eu-ai-act-compliance-kit@v1
        id: ai_compliance
        with:
          system_yaml: systems/my_ai_system.yaml
          fail_on_high_risk: true
          report_format: json
          report_path: compliance_report.json

      - name: Print compliance outputs
        run: |
          echo "Risk tier: ${{ steps.ai_compliance.outputs.risk_tier }}"
          echo "Compliance %: ${{ steps.ai_compliance.outputs.compliance_percentage }}"
          echo "Non-compliant count: ${{ steps.ai_compliance.outputs.non_compliant_count }}"
          echo "Report path: ${{ steps.ai_compliance.outputs.report_path }}"
```

Action outputs:
- `risk_tier`
- `compliance_percentage`
- `report_path`
- `articles_applicable`
- `total_requirements`
- `compliant_count`
- `non_compliant_count`
- `partial_count`
- `not_assessed_count`

Fail policy defaults in the action:
- `unacceptable` tier always fails the workflow.
- If `fail_on_high_risk=true`, workflow fails only when `risk_tier=high_risk` and `non_compliant_count > 0`.

Action `report_format` support remains `json|md|html` in this release.

### Local Pre-push Gate (Developer Workflow)

Install and run the local targeted gate:

```bash
pre-commit install --hook-type pre-push
pre-commit autoupdate
pre-commit run --hook-stage pre-push --all-files
```

Behavior:
- Runs only for changed YAML files that match AI system descriptor structure.
- Executes `validate -> classify --json -> check --json` per descriptor.
- Skips unrelated YAML files (workflow/config/docs YAML).

Fail policy (aligned with CI/action defaults):
- `unacceptable` tier always fails.
- `high_risk` fails only when `non_compliant_count > 0`.
- No changed descriptors => pass with informational message.

## Documentation

- [Documentation Home](docs/index.md)
- [Changelog](CHANGELOG.md)
- [Installation Guide](docs/installation.md)
- [Quick Start Tutorial](docs/quickstart.md)
- [CLI Command Reference](docs/cli-reference.md)
- [EU AI Act Articles Explained](docs/eu-ai-act-guide.md)
- [Examples Walkthrough](docs/examples.md)
- [Custom System Descriptors](docs/custom-systems.md)
- [API Reference](docs/api-reference.md)
- [Launch Post Draft](docs/launch_post.md)

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

### Areas for Contribution
- Expanding risk classification rules with domain expertise
- Expanding technical compliance mappings and evidence logic
- Improving PDF report styling and templates
- Adding language translations
- Improving documentation and examples
- Submitting test cases for edge scenarios

## Roadmap

See [ROADMAP.md](ROADMAP.md) for detailed development plan:

- **Phase 1** ✅ Risk Classification Engine
- **Phase 2** ✅ Compliance Checker Core
- **Phase 3** ✅ Reporting & CLI Core (JSON/Markdown/HTML/PDF)
- **Phase 4** ✅ CI/CD Hardening
- **Phase 5** ✅ Documentation & Launch

## License

Apache License 2.0 — See [LICENSE](LICENSE) for details.

This toolkit is provided as guidance only. Professional legal review is always recommended for official compliance certification.

## Disclaimer

This toolkit provides automated risk classification and compliance guidance for the EU AI Act. It is **not a substitute for professional legal advice**. Organizations must:

- Conduct thorough compliance assessments with qualified legal counsel
- Maintain complete audit trails and documentation
- Implement actual safeguards described in compliance reports
- Comply with all applicable EU AI Act requirements and enforcement deadlines
- Consider implications of your specific use cases and jurisdictions

The toolkit is a starting point for understanding compliance obligations, not a guarantee of legal compliance.

## Support

- 📖 [Documentation](https://eu-ai-act-compliance-kit.readthedocs.io)
- 🐛 [Bug Reports](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/issues)
- 💬 [Discussions](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/discussions)

## Citation

If you use this toolkit in your research or projects, please cite:

```bibtex
@software{eu_ai_act_compliance_kit,
  title={EU AI Act Compliance Kit},
  author={EU AI Act Compliance Kit Contributors},
  year={2026},
  url={https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit},
  version={0.1.0}
}
```

---

**Status**: Alpha release | **Maintainer**: EU AI Act Compliance Kit Contributors | **Last Updated**: March 19, 2026
