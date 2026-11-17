"""Standalone diagnostics for the station comparison workflow."""

from __future__ import annotations

import io
import os
from html import escape
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from .io import data_uri, write_html
from .labels import label_for
from .styles import LINES


def _period_figure(periods, variable):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
    from matplotlib.figure import Figure

    fig = Figure(figsize=(10, 4.8), layout="constrained")
    FigureCanvasAgg(fig)
    axes = fig.subplots(2, 1, sharex=True)
    for ax, scale in zip(axes, ("monthly", "seasonal")):
        rows = periods[periods.timescale == scale]
        complete = rows.paired_days.eq(rows.calendar_days)
        ax.vlines(rows.period_start, rows.station, rows.grid, color="0.72", linewidth=1, zorder=1)
        for column, color, marker in (("station", LINES[3], "o"), ("grid", LINES[1], "^")):
            for mask, fill in ((complete, color), (~complete, "white")):
                ax.scatter(
                    rows.period_start[mask],
                    rows[column][mask],
                    s=25,
                    marker=marker,
                    facecolors=fill,
                    edgecolors=color,
                    linewidths=1,
                    label=column.title() if fill == color else None,
                )
        ax.set_ylabel("Total" if variable == "precipitation" else "Mean")
        ax.set_title(f"{scale.title()} • {label_for(variable)}", loc="left", fontsize=11)
        ax.grid(axis="y", alpha=0.2)
    axes[0].legend(ncols=2, loc="best", fontsize=8)
    locator = AutoDateLocator(minticks=3, maxticks=8)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(ConciseDateFormatter(locator))
    axes[-1].set_xlabel("Start of calendar period")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110)
    return data_uri("image/png", buffer.getvalue())


def _metrics_table(report, pooled):
    if pooled:
        keys = (
            "pooled_daily_metrics",
            "pooled_monthly_metrics",
            "pooled_seasonal_metrics",
            "pooled_annual_metrics",
        )
    else:
        keys = ("metrics", "monthly_metrics", "seasonal_metrics", "annual_metrics")
    rows = []
    for key in keys:
        for row in report.get(key, []):
            rows.append(
                {
                    "Station": row["station_id"],
                    "Grid": row["grid_source"],
                    "Variable": label_for(row["variable"]),
                    "Scale": row.get("timescale", "daily"),
                    "Paired days": row.get("overlap_days"),
                    "Periods": row.get("period_count"),
                    "Bias": row["bias"],
                    "MAE": row["mae"],
                    "RMSE": row["rmse"],
                    "Correlation": row.get("correlation"),
                    "Wet hits": row.get("wet_day_hits"),
                    "Misses": row.get("wet_day_misses"),
                    "False alarms": row.get("wet_day_false_alarms"),
                    "Hit rate": row.get("wet_day_hit_rate"),
                    "Critical success index": row.get("critical_success_index"),
                }
            )
    if not rows:
        return ""
    table = pd.DataFrame(rows).dropna(how="all", axis=1)
    return table.to_html(index=False, border=0, na_rep="—", float_format=lambda x: f"{x:g}")


def write_station_diagnostics(report, period_tables, path: Path):
    """Write one portable HTML file. Only replace the destination after rendering."""
    parts = [
        """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Station and grid comparison</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font:16px/1.45 system-ui,sans-serif;color:#182b36;max-width:70rem;margin:auto;padding:2rem}
img{width:100%;max-width:62rem}section{overflow-x:auto}table{border-collapse:collapse;font-size:.85rem}
td,th{padding:.3rem .5rem;border-bottom:1px solid #cad3d7;text-align:right}
th{background:#edf3f4}h2{margin-top:2rem}</style><h1>Station and grid comparison</h1>""",
        f"<p>{escape(report['date_from'])} to {escape(report['date_to'])} · "
        f"Station source: {escape(report['station_source'])}</p>",
    ]
    candidate_map = (report.get("candidate_review_artifacts") or {}).get("html")
    if candidate_map:
        link = quote(Path(os.path.relpath(candidate_map, path.parent)).as_posix())
        parts.append(f'<p><a href="{link}">Open candidate station map</a></p>')
    if "paired" in report["grid_sources"]:
        pairs = {
            "precipitation": report.get("precip_source"),
            "temperature": report.get("temp_source"),
        }
        parts.append(
            "<p>Configured paired sources: "
            + ", ".join(f"{variable} — {escape(str(source))}" for variable, source in pairs.items())
            + ".</p>"
        )
    notes = [
        *report["warnings"],
        *(f"{r['station_id']} / {r['grid_source']}: {r['error']}" for r in report["grid_failures"]),
    ]
    if notes:
        parts.append("<details open><summary>Coverage and source warnings</summary><ul>")
        parts.extend(f"<li>{escape(str(note))}</li>" for note in notes)
        parts.append("</ul></details>")
    if period_tables:
        periods = pd.concat(period_tables, ignore_index=True)
        csv = periods.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")
        parts.extend(
            [
                '<p><a download="station-grid-periods.csv" href="'
                + data_uri("text/csv", csv)
                + '">Download paired monthly and seasonal values (CSV)</a></p>',
                "<p>Circles show observations and triangles show grid values. Hollow symbols "
                "mark periods with missing paired days, including partial periods at the edges. "
                "Rainfall totals cover paired days only. Seasons start in December, March, June "
                "and September. December belongs to the following year’s DJF. Different products "
                "can have different paired days. Check coverage before comparing scores.</p>",
            ]
        )
        station_names = {s["station_id"]: s.get("station_name") for s in report["station_summary"]}
        for (source, variable), group in periods.groupby(["grid_source", "variable"], sort=True):
            single = group[group.reference == "station"]
            for (reference, station), series in group.groupby(
                ["reference", "station_id"], sort=False
            ):
                if reference == "pooled":
                    if single.station_id.nunique() == 1:
                        continue
                    name = "Pooled daily mean across contributing stations"
                else:
                    name = str(station_names.get(station) or station)
                    if name != str(station):
                        name += f" ({station})"
                title = escape(f"{name} · {source} · {label_for(variable)}")
                image = _period_figure(series, variable)
                parts.append(
                    f'<h2>{title}</h2><img alt="Monthly and seasonal pairs for {title}" src="{image}">'
                )
        parts.append(
            f"<p>Bias is grid minus station. MAE and RMSE use the variable’s units. "
            f"Wet-day threshold: {report['wet_day_threshold_mm']:g} mm/day. "
            "A dash means unavailable. Annual values can cover partial years.</p>"
        )
        for pooled, heading in (
            (False, "Station metrics"),
            (True, "Pooled metrics (daily station mean)"),
        ):
            parts.append(f"<section><h2>{heading}</h2>{_metrics_table(report, pooled)}</section>")
    else:
        parts.append("<p>No paired station and grid observations in this window.</p>")
    parts.append("</html>")
    write_html(path, "\n".join(parts))
