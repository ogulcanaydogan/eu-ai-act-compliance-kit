# Launch Evidence Pack (v0.1.0)

This page is the single-source launch evidence sheet for `v0.1.0`.

Last validated: **March 20, 2026** (Europe/London).

## Canonical Project Links

- Repository: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit>
- Documentation: <https://eu-ai-act-compliance-kit.readthedocs.io>
- Changelog: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/blob/main/CHANGELOG.md>
- Roadmap: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/blob/main/ROADMAP.md>

## Release Evidence (v0.1.0)

- Version: `0.1.0` (`pyproject.toml`)
- Tag: `v0.1.0`
- Release workflow: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/workflows/release.yml>

Primary successful launch run:

- Run: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23342105986>
- QA + Build: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23342105986/job/67897983282>
- Publish to PyPI: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23342105986/job/67898038584>
- Create GitHub Release: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23342105986/job/67898198179>

Post-fix validation rerun (Trusted Publisher recovery chain):

- Run: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746/attempts/15>
- QA + Build: success
- Publish to TestPyPI: success
- TestPyPI Smoke Install: success
- Publish to PyPI: failed with `HTTP 400` (duplicate upload after package was already published)

GitHub Release:

- Release page: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/releases/tag/v0.1.0>
- Artifacts:
  - `eu_ai_act_compliance_kit-0.1.0-py3-none-any.whl`
  - `eu_ai_act_compliance_kit-0.1.0.tar.gz`

## Distribution Channels

- TestPyPI package page: <https://test.pypi.org/project/eu-ai-act-compliance-kit/>
- PyPI package page: <https://pypi.org/project/eu-ai-act-compliance-kit/>

Trusted publishing policy:

- `testpypi` environment: automatic
- `pypi` environment: manual approval required

## Documentation Channel

- Read the Docs config file: `.readthedocs.yaml`
- MkDocs config: `mkdocs.yml`
- RTD docs URL: <https://eu-ai-act-compliance-kit.readthedocs.io/en/latest/>
- RTD project dashboard: <https://app.readthedocs.org/projects/eu-ai-act-compliance-kit/>
- RTD successful build (`latest`): <https://app.readthedocs.org/projects/eu-ai-act-compliance-kit/builds/31879843/>

## Live Validation Snapshot (March 20, 2026)

- `https://test.pypi.org/pypi/eu-ai-act-compliance-kit/json` -> `200`
- `https://pypi.org/pypi/eu-ai-act-compliance-kit/json` -> `200`
- `https://eu-ai-act-compliance-kit.readthedocs.io/en/latest/` -> `200`
- Local install smoke (TestPyPI) + `ai-act --help`: pass
- Local install smoke (PyPI) + `ai-act --help`: pass

## Preflight Quality Signals

- Test suite: `pytest -q`
- Build: `python -m build`
- Package metadata: `twine check dist/*`
- Docs strict build: `mkdocs build --strict`

## Community and Open Contribution Signals

- Contribution guide: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/blob/main/CONTRIBUTING.md>
- Issue tracker: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/issues>
- Pull requests: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/pulls>

## Post-Launch Verification Checklist

- [x] `v0.1.0` release pipeline produced a public package and release artifacts
- [x] GitHub Release `v0.1.0` visible with wheel + sdist artifacts
- [x] TestPyPI availability verified (`json=200`) and smoke install passed
- [x] PyPI availability verified (`json=200`) and smoke install passed
- [x] RTD docs endpoint returns HTTP `200`

## Final Evidence Links

- Successful workflow run: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23342105986>
- Recovery rerun (attempt 15): <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/actions/runs/23296772746/attempts/15>
- GitHub Release: <https://github.com/ogulcanaydogan/eu-ai-act-compliance-kit/releases/tag/v0.1.0>
- TestPyPI package: <https://test.pypi.org/project/eu-ai-act-compliance-kit/>
- PyPI package: <https://pypi.org/project/eu-ai-act-compliance-kit/>
- RTD docs: <https://eu-ai-act-compliance-kit.readthedocs.io/en/latest/>
