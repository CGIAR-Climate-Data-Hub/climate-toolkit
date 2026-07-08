"""ERA5 adapter.

ERA5 runtime in this package is Earth Engine-backed. This module exists as the
authoritative ERA5 entry point so runtime dispatch, import surface, and setup
expectations stay aligned.
"""

from .gee_xee import DownloadData as _GeeDownloadData


class DownloadData(_GeeDownloadData):
    """ERA5 Earth Engine-backed adapter."""


__all__ = ["DownloadData"]
