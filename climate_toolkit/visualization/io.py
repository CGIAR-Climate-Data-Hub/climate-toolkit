"""Figure output helpers."""

from __future__ import annotations

import os


def save_figure(fig, path: str, *, dpi: int = 120, **savefig_kwargs) -> str:
    """Save ``fig`` to ``path`` (creating parent directories) and return ``path``.

    Extra keyword arguments (e.g. ``bbox_inches="tight"``, ``facecolor="white"``)
    are forwarded to ``fig.savefig``.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    fig.savefig(path, dpi=dpi, **savefig_kwargs)
    return path
