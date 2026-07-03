import unittest

from climate_tookit.fetch_data.fetch_data import resolve_models
from climate_tookit.fetch_data.source_data.sources.nex_gddp import (
    AVAILABLE_MODELS as NEX_GDDP_MODELS,
)


class ResolveModelsTests(unittest.TestCase):
    def test_single_model_is_returned_unchanged(self):
        self.assertEqual([NEX_GDDP_MODELS[0]], resolve_models(NEX_GDDP_MODELS[0], None))

    def test_non_nex_source_none_model(self):
        self.assertEqual([None], resolve_models(None, None))

    def test_models_flag_comma_list_expands(self):
        picked = list(NEX_GDDP_MODELS[:3])
        self.assertEqual(picked, resolve_models(None, ",".join(picked)))

    def test_model_flag_comma_list_expands(self):
        """Regression for #97: --model must also accept a comma-separated list."""
        picked = list(NEX_GDDP_MODELS[:3])
        self.assertEqual(picked, resolve_models(",".join(picked), None))

    def test_model_flag_all_expands_to_every_model(self):
        self.assertEqual(list(NEX_GDDP_MODELS), resolve_models("all", None))

    def test_models_flag_all_expands_to_every_model(self):
        self.assertEqual(list(NEX_GDDP_MODELS), resolve_models(None, "all"))

    def test_models_flag_takes_precedence_over_model(self):
        self.assertEqual([NEX_GDDP_MODELS[1]], resolve_models(NEX_GDDP_MODELS[0], NEX_GDDP_MODELS[1]))

    def test_invalid_name_in_model_comma_list_raises(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_models(f"{NEX_GDDP_MODELS[0]},NOT-A-MODEL", None)
        self.assertIn("NOT-A-MODEL", str(ctx.exception))

    def test_invalid_name_in_models_flag_raises(self):
        with self.assertRaises(ValueError):
            resolve_models(None, "NOT-A-MODEL")

    def test_whitespace_in_list_is_tolerated(self):
        picked = list(NEX_GDDP_MODELS[:2])
        self.assertEqual(picked, resolve_models(f" {picked[0]} , {picked[1]} ", None))


if __name__ == "__main__":
    unittest.main()
