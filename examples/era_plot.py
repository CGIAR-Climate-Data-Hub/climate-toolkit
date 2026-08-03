"""Plot an ERA LTE workflow comparison CSV as PNG charts.

The workflow writes a CSV; this turns that CSV into pictures. Run the workflow
first, then plot its output::

    python examples/era_lte_workflow.py lte_summary_expanded.csv --out full.csv
    python examples/era_plot.py full.csv --out era_plots.png
    open era_plots.png            # macOS  (Linux: xdg-open, Windows: start)

Draws whatever the CSV supports:
* **Crop yield by crop** — mean ``reported_yield`` (t/ha) per crop.
* **Season-1 rainfall agreement** — toolkit seasonal mean vs ERA-reported
  ``Site.MSP.S1`` per site, against the 1:1 line.

Needs a CSV with yield and/or rainfall columns — i.e. run the workflow against
``lte_summary_expanded.csv`` (both) or a season/rainfall export.
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")  # no display needed; writes a file
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

GREEN, BLUE = "#2f7d52", "#2f6f9f"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="A comparison CSV written by era_lte_workflow.py")
    ap.add_argument("--out", default="era_plots.png", help="Output PNG path")
    ap.add_argument("--top", type=int, default=12, help="Max crops to show")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, low_memory=False)
    for c in ("reported_yield", "reported_rain_mm", "tk_rain_total_mm", "season_number"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    panels = []
    if "crop_name" in df and df.get("reported_yield", pd.Series(dtype=float)).notna().any():
        panels.append("yield")
    if "reported_rain_mm" in df and df.get("tk_rain_total_mm", pd.Series(dtype=float)).notna().any():
        panels.append("rain")
    if not panels:
        raise SystemExit(
            "Nothing to plot: this CSV has no yield or rainfall columns. Run the "
            "workflow against lte_summary_expanded.csv for both."
        )

    fig, axes = plt.subplots(1, len(panels), figsize=(6.2 * len(panels), 5))
    axes = [axes] if len(panels) == 1 else list(axes)
    ax_i = 0

    if "yield" in panels:
        ax = axes[ax_i]; ax_i += 1
        crop = (
            df.dropna(subset=["reported_yield"])
            .groupby("crop_name")["reported_yield"].mean()
            .sort_values().tail(args.top)
        )
        ax.barh(crop.index.astype(str), crop.values, color=GREEN)
        for y, v in enumerate(crop.values):
            ax.text(v, y, f" {v:.1f}", va="center", fontsize=8)
        ax.set_title("Mean crop yield by crop")
        ax.set_xlabel("t/ha")

    if "rain" in panels:
        ax = axes[ax_i]; ax_i += 1
        s1 = df[df["season_number"] == 1] if "season_number" in df else df
        site = (
            s1.dropna(subset=["reported_rain_mm", "tk_rain_total_mm"])
            .groupby("site_id").agg(reported=("reported_rain_mm", "first"),
                                    tk=("tk_rain_total_mm", "mean"))
        )
        mx = max(site["reported"].max(), site["tk"].max()) * 1.05 if len(site) else 1.0
        ax.plot([0, mx], [0, mx], "--", color="gray", linewidth=1, label="1:1")
        ax.scatter(site["reported"], site["tk"], color=BLUE, alpha=0.8, edgecolor="white")
        ax.set_xlim(0, mx); ax.set_ylim(0, mx)
        ax.set_title(f"Season-1 rainfall: toolkit vs ERA ({len(site)} sites)")
        ax.set_xlabel("ERA-reported Site.MSP.S1 (mm)")
        ax.set_ylabel("toolkit seasonal mean (mm)")
        ax.legend(loc="upper left", fontsize=8)

    fig.tight_layout()
    fig.savefig(args.out, dpi=130)
    print(f"wrote {args.out}  (open it: `open {args.out}`)")


if __name__ == "__main__":
    main()
