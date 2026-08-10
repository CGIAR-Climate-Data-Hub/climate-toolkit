"""Combined multi-site view: one toolkit variable vs yield across ERA sites.

Takes a year-matched table from ``era_yield_analysis.py`` (with several sites)
and lays out one panel per site — the chosen toolkit variable as bars, yield
lines per treatment — so sites can be compared side by side.

    # build a table spanning several sites, then plot them together
    python examples/era_yield_analysis.py lte_final.csv --limit 300 --out era_many.csv
    python examples/era_yield_multisite.py era_many.csv --variable tk_rain_total_mm --out era_multisite.png

    # or combine per-site CSVs you already made:
    python examples/era_yield_multisite.py era_gourton.csv era_Makoka.csv era_Kouve.csv --out era_multisite.png
"""

from __future__ import annotations

import argparse
import math

from climate_toolkit.visualization import (
    BAR, LINES, VARIABLE_LABELS, label_for, save_figure, shorten_treatment, use_headless,
)

use_headless()
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def _panel(ax, s, var, top_treatments):
    years = sorted(s["year"].unique())
    bars = s.drop_duplicates("year").set_index("year")[var]
    ax.bar(bars.index, bars.values, color=BAR, width=0.8, zorder=1)
    ax.set_xticks(years)
    ax.set_xticklabels([str(int(y)) for y in years], rotation=45, fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax2 = ax.twinx()
    treatments = list(s["treatment"].value_counts().head(top_treatments).index)
    for i, t in enumerate(treatments):
        st = s[s["treatment"] == t].groupby("year")["yield_t_ha"].mean()
        ax2.plot(st.index, st.values, marker="o", ms=2.5, lw=1.4,
                 color=LINES[i % len(LINES)], label=shorten_treatment(t, n=20), zorder=3)
    ax2.tick_params(axis="y", labelsize=7)
    ax2.legend(fontsize=6, ncol=min(len(treatments), 2), loc="upper left", frameon=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="+", help="One or more era_yield_analysis.py outputs")
    ap.add_argument("--variable", default="tk_rain_total_mm", choices=list(VARIABLE_LABELS))
    ap.add_argument("--sites", type=int, default=6, help="Max sites to show")
    ap.add_argument("--min-years", type=int, default=3, help="Skip sites with fewer years")
    ap.add_argument("--top-treatments", type=int, default=4)
    ap.add_argument("--out", default="era_multisite.png")
    args = ap.parse_args()

    df = pd.concat([pd.read_csv(p, low_memory=False) for p in args.csv], ignore_index=True)
    df[args.variable] = pd.to_numeric(df[args.variable], errors="coerce")
    df["yield_t_ha"] = pd.to_numeric(df["yield_t_ha"], errors="coerce")

    # only sites with enough years for a real time series, most-years first
    years_per = df.groupby("site_id")["year"].nunique()
    order = (years_per[years_per >= args.min_years].sort_values(ascending=False)
             .head(args.sites).index)
    n = len(order)
    if n == 0:
        raise SystemExit("No sites to plot.")
    cols = 2 if n > 1 else 1
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(7.2 * cols, 3.1 * rows), squeeze=False)
    for idx, site in enumerate(order):
        ax = axes[idx // cols][idx % cols]
        s = df[df["site_id"] == site]
        crop = s["crop"].mode().iloc[0] if not s["crop"].mode().empty else ""
        _panel(ax, s, args.variable, args.top_treatments)
        ax.set_title(f"{site} — {crop}", fontsize=10)
    for j in range(n, rows * cols):
        axes[j // cols][j % cols].axis("off")

    fig.suptitle(f"{label_for(args.variable)} vs yield across ERA sites  "
                 f"(bars = {args.variable}, lines = yield t/ha)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save_figure(fig, args.out, dpi=120)
    print(f"wrote {args.out} ({n} sites: {', '.join(order)})")


if __name__ == "__main__":
    main()
