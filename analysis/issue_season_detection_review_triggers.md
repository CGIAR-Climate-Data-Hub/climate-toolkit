# Issue Draft: Add Season-Detection Review Triggers and Prompt Logic

## Summary

Add explicit review-trigger logic for season detection so the toolkit can distinguish between:

- auto-detection is usable
- auto-detection is questionable
- auto-detection is not suitable and should trigger a user decision

This is needed because the current outputs can represent very different failure or ambiguity modes:

- no seasons detected
- some years missing seasons
- many years missing seasons
- highly inconsistent onset dates
- highly inconsistent season lengths
- humid/perhumid climates with no clear onset-cessation structure
- transitional zones where windows split or merge

## Problem

Right now the package can:

- detect seasons
- fail to detect seasons
- skip humid/perhumid cases
- warn when LTM coverage is short

But it does not yet classify whether the season results are:

- reliable enough to use automatically
- unstable enough to warn
- unstable enough to require human review or fixed-date override

This matters because the same outward symptom (`no seasons detected`) can mean very different things:

- perhumid climate with genuinely no clear dry break
- weak data / unstable rainfall signal
- only some years are problematic
- all years are problematic

## Proposed Output Fields

Add explicit detection-quality fields such as:

- `season_detection_status = ok | warn | prompt_required`
- `season_detection_reasons = [...]`
- `human_review_recommended = true | false`
- `calendar_override_recommended = true | false`

## Proposed Trigger Classes

### 1. Hard prompt trigger

Prompt user for:

- fixed dates
- calendar preset
- or continue anyway

Trigger if any of:

- no seasons detected for all years
- humid/perhumid case with no clear onset-cessation
- any target year has zero seasons while others have seasons
- detected seasons in fewer than 60% of expected years
- year-to-year season counts cannot be aligned into stable LTM windows
- onset-date standard deviation > 30 days
- season-length standard deviation > 30 days
- strong split/merge behavior across years

### 2. Soft prompt / review warning

Proceed, but warn and recommend review.

Trigger if any of:

- detected seasons in 60–80% of expected years
- onset-date standard deviation 15–30 days
- season-length standard deviation 15–30 days
- regime flips across years (`unimodal`, `bimodal`, `erratic`, `transitional`)
- one long season shows internal double-peak structure
- season_count differs moderately across years but remains partly alignable

### 3. No prompt

Proceed automatically if:

- season counts stable across years
- no missing season years
- onset variability modest
- cessation variability modest
- season-length variability modest
- no major morphology ambiguity

## Quantitative Diagnostics To Compute

For each season slot / year group:

- `n_years_expected`
- `n_years_detected`
- `season_count_distribution`
- `onset_mean_doy`
- `onset_sd_days`
- `cessation_mean_doy`
- `cessation_sd_days`
- `length_mean_days`
- `length_sd_days`
- `regime_distribution`

Optional later:

- `season_morphology_distribution`

## Important Distinctions

The logic should explicitly distinguish:

### A. No season detected

Potential causes:

- perhumid climate
- very weak rainfall seasonality
- poor detection stability

### B. Some seasons missing

Potential causes:

- interannual variability
- threshold sensitivity
- transitional rainfall regime

### C. Seasons detected but inconsistent

Potential causes:

- onset instability
- split/merge behavior
- long season with double-peak internal structure

These should not all be treated the same.

## Suggested UX

When `prompt_required`:

Show something like:

> Auto season detection is not stable enough for reliable crop-window interpretation.

Then offer:

1. use fixed dates
2. use a crop-calendar preset
3. continue with auto-detected results anyway

When `warn`:

Show:

> Auto season detection completed, but year-to-year stability is weak. Review recommended.

## Humid / Perhumid UX

Perhumid climates should not just show empty season sections.

Instead:

- state clearly that onset-cessation analysis is not suitable
- recommend fixed windows or crop calendars if seasonal interpretation is still needed

## Relationship To Other Follow-Up Work

This issue should connect to:

- season morphology / transitional regime classification
- fixed-date override UX
- crop-calendar preset support

## Definition of Done

- season-detection quality status added
- hard and soft trigger rules implemented
- output clearly distinguishes missing vs unstable vs unsuitable season detection
- humid/perhumid cases recommend alternative workflow
- user can be prompted toward fixed dates or calendar presets when appropriate
