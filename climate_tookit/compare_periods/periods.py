"""
Compare Periods
Runs statistics.py for a baseline period and a focal year, then diffs the four
sections statistics.py produces:
    raw_climate_summary:    per-variable mean/min/max/std
    overall_statistics :    period totals (baseline annualised before diffing)
    season_statistics  :    per-season metrics
                             - lumped 'typical season' when --fixed-season is omitted
                             - one comparison per window when --fixed-season is given, so a two-season spec doesn't blend MAM with OND
    annual_summary     :   humid test (annual rainfall, humid_year ratio)

--fixed-season is passed straight through to statistics.py, so its three flavors work without periods.py knowing about them:
    Single        : '03-01:05-31'
    Two seasons   : '03-01:05-31,10-01:12-15'
    Year-crossing : '11-01:02-28'
Plain `chirps_v2` source defaults tmax=25/tmin=15 in statistics.py, so temperature is excluded from every diff section when chirps_v2 is source.
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

import pandas as pd

current_dir  = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from climate_tookit.climate_statistics.statistics import analyze_climate_statistics

CATEGORIES   = ["precipitation", "temperature", "et0", "water_balance"]
ANNUALIZABLE = {
    "precipitation": ["total_mm", "rainy_days", "dry_days"],
    "et0":           ["total_mm"],
    "water_balance": ["total_balance", "deficit_days", "surplus_days"],
}
OVERALL_WATER_BALANCE_EXCLUDED = {
    "NDWS",
    "NDWL0",
    "WRSI",
    "mean_eratio",
    "mean_logging_mm",
    "crop_water_requirement_mm",
    "actual_crop_et_mm",
    "ending_soil_water_mm",
    "runoff_mm",
}
PRECIP_ONLY  = {"chirps", "chirps_v2"}
SUPPORTED    = {"era_5", "agera_5", "chirps+chirts", "chirps_v2+chirts", "nasa_power",
                "chirps", "chirps_v2", "chirts", "terraclimate", "imerg", "tamsat", "auto"}

# helpers
def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def _round(d: Any, n: int = 2) -> Any:
    if isinstance(d, dict):  return {k: _round(v, n) for k, v in d.items()}
    if isinstance(d, list):  return [_round(v, n) for v in d]
    return round(d, n) if _is_num(d) else d


def _percent_change(diff: float, baseline: float) -> Optional[float]:
    """
    Percent change relative to baseline magnitude.

    Using abs(baseline) keeps sign aligned with diff when baseline is negative,
    e.g. -722 vs -705 -> diff -17.1 -> -2.43% rather than +2.43%.
    Suppress percent change when value crosses zero, because ratio-to-baseline
    becomes misleading around sign flips (for example seasonal water balance
    near neutral becoming strongly negative).
    """
    if baseline == 0:
        return None
    actual = baseline + diff
    if baseline * actual < 0:
        return None
    return diff / abs(baseline) * 100.0


def _fmt_pct(v: Optional[float]) -> str:
    return f"{v:+.2f}%" if _is_num(v) else "n/a"


def _diff_spei(
    focal_spei: Optional[Dict[str, Any]],
    baseline_spei: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not (focal_spei and baseline_spei):
        return None
    focal_series = focal_spei.get("monthly_series") or []
    baseline_series = baseline_spei.get("monthly_series") or []
    focal_cfg = focal_spei.get("config") or {}
    baseline_cfg = baseline_spei.get("config") or {}

    baseline_by_month: Dict[int, List[float]] = {}
    for row in baseline_series:
        month = row.get("month")
        value = row.get("spei")
        if isinstance(month, int) and _is_num(value):
            baseline_by_month.setdefault(month, []).append(float(value))

    windows = []
    for row in focal_series:
        month = row.get("month")
        focal_value = row.get("spei")
        if not (isinstance(month, int) and _is_num(focal_value)):
            continue
        base_vals = baseline_by_month.get(month) or []
        if not base_vals:
            continue
        baseline_avg = sum(base_vals) / len(base_vals)
        diff = float(focal_value) - baseline_avg
        pct = _percent_change(diff, baseline_avg)
        windows.append({
            "date": row.get("date"),
            "month": month,
            "focal_spei": round(float(focal_value), 3),
            "baseline_avg_spei": round(baseline_avg, 3),
            "diff": round(diff, 3),
            "pct": round(pct, 2) if _is_num(pct) else None,
        })

    focal_vals = [float(row["spei"]) for row in focal_series if _is_num(row.get("spei"))]
    base_vals = [float(row["spei"]) for row in baseline_series if _is_num(row.get("spei"))]
    summary = None
    if focal_vals and base_vals:
        focal_avg = sum(focal_vals) / len(focal_vals)
        base_avg = sum(base_vals) / len(base_vals)
        diff = focal_avg - base_avg
        pct = _percent_change(diff, base_avg)
        summary = {
            "focal_avg_spei": round(focal_avg, 3),
            "baseline_avg_spei": round(base_avg, 3),
            "diff": round(diff, 3),
            "pct": round(pct, 2) if _is_num(pct) else None,
        }

    return {
        "config": {
            "focal": focal_cfg,
            "baseline": baseline_cfg,
        },
        "summary": summary,
        "monthly": windows,
    }

def _annualize(stats: Dict[str, Any], n_years: int) -> Dict[str, Any]:
    """Period totals -> per-year averages. Means/maxes/mins untouched."""
    if n_years <= 0:
        return stats
    out: Dict[str, Any] = {}
    for cat, metrics in stats.items():
        if not isinstance(metrics, dict):
            out[cat] = metrics
            continue
        annz = ANNUALIZABLE.get(cat, [])
        out[cat] = {m: round(v / n_years, 2) if (m in annz and _is_num(v)) else v
                    for m, v in metrics.items()}
    return out


def _filter_overall_statistics_for_period_compare(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Overall period block should carry annualizable climate normals only.

    Root-zone crop water-balance diagnostics such as NDWS and WRSI stay valid in
    seasonal/LTM blocks, but become misleading when shown in the whole-period
    overall block because they are not annualized climate normals.
    """
    out: Dict[str, Any] = {}
    for cat, metrics in (stats or {}).items():
        if cat != "water_balance" or not isinstance(metrics, dict):
            out[cat] = metrics
            continue
        filtered = {
            metric: value
            for metric, value in metrics.items()
            if metric not in OVERALL_WATER_BALANCE_EXCLUDED
        }
        out[cat] = filtered
    return out

def _agg_seasons(seasons: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Average season metrics into a single 'typical season' block."""
    if not seasons:
        return {"_n": 0}
    sums: Dict[str, List[float]] = {}
    for s in seasons:
        for cat in ("precipitation", "temperature", "water_balance"):
            for m, v in (s.get(cat) or {}).items():
                if _is_num(v):
                    sums.setdefault(f"{cat}.{m}", []).append(float(v))
    out: Dict[str, Any] = {"_n": len(seasons)}
    for k, vs in sums.items():
        cat, m = k.split(".", 1)
        out.setdefault(cat, {})[m] = round(sum(vs) / len(vs), 2)
    return out


def _season_counts_by_year(seasons: List[Dict[str, Any]]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for season in seasons or []:
        year = season.get("year")
        if isinstance(year, int):
            counts[year] = counts.get(year, 0) + 1
    return counts


def _auto_season_count_guard(
    baseline_seasons: List[Dict[str, Any]],
    focal_seasons: List[Dict[str, Any]],
) -> str | None:
    """
    Auto-detected compare_periods semantics break when season counts differ by year.

    In that case, averaging all detected seasons into one "typical season" can blend
    incomparable climatological windows. Fixed-season mode is required for a stable
    baseline/focal comparison.
    """
    baseline_counts = _season_counts_by_year(baseline_seasons)
    focal_counts = _season_counts_by_year(focal_seasons)
    observed_counts = set(baseline_counts.values()) | set(focal_counts.values())
    if len(observed_counts) <= 1:
        return None

    baseline_summary = ", ".join(
        f"{year}:{count}" for year, count in sorted(baseline_counts.items())
    ) or "none"
    focal_summary = ", ".join(
        f"{year}:{count}" for year, count in sorted(focal_counts.items())
    ) or "none"
    return (
        "Auto-detected season counts differ across baseline/focal years, so "
        "season-level compare_periods output would blend incomparable seasons. "
        f"Baseline counts by year: {baseline_summary}. "
        f"Focal counts by year: {focal_summary}. "
        "Re-run with --fixed-season for a stable comparison."
    )

def _diff_block(a: Dict, b: Dict, a_lbl: str, b_lbl: str,
                drop_temp: bool = False) -> Dict[str, Any]:
    """Diff two category-keyed blocks: {category: {metric: {a_lbl, b_lbl, diff, pct}}}"""
    out: Dict[str, Any] = {}
    for cat in CATEGORIES:
        if drop_temp and cat == "temperature":
            continue
        ab, bb = a.get(cat), b.get(cat)
        if not (isinstance(ab, dict) and isinstance(bb, dict)):
            continue
        cat_out = {}
        for m, av in ab.items():
            bv = bb.get(m)
            if not (_is_num(av) and _is_num(bv)):
                continue
            d = av - bv
            p = _percent_change(d, bv)
            cat_out[m] = {a_lbl:    round(av, 2), b_lbl:    round(bv, 2),
                          "diff":   round(d,  2),
                          "pct":    round(p,  2) if _is_num(p) else None}
        if cat_out:
            out[cat] = cat_out
    return out

def _diff_raw(focal_raw: List[Dict], baseline_raw: List[Dict],
              drop_temp: bool = False) -> Dict[str, Any]:
    """Diff raw_climate_summary lists: {variable: {stat: {focal, baseline, diff, pct}}}"""
    fd = {r.get("Variable"): r for r in focal_raw    if r.get("Variable")}
    bd = {r.get("Variable"): r for r in baseline_raw if r.get("Variable")}
    out: Dict[str, Any] = {}
    for var, fr in fd.items():
        if drop_temp and "Temperature" in var:
            continue
        br = bd.get(var)
        if not br:
            continue
        per_stat = {}
        for s in ("Mean", "Min", "Max", "Std"):
            fv, bv = fr.get(s), br.get(s)
            if not (_is_num(fv) and _is_num(bv)):
                continue
            d = fv - bv
            p = _percent_change(d, bv)
            per_stat[s] = {"focal":    round(fv, 3), "baseline": round(bv, 3),
                           "diff":     round(d,  3),
                           "pct":      round(p,  2) if _is_num(p) else None}
        if per_stat:
            out[var] = per_stat
    return out

def _diff_annual(focal_ann: Dict[str, Dict], baseline_ann: Dict[str, Dict],
                 focal_year: int) -> Dict[str, Any]:
    """Diff annual_summary: focal year value vs baseline aggregate."""
    fi = focal_ann.get(str(focal_year)) or {}
    rains  = [v["annual_rain_mm"] for v in baseline_ann.values()
              if v and _is_num(v.get("annual_rain_mm"))]
    humid  = sum(1 for v in baseline_ann.values() if v and v.get("is_humid"))
    total  = sum(1 for v in baseline_ann.values() if v)

    out: Dict[str, Any] = {}
    fr = fi.get("annual_rain_mm")
    if _is_num(fr) and rains:
        b_avg = sum(rains) / len(rains)
        d, p = fr - b_avg, _percent_change(fr - b_avg, b_avg)
        out["annual_rain_mm"] = {"focal":    round(float(fr), 1),
                                  "baseline_avg": round(b_avg, 1),
                                  "diff":     round(d, 1),
                                  "pct":      round(p, 2) if _is_num(p) else None}
    out["humid_status"] = {
        "focal_is_humid":    fi.get("is_humid"),
        "focal_humid_test":  fi.get("humid_test"),
        "baseline_humid":    f"{humid}/{total}" + (
            f" ({humid/total*100:.1f}%)" if total else ""),
    }
    return out

# main API 
def compare(
    location:       Tuple[float, float],
    baseline_start: int,
    baseline_end:   int,
    focal_year:     int,
    source:         str,
    fixed_season:   Optional[str] = None,
    spei_scale_months: Optional[int] = None,
    spei_fit: str = "ub-pwm",
    spei_ref_start: Optional[str] = None,
    spei_ref_end: Optional[str] = None,
) -> Dict[str, Any]:
    """Run statistics.py for baseline + focal, diff the four sections."""
    if source.lower() not in SUPPORTED:
        return {"error": f"Source '{source}' not supported. "
                         f"Use one of: {', '.join(sorted(SUPPORTED))}"}
    if baseline_end < baseline_start:
        return {"error": "baseline_end must be >= baseline_start"}

    n_years   = baseline_end - baseline_start + 1
    drop_temp = source.lower() in PRECIP_ONLY
    fs_kw     = {"fixed_season": fixed_season} if fixed_season else {}
    spei_kw   = (
        {
            "spei_scale_months": spei_scale_months,
            "spei_fit": spei_fit,
            "spei_ref_start": spei_ref_start,
            "spei_ref_end": spei_ref_end,
        }
        if spei_scale_months is not None else {}
    )

    print(f"\nFetching baseline {baseline_start}-{baseline_end} | source={source}")
    try:
        base = analyze_climate_statistics(
            location_coord=location,
            start_year=baseline_start, end_year=baseline_end,
            source=source, **fs_kw, **spei_kw)
    except Exception as exc:
        return {
            "error": (
                f"Baseline fetch/analysis failed for {source} "
                f"({baseline_start}-{baseline_end}): {type(exc).__name__}: {exc}"
            )
        }
    if isinstance(base, dict) and base.get("error"):
        return {
            "error": (
                f"Baseline fetch/analysis failed for {source} "
                f"({baseline_start}-{baseline_end}): {base['error']}"
            )
        }

    print(f"\nFetching focal year {focal_year} | source={source}")
    try:
        focal = analyze_climate_statistics(
            location_coord=location,
            start_year=focal_year, end_year=focal_year,
            source=source, **fs_kw, **spei_kw)
    except Exception as exc:
        return {
            "error": (
                f"Focal fetch/analysis failed for {source} "
                f"({focal_year}): {type(exc).__name__}: {exc}"
            )
        }
    if isinstance(focal, dict) and focal.get("error"):
        return {
            "error": (
                f"Focal fetch/analysis failed for {source} "
                f"({focal_year}): {focal['error']}"
            )
        }

    if not fixed_season:
        auto_guard_error = _auto_season_count_guard(
            base.get("season_statistics", []),
            focal.get("season_statistics", []),
        )
        if auto_guard_error:
            return {"error": auto_guard_error}

    # 1. raw_climate_summary
    raw_diff = _diff_raw(focal.get("raw_climate_summary", []),
                         base.get("raw_climate_summary",  []),
                         drop_temp)

    # 2. overall_statistics (annualise baseline)
    base_overall = _filter_overall_statistics_for_period_compare(
        _annualize(_round(base.get("overall_statistics", {}), 2), n_years)
    )
    focal_overall = _filter_overall_statistics_for_period_compare(
        _round(focal.get("overall_statistics", {}), 2)
    )
    overall_diff  = _diff_block(focal_overall, base_overall,
                                "focal_year", "baseline_avg", drop_temp)

    # 3. season_statistics
    base_seasons  = _round(base.get("season_statistics",  []), 2)
    focal_seasons = _round(focal.get("season_statistics", []), 2)
    season_diff: Optional[Dict[str, Any]] = None
    if base_seasons or focal_seasons:
        if fixed_season:
            # Per-window: group by season_number (statistics.py assigns 1,2,...
            # in the order of windows in --fixed-season, year-crossing included).
            labels = [w.strip() for w in fixed_season.split(",")]
            base_grp:  Dict[int, List[Dict]] = {}
            focal_grp: Dict[int, List[Dict]] = {}
            for s in base_seasons:
                base_grp.setdefault(s.get("season_number", 1), []).append(s)
            for s in focal_seasons:
                focal_grp.setdefault(s.get("season_number", 1), []).append(s)

            windows = []
            for sn in sorted(set(base_grp) | set(focal_grp)):
                label = labels[sn - 1] if 0 < sn <= len(labels) else f"window_{sn}"
                fb    = _agg_seasons(focal_grp.get(sn, []))
                bb    = _agg_seasons(base_grp.get(sn, []))
                windows.append({
                    "window":         label,
                    "season_number":  sn,
                    "n_baseline":     bb["_n"],
                    "n_focal":        fb["_n"],
                    "diff":           _diff_block(fb, bb, "focal", "baseline_avg",
                                                  drop_temp),
                })
            season_diff = {"windows": windows}
        else:
            fb = _agg_seasons(focal_seasons)
            bb = _agg_seasons(base_seasons)
            season_diff = {
                "n_baseline": bb["_n"],
                "n_focal":    fb["_n"],
                "diff":       _diff_block(fb, bb, "focal_avg", "baseline_avg",
                                          drop_temp),
            }
    # 4. annual_summary
    annual_diff = _diff_annual(focal.get("annual_summary", {}),
                               base.get("annual_summary",  {}),
                               focal_year)
    spei_diff = _diff_spei(
        focal.get("spei"),
        base.get("spei"),
    )
    return {
        "focal_year":           focal_year,
        "baseline_period":      f"{baseline_start}-{baseline_end}",
        "baseline_years":       n_years,
        "source":               source,
        "fixed_season":         fixed_season,
        "spei_scale_months":    spei_scale_months,
        "spei_fit":             spei_fit if spei_scale_months is not None else None,
        "temperature_excluded": drop_temp,
        "raw_climate_summary":  raw_diff,
        "overall_statistics":   overall_diff,
        "season_statistics":    season_diff,
        "annual_summary":       annual_diff,
        "spei":                 spei_diff,
    }

#  printing 
def _print_block(diff: Dict[str, Any]) -> None:
    if not diff:
        print("  (no comparable metrics)")
        return
    rows = []
    for cat, metrics in diff.items():
        for metric, vals in metrics.items():
            row = {"Category": cat, "Metric": metric}
            for k, v in vals.items():
                if k == "diff":  row["Δ"]  = f"{v:+.2f}"
                elif k == "pct": row["Δ%"] = _fmt_pct(v)
                else:            row[k]    = f"{v:.2f}"
            rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))

def print_report(r: Dict[str, Any]) -> None:
    if "error" in r:
        print(f"\nError: {r['error']}")
        return

    print(f"\n{'=' * 60}")
    print(f"COMPARISON: focal {r['focal_year']} vs baseline {r['baseline_period']}")
    print(f"{'=' * 60}")
    print(f"  Source        : {r['source']}")
    if r.get("fixed_season"):
        print(f"  Fixed seasons : {r['fixed_season']}")
    if r.get("temperature_excluded"):
        print("  [!] precipitation-only source -- temperature excluded.")

    print(f"\n--- 1. RAW CLIMATE SUMMARY ---")
    raw = r.get("raw_climate_summary", {})
    if raw:
        rows = [{"Variable": var, "Stat": stat,
                 "focal":    f"{v['focal']:.3f}",
                 "baseline": f"{v['baseline']:.3f}",
                 "Δ":        f"{v['diff']:+.3f}",
                 "Δ%":       _fmt_pct(v.get("pct"))}
                for var, stats in raw.items() for stat, v in stats.items()]
        print(pd.DataFrame(rows).to_string(index=False))
    else:
        print("  (no data)")

    print(f"\n--- 2. OVERALL STATISTICS  (baseline annualised) ---")
    _print_block(r.get("overall_statistics", {}))

    season = r.get("season_statistics")
    if season:
        print(f"\n--- 3. SEASON STATISTICS ---")
        if "windows" in season:
            for w in season["windows"]:
                print(f"\n  Window {w['window']} (season #{w['season_number']}, "
                      f"n_baseline={w['n_baseline']}, n_focal={w['n_focal']})")
                _print_block(w["diff"])
        else:
            print(f"  (n_baseline={season['n_baseline']}, n_focal={season['n_focal']})")
            _print_block(season["diff"])

    print(f"\n--- 4. ANNUAL SUMMARY ---")
    ann = r.get("annual_summary", {})
    arm = ann.get("annual_rain_mm")
    if arm:
        print(f"  Annual rainfall : focal={arm['focal']} mm | "
              f"baseline_avg={arm['baseline_avg']} mm | "
              f"Δ={arm['diff']:+.1f} ({_fmt_pct(arm.get('pct'))})")
    hs = ann.get("humid_status") or {}
    if hs:
        focal_state = ("humid" if hs.get("focal_is_humid") else
                       "not humid" if hs.get("focal_is_humid") is False else "n/a")
        print(f"  Humid status    : focal={focal_state} | "
              f"baseline={hs.get('baseline_humid', 'n/a')}")
        if hs.get("focal_humid_test"):
            print(f"                    test: {hs['focal_humid_test']}")

    spei = r.get("spei")
    if spei:
        print(f"\n--- 5. SPEI ---")
        summary = spei.get("summary") or {}
        if summary:
            print(
                f"  Mean SPEI       : focal={summary['focal_avg_spei']:.3f} | "
                f"baseline_avg={summary['baseline_avg_spei']:.3f} | "
                f"Δ={summary['diff']:+.3f} ({_fmt_pct(summary.get('pct'))})"
            )
        monthly = spei.get("monthly") or []
        if monthly:
            rows = []
            for row in monthly:
                rows.append({
                    "date": row["date"],
                    "month": row["month"],
                    "focal_spei": f"{row['focal_spei']:.3f}",
                    "baseline_avg_spei": f"{row['baseline_avg_spei']:.3f}",
                    "Δ": f"{row['diff']:+.3f}",
                    "Δ%": _fmt_pct(row.get("pct")),
                })
            print(pd.DataFrame(rows).to_string(index=False))
    print()

# CLI 
def main() -> None:
    p = argparse.ArgumentParser(
        description="Compare a focal year against a baseline period using statistics.py.",
        formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--location", required=True, help="lat,lon (e.g. -1.286,36.817)")
    p.add_argument("--baseline-start", type=int, required=True)
    p.add_argument("--baseline-end",   type=int, required=True)
    p.add_argument("--focal-year",     type=int, required=True)
    p.add_argument("--source", required=True,
                   help=f"One of: {', '.join(sorted(SUPPORTED))}")
    p.add_argument("--spei-scale-months", type=int, default=None,
                   help="Optional SPEI scale in months to compare alongside other statistics.")
    p.add_argument("--spei-fit", choices=["ub-pwm", "empirical"], default="ub-pwm",
                   help="SPEI fitting method when --spei-scale-months is used.")
    p.add_argument("--spei-ref-start", default=None,
                   help="Optional SPEI reference-period start date, e.g. 1991-01-01.")
    p.add_argument("--spei-ref-end", default=None,
                   help="Optional SPEI reference-period end date, e.g. 2020-12-31.")
    p.add_argument("--format", choices=["pandas", "json"], default="pandas",
                   help="Output format: human-readable table view or raw JSON.")
    p.add_argument("--fixed-season", default=None,
                   metavar="MM-DD:MM-DD[,MM-DD:MM-DD]",
                   help=("Optional. Passed through to statistics.py.\n"
                         "  Single        : '03-01:05-31'\n"
                         "  Two seasons   : '03-01:05-31,10-01:12-15'\n"
                         "  Year-crossing : '11-01:02-28'"))
    p.add_argument("--output", default=None, help="Write JSON results to this path")
    args = p.parse_args()

    try:
        lat, lon = (float(x) for x in args.location.replace(" ", ",").split(","))
    except ValueError:
        print("Error: --location must be 'lat,lon'"); sys.exit(1)

    result = compare(
        location=(lat, lon),
        baseline_start=args.baseline_start,
        baseline_end=args.baseline_end,
        focal_year=args.focal_year,
        source=args.source,
        fixed_season=args.fixed_season,
        spei_scale_months=args.spei_scale_months,
        spei_fit=args.spei_fit,
        spei_ref_start=args.spei_ref_start,
        spei_ref_end=args.spei_ref_end,
    )
    rendered = json.dumps(result, indent=2, default=str)
    if args.format == "json":
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered)
            print(f"✓ Saved: {output_path}")
        else:
            print(rendered)
    else:
        print_report(result)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered)
            print(f"✓ Saved: {output_path}")
    if "error" in result:
        sys.exit(1)

if __name__ == "__main__":
    main()

# Auto-detected seasons (no --fixed-season):
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2016 --focal-year=2015 --source=chirps_v2+chirts --output=results/nairobi_2015_vs_1991-2016_auto.json

# Single fixed season:
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2020 --focal-year=2019 --source=terraclimate --fixed-season=03-01:05-31 --output=results/nairobi_2019_MAM.json

# Two fixed seasons:
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2020 --focal-year=2019 --source=era_5 --fixed-season='03-01:05-31,10-01:12-15' --output=results/nairobi_2019_MAM_OND.json

# Year-crossing single window:
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2016 --focal-year=2016 --source=chirps_v2 --fixed-season=11-01:02-28 --output=results/nairobi_2016_NDJF.json
