# Releasing to PyPI

Publishing uses **Trusted Publishing** (OIDC) — **no API tokens are stored**.
There are two paths, and both build + upload the same way:

- **Automated (default): `release-please`** (`.github/workflows/release-please.yml`).
  A bot keeps a "release PR" open that bumps the version in `pyproject.toml` and
  updates `CHANGELOG.md` from your [Conventional Commits](https://www.conventionalcommits.org/).
  **Merging that PR** cuts the GitHub Release and publishes to PyPI. This is the
  normal way to ship — see [Cutting a release](#cutting-a-release-every-new-version).
- **Manual: `publish.yml`.** Cutting a GitHub Release by hand still works and
  publishes over OIDC. Tick *"Set as a pre-release"* to route it to **TestPyPI**
  as a rehearsal; a normal Release goes to **PyPI**. Use this for a one-off or a
  TestPyPI dry run.

## One-time setup (a maintainer)

Register the repo as a trusted publisher — this cannot be automated. Do it on
**PyPI**, and also on **TestPyPI** if you want the rehearsal path:

> pypi.org (and/or test.pypi.org) → your account → **Publishing** → **Add a pending publisher**
> - **PyPI Project Name:** `climate-toolkit`
> - **Owner:** `CGIAR-Climate-Data-Hub`
> - **Repository name:** `climate-toolkit`
> - **Workflow name:** `publish.yml`
> - **Environment name:** `pypi` on PyPI · `testpypi` on TestPyPI

Optionally protect the `pypi` GitHub Environment (repo → Settings → Environments)
with required reviewers, so a human approves each production publish.

**Also enable release-please to open PRs** (one-time, a maintainer):
repo → **Settings → Actions → General → Workflow permissions** → tick
**"Allow GitHub Actions to create and approve pull requests"**. Without it the
release PR can't be created.

## Cutting a release (every new version)

PyPI versions are **immutable** — every upload needs a new version number. With
release-please you don't edit the version or changelog by hand; commit messages
drive it.

1. **Land your changes with Conventional Commit messages.** The commit *type*
   decides the next version (via [semver](https://semver.org)):
   - `fix:` → patch (`0.1.0` → `0.1.1`)
   - `feat:` → minor (`0.1.0` → `0.2.0`)
   - `feat!:` / a `BREAKING CHANGE:` footer → major (`0.1.0` → `1.0.0`)
   - `docs:` / `chore:` / `ci:` / `refactor:` → no release on their own

2. **Review the release PR.** release-please opens/updates a PR titled
   *"chore: release x.y.z"* with the bumped `pyproject.toml` and a generated
   `CHANGELOG.md` section. Sanity-check the version and notes.

3. **Merge the release PR.** That creates the GitHub Release + `vX.Y.Z` tag and
   the workflow publishes to PyPI automatically. Nothing else to do.

### Manual alternative / TestPyPI rehearsal

To ship without release-please (or to rehearse on TestPyPI), cut a Release by
hand: bump `version` in `pyproject.toml`, merge, then repo → **Releases** →
**Draft a new release**, tag `vX.Y.Z` targeting `main`, **Publish**. `publish.yml`
uploads to PyPI. Tick *"Set as a pre-release"* to send it to **TestPyPI** instead:
```bash
pip install -i https://test.pypi.org/simple/ climate-toolkit --pre
```

## Verify

- Watch the **Actions** tab — the `Publish to PyPI` run should be green.
- Confirm it's live: https://pypi.org/project/climate-toolkit/
- Fresh install:
  ```bash
  pip install climate-toolkit            # add --pre for an alpha/rc
  python -c "import climate_toolkit as ct; print(ct.__version__)"
  ```

## Notes

- Ordinary pushes to `main` only make release-please **open/update the release
  PR** — they never publish. PyPI is touched only when a Release is created
  (by merging the release PR, or a manual Release).
- A release re-using an existing version number will **fail** at upload (PyPI
  rejects duplicates). Always bump first.
- CI already builds and `twine check`s the dist on every push, so a release
  should never be the first time the build is exercised.
