from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from climate_tookit.climate_statistics.statistics import analyze_climate_statistics


@dataclass(frozen=True)
class Site:
    name: str
    lat: float
    lon: float
    region: str


DEFAULT_SITES: List[Site] = [
    Site("Nairobi", -1.286, 36.817, "East Africa"),
    Site("Lodwar", 3.119, 35.5973, "East Africa arid"),
    Site("Cusco", -13.5319, -71.9675, "Andes"),
]

def _candidate_value(row: Dict[str, Any], candidate: str) -> str:
    identity = row.get("season_identity") or {}
    if candidate == "season_number":
        return str(row.get("season_number"))
    if candidate == "onset_month":
        return f"{identity.get('onset_month', 'na'):02d}" if isinstance(identity.get("onset_month"), int) else "na"
    if candidate == "month_pair":
        om = identity.get("onset_month")
        cm = identity.get("cessation_month")
        if isinstance(om, int) and isinstance(cm, int):
            return f"{om:02d}-{cm:02d}"
        return "na"
    if candidate == "regime_onset_month":
        return identity.get("experimental_alignment_key") or "na"
    raise ValueError(f"Unknown candidate: {candidate}")


def summarize_candidate(rows: List[Dict[str, Any]], candidate: str) -> Dict[str, Any]:
    keyed_rows: List[Dict[str, Any]] = []
    for row in rows:
        key = _candidate_value(row, candidate)
        keyed = dict(row)
        keyed["candidate_key"] = key
        keyed_rows.append(keyed)

    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for row in keyed_rows:
        by_key.setdefault(row["candidate_key"], []).append(row)

    collisions: List[Dict[str, Any]] = []
    for key, bucket in by_key.items():
        year_counts: Dict[int, int] = {}
        for row in bucket:
            year = int(row["year"])
            year_counts[year] = year_counts.get(year, 0) + 1
        for year, count in sorted(year_counts.items()):
            if count > 1:
                collisions.append({"key": key, "year": year, "count": count})

    reused_keys = {
        key: sorted({int(row["year"]) for row in bucket})
        for key, bucket in by_key.items()
        if len({int(row["year"]) for row in bucket}) > 1
    }
    seasons_with_reused_key = sum(
        1 for row in keyed_rows if row["candidate_key"] in reused_keys
    )
    total = len(keyed_rows)

    return {
        "candidate": candidate,
        "n_seasons": total,
        "n_distinct_keys": len(by_key),
        "collision_free": len(collisions) == 0,
        "collisions": collisions,
        "reused_key_count": len(reused_keys),
        "reused_key_fraction": round(seasons_with_reused_key / total, 3) if total else 0.0,
        "fragmentation_ratio": round(len(by_key) / total, 3) if total else 0.0,
        "keys": [
            {
                "key": key,
                "years": sorted({int(row["year"]) for row in bucket}),
                "n_rows": len(bucket),
                "regimes": sorted({str(row.get("regime", "unknown")) for row in bucket}),
                "onset_months": sorted({
                    int((row.get("season_identity") or {}).get("onset_month"))
                    for row in bucket
                    if isinstance((row.get("season_identity") or {}).get("onset_month"), int)
                }),
            }
            for key, bucket in sorted(by_key.items())
        ],
    }


def overall_recommendation(candidate_summaries: Iterable[Dict[str, Any]]) -> str:
    summaries = list(candidate_summaries)
    regime_month = next((s for s in summaries if s["candidate"] == "regime_onset_month"), None)
    if not regime_month:
        return "No recommendation"
    if not regime_month["collision_free"]:
        return "Do not enable auto regrouping with regime+onset_month; collisions already present."
    reused = regime_month["reused_key_fraction"]
    frag = regime_month["fragmentation_ratio"]
    if reused >= 0.5 and frag <= 0.7:
        return (
            "regime+onset_month looks promising as exploratory alignment key, but keep guard in place until wider-site validation."
        )
    return (
        "regime+onset_month reduces slot-mixing risk but remains fragmented/coverage-limited; keep warning/guard path and do not auto-enable regrouping yet."
    )


def collect_site_rows(site: Site, start_year: int, end_year: int, source: str) -> Dict[str, Any]:
    result = analyze_climate_statistics(
        location_coord=(site.lat, site.lon),
        start_year=start_year,
        end_year=end_year,
        source=source,
    )
    if result.get("error"):
        return {
            "site": asdict(site),
            "error": result["error"],
            "season_rows": [],
            "candidate_summaries": [],
            "recommendation": "Run failed",
        }

    season_rows = result.get("season_statistics", [])
    candidate_summaries = [
        summarize_candidate(season_rows, candidate)
        for candidate in ("season_number", "onset_month", "month_pair", "regime_onset_month")
    ]
    return {
        "site": asdict(site),
        "error": None,
        "season_rows": season_rows,
        "candidate_summaries": candidate_summaries,
        "recommendation": overall_recommendation(candidate_summaries),
        "season_slot_warning": result.get("season_slot_warning"),
    }


def flatten_rows(site_reports: List[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for report in site_reports:
        site = report["site"]
        for row in report.get("season_rows", []):
            identity = row.get("season_identity") or {}
            rows.append(
                {
                    "site": site["name"],
                    "region": site["region"],
                    "year": row.get("year"),
                    "season_number": row.get("season_number"),
                    "regime": row.get("regime"),
                    "onset": row.get("onset"),
                    "cessation": row.get("cessation"),
                    "length_days": row.get("length_days"),
                    "onset_month": identity.get("onset_month"),
                    "cessation_month": identity.get("cessation_month"),
                    "midpoint_month": identity.get("midpoint_month"),
                    "season_number_key": str(row.get("season_number")),
                    "onset_month_key": f"{identity.get('onset_month'):02d}" if isinstance(identity.get("onset_month"), int) else "na",
                    "month_pair_key": (
                        f"{identity.get('onset_month'):02d}-{identity.get('cessation_month'):02d}"
                        if isinstance(identity.get("onset_month"), int) and isinstance(identity.get("cessation_month"), int)
                        else "na"
                    ),
                    "regime_onset_month_key": identity.get("experimental_alignment_key"),
                }
            )
    return pd.DataFrame(rows)


def render_markdown(
    site_reports: List[Dict[str, Any]],
    start_year: int,
    end_year: int,
    source: str,
) -> str:
    lines: List[str] = []
    lines.append("# Auto Season Alignment Report")
    lines.append("")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Period: `{start_year}`-`{end_year}`")
    lines.append(f"- Sites: `{len(site_reports)}`")
    lines.append("")

    for report in site_reports:
        site = report["site"]
        lines.append(f"## {site['name']} ({site['region']})")
        lines.append("")
        if report.get("error"):
            lines.append(f"- Error: `{report['error']}`")
            lines.append("")
            continue
        if report.get("season_slot_warning"):
            lines.append(f"- Guard triggered: `{report['season_slot_warning']}`")
        lines.append(f"- Recommendation: {report['recommendation']}")
        lines.append("")
        lines.append("### Seasons")
        lines.append("")
        lines.append("| Year | Slot | Regime | Onset | Cessation | Align key |")
        lines.append("|---|---:|---|---|---|---|")
        for row in report.get("season_rows", []):
            identity = row.get("season_identity") or {}
            lines.append(
                f"| {row.get('year')} | {row.get('season_number')} | {row.get('regime')} | "
                f"{row.get('onset')} | {row.get('cessation')} | {identity.get('experimental_alignment_key')} |"
            )
        lines.append("")
        lines.append("### Candidate key summary")
        lines.append("")
        lines.append("| Candidate | Collision free | Reused key fraction | Fragmentation ratio | Distinct keys |")
        lines.append("|---|---|---:|---:|---:|")
        for summary in report.get("candidate_summaries", []):
            lines.append(
                f"| `{summary['candidate']}` | `{summary['collision_free']}` | "
                f"{summary['reused_key_fraction']:.3f} | {summary['fragmentation_ratio']:.3f} | {summary['n_distinct_keys']} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build auto-season alignment report.")
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--end-year", type=int, default=2020)
    parser.add_argument("--source", default="auto")
    parser.add_argument(
        "--output-prefix",
        default="analysis/auto_season_alignment_report",
        help="Prefix for .json/.csv/.md outputs",
    )
    args = parser.parse_args()

    reports = [
        collect_site_rows(site, args.start_year, args.end_year, args.source)
        for site in DEFAULT_SITES
    ]

    output_prefix = Path(args.output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    md_path = output_prefix.with_suffix(".md")

    payload = {
        "start_year": args.start_year,
        "end_year": args.end_year,
        "source": args.source,
        "sites": reports,
    }
    json_path.write_text(json.dumps(payload, indent=2))
    flatten_rows(reports).to_csv(csv_path, index=False)
    md_path.write_text(render_markdown(reports, args.start_year, args.end_year, args.source))

    print(f"Saved JSON report to {json_path}")
    print(f"Saved CSV report to {csv_path}")
    print(f"Saved Markdown report to {md_path}")


if __name__ == "__main__":
    main()
