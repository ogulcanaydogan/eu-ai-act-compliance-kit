# API Reference

This package can be used as a Python library in addition to CLI usage.

## Package Metadata

```python
import eu_ai_act

print(eu_ai_act.__version__)
```

## Public Exports

From `eu_ai_act`:

- `AISystemDescriptor`
- `RiskTier`
- `UseCaseDomain`
- `RiskClassifier`
- `ComplianceChecker`
- `ChecklistGenerator`
- `ReportGenerator`
- `TransparencyFinding`
- `TransparencyChecker`
- `GPAIModelInfo`
- `GPAIAssessment`
- `GPAIAssessor`
- `SecurityMapper`
- `SecurityMappingResult`
- `SecurityMappingSummary`
- `SecurityControlResult`

## Loading Descriptors

```python
from eu_ai_act.schema import load_system_descriptor_from_file

descriptor = load_system_descriptor_from_file("examples/medical_diagnosis.yaml")
```

## Classification

```python
from eu_ai_act.classifier import RiskClassifier

classifier = RiskClassifier()
classification = classifier.classify(descriptor)

print(classification.tier.value)
print(classification.reasoning)
print(classification.articles_applicable)
print(classification.confidence)
```

## Compliance Checking

```python
from eu_ai_act.checker import ComplianceChecker

checker = ComplianceChecker()
report = checker.check(descriptor)

print(report.risk_tier.value)
print(report.summary.total_requirements)
print(report.summary.compliance_percentage)
print(report.findings.keys())
```

## Checklist Generation

```python
from eu_ai_act.checklist import ChecklistGenerator

generator = ChecklistGenerator()
checklist = generator.generate(
    descriptor=descriptor,
    tier=report.risk_tier,
    findings=report.findings,
    generated_at=report.generated_at,
)

print(checklist.to_json())
```

## Transparency and GPAI

```python
from eu_ai_act.transparency import TransparencyChecker
from eu_ai_act.gpai import GPAIAssessor, load_gpai_model_info_from_file

transparency_checker = TransparencyChecker()
transparency_findings = []
transparency_findings.extend(transparency_checker.check_art50_disclosure(descriptor))
transparency_findings.extend(transparency_checker.check_deepfake_detection(descriptor))
transparency_findings.extend(transparency_checker.check_gpai_obligations(descriptor))

gpai_info = load_gpai_model_info_from_file("examples/gpai_model.yaml")
gpai_assessment = GPAIAssessor().assess(gpai_info)
```

## Report Generation

```python
from eu_ai_act.reporter import ReportGenerator

report_generator = ReportGenerator()
json_report = report_generator.generate_report(
    descriptor=descriptor,
    classification=classification,
    compliance_report=report,
    transparency_findings=transparency_findings,
    gpai_assessment=gpai_assessment,
    checklist=checklist,
    format="json",
)

pdf_bytes = report_generator.generate_pdf_report(
    descriptor=descriptor,
    classification=classification,
    compliance_report=report,
    transparency_findings=transparency_findings,
    gpai_assessment=gpai_assessment,
    checklist=checklist,
)

with open("report.pdf", "wb") as f:
    f.write(pdf_bytes)
```

Supported report formats: `json`, `md`, `html`.
PDF is available via `generate_pdf_report(...) -> bytes` and requires optional dependency:
`pip install -e ".[reporting]"`.

## OWASP Security Mapping

```python
from eu_ai_act.security_mapping import SecurityMapper

security_mapping = SecurityMapper().map_from_compliance(report)
print(security_mapping.framework)
print(security_mapping.summary.to_dict())
print(security_mapping.controls[0].to_dict())
```
