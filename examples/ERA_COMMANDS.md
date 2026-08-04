# ERA × Climate Toolkit — command reference

All commands are **credential-free** (they default to NASA POWER). Run them from
the repository root, inside the project environment.

## 0. Setup (once)

```bash
git clone https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git
cd climate-toolkit
uv sync                    # or: pip install -e .
```

Prefix commands with `uv run` (e.g. `uv run python examples/...`) if you use `uv`
and haven't activated the venv. Two scripts need one extra package:
`pip install ijson` (only for `era_extract_site_out.py`); matplotlib ships with the
project (for the plot scripts).

### Data files

| File | How to get it |
|---|---|
| `examples/data/unique_sites_for_toolkit.csv` | already in the repo (126 sites, seasons) |
| `lte_final.csv` | `curl -sL https://raw.githubusercontent.com/ERAgriculture/LTEs/main/data/lte_final.csv -o lte_final.csv` |
| `lte_summary_expanded.csv` | the compiled table shared by the ERA team (place in repo root) |

---

## 1. List the sites in a file

```bash
python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --list-sites
```

## 2. Run the workflow — single / multiple / all sites

Uses ERA's season windows to compute per-season toolkit climate metrics.

```bash
# SINGLE site
python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --site "Awassa" --out single.csv

# MULTIPLE sites — one --site each (ERA names may contain commas; don't join them)
python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --site "Awassa" --site "Samaru" --out multi.csv

# ALL sites
python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --source nasa_power --out all_sites.csv
```

Add `--dry-run` (instant, shows the season mapping, no network) or `--limit 10`
(first N sites) to any run.

## 3. Full comparison with reported rainfall + crop yield

Point the same workflow at the expanded table (has yield + reported rainfall):

```bash
python examples/era_lte_workflow.py lte_summary_expanded.csv --source nasa_power --out full.csv
```

---

## 4. Validation — toolkit rainfall vs ERA's own `rain_rain_sum`

Like-for-like: the toolkit computes rainfall over ERA's exact growing-season
window and is compared to the value ERA itself computed. (Result to date:
r = 0.94 over 352 windows.)

```bash
python examples/era_final_validate.py lte_final.csv --source nasa_power --out era_final_compare_all.csv
python examples/era_plot.py era_final_compare_all.csv --out era_validation.png     # scatter
```

Use `--limit 60` for a quick sample first.

---

## 5. Yield vs toolkit climate — the trend figures

Two steps: build a year-matched table, then plot it.

```bash
# 5a. build the table (all sites, or one site)
python examples/era_yield_analysis.py lte_final.csv --site "Gourton" --out era_gourton.csv

# 5b. per-site trends: climate variable as bars, one yield line per treatment (5 panels)
python examples/era_yield_plot.py era_gourton.csv --site "Gourton" --out era_gourton_trends.png

# just one variable (single panel): tk_rain_total_mm | tk_rainy_days | tk_dry_days | tk_NDWS | tk_WRSI
python examples/era_yield_plot.py era_gourton.csv --site "Gourton" --variable tk_WRSI --out gourton_wrsi.png

# match a specific practice subset (e.g. the NT nitrogen rates)
python examples/era_yield_plot.py era_gourton.csv --site "Gourton" --treatments "NT 0N,NT 100N,NT 200N" --out gourton_NT.png
```

## 6. Combined multi-site view

One toolkit variable vs yield across several sites in one figure.

```bash
# build per-site tables first (repeat --site), then combine:
python examples/era_yield_analysis.py lte_final.csv --site "Makoka"  --out era_Makoka.csv
python examples/era_yield_analysis.py lte_final.csv --site "Nyabeda" --out era_Nyabeda.csv
python examples/era_yield_analysis.py lte_final.csv --site "Kouve"   --out era_Kouve.csv

python examples/era_yield_multisite.py era_gourton.csv era_Makoka.csv era_Nyabeda.csv era_Kouve.csv \
  --variable tk_rain_total_mm --out era_multisite.png

# or build one table spanning many sites in a single pass:
python examples/era_yield_analysis.py lte_final.csv --limit 400 --out era_many.csv
python examples/era_yield_multisite.py era_many.csv --variable tk_WRSI --out era_multisite_wrsi.png
```

`--variable` accepts `tk_rain_total_mm`, `tk_rainy_days`, `tk_dry_days`,
`tk_NDWS`, `tk_WRSI`. `--min-years N` skips sites with too few years.

---

## 7. Use it from Python (no CLI)

```bash
python examples/era_lte_as_library.py --site "Awassa" --limit 5
```

## Open any PNG

```bash
open era_gourton_trends.png     # macOS   (Linux: xdg-open · Windows: start)
```
