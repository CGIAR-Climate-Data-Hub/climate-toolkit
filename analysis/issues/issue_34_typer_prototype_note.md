# Issue #34 Typer Prototype Note

## Scope

This note records the first Typer migration slice for issue `#34`:

- evaluate Typer on one low-risk public CLI
- preserve the existing console-script entry point
- avoid wider CLI churn until the maintenance benefit is clearer

## Why `climatology` was chosen

`climate-toolkit-climatology` was a better prototype target than larger commands
such as weather-station or `fetch` because its CLI surface is comparatively
small and mostly scalar:

- required scalar options: `--location`, `--start-year`, `--end-year`, `--source`
- optional scalar options: `--format`, `--output`, `--output-dir`, `--model-workers`
- list-like values are already comma-separated strings (`--scenarios`, `--models`, `--exclude-models`)

That means Typer can preserve the existing flag spellings without inventing a
new repeated-option contract for list handling.

## Prototype decisions

- keep console-script name unchanged:
  - `climate-toolkit-climatology`
- keep module entry point unchanged:
  - `climate_tookit.climatology.long_term_climatology:main`
- move parsing/help to Typer
- keep execution logic in a separate `_run_climatology_cli(...)` helper
- disable Typer shell-completion flags in help for now with `add_completion=False`
- keep the CLI as a single-command root surface, not a new command tree

## What this demonstrates

- Typer can improve help rendering without forcing a new subcommand structure
- we can preserve existing long option names
- we can keep `main()` as the stable console-script entry point while internally
  delegating parsing to Typer

## Current limits

This prototype does **not** prove that every current CLI should move to Typer
unchanged. In particular, commands that currently depend on `argparse`
multi-value patterns such as `nargs="+"` need a deliberate compatibility
strategy before migration.

## Expansion guidance

If Typer migration continues, next candidates should be commands with:

- scalar option-heavy interfaces
- clear separation between parsing and compute/report logic
- no hidden dependence on `argparse`-specific grouping semantics

Likely better next targets than weather-station CLIs:

- `compare_datasets`
- selected ensemble wrappers only after list-option behavior is reviewed

## Reference points

- Typer PyPI release page: latest stable `0.26.7`, released June 3, 2026, Python `>=3.10`
- Typer docs: single-command apps and generated help behavior
