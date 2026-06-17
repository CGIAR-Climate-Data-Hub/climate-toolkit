Title: Auto-detected season-slot baselines can mix incomparable seasons when yearly season counts differ

Summary

In auto-detect mode, downstream modules group and average seasonal outputs by `season_number`. That breaks semantic alignment when one year has one detected season and another year has two detected seasons. `season_number=1` then stops meaning one stable seasonal window and instead becomes "first detected season this year", which can represent different climatological seasons across years.

Cross-reference issue search summary

Checked open and closed issues before drafting:

- `#81` general climatology feedback: no issue for unstable auto-detected `season_number` semantics
- `#79`, `#73`, `#68` season/hazards feedback: no issue for LTM slot mixing across changing yearly season counts
- `#70`, `#78`, `#91`, `#92` compare-periods issues: different root causes

So this appears to be new issue, not duplicate.

Evidence

Live `season_analysis.seasons` auto run for Nairobi:

```bash
.venv/bin/python -m climate_tookit.season_analysis.seasons \
  --location="-1.286,36.817" \
  --start-year=2018 \
  --end-year=2019 \
  --source=auto \
  --no-save
```

Resolved final seasons:

- 2018:
  - Season 1: `2018-03-02 -> 2018-06-05`
- 2019:
  - Season 1: `2019-05-08 -> 2019-06-25`
  - Season 2: `2019-10-09 -> 2019-12-29`

Live `calculate_hazards.hazards` auto run on same site/window then produced:

- `2018` `season_number=1`, `total_seasons_per_year=1`
- `2019` `season_number=1`, `total_seasons_per_year=2`
- `2019` `season_number=2`, `total_seasons_per_year=2`

But `baseline_ltm.per_season[0]` still averages both `season_number=1` entries together:

- 2018 long rains
- 2019 long rains

and treats them as one comparable season slot, even though auto mode does not guarantee that `season_number=1` means same seasonal regime across all years.

Why this matters

This affects more than `hazards.py`.

Current slot-based grouping also appears in:

- `climate_tookit/calculate_hazards/hazards.py`
- `climate_tookit/climate_statistics/statistics.py`
- `climate_tookit/compare_periods/periods.py`
- likely ensemble wrappers that inherit same season-slot assumption

When yearly season counts differ, downstream LTM and comparison outputs can look precise while comparing non-like-with-like seasonal blocks.

Expected behavior

One of these should happen:

1. Auto-detected runs should refuse season-slot LTM/comparison summaries when yearly season counts are inconsistent.
2. Auto-detected runs should only aggregate after aligning seasons by stronger logic than raw `season_number`.
3. Output should at minimum warn clearly that slot-based baseline/comparison semantics are unstable for this run.

Actual behavior

Modules proceed with season-slot averaging/comparison as if slot identities were stable.

Suggested direction

- Add guard on auto-detected workflows:
  - inspect per-year `total_seasons_per_year`
  - if not constant across years, either:
    - return warning and skip LTM per-season comparisons, or
    - require fixed seasons for comparison-ready outputs
- Keep fixed-season workflows as preferred path for robust year-to-year / baseline comparisons

Scope

Method/aggregation correctness issue. Data fetch and season detection can still be individually correct.
