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
Plain `chirps_v2` source is legacy behavior: statistics.py injects default tmax=25/tmin=15, so temperature is excluded from every diff section when chirps_v2 is source. Prefer `source=auto` or explicit `source=paired`.
"""

import sys
import json
import argparse
import shutil
import textwrap
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

import pandas as pd

from climate_tookit.climate_statistics.statistics import analyze_climate_statistics
from climate_tookit.climatology import (
    DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    DEFAULT_LIVESTOCK_TYPE,
    list_thi_livestock_profiles,
    resolve_thi_profile,
)
from climate_tookit.crop_calendar.ggcmi import CALENDAR_SYSTEM_CHOICES

CATEGORIES   = ["precipitation", "temperature", "et0", "water_balance", "vpd", "spei"]
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
PRECIP_ONLY  = {"chirps", "chirps_v2", "chirps_v3_daily_rnl", "imerg", "tamsat"}
SUPPORTED    = {"era_5", "agera_5", "chirps+chirts", "chirps_v2+chirts", "nasa_power",
                "chirps", "chirps_v2", "chirps_v3_daily_rnl", "chirts", "terraclimate", "imerg", "tamsat", "auto",
                "paired"}
XCLIM_FAMILY_LABELS = {
    "core_period_metrics": "Core standard period metrics",
    "precip_reference_indices": "Precipitation reference indices",
}
TERMINAL_TABLE_HEADER_ALIASES = {
    "Category": "cat",
    "Metric": "metric",
    "Variable": "var",
    "Stat": "stat",
    "future_ltm": "future",
    "baseline_ltm": "base",
    "future_avg": "future",
    "baseline_avg": "base",
    "focal": "focal",
    "focal_spei": "focal",
    "baseline_avg_spei": "base",
    "focal_spi": "focal",
    "baseline_avg_spi": "base",
    "Likely Δ": "likely_Δ",
}

# helpers
def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def _round(d: Any, n: int = 2) -> Any:
    if isinstance(d, dict):  return {k: _round(v, n) for k, v in d.items()}
    if isinstance(d, list):  return [_round(v, n) for v in d]
    return round(d, n) if _is_num(d) else d


def _terminal_width(default: int = 120) -> int:
    try:
        return shutil.get_terminal_size((default, 20)).columns
    except OSError:
        return default


def _short_cell(value: Any, max_len: int = 18) -> Any:
    if value is None or pd.isna(value):
        return "n/a"
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _drop_constant_display_columns(
    frame: pd.DataFrame,
    *,
    candidates: List[str],
) -> pd.DataFrame:
    display = frame.copy()
    for column in candidates:
        if column not in display.columns:
            continue
        values = display[column].dropna().astype(str).str.strip()
        if not values.empty and values.nunique() == 1:
            display = display.drop(columns=[column])
    return display


def _render_compact_table(
    frame: pd.DataFrame,
    *,
    drop_constant: Optional[List[str]] = None,
    truncate_columns: Optional[List[str]] = None,
    truncate_width: int = 18,
) -> str:
    display = frame.copy().fillna("n/a")
    if drop_constant:
        display = _drop_constant_display_columns(display, candidates=drop_constant)
    for column in truncate_columns or []:
        if column in display.columns:
            display[column] = display[column].map(
                lambda value: _short_cell(value, max_len=truncate_width)
            )
    display = display.rename(columns=TERMINAL_TABLE_HEADER_ALIASES)
    rendered = display.to_string(index=False)
    if max((len(line) for line in rendered.splitlines()), default=0) <= _terminal_width():
        return rendered
    for column in display.columns:
        if display[column].dtype == object:
            display[column] = display[column].map(
                lambda value: _short_cell(value, max_len=min(truncate_width, 14))
            )
    return display.to_string(index=False)


def _print_wrapped(prefix: str, text: str, *, indent: str = "") -> None:
    wrapped = textwrap.fill(
        text,
        width=max(72, _terminal_width() - len(prefix) - len(indent)),
        initial_indent=indent + prefix,
        subsequent_indent=indent + (" " * len(prefix)),
        break_long_words=False,
        break_on_hyphens=False,
    )
    print(wrapped)


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


def _mean(values: List[float], ndigits: int = 1) -> Optional[float]:
    clean = [float(v) for v in values if _is_num(v)]
    if not clean:
        return None
    return round(sum(clean) / len(clean), ndigits)


def _parse_fixed_season_windows(fixed_season: Optional[str]) -> List[Tuple[int, str, Tuple[int, int], Tuple[int, int]]]:
    windows: List[Tuple[int, str, Tuple[int, int], Tuple[int, int]]] = []
    if not fixed_season:
        return windows
    for idx, raw in enumerate(fixed_season.split(","), start=1):
        label = raw.strip()
        if not label:
            continue
        start_str, end_str = label.split(":")
        start_md = tuple(int(x) for x in start_str.split("-", 1))
        end_md = tuple(int(x) for x in end_str.split("-", 1))
        windows.append((idx, label, start_md, end_md))
    return windows


def _summarize_methodology_rows(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    methods = [
        row.get("water_balance_methodology")
        for row in rows or []
        if isinstance(row.get("water_balance_methodology"), dict)
    ]
    if not methods:
        return None

    requested_modes = sorted({
        method.get("count_window", {}).get("requested_mode")
        for method in methods
        if method.get("count_window", {}).get("requested_mode")
    })
    applied_modes = sorted({
        method.get("count_window", {}).get("applied_mode")
        for method in methods
        if method.get("count_window", {}).get("applied_mode")
    })
    counted_days = [
        method.get("count_window", {}).get("counted_days")
        for method in methods
        if _is_num(method.get("count_window", {}).get("counted_days"))
    ]
    counted_subseasons = [
        method.get("count_window", {}).get("counted_subseasons")
        for method in methods
        if _is_num(method.get("count_window", {}).get("counted_subseasons"))
    ]
    warnings = []
    for method in methods:
        for warning in method.get("warnings") or []:
            if warning and warning not in warnings:
                warnings.append(warning)

    return {
        "requested_modes": requested_modes,
        "applied_modes": applied_modes,
        "counted_days": {
            "mean": _mean(counted_days, 1),
            "min": min(counted_days) if counted_days else None,
            "max": max(counted_days) if counted_days else None,
            "n": len(counted_days),
        },
        "counted_subseasons": {
            "mean": _mean(counted_subseasons, 1),
            "min": min(counted_subseasons) if counted_subseasons else None,
            "max": max(counted_subseasons) if counted_subseasons else None,
            "n": len(counted_subseasons),
        },
        "warnings": warnings,
    }


def _merge_period_methodology(
    left_rows: List[Dict[str, Any]],
    right_rows: List[Dict[str, Any]],
    left_label: str,
    right_label: str,
) -> Optional[Dict[str, Any]]:
    left = _summarize_methodology_rows(left_rows)
    right = _summarize_methodology_rows(right_rows)
    if not left and not right:
        return None
    return {
        left_label: left,
        right_label: right,
    }


def _format_methodology_side(label: str, summary: Optional[Dict[str, Any]]) -> Optional[str]:
    if not summary:
        return None
    mode = ",".join(summary.get("applied_modes") or []) or "n/a"
    days = summary.get("counted_days") or {}
    day_bits = []
    if _is_num(days.get("mean")):
        day_bits.append(f"days_mean={days['mean']:.1f}")
    if _is_num(days.get("min")) and _is_num(days.get("max")):
        day_bits.append(f"days_range={int(days['min'])}-{int(days['max'])}")
    return f"{label}: mode={mode}" + (f" | {' | '.join(day_bits)}" if day_bits else "")


def _print_methodology_summary(methodology: Optional[Dict[str, Any]]) -> None:
    if not methodology:
        return
    parts = []
    for label in ("focal", "baseline_avg", "future_avg", "baseline_ltm", "future_ltm"):
        formatted = _format_methodology_side(label, methodology.get(label))
        if formatted:
            parts.append(formatted)
    if parts:
        print(f"    NDWS/WRSI method: {' ; '.join(parts)}")


def _has_custom_water_balance_metrics(payload: Dict[str, Any]) -> bool:
    season = payload.get("season_statistics")
    if isinstance(season, dict):
        if "windows" in season:
            for window in season["windows"] or []:
                diff = (window or {}).get("diff") or {}
                water_balance = diff.get("water_balance") or {}
                if any(key in water_balance for key in ("NDWS", "NDWL0", "WRSI")):
                    return True
        else:
            diff = season.get("diff") or {}
            water_balance = diff.get("water_balance") or {}
            if any(key in water_balance for key in ("NDWS", "NDWL0", "WRSI")):
                return True

    overall = payload.get("overall_statistics") or {}
    water_balance = overall.get("water_balance") if isinstance(overall, dict) else {}
    return any(key in (water_balance or {}) for key in ("NDWS", "NDWL0", "WRSI"))


def _collapse_xclim_reference_rows(rows: Optional[List[Dict[str, Any]]], *, round_n: int = 4) -> Dict[str, float]:
    pool: Dict[str, List[float]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if key == "period_start":
                continue
            if _is_num(value):
                pool.setdefault(key, []).append(float(value))
    return {
        key: round(sum(values) / len(values), round_n)
        for key, values in pool.items()
        if values
    }


def _xclim_reference_metric_map(payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    block = payload or {}
    out: Dict[str, Dict[str, float]] = {}
    core = _collapse_xclim_reference_rows(block.get("core_period_metrics"))
    precip = _collapse_xclim_reference_rows(block.get("precip_reference_indices"))
    if core:
        out["core_period_metrics"] = core
    if precip:
        out["precip_reference_indices"] = precip
    return out


def _xclim_reference_status(block: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = block or {}
    return {
        "available": bool(payload.get("available")),
        "core_period_status": payload.get("core_period_status"),
        "core_period_skip_reason": payload.get("core_period_skip_reason"),
        "precip_reference_status": payload.get("precip_reference_status"),
        "precip_reference_skip_reason": payload.get("precip_reference_skip_reason"),
    }


def _xclim_reference_compare_block(
    left: Optional[Dict[str, Any]],
    right: Optional[Dict[str, Any]],
    left_label: str,
    right_label: str,
) -> Dict[str, Any]:
    left_map = _xclim_reference_metric_map(left)
    right_map = _xclim_reference_metric_map(right)
    diff: Dict[str, Any] = {}
    for family, left_metrics in left_map.items():
        right_metrics = right_map.get(family)
        if not isinstance(right_metrics, dict):
            continue
        family_diff: Dict[str, Any] = {}
        for metric, left_value in left_metrics.items():
            right_value = right_metrics.get(metric)
            if not (_is_num(left_value) and _is_num(right_value)):
                continue
            delta = left_value - right_value
            pct = _percent_change(delta, right_value)
            family_diff[metric] = {
                left_label: round(float(left_value), 2),
                right_label: round(float(right_value), 2),
                "diff": round(float(delta), 2),
                "pct": round(float(pct), 2) if _is_num(pct) else None,
            }
        if family_diff:
            diff[family] = family_diff
    return {
        "status": {
            right_label: _xclim_reference_status(right),
            left_label: _xclim_reference_status(left),
        },
        "diff": diff,
    }


def _print_xclim_reference_compare(payload: Optional[Dict[str, Any]]) -> None:
    if not payload:
        return
    print(f"\n--- XCLIM STANDARD REFERENCES ---")
    status = payload.get("status") or {}
    for label in ("focal", "baseline_avg", "future_avg", "baseline_ltm", "future_ltm"):
        info = status.get(label)
        if not isinstance(info, dict):
            continue
        parts = [f"{label}: available={info.get('available')}"]
        if info.get("core_period_status"):
            parts.append(f"core={info.get('core_period_status')}")
        if info.get("precip_reference_status"):
            parts.append(f"precip={info.get('precip_reference_status')}")
        print("  " + " | ".join(parts))
        if info.get("core_period_skip_reason"):
            print(f"    core note   : {info['core_period_skip_reason']}")
        if info.get("precip_reference_skip_reason"):
            print(f"    precip note : {info['precip_reference_skip_reason']}")
    diff = payload.get("diff", {}) or {}
    for family in ("core_period_metrics", "precip_reference_indices"):
        metrics = diff.get(family)
        if not isinstance(metrics, dict) or not metrics:
            continue
        print(f"\n  {XCLIM_FAMILY_LABELS.get(family, family)}")
        rows = []
        for metric, vals in metrics.items():
            row = {"Metric": metric}
            for key, value in vals.items():
                if key == "diff":
                    row["Δ"] = f"{value:+.2f}"
                elif key == "pct":
                    row["Δ%"] = _fmt_pct(value)
                else:
                    row[key] = f"{value:.2f}"
            rows.append(row)
        print(pd.DataFrame(rows).to_string(index=False))


def _month_day_in_window(
    month: int,
    day: int,
    start_md: Tuple[int, int],
    end_md: Tuple[int, int],
) -> bool:
    current = (month, day)
    if start_md <= end_md:
        return start_md <= current <= end_md
    return current >= start_md or current <= end_md


def _seasonal_spei_period_block(
    spei_block: Optional[Dict[str, Any]],
    fixed_season: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not (spei_block and fixed_season):
        return None
    windows = _parse_fixed_season_windows(fixed_season)
    if not windows:
        return None

    pool: Dict[int, Dict[str, Any]] = {
        sn: {"window": label, "season_number": sn, "values": []}
        for sn, label, _, _ in windows
    }
    for row in spei_block.get("monthly_series") or []:
        date_str = row.get("date")
        value = row.get("spei")
        if not (_is_num(value) and isinstance(date_str, str) and len(date_str) >= 10):
            continue
        try:
            month = int(date_str[5:7])
            day = int(date_str[8:10])
        except ValueError:
            continue
        for sn, label, start_md, end_md in windows:
            if _month_day_in_window(month, day, start_md, end_md):
                pool[sn]["values"].append(float(value))
                break

    out_windows = []
    for sn, label, _, _ in windows:
        values = pool[sn]["values"]
        if not values:
            continue
        out_windows.append({
            "window": label,
            "season_number": sn,
            "n_months": len(values),
            "block": {
                "spei": {
                    "mean_spei": round(sum(values) / len(values), 3),
                }
            },
        })
    return {"windows": out_windows} if out_windows else None


def _merge_seasonal_spei_into_summary(
    season_summary: Optional[Dict[str, Any]],
    spei_summary: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not spei_summary:
        return season_summary
    if not season_summary:
        season_summary = {"windows": []}

    if "windows" in spei_summary:
        existing = {
            w.get("season_number", 1): w
            for w in season_summary.get("windows", [])
        }
        for sw in spei_summary.get("windows", []):
            sn = sw.get("season_number", 1)
            target = existing.get(sn)
            if target is None:
                target = {
                    "window": sw.get("window"),
                    "season_number": sn,
                    "block": {},
                }
                season_summary.setdefault("windows", []).append(target)
                existing[sn] = target
            target.setdefault("block", {}).update(sw.get("block", {}))
            if sw.get("n_months") is not None:
                target["spei_n_months"] = sw.get("n_months")
        if "windows" in season_summary:
            season_summary["windows"] = sorted(
                season_summary["windows"],
                key=lambda w: w.get("season_number", 1),
            )
        return season_summary

    season_summary.setdefault("block", {}).update(spei_summary.get("block", {}))
    return season_summary


def _merge_seasonal_spei_into_diff(
    season_diff: Optional[Dict[str, Any]],
    a_spei: Optional[Dict[str, Any]],
    b_spei: Optional[Dict[str, Any]],
    a_lbl: str,
    b_lbl: str,
) -> Optional[Dict[str, Any]]:
    if not (a_spei and b_spei):
        return season_diff
    if not season_diff:
        season_diff = {"windows": []}

    a_by_sn = {
        w.get("season_number", 1): w.get("block", {})
        for w in a_spei.get("windows", [])
    }
    b_by_sn = {
        w.get("season_number", 1): w.get("block", {})
        for w in b_spei.get("windows", [])
    }
    all_sns = sorted(set(a_by_sn) | set(b_by_sn))
    if "windows" not in season_diff:
        season_diff["windows"] = []
    existing = {
        w.get("season_number", 1): w
        for w in season_diff.get("windows", [])
    }
    labels = {
        w.get("season_number", 1): w.get("window")
        for w in (a_spei.get("windows", []) + b_spei.get("windows", []))
    }
    for sn in all_sns:
        diff_block = _diff_block(a_by_sn.get(sn, {}), b_by_sn.get(sn, {}), a_lbl, b_lbl)
        if not diff_block:
            continue
        target = existing.get(sn)
        if target is None:
            target = {
                "window": labels.get(sn, f"window_{sn}"),
                "season_number": sn,
                "n_baseline": 0,
                "n_focal": 0,
                "diff": {},
            }
            season_diff["windows"].append(target)
            existing[sn] = target
        target.setdefault("diff", {}).update(diff_block)
    season_diff["windows"] = sorted(
        season_diff["windows"],
        key=lambda w: w.get("season_number", 1),
    )
    return season_diff


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
        windows.append({
            "date": row.get("date"),
            "month": month,
            "focal_spei": round(float(focal_value), 3),
            "baseline_avg_spei": round(baseline_avg, 3),
            "diff": round(diff, 3),
            "pct": None,
        })

    focal_vals = [float(row["spei"]) for row in focal_series if _is_num(row.get("spei"))]
    base_vals = [float(row["spei"]) for row in baseline_series if _is_num(row.get("spei"))]
    summary = None
    if focal_vals and base_vals:
        focal_avg = sum(focal_vals) / len(focal_vals)
        base_avg = sum(base_vals) / len(base_vals)
        diff = focal_avg - base_avg
        summary = {
            "focal_avg_spei": round(focal_avg, 3),
            "baseline_avg_spei": round(base_avg, 3),
            "diff": round(diff, 3),
            "pct": None,
        }

    return {
        "config": {
            "focal": focal_cfg,
            "baseline": baseline_cfg,
        },
        "summary": summary,
        "monthly": windows,
    }


def _diff_spi(
    focal_spi: Optional[Dict[str, Any]],
    baseline_spi: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not (focal_spi and baseline_spi):
        return None
    focal_series = focal_spi.get("monthly_series") or []
    baseline_series = baseline_spi.get("monthly_series") or []
    focal_cfg = focal_spi.get("config") or {}
    baseline_cfg = baseline_spi.get("config") or {}

    baseline_by_month: Dict[int, List[float]] = {}
    for row in baseline_series:
        month = row.get("month")
        value = row.get("spi")
        if isinstance(month, int) and _is_num(value):
            baseline_by_month.setdefault(month, []).append(float(value))

    windows = []
    for row in focal_series:
        month = row.get("month")
        focal_value = row.get("spi")
        if not (isinstance(month, int) and _is_num(focal_value)):
            continue
        base_vals = baseline_by_month.get(month) or []
        if not base_vals:
            continue
        baseline_avg = sum(base_vals) / len(base_vals)
        diff = float(focal_value) - baseline_avg
        windows.append({
            "date": row.get("date"),
            "month": month,
            "focal_spi": round(float(focal_value), 3),
            "baseline_avg_spi": round(baseline_avg, 3),
            "diff": round(diff, 3),
            "pct": None,
        })

    focal_vals = [float(row["spi"]) for row in focal_series if _is_num(row.get("spi"))]
    base_vals = [float(row["spi"]) for row in baseline_series if _is_num(row.get("spi"))]
    summary = None
    if focal_vals and base_vals:
        focal_avg = sum(focal_vals) / len(focal_vals)
        base_avg = sum(base_vals) / len(base_vals)
        diff = focal_avg - base_avg
        summary = {
            "focal_avg_spi": round(focal_avg, 3),
            "baseline_avg_spi": round(base_avg, 3),
            "diff": round(diff, 3),
            "pct": None,
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
        for cat in ("precipitation", "temperature", "water_balance", "vpd", "livestock_heat_stress"):
            for m, v in (s.get(cat) or {}).items():
                if _is_num(v):
                    sums.setdefault(f"{cat}.{m}", []).append(float(v))
    out: Dict[str, Any] = {"_n": len(seasons)}
    for k, vs in sums.items():
        cat, m = k.split(".", 1)
        out.setdefault(cat, {})[m] = round(sum(vs) / len(vs), 2)
    first_heat = next(
        (
            s.get("livestock_heat_stress")
            for s in seasons
            if isinstance(s.get("livestock_heat_stress"), dict)
        ),
        None,
    )
    if isinstance(first_heat, dict):
        for meta_key in (
            "livestock_type",
            "livestock_label",
            "climate_profile",
            "threshold_source",
            "method_note",
        ):
            if first_heat.get(meta_key) is not None:
                out.setdefault("livestock_heat_stress", {})[meta_key] = first_heat.get(meta_key)
    first_vpd = next(
        (
            s.get("vpd")
            for s in seasons
            if isinstance(s.get("vpd"), dict)
        ),
        None,
    )
    if isinstance(first_vpd, dict) and first_vpd.get("method") is not None:
        out.setdefault("vpd", {})["method"] = first_vpd.get("method")
    methodology = _summarize_methodology_rows(seasons)
    if methodology:
        out["water_balance_methodology"] = methodology
    return out


def _resolve_livestock_reporting_metadata(
    *payloads: Dict[str, Any],
    requested_type: Optional[str] = None,
    requested_climate: Optional[str] = None,
) -> Dict[str, Any]:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        heat = ((payload.get("overall_statistics") or {}).get("livestock_heat_stress") or {})
        if isinstance(heat, dict) and heat:
            return {
                "livestock_type": heat.get("livestock_type") or requested_type,
                "livestock_label": heat.get("livestock_label"),
                "livestock_climate_profile_applied": heat.get("climate_profile") or requested_climate,
            }
        season_stats = payload.get("season_statistics") or []
        if isinstance(season_stats, list):
            for season in season_stats:
                heat = (season.get("livestock_heat_stress") or {})
                if isinstance(heat, dict) and heat:
                    return {
                        "livestock_type": heat.get("livestock_type") or requested_type,
                        "livestock_label": heat.get("livestock_label"),
                        "livestock_climate_profile_applied": heat.get("climate_profile") or requested_climate,
                    }
    return {
        "livestock_type": requested_type,
        "livestock_label": None,
        "livestock_climate_profile_applied": requested_climate,
    }


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


def _compare_season_detection_summary(
    base: Dict[str, Any],
    focal: Dict[str, Any],
    fixed_season: Optional[str],
) -> Dict[str, Any]:
    baseline_status = base.get("season_detection_status")
    focal_status = focal.get("season_detection_status")
    baseline_reasons = base.get("season_detection_reasons") or []
    focal_reasons = focal.get("season_detection_reasons") or []
    baseline_guidance = base.get("season_detection_guidance") or []
    focal_guidance = focal.get("season_detection_guidance") or []

    needs_prompt = (
        not fixed_season and
        (baseline_status == "prompt_required" or focal_status == "prompt_required")
    )
    has_warning = (
        not fixed_season and
        (baseline_status == "warn" or focal_status == "warn")
    )
    combined_guidance = list(dict.fromkeys([
        *baseline_guidance,
        *focal_guidance,
    ]))

    return {
        "baseline": {
            "status": baseline_status,
            "reasons": baseline_reasons,
            "guidance": baseline_guidance,
            "details": base.get("season_detection"),
        },
        "focal": {
            "status": focal_status,
            "reasons": focal_reasons,
            "guidance": focal_guidance,
            "details": focal.get("season_detection"),
        },
        "compare_status": (
            "prompt_required" if needs_prompt
            else "warn" if has_warning
            else "ok"
        ),
        "human_review_recommended": needs_prompt or has_warning,
        "fixed_season_recommended": needs_prompt,
        "guidance": combined_guidance,
    }


def _compare_season_detection_guard(summary: Dict[str, Any]) -> Optional[str]:
    if summary.get("compare_status") != "prompt_required":
        return None
    baseline = summary.get("baseline") or {}
    focal = summary.get("focal") or {}
    baseline_bits = []
    focal_bits = []
    if baseline.get("status"):
        baseline_bits.append(f"status={baseline['status']}")
    if baseline.get("reasons"):
        baseline_bits.append(f"reasons={','.join(baseline['reasons'])}")
    if focal.get("status"):
        focal_bits.append(f"status={focal['status']}")
    if focal.get("reasons"):
        focal_bits.append(f"reasons={','.join(focal['reasons'])}")
    return (
        "Auto season detection not reliable enough for compare_periods at this location/window. "
        f"Baseline[{'; '.join(baseline_bits) or 'n/a'}]. "
        f"Focal[{'; '.join(focal_bits) or 'n/a'}]. "
        "Re-run with --fixed-season for stable seasonal comparison."
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
            p = None if cat == "spei" else _percent_change(d, bv)
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
    precip_source:  Optional[str] = None,
    temp_source:    Optional[str] = None,
    crop_name:      Optional[str] = None,
    livestock_type: str = DEFAULT_LIVESTOCK_TYPE,
    livestock_climate_profile: str = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    livestock_elevation_override_m: Optional[float] = None,
    calendar_source: Optional[str] = None,
    calendar_system: str = "rf",
    spei_scale_months: Optional[int] = None,
    spei_fit: str = "ub-pwm",
    spei_ref_start: Optional[str] = None,
    spei_ref_end: Optional[str] = None,
    spi_scale_months: Optional[int] = None,
    spi_fit: str = "ub-pwm",
    spi_ref_start: Optional[str] = None,
    spi_ref_end: Optional[str] = None,
    workers: int = 1,
) -> Dict[str, Any]:
    """Run statistics.py for baseline + focal, diff the four sections."""
    if source.lower() not in SUPPORTED:
        return {"error": f"Source '{source}' not supported. "
                         f"Use one of: {', '.join(sorted(SUPPORTED))}"}
    if baseline_end < baseline_start:
        return {"error": "baseline_end must be >= baseline_start"}
    if source.lower() == "paired" and (not precip_source or not temp_source):
        return {
            "error": (
                "Source 'paired' requires both --precip-source and --temp-source."
            )
        }
    try:
        reporting_thi_profile = resolve_thi_profile(
            livestock_type=livestock_type,
            climate_profile=livestock_climate_profile,
            lat=location[0],
            lon=location[1],
            elevation_m=livestock_elevation_override_m,
            auto_fetch_elevation=True,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    calendar_system = str(calendar_system).lower()
    if calendar_system not in CALENDAR_SYSTEM_CHOICES:
        return {
            "error": (
                f"Invalid calendar_system '{calendar_system}'. "
                f"Choose from {', '.join(CALENDAR_SYSTEM_CHOICES)}."
            )
        }

    n_years   = baseline_end - baseline_start + 1
    drop_temp = source.lower() in PRECIP_ONLY and source.lower() != "paired"
    fs_kw     = {"fixed_season": fixed_season} if fixed_season else {}
    paired_kw = {}
    if precip_source:
        paired_kw["precip_source"] = precip_source
    if temp_source:
        paired_kw["temp_source"] = temp_source
    calendar_kw = {
        "crop_name": crop_name,
        "livestock_type": livestock_type,
        "livestock_climate_profile": livestock_climate_profile,
        "livestock_elevation_override_m": livestock_elevation_override_m,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
    }
    spei_kw   = (
        {
            "spei_scale_months": spei_scale_months,
            "spei_fit": spei_fit,
            "spei_ref_start": spei_ref_start,
            "spei_ref_end": spei_ref_end,
        }
        if spei_scale_months is not None else {}
    )
    spi_kw = (
        {
            "spi_scale_months": spi_scale_months,
            "spi_fit": spi_fit,
            "spi_ref_start": spi_ref_start,
            "spi_ref_end": spi_ref_end,
        }
        if spi_scale_months is not None else {}
    )

    print(f"\nFetching baseline {baseline_start}-{baseline_end} | source={source}")
    try:
        base = analyze_climate_statistics(
            location_coord=location,
            start_year=baseline_start, end_year=baseline_end,
            source=source, workers=workers, **fs_kw, **paired_kw, **calendar_kw, **spei_kw, **spi_kw)
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
            source=source, workers=workers, **fs_kw, **paired_kw, **calendar_kw, **spei_kw, **spi_kw)
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

    season_detection = _compare_season_detection_summary(
        base,
        focal,
        fixed_season,
    )
    season_detection_error = _compare_season_detection_guard(season_detection)
    if season_detection_error:
        return {"error": season_detection_error, "season_detection": season_detection}

    if not fixed_season:
        auto_guard_error = _auto_season_count_guard(
            base.get("season_statistics", []),
            focal.get("season_statistics", []),
        )
        if auto_guard_error:
            return {"error": auto_guard_error, "season_detection": season_detection}

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
                    "water_balance_methodology": _merge_period_methodology(
                        focal_grp.get(sn, []),
                        base_grp.get(sn, []),
                        "focal",
                        "baseline_avg",
                    ),
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
                "water_balance_methodology": _merge_period_methodology(
                    focal_seasons,
                    base_seasons,
                    "focal",
                    "baseline_avg",
                ),
                "diff":       _diff_block(fb, bb, "focal_avg", "baseline_avg",
                                          drop_temp),
            }
    season_diff = _merge_seasonal_spei_into_diff(
        season_diff,
        _seasonal_spei_period_block(focal.get("spei"), fixed_season),
        _seasonal_spei_period_block(base.get("spei"), fixed_season),
        "focal",
        "baseline_avg",
    )
    # 4. annual_summary
    annual_diff = _diff_annual(focal.get("annual_summary", {}),
                               base.get("annual_summary",  {}),
                               focal_year)
    xclim_diff = _xclim_reference_compare_block(
        focal.get("xclim_references"),
        base.get("xclim_references"),
        "focal",
        "baseline_avg",
    )
    spei_diff = _diff_spei(
        focal.get("spei"),
        base.get("spei"),
    )
    spi_diff = _diff_spi(
        focal.get("spi"),
        base.get("spi"),
    )
    livestock_meta = _resolve_livestock_reporting_metadata(
        focal,
        base,
        requested_type=livestock_type,
        requested_climate=reporting_thi_profile.get("climate_profile_applied") or livestock_climate_profile,
    )
    return {
        "focal_year":           focal_year,
        "baseline_period":      f"{baseline_start}-{baseline_end}",
        "baseline_years":       n_years,
        "source":               source,
        "fixed_season":         fixed_season,
        "precip_source":        precip_source,
        "temp_source":          temp_source,
        "crop_name":            crop_name,
        "livestock_type":       livestock_meta.get("livestock_type") or livestock_type,
        "livestock_label":      livestock_meta.get("livestock_label"),
        "livestock_climate_profile": livestock_climate_profile,
        "livestock_climate_profile_applied": livestock_meta.get("livestock_climate_profile_applied") or reporting_thi_profile.get("climate_profile_applied") or livestock_climate_profile,
        "calendar_source":      calendar_source,
        "calendar_system":      calendar_system,
        "baseline_calendar_preset_used": bool(base.get("calendar_preset_used")),
        "baseline_calendar_preset": base.get("calendar_preset"),
        "focal_calendar_preset_used": bool(focal.get("calendar_preset_used")),
        "focal_calendar_preset": focal.get("calendar_preset"),
        "spei_scale_months":    spei_scale_months,
        "spei_fit":             spei_fit if spei_scale_months is not None else None,
        "spi_scale_months":     spi_scale_months,
        "spi_fit":              spi_fit if spi_scale_months is not None else None,
        "temperature_excluded": drop_temp,
        "season_detection":     season_detection,
        "raw_climate_summary":  raw_diff,
        "overall_statistics":   overall_diff,
        "season_statistics":    season_diff,
        "annual_summary":       annual_diff,
        "xclim_references":     xclim_diff,
        "spei":                 spei_diff,
        "spi":                  spi_diff,
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
    print(
        _render_compact_table(
            pd.DataFrame(rows),
            drop_constant=["Category"],
        )
    )


def _print_season_detection_summary(summary: Optional[Dict[str, Any]]) -> None:
    if not summary:
        return

    def _print_details(label: str, payload: Dict[str, Any]) -> None:
        details = (payload or {}).get("details") or {}
        diagnostics = details.get("diagnostics") or {}
        counts = diagnostics.get("counts_by_year") or {}
        if counts:
            counts_text = ", ".join(
                f"{year}:{count}" for year, count in sorted(counts.items())
            )
            print(f"    {label}_counts={counts_text}")
        skips = diagnostics.get("skip_reasons_by_year") or {}
        if skips:
            print(f"    {label}_notes:")
            for year, note in sorted(skips.items()):
                print(f"      - {year}: {note}")

    print(f"  Season detect : {summary.get('compare_status', 'n/a')}")
    baseline = summary.get("baseline") or {}
    focal = summary.get("focal") or {}
    print(
        f"    baseline={baseline.get('status', 'n/a')}"
        + (
            f" [{', '.join(baseline.get('reasons') or [])}]"
            if baseline.get("reasons") else ""
        )
    )
    print(
        f"    focal={focal.get('status', 'n/a')}"
        + (
            f" [{', '.join(focal.get('reasons') or [])}]"
            if focal.get("reasons") else ""
        )
    )
    _print_details("baseline", baseline)
    _print_details("focal", focal)
    guidance = summary.get("guidance") or []
    if guidance:
        print("    guidance:")
        for item in guidance:
            _print_wrapped("- ", str(item), indent="      ")

def print_report(r: Dict[str, Any], *, detailed: bool = True) -> None:
    if "error" in r:
        print(f"\nError: {r['error']}")
        _print_season_detection_summary(r.get("season_detection"))
        return

    print(f"\n{'=' * 60}")
    print(f"COMPARISON: focal {r['focal_year']} vs baseline {r['baseline_period']}")
    print(f"{'=' * 60}")
    print(f"  Source        : {r['source']}")
    if r.get("source") == "paired":
        print(f"  Paired        : precip={r.get('precip_source')} | temp={r.get('temp_source')}")
    if r.get("fixed_season"):
        print(f"  Fixed seasons : {r['fixed_season']}")
    if r.get("crop_name"):
        print(f"  Crop          : {r['crop_name']}")
    if r.get("livestock_type"):
        climate_applied = r.get("livestock_climate_profile_applied") or r.get("livestock_climate_profile")
        climate_requested = r.get("livestock_climate_profile")
        climate_bits = [f"climate={climate_applied}"]
        if climate_requested and climate_requested != climate_applied:
            climate_bits.append(f"requested={climate_requested}")
        print(
            f"  Livestock     : {r['livestock_type']} | "
            + " | ".join(climate_bits)
        )
        heat_meta = (r.get("overall_statistics") or {}).get("livestock_heat_stress") or {}
        thi_note = heat_meta.get("method_note")
        thi_thresholds = heat_meta.get("threshold_source")
        if thi_note or thi_thresholds:
            parts = []
            if thi_note:
                parts.append(str(thi_note))
            if thi_thresholds:
                parts.append(f"thresholds={thi_thresholds}")
            print(f"  THI note      : {' | '.join(parts)}")
    if r.get("calendar_source"):
        print(f"  Calendar req. : {r['calendar_source']} | system={r.get('calendar_system')}")
    if r.get("baseline_calendar_preset_used") or r.get("focal_calendar_preset_used"):
        baseline_preset = r.get("baseline_calendar_preset") or {}
        focal_preset = r.get("focal_calendar_preset") or {}
        if baseline_preset:
            print(
                "  Baseline cal. : "
                f"{baseline_preset.get('calendar_source')} | "
                f"crop={baseline_preset.get('crop_name')} | "
                f"system={baseline_preset.get('calendar_system')} | "
                f"fixed={baseline_preset.get('fixed_season')}"
            )
        if focal_preset:
            print(
                "  Focal cal.    : "
                f"{focal_preset.get('calendar_source')} | "
                f"crop={focal_preset.get('crop_name')} | "
                f"system={focal_preset.get('calendar_system')} | "
                f"fixed={focal_preset.get('fixed_season')}"
            )
    if r.get("temperature_excluded"):
        print("  [!] precipitation-only source -- temperature excluded.")
    if _has_custom_water_balance_metrics(r):
        _print_wrapped(
            "  Water balance : ",
            "NDWS, NDWL0, and WRSI are custom crop-water-balance metrics, "
            "not standard xclim/ETCCDI indicators.",
        )
    _print_season_detection_summary(r.get("season_detection"))

    print(f"\n--- 1. RAW CLIMATE SUMMARY ---")
    raw = r.get("raw_climate_summary", {})
    if raw:
        rows = [{"Variable": var, "Stat": stat,
                 "focal":    f"{v['focal']:.3f}",
                 "baseline": f"{v['baseline']:.3f}",
                 "Δ":        f"{v['diff']:+.3f}",
                 "Δ%":       _fmt_pct(v.get("pct"))}
                for var, stats in raw.items() for stat, v in stats.items()]
        print(_render_compact_table(pd.DataFrame(rows), drop_constant=["Variable"]))
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
                _print_methodology_summary(w.get("water_balance_methodology"))
                _print_block(w["diff"])
        else:
            print(f"  (n_baseline={season['n_baseline']}, n_focal={season['n_focal']})")
            _print_methodology_summary(season.get("water_balance_methodology"))
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

    _print_xclim_reference_compare(r.get("xclim_references"))

    spei = r.get("spei")
    if spei:
        print(f"\n--- 5. SPEI (monthly/period summary, not seasonal) ---")
        summary = spei.get("summary") or {}
        if summary:
            print(
                f"  Mean SPEI       : focal={summary['focal_avg_spei']:.3f} | "
                f"baseline_avg={summary['baseline_avg_spei']:.3f} | "
                f"Δ={summary['diff']:+.3f}"
            )
        monthly = spei.get("monthly") or []
        if monthly and detailed:
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
            print(_render_compact_table(pd.DataFrame(rows)))
        elif monthly:
            print("  Monthly detail  : hidden in compact mode; rerun with --verbose.")
    spi = r.get("spi")
    if spi:
        print(f"\n--- 6. SPI (monthly/period summary, not seasonal) ---")
        summary = spi.get("summary") or {}
        if summary:
            print(
                f"  Mean SPI        : focal={summary['focal_avg_spi']:.3f} | "
                f"baseline_avg={summary['baseline_avg_spi']:.3f} | "
                f"Δ={summary['diff']:+.3f}"
            )
        monthly = spi.get("monthly") or []
        if monthly and detailed:
            rows = []
            for row in monthly:
                rows.append({
                    "date": row["date"],
                    "month": row["month"],
                    "focal_spi": f"{row['focal_spi']:.3f}",
                    "baseline_avg_spi": f"{row['baseline_avg_spi']:.3f}",
                    "Δ": f"{row['diff']:+.3f}",
                    "Δ%": _fmt_pct(row.get("pct")),
                })
            print(_render_compact_table(pd.DataFrame(rows)))
        elif monthly:
            print("  Monthly detail  : hidden in compact mode; rerun with --verbose.")
    print()

# CLI 
def main() -> int:
    p = argparse.ArgumentParser(
        description="Compare a focal year against a baseline period using statistics.py.",
        formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--location", required=True, help="lat,lon (e.g. -1.286,36.817)")
    p.add_argument("--baseline-start", type=int, required=True)
    p.add_argument("--baseline-end",   type=int, required=True)
    p.add_argument("--focal-year",     type=int, required=True)
    p.add_argument("--source", required=True,
                   help=(
                       f"One of: {', '.join(sorted(SUPPORTED))}. "
                       "Default historical daily path elsewhere in package is "
                       "chirps_v3_daily_rnl + agera_5 via auto or paired mode."
                   ))
    p.add_argument("--precip-source", default=None,
                   help="Required with --source=paired. Example: chirps_v2, chirps_v3_daily_rnl, imerg, or tamsat.")
    p.add_argument("--temp-source", default=None,
                   help="Required with --source=paired. Example: agera_5, era_5, or nasa_power.")
    p.add_argument("--crop", default=None,
                   help="Optional crop used when requesting external calendar presets such as GGCMI.")
    p.add_argument("--livestock-type", choices=list_thi_livestock_profiles(), default=DEFAULT_LIVESTOCK_TYPE,
                   help="Livestock THI profile to pass through to statistics workflow.")
    p.add_argument("--livestock-climate-profile", choices=["auto", "temperate", "tropical"],
                   default=DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
                   help="THI climate context. auto uses latitude plus highland elevation when available.")
    p.add_argument("--livestock-elevation-override-m", "--livestock-elevation-m",
                   dest="livestock_elevation_override_m", type=float, default=None,
                   help="Optional site elevation override, meters above sea level, for THI climate-context selection.")
    p.add_argument("--calendar-source", choices=["ggcmi"], default=None,
                   help="Optional crop-calendar preset source to use if auto season detection is not reliable.")
    p.add_argument("--calendar-system", choices=list(CALENDAR_SYSTEM_CHOICES), default="rf",
                   help="Crop-calendar system when --calendar-source is used.")
    p.add_argument("--spei-scale-months", type=int, default=None,
                   help="Optional SPEI scale in months to compare alongside other statistics.")
    p.add_argument("--spei-fit", choices=["ub-pwm", "empirical"], default="ub-pwm",
                   help="SPEI fitting method when --spei-scale-months is used.")
    p.add_argument("--spei-ref-start", default=None,
                   help="Optional SPEI reference-period start date, e.g. 1991-01-01.")
    p.add_argument("--spei-ref-end", default=None,
                   help="Optional SPEI reference-period end date, e.g. 2020-12-31.")
    p.add_argument("--spi-scale-months", type=int, default=None,
                   help="Optional SPI scale in months to compare alongside other statistics.")
    p.add_argument("--spi-fit", choices=["ub-pwm", "empirical"], default="ub-pwm",
                   help="SPI fitting method when --spi-scale-months is used.")
    p.add_argument("--spi-ref-start", default=None,
                   help="Optional SPI reference-period start date, e.g. 1991-01-01.")
    p.add_argument("--spi-ref-end", default=None,
                   help="Optional SPI reference-period end date, e.g. 2020-12-31.")
    p.add_argument(
        "--workers", type=int, default=1,
        help="Bounded historical GEE/Xee worker count for chunked fetches.",
    )
    p.add_argument("--format", choices=["pandas", "json"], default="pandas",
                   help="Output format: human-readable table view or raw JSON.")
    p.add_argument("--verbose", action="store_true",
                   help="Show detailed monthly SPEI/SPI tables in terminal output.")
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
        print("Error: --location must be 'lat,lon'")
        return 1

    result = compare(
        location=(lat, lon),
        baseline_start=args.baseline_start,
        baseline_end=args.baseline_end,
        focal_year=args.focal_year,
        source=args.source,
        fixed_season=args.fixed_season,
        precip_source=args.precip_source,
        temp_source=args.temp_source,
        crop_name=args.crop,
        livestock_type=args.livestock_type,
        livestock_climate_profile=args.livestock_climate_profile,
        livestock_elevation_override_m=args.livestock_elevation_override_m,
        calendar_source=args.calendar_source,
        calendar_system=args.calendar_system,
        spei_scale_months=args.spei_scale_months,
        spei_fit=args.spei_fit,
        spei_ref_start=args.spei_ref_start,
        spei_ref_end=args.spei_ref_end,
        spi_scale_months=args.spi_scale_months,
        spi_fit=args.spi_fit,
        spi_ref_start=args.spi_ref_start,
        spi_ref_end=args.spi_ref_end,
        workers=args.workers,
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
        print_report(result, detailed=args.verbose)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered)
            print(f"✓ Saved: {output_path}")
    if "error" in result:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

# Auto-detected seasons (no --fixed-season):
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2016 --focal-year=2015 --source=chirps_v2+chirts --output=results/nairobi_2015_vs_1991-2016_auto.json

# Single fixed season:
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2020 --focal-year=2019 --source=terraclimate --fixed-season=03-01:05-31 --output=results/nairobi_2019_MAM.json

# Two fixed seasons:
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2020 --focal-year=2019 --source=era_5 --fixed-season='03-01:05-31,10-01:12-15' --output=results/nairobi_2019_MAM_OND.json

# Year-crossing single window:
# python -m climate_tookit.compare_periods.periods --location=-1.286,36.817 --baseline-start=1991 --baseline-end=2016 --focal-year=2016 --source=chirps_v2 --fixed-season=11-01:02-28 --output=results/nairobi_2016_NDJF.json
