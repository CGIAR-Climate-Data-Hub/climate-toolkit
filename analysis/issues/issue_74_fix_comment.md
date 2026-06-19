Status note:

- historical branch note
- README guidance has since moved further:
  - public CLI remains `climate-toolkit-fetch`
  - notebook/public Python guidance now prefers top-level API names such as `from climate_tookit import fetch_climate_data`

Branch fix now exists on `codex-nex-gddp-access-rnd`.

Resolution choice:

- treat `#74` as a usability/documentation issue on this branch
- steer users to the package entry point and notebook-safe API instead of raw internal script paths

What changed:

- `README.md`
  - corrected the package path from `climate_toolkit/` to `climate_tookit/`
  - replaced the old `python climate_toolkit/fetch_data/source_data/source_data.py` guidance
  - documented the supported CLI entry point:
    - `python -m climate_tookit.fetch_data.fetch_data ...`
  - added a Jupyter/notebook section explaining:
    - shell commands in notebooks need `!`
    - import-based `fetch_data(...)` is the safer notebook workflow
  - added a concrete notebook example and a NEX-GDDP-specific example

Why this addresses the issue:

- the old README directed users to an internal module path that was both misspelled and easy to misuse in Jupyter
- the updated guidance now points users at the package-level interface that works in terminal and is easier to translate to notebooks

Verification run on branch:

```bash
.venv/bin/python -m climate_tookit.fetch_data.fetch_data --help
rg -n "climate_toolkit|source_data\\.py|python -m climate_tookit\\.fetch_data\\.fetch_data|Jupyter / notebook usage" README.md
```

Actual branch result:

```text
usage: fetch_data.py [-h] --source SOURCE --lat LAT --lon LON --start START --end END ...
```

and README now contains:

- the package entry point example
- the notebook guidance section
- no stale `climate_toolkit/...` invocation

Issue should stay open until merged to target branch.
