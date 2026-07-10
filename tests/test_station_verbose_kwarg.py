"""Regression guard for the GHCN station-selector ``verbose`` kwarg.

`download_station_data` / `compare_station_to_grids` (and `station_selector`)
call the candidate selectors with ``verbose=...``. The GSOD selectors accept it
but the GHCN ones did not, so every GHCN station lookup raised
``TypeError: select_ghcn_station_candidates() got an unexpected keyword
argument 'verbose'``. These functions must stay signature-compatible.
"""

import inspect
import unittest

from climate_toolkit.weather_station.ghcn_daily import (
    list_ghcn_station_candidates,
    select_ghcn_station_candidates,
)
from climate_toolkit.weather_station.gsod import (
    list_gsod_station_candidates,
    select_gsod_station_candidates,
)


class StationSelectorVerboseKwargTests(unittest.TestCase):
    def test_candidate_selectors_accept_verbose(self):
        for fn in (
            list_ghcn_station_candidates,
            select_ghcn_station_candidates,
            list_gsod_station_candidates,
            select_gsod_station_candidates,
        ):
            with self.subTest(function=fn.__name__):
                self.assertIn(
                    "verbose",
                    inspect.signature(fn).parameters,
                    f"{fn.__name__} must accept a 'verbose' keyword (callers pass it)",
                )


if __name__ == "__main__":
    unittest.main()
