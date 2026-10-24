"""Unit tests for config flow logic and tariff options."""
import tests.ha_mock  # noqa: F401
import unittest

from custom_components.peak_shave.config_flow import _build_tariff_options
from custom_components.peak_shave.const import TARIFF_PRESETS


class TestConfigFlow(unittest.TestCase):
    """Test config flow helpers and schemas."""

    def test_tariff_options_builder(self):
        """Verify all tariff presets are converted into UI select options."""
        options = _build_tariff_options()
        self.assertEqual(len(options), len(TARIFF_PRESETS))
        preset_keys = {opt.value for opt in options}
        self.assertIn("lede_tier_1", preset_keys)
        self.assertIn("lede_tier_2", preset_keys)
        self.assertIn("custom", preset_keys)


if __name__ == "__main__":
    unittest.main()
