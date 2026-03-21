# Contributing to EU AI Act Compliance Kit

Thank you for your interest in contributing! This document provides guidelines for development, testing, and submitting pull requests.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment.

## Getting Started

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit.git
   cd eu-ai-act-compliance-kit
   ```

2. **Create a virtual environment**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install in development mode**
   ```bash
   pip install -e ".[dev,docs]"
   ```

4. **Set up pre-commit hooks** (recommended)
   ```bash
   pre-commit install --hook-type pre-push
   ```
   Update hook revisions when needed:
   ```bash
   pre-commit autoupdate
   ```
   Optional smoke check:
   ```bash
   pre-commit run --hook-stage pre-push --all-files
   ```

### Project Structure

```
src/eu_ai_act/
├── schema.py          # Pydantic models for AI system descriptors
├── classifier.py      # Risk tier classification logic
├── checker.py         # Compliance requirement checking
├── checklist.py       # Checklist generation
├── reporter.py        # Report generation (JSON, HTML, MD, PDF)
├── articles.py        # EU AI Act articles database
├── transparency.py    # Art. 50 and GPAI transparency checks
├── gpai.py           # GPAI model obligation assessment
└── cli.py            # Click CLI commands

tests/
├── test_schema.py     # Schema validation tests
├── test_classifier.py # Classification logic tests
├── test_checker.py    # Compliance checking tests
├── test_reporter.py   # Report generation tests
├── test_cli.py        # CLI integration tests
└── fixtures/          # Test data and fixtures
```

### First Contribution Path

Use this minimal path before opening your first PR:

```bash
pip install -e ".[dev,docs]"
./scripts/quickstart_smoke.sh
pre-commit install --hook-type pre-push
pre-commit run --hook-stage pre-push --all-files
```

If these steps pass, choose a small scoped change (docs/tests/bugfix), keep the
PR focused, and include the command outputs in the PR description.

## Development Workflow

### 1. Create a branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number
```

### 2. Make changes and commit
```bash
# Make your changes
git add .
git commit -m "Clear, concise commit message"
```

**Commit message guidelines:**
- Use imperative mood ("add feature" not "adds feature")
- Reference issues when relevant (#123)
- Keep first line under 50 characters
- Add detailed description in body if needed

### 3. Run tests locally
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_classifier.py -v

# Run with coverage
pytest tests/ --cov=src/eu_ai_act --cov-report=html

# Run only fast tests
pytest tests/ -m "not slow"
```

### Local pre-push compliance gate

This repository uses a targeted pre-push gate for AI descriptor changes via
`.pre-commit-config.yaml` and `scripts/prepush_gate.py`.

Flow for each changed descriptor:
1. `ai-act validate`
2. `ai-act classify --json`
3. `ai-act check --json`

Fail policy is aligned with CI/action behavior:
- `unacceptable` always fails.
- `high_risk` fails when `non_compliant_count > 0`.
- No changed AI descriptors means gate passes with an informational message.

### 4. Format and lint code
```bash
# Format with black
black src/ tests/

# Check with ruff
ruff check src/ tests/

# Type check with mypy
mypy src/eu_ai_act/
```

### 5. Update documentation
- Update relevant docstrings in code
- Update README.md for user-facing changes
- Update ROADMAP.md for feature additions
- Add examples to `examples/` directory

### 6. Push and create pull request
```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub with:
- Clear title describing the change
- Description of the change and why it's needed
- Reference to any related issues (#123)
- List of any breaking changes

## How to Release

Release flow is tag-driven and publishes to PyPI through trusted publishing.

1. Ensure `pyproject.toml` version is bumped and changelog is updated.
2. Create and push a semver tag:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
3. GitHub `release.yml` runs:
   - QA + build + artifact checks
   - PyPI publish (gated by `pypi` environment approval)
   - GitHub Release creation with attached artifacts

Notes:
- Docs hosting remains Read the Docs; CI only validates docs builds.
- Release tag must match `v*.*.*`.

## Testing

### Test Requirements

- **Coverage Target**: >80% of code must be covered by tests
- **Test Framework**: pytest
- **Assertion Library**: pytest's built-in assertions

### Writing Tests

```python
# tests/test_classifier.py
import pytest
from eu_ai_act.schema import AISystemDescriptor, UseCaseDomain
from eu_ai_act.classifier import RiskClassifier, RiskTier

class TestRiskClassifier:
    """Test suite for RiskClassifier"""

    def test_classify_high_risk_medical_system(self):
        """Test that medical AI systems are classified as high-risk"""
        # Setup
        descriptor = AISystemDescriptor(
            name="Test Medical AI",
            # ... other fields
        )
        classifier = RiskClassifier()

        # Execute
        classification = classifier.classify(descriptor)

        # Assert
        assert classification.tier == RiskTier.HIGH_RISK
        assert classification.confidence > 0.85
        assert "Art. 6" in classification.articles_applicable

    def test_classify_prohibited_social_scoring(self):
        """Test that social scoring systems are classified as unacceptable"""
        # Setup and execute...
        # Assert prohibition
        assert classification.tier == RiskTier.UNACCEPTABLE
```

### Test Fixtures

Place test data in `tests/fixtures/`:
```python
# tests/conftest.py
import pytest
from eu_ai_act.schema import AISystemDescriptor

@pytest.fixture
def medical_ai_descriptor():
    """Sample high-risk medical AI system"""
    return AISystemDescriptor(
        name="Medical AI",
        # ...
    )
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test
pytest tests/test_classifier.py::TestRiskClassifier::test_classify_high_risk

# Run with coverage report
pytest tests/ --cov=src/eu_ai_act --cov-report=term-missing

# Run and stop on first failure
pytest tests/ -x

# Run only tests marked as integration
pytest tests/ -m integration
```

## Code Style

### Black
The project uses **black** for code formatting (line length: 100).

```bash
black src/ tests/
```

### Ruff
Use **ruff** for linting.

```bash
ruff check src/ tests/
ruff check src/ tests/ --fix  # Auto-fix
```

### Type Hints
Include type hints for all functions and class methods:

```python
from typing import List, Optional
from eu_ai_act.schema import AISystemDescriptor, RiskTier

def classify(self, descriptor: AISystemDescriptor) -> RiskTier:
    """Classify an AI system by risk tier.

    Args:
        descriptor: AI system descriptor

    Returns:
        RiskTier classification
    """
    # Implementation
```

### Docstrings
Use Google-style docstrings:

```python
def classify(descriptor: AISystemDescriptor) -> RiskClassification:
    """Classify an AI system into a risk tier.

    Analyzes the AI system descriptor and assigns it to one of four
    risk tiers based on EU AI Act Article 6 and Annex III criteria.

    Args:
        descriptor: AI system descriptor with use cases and safeguards

    Returns:
        RiskClassification with tier, reasoning, and applicable articles

    Raises:
        ValueError: If descriptor is invalid or incomplete

    Example:
        >>> descriptor = AISystemDescriptor(...)
        >>> classifier = RiskClassifier()
        >>> classification = classifier.classify(descriptor)
        >>> print(classification.tier)
        "high_risk"
    """
```

## Documentation

### Markdown Guidelines
- Use clear, concise language
- Include code examples
- Link to relevant sections
- Keep lists short and organized

### Building Documentation Locally
```bash
pip install -e ".[docs]"
mkdocs serve
# Visit http://localhost:8000
```

### Documentation Updates
- **README.md**: User-facing features, quickstart, examples
- **docs/**: Detailed guides and API reference
- **Docstrings**: In-code documentation for developers

## Submitting Pull Requests

1. **Before submitting:**
   - [ ] Tests pass locally (`pytest tests/ -v`)
   - [ ] Code is formatted (`black src/ tests/`)
   - [ ] Linting passes (`ruff check src/ tests/`)
   - [ ] Type checking passes (`mypy src/eu_ai_act/`)
   - [ ] Coverage maintained (>80%)
   - [ ] Documentation updated
   - [ ] Commit messages are clear

2. **PR Title Format:**
   - `fix: description` for bug fixes
   - `feat: description` for new features
   - `docs: description` for documentation
   - `test: description` for test improvements
   - `refactor: description` for code refactoring

3. **PR Description Template:**
   ```markdown
   ## Description
   Brief description of the change

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Documentation update
   - [ ] Performance improvement
   - [ ] Breaking change

   ## Related Issues
   Closes #123

   ## Testing
   Describe how you tested the change

   ## Checklist
   - [ ] Tests pass locally
   - [ ] Code is formatted
   - [ ] Documentation updated
   - [ ] No breaking changes (or listed above)
   ```

## Areas for Contribution

### High Priority
- **Phase 2 Implementation**: Compliance checking engine
- **Risk Classification Expansion**: Add domain-specific rules
- **Test Coverage**: Increase test coverage beyond 80%
- **Documentation**: More examples and guides

### Medium Priority
- **Report Templates**: Custom HTML/PDF templates
- **Integration Tests**: Integration with CI/CD systems
- **Performance**: Optimize classification for large systems
- **Internationalization**: Support additional languages

### Nice to Have
- **Dashboard UI**: Web interface for compliance tracking
- **API Server**: REST API for programmatic access
- **Database Support**: Persistent storage of assessments
- **Visualization**: Charts and compliance trends

## Reporting Bugs

Use the [Bug Report](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/issues/new?template=bug_report.md) template on GitHub.

Include:
- Clear title
- Detailed description of the issue
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment (OS, Python version, etc.)
- Relevant code or YAML files

## Requesting Features

Use the [Feature Request](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/issues/new?template=feature_request.md) template.

Include:
- Clear title and description
- Use case and motivation
- Proposed implementation (if applicable)
- Any relevant EU AI Act articles

## Questions?

- Open a [Discussion](https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/discussions)
- Check existing issues for similar questions
- Email: compliance-kit@example.com

## Recognition

Contributors are recognized in:
- CONTRIBUTORS.md file
- GitHub contributors page
- Release notes

Thank you for contributing to making EU AI Act compliance accessible!
