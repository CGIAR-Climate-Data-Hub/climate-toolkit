"""Drive the ERA LTE workflow from Python — no terminal, no credentials.

Companion to ``era_lte_workflow.py`` (the CLI). This shows the *same* workflow
used as a library: import the functions, hand them an ERA table, and get pandas
objects back. Everything here uses ``nasa_power``, which needs no Earth Engine
setup.

By default it runs on the **real** ERA registry shipped with the repo
(``examples/data/unique_ltes.csv`` — the ``unique.ltes.csv`` Rwema linked in
issue #141, 241 real LTE sites). That registry has coordinates and study years
but no season windows, so sites run in auto-season mode.

Run it as-is (first few real sites)::

    python examples/era_lte_as_library.py --limit 3

Point it at a compiled ``lte_summary`` export (adds season windows + yield, so
the treatment/yield/rainfall comparison columns appear)::

    python examples/era_lte_as_library.py --csv lte_summary.csv --site Kitale
"""

from __future__ import annotations

import argparse
import os
import sys

# Make the workflow importable when running from a repo checkout. (`import
# climate_toolkit` itself works from a plain install; the example *scripts*
# live in examples/, which ships with the repo rather than the wheel.)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from examples.era_lte_workflow import load_sites, run, run_site, select_sites

# Rwema's real toolkit-ready ERA sites (season windows included). See
# examples/data/README.md.
DEFAULT_CSV = os.path.join(REPO_ROOT, "examples", "data", "unique_sites_for_toolkit.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=DEFAULT_CSV,
                        help="ERA CSV (default: the shipped real registry)")
    parser.add_argument("--site", action="append", help="Site.ID(s) to run (default: all)")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N sites")
    parser.add_argument("--source", default="nasa_power", help="Climate source (default: nasa_power)")
    args = parser.parse_args()

    # 1) Load — reads the messy real registry (semicolon/cp1252) or a clean
    #    lte_summary export, and aliases the ERA-native column names.
    sites = load_sites(args.csv)
    print(f"load_sites -> {len(sites)} site-periods | {sites['site_id'].nunique()} unique sites")

    # 2) Select — single, several (list), all (site_ids=None), then first N.
    subset = select_sites(sites, site_ids=args.site, limit=args.limit)
    print(f"select_sites -> {len(subset)} rows")

    # 3a) One row at a time: run_site returns per-season records (dicts).
    records = run_site(subset.iloc[0], source=args.source)
    print(f"run_site(first row) -> {len(records)} season records")
    print("    columns:", list(records[0].keys()))

    # 3b) Or the whole selection at once: run() returns (and writes) a DataFrame.
    df = run(args.csv, source=args.source, site_ids=args.site, limit=args.limit,
             out_csv="era_lte_compare.csv")
    print(f"run(...) -> DataFrame {df.shape}")
    # Show whichever columns this table produced (yield/treatment only exist for
    # a compiled lte_summary export; the registry runs in auto-season mode).
    cols = [c for c in ("site_id", "treatment", "reported_yield", "year",
                        "fixed_season", "tk_rain_total_mm", "tk_WRSI", "rain_delta_mm")
            if c in df]
    print(df[cols].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
