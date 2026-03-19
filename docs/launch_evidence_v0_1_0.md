# Launch Evidence Pack (v0.1.0)

This page is a single-source evidence sheet for launch readiness and UK Global
Talent-style impact documentation.

## Canonical Project Links

- Repository: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit>
- Documentation: <https://eu-ai-act-compliance-kit.readthedocs.io>
- Changelog: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/blob/main/CHANGELOG.md>
- Roadmap: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/blob/main/ROADMAP.md>

## Release Evidence (v0.1.0)

- Version: `0.1.0` (`pyproject.toml`)
- Tag: `v0.1.0`
- Release workflow: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/workflows/release.yml>
- Latest run for `v0.1.0`: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746>

## Preflight Quality Signals

- Test suite: `pytest -q`
- Build: `python -m build`
- Package metadata: `twine check dist/*`
- Docs strict build: `mkdocs build --strict`

These commands are the minimum release preflight and are expected to pass on
`main` before semver tag push.

## Distribution Channels

- TestPyPI package page: <https://test.pypi.org/project/eu-ai-act-compliance-kit/>
- PyPI package page: <https://pypi.org/project/eu-ai-act-compliance-kit/>

Trusted publishing policy:

- `testpypi` environment: automatic
- `pypi` environment: manual approval required

## Documentation Channel

- Read the Docs config file: `.readthedocs.yaml`
- MkDocs config: `mkdocs.yml`
- Docs URL target: `https://eu-ai-act-compliance-kit.readthedocs.io`

## Community and Open Contribution Signals

- Contribution guide: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/blob/main/CONTRIBUTING.md>
- Issue tracker: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/issues>
- Pull requests: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/pulls>

## Post-Launch Verification Checklist

- [ ] `v0.1.0` workflow completed end-to-end (TestPyPI -> PyPI -> GitHub Release)
- [ ] GitHub Release `v0.1.0` visible with wheel + sdist artifacts
- [ ] TestPyPI install smoke succeeds: `ai-act --help`
- [ ] PyPI install smoke succeeds: `ai-act --help`
- [ ] RTD homepage returns HTTP `200` and pages are accessible
