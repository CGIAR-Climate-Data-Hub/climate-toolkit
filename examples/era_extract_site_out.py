"""Extract real ERA tables into a toolkit-ready CSV — no R needed.

The registry (``unique_ltes.csv``) has only coordinates and years. The season
windows, ERA-reported seasonal rainfall, and crop yields live in the full ERA
dataset, published as JSON on the ERA S3 bucket. This pulls the tables the
toolkit needs so ``era_lte_workflow.py`` can produce a real comparison.

Two tables are read:

* ``Site.Out`` -> per site: coordinates, season windows, ``Site.MSP.S1``
  (ERA-reported mean seasonal rainfall). This is the rainfall comparison and is
  unambiguous — a single table, no joins.
* ``Data.Out`` (only with ``--with-yield``) -> per (site, treatment, crop): mean
  **Crop Yield**. ``Out.Subind == "Crop Yield"`` is an explicit ERA field, and
  the mixed units (``t/ha``, ``kg/ha``, ``Mg/ha``) are normalized to t/ha. This
  is an independent extraction — cross-check against ERA's official
  ``lte_summary`` (issue #141) before treating the yields as authoritative.

Get the ERA dataset JSON (public, ~486 MB), then run::

    curl -o era.json \\
      https://digital-atlas.s3.amazonaws.com/era/data/agronomic_majestic-hippo-2020-2025-03-19.2_industrious-elephant-2023-2025-03-19.1.json
    pip install ijson

    # rainfall comparison only:
    python examples/era_extract_site_out.py --json era.json --out era_site_out.csv
    # rainfall + treatment + crop yield:
    python examples/era_extract_site_out.py --json era.json --with-yield --out era_full.csv

    python examples/era_lte_workflow.py era_full.csv --source nasa_power

``Site.MSP.S1`` is a long-term *mean* seasonal precip, so the toolkit's seasonal
totals over a fixed window (default 1991-2020) are compared against that mean.
"""

from __future__ import annotations

import argparse
import csv


def _ijson():
    """Import ijson lazily so this module stays importable without it."""
    try:
        import ijson
    except ImportError as exc:  # pragma: no cover - dependency hint
        raise SystemExit("This script needs ijson: pip install ijson") from exc
    return ijson


# Site.Out fields we keep — native ERA names that era_lte_workflow aliases.
SITE_FIELDS = [
    "Site.ID", "Site.LatD", "Site.LonD",
    "Site.Start.S1", "Site.End.S1", "Site.Start.S2", "Site.End.S2",
    "Site.MSP.S1", "Site.MAP", "Site.MAT",
]

# ED.Mean.T units seen for Crop Yield, converted to t/ha (Mg/ha == t/ha).
_YIELD_TO_T_HA = {"t/ha": 1.0, "mg/ha": 1.0, "kg/ha": 0.001}


def _load_site_out(json_path):
    """First representative Site.Out row per site that has season + rainfall."""
    ijson = _ijson()
    sites = {}
    with open(json_path, "rb") as f:
        for rec in ijson.items(f, "Site.Out.item"):
            if not (rec.get("Site.Start.S1") and rec.get("Site.End.S1")
                    and rec.get("Site.MSP.S1") not in (None, "")):
                continue
            if rec.get("Site.LatD") in (None, "") or rec.get("Site.LonD") in (None, ""):
                continue
            sites.setdefault(rec.get("Site.ID"), rec)
    return sites


def _load_yields(json_path):
    """Mean Crop Yield (t/ha) per (Site.ID, treatment, crop) from Data.Out.

    Filters to the explicit ``Out.Subind == 'Crop Yield'`` and normalizes the
    mixed t/ha, kg/ha, Mg/ha units. Averages replicate/year observations.
    """
    ijson = _ijson()
    sums, counts = {}, {}
    with open(json_path, "rb") as f:
        for rec in ijson.items(f, "Data.Out.item"):
            if rec.get("Out.Subind") != "Crop Yield":
                continue
            factor = _YIELD_TO_T_HA.get(str(rec.get("Out.Unit", "")).lower())
            value = rec.get("ED.Mean.T")
            if factor is None or value in (None, ""):
                continue
            try:
                t_ha = float(value) * factor
            except (TypeError, ValueError):
                continue
            key = (rec.get("Site.ID"), rec.get("T.Name"), rec.get("Product.Simple"))
            sums[key] = sums.get(key, 0.0) + t_ha
            counts[key] = counts.get(key, 0) + 1
    return {k: sums[k] / counts[k] for k in sums}


def extract(json_path, out_csv, start_year, end_year, with_yield=False):
    sites = _load_site_out(json_path)
    yields = _load_yields(json_path) if with_yield else {}

    header = [*SITE_FIELDS, "Year.start", "Year.end"]
    if with_yield:
        header += ["Treatment", "P.Product", "Yield"]

    written = 0
    with open(out_csv, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(header)
        for site_id, rec in sites.items():
            base = [rec.get(k, "") for k in SITE_FIELDS] + [start_year, end_year]
            site_yields = [(t, p, y) for (s, t, p), y in yields.items() if s == site_id]
            if with_yield and site_yields:
                for treatment, product, y in site_yields:
                    writer.writerow(base + [treatment, product, round(y, 3)])
                    written += 1
            else:
                writer.writerow(base + (["", "", ""] if with_yield else []))
                written += 1
    return written


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", required=True, help="ERA dataset JSON (from ERA S3)")
    p.add_argument("--out", default="era_site_out.csv", help="Output CSV path")
    p.add_argument("--with-yield", action="store_true",
                   help="Also join Crop Yield + treatment from Data.Out")
    p.add_argument("--start-year", type=int, default=1991, help="Analysis window start")
    p.add_argument("--end-year", type=int, default=2020, help="Analysis window end")
    args = p.parse_args()
    n = extract(args.json, args.out, args.start_year, args.end_year, args.with_yield)
    kind = "site-treatment rows" if args.with_yield else "sites"
    print(f"wrote {args.out} ({n} {kind}) with season window + reported rainfall"
          + (" + crop yield" if args.with_yield else ""))


if __name__ == "__main__":
    main()
