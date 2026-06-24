## Issue #29 TAI method note

Current conclusion:

- `TAI` should remain **unimplemented** until the package names the exact index and
  fixes the PET basis, aggregation surface, and threshold provenance.

Why this remains blocked:

- the repo comment history and Sammy issue context point toward a
  **Thornthwaite moisture-deficit style aridity index**
- local `xclim` only provides `aridity_index(pr, pet)`, which is a
  **UNEP-style `P / PET` ratio**
- those are **not interchangeable metrics**

## What we verified

### 1. `xclim` is not a drop-in `TAI`

Local installed `xclim.indices.aridity_index` is documented as:

- ratio of total precipitation over potential evapotranspiration
- classification in the `hyperarid` to `dry subhumid` UNEP-style framing
- wetter conditions have **higher** values

Implication:

- `xclim.aridity_index` is useful if we later want a separate
  **UNEP aridity ratio**
- it should **not** be exposed as the toolkit's intended Thornthwaite-style `TAI`

### 2. Current toolkit PET path does not settle the method

Current package drought/water-balance path already has useful components:

- `climate_tookit.climatology.spei.prepare_monthly_climatic_water_balance(...)`
  aggregates monthly precipitation and monthly ET totals
- when ET is not supplied, that path derives daily `ET0_mm_day`
  from `season_analysis.add_et0(...)`
- current metadata explicitly labels that derived path as
  `season_analysis.add_et0_hargreaves`

Implication:

- current package backbone is **Hargreaves reference ET0**, not a named
  Thornthwaite PET implementation
- that may still be useful later, but it is a **method choice** and should not be
  silently treated as equivalent to Thornthwaite PET

### 3. Thornthwaite-family naming is overloaded

Secondary references checked during this issue pass separate at least two
 commonly conflated ideas:

- Thornthwaite climate-classification aridity / humidity indices based on
  water deficit or surplus relative to PET
- UNEP / dryland-style aridity ratio `P / PET`

In practice this means a generic public metric name like `tai` is too ambiguous.

## Recommended package decision

### Public naming

- do **not** add a generic public metric named only `TAI`
- if implemented later, use an explicit name such as:
  - `thornthwaite_aridity_index`
  - and, separately if desired, `unep_aridity_index`

### First implementation target

- first home should be `climatology`, not `calculate_hazards`
- reason:
  - this is primarily a **climate context / dryness** metric
  - hazard-band outputs should only come after formula and threshold provenance are signed off

### Aggregation surface

- compute **monthly first**
- do **not** define this directly from daily values

Suggested workflow:

1. monthly precipitation total
2. monthly PET total using an explicitly named PET method
3. monthly deficit `max(PET - P, 0)`
4. aggregate to annual / climatology window
5. compute whichever Thornthwaite-style index the project explicitly adopts

### PET method choice must be explicit

Open options:

- implement a true Thornthwaite monthly PET path
- or adopt current Hargreaves-derived ET0 as a documented approximation / alternate method

But the package must not blur these into one unnamed `TAI`.

### Thresholds

- no validated threshold set was found in current code
- do not ship hazard classes until threshold source is documented and accepted

## Conservative implementation plan

1. Add a method design note first.
2. Decide whether the package wants:
   - Thornthwaite deficit index
   - UNEP `P / PET` ratio
   - or both under different names
3. Fix PET method and denominator definition.
4. Add one validated example calculation.
5. Only then expose CLI / hazard integration.

## Recommendation for issue status

- keep `#29` open until:
  - metric name is fixed
  - PET method is fixed
  - aggregation definition is fixed
  - threshold provenance is fixed
