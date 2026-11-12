import unittest

import numpy as np

from scripts.pilot_kapiti_forage import slope_grid, valid_pixels


class KapitiForagePilotTest(unittest.TestCase):
    def test_paired_quality_mask(self):
        good = (1 << 11) | (1 << 6)
        flags = np.array(
            [good, good | (1 << 8), good | (1 << 14), good | 1, 0, good, good],
            dtype=np.uint16,
        )
        ndvi = np.full(flags.size, 3000)
        evi = np.full(flags.size, 2000)
        ndvi[-2] = -3000
        evi[-1] = -3000
        np.testing.assert_array_equal(
            valid_pixels(ndvi, evi, flags),
            [True, False, False, False, False, False, False],
        )

    def test_trend_compares_same_dates_despite_missing_seasonal_peaks(self):
        years = np.arange(2001, 2026)
        matrix = 0.002 * (years[:, None] - 2001) + np.array([0.1, 0.3, 0.5])
        matrix[:10, 2] = np.nan
        matrix[-10:, 0] = np.nan
        self.assertAlmostEqual(slope_grid(matrix, years), 0.002)
        # Repeated years in a bootstrap sample cannot contribute zero-time pairs.
        indices = [0, 0, 5, 20, 23, 23]
        self.assertAlmostEqual(slope_grid(matrix[indices], years[indices]), 0.002)
