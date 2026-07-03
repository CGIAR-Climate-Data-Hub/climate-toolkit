"""Tier 1: run the Climate Toolkit across the ERA Long-Term Experiments (LTEs).

Bridges the ERA LTEs dataset (https://github.com/ERAgriculture/LTEs) to this
toolkit. It reads ERA's shipped ``data/unique_ltes.csv`` — the LTE registry with
columns ``LTE.ID, Site.ID, Year.start, Year.end, Latitude, Longitude`` — and,
for each unique LTE site-period, runs ``analyze_climate_statistics`` with
automatic season detection, emitting a tidy climate-summary table (one row per
detected season-year). No R is required for this tier.

For the yield comparison (Tier 2), a short R script exports ERA's season windows
and outcomes from the ``industrious_elephant`` ``.RData`` tables to a flat CSV;
see the workflow notes on issue #110.

Usage
-----
    # 1. Get the ERA registry CSV (already in the ERA repo):
    #    https://github.com/ERAgriculture/LTEs/blob/main/data/unique_ltes.csv
    # 2. Point Earth Engine at your project, then run:
    set GCP_PROJECT_ID=<your-ee-project>          # PowerShell: $env:GCP_PROJECT_ID="..."
    python examples/era_lte_tier1.py unique_ltes.csv --dry-run   # list sites, no fetch
    python examples/era_lte_tier1.py unique_ltes.csv --limit 5   # smoke on 5 sites
    python examples/era_lte_tier1.py unique_ltes.csv             # full run

Note: a full run fetches gridded climate for every site over its whole duration
via Earth Engine and can take a long time; use ``--limit`` to validate first.
"""

import argparse

import pandas as pd

from climate_toolkit.climate_statistics import analyze_climate_statistics


def _year(value):
    """Parse an ERA ``Year.start``/``Year.end`` cell into an int, or None.

    ERA stores these inconsistently (floats like ``2005.0``, strings like
    ``"2008"``, and occasional non-numeric/blank cells), so parse defensively.
    """
    try:
        return int(float(str(value).strip()[:4]))
    except (ValueError, TypeError):
        return None


def load_sites(csv_path):
    """Load ``unique_ltes.csv`` into one row per unique LTE site-period."""
    df = pd.read_csv(csv_path).rename(columns={"Latitude": "lat", "Longitude": "lon"})
    df["start_year"] = df["Year.start"].map(_year)
    df["end_year"] = df["Year.end"].map(_year)
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["start_year"].notna() & df["end_year"].notna()]
    # The registry repeats sites across rows; one toolkit run per site-period.
    df = df.drop_duplicates(subset=["Site.ID", "lat", "lon", "start_year", "end_year"])
    return df.reset_index(drop=True)


def seasonal_rows(result):
    """Flatten ``season_statistics`` into per (year, season) toolkit metrics."""
    rows = []
    for s in result.get("season_statistics", []):
        precip = s.get("precipitation") or {}
        temp = s.get("temperature") or {}
        wb = s.get("water_balance") or {}
        length = s.get("length_days")
        rainy = precip.get("rainy_days")
        rows.append(
            {
                "year": s.get("year"),
                "season_number": s.get("season_number"),
                "onset": s.get("onset"),
                "cessation": s.get("cessation"),
                "length_days": length,
                "tk_rain_total_mm": precip.get("total_mm"),
                "tk_rainy_days": rainy,
                "tk_dry_days": (length - rainy)
                if (length is not None and rainy is not None)
                else None,
                "tk_mean_tavg_c": temp.get("mean_tavg"),
                "tk_NDWS": wb.get("NDWS"),
                "tk_WRSI": wb.get("WRSI"),
            }
        )
    return rows


def run(csv_path, source="agera_5", out_csv="era_lte_climate.csv", limit=None, dry_run=False):
    sites = load_sites(csv_path)
    if limit:
        sites = sites.head(limit)
    print(f"{len(sites)} unique ERA LTE site-periods to process")

    if dry_run:
        print(sites[["LTE.ID", "Site.ID", "lat", "lon", "start_year", "end_year"]].to_string())
        return sites

    out = []
    for _, row in sites.iterrows():
        try:
            result = analyze_climate_statistics(
                location_coord=(float(row["lat"]), float(row["lon"])),
                start_year=int(row["start_year"]),
                end_year=int(row["end_year"]),
                source=source,
                verbose=False,  # auto season detection
            )
        except Exception as exc:  # keep going; one bad site shouldn't stop the run
            print(f"[skip] {row['LTE.ID']} {row['Site.ID']}: {exc}")
            continue
        for tk in seasonal_rows(result):
            out.append(
                {
                    "LTE.ID": row["LTE.ID"],
                    "Site.ID": row["Site.ID"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    **tk,
                }
            )

    pd.DataFrame(out).to_csv(out_csv, index=False)
    print(f"wrote {out_csv} ({len(out)} season-rows)")


def main():
    parser = argparse.ArgumentParser(description="Run the toolkit across ERA LTE sites.")
    parser.add_argument("csv", help="Path to ERA unique_ltes.csv")
    parser.add_argument("--source", default="agera_5", help="Climate source (default: agera_5)")
    parser.add_argument("--out", default="era_lte_climate.csv", help="Output CSV path")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N sites")
    parser.add_argument("--dry-run", action="store_true", help="List sites without fetching")
    args = parser.parse_args()
    run(args.csv, args.source, args.out, args.limit, args.dry_run)


if __name__ == "__main__":
    main()
