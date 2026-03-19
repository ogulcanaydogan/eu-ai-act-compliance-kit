# Custom System Descriptors

Create a YAML descriptor that conforms to `AISystemDescriptor`.

## Required Top-Level Fields

- `name` (string)
- `version` (string)
- `description` (string, minimum length 10)
- `use_cases` (list, at least 1)
- `data_practices` (list, at least 1)
- `human_oversight` (object)
- `training_data_source` (string, minimum length 10)
- `documentation` (boolean)
- `performance_monitoring` (boolean)

Optional:

- `incident_procedure`
- `created_at`
- `last_updated`

## Minimal Valid Template

```yaml
name: "My AI System"
version: "1.0.0"
description: "Model that supports internal operational decision support."

use_cases:
  - domain: general_purpose
    description: "Assists support agents with response drafting."
    autonomous_decision: false
    impacts_fundamental_rights: false

data_practices:
  - type: personal
    retention_period: 30
    sharing_third_parties: false
    explicit_consent: true

human_oversight:
  oversight_mechanism: "approval_required"
  fallback_procedure: "Escalate to supervisor if confidence is low."
  review_frequency: "per_decision"
  human_authority: true

training_data_source: "Curated internal support archive with review filters."
documentation: true
performance_monitoring: true
```

## Domain Values

`use_cases[].domain` supported enum values:

- `biometric`
- `critical_infrastructure`
- `law_enforcement`
- `employment`
- `credit_scoring`
- `education`
- `general_purpose`
- `healthcare`
- `content_moderation`
- `other`

## Validation Workflow

```bash
ai-act validate my_system.yaml
ai-act classify my_system.yaml
ai-act check my_system.yaml --json
```

## Modeling Guidance

- Prefer concrete descriptions over generic one-liners
- Document oversight and fallback procedures clearly
- Keep `training_data_source` specific and evidence-oriented
- Set `documentation` and `performance_monitoring` to reflect real controls
