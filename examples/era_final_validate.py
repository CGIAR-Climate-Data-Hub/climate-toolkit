"""Validate the toolkit's rainfall against ERA's own climate-merged values.

ERA's ``lte_final.csv`` (ERAgriculture/LTEs) already carries, per observation,
the growing-season rainfall ERA itself computed (``rain_rain_sum``) over the
window ``Plant.Start`` -> ``rain_Harvest.End``. This fetches the toolkit's daily
precipitation over the *same* window and year and compares the two — a
like-for-like, year-matched methodology check (note: ERA's underlying gridded
source may differ from ``nasa_power``, so some spread is expected).

    python examples/era_final_validate.py lte_final.csv --source nasa_power --limit 60 --out era_final_compare.csv
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import pandas as pd

import climate_toolkit as ct
from climate_toolkit.fetch_data.source_data.sources.utils.models import ClimateVariable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from examples.era_fetch_data import maybe_fetch  # noqa: E402


def _matchable(df: pd.DataFrame) -> pd.DataFrame:
    c = df[df["rain_rain_sum"].notna()].copy()
    c["ps"] = pd.to_datetime(c["Plant.Start"], errors="coerce")
    c["he"] = pd.to_datetime(c["rain_Harvest.End"].fillna(c["Harvest.End"]), errors="coerce")
    c["days"] = (c["he"] - c["ps"]).dt.days
    c = c[c["ps"].notna() & c["he"].notna() & c["days"].between(1, 400)]
    c = c[c["Latitude"].notna() & c["Longitude"].notna()]
    # one row per unique (site, window) — climate is identical across treatments
    return c.drop_duplicates(["Latitude", "Longitude", "Plant.Start", "rain_Harvest.End"])


def _precip_sum(source, lat, lon, d0, d1):
    df = ct.fetch_climate_data(
        source=source, location_coord=(float(lat), float(lon)),
        variables=[ClimateVariable.precipitation],
        date_from=d0, date_to=d1, verbose=False,
    )
    col = next((x for x in df.columns if "precip" in x.lower()), None)
    return float(df[col].sum()) if col else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="ERA lte_final.csv")
    ap.add_argument("--source", default="nasa_power")
    ap.add_argument("--limit", type=int, default=None, help="Only first N unique windows")
    ap.add_argument("--out", default="era_final_compare.csv")
    args = ap.parse_args()

    sites = _matchable(pd.read_csv(maybe_fetch(args.csv), low_memory=False))
    if args.limit:
        sites = sites.head(args.limit)
    print(f"{len(sites)} unique site-year windows with ERA rain_rain_sum")

    rows = []
    for _, r in sites.iterrows():
        try:
            tk = _precip_sum(args.source, r["Latitude"], r["Longitude"],
                             r["ps"].date(), r["he"].date())
        except Exception as exc:
            print(f"[skip] {r['Site.ID']} {r['ps'].date()}: {exc}")
            continue
        if tk is None:
            continue
        rows.append({
            "site_id": r["Site.ID"], "crop": r["Product.Simple"],
            "window_start": r["ps"].date(), "window_end": r["he"].date(),
            "window_days": int(r["days"]),
            "era_rain_sum_mm": round(float(r["rain_rain_sum"]), 1),
            "tk_rain_sum_mm": round(tk, 1),
            "delta_mm": round(tk - float(r["rain_rain_sum"]), 1),
            "era_eratio": round(float(r["eratio_eratio_mean"]), 3) if pd.notna(r["eratio_eratio_mean"]) else None,
        })

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print(f"wrote {args.out} ({len(out)} rows)")
    if len(out):
        d = out["delta_mm"]
        corr = out["tk_rain_sum_mm"].corr(out["era_rain_sum_mm"])
        print(f"toolkit vs ERA rain_rain_sum — bias={d.mean():.0f} mm | MAE={d.abs().mean():.0f} mm "
              f"| r={corr:.2f} | n={len(out)}")


if __name__ == "__main__":
    main()
