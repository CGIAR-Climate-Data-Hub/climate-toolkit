# Issue Draft: Add Season Morphology and Transitional-Regime Classification

## Summary

Current season outputs use a coarse regime concept such as `unimodal` or `bimodal`, but this is not enough for transitional rainfall zones.

We need to distinguish:

- `year_regime` or site-year seasonal organization
- `season_morphology` or within-season internal structure

This is especially important where one long rainy season may contain two distinct peaks, or where a location flips between unimodal and bimodal behavior across years.

## Problem

At present:

- a year may be labeled from a simple regime classifier
- season detection may independently find one or two rainy windows
- these two methods can disagree

Even after fixing misleading display labels, the deeper methodological issue remains:

- one detected season may still contain two internal rainfall peaks
- transitional zones may not fit clean `unimodal` / `bimodal` categories

Examples of ambiguous cases:

- one long season with two clear peaks
- two weak seasons separated by a short dry break
- one main season plus a minor shoulder pulse
- year-to-year switching between unimodal and bimodal behavior

## Why This Matters

Important for:

- East African transitional rainfall zones
- highland and topographically complex areas
- seasonal interpretation for cropping calendars
- comparing historical vs projected changes in season organization
- avoiding false certainty in regime labels

If not handled well, outputs can mislead users into thinking:

- the year is cleanly unimodal when it is actually transitional
- two detected windows always mean a strongly bimodal rainfall regime
- one detected window always means a simple single-peak season

## Proposed Improvement

Separate two concepts explicitly.

### 1. `year_regime`

Coarse year-level seasonal organization.

Possible labels:

- `unimodal`
- `bimodal`
- `late_peak_unimodal`
- `erratic`
- `transitional`

### 2. `season_morphology`

Within-season internal structure for each detected season.

Possible labels:

- `single_peak`
- `double_peak`
- `multi_pulse`
- `flat`
- `erratic`
- `with_midseason_break`

## Suggested Metrics / Fields

For each detected season, calculate:

- `season_peak_count`
- `season_peak_dates`
- `season_peak_months`
- `season_peak_prominence`
- `intra_season_dry_break_days`
- `season_morphology`

For each year:

- `year_regime`
- `year_peak_count`
- `largest_peak_month`
- `secondary_peak_strength_ratio`
- `regime_confidence`

## Suggested Logic

### Year-level

Continue using broad peak/window logic for:

- annual organization
- number of rainy windows
- separation between windows

But add a `transitional` class where evidence is ambiguous.

### Season-level

Within each detected season:

1. aggregate rainfall to a smoother daily or dekadal signal
2. identify internal local peaks
3. assess peak separation and prominence
4. classify morphology

Example:

- one season, one dominant peak -> `single_peak`
- one season, two separated dominant peaks -> `double_peak`
- one season with a clear internal dry interruption -> `with_midseason_break`

## Output Changes

Instead of only:

- `Season 1`
- `Season 2`

show:

- `Year regime: transitional`
- `Season 1 morphology: double_peak`

or:

- `Year regime: bimodal`
- `Season 1 morphology: single_peak`
- `Season 2 morphology: single_peak`

## Use Cases

- East Africa long rains with embedded pulses
- zones between single- and double-season rainfall regimes
- climate-change cases where two windows merge into one broader season
- identifying whether projected changes affect onset/cessation only, or peak structure too

## Definition of Done

- year-level regime and season-level morphology are separate fields
- transitional years can be labeled explicitly
- each detected season can report internal peak structure
- outputs no longer imply that every season itself is `unimodal` or `bimodal`
- display and JSON outputs expose both `year_regime` and `season_morphology`

## Notes

This is a methodological enhancement, not just a display tweak.

The recent display patch removed misleading per-season `unimodal` labels when two seasons are detected in the same year, but a fuller transitional-zone interpretation still needs to be implemented.
