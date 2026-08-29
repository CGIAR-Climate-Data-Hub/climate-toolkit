"""Year-matched toolkit-climate vs yield table from ERA ``lte_final.csv``.

For each ERA crop-yield observation that has a growing-season window, run the
toolkit over that exact window and year and record its climate metrics next to
the reported yield. The output lets you see how each toolkit variable relates to
yield (Rwema's request): tk_rain_total, tk_rainy_days, tk_dry_days, tk_NDWS,
tk_WRSI vs yield — as scatters and per-site time series (see era_yield_plot.py).

    python examples/era_yield_analysis.py lte_final.csv --source nasa_power --limit 200 --out era_yield_climate.csv
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

import climate_toolkit as ct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from examples.era_fetch_data import maybe_fetch  # noqa: E402

_YIELD_TO_T_HA = {"mg/ha": 1.0, "t/ha": 1.0, "kg/ha": 0.001}


def _code_to_lte():
    """Map ERA study ``Code`` -> master ``LTE.ID`` from the shipped registry.

    ``lte_final.csv`` carries ``Code`` but not ``LTE.ID``; the registry
    (``examples/data/unique_ltes.csv``) links them, so the output can carry the
    master long-term-experiment id without breaking site-season uniqueness.
    """
    reg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "unique_ltes.csv")
    try:
        reg = pd.read_csv(reg_path, sep=None, engine="python", encoding="cp1252")
    except Exception:
        return {}
    reg.columns = [str(c).strip() for c in reg.columns]
    if "Code" not in reg.columns or "LTE.ID" not in reg.columns:
        return {}
    reg = reg.dropna(subset=["Code", "LTE.ID"]).drop_duplicates("Code")
    return dict(zip(reg["Code"].astype(str), reg["LTE.ID"].astype(str)))


def matchable(df: pd.DataFrame, season_days: int = 150) -> pd.DataFrame:
    """Crop-yield rows with a usable growing-season window and yield (t/ha).

    Window = ``Plant.Start`` -> harvest. Where the harvest date is missing
    (EcoCrop-dated sites like Gourton), fall back to ``Plant.Start`` +
    ``season_days`` so those sites still get a consistent season window.
    """
    c = df[(df["Out.SubInd"] == "Crop Yield") & df["MeanT"].notna()].copy()
    c["ps"] = pd.to_datetime(c["Plant.Start"], errors="coerce")
    he = pd.to_datetime(c["rain_Harvest.End"].fillna(c["Harvest.End"]), errors="coerce")
    fallback = c["ps"] + pd.to_timedelta(season_days, unit="D")
    c["he"] = he.fillna(fallback)
    c["days"] = (c["he"] - c["ps"]).dt.days
    c = c[c["ps"].notna() & c["he"].notna() & c["days"].between(30, 365)]
    c = c[c["Latitude"].notna() & c["Longitude"].notna()]
    c["year"] = pd.to_numeric(c["M.Year"].astype(str).str.extract(r"^(\d{4})")[0], errors="coerce")
    c = c[c["year"].notna()]
    fac = c["Units"].astype(str).str.lower().map(_YIELD_TO_T_HA)
    c["yield_t_ha"] = pd.to_numeric(c["MeanT"], errors="coerce") * fac
    c["treatment"] = c["T.Descrip"].fillna(c["TID"]).astype(str)
    return c[c["yield_t_ha"].between(0.05, 30)]


def _tk_metrics(lat, lon, year, ps, he, source, cache):
    key = (round(lat, 3), round(lon, 3), int(year), ps.strftime("%m-%d"), he.strftime("%m-%d"))
    if key in cache:
        return cache[key]
    fixed = f"{ps.strftime('%m-%d')}:{he.strftime('%m-%d')}"
    res = ct.analyze_climate_statistics(
        location_coord=(float(lat), float(lon)), start_year=int(year), end_year=int(year),
        source=source, fixed_season=fixed, verbose=False,
    )
    ss = res.get("season_statistics") or []
    m = None
    if ss:
        s = ss[0]
        p = s.get("precipitation") or {}
        wb = s.get("water_balance") or {}
        length, rainy = s.get("length_days"), p.get("rainy_days")
        m = {
            "tk_rain_total_mm": p.get("total_mm"),
            "tk_rainy_days": rainy,
            "tk_dry_days": (length - rainy) if (length is not None and rainy is not None) else None,
            "tk_NDWS": wb.get("NDWS"),
            "tk_WRSI": wb.get("WRSI"),
        }
    cache[key] = m
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="ERA lte_final.csv")
    ap.add_argument("--source", default="nasa_power")
    ap.add_argument("--limit", type=int, default=None, help="Only first N unique windows")
    ap.add_argument("--site", help="Only this Site.ID (substring match)")
    ap.add_argument("--crop", help="Only this crop, e.g. 'Maize' (substring match on Product.Simple). "
                    "Useful for sites with several crops, e.g. Kouve = cotton + maize.")
    ap.add_argument("--season-days", type=int, default=150, help="Fallback season length when no harvest date")
    ap.add_argument("--out", default="era_yield_climate.csv")
    args = ap.parse_args()

    raw = pd.read_csv(maybe_fetch(args.csv), low_memory=False)
    if args.site:
        raw = raw[raw["Site.ID"].astype(str).str.contains(args.site, case=False, na=False)]
    if args.crop:
        raw = raw[raw["Product.Simple"].astype(str).str.contains(args.crop, case=False, na=False)]
    obs = matchable(raw, season_days=args.season_days)
    code2lte = _code_to_lte()
    # unique climate windows to fetch (many observations share one)
    keys = obs.drop_duplicates(["Latitude", "Longitude", "year", "ps", "he"])
    if args.limit:
        keys = keys.head(args.limit)
    print(f"{len(obs)} yield observations · {len(keys)} unique windows to compute")

    cache: dict = {}
    for _, r in keys.iterrows():
        try:
            _tk_metrics(r["Latitude"], r["Longitude"], r["year"], r["ps"], r["he"], args.source, cache)
        except Exception as exc:
            print(f"[skip] {r['Site.ID']} {r['year']}: {exc}")

    rows = []
    for _, o in obs.iterrows():
        key = (round(o["Latitude"], 3), round(o["Longitude"], 3), int(o["year"]),
               o["ps"].strftime("%m-%d"), o["he"].strftime("%m-%d"))
        m = cache.get(key)
        if not m:
            continue
        code = o.get("Code")
        rows.append({
            # identifiers first, so every site-season record is uniquely keyed
            # and linked to the master LTE registry (Code -> LTE.ID).
            "lte_id": code2lte.get(str(code)),
            "code": code,
            "site_key": o.get("Site.Key"),
            "index": o.get("Index"),
            "site_id": o["Site.ID"], "year": int(o["year"]), "crop": o["Product.Simple"],
            "variety": o.get("Variety"),  # cultivar; often changes over the LTE's life
            "treatment": o["treatment"], "yield_t_ha": round(float(o["yield_t_ha"]), 3), **m,
        })

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print(f"wrote {args.out} ({len(out)} year-matched rows, {out['site_id'].nunique()} sites)")
    for v in ("tk_rain_total_mm", "tk_rainy_days", "tk_dry_days", "tk_NDWS", "tk_WRSI"):
        d = out.dropna(subset=[v, "yield_t_ha"])
        if len(d) > 2:
            print(f"  corr({v}, yield) = {d[v].corr(d['yield_t_ha']):+.2f}  (n={len(d)})")


if __name__ == "__main__":
    main()
