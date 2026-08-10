"""Human-readable labels for toolkit climate variables.

One label source so figures don't disagree on what, e.g., ``tk_NDWS`` is called
(design principle #4 in issue #25 — CF/unit-aware, consistent labelling).
"""

from __future__ import annotations

#: Toolkit column name -> display label (units included where relevant).
VARIABLE_LABELS: dict[str, str] = {
    "tk_rain_total_mm": "Seasonal rainfall (mm)",
    "tk_rainy_days": "Rainy days",
    "tk_dry_days": "Dry days",
    "tk_NDWS": "Water-stress days (NDWS)",
    "tk_WRSI": "Water-satisfaction (WRSI)",
}


def label_for(var: str) -> str:
    """Return a display label for ``var``, falling back to its raw name."""
    return VARIABLE_LABELS.get(var, var)
