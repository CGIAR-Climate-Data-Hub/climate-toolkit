# ERA LTE data

Real ERA Long-Term Experiment data compiled by the ERA team (Rwema / Namita)
for use with `examples/era_lte_workflow.py`. No synthetic samples.

## `unique_sites_for_toolkit.csv` — recommended toolkit input

Per-site, toolkit-ready: `Site.ID, Latitude, Longitude, Study.Start, Study.End,
fixed_season` for ~126 real ERA sites.

- **`fixed_season`** is pre-built by the ERA compile, in month-name syntax:
  `Feb:May,Jun:Sep` (colon within a window, comma between windows). The workflow
  maps the ERA day qualifiers (confirmed with the ERA team): `d-` = Mid (15th),
  `e-` = Late (25th), `y-` = Early (5th); a bare month is the 1st (start) / last
  day (end); `NA` windows are dropped.
- Season-window rows run in **fixed-season mode** → the toolkit-vs-reported
  comparison. (This file has no yield; use the expanded table for that.)

```bash
python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --source nasa_power
```

## `lte_summary_expanded.csv` — full year-matched table (local, not committed)

The complete ERA compile: ~47.7k rows, one per `(treatment, year)`, with
`Treatment, P.Product, Yield, Out.Code.Joined (Crop Yield..t/ha), Site.MSP.S1,
Site.Start.S1/End.S1, Study.Start/End, Year`. This is the authoritative source
for **crop yield + treatment + reported rainfall**, year-matched via `Year`.

It's ~7 MB, so it is kept locally (repo root) rather than committed. Point the
workflow at it directly:

```bash
python examples/era_lte_workflow.py lte_summary_expanded.csv --source nasa_power
```

## `unique_ltes.csv` — raw ERA registry (241 sites)

The unedited ERA site registry (semicolon/cp1252). Coordinates + years only, no
season windows → runs in auto-season mode. Kept as a raw reference; prefer
`unique_sites_for_toolkit.csv` for real comparisons.
