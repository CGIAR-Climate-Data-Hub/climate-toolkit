"""Extract ERA's ``Site.Out`` table into a toolkit-ready CSV — no R needed.

The registry (``unique_ltes.csv``) has only coordinates and years. The season
windows and ERA-reported seasonal rainfall live in the full ERA dataset's
``Site.Out`` table, published as JSON on the ERA S3 bucket. This pulls that one
table and writes a CSV that ``era_lte_workflow.py`` consumes directly — giving
the real toolkit-vs-reported rainfall comparison (``Site.MSP.S1``).

It does NOT reconstruct treatment/yield — those need the multi-table join in
the ERA R workflow (issue #141). This is the rainfall-comparison slice only.

Get the ERA dataset JSON (public, ~486 MB), then run::

    # one-off download (or use the .RData the R workflow points at):
    curl -o era.json \\
      https://digital-atlas.s3.amazonaws.com/era/data/agronomic_majestic-hippo-2020-2025-03-19.2_industrious-elephant-2023-2025-03-19.1.json

    pip install ijson    # streaming JSON parser
    python examples/era_extract_site_out.py --json era.json --out era_site_out.csv
    python examples/era_lte_workflow.py era_site_out.csv --source nasa_power

``Site.MSP.S1`` is a long-term *mean* seasonal precip, so the toolkit's seasonal
totals over a fixed climatological window (default 1991-2020) are compared
against that mean. Pass ``--start-year/--end-year`` to change the window.
"""

from __future__ import annotations

import argparse
import csv

try:
    import ijson
except ImportError:  # pragma: no cover - dependency hint
    raise SystemExit("This script needs ijson: pip install ijson")

# Site.Out fields we keep — native ERA names that era_lte_workflow aliases.
FIELDS = [
    "Site.ID", "Site.LatD", "Site.LonD",
    "Site.Start.S1", "Site.End.S1", "Site.Start.S2", "Site.End.S2",
    "Site.MSP.S1", "Site.MAP", "Site.MAT",
]


def extract(json_path, out_csv, start_year, end_year):
    seen = set()
    written = 0
    with open(json_path, "rb") as f, open(out_csv, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow([*FIELDS, "Year.start", "Year.end"])
        for rec in ijson.items(f, "Site.Out.item"):
            # Keep only rows with a real season window AND reported rainfall —
            # the two inputs the comparison needs.
            if not (rec.get("Site.Start.S1") and rec.get("Site.End.S1")
                    and rec.get("Site.MSP.S1") not in (None, "")):
                continue
            if rec.get("Site.LatD") in (None, "") or rec.get("Site.LonD") in (None, ""):
                continue
            site_id = rec.get("Site.ID")
            if site_id in seen:  # one representative row per site
                continue
            seen.add(site_id)
            writer.writerow([rec.get(k, "") for k in FIELDS] + [start_year, end_year])
            written += 1
    return written


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", required=True, help="ERA dataset JSON (from ERA S3)")
    p.add_argument("--out", default="era_site_out.csv", help="Output CSV path")
    p.add_argument("--start-year", type=int, default=1991, help="Analysis window start")
    p.add_argument("--end-year", type=int, default=2020, help="Analysis window end")
    args = p.parse_args()
    n = extract(args.json, args.out, args.start_year, args.end_year)
    print(f"wrote {args.out} ({n} sites with season window + reported rainfall)")


if __name__ == "__main__":
    main()
