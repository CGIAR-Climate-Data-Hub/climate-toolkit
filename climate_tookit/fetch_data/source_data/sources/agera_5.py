"""AgERA5 adapter.

AgERA5 runtime in this package is Earth Engine-backed. This module exists as
authoritative AgERA5 entry point so runtime dispatch and source surface stay
aligned.
"""

from .gee import DownloadData as _GeeDownloadData


class DownloadData(_GeeDownloadData):
    """AgERA5 Earth Engine-backed adapter."""


__all__ = ["DownloadData"]
