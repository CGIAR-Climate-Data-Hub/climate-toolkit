# Issue Draft: Add Fixed-Date Overrides and Optional Crop-Calendar Presets

## Summary

Design the seasonal workflow so users can:

1. provide fixed season dates directly
2. optionally use crop-calendar presets
3. override any preset with local knowledge

The default should not assume a global crop calendar is locally correct.

## Why

Auto rainfall-season detection is useful, but not always appropriate for crop windows.

Problem cases:

- perhumid climates
- transitional unimodal/bimodal zones
- irrigated systems
- multiple cropping systems
- local cultivar differences
- management calendars that do not match rainfall onset exactly

So the workflow needs a clear hierarchy:

1. user override dates
2. project/local curated calendar
3. optional global preset
4. rainfall-based auto detection

## Recommendation

Default to fixed-date prompting before forcing a global crop-calendar answer.

Crop-calendar presets should be optional helpers, not authoritative defaults.

## Candidate Calendar Sources

### 1. AgMIP-GGCMI cropCalendars

Repo:

- [AgMIP-GGCMI/cropCalendars](https://github.com/AgMIP-GGCMI/cropCalendars)

What it is:

- R package for simulating climate-driven crop calendars

Repo README says it follows:

- Waha et al. (2012)
- Minoli et al. (2019)

Pros:

- explicit crop-calendar simulation approach
- climate-driven and projection-oriented
- relevant to GGCMI / AgMIP workflows

Cons:

- R-based
- simulated global/default logic, not necessarily local truth
- not ideal as an unquestioned default for end-user local agronomy

### 2. MIRCA-style global crop calendars

Potential use:

- static gridded planting / harvest dates

Pros:

- simple raster-like lookup idea
- easier to use as a preset layer

Cons:

- can be dated
- can miss local or recent management changes
- still coarse for many advisory contexts

### 3. Country / project curated calendars

Potential use:

- country-specific or project-specific crop window presets

Pros:

- often more locally meaningful
- easier to explain to users

Cons:

- patchy coverage
- may be inconsistent in format and provenance

## Proposed UX Order

### A. First choice: user-supplied fixed dates

Examples:

- `--fixed-season "03-01:06-30,10-01:12-31"`
- or crop-specific start / end windows

This should be the cleanest and most trusted path when the user knows the system.

### B. Second choice: curated preset

Use:

- local/project calendar if available
- country or subregional crop preset if available

### C. Third choice: global preset

Use:

- GGCMI-derived or MIRCA-like preset

But label clearly as:

- suggested default
- user-overridable

### D. Fourth choice: auto-detected rainfall season

Useful when:

- no fixed dates available
- no crop calendar available
- rainfall timing is a reasonable proxy

But it should not pretend to be a crop calendar.

## Needed CLI / API Options

Examples:

- `--fixed-season`
- `--crop maize`
- `--calendar-source ggcmi`
- `--calendar-source local`
- `--calendar-override`
- `--allow-auto-season-fallback`

## Suggested Runtime Behavior

If season detection is unstable or unsuitable:

Prompt user toward:

1. fixed dates
2. crop-calendar preset
3. continue with auto-detection anyway

If using a preset:

- print preset source
- print crop
- print whether preset is local/curated/global
- allow override

## Metadata To Preserve

- `calendar_mode = fixed | local_preset | global_preset | auto_detected`
- `calendar_source`
- `crop`
- `calendar_confidence`
- `user_override = true | false`

## Important Principle

Do not make global preset calendars the hidden default truth.

Use them as optional support, especially where:

- local agronomy is unknown
- season detection is not suitable
- the user wants a first-pass crop window

## Definition of Done

- fixed-date workflow is first-class
- crop-calendar preset workflow is optional and overridable
- runtime can route users to fixed dates when season detection is weak
- metadata records which route was used
- documentation explains difference between rainfall season and crop calendar
