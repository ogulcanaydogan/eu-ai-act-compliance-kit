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
- Run attempt (current): `8`
- Latest failed publish job (`invalid-publisher`): <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746/job/67886980389>
- Last 3 failed TestPyPI publish jobs:
  - Attempt 6: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746/job/67800631468>
  - Attempt 7: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746/job/67806660875>
  - Attempt 8: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746/job/67886980389>

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

## Escalation Snapshot (After Retry Limit)

Retry policy target was max 3 reruns; current run is attempt 8 and still fails
at TestPyPI trusted publishing with `invalid-publisher`.

### Last 3 attempt outcomes

- Attempt 6 (`67800631468`): `Publish to TestPyPI` failed with
  `invalid-publisher`.
- Attempt 7 (`67806660875`): `Publish to TestPyPI` failed with
  `invalid-publisher`.
- Attempt 8 (`67886980389`): `Publish to TestPyPI` failed with
  `invalid-publisher`.

### Latest failed log excerpt (attempt 8)

```text
Trusted publishing exchange failure
Token request failed
invalid-publisher: valid token, but no corresponding publisher
sub=repo:ogulcanaydogan/eu-ai-act-compliance-kit:environment:testpypi
workflow_ref=ogulcanaydogan/eu-ai-act-compliance-kit/.github/workflows/release.yml@refs/tags/v0.1.0
ref=refs/tags/v0.1.0
environment=testpypi
```

### Claim set from failed publish job

- `sub`: `repo:ogulcanaydogan/eu-ai-act-compliance-kit:environment:testpypi`
- `repository`: `ogulcanaydogan/eu-ai-act-compliance-kit`
- `workflow_ref`: `ogulcanaydogan/eu-ai-act-compliance-kit/.github/workflows/release.yml@refs/tags/v0.1.0`
- `ref`: `refs/tags/v0.1.0`
- `environment`: `testpypi`

### Environment policy snapshot (GitHub)

- `testpypi` environment:
  - branch policy: custom, tag pattern `v*.*.*`
  - required reviewers: none (auto)
- `pypi` environment:
  - branch policy: custom, tag pattern `v*.*.*`
  - required reviewer: `ogulcanaydogan`

### Support-ready incident summary

- Symptom: OIDC token exchange fails at TestPyPI with `invalid-publisher`.
- Scope: Release chain blocks at `publish-testpypi`; downstream jobs are skipped.
- Root cause likelihood: missing or non-matching Trusted Publisher registration
  on TestPyPI (and/or PyPI).
- Required fix owner: package index account admin (UI-side configuration).
- Launch policy status: single rerun has been consumed; do not rerun again until
  publisher registration is corrected and explicitly re-approved.

## Remaining One-Time Setup (External UIs)

These final steps require authenticated access to TestPyPI and PyPI.

### 1) Configure Trusted Publisher on TestPyPI

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

### 2) Configure Trusted Publisher on PyPI

Create a trusted publisher for project `eu-ai-act-compliance-kit` with:

- Owner: `ogulcanaydogan`
- Repository: `eu-ai-act-compliance-kit`
- Workflow: `.github/workflows/release.yml`
- Environment: `pypi`

### 3) Support escalation packet (current active path)

1. Open support requests to TestPyPI/PyPI with:
   - latest failed job URL
   - claim set shown above
   - confirmation that GitHub environments are configured (`testpypi`, `pypi`)
2. Wait for publisher-registration confirmation from platform support or fix
   completion in project settings.
3. Only after confirmation, re-enable a new release run decision.
