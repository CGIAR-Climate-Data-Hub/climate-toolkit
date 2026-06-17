import unittest

from climate_tookit.calculate_hazards.hazards import resolve_thresholds


class CropRegistryHazardTests(unittest.TestCase):
    def test_calendar_only_crop_can_use_custom_thresholds(self):
        thresholds = resolve_thresholds(
            "Cotton",
            custom_thresholds={
                "Total Precip": {
                    "no_stress": (400, 900),
                }
            },
        )
        self.assertIn("NDWS", thresholds)
        self.assertIn("Total Precip", thresholds)


if __name__ == "__main__":
    unittest.main()
