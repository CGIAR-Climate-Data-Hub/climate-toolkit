#!/usr/bin/env python3
"""Run a lightweight NEX-GDDP sanity matrix across representative sites.

This harness deliberately uses the active preprocess pipeline rather than the
higher-level climatology wrappers, because the wrappers currently have known
import-path issues under normal package execution.

Outputs:
- JSON payload with per-site / per-scenario ensemble summaries
- Markdown report with directional checks and site-realism checks
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from climate_tookit.fetch_data.preprocess_data.preprocess_data import preprocess_data
from climate_tookit.fetch_data.source_data.sources.nex_gddp import AVAILABLE_MODELS
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable


@dataclass(frozen=True)
class Site:
    name: str
    region: str
    lat: float
    lon: float
    note: str


SITES: list[Site] = [
    Site("Nairobi", "East Africa bimodal", -1.286, 36.817, "Moderate elevation, bimodal rainfall"),
    Site("Niamey", "Sahel", 13.5116, 2.1254, "Hot semi-arid Sahel"),
    Site("Addis Ababa", "Ethiopian highlands", 8.9806, 38.7578, "High-elevation cool tropical highlands"),
    Site("Cusco", "Andean highlands", -13.5319, -71.9675, "Cool Andean highlands"),
    Site("Lodwar", "East Africa dryland", 3.1190, 35.5973, "Hot arid lowland"),
]

SCENARIO_RUNS: dict[str, tuple[int, int, str]] = {
    "historical": (1991, 2020, "historical"),
    "ssp245": (2040, 2060, "ssp245"),
    "ssp585": (2040, 2060, "ssp585"),
}

VARIABLES = [
    ClimateVariable.precipitation,
    ClimateVariable.max_temperature,
    ClimateVariable.min_temperature,
]


def _annual_metrics(df: pd.DataFrame) -> dict[str, Any]:
    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    frame["tavg"] = (frame["max_temperature"] + frame["min_temperature"]) / 2.0

    annual = (
        frame.groupby("year", as_index=False)
        .agg(
            precipitation_total_mm=("precipitation", "sum"),
            tavg_c=("tavg", "mean"),
            tmax_c=("max_temperature", "mean"),
            tmin_c=("min_temperature", "mean"),
        )
    )
    monthly = (
        frame.groupby("month", as_index=False)
        .agg(
            precipitation_total_mm=("precipitation", "sum"),
            tavg_c=("tavg", "mean"),
        )
    )
    monthly["precipitation_total_mm"] = monthly["precipitation_total_mm"] / frame["year"].nunique()

    peak_precip_month = int(
        monthly.sort_values("precipitation_total_mm", ascending=False).iloc[0]["month"]
    )

    return {
        "mean_annual_precip_total_mm": round(float(annual["precipitation_total_mm"].mean()), 2),
        "mean_annual_tavg_c": round(float(annual["tavg_c"].mean()), 2),
        "mean_annual_tmax_c": round(float(annual["tmax_c"].mean()), 2),
        "mean_annual_tmin_c": round(float(annual["tmin_c"].mean()), 2),
        "peak_precip_month": peak_precip_month,
        "monthly_precip_mm": {
            int(row.month): round(float(row.precipitation_total_mm), 2)
            for row in monthly.itertuples(index=False)
        },
        "monthly_tavg_c": {
            int(row.month): round(float(row.tavg_c), 2)
            for row in monthly.itertuples(index=False)
        },
        "years": int(frame["year"].nunique()),
        "days": int(len(frame)),
    }


def _ensemble_metrics(site: Site, start_year: int, end_year: int, scenario: str) -> dict[str, Any]:
    per_model: dict[str, dict[str, Any]] = {}
    for model in AVAILABLE_MODELS:
        df = preprocess_data(
            source="nex_gddp",
            location_coord=(site.lat, site.lon),
            variables=VARIABLES,
            date_from=date(start_year, 1, 1),
            date_to=date(end_year, 12, 31),
            model=model,
            scenario=scenario,
        )
        per_model[model] = _annual_metrics(df)

    keys = [
        "mean_annual_precip_total_mm",
        "mean_annual_tavg_c",
        "mean_annual_tmax_c",
        "mean_annual_tmin_c",
    ]
    ensemble = {
        key: round(sum(per_model[m][key] for m in AVAILABLE_MODELS) / len(AVAILABLE_MODELS), 2)
        for key in keys
    }
    peak_months = [per_model[m]["peak_precip_month"] for m in AVAILABLE_MODELS]
    ensemble["peak_precip_month"] = max(set(peak_months), key=peak_months.count)
    ensemble["models"] = len(AVAILABLE_MODELS)
    ensemble["years"] = start_year, end_year
    return {
        "ensemble": ensemble,
        "per_model": per_model,
    }


def _directional_checks(site_payload: dict[str, Any]) -> list[dict[str, Any]]:
    hist = site_payload["historical"]["ensemble"]
    s245 = site_payload["ssp245"]["ensemble"]
    s585 = site_payload["ssp585"]["ensemble"]
    checks = []

    for metric in ("mean_annual_tavg_c", "mean_annual_tmax_c", "mean_annual_tmin_c"):
        ok = hist[metric] < s245[metric] < s585[metric]
        checks.append({
            "check": f"{metric}: historical < ssp245 < ssp585",
            "ok": ok,
            "values": [hist[metric], s245[metric], s585[metric]],
        })

    # This is backend-specific, not climate-science-general.
    precip_ok = hist["mean_annual_precip_total_mm"] > s245["mean_annual_precip_total_mm"] > s585["mean_annual_precip_total_mm"]
    checks.append({
        "check": "precipitation declines historical > ssp245 > ssp585 (current backend expectation)",
        "ok": precip_ok,
        "values": [
            hist["mean_annual_precip_total_mm"],
            s245["mean_annual_precip_total_mm"],
            s585["mean_annual_precip_total_mm"],
        ],
    })
    return checks


def _site_realism_checks(results: dict[str, Any]) -> list[dict[str, Any]]:
    hist = {site: payload["historical"]["ensemble"] for site, payload in results["sites"].items()}
    tavg_values = {site: hist[site]["mean_annual_tavg_c"] for site in hist}
    precip_values = {site: hist[site]["mean_annual_precip_total_mm"] for site in hist}
    peak_months = {site: hist[site]["peak_precip_month"] for site in hist}

    checks = []
    tavg_range = round(max(tavg_values.values()) - min(tavg_values.values()), 2)
    precip_range = round(max(precip_values.values()) - min(precip_values.values()), 2)
    checks.append({
        "check": "historical inter-site mean annual temperature spread >= 5C",
        "ok": tavg_range >= 5.0,
        "value": tavg_range,
    })
    checks.append({
        "check": "historical inter-site mean annual precipitation spread >= 300 mm",
        "ok": precip_range >= 300.0,
        "value": precip_range,
    })
    checks.append({
        "check": "Addis Ababa cooler than Lodwar",
        "ok": tavg_values["Addis Ababa"] < tavg_values["Lodwar"],
        "value": [tavg_values["Addis Ababa"], tavg_values["Lodwar"]],
    })
    checks.append({
        "check": "Cusco cooler than Niamey",
        "ok": tavg_values["Cusco"] < tavg_values["Niamey"],
        "value": [tavg_values["Cusco"], tavg_values["Niamey"]],
    })
    checks.append({
        "check": "Nairobi wetter than Lodwar",
        "ok": precip_values["Nairobi"] > precip_values["Lodwar"],
        "value": [precip_values["Nairobi"], precip_values["Lodwar"]],
    })
    checks.append({
        "check": "Not all sites share same peak precipitation month",
        "ok": len(set(peak_months.values())) > 1,
        "value": peak_months,
    })
    return checks


def build_report() -> dict[str, Any]:
    sites_payload: dict[str, Any] = {}
    for site in SITES:
        scenario_payload: dict[str, Any] = {}
        for label, (start_year, end_year, scenario) in SCENARIO_RUNS.items():
            scenario_payload[label] = _ensemble_metrics(site, start_year, end_year, scenario)
        sites_payload[site.name] = {
            "region": site.region,
            "lat": site.lat,
            "lon": site.lon,
            "note": site.note,
            **scenario_payload,
        }

    report = {
        "backend_context": (
            "Active nex_gddp backend is currently synthetic placeholder data. "
            "Scenario directionality can still be tested, but spatial realism "
            "and seasonal realism should not be treated as production-valid."
        ),
        "sites": sites_payload,
    }

    directional: dict[str, list[dict[str, Any]]] = {}
    for site_name, payload in sites_payload.items():
        directional[site_name] = _directional_checks(payload)
    report["directional_checks"] = directional
    report["site_realism_checks"] = _site_realism_checks(report)
    return report


def _md_check_line(check: dict[str, Any]) -> str:
    status = "PASS" if check["ok"] else "FAIL"
    value = check.get("value", check.get("values"))
    return f"- `{status}` {check['check']} | `{value}`"


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# NEX-GDDP Sanity Matrix")
    lines.append("")
    lines.append(report["backend_context"])
    lines.append("")
    lines.append("## Sites")
    lines.append("")
    lines.append("| Site | Region | Historical precip (mm) | Historical Tavg (C) | Historical peak precip month | SSP245 Tavg | SSP585 Tavg |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for site_name, payload in report["sites"].items():
        hist = payload["historical"]["ensemble"]
        s245 = payload["ssp245"]["ensemble"]
        s585 = payload["ssp585"]["ensemble"]
        lines.append(
            f"| {site_name} | {payload['region']} | "
            f"{hist['mean_annual_precip_total_mm']:.2f} | "
            f"{hist['mean_annual_tavg_c']:.2f} | "
            f"{hist['peak_precip_month']} | "
            f"{s245['mean_annual_tavg_c']:.2f} | "
            f"{s585['mean_annual_tavg_c']:.2f} |"
        )

    lines.append("")
    lines.append("## Directional Checks")
    lines.append("")
    for site_name, checks in report["directional_checks"].items():
        lines.append(f"### {site_name}")
        for check in checks:
            lines.append(_md_check_line(check))
        lines.append("")

    lines.append("## Site Realism Checks")
    lines.append("")
    for check in report["site_realism_checks"]:
        lines.append(_md_check_line(check))
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NEX-GDDP sanity matrix harness")
    parser.add_argument(
        "--output-prefix",
        default="nex_sanity_matrix",
        help="Prefix for JSON and Markdown outputs",
    )
    args = parser.parse_args()

    report = build_report()
    json_path = Path(f"{args.output_prefix}.json")
    md_path = Path(f"{args.output_prefix}.md")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
