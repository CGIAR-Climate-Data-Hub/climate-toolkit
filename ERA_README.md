# ERA LTE × Climate Toolkit — real comparison

Comparing the Climate Toolkit's seasonal rainfall against **real ERA Long-Term
Experiment** field records, using the authoritative tables compiled by the ERA
team (Rwema / Namita). No synthetic data. Everything credential-free (NASA POWER).

## The real ERA datasets

| File | What it is | Where |
|---|---|---|
| `examples/data/unique_sites_for_toolkit.csv` | 126 real sites, toolkit-ready, pre-built `fixed_season` | committed |
| `lte_summary_expanded.csv` | full year-matched table: ~47.7k rows with treatment, crop, yield, reported rainfall | local (7 MB, not committed) |
| `examples/data/unique_ltes.csv` | raw ERA registry (241 sites, no seasons → auto mode) | committed |

`unique_sites_for_toolkit.csv` gives the season/climate comparison;
`lte_summary_expanded.csv` adds **reported rainfall + treatment + crop yield**
(year-matched via its `Year` column).

## Run it — site scenarios

```bash
# list sites
uv run python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --list-sites

# SINGLE site
uv run python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --site "Awassa" --out single.csv

# MULTIPLE sites (one --site each; ERA names may contain commas — don't join them)
uv run python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv \
  --site "Awassa" --site "Samaru" --out multi.csv

# ALL sites
uv run python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --source nasa_power --out all_sites.csv
```

For the full comparison **with reported rainfall + yield**, point the same
commands at the expanded table:

```bash
uv run python examples/era_lte_workflow.py lte_summary_expanded.csv --source nasa_power --out full.csv
```

Add `--dry-run` (instant, no network) or `--limit 10` (quick sample) to any run.

## Season syntax

`unique_sites_for_toolkit.csv` carries a pre-built `fixed_season` in month-name
form (`Feb:May,Jun:Sep`). The workflow parses it, mapping the ERA day qualifiers
(confirmed with the ERA team): **`d-` = Mid (15th)**, **`e-` = Late (25th)**,
**`y-` = Early (5th)**; a bare month is the 1st (start) / last day (end), a
leading `-` is a plain month, and `NA` windows are dropped.

## Caveat on yield

The rainfall comparison is authoritative. Yields come straight from the ERA
`lte_summary_expanded.csv` (`Out.Code.Joined = Crop Yield..t/ha`), year-matched —
but the `Treatment` field is a compound ERA code, and yield-vs-climate inference
should still be reviewed with the ERA team.
