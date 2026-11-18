"""Figure output helpers."""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path


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


def data_uri(mime_type: str, content: bytes) -> str:
    """Embed binary content in a standalone HTML report."""
    return f"data:{mime_type};base64," + base64.b64encode(content).decode("ascii")


def write_html(path: Path, content: str) -> None:
    """Atomically replace a standalone HTML report after it has rendered."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as staging:
        staged = Path(staging) / "report.html"
        staged.write_text(content, encoding="utf-8")
        os.replace(staged, path)
