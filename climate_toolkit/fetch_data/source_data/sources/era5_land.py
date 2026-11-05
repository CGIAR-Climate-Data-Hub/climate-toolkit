"""ERA5-Land adapter under the canonical ``era5_land`` source key.

Dispatches to Earth Engine's ECMWF/ERA5_LAND/DAILY_AGGR collection.
The distinct Copernicus AgERA5 product is not served by this adapter.
"""

from .gee_xee import DownloadData as _GeeDownloadData


class DownloadData(_GeeDownloadData):
    """ERA5-Land Earth Engine-backed adapter."""


__all__ = ["DownloadData"]
