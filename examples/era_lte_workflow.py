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

    # Run the real shipped registry (241 sites, auto season) — first 5:
    python examples/era_lte_workflow.py examples/data/unique_ltes.csv --limit 5

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


def lte_to_fixed_season(row) -> str:
    """Build a toolkit ``fixed_season`` string from an LTE row's season windows.

    One season -> ``"MM-DD:MM-DD"``; two seasons -> ``"MM-DD:MM-DD,MM-DD:MM-DD"``.
    """
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


def run_site(row, source: str) -> list[dict]:
    """Run the toolkit for one LTE site, return per-season metrics.

    Uses ERA's own season window when present (``fixed_season``), otherwise
    falls back to auto season detection so the shipped registry CSV still runs.
    """
    kwargs = dict(
        location_coord=(float(row["lat"]), float(row["lon"])),
        start_year=int(row["start_year"]),
        end_year=int(row["end_year"]),
        source=source,
        verbose=False,
    )
    if has_season_windows(row):
        fixed = lte_to_fixed_season(row)
        kwargs["fixed_season"] = fixed
    else:
        fixed = None
    result = analyze_climate_statistics(**kwargs)
    # Echo the input context onto every row (site_id always; the rest when
    # present), so the output table stands on its own for analysis.
    context = {"site_id": row.get("site_id")}
    for field in CONTEXT_FIELDS:
        if field == "site_id" or field not in row:
            continue
        if not pd.isna(row.get(field)):
            context[field] = row[field]
    out = []
    for tk in seasonal_rows(result):
        record = {
            **context,
            "mode": "fixed" if fixed else "auto",
            "fixed_season": fixed,
            **tk,
        }
        if "reported_rain_mm" in row and not pd.isna(row.get("reported_rain_mm")):
            reported = float(row["reported_rain_mm"])
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
        wanted = [s.strip() for item in site_ids for s in str(item).split(",") if s.strip()]
        available = set(sites["site_id"].astype(str))
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
    for _, row in sites.iterrows():
        try:
            out_rows.extend(run_site(row, source))
        except Exception as exc:  # one bad site shouldn't stop the workflow
            print(f"[skip] {row.get('site_id')}: {exc}")

    frame = pd.DataFrame(out_rows)
    frame.to_csv(out_csv, index=False)
    print(f"wrote {out_csv} ({len(frame)} rows)")
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
        help="Run only this Site.ID. Repeatable and/or comma-separated "
        "(--site A --site B, or --site A,B). Default: all sites.",
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
