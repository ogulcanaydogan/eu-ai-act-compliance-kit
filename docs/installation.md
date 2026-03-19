# Installation

## Prerequisites

- Python `>=3.11`
- `pip`
- Optional: virtual environment manager (`venv`, `uv`, or similar)

## Install From Source

```bash
git clone https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit.git
cd eu-ai-act-compliance-kit
pip install -e .
```

## Install Development Extras

```bash
pip install -e ".[dev]"
```

Includes: `pytest`, `ruff`, `black`, `mypy`, `pre-commit`.

## Install Documentation Extras

```bash
pip install -e ".[docs]"
```

Includes: `mkdocs`, `mkdocs-material`.

## Install Reporting Extras (PDF)

```bash
pip install -e ".[reporting]"
```

Includes: `weasyprint`.

## Verify Installation

```bash
ai-act --help
ai-act classify examples/medical_diagnosis.yaml --json
```

## Build Docs Locally

```bash
mkdocs build --strict
mkdocs serve
```

Open `http://127.0.0.1:8000` for local preview.
