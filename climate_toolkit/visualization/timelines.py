"""Timeline helpers for plots that annotate change points over time."""

from __future__ import annotations


def variety_transitions(s, variety_col: str = "variety", year_col: str = "year"):
    """Years at which the dominant value of ``variety_col`` changes, with the new value.

    Varieties (cultivars) are swapped over the life of a long-term experiment, so
    marking the switch points helps read a yield trend. The **first year is always
    included**, so a site that used a single variety throughout still gets one
    marker showing which variety it was.

    Returns ``[(year, value), ...]``; empty when the column is missing or all-NaN.
    """
    if variety_col not in s.columns:
        return []
    v = s.dropna(subset=[variety_col]).copy()
    if v.empty:
        return []
    per = (
        v.assign(**{variety_col: v[variety_col].astype(str)})
        .groupby(year_col)[variety_col]
        .agg(lambda x: x.mode().iloc[0])
        .sort_index()
    )
    changes, prev = [], None
    for yr, name in per.items():
        if name != prev:
            changes.append((int(yr), name))
            prev = name
    return changes
