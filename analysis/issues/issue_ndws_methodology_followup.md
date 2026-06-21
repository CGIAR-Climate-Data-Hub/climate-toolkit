Title: Review NDWS methodology, calibration, and user-facing interpretation

Summary

`NDWS` is now computed in `calculate_hazards.hazards` from running soil-water balance days where `ERATIO < 0.5`, following current Adaptation Atlas-inspired implementation. Live fixed-window tests suggest metric may be methodologically harsh or easy to misread, especially when applied across broad fixed windows that include dry shoulder periods.

Why this needs follow-up

- Metric is not obviously broken in code, but outputs deserve methodological review before treating as decision-ready.
- Current implementation uses generic soil defaults:
  - `soilcp=100`
  - `soilsat=100`
  - `kc=1.0`
- Fixed-window runs count stress across full window, not only crop-active core season.
- Users may interpret `NDWS` as crop-season drought severity, while current implementation is closer to "days with strong water stress under generic soil assumptions across chosen analysis window".

Evidence from live Nairobi fixed-window runs

Location:
- Nairobi `(-1.286, 36.817)`

Command family:
- `climate_tookit.calculate_hazards.hazards ... --fixed-season "03-01:06-30,10-01:12-31" --source auto`
- `climate_tookit.climate_statistics.statistics ... --fixed-season "03-01:06-30,10-01:12-31" --source auto`

Representative outputs:

- 2018 long rains fixed window:
  - rainfall `616.2-616.7 mm`
  - `NDD=29`
  - `NDWS=59`
  - `stress_ratio=0.803` in `climate_statistics`

- 2019 long rains fixed window:
  - rainfall `299.5 mm`
  - `NDD=51`
  - `NDWS=104`
  - `stress_ratio=0.852` in `climate_statistics`

- 2019 short rains fixed window:
  - rainfall `478.0 mm`
  - `NDD=17`
  - `NDWS=40`
  - `stress_ratio=0.435` in `climate_statistics`

Observations

- High `NDWS` values can appear even when rainfall totals are not obviously catastrophic.
- Part of this may be legitimate season structure.
- Part may come from fixed windows including dry shoulders before/after core rainy period.
- In humid fixed-window contexts, `crop_active` NDWS can currently fall back all the way to `full_window`
  because the internal ETO detector hits its perhumid guard and returns no sub-season at all.
- `hazards.py` and `climate_statistics.statistics` both reflect water stress, but with different formulations:
  - `hazards.py`: running soil-water hazard count (`NDWS`)
  - `climate_statistics.statistics`: daily `precip - ET0` balance summary and `stress_ratio`
- These are related but not interchangeable, and current outputs do not explain distinction clearly.

New finding from humid-site replay

- South Nigeria `(4.8156, 7.0498)` with fixed window `03-01:10-31`:
  - `full_window NDWS`: `7`, `6`, `28` across 2018-2020
  - `crop_active NDWS`: unchanged, because no ETO sub-season was returned
- Offline replay from cache showed this is not an open-season handling bug.
- The blocker is the internal detector guard:
  - `Perhumid location (annual rain=2218mm, low-rain months=0, rainy days=224). No clear onset/cessation.`
- Package behavior has now been improved so this reason is surfaced in
  `water_balance_methodology.warnings` instead of only reporting a generic
  "no closed ETO sub-season" fallback.

Questions to resolve

1. Should `NDWS` be computed over full fixed window, or only over detected crop-season / ETO sub-season?
2. Are default `soilcp`, `soilsat`, and `kc=1.0` too generic for user-facing hazard labels?
3. Should crop-specific or stage-specific coefficients be introduced later?
4. Should `NDWS` hazard thresholds be recalibrated for current implementation and chosen windows?
5. Should UI/CLI wording explicitly distinguish:
   - `NDWS` = model-based water-stress days
   - `stress_ratio` = share of days with negative simple water balance
6. Should outputs warn when `NDWS` is computed on broad fixed windows that include likely shoulder periods?

Suggested next steps

- Keep current implementation for now, but document as provisional / needs calibration review.
- Add explanation in docs/help that `NDWS` depends on chosen window and generic soil assumptions.
- Compare results on:
  - full fixed window
  - ETO sub-season only
  - several wetter and drier African / Andean sites
- Check Adaptation Atlas reference implementation more closely for:
  - intended temporal window
  - expected soil assumptions
  - any crop-specific calibration

Scope

Methodology / interpretation issue, not confirmed code defect.

Current progress

- user-facing labels in `climate_statistics.statistics` have been improved from
  internal wording like `shared_root_zone` to clearer `crop_model`
- compact outputs now emit an explicit note that `NDWS`, `NDWL0`, and `WRSI`
  are custom crop-water-balance metrics, not standard `xclim` / ETCCDI
  indicators
- `compare_periods.periods` now surfaces the same distinction in terminal
  output

That means the immediate risk is now more about calibration and interpretation
than silent mislabelling.
