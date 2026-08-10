"""Small text helpers for plot legends and labels."""

from __future__ import annotations


def shorten_treatment(label: str, n: int = 24) -> str:
    """Trim ERA's verbose treatment names for a readable legend.

    Drops rotation / repeat suffixes (``>>``, ``***``) and ellipsizes anything
    longer than ``n`` characters.
    """
    t = str(label).split(">>")[0].split("***")[0].strip()
    return t if len(t) <= n else t[: n - 1] + "…"
