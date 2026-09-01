"""Plot toolkit climate variables against yield over time (Rwema's request).

Reproduces the ERA "yield & rainfall trends" figure — a per-site dual-axis time
series with the climate variable as bars and one yield line per treatment — but
lets you swap rainfall for any toolkit variable. Input is the year-matched table
from ``era_yield_analysis.py``.

* default: a 5-panel figure for one site — tk_rain_total, tk_rainy_days,
  tk_dry_days, tk_NDWS, tk_WRSI each as bars with the yield lines on top.
* ``--variable tk_WRSI`` : just that one variable, single panel.

    python examples/era_yield_analysis.py lte_final.csv --site "Gourton" --out gourton.csv
    python examples/era_yield_plot.py gourton.csv --site "Gourton" --out gourton_trends.png
"""

from __future__ import annotations

import argparse
import os
import sys

# Prefer the cloned repo's climate_toolkit over any older pip-installed one, so
# the shared `visualization` package resolves even when the installed release
# predates it (e.g. Colab installs from PyPI, then runs these repo examples).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from climate_toolkit.visualization import (  # noqa: E402
    BAR,
    LINES,
    label_for,
    save_figure,
    shorten_treatment,
    use_headless,
    variety_transitions,
)

use_headless()
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

VARS = [(c, label_for(c)) for c in
        ("tk_rain_total_mm", "tk_rainy_days", "tk_dry_days", "tk_NDWS", "tk_WRSI")]


def _panel(ax, s, var, label, treatments, put_legend, variety_changes=()):
    years = sorted(s["year"].unique())
    bars = s.drop_duplicates("year").set_index("year")[var]
    ax.bar(bars.index, bars.values, color=BAR, width=0.8, label=label, zorder=1)
    ax.set_ylabel(label, color="#4a6b82", fontsize=9)
    ax.set_xticks(years)
    ax.set_xticklabels([str(int(y)) for y in years], rotation=45, fontsize=8)
    for yr, vname in variety_changes:  # dashed guide where the crop variety changes
        ax.axvline(yr, color="#8a8f98", ls="--", lw=0.8, zorder=0)
        if put_legend:
            ax.text(yr, ax.get_ylim()[1] * 0.98, f" {vname}", rotation=90,
                    va="top", ha="left", fontsize=6.5, color="#5a5f68", zorder=4)
    ax2 = ax.twinx()
    for i, t in enumerate(treatments):
        st = s[s["treatment"] == t].groupby("year")["yield_t_ha"].mean()
        ax2.plot(st.index, st.values, marker="o", ms=3, lw=1.6,
                 color=LINES[i % len(LINES)], label=shorten_treatment(t), zorder=3)
    ax2.set_ylabel("yield (t/ha)", color="#2f7d52", fontsize=9)
    if put_legend:
        ax2.legend(title="Treatment", fontsize=7, title_fontsize=7, ncol=min(len(treatments), 3),
                   loc="lower center", bbox_to_anchor=(0.5, 1.02), frameon=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="Output of era_yield_analysis.py")
    ap.add_argument("--site", help="Site.ID to plot (substring; default: most-years site)")
    ap.add_argument("--crop", help="Only this crop (substring), for multi-crop sites like Kouve")
    ap.add_argument("--variable", help="Plot only this toolkit variable (single panel)")
    ap.add_argument("--treatments", help="Comma-separated treatment filter (substring match, "
                    "e.g. 'NT 0N,NT 100N,NT 200N' to match Rwema's NT subset)")
    ap.add_argument("--top-treatments", type=int, default=6, help="Max treatments to draw")
    ap.add_argument("--no-variety", action="store_true",
                    help="Don't mark where the crop variety changes over time")
    ap.add_argument("--out", default="era_yield_trends.png")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, low_memory=False)
    for col, _ in VARS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["yield_t_ha"] = pd.to_numeric(df["yield_t_ha"], errors="coerce")

    if args.site:
        df = df[df["site_id"].astype(str).str.contains(args.site, case=False, na=False)]
    if args.crop:
        df = df[df["crop"].astype(str).str.contains(args.crop, case=False, na=False)]
    if df.empty:
        raise SystemExit("No rows for that site/crop. Check --site/--crop or run era_yield_analysis.py first.")
    site = df["site_id"].value_counts().idxmax()
    s = df[df["site_id"] == site].copy()
    crop = s["crop"].mode().iloc[0] if not s["crop"].mode().empty else ""

    if args.treatments:
        wanted = [w.strip().lower() for w in args.treatments.split(",") if w.strip()]
        keep = [t for t in s["treatment"].unique()
                if any(w in str(t).lower() for w in wanted)]
        s = s[s["treatment"].isin(keep)]
        if s.empty:
            raise SystemExit(f"No treatments matched {args.treatments!r}. Available: "
                             f"{sorted(df[df['site_id'] == site]['treatment'].unique())}")
    treatments = list(s["treatment"].value_counts().head(args.top_treatments).index)
    panels = [(v, lbl) for v, lbl in VARS if v == args.variable] if args.variable else VARS
    variety_changes = [] if args.no_variety else variety_transitions(s)

    fig, axes = plt.subplots(len(panels), 1, figsize=(11, 3.1 * len(panels)))
    axes = [axes] if len(panels) == 1 else list(axes)
    for i, (var, label) in enumerate(panels):
        _panel(axes[i], s, var, label, treatments, put_legend=(i == 0),
               variety_changes=variety_changes)
    yr = f"{int(s['year'].min())}–{int(s['year'].max())}"
    fig.suptitle(f"{site} — {crop}: toolkit climate vs yield ({yr})", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    save_figure(fig, args.out, dpi=120)
    print(f"wrote {args.out}  (site={site}, treatments={len(treatments)}, panels={len(panels)})")


if __name__ == "__main__":
    main()
