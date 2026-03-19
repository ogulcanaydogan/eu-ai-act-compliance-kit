# Examples

The repository includes descriptors for different risk and obligation profiles.

## AI System Examples

### `examples/medical_diagnosis.yaml`

- Typical outcome: `high_risk`
- Focus areas: `Art. 10`, `Art. 11`, `Art. 13`, `Art. 14`, `Art. 15`, `Art. 43`

```bash
ai-act classify examples/medical_diagnosis.yaml
ai-act check examples/medical_diagnosis.yaml --json
```

### `examples/hiring_tool.yaml`

- Typical outcome: `high_risk`
- Focus areas: employment and rights-impact controls

```bash
ai-act classify examples/hiring_tool.yaml
ai-act report examples/hiring_tool.yaml --format md -o hiring_report.md
```

### `examples/chatbot.yaml`

- Typical outcome: `minimal`
- Useful for transparency checks

```bash
ai-act transparency examples/chatbot.yaml --json
```

### `examples/social_scoring.yaml`

- Typical outcome: `unacceptable`
- Demonstrates prohibited-practice behavior

```bash
ai-act classify examples/social_scoring.yaml
```

### `examples/spam_filter.yaml`

- Typical outcome: `minimal`
- Useful for CI action pass scenario

```bash
ai-act check examples/spam_filter.yaml --json
```

## GPAI Examples

### `examples/gpai_model.yaml`

- High-compute profile with strong capability signals
- Intended for systemic-risk trigger scenario testing

```bash
ai-act gpai examples/gpai_model.yaml --json
```

### `examples/gpai_model_low_risk.yaml`

- Lower-scale model profile
- Useful for non-systemic baseline tests

```bash
ai-act gpai examples/gpai_model_low_risk.yaml --json
```

## Recommended Smoke Run

```bash
ai-act validate examples/medical_diagnosis.yaml
ai-act classify examples/medical_diagnosis.yaml --json
ai-act check examples/medical_diagnosis.yaml --json
ai-act checklist examples/medical_diagnosis.yaml --format md -o checklist.md
ai-act report examples/medical_diagnosis.yaml --format html -o report.html
```
