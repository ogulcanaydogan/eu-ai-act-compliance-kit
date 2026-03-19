# Quickstart

This guide walks through the default workflow with repository examples.

## 1. Validate Descriptor

```bash
ai-act validate examples/medical_diagnosis.yaml
```

## 2. Classify Risk Tier

```bash
ai-act classify examples/medical_diagnosis.yaml --json
```

Expected top-level fields:

- `system_name`
- `risk_tier`
- `confidence`
- `reasoning`
- `articles_applicable`

## 3. Run Compliance Check

```bash
ai-act check examples/medical_diagnosis.yaml --json
```

Check output includes:

- `summary.total_requirements`
- `summary.compliant_count`
- `summary.non_compliant_count`
- `summary.partial_count`
- `summary.not_assessed_count`
- `summary.compliance_percentage`
- `findings`
- `transparency`
- `gpai_summary`
- `audit_trail`

## 4. Generate Checklist

```bash
ai-act checklist examples/medical_diagnosis.yaml --format md -o checklist.md
ai-act checklist examples/medical_diagnosis.yaml --format html -o checklist.html
```

Checklist items are action-oriented and generated only for statuses:
`non_compliant`, `partial`, and `not_assessed`.

## 5. Generate Report

```bash
ai-act report examples/medical_diagnosis.yaml --format json -o report.json
ai-act report examples/medical_diagnosis.yaml --format md -o report.md
ai-act report examples/medical_diagnosis.yaml --format html -o report.html
ai-act report examples/medical_diagnosis.yaml --format pdf -o report.pdf
```

Supported report formats in this release: `json`, `md`, `html`, `pdf`.
PDF generation requires reporting extras:

```bash
pip install -e ".[reporting]"
```

## 6. Optional Transparency and GPAI Commands

```bash
ai-act transparency examples/chatbot.yaml --json
ai-act gpai examples/gpai_model.yaml --json
```

## 7. CI/CD Integration (Composite Action)

```yaml
- uses: ogulcanaydogan/eu-ai-act-compliance-kit@v1
  id: ai_compliance
  with:
    system_yaml: examples/spam_filter.yaml
    fail_on_high_risk: "true"
    report_format: json
    report_path: compliance_report.json
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

Gate policy:

- `unacceptable` always fails
- `high_risk` fails only when `fail_on_high_risk=true` and `non_compliant_count > 0`

Action `report_format` remains `json|md|html` (no PDF in action contract).
