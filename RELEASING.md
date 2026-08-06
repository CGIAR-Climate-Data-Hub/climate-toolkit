# Releasing to PyPI

Publishing is automated via **Trusted Publishing** (`.github/workflows/publish.yml`):
publishing a GitHub Release builds the package and uploads it to PyPI over OIDC —
**no API tokens are stored**.

## One-time setup (a maintainer, on PyPI)

Register the repo as a trusted publisher — this cannot be automated:

> PyPI → your account → **Publishing** → **Add a pending publisher**
> - **PyPI Project Name:** `climate-toolkit`
> - **Owner:** `CGIAR-Climate-Data-Hub`
> - **Repository name:** `climate-toolkit`
> - **Workflow name:** `publish.yml`
> - **Environment name:** `pypi`

Optionally protect the `pypi` GitHub Environment (repo → Settings → Environments)
with required reviewers, so a human approves each publish.

## Cutting a release (every new version)

PyPI versions are **immutable** — every upload needs a new version number.

1. **Bump the version** in `pyproject.toml`:
   ```toml
   version = "0.1.0"        # was 0.1.0a0
   ```
   - `0.1.0a0`, `0.1.0rc1` → pre-releases (only installed with `pip install --pre`)
   - `0.1.0`, `0.2.0`, `1.0.0` → normal releases (`pip install climate-toolkit`)
   Follow [semantic versioning](https://semver.org): patch = fixes, minor =
   features, major = breaking changes.

2. **Update `CHANGELOG.md`** with what's in this release.

3. **Merge to `main`** (via the normal PR flow).

4. **Publish a GitHub Release:**
   - Repo → **Releases** → **Draft a new release**
   - **Tag:** `v0.1.0` (matching the version), target `main`
   - Title + notes, then **Publish release**.

   The `publish.yml` workflow runs automatically and uploads to PyPI.

## Verify

- Watch the **Actions** tab — the `Publish to PyPI` run should be green.
- Confirm it's live: https://pypi.org/project/climate-toolkit/
- Fresh install:
  ```bash
  pip install climate-toolkit            # add --pre for an alpha/rc
  python -c "import climate_toolkit as ct; print(ct.__version__)"
  ```

## Notes

- The workflow only fires on a **published Release**, never on ordinary pushes —
  so day-to-day commits never touch PyPI.
- A release re-using an existing version number will **fail** at upload (PyPI
  rejects duplicates). Always bump first.
- CI already builds and `twine check`s the dist on every push, so a release
  should never be the first time the build is exercised.
