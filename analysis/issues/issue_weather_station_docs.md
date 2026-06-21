## Summary
Weather-station capabilities now span discovery, selection, download, validation against grid products, custom station-file ingestion, candidate review artifacts, caching, and historical-analysis overrides. Once workflow stabilizes, this needs one coherent user-facing documentation pass.

## Why
Current behavior is growing fast and is no longer self-evident from CLI help alone. Users need clear guidance on what each mode does, what inputs are required, what outputs are produced, and what methodological caveats apply.

## Documentation scope
- Explain station backends and selection modes: `auto`, `ghcn_daily`, `gsod`, `custom_csv`; `list`, `specified`, `auto`.
- Explain `auto-1`, `auto-2`, `auto-n`, `auto-all`, and default guardrails.
- Document completeness filtering, distance filtering, elevation-difference filtering, and how/when guard relaxation happens.
- Document custom station-file support:
  - accepted file types (`csv`, `json`)
  - accepted column aliases
  - supported units and unit flags
  - minimum required columns
  - metadata fallbacks when station id/name/lat/lon/elevation missing
- Document candidate review artifacts:
  - CSV
  - JSON
  - HTML map showing anchor location vs nearby stations
- Document compare workflow:
  - station vs grid comparison intent
  - supported grid sources
  - interpretation of daily, monthly, seasonal, annual, and xclim-derived metrics
  - independence caveat for station-informed grid products
- Document historical-analysis override workflow where custom station variables can substitute into historical climate analysis.
- Document cache behavior and on-disk storage layout for station metadata, downloaded station files, normalized custom files, and review artifacts.
- Document current limitations and caveats:
  - sparse station coverage in some places
  - missing-variable handling
  - mixed-station / per-variable selection behavior
  - network/API failure modes
  - annual/xclim metric interpretation under gappy overlap

## Suggested deliverables
- README section for weather-station workflows
- dedicated docs page or wiki page
- 2-3 minimal worked examples:
  - discover nearby stations and save map
  - compare chosen station against grid products
  - run historical analysis with custom station precipitation and/or temperature override

## Timing
Do after weather-station workflows and CLI/API settle enough that docs will not immediately drift.

## 2026-06-21 progress

Delivered in current repo docs:

- expanded README weather-station quickstart and caveat section
- dedicated user-facing workflow page:
  - `docs/weather_station_workflows.md`

Now documented:

- backend choices
- selection modes
- `auto-1` / `auto-n` / `auto-all`
- compare `selection-strategy`
- default guardrails and completeness relaxation
- custom file inputs, aliases, metadata, and units
- candidate review artifacts and HTML map
- compare outputs and interpretation caveats
- historical override workflow
- cache layout and reuse behavior
- current limitations

Remaining follow-up, if wanted later:

- sync same content into project wiki
- add screenshots / rendered examples of candidate-review map and compare output
