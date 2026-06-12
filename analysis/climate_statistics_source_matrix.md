# climate_statistics.statistics source matrix

Module: `climate_tookit.climate_statistics.statistics`

Test window used for historical sources:
- location: `-1.286,36.817` (Nairobi)
- fixed season: `03-01:05-31`
- years: `2018-2019`

Test window used for NEX-GDDP:
- location: `-1.286,36.817`
- fixed season: `03-01:05-31`
- years: `2050-2051`
- model: `MRI-ESM2-0`
- scenario: `ssp245`

## Live results

| source | status | notes | output |
|---|---|---|---|
| `era_5` | pass | daily source; fixed-season stats sensible | `analysis/stress_stats_era5.json` |
| `agera_5` | pass | daily source; fixed-season stats sensible | `analysis/stress_stats_agera5.json` |
| `auto` | pass | now follows `era_5 -> agera_5 -> chirps+chirts` fallback, aligned with `seasons.py` intent | `analysis/stress_stats_auto.json` |
| `chirps` | pass with fallback | precip-only source; module injects `tmax=25`, `tmin=15` by design | `analysis/stress_stats_chirps.json` |
| `nasa_power` | pass | direct API source; full temp/precip path works | `analysis/stress_stats_nasa_power.json` |
| `nex_gddp` | pass | multi-year fixed-season run works; cache-hit path verified | `analysis/stress_stats_nex_gddp.json` |
| `chirps+chirts` | clean reject | valid paired-source concept, but this 2018-2019 run is unavailable because CHIRTS daily coverage ends in 2016 | `analysis/stress_stats_chirps_chirts.json` |
| `terraclimate` | clean reject | monthly-cadence source; not valid for daily ET0 / season-window statistics | `analysis/stress_stats_terraclimate.json` |
| `imerg` | clean reject | precip-only source; not supported in current single-source interface, but scientifically valid if paired with temp source | `analysis/stress_stats_imerg.json` |
| `chirts` | clean reject (single-source) | temp-only source; only useful as precip-paired input, and daily coverage ends in 2016 | n/a |

## Key findings

1. `auto` was inconsistent with `seasons.py`.
   It used to route straight to `chirps+chirts`, which breaks for post-2016 windows because CHIRTS daily ends in 2016.

2. `chirps+chirts` failure in 2018-2019 is expected from dataset coverage, not random fetch instability.
   Official Earth Engine CHIRTS daily catalog shows availability `1983-01-01` to `2016-12-31`:
   <https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRTS_DAILY>

3. `terraclimate` is structurally wrong for this module.
   It is monthly in local source config, while `statistics.py` computes daily ET0, daily water balance, and daily fixed/auto season windows.

4. `imerg`, `chirps`, and `chirts` need explicit pairing logic if they should be handled cleanly here.
   Current module logic is mostly single-source daily-season-statistics logic, not a general precip-source + temp-source composition interface.

## Code changes made during this pass

- `statistics.py`
  - added source compatibility guards for `terraclimate`, `imerg`, `chirts`, and post-2016 `chirps+chirts`
  - changed `auto` to try `era_5`, then `agera_5`, then `chirps+chirts`
  - wrapped fetch failures into clean error payloads
  - made CLI save error reports cleanly and exit nonzero instead of dumping tracebacks

- tests
  - added `tests/test_statistics_source_policy.py`
