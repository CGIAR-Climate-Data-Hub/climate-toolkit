"""ERA LTE workflow — drive the Climate Toolkit with ERA's own season windows.

This is a *workflow built on the toolkit's public API*, not just a run over ERA
coordinates. For each ERA Long-Term Experiment (LTE) site it:

1. translates the LTE's reported season window(s) into the toolkit's
   ``fixed_season`` syntax (``"MM-DD:MM-DD"``, or two comma-separated windows),
2. runs :func:`climate_toolkit.analyze_climate_statistics` with that fixed
   season (ERA's season, *not* auto-detection), and
3. optionally compares the toolkit's seasonal rainfall against ERA's reported
   rainfall — the validation/benchmarking loop that motivates #110.

Input CSV contract
------------------
One row per LTE site-period, with columns (registry aliases in parentheses):

    site_id (Site.ID), lat (Latitude), lon (Longitude),
    start_year (Year.start), end_year (Year.end),          # required
    s1_start, s1_end            # optional season-1 window as month-day, "03-01"
    s2_start, s2_end            # optional second season
    reported_rain_mm            # optional ERA-reported seasonal rainfall
    fixed_season                # optional pre-built season, e.g. "Feb:May,Jun:Sep"

A pre-built ``fixed_season`` column (Rwema's ``unique_sites_for_toolkit.csv``)
is used as-is when present — see :func:`normalize_fixed_season` — taking
precedence over the ``s1_start``/``s1_end`` columns.

Two modes, chosen per row:

* **Fixed-season** (when ``s1_start``/``s1_end`` are present): the LTE's own
  season window is translated to the toolkit's ``fixed_season`` and compared
  against ``reported_rain_mm`` if given. Year-crossing seasons (end month before
  start month) are supported — the toolkit wraps them to the next year. Season
  windows come from ERA's ``Site.Start.S1`` / ``Site.End.S1`` (and S2) fields.
* **Auto** (no season columns): falls back to auto season detection, so ERA's
  shipped real registry ``examples/data/unique_ltes.csv`` (241 sites, lat/lon/
  years only) runs as-is.

Producing the enriched export
-----------------------------
The season windows and reported rainfall live in the ERA data tables, not the
shipped registry CSV. Namita Joshi's ``lte_summary.Rmd`` in the ERA repo builds
exactly the joined table needed (it stitches ``Site.Out``, ``Data.Out``,
``Times.Out`` and ``PD.Out`` on ``B.Code``). Export its result to CSV and this
workflow consumes it directly — the ERA-native column names are aliased:

    Site.LatD/Site.LonD -> lat/lon        Site.Start.S1/Site.End.S1 -> s1_start/s1_end
    Study.Start/Study.End -> start/end_year   Site.Start.S2/Site.End.S2 -> s2_start/s2_end
    Site.MSP.S1 (mean seasonal precip) -> reported_rain_mm   P.Product -> crop_name
    Treatment -> treatment                Yield -> reported_yield

``treatment``, ``crop_name`` and ``reported_yield`` are echoed onto every output
row so the toolkit's climate metrics can be lined up against the ERA-reported
outcome — the reason for compiling ``lte_summary`` in the first place.

Note ``Site.MSP.S1`` is ERA's long-term *mean* seasonal precipitation, so the
comparison is each toolkit season-year against the ERA seasonal mean.

Guides: https://github.com/ERAgriculture/LTEs (see ``lte_summary.Rmd`` and
``data/metadata.csv`` for the full field list).

Usage
-----
All examples are credential-free with ``--source nasa_power`` (the default).
The repo ships the real ERA registry, so these run out of the box — just swap
in a compiled ``lte_summary`` export when you want season windows + yields::

    # Run Rwema's real toolkit-ready ERA sites (season windows included):
    python examples/era_lte_workflow.py examples/data/unique_sites_for_toolkit.csv --limit 5

    # Discover the Site.ID values in the CSV (to pick with --site):
    python examples/era_lte_workflow.py era_lte.csv --list-sites

    # Preview the season mapping only, no network calls:
    python examples/era_lte_workflow.py era_lte.csv --dry-run

    # ALL sites (default — no --site / --limit):
    python examples/era_lte_workflow.py era_lte.csv --out era_lte_compare.csv

    # SINGLE site:
    python examples/era_lte_workflow.py era_lte.csv --site Kitale

    # MULTIPLE sites (repeat --site, or comma-separate):
    python examples/era_lte_workflow.py era_lte.csv --site Kitale --site Tamale
    python examples/era_lte_workflow.py era_lte.csv --site Kitale,Tamale

    # First N sites (handy for a quick demo); combines with --site:
    python examples/era_lte_workflow.py era_lte.csv --limit 5

From Python (as a library)
--------------------------
The same functions the CLI calls are importable — drive the workflow from a
notebook or script and get pandas objects back, no terminal needed::

    import sys; sys.path.insert(0, "/path/to/climate-toolkit")  # repo checkout
    from examples.era_lte_workflow import load_sites, select_sites, run

    sites = load_sites("lte_summary.csv")          # -> DataFrame (aliased cols)
    subset = select_sites(sites, site_ids=["Kitale", "Tamale"])  # or None = all
    df = run("lte_summary.csv", source="nasa_power", site_ids=["Kitale"])
    #   -> pandas DataFrame of toolkit metrics + ERA context, also written to CSV

``run_site(row, source)`` runs a single loaded row and returns the per-season
records if you want to build the frame yourself.
"""

from __future__ import annotations

import argparse
import calendar
import re

import pandas as pd

from climate_toolkit.climate_statistics import analyze_climate_statistics

COLUMN_ALIASES = {
    "Site.ID": "site_id",
    # Coordinates: the lte_summary export renames to Latitude/Longitude, but
    # accept the raw Site.Out names too.
    "Latitude": "lat",
    "Longitude": "lon",
    "Site.LatD": "lat",
    "Site.LonD": "lon",
    # Study duration.
    "Year.start": "start_year",
    "Year.end": "end_year",
    "Study.Start": "start_year",
    "Study.End": "end_year",
    # Season windows (Character date fields in the ERA Site.Out table).
    "Site.Start.S1": "s1_start",
    "Site.End.S1": "s1_end",
    "Site.Start.S2": "s2_start",
    "Site.End.S2": "s2_end",
    # ERA-reported mean seasonal precipitation -> ground truth for comparison.
    "Site.MSP.S1": "reported_rain_mm",
    # Crop, for per-site hazard/season context.
    "P.Product": "crop_name",
    # Agronomic context carried through to the output so climate metrics can be
    # lined up against the ERA-reported outcome (the point of the lte_summary
    # table): experimental treatment, its yield, and the yield's error.
    "Treatment": "treatment",
    "Yield": "reported_yield",
    "ED.Error": "yield_error",
    # Experiment identifiers and the outcome year the yield refers to.
    "LTE.ID": "lte_id",
    "Code": "code",
    "Time": "outcome_year",
    # ERA site climate normals + second-season rainfall, kept for context.
    "Site.MSP.S2": "reported_rain_s2_mm",
    "Site.MAP": "map_mm",
    "Site.MAT": "mat_c",
    # Planting window, useful alongside the season window.
    "Planting.Start": "planting_start",
    "Planting.End": "planting_end",
}

# ERA input columns echoed onto every output row (when present), in output
# order, so the comparison table is self-contained for downstream analysis —
# identifiers, location, study window, agronomic context, and site normals.
CONTEXT_FIELDS = (
    "site_id", "lte_id", "code", "lat", "lon", "start_year", "end_year",
    "crop_name", "treatment", "outcome_year", "reported_yield", "yield_error",
    "planting_start", "planting_end", "map_mm", "mat_c", "reported_rain_s2_mm",
)


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# ERA records soft season bounds like "Early-Mar" / "Mid-Jun" / "Late-Oct".
_QUALIFIER_DAY = {"early": 5, "mid": 15, "late": 25}

_SOFT_DATE_RE = re.compile(r"^(?:(early|mid|late)[-\s]*)?([a-z]+)\.?$", re.IGNORECASE)


def _last_day_of_month(month: int) -> int:
    """Last day of ``month``, using a non-leap year so February is 28."""
    return calendar.monthrange(2001, month)[1]


def parse_month_day(value, *, is_end: bool = False) -> str:
    """Normalize an ERA season boundary to zero-padded ``"MM-DD"``.

    Handles both the numeric forms (``"MM-DD"``, ``"M-D"``, ``"MM/DD"``,
    ``"MM.DD"``, 4-digit ``"MMDD"``, date-like objects) and ERA's *descriptive*
    season bounds recorded in ``Site.Start.S1`` / ``Site.End.S1``:

    * bare month  -> 1st of the month for a start, last day for an end
      (``"Mar"`` -> ``03-01``; ``"July"`` (end) -> ``07-31``)
    * ``Early-``  -> 5th   (``"Early-Mar"`` -> ``03-05``)
    * ``Mid-``    -> 15th  (``"Mid-Mar"``   -> ``03-15``)
    * ``Late-``   -> 25th  (``"Late-Jun"``  -> ``06-25``)

    ``is_end`` only affects bare month names. Raises ``ValueError`` for anything
    unparseable, so bad ERA rows fail loudly rather than silently mis-seasoning.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("season boundary is missing")

    if hasattr(value, "month") and hasattr(value, "day"):
        month, day = int(value.month), int(value.day)
    else:
        token = str(value).strip()
        if not token:
            raise ValueError("season boundary is missing")

        soft = _SOFT_DATE_RE.match(token)
        if soft and soft.group(2).lower() in _MONTHS:
            qualifier, month_name = soft.group(1), soft.group(2).lower()
            month = _MONTHS[month_name]
            if qualifier:
                day = _QUALIFIER_DAY[qualifier.lower()]
            else:
                day = _last_day_of_month(month) if is_end else 1
        else:
            parts = re.split(r"[-/.]", token)
            if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
                month, day = int(parts[0]), int(parts[1])
            elif re.fullmatch(r"\d{4}", token):
                month, day = int(token[:2]), int(token[2:])
            else:
                raise ValueError(f"unrecognized season boundary: {value!r}")

    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError(f"month-day out of range: {value!r} -> {month:02d}-{day:02d}")
    return f"{month:02d}-{day:02d}"


# Rwema's unique_sites_for_toolkit.csv abbreviates the ERA Early/Mid/Late day
# qualifiers to one letter (confirmed with the ERA team, #141):
#   d- = Mid (15th)   e- = Late (25th)   y- = Early (5th)
_SEASON_QUALIFIER = {"d": "Mid", "e": "Late", "y": "Early"}


def _resolve_season_qualifier(token: str) -> str:
    """Rewrite Rwema's abbreviated season qualifier to the ERA Early/Mid/Late form.

    ``unique_sites_for_toolkit.csv`` writes season bounds as month names with a
    one-letter day qualifier (``d-Mar``, ``e-May``, ``y-Feb``). Rewrite it to the
    ``Early-/Mid-/Late-`` prefix that :func:`parse_month_day` already maps to the
    5th / 15th / 25th. A bare leading ``-`` (e.g. ``-July``) or an unknown prefix
    is dropped, leaving a plain month (1st for a start, last day for an end).
    """
    tok = str(token).strip()
    m = re.match(r"^([A-Za-z])-(.+)$", tok)
    if m and m.group(1).lower() in _SEASON_QUALIFIER:
        return f"{_SEASON_QUALIFIER[m.group(1).lower()]}-{m.group(2).strip()}"
    return re.sub(r"^(?:[A-Za-z]+-|-)", "", tok).strip()


def normalize_fixed_season(value) -> str | None:
    """Convert a pre-built ``fixed_season`` string to the toolkit's MM-DD form.

    Accepts Rwema's month-name syntax (``"Feb:May,Jun:Sep"``, colon between a
    window's start and end, comma between windows) including the day qualifiers
    handled by :func:`_strip_season_qualifier`. ``NA`` windows are dropped.
    Returns ``None`` if nothing usable remains (so the caller can fall back).
    """
    windows = []
    for win in str(value).split(","):
        parts = win.split(":")
        if len(parts) != 2:
            continue
        start, end = _resolve_season_qualifier(parts[0]), _resolve_season_qualifier(parts[1])
        if not start or not end or start.upper() == "NA" or end.upper() == "NA":
            continue
        windows.append(f"{parse_month_day(start)}:{parse_month_day(end, is_end=True)}")
    return ",".join(windows) if windows else None


def _prebuilt_fixed_season(row):
    """Return the row's usable pre-built ``fixed_season`` (normalized), or None."""
    fs = row.get("fixed_season")
    if fs is None or (isinstance(fs, float) and pd.isna(fs)) or str(fs).strip() == "":
        return None
    return normalize_fixed_season(fs)


def lte_to_fixed_season(row) -> str:
    """Build a toolkit ``fixed_season`` string for an LTE row.

    Prefers a pre-built ``fixed_season`` column (Rwema's month-name syntax) when
    present; otherwise assembles one from the ``s1_start``/``s1_end`` (+ S2)
    season-window columns. One season -> ``"MM-DD:MM-DD"``; two ->
    ``"MM-DD:MM-DD,MM-DD:MM-DD"``.
    """
    prebuilt = _prebuilt_fixed_season(row)
    if prebuilt:
        return prebuilt
    s1 = (
        f"{parse_month_day(row['s1_start'])}"
        f":{parse_month_day(row['s1_end'], is_end=True)}"
    )
    s2_start, s2_end = row.get("s2_start"), row.get("s2_end")
    has_s2 = not (
        s2_start is None
        or s2_end is None
        or (isinstance(s2_start, float) and pd.isna(s2_start))
        or str(s2_start).strip() == ""
    )
    if has_s2:
        s2 = f"{parse_month_day(s2_start)}:{parse_month_day(s2_end, is_end=True)}"
        return f"{s1},{s2}"
    return s1


def has_season_windows(row) -> bool:
    """True if the row carries an S1 season window (enables fixed-season mode).

    ERA's shipped ``unique_ltes.csv`` is registry-only (no season windows), so
    the workflow falls back to auto season detection for it; an enriched export
    with ``s1_start``/``s1_end`` unlocks the fixed-season + comparison path.
    """
    if _prebuilt_fixed_season(row):
        return True

    def _present(key):
        val = row.get(key)
        return not (
            val is None
            or (isinstance(val, float) and pd.isna(val))
            or str(val).strip() == ""
        )

    return _present("s1_start") and _present("s1_end")


def _year(value):
    """Parse an ERA ``Year.start`` / ``Year.end`` cell into an int, or None."""
    try:
        return int(float(str(value).strip()[:4]))
    except (ValueError, TypeError):
        return None


# ERA's expanded table stores Yield in mixed units; the unit is encoded in
# Out.Code.Joined (e.g. "Crop Yield..kg/ha", "Crop Yield..t/ha DM..Mean").
_YIELD_UNIT_TO_T_HA = {"t/ha": 1.0, "mg/ha": 1.0, "kg/ha": 0.001}


def _normalize_yield_units(df: pd.DataFrame) -> pd.DataFrame:
    """Convert ``reported_yield`` to t/ha using the unit in ``Out.Code.Joined``.

    Rwema's ``lte_summary_expanded.csv`` reports ``Yield`` in whatever unit the
    source outcome used (t/ha, kg/ha, Mg/ha), so a raw column mixes scales.
    Normalize to t/ha where the unit is recognized; leave rows without a usable
    unit column untouched.
    """
    if "reported_yield" not in df.columns or "Out.Code.Joined" not in df.columns:
        return df

    def _factor(code):
        m = re.search(r"\.\.([A-Za-z/]+)", str(code))
        return _YIELD_UNIT_TO_T_HA.get(m.group(1).lower()) if m else None

    factor = df["Out.Code.Joined"].map(_factor)
    yields = pd.to_numeric(df["reported_yield"], errors="coerce")
    mask = factor.notna() & yields.notna()
    df.loc[mask, "reported_yield"] = yields[mask] * factor[mask]
    return df


def _drop_redundant_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Drop alias columns whose canonical target is already present.

    Several ERA names map to the same target (e.g. both ``Latitude`` and
    ``Site.LatD`` -> ``lat``). ``lte_summary`` emits only one of each, but if an
    export ever carried both — or already carried the canonical ``lat`` — the
    rename would produce duplicate columns. Keep the first claimant and drop the
    rest so that is impossible.
    """
    taken = {col for col in df.columns if col not in COLUMN_ALIASES}
    redundant = []
    for source, target in COLUMN_ALIASES.items():
        if source not in df.columns:
            continue
        if target in taken:
            redundant.append(source)
        else:
            taken.add(target)
    return df.drop(columns=redundant) if redundant else df


def _read_era_csv(csv_path) -> pd.DataFrame:
    """Read a real ERA export robustly, whatever shape it arrives in.

    The shipped registry (``unique_ltes.csv``) is semicolon-delimited and
    cp1252-encoded with trailing spaces in the header and empty trailing
    columns; a clean ``lte_summary`` export is comma/UTF-8. Sniff the delimiter,
    try UTF-8 then the Windows/Latin fallbacks, then tidy the header (strip
    whitespace, drop blank/``Unnamed`` columns) so the aliases match.
    """
    last_err = None
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            # sep=None + the python engine sniffs ',' vs ';' vs tab.
            df = pd.read_csv(csv_path, sep=None, engine="python", encoding=encoding)
            break
        except UnicodeDecodeError as err:
            last_err = err
    else:  # pragma: no cover - every ERA file decodes as one of the above
        raise last_err

    df.columns = [str(c).strip() for c in df.columns]
    keep = [c for c in df.columns if c and not c.startswith("Unnamed")]
    return df[keep].dropna(axis=1, how="all")


def load_sites(csv_path) -> pd.DataFrame:
    """Load an ERA LTE export or the shipped registry, applying name aliases.

    Only lat/lon/years are required; season windows are optional (see
    :func:`has_season_windows`). Handles both the messy real registry and a
    clean ``lte_summary`` export — see :func:`_read_era_csv`.
    """
    df = _read_era_csv(csv_path)
    df = _drop_redundant_aliases(df).rename(columns=COLUMN_ALIASES)
    df["start_year"] = df["start_year"].map(_year)
    df["end_year"] = df["end_year"].map(_year)
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["start_year"].notna() & df["end_year"].notna()]
    df = _normalize_yield_units(df)
    return df.reset_index(drop=True)


def seasonal_rows(result) -> list[dict]:
    """Flatten ``season_statistics`` into per (year, season) toolkit metrics."""
    rows = []
    for s in result.get("season_statistics", []):
        precip = s.get("precipitation") or {}
        wb = s.get("water_balance") or {}
        length = s.get("length_days")
        rainy = precip.get("rainy_days")
        rows.append(
            {
                "year": s.get("year"),
                "season_number": s.get("season_number"),
                "tk_rain_total_mm": precip.get("total_mm"),
                "tk_rainy_days": rainy,
                "tk_dry_days": (length - rainy)
                if (length is not None and rainy is not None)
                else None,
                "tk_NDWS": wb.get("NDWS"),
                "tk_WRSI": wb.get("WRSI"),
            }
        )
    return rows


def run_site(row, source: str, cache: dict | None = None) -> list[dict]:
    """Run the toolkit for one LTE site, return per-season metrics.

    Uses ERA's own season window when present (``fixed_season``), otherwise
    falls back to auto season detection so the shipped registry CSV still runs.
    Pass a shared ``cache`` dict to reuse the climate fetch across rows that
    resolve to the same location, period and season (see below).
    """
    lat, lon = float(row["lat"]), float(row["lon"])
    start_year, end_year = int(row["start_year"]), int(row["end_year"])
    fixed = lte_to_fixed_season(row) if has_season_windows(row) else None

    # The compiled table repeats a site across treatment/time rows, so the same
    # (location, period, season, source) fetch recurs many times. Cache the
    # toolkit result on that key and reuse it — the per-row ERA context still
    # varies below, only the expensive climate fetch is shared.
    cache_key = (lat, lon, start_year, end_year, fixed, source)
    if cache is not None and cache_key in cache:
        tk_rows = cache[cache_key]
    else:
        kwargs = dict(
            location_coord=(lat, lon),
            start_year=start_year,
            end_year=end_year,
            source=source,
            verbose=False,
        )
        if fixed:
            kwargs["fixed_season"] = fixed
        tk_rows = seasonal_rows(analyze_climate_statistics(**kwargs))
        if cache is not None:
            cache[cache_key] = tk_rows

    # Echo the input context onto every row (site_id always; the rest when
    # present), so the output table stands on its own for analysis.
    context = {"site_id": row.get("site_id")}
    for field in CONTEXT_FIELDS:
        if field == "site_id" or field not in row:
            continue
        if not pd.isna(row.get(field)):
            context[field] = row[field]
    out = []
    for tk in tk_rows:
        record = {
            **context,
            "mode": "fixed" if fixed else "auto",
            "fixed_season": fixed,
            **tk,
        }
        # Compare each toolkit season against ERA's mean seasonal precip for the
        # *same* season: Site.MSP.S1 for season 1, Site.MSP.S2 for season 2
        # (confirmed with the ERA team — MSP is seasonal, Site.MAP is annual).
        msp_field = "reported_rain_mm" if tk.get("season_number") == 1 else "reported_rain_s2_mm"
        if msp_field in row and not pd.isna(row.get(msp_field)):
            reported = float(row[msp_field])
            record["reported_rain_mm"] = reported
            if tk["tk_rain_total_mm"] is not None:
                record["rain_delta_mm"] = tk["tk_rain_total_mm"] - reported
        out.append(record)
    return out


def select_sites(sites, site_ids=None, limit=None):
    """Narrow the loaded frame to the requested Site.ID value(s), then N.

    ``site_ids`` accepts a list where each item may itself be comma-separated
    (``--site A --site B`` and ``--site A,B`` both work). ``None``/empty means
    all sites. Unknown IDs raise, so a typo fails loudly instead of running
    nothing. ``limit`` keeps the first N of whatever remains.
    """
    if site_ids:
        available = set(sites["site_id"].astype(str))
        # Real ERA Site.IDs contain commas ("AfricaRice, Fanaye"), so only
        # comma-split a value that isn't itself an exact Site.ID. For a
        # comma-named site, pass it as its own --site (repeatable).
        wanted = []
        for item in site_ids:
            item = str(item).strip()
            if item in available:
                wanted.append(item)
            else:
                wanted.extend(s.strip() for s in item.split(",") if s.strip())
        missing = [s for s in wanted if s not in available]
        if missing:
            raise SystemExit(
                f"--site: no such Site.ID {missing} (available: {sorted(available)})"
            )
        sites = sites[sites["site_id"].astype(str).isin(wanted)]
    if limit:
        sites = sites.head(limit)
    return sites.reset_index(drop=True)


def run(
    csv_path,
    source="nasa_power",
    out_csv="era_lte_compare.csv",
    limit=None,
    dry_run=False,
    site_ids=None,
):
    sites = select_sites(load_sites(csv_path), site_ids=site_ids, limit=limit)
    print(f"{len(sites)} ERA LTE site-periods")

    if dry_run:
        for _, row in sites.iterrows():
            if has_season_windows(row):
                try:
                    print(f"  {row.get('site_id')}: fixed_season={lte_to_fixed_season(row)!r}")
                except ValueError as exc:
                    print(f"  {row.get('site_id')}: [bad season window] {exc}")
            else:
                print(f"  {row.get('site_id')}: auto season detection (no season window)")
        return sites

    out_rows = []
    cache: dict = {}  # shared across rows so repeated site coords fetch once
    for _, row in sites.iterrows():
        try:
            out_rows.extend(run_site(row, source, cache=cache))
        except Exception as exc:  # one bad site shouldn't stop the workflow
            print(f"[skip] {row.get('site_id')}: {exc}")

    frame = pd.DataFrame(out_rows)
    frame.to_csv(out_csv, index=False)
    print(f"wrote {out_csv} ({len(frame)} rows)")
    print(f"climate fetches: {len(cache)} (deduplicated from {len(sites)} site-periods)")
    if "rain_delta_mm" in frame and frame["rain_delta_mm"].notna().any():
        deltas = frame["rain_delta_mm"].dropna()
        print(
            "toolkit vs ERA-reported rainfall — "
            f"bias={deltas.mean():.1f} mm | MAE={deltas.abs().mean():.1f} mm | n={len(deltas)}"
        )
    return frame


def main():
    parser = argparse.ArgumentParser(description="ERA LTE workflow on the Climate Toolkit.")
    parser.add_argument("csv", help="ERA LTE export CSV (see module docstring for columns)")
    parser.add_argument("--source", default="nasa_power", help="Climate source (default: nasa_power)")
    parser.add_argument("--out", default="era_lte_compare.csv", help="Output CSV path")
    parser.add_argument(
        "--site",
        action="append",
        default=None,
        metavar="SITE_ID",
        help="Run only this Site.ID. Repeatable (--site A --site B). A value "
        "that isn't itself a Site.ID is comma-split (--site A,B); ERA names that "
        "contain commas must each be their own --site. Default: all sites.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N sites")
    parser.add_argument(
        "--list-sites",
        action="store_true",
        help="Print the Site.ID values in the CSV and exit (use to pick --site).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show season mapping without fetching")
    args = parser.parse_args()

    if args.list_sites:
        for site_id in load_sites(args.csv)["site_id"].astype(str).drop_duplicates():
            print(site_id)
        return

    run(args.csv, args.source, args.out, args.limit, args.dry_run, site_ids=args.site)


if __name__ == "__main__":
    main()
