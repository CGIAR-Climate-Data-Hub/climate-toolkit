"""Figure output helpers."""

from __future__ import annotations

import os


def save_figure(fig, path: str, *, dpi: int = 120) -> str:
    """Save ``fig`` to ``path`` (creating parent directories) and return ``path``."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    return path
