"""Drive the ERA LTE workflow from Python — no terminal, no credentials.

Companion to ``era_lte_workflow.py`` (the CLI). This shows the *same* workflow
used as a library: import the functions, hand them a compiled ``lte_summary``
table, and get pandas objects back. Everything here uses ``nasa_power``, which
needs no Earth Engine setup.

Run it as-is (it writes a tiny built-in sample and processes one site)::

    python examples/era_lte_as_library.py

Or point it at a real ERA ``lte_summary`` export::

    python examples/era_lte_as_library.py --csv lte_summary.csv --site Kitale
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

# Make the workflow importable when running from a repo checkout. (`import
# climate_toolkit` itself works from a plain install; the example *scripts*
# live in examples/, which ships with the repo rather than the wheel.)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from examples.era_lte_workflow import load_sites, run, run_site, select_sites

# A minimal slice of the compiled `lte_summary` schema (two treatment rows for
# one Kenyan LTE site) so this script runs with no external file.
SAMPLE_CSV = (
    "Site.ID,Latitude,Longitude,Study.Start,Study.End,"
    "Site.Start.S1,Site.End.S1,Site.MSP.S1,P.Product,Treatment,Yield,ED.Error\n"
    "Kitale,1.019,35.0,2018,2020,Mid-Mar,Late-Jun,520,Maize,Control,2.1,0.3\n"
    "Kitale,1.019,35.0,2018,2020,Mid-Mar,Late-Jun,520,Maize,Manure,3.4,0.4\n"
)


def _sample_csv_path() -> str:
    fd, path = tempfile.mkstemp(prefix="lte_summary_sample_", suffix=".csv")
    with os.fdopen(fd, "w") as fh:
        fh.write(SAMPLE_CSV)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="ERA lte_summary CSV (default: built-in sample)")
    parser.add_argument("--site", action="append", help="Site.ID(s) to run (default: all)")
    parser.add_argument("--source", default="nasa_power", help="Climate source (default: nasa_power)")
    args = parser.parse_args()

    csv_path = args.csv or _sample_csv_path()

    # 1) Load — aliases the ERA-native column names into the workflow contract.
    sites = load_sites(csv_path)
    print(f"load_sites -> {len(sites)} rows | sites: {list(sites['site_id'].unique())}")

    # 2) Select — single, several (list), or all (site_ids=None).
    subset = select_sites(sites, site_ids=args.site)
    print(f"select_sites -> {len(subset)} rows")

    # 3a) One row at a time: run_site returns per-season records (dicts).
    records = run_site(subset.iloc[0], source=args.source)
    print(f"run_site(first row) -> {len(records)} season records")
    print("    columns:", list(records[0].keys()))

    # 3b) Or the whole selection at once: run() returns (and writes) a DataFrame.
    df = run(csv_path, source=args.source, site_ids=args.site, out_csv="era_lte_compare.csv")
    print(f"run(...) -> DataFrame {df.shape}")
    context_cols = [c for c in ("site_id", "treatment", "reported_yield", "yield_error") if c in df]
    metric_cols = [c for c in ("year", "fixed_season", "tk_rain_total_mm", "tk_WRSI", "rain_delta_mm") if c in df]
    print(df[context_cols + metric_cols].to_string(index=False))


if __name__ == "__main__":
    main()
