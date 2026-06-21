# Project Instructions

Primary architecture reference:

- `analysis/package_architecture_summary.md`

Use that file as current-state source-of-truth for:

- package module graph
- stable public API surface
- workflow layering
- source-routing reality
- cache and persistence model

When making architectural changes, update:

1. `analysis/package_architecture_summary.md`
2. relevant README sections
3. any issue/design memo directly affected

Architectural change means any change to:

- stable top-level exports
- CLI entry points
- module ownership or dependency direction
- source/backend routing
- cache layout or persistence behavior
- weather-station integration path
- compare-periods or climate-statistics payload contracts

Avoid writing new architecture notes that duplicate this file unless:

- note is narrow topic-specific deep dive, or
- note is issue-specific investigation

If deep-dive note created, link back to architecture summary.

