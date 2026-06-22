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

Current release strategy is intentionally conservative:

- use GitHub releases first
- do not publish directly to PyPI yet
- consider TestPyPI only after install docs, wheel smoke checks, and
  auth-heavy runtime expectations remain stable across contributor machines

Reason:

- toolkit has non-trivial runtime expectations around Earth Engine auth,
  optional Earthdata-backed paths, caches, and large-data workflows
- package install shape is now stronger, but public-distribution support burden
  should not outrun runtime/documentation maturity

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

## Future Promotion Gates

Before TestPyPI / PyPI:

1. keep wheel and sdist smoke checks green in CI
2. keep README install paths current
3. avoid placeholder auth/setup values in user-facing docs
4. document expected runtime/auth requirements clearly for packaged users
5. decide version bump / tag process for first public release
