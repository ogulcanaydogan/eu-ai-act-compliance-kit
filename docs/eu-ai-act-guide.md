# EU AI Act Guide (Toolkit Mapping)

This page summarizes how the toolkit maps key obligations in Regulation (EU)
2024/1689. It is a technical mapping, not legal advice.

## Risk Tiers in the Toolkit

- `unacceptable`: prohibited practices (`Art. 5`)
- `high_risk`: Annex III style domains and strong rights-impact signals (`Art. 6`, plus controls)
- `limited`: transparency-heavy obligations (`Art. 50`)
- `minimal`: baseline/low-risk context

## Articles Actively Evaluated in Compliance Checker

- `Art. 5`
- `Art. 10`
- `Art. 11`
- `Art. 13`
- `Art. 14`
- `Art. 15`
- `Art. 43`
- `Art. 50`

Checker statuses:

- `compliant`
- `non_compliant`
- `partial`
- `not_assessed`

Policy baseline:

- Missing evidence should bias to `not_assessed`
- Explicit control gaps should return `non_compliant`
- Mixed/partial controls should return `partial`

## Transparency and GPAI Coverage

Transparency module provides finding-level signals for:

- `Art. 50` disclosure indicators
- Deepfake/synthetic media indicators
- GPAI-related obligation triggers

GPAI module assesses `Art. 51-55` signals from a dedicated GPAI model descriptor
and flags systemic-risk indicators using deterministic thresholds.

## Deadlines and Action Prioritization

Checklist defaults:

- `Art. 5`: `0` months
- `Art. 50`: `6` months
- `Art. 10/11/13/14/15/43`: `24` months

Only actionable statuses are emitted as checklist items (`non_compliant`,
`partial`, `not_assessed`).

## Legal Disclaimer

Use this toolkit for engineering controls, evidence collection, and audit trail
preparation. Final compliance determinations should be validated by legal teams.
