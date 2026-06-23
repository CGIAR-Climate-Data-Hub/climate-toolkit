# Issue #34 Typer Evaluation Decision Memo

## Scope

This memo records evaluation outcome for issue `#34`:

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

## New evidence after prototype

Follow-up work in issue `#68` exposed one important risk:

- Typer-backed CLI modules can fail at import time in stale or partial
  environments if `typer` is missing, even when core analysis code is fine

Mitigation added for `climate-toolkit-climatology`:

- keep `main()` as stable wrapper
- use Typer when installed
- fall back to `argparse` in degraded environments

This reduced operational risk for prototype command, but also argues against
fast wide migration until common fallback pattern is deliberate and shared.

## Current limits

This prototype does **not** prove that every current CLI should move to Typer
unchanged. In particular, commands that currently depend on `argparse`
multi-value patterns such as `nargs="+"` need a deliberate compatibility
strategy before migration.

Commands with larger migration risk include:

- weather-station CLIs with dense option surface and selection modes
- `fetch` and batch helpers with repeated-site / repeated-variable patterns
- ensemble wrappers with list-heavy options and runtime-specific progress output

## Backward compatibility strategy

Current public contract to preserve:

- console-script names in `pyproject.toml` stay unchanged
- stable module entrypoints stay `...:main`
- long option spellings should remain unchanged unless migration note says
  otherwise
- no forced move to subcommand trees for existing single-command tools

If Typer migration continues, each command should satisfy all of:

1. keep existing console-script name
2. keep `main()` as stable package/script entrypoint
3. preserve existing long option names
4. add tests for `--help`, invalid-argument behavior, and output path behavior
5. decide whether degraded env needs `argparse` fallback or hard dependency
6. avoid rewriting compute logic and CLI logic in same PR

## Decision

Current decision:

- do **not** migrate whole CLI family now
- keep mixed approach
- allow gradual Typer adoption only for isolated, scalar-option-heavy commands
- require explicit compatibility tests and migration notes per command

Near-term recommendation:

- keep `climate-toolkit-climatology` as reference prototype
- defer broader migration until packaging/docs/tooling work is stable
- revisit next on one low-risk command only if maintenance pain from
  `argparse` is concrete, not hypothetical

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
