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
- Latest failed publish job (`invalid-publisher`): <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746/job/67750646592>

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
- RTD project dashboard: <https://app.readthedocs.org/projects/eu-ai-act-compliance-kit/>
- RTD successful build (`latest`): <https://app.readthedocs.org/projects/eu-ai-act-compliance-kit/builds/31879843/>

## Community and Open Contribution Signals

- Contribution guide: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/blob/main/CONTRIBUTING.md>
- Issue tracker: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/issues>
- Pull requests: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/pulls>

## Post-Launch Verification Checklist

- [ ] `v0.1.0` workflow completed end-to-end (TestPyPI -> PyPI -> GitHub Release)
- [ ] GitHub Release `v0.1.0` visible with wheel + sdist artifacts
- [ ] TestPyPI install smoke succeeds: `ai-act --help`
- [ ] PyPI install smoke succeeds: `ai-act --help`
- [x] RTD homepage returns HTTP `200` and pages are accessible

## Remaining One-Time Setup (External UIs)

These final steps require authenticated access to TestPyPI, PyPI, and Read the
Docs.

### 1) Import project on Read the Docs

1. Log in at `https://app.readthedocs.org/` with GitHub.
2. Import repository: `ogulcanaydogan/eu-ai-act-compliance-kit`.
3. Confirm build config is read from `.readthedocs.yaml`.
4. Trigger `latest` build and verify:
   - `https://eu-ai-act-compliance-kit.readthedocs.io/` returns `200`.

### 2) Configure Trusted Publisher on TestPyPI

Create a trusted publisher for project `eu-ai-act-compliance-kit` with:

- Owner: `ogulcanaydogan`
- Repository: `eu-ai-act-compliance-kit`
- Workflow: `.github/workflows/release.yml`
- Environment: `testpypi`

Expected OIDC claims (from failed run log):

- `sub`: `repo:ogulcanaydogan/eu-ai-act-compliance-kit:environment:testpypi`
- `workflow_ref`: `ogulcanaydogan/eu-ai-act-compliance-kit/.github/workflows/release.yml@refs/tags/v0.1.0`
- `ref`: `refs/tags/v0.1.0`

Observed failure status:

- Current release reruns fail at TestPyPI publish with `invalid-publisher`.
- GitHub environment and claims are correct; missing step is TestPyPI-side trusted
  publisher registration matching the claims above.

### 3) Configure Trusted Publisher on PyPI

Create a trusted publisher for project `eu-ai-act-compliance-kit` with:

- Owner: `ogulcanaydogan`
- Repository: `eu-ai-act-compliance-kit`
- Workflow: `.github/workflows/release.yml`
- Environment: `pypi`

### 4) Rerun release workflow and approve PyPI gate

1. Rerun failed release run:
   - `gh run rerun 23296772746`
2. Approve `pypi` environment when prompt appears in Actions UI.
3. Verify `publish-pypi` and `github-release` jobs complete successfully.
