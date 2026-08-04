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

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

BAR = "#bcd8ea"
LINES = ["#2f7d52", "#d1652b", "#6a5acd", "#2f6f9f", "#b5401f", "#4a7f3a", "#9c27b0", "#00838f"]
VARS = [
    ("tk_rain_total_mm", "Seasonal rainfall (mm)"),
    ("tk_rainy_days", "Rainy days"),
    ("tk_dry_days", "Dry days"),
    ("tk_NDWS", "Water-stress days (NDWS)"),
    ("tk_WRSI", "Water-satisfaction (WRSI)"),
]


def _short(label: str, n: int = 24) -> str:
    """Shorten ERA's verbose treatment names for a readable legend."""
    t = str(label).split(">>")[0].split("***")[0].strip()  # drop rotation/repeat suffixes
    return t if len(t) <= n else t[: n - 1] + "…"


def _panel(ax, s, var, label, treatments, put_legend):
    years = sorted(s["year"].unique())
    bars = s.drop_duplicates("year").set_index("year")[var]
    ax.bar(bars.index, bars.values, color=BAR, width=0.8, label=label, zorder=1)
    ax.set_ylabel(label, color="#4a6b82", fontsize=9)
    ax.set_xticks(years)
    ax.set_xticklabels([str(int(y)) for y in years], rotation=45, fontsize=8)
    ax2 = ax.twinx()
    for i, t in enumerate(treatments):
        st = s[s["treatment"] == t].groupby("year")["yield_t_ha"].mean()
        ax2.plot(st.index, st.values, marker="o", ms=3, lw=1.6,
                 color=LINES[i % len(LINES)], label=_short(t), zorder=3)
    ax2.set_ylabel("yield (t/ha)", color="#2f7d52", fontsize=9)
    if put_legend:
        ax2.legend(title="Treatment", fontsize=7, title_fontsize=7, ncol=min(len(treatments), 3),
                   loc="lower center", bbox_to_anchor=(0.5, 1.02), frameon=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="Output of era_yield_analysis.py")
    ap.add_argument("--site", help="Site.ID to plot (substring; default: most-years site)")
    ap.add_argument("--variable", help="Plot only this toolkit variable (single panel)")
    ap.add_argument("--treatments", help="Comma-separated treatment filter (substring match, "
                    "e.g. 'NT 0N,NT 100N,NT 200N' to match Rwema's NT subset)")
    ap.add_argument("--top-treatments", type=int, default=6, help="Max treatments to draw")
    ap.add_argument("--out", default="era_yield_trends.png")
    args = ap.parse_args()

    df = pd.read_csv(args.csv, low_memory=False)
    for col, _ in VARS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["yield_t_ha"] = pd.to_numeric(df["yield_t_ha"], errors="coerce")

    if args.site:
        df = df[df["site_id"].astype(str).str.contains(args.site, case=False, na=False)]
    if df.empty:
        raise SystemExit("No rows for that site. Check --site or run era_yield_analysis.py first.")
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

    fig, axes = plt.subplots(len(panels), 1, figsize=(11, 3.1 * len(panels)))
    axes = [axes] if len(panels) == 1 else list(axes)
    for i, (var, label) in enumerate(panels):
        _panel(axes[i], s, var, label, treatments, put_legend=(i == 0))
    yr = f"{int(s['year'].min())}–{int(s['year'].max())}"
    fig.suptitle(f"{site} — {crop}: toolkit climate vs yield ({yr})", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(args.out, dpi=120)
    print(f"wrote {args.out}  (site={site}, treatments={len(treatments)}, panels={len(panels)})")


if __name__ == "__main__":
    main()
