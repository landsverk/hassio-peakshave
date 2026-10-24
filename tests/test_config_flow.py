"""Unit tests for config flow logic, options flow, and device modification."""
import tests.ha_mock  # noqa: F401
import asyncio
import unittest
from unittest.mock import MagicMock

from custom_components.peak_shave.config_flow import (
    PeakShaveOptionsFlowHandler,
    _build_tariff_options,
)
from custom_components.peak_shave.const import (
    CONF_DEVICES,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_ESTIMATED_POWER,
    CONF_MIN_COOLDOWN,
    CONF_MIN_WATER_TEMP,
    CONF_TARGET_WATER_TEMP,
    CONF_PRIORITY,
    CONF_WATER_HEATER_ENTITY,
    CONF_WATER_TEMP_SENSOR,
    DEVICE_TYPE_WATER_HEATER,
    DEVICE_TYPE_CLIMATE,
    TARIFF_PRESETS,
)


class TestConfigFlow(unittest.TestCase):
    """Test config flow helpers, options flow, and in-place device editing."""

    def test_tariff_options_builder(self):
        """Verify all tariff presets are converted into UI select options."""
        options = _build_tariff_options()
        self.assertEqual(len(options), len(TARIFF_PRESETS))
        preset_keys = {opt.value for opt in options}
        self.assertIn("lede_tier_1", preset_keys)
        self.assertIn("lede_tier_2", preset_keys)
        self.assertIn("custom", preset_keys)

    def test_options_flow_init_lists_devices(self):
        """Options flow init step must list existing devices directly for 1-click edit."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "wb1",
                    CONF_DEVICE_NAME: "Varmtvannsbereder",
                    CONF_DEVICE_TYPE: DEVICE_TYPE_WATER_HEATER,
                    CONF_PRIORITY: 2,
                    CONF_MIN_WATER_TEMP: 50.0,
                },
                {
                    CONF_DEVICE_ID: "ac1",
                    CONF_DEVICE_NAME: "Stue Varmepumpe",
                    CONF_DEVICE_TYPE: DEVICE_TYPE_CLIMATE,
                    CONF_PRIORITY: 5,
                },
            ]
        }
        mock_entry.options = {}

        flow = PeakShaveOptionsFlowHandler(mock_entry)
        result = asyncio.run(flow.async_step_init())

        self.assertEqual(result["type"], "form")
        schema = result["data_schema"]
        # Options in schema must include edit_wb1 and edit_ac1
        action_selector = list(schema.schema.values())[0]
        self.assertIsNotNone(action_selector)
        opt_values = [opt["value"] for opt in action_selector.config["options"]]
        self.assertIn("edit_wb1", opt_values)
        self.assertIn("edit_ac1", opt_values)
        self.assertIn("add_water_heater", opt_values)
        self.assertIn("add_ac", opt_values)

    def test_options_flow_edit_device_in_place(self):
        """Editing an existing device modifies it in place without delete-and-re-add."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "wb1",
                    CONF_DEVICE_NAME: "Varmtvannsbereder",
                    CONF_DEVICE_TYPE: DEVICE_TYPE_WATER_HEATER,
                    CONF_WATER_HEATER_ENTITY: "switch.boiler",
                    CONF_PRIORITY: 2,
                    CONF_MIN_WATER_TEMP: 50.0,
                    CONF_ESTIMATED_POWER: 2.0,
                    CONF_MIN_COOLDOWN: 180,
                }
            ]
        }
        mock_entry.options = {}

        flow = PeakShaveOptionsFlowHandler(mock_entry)
        flow._selected_device_id = "wb1"

        # User updates priority to 1 and min_water_temp to 55°C
        update_input = {
            CONF_DEVICE_NAME: "Hovedbereder 300L",
            CONF_PRIORITY: 1,
            CONF_WATER_HEATER_ENTITY: "switch.boiler",
            CONF_MIN_WATER_TEMP: 55.0,
            CONF_TARGET_WATER_TEMP: 65.0,
            CONF_ESTIMATED_POWER: 2.5,
            CONF_MIN_COOLDOWN: 180,
            "delete_device": False,
        }
        result = asyncio.run(flow.async_step_edit_device(update_input))
        self.assertEqual(result["type"], "create_entry")

        # Verify device was updated in place and still has 1 device with id wb1
        devices = flow._options[CONF_DEVICES]
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0][CONF_DEVICE_ID], "wb1")
        self.assertEqual(devices[0][CONF_DEVICE_NAME], "Hovedbereder 300L")
        self.assertEqual(devices[0][CONF_PRIORITY], 1)
        self.assertEqual(devices[0][CONF_MIN_WATER_TEMP], 55.0)

    def test_options_flow_delete_device(self):
        """Checking 'delete_device' removes the device cleanly."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_DEVICES: [
                {
                    CONF_DEVICE_ID: "wb1",
                    CONF_DEVICE_NAME: "Bereder",
                    CONF_DEVICE_TYPE: DEVICE_TYPE_WATER_HEATER,
                },
                {
                    CONF_DEVICE_ID: "ac1",
                    CONF_DEVICE_NAME: "AC",
                    CONF_DEVICE_TYPE: DEVICE_TYPE_CLIMATE,
                },
            ]
        }
        mock_entry.options = {}

        flow = PeakShaveOptionsFlowHandler(mock_entry)
        flow._selected_device_id = "wb1"

        # Submit with delete_device=True
        result = asyncio.run(flow.async_step_edit_device({"delete_device": True}))
        self.assertEqual(result["type"], "create_entry")

        # Only ac1 remains
        devices = flow._options[CONF_DEVICES]
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0][CONF_DEVICE_ID], "ac1")

    def test_options_flow_add_water_heater(self):
        """User can add a new water boiler via add_water_heater step."""
        mock_entry = MagicMock()
        mock_entry.data = {CONF_DEVICES: []}
        mock_entry.options = {}

        flow = PeakShaveOptionsFlowHandler(mock_entry)
        user_input = {
            CONF_WATER_HEATER_ENTITY: "switch.varmtvann",
            CONF_DEVICE_NAME: "OSO Bereder",
            CONF_PRIORITY: 1,
            CONF_MIN_WATER_TEMP: 52.0,
            CONF_TARGET_WATER_TEMP: 70.0,
            CONF_ESTIMATED_POWER: 3.0,
            CONF_MIN_COOLDOWN: 120,
        }
        result = asyncio.run(flow.async_step_add_water_heater(user_input))
        self.assertEqual(result["type"], "create_entry")

        devices = flow._options[CONF_DEVICES]
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0][CONF_DEVICE_TYPE], DEVICE_TYPE_WATER_HEATER)
        self.assertEqual(devices[0][CONF_DEVICE_NAME], "OSO Bereder")
        self.assertEqual(devices[0][CONF_PRIORITY], 1)
        self.assertEqual(devices[0][CONF_MIN_WATER_TEMP], 52.0)


if __name__ == "__main__":
    unittest.main()
