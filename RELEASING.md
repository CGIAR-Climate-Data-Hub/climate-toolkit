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
> - **Workflow name:** `release-please.yml` for automated releases; register
>   `publish.yml` separately if manual releases are also needed.
> - **Environment name:** `pypi` on PyPI. The optional TestPyPI registration uses
>   `publish.yml` with environment `testpypi`.

For the existing project, use **Manage → Publishing → Add a new publisher**.
The repository owner, repository, workflow filename and environment must match
the job issuing the OIDC token. A successful manual `publish.yml` upload does
not prove that `release-please.yml` is authorized. See
[PyPI trusted-publisher configuration](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

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

   The release configuration also updates the project's version in `uv.lock`
   in the same PR. Dependency versions remain unchanged. CI exercises the actual
   Release Please TOML updater and checks the resulting candidate with `uv lock
   --check`. Its JSONPath uses `name.value` because Release Please's TOML parser
   wraps scalar values with position metadata. Keep the updater smoke test when
   upgrading Release Please. This replaces the separate post-PR lockfile push.

   If an older release PR has a stale lockfile, regenerate it with the CI uv
   version, inspect the diff and commit the repair to that release branch before
   merging. Re-running an old failed workflow does not test a newer commit;
   check that green CI belongs to the current release PR head.

3. **Merge the release PR.** That creates the GitHub Release + `vX.Y.Z` tag and
   the workflow publishes to PyPI automatically. Verify the upload before
   preparing the user announcement below.

   Automated publishing checks out that release tag explicitly. Publishing
   remains a separate action from merging feature/fix PRs.

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

## Email release updates

The **Climate Toolkit release updates** list is for people who use the
package. Aim for one short notice per stable PyPI version. Skip release PRs,
pre-releases and TestPyPI rehearsals. GitHub Releases and the versioned
changelog remain the public record.

Pete manages requests at p.steward@cgiar.org. Keep a private contact list in
the mailbox. Add each sender who asks to subscribe once. Remove anyone who
asks to unsubscribe before preparing the next notice.

**For each stable release:**

1. Verify the exact version on PyPI and read its changelog at the release tag.
   Check linked pull requests when a changelog entry does not explain user impact.
2. Draft the subject as `Climate Toolkit <version>: <main user impact>`.
   Open with who is affected. Give a concrete action: what to change, what to
   rerun, or why no action is needed. Call out changed defaults, units or
   scientific results where applicable. Include links to the project, tagged
   changelog and version on PyPI, and invite readers to reply “unsubscribe” to leave the list.
3. Address the notice to Pete and put current subscribers in Bcc. Show Pete
   the exact recipients, subject and full draft.
   Send only after Pete explicitly approves that draft. Check Sent Items for the
   version before retrying.

## Notes

- Ordinary pushes to `main` only make release-please **open/update the release
  PR** — they never publish. PyPI is touched only when a Release is created
  (by merging the release PR, or a manual Release).
- A release re-using an existing version number will **fail** at upload (PyPI
  rejects duplicates). Always bump first.
- CI already builds and `twine check`s the dist on every push, so a release
  should never be the first time the build is exercised.
