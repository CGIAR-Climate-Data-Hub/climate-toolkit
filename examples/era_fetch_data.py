"""Download the public ERA ``lte_final.csv`` — cross-platform, no curl needed.

Works the same on Windows PowerShell, macOS, and Linux (avoids the
``curl`` vs ``Invoke-WebRequest`` differences):

    python examples/era_fetch_data.py                 # -> lte_final.csv
    python examples/era_fetch_data.py --out data/lte_final.csv
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request

URL = "https://raw.githubusercontent.com/ERAgriculture/LTEs/main/data/lte_final.csv"


def _progress(block, block_size, total):
    if total <= 0:
        return
    pct = min(100, block * block_size * 100 // total)
    if pct != _progress.last:  # print once per percent, not per block
        _progress.last = pct
        sys.stdout.write(f"\r  {pct:3d}%  ({total // (1024 * 1024)} MB)")
        sys.stdout.flush()


_progress.last = -1


def download(url: str, out: str) -> str:
    """Download ``url`` to ``out`` (cross-platform), or exit with a clear error."""
    _progress.last = -1
    try:
        urllib.request.urlretrieve(url, out, _progress)
    except Exception as exc:  # network / URL problems -> a clear message, not a traceback
        raise SystemExit(f"\ndownload failed: {exc}")
    return out


def maybe_fetch(path: str, url: str = URL) -> str:
    """Return ``path``; if it's a missing ``lte_final.csv``, download it first.

    Lets the ERA scripts run without a separate download step. Only the known
    public file is auto-fetched — any other missing path is left for the caller
    to error on.
    """
    if os.path.exists(path) or os.path.basename(path).lower() != "lte_final.csv":
        return path
    print(f"{path} not found — fetching the public ERA lte_final.csv:")
    download(url, path)
    print(f"\ndownloaded -> {path}")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="lte_final.csv", help="Output path (default: lte_final.csv)")
    ap.add_argument("--url", default=URL, help="Source URL (default: ERA lte_final.csv)")
    args = ap.parse_args()

    print(f"downloading {args.url}\n         -> {args.out}")
    download(args.url, args.out)
    print(f"\ndone -> {args.out}")


if __name__ == "__main__":
    main()
