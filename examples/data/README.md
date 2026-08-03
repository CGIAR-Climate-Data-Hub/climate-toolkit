# ERA LTE data

## `unique_ltes.csv`

The real ERA **unique LTEs registry** — one row per Long-Term Experiment
site/code, with coordinates and study years for 241 unique sites.

- **Source:** [CIAT/ERA_dev](https://github.com/CIAT/ERA_dev) —
  `data_entry/long_term_experiments/unique.ltes.csv`
  (linked by @Rwema25 in issue #141).
- **Format (as published):** semicolon-delimited, cp1252-encoded, with trailing
  spaces in some headers. `examples/era_lte_workflow.py` reads it as-is
  (`load_sites` sniffs the delimiter and encoding and tidies the header).
- **What it has:** `LTE.ID, Site.ID, Code, Year.start, Year.end, Latitude,
  Longitude` (plus notes/treatments/DOI metadata).
- **What it lacks:** season windows and yields. So sites run in **auto-season**
  mode — climate context per site, without the toolkit-vs-reported comparison.

For the fuller comparison (season windows + treatment + yield), use a compiled
`lte_summary` table exported from the ERA R workflow in issue #141, e.g.:

```bash
python examples/era_lte_workflow.py lte_summary.csv --source nasa_power
```
