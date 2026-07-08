from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def build_season_identity(
    onset: Any,
    cessation: Any,
    *,
    length_days: Optional[int] = None,
    regime: Optional[str] = None,
    season_number: Optional[int] = None,
    total_seasons_per_year: Optional[int] = None,
) -> Dict[str, Any]:
    onset_ts = pd.to_datetime(onset)
    cess_ts = pd.to_datetime(cessation)
    midpoint_ts = onset_ts + (cess_ts - onset_ts) / 2
    duration = (
        int(length_days)
        if length_days is not None
        else int((cess_ts - onset_ts).days + 1)
    )

    onset_month = int(onset_ts.month)
    cess_month = int(cess_ts.month)
    regime_name = regime or "unknown"

    alignment_candidates = [
        f"onset_month:{onset_month:02d}",
        f"month_pair:{onset_month:02d}-{cess_month:02d}",
        f"regime:{regime_name}|onset_month:{onset_month:02d}",
    ]

    return {
        "onset_date": onset_ts.strftime("%Y-%m-%d"),
        "cessation_date": cess_ts.strftime("%Y-%m-%d"),
        "midpoint_date": midpoint_ts.strftime("%Y-%m-%d"),
        "onset_month": onset_month,
        "cessation_month": cess_month,
        "midpoint_month": int(midpoint_ts.month),
        "onset_doy": int(onset_ts.dayofyear),
        "cessation_doy": int(cess_ts.dayofyear),
        "midpoint_doy": int(midpoint_ts.dayofyear),
        "length_days": duration,
        "crosses_year_boundary": bool(cess_ts.year > onset_ts.year),
        "regime": regime_name,
        "season_number": season_number,
        "total_seasons_per_year": total_seasons_per_year,
        "slot_label": (
            f"season_{season_number}_of_{total_seasons_per_year}"
            if season_number is not None and total_seasons_per_year is not None
            else None
        ),
        "candidate_alignment_keys": alignment_candidates,
        "experimental_alignment_key": alignment_candidates[-1],
    }
