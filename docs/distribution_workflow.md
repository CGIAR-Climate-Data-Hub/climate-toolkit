# Distribution Workflow

## Current Status

Toolkit is installable as normal Python package and now has explicit
distribution smoke coverage for:

- editable install: `python -m pip install -e .`
- non-editable local install: `python -m pip install .`
- artifact build: `python -m build`
- artifact metadata validation: `twine check dist/*`
- wheel / sdist install smoke via automated tests

## Current Release Decision

The toolkit is **published on PyPI** as
[`climate-toolkit`](https://pypi.org/project/climate-toolkit/) —
`pip install climate-toolkit`.

Releases are automated via **Trusted Publishing** (OIDC, no stored tokens):
publishing a GitHub Release builds the package and uploads it to PyPI; marking
the Release as a pre-release routes it to TestPyPI as a rehearsal instead. The
full process is in [`RELEASING.md`](https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit/blob/main/RELEASING.md).

## Local Verification

Preferred locked workflow:

```bash
uv sync --locked --group dev
rm -rf .tmp/dist-release
uv run python -m build --no-isolation --outdir .tmp/dist-release
uv run twine check .tmp/dist-release/*
uv run pytest -q tests/test_distribution_artifacts.py
```

Fallback `pip` checks:

```bash
python -m pip install -e .
python -m pip install .
```

## Per-release checklist

These gates were met for the first public release (0.1.0) and remain the
checklist for each subsequent version:

1. keep wheel and sdist smoke checks green in CI
2. keep README install paths current
3. avoid placeholder auth/setup values in user-facing docs
4. document expected runtime/auth requirements clearly for packaged users
5. bump the version (PyPI versions are immutable) and tag the release
