"""Period and season uncertainty figures from NEX-GDDP model comparisons."""

from __future__ import annotations

import io
import math
from html import escape
from pathlib import Path

import pandas as pd

from .io import data_uri, write_html
from .styles import LINES

# Each input is annualized or averaged over individual seasons by ensemble_compare.
METRICS = (
    ("precipitation", "total_mm", "Precipitation", "mm"),
    ("temperature", "mean_tmax", "Mean daily Tmax", "°C"),
    ("temperature", "mean_tmin", "Mean daily Tmin", "°C"),
    ("water_balance", "total_balance", "Precipitation − ET₀", "mm"),
)


def _period_table(report):
    model_blocks = {}
    windows = ["Annual"]
    fixed = report.get("fixed_season")
    for i, label in enumerate(fixed.split(",") if fixed else [], 1):
        windows.append(f"Season {i} · {label.strip()}")
    for row in report.get("per_model_results", []):
        model = row.get("_model") or row["model"]
        blocks = {"Annual": row.get("overall_statistics") or {}}
        seasons = row.get("season_statistics") or {}
        if "windows" in seasons:
            for w in seasons["windows"]:
                name = f"Season {w['season_number']} · {w['window']}"
                blocks[name] = w.get("diff") or {}
        elif seasons.get("diff"):
            blocks["Detected seasons (pooled)"] = seasons["diff"]
        model_blocks[model] = blocks
        windows.extend(name for name in blocks if name not in windows)

    failures = {f["model"] for f in report.get("models_failed", [])}
    models = sorted(set(report.get("models_used", [])) | model_blocks.keys() | failures)
    rows = []
    for window in windows:
        for category, key, metric, unit in METRICS:
            for model in models:
                block = model_blocks.get(model, {}).get(window, {})
                values = (block.get(category) or {}).get(key) or {}
                # Keep the workflow's stored delta (rounded from its source precision).
                triple = [values.get(k) for k in ("baseline_avg", "future_avg", "diff")]
                valid = all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in triple
                )
                status = "paired" if valid else ("failed" if model in failures else "missing")
                rows.append(
                    (model, window, metric, unit, status, *(triple if valid else [None] * 3))
                )
    return pd.DataFrame(
        rows,
        columns=["model", "window", "metric", "unit", "status", "baseline", "future", "change"],
    )


def _interval(ax, values, y, color):
    # Offset model dots from the interval so values inside the IQR remain visible.
    dot_y = y + 0.18 if len(values) > 1 else y
    ax.scatter(values, [dot_y] * len(values), s=14, alpha=0.65, color=color, zorder=2)
    if len(values) > 1:
        p10, p25, median, p75, p90 = values.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        ax.hlines(y, p10, p90, color=color, lw=2)
        ax.hlines(y, p25, p75, color=color, lw=7)
        ax.plot(median, y, marker="|", color="black", markersize=12, zorder=3)


def _spread_figure(rows):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator

    fig = Figure(figsize=(10, 7.5), layout="constrained")
    FigureCanvasAgg(fig)
    axes = fig.subplots(len(METRICS), 2)
    for (_, _, metric, unit), (levels, changes) in zip(METRICS, axes):
        group = rows[rows.metric == metric]
        paired = group[group.status == "paired"]
        levels.set_title(f"{metric} ({unit})", loc="left")
        changes.set_title(f"Change ({unit}) · {len(paired)}/{len(group)} models", loc="left")
        _interval(levels, paired.baseline, 1, LINES[3])
        _interval(levels, paired.future, 0, LINES[1])
        _interval(changes, paired.change, 0, LINES[0])
        changes.axvline(0, color="0.6", ls=":", zorder=0)
        levels.set_yticks([1, 0], ["Baseline", "Future"])
        changes.set_yticks([])
        levels.set_ylim(-0.7, 1.7)
        changes.set_ylim(-1, 1)
        for ax in (levels, changes):
            ax.xaxis.set_major_locator(MaxNLocator(6))
            ax.grid(axis="x", alpha=0.16)
            if paired.empty:
                ax.text(0.5, 0.5, "No paired models", ha="center", transform=ax.transAxes)
    image = io.BytesIO()
    fig.savefig(image, format="png", dpi=115)
    return data_uri("image/png", image.getvalue())


def write_ensemble_uncertainty(results: dict, path: str | Path) -> None:
    """Render an ensemble_compare result or the CLI's scenario-keyed JSON mapping."""
    scenarios = (
        {results.get("scenario", "Ensemble"): results}
        if "per_model_results" in results or "error" in results
        else results
    )
    parts = [
        """<!doctype html><html lang="en"><meta charset="utf-8">
<title>NEX-GDDP ensemble uncertainty</title><meta name="viewport" content="width=device-width">
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:68rem;margin:auto;padding:2rem;color:#21323e}
img{width:100%}section{overflow-x:auto}td,th{padding:.25rem .6rem;text-align:left}
tr:nth-child(even){background:#eef3f5}h2{margin-top:2rem}</style><h1>NEX-GDDP ensemble uncertainty</h1>
<p>Dots show individual models. Thin lines span the 10th–90th percentiles, thick lines the
25th–75th, and ticks mark medians. All three distributions use the same paired models.
Change is future minus baseline within each model. Intervals describe model spread, not
probabilities or confidence limits. A single contributing model appears as one dot.</p>"""
    ]
    for scenario, report in scenarios.items():
        if not isinstance(report, dict):
            raise ValueError(
                "Expected a periods-ensemble result or a mapping of scenarios to results."
            )
        parts.append(f"<h2>{escape(str(scenario))}</h2>")
        failures = report.get("failed_models") or report.get("models_failed") or []
        for failure in failures:
            parts.append(
                f"<p>{escape(str(failure['model']))} failed: "
                f"{escape(str(failure.get('error', '')))}</p>"
            )
        if "error" in report:
            parts.append(f"<p>{escape(str(report['error']))}</p>")
            continue
        if "per_model_results" not in report:
            raise ValueError(
                "Ensemble uncertainty requires a periods-ensemble result with per_model_results."
            )
        loc = report.get("metadata", {}).get("location") or {}
        location = f" · {loc['lat']}, {loc['lon']}" if "lat" in loc and "lon" in loc else ""
        parts.append(
            f"<p>Baseline {escape(str(report['baseline_period']))} · "
            f"Future {escape(str(report['future_period']))}{escape(location)}</p>"
        )
        detection = report.get("season_detection") or {}
        if detection.get("human_review_recommended"):
            parts.append("<p>Season detection flagged this comparison for human review.</p>")
        rows = _period_table(report)
        csv = (
            rows.assign(
                scenario=scenario,
                baseline_period=report["baseline_period"],
                future_period=report["future_period"],
            )
            .to_csv(index=False)
            .encode()
        )
        parts.append(
            '<a download="ensemble-periods.csv" href="'
            + data_uri("text/csv", csv)
            + '">Download model values and contribution status (CSV)</a>'
        )
        for window, group in rows.groupby("window", sort=False):
            title = escape(window)
            image = _spread_figure(group)
            parts.append(
                f'<h3>{title}</h3><img alt="Period distributions and paired changes for {title}" src="{image}">'
            )
            coverage = group.pivot(index="model", columns="metric", values="status")
            coverage.columns.name = None
            parts.append(
                "<details><summary>Model contributions</summary><section>"
                + coverage.to_html(border=0)
                + "</section></details>"
            )
    write_html(Path(path), "\n".join(parts) + "</html>")
