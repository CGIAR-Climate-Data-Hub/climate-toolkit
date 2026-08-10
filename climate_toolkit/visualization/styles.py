"""Shared figure styling for climate-toolkit plots.

Part of the unified visualization layer (issue #25). Keeping colours and the
backend selection in one place stops every plotting script from re-declaring
its own palette.
"""

from __future__ import annotations

#: Bar fill for climate-variable bars in the ERA yield / trend figures.
BAR = "#bcd8ea"

#: Colour cycle for per-treatment yield lines (and similar overlays). Index into
#: it with ``LINES[i % len(LINES)]``.
LINES = [
    "#2f7d52", "#d1652b", "#6a5acd", "#2f6f9f",
    "#b5401f", "#4a7f3a", "#9c27b0", "#00838f",
]


def use_headless() -> None:
    """Select matplotlib's non-interactive ``Agg`` backend.

    Safe for CLI / batch / servers with no display. Call it *before* importing
    ``matplotlib.pyplot``.

    matplotlib is imported here (not at module load) so importing
    ``climate_toolkit.visualization`` stays cheap, and so the import resolves the
    real module at call time rather than binding whatever is in ``sys.modules``
    when this module is first imported.
    """
    import matplotlib

    matplotlib.use("Agg")
