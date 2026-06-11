## Summary

The active placeholder `nex_gddp` backend is effectively location-invariant across very different sites.

In a five-site sanity matrix covering:

- Nairobi
- Niamey
- Addis Ababa
- Cusco
- Lodwar

the active 16-model ensemble returns almost identical historical annual precipitation, identical historical annual temperature, and the same peak precipitation month for every site.

So while the current placeholder backend does introduce scenario shifts (`historical` vs `ssp245` vs `ssp585`), it does **not** currently provide credible location-specific climate context.

This issue is present on:

- `origin/main`
- `origin/staging`

The active `nex_gddp.py` implementation on both branches uses the same synthetic generator structure.

## Issue search summary

Before drafting this, existing issues were checked to avoid duplicates.

Open issues reviewed:

- `#85` NEX-GDDP placeholder implementation still active on main and staging
- `#86` ensemble_hazards includes unsupported default scenario ssp370
- `#87` ensemble_hazards is not reliably importable under normal package execution
- `#88` ERA5 runtime path uses GEE while repo still exposes CDS-based ERA5 setup
- `#89` statistics and long_term_climatology silently disable preprocess pipeline under package import
- `#90` AgERA5 runtime uses generic GEE backend while agera_5.py remains a dead stub
- `#91` ensemble_periods uses future SSP for baseline instead of historical
- `#93` ensemble_statistics labels pre-2021 SSP runs as BASELINE by year alone

Related existing issue:

- `#85` tracks the root fact that active NEX-GDDP is still placeholder data

This new issue is narrower and evidence-driven: it documents one concrete failure mode of that placeholder backend, namely the lack of meaningful spatial differentiation across very different sites.

## How this was determined

This finding came from a code audit assisted by GPT-5.4 at medium reasoning effort and then manually verified with a repeatable local sanity harness.

Audit steps:

- inspected active `climate_tookit/fetch_data/source_data/sources/nex_gddp.py`
- noted that scenario effects are hard-coded, but no site-specific climatology terms are present beyond RNG seeding
- built a sanity harness over the active preprocess pipeline
- ran a 5-site × 3-scenario × 16-model ensemble matrix
- checked both scenario directionality and site realism

Artifacts produced during audit:

- `analysis/run_nex_sanity_matrix.py`
- `analysis/nex_sanity_matrix.md`
- `analysis/nex_sanity_matrix.json`

## Evidence

### Active placeholder backend uses mostly shared global structure

`climate_tookit/fetch_data/source_data/sources/nex_gddp.py` currently uses:

- fixed precipitation base: `3.5`
- fixed temperature bases: `26.0`, `16.0`
- fixed seasonal sine waves
- scenario-wide warming / precipitation multipliers
- model index perturbation

Location is included in the RNG seed:

```python
seed_str = f"{self.model}|{self.scenario}|{lat:.6f}|{lon:.6f}"
```

but there is no meaningful location-dependent climatology term comparable to elevation, latitude regime, or regional rainfall structure.

### Sanity matrix result

From `analysis/nex_sanity_matrix.md`:

| Site | Region | Historical precip (mm) | Historical Tavg (C) | Historical peak precip month | SSP245 Tavg | SSP585 Tavg |
|---|---|---:|---:|---:|---:|---:|
| Nairobi | East Africa bimodal | 1279.43 | 21.00 | 3 | 22.62 | 23.25 |
| Niamey | Sahel | 1280.33 | 21.00 | 3 | 22.61 | 23.25 |
| Addis Ababa | Ethiopian highlands | 1280.70 | 21.00 | 3 | 22.62 | 23.25 |
| Cusco | Andean highlands | 1279.74 | 21.00 | 3 | 22.61 | 23.25 |
| Lodwar | East Africa dryland | 1278.53 | 21.00 | 3 | 22.63 | 23.25 |

### Directional scenario checks pass, but realism checks fail

The harness found:

- scenario monotonicity passes everywhere
  - `historical < ssp245 < ssp585` for temperature
  - `historical > ssp245 > ssp585` for precipitation under current placeholder rules

but site realism checks fail:

- historical inter-site mean annual temperature spread: `0.0 C`
- historical inter-site mean annual precipitation spread: `2.17 mm`
- Addis Ababa cooler than Lodwar: `FAIL`
- Cusco cooler than Niamey: `FAIL`
- all five sites peak in same precipitation month: `3`

## Minimal repro

Run:

```bash
MPLCONFIGDIR=/private/tmp/mpl .venv/bin/python analysis/run_nex_sanity_matrix.py --output-prefix analysis/nex_sanity_matrix
```

Then inspect:

```bash
sed -n '1,220p' analysis/nex_sanity_matrix.md
```

Expected for a location-aware climate backend:

- large climatic differences across Andean highlands, Sahel, Ethiopian highlands, Nairobi, and Lodwar
- different annual precipitation totals
- different mean temperatures
- different seasonal peaks

Actual result under current placeholder:

- near-identical annual precipitation totals
- identical historical annual temperatures
- same peak precipitation month across all sites

## Why this matters

This limits usefulness for alpha testing:

- users may think location context is meaningful when it is not
- cross-site comparisons can appear more credible than they are
- African vs Andean site differences are effectively erased

This is especially important because one of the stated goals of the toolkit is to provide climate context for a location.

## Proposed fix

Short term:

- clearly document that active placeholder NEX output should not be used for cross-site realism checks
- surface this limitation wherever NEX-GDDP outputs are presented to users

Long term:

- replace placeholder generator with real NEX-GDDP retrieval

If placeholder data must remain temporarily:

- do not present it as if it captures real location-specific climatology
- add regression checks so obviously location-invariant behavior is not mistaken for production readiness
