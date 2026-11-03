# ERA × Climate Toolkit — command reference

All commands are **credential-free** (they default to NASA POWER). Run them from
the repository root, inside the project environment.

## 0. Setup (once)

```bash
git clone https://github.com/CGIAR-Climate-Data-Hub/climate-toolkit.git
cd climate-toolkit
uv sync                    # or: pip install -e .
```

**Already have a clone? Make sure it's the latest `main` first** (many fixes here
are recent). If commands behave differently than this guide, this is usually why:

```bash
git remote -v              # should point at CGIAR-Climate-Data-Hub/climate-toolkit
git status                 # commit/stash any local edits, or they block the pull
git checkout main
git pull
```

Prefix commands with `uv run` (e.g. `uv run python examples/...`) if you use `uv`
and haven't activated the venv. Two scripts need one extra package:
`pip install ijson` (only for `era_extract_site_out.py`); matplotlib ships with the
project (for the plot scripts).

### Data files

| File | How to get it |
|---|---|
| `examples/data/unique_sites_for_toolkit.csv` | already in the repo (126 sites, seasons) |
| `lte_final.csv` | public — **auto-downloaded** by the §4–6 scripts if missing. To fetch it yourself: `python examples/era_fetch_data.py` (Windows/macOS/Linux), or manually (see below). |
| `lte_summary_expanded.csv` | **not in the repo and no download URL** — it's a file the ERA team shares. You must place it in the folder you run from (or pass its full path). Only §3 needs it; everything else uses the two files above. |

> **`ERA input CSV not found`?** The path you passed isn't in the current
> folder. Either `cd` to where the file is / pass its full path, or — if it's
> `lte_summary_expanded.csv` that you don't have — use the public `lte_final.csv`
> with §4 (validation) and §5–6 (yield vs climate) instead. Note `era_lte_workflow.py`
> reads the `lte_summary`/`unique_sites` schema, **not** `lte_final.csv` — for
> `lte_final.csv` use the `era_final_*` / `era_yield_*` scripts.

**Manual download of `lte_final.csv`** (if you'd rather not use the helper):

```bash
# macOS / Linux
curl -sL https://raw.githubusercontent.com/ERAgriculture/LTEs/main/data/lte_final.csv -o lte_final.csv
```
```powershell
# Windows PowerShell — `curl` is an alias for Invoke-WebRequest, so use one of:
curl.exe -L https://raw.githubusercontent.com/ERAgriculture/LTEs/main/data/lte_final.csv -o lte_final.csv
Invoke-WebRequest https://raw.githubusercontent.com/ERAgriculture/LTEs/main/data/lte_final.csv -OutFile lte_final.csv
```

---

## Quick start — these work from a fresh clone (no extra files)

Do these three first. They use only the bundled sites and the **public**
`lte_final.csv` (auto-downloaded on first use) — nothing you have to obtain
separately. On Windows, use backslashes (`examples\...`).

```bash
# 1) list the bundled ERA sites (instant, no network)
python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --list-sites

# 2) validation — toolkit rainfall vs ERA's own value (auto-downloads lte_final.csv)
python examples/era_final_validate.py lte_final.csv --source nasa_power --limit 30 --out era_final_compare.csv
python examples/era_plot.py era_final_compare.csv --out era_validation.png

# 3) yield vs toolkit climate for one site (auto-downloads lte_final.csv)
python examples/era_yield_analysis.py lte_final.csv --site "Gourton" --out era_gourton.csv
python examples/era_yield_plot.py era_gourton.csv --site "Gourton" --out era_gourton_trends.png
```

> ⚠️ **Don't start with the `lte_summary_expanded.csv` command (§3).** That file
> is the ERA team's compiled table — it is *not* in the repo and has no download
> URL, so that command fails unless you already have the file on disk. Everything
> above needs no such file.

The sections below break these down and add the multi-site view.

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

Point the same workflow at the expanded table (has yield + reported rainfall).
**Requires the `lte_summary_expanded.csv` file in your working folder** (see the
data-files note above) — if you don't have it, skip to §4–6, which use the public
`lte_final.csv`.

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

Everything above is a thin wrapper over importable functions — you can drive it
from a notebook or script and get pandas objects back.

**The core toolkit** works from a plain install, imported anywhere:

```python
import climate_toolkit as ct
from datetime import date

# daily climate data -> pandas DataFrame
df = ct.fetch_climate_data(source="nasa_power", location_coord=(-1.286, 36.817),
                           date_from=date(2020, 1, 1), date_to=date(2020, 12, 31))

# seasonal climatology / water balance -> dict
stats = ct.analyze_climate_statistics(location_coord=(1.019, 35.0),
                                      start_year=2018, end_year=2020, source="nasa_power")
```

`import climate_toolkit as ct` exposes: `fetch_climate_data`,
`analyze_climate_statistics`, `evaluate_hazards`, `compare_climate_periods`,
`compare_climate_sources`, `download_station_data`, `compare_station_to_grids`,
`run_pipeline`.

**The ERA workflow** functions live in `examples/` (they ship with the repo, not
the installed wheel), so add the repo folder to the path, then import:

```python
import sys
sys.path.insert(0, "/path/to/climate-toolkit")     # your repo folder

from examples.era_lte_workflow import load_sites, select_sites, run
sites  = load_sites("examples/data/unique_sites_for_toolkit.csv")
subset = select_sites(sites, site_ids=["Awassa", "Samaru"])   # or None = all
df     = run("examples/data/unique_sites_for_toolkit.csv",
             source="nasa_power", site_ids=["Awassa"])         # -> pandas DataFrame
```

**Ready-made demo** of that pattern:

```bash
python examples/era_lte_as_library.py --site "Awassa" --limit 5
```

## Open any PNG

```bash
open era_gourton_trends.png     # macOS   (Linux: xdg-open · Windows: start)
```
