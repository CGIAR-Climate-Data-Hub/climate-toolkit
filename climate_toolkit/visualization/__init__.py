"""Shared visualization foundation for climate-toolkit outputs.

The start of the unified plotting / reporting layer planned in issue #25:
shared figure styling, variable labels, small text helpers, and figure IO, so
plotting logic stops being duplicated across modules and example scripts.

This is intentionally a thin, dependency-light foundation (matplotlib only,
already a base dependency). The ERA yield / trend example plots are its first
consumers; more modules will follow.
"""

from __future__ import annotations

from climate_toolkit.visualization import io, labels, styles, text
from climate_toolkit.visualization.io import save_figure
from climate_toolkit.visualization.labels import VARIABLE_LABELS, label_for
from climate_toolkit.visualization.styles import BAR, LINES, use_headless
from climate_toolkit.visualization.text import shorten_treatment

__all__ = [
    "io",
    "labels",
    "styles",
    "text",
    "save_figure",
    "VARIABLE_LABELS",
    "label_for",
    "BAR",
    "LINES",
    "use_headless",
    "shorten_treatment",
]
