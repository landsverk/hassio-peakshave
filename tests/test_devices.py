"""Unit tests for individual device controllers."""
import tests.ha_mock  # noqa: F401
import unittest
from datetime import datetime, timedelta, timezone

from custom_components.peak_shave.const import (
    ACTION_SETBACK,
    ACTION_TURN_OFF,
    CONF_CLIMATE_ACTION,
    CONF_CLIMATE_ENTITY,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_ESTIMATED_POWER,
    CONF_EV_CURRENT_ENTITY,
    CONF_EV_MAX_CURRENT,
    CONF_EV_MIN_CURRENT,
    CONF_EV_MIN_SOC,
    CONF_EV_PHASES,
    CONF_EV_SWITCH_ENTITY,
    CONF_EV_VOLTAGE,
    CONF_MAX_TEMPERATURE,
    CONF_MIN_COOLDOWN,
    CONF_MIN_TEMPERATURE,
    CONF_MIN_WATER_TEMP,
    CONF_POWER_SENSOR,
    CONF_PRIORITY,
    CONF_SETBACK_DELTA,
    CONF_SWITCH_ENTITY,
    CONF_TARGET_WATER_TEMP,
    CONF_WATER_HEATER_ENTITY,
    CONF_WATER_TEMP_SENSOR,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_EV,
    DEVICE_TYPE_SWITCH,
    DEVICE_TYPE_WATER_HEATER,
)
from custom_components.peak_shave.devices import (
    ClimateDevice,
    EVChargerDevice,
    SwitchDevice,
    WaterHeaterDevice,
    create_device_from_config,
)


class TestDevices(unittest.TestCase):
    """Test device models, controllers, and edge cases."""

    def setUp(self):
        self.now = datetime(2026, 10, 24, 14, 0, 0, tzinfo=timezone.utc)

    def test_switch_device_lifecycle(self):
        """Test switch device shedding, cooldown, and restoration."""
        switch = SwitchDevice({
            CONF_DEVICE_ID: "plug_1",
            CONF_DEVICE_NAME: "Water Heater",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.water_heater",
            CONF_POWER_SENSOR: "sensor.water_heater_power",
            CONF_ESTIMATED_POWER: 2.0,
            CONF_MIN_COOLDOWN: 120,
            CONF_PRIORITY: 1,
        })
        switch.update_switch_state(True)
        switch.update_power_reading(1.95)

        self.assertTrue(switch.can_shed(self.now))
        self.assertAlmostEqual(switch.estimated_shed_power_reduction(), 1.95, places=2)

        # Shed device
        actions = switch.plan_shed(self.now)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].domain, "switch")
        self.assertEqual(actions[0].service, "turn_off")
        self.assertEqual(actions[0].target_entity, "switch.water_heater")
        self.assertTrue(switch.is_shed)
        self.assertFalse(switch.is_on)

        # Immediate restore attempt: blocked by 120s cooldown
        t_soon = self.now + timedelta(seconds=30)
        self.assertFalse(switch.can_restore(t_soon))
        self.assertAlmostEqual(switch.seconds_until_available(t_soon), 90.0, places=1)

        # After cooldown expired: can restore
        t_after_cooldown = self.now + timedelta(seconds=121)
        self.assertTrue(switch.can_restore(t_after_cooldown))

        # Restore device
        restore_actions = switch.plan_restore(t_after_cooldown)
        self.assertEqual(len(restore_actions), 1)
        self.assertEqual(restore_actions[0].service, "turn_on")
        self.assertFalse(switch.is_shed)
        self.assertTrue(switch.is_on)

    def test_climate_turn_off_mode(self):
        """Test climate device configured in turn-off mode."""
        ac = ClimateDevice({
            CONF_DEVICE_ID: "heat_pump",
            CONF_DEVICE_NAME: "Basement Heat Pump",
            CONF_DEVICE_TYPE: DEVICE_TYPE_CLIMATE,
            CONF_CLIMATE_ENTITY: "climate.heat_pump",
            CONF_CLIMATE_ACTION: ACTION_TURN_OFF,
            CONF_MIN_TEMPERATURE: 17.0,
            CONF_ESTIMATED_POWER: 1.2,
            CONF_MIN_COOLDOWN: 300,
            CONF_PRIORITY: 2,
        })
        ac.update_climate_state(
            current_temp=21.0,
            target_temp=22.0,
            hvac_mode="heat",
            hvac_action="heating",
        )
        self.assertTrue(ac.can_shed(self.now))

        actions = ac.plan_shed(self.now)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].service, "set_hvac_mode")
        self.assertEqual(actions[0].service_data["hvac_mode"], "off")

        # After cooldown, restore returns HVAC mode to 'heat'
        t_after = self.now + timedelta(seconds=301)
        self.assertTrue(ac.can_restore(t_after))
        restore_actions = ac.plan_restore(t_after)
        self.assertEqual(len(restore_actions), 2)  # set_hvac_mode and set_temperature
        self.assertEqual(restore_actions[0].service_data["hvac_mode"], "heat")
        self.assertEqual(restore_actions[1].service_data["temperature"], 22.0)

    def test_climate_cooling_max_temperature(self):
        """Test climate device in cooling mode respecting max temperature."""
        ac = ClimateDevice({
            CONF_DEVICE_ID: "ac_cool",
            CONF_DEVICE_NAME: "AC Cooler",
            CONF_DEVICE_TYPE: DEVICE_TYPE_CLIMATE,
            CONF_CLIMATE_ENTITY: "climate.ac_cooler",
            CONF_CLIMATE_ACTION: ACTION_SETBACK,
            CONF_MAX_TEMPERATURE: 25.0,
            CONF_SETBACK_DELTA: 2.0,
            CONF_PRIORITY: 3,
        })
        # If room is already 25.5°C in cooling mode, don't shed to avoid overheating
        ac.update_climate_state(
            current_temp=25.5,
            target_temp=22.0,
            hvac_mode="cool",
            hvac_action="cooling",
        )
        self.assertFalse(ac.can_shed(self.now))

        # If room is 23.0°C, shedding is permitted
        ac.update_climate_state(
            current_temp=23.0,
            target_temp=22.0,
            hvac_mode="cool",
            hvac_action="cooling",
        )
        self.assertTrue(ac.can_shed(self.now))
        actions = ac.plan_shed(self.now)
        # Cooling setback raises target temperature (e.g. from 22 to 24)
        self.assertEqual(actions[0].service_data["temperature"], 24.0)

    def test_ev_charger_progressive_shedding(self):
        """Test EV charger multi-stage shedding: throttle current -> pause switch."""
        ev = EVChargerDevice({
            CONF_DEVICE_ID: "wallbox",
            CONF_DEVICE_NAME: "Garage Wallbox",
            CONF_DEVICE_TYPE: DEVICE_TYPE_EV,
            CONF_EV_CURRENT_ENTITY: "number.wallbox_current",
            CONF_EV_SWITCH_ENTITY: "switch.wallbox_charging",
            CONF_EV_MIN_CURRENT: 6,
            CONF_EV_MAX_CURRENT: 16,
            CONF_EV_MIN_SOC: 50,
            CONF_EV_PHASES: 3,
            CONF_EV_VOLTAGE: 230,
            CONF_MIN_COOLDOWN: 10,
        })
        ev.update_ev_state(current_amps=16, is_charging=True, battery_soc=75)

        # Stage 1: Step down current from 16A
        actions1 = ev.plan_shed(self.now)
        self.assertEqual(len(actions1), 1)
        self.assertEqual(actions1[0].service, "set_value")
        self.assertEqual(actions1[0].service_data["value"], 11)
        self.assertEqual(ev.shed_stage, 1)

        # Stage 2: Step down again from 11A -> 8A
        t2 = self.now + timedelta(seconds=15)
        self.assertTrue(ev.can_shed(t2))
        actions2 = ev.plan_shed(t2)
        self.assertEqual(actions2[0].service_data["value"], 8)

        # Stage 3: Step down from 8A -> 6A (min_current)
        t3 = t2 + timedelta(seconds=15)
        self.assertTrue(ev.can_shed(t3))
        actions3 = ev.plan_shed(t3)
        self.assertEqual(actions3[0].service_data["value"], 6)

        # Stage 4: Already at min current 6A -> Next step pauses charging switch
        t4 = t3 + timedelta(seconds=15)
        self.assertTrue(ev.can_shed(t4))
        actions4 = ev.plan_shed(t4)
        self.assertEqual(actions4[0].domain, "switch")
        self.assertEqual(actions4[0].service, "turn_off")
        self.assertEqual(ev.shed_stage, 2)
        self.assertFalse(ev.is_charging)

        # Fully shed (at stage 2 and switch off): cannot shed further
        t5 = t4 + timedelta(seconds=15)
        self.assertFalse(ev.can_shed(t5))

        # Restoring: First unpause switch at min current
        actions_restore1 = ev.plan_restore(t5)
        self.assertEqual(actions_restore1[0].domain, "switch")
        self.assertEqual(actions_restore1[0].service, "turn_on")
        self.assertEqual(ev.shed_stage, 1)

        # Second restore: Restore nominal 16A current
        t6 = t5 + timedelta(seconds=15)
        actions_restore2 = ev.plan_restore(t6)
        self.assertEqual(actions_restore2[0].domain, "number")
        self.assertEqual(actions_restore2[0].service_data["value"], 16)
        self.assertEqual(ev.shed_stage, 0)
        self.assertFalse(ev.is_shed)

    def test_water_heater_device_lifecycle(self):
        """Test domestic water boiler shedding, min temp protection, and emergency restore."""
        boiler = WaterHeaterDevice({
            CONF_DEVICE_ID: "boiler_1",
            CONF_DEVICE_NAME: "OSO Hotwater Boiler",
            CONF_DEVICE_TYPE: DEVICE_TYPE_WATER_HEATER,
            CONF_WATER_HEATER_ENTITY: "switch.boiler_relay",
            CONF_WATER_TEMP_SENSOR: "sensor.boiler_tank_temperature",
            CONF_MIN_WATER_TEMP: 50.0,
            CONF_TARGET_WATER_TEMP: 65.0,
            CONF_ESTIMATED_POWER: 2.0,
            CONF_MIN_COOLDOWN: 180,
            CONF_PRIORITY: 1,
        })
        boiler.update_water_heater_state(is_heating=True, current_water_temp=62.0)
        boiler.update_power_reading(2.05)

        # 1. Normal state (62°C > 50°C): safe to shed
        self.assertTrue(boiler.can_shed(self.now))
        self.assertAlmostEqual(boiler.estimated_shed_power_reduction(), 2.05, places=2)

        # Shed boiler
        actions = boiler.plan_shed(self.now)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].domain, "switch")
        self.assertEqual(actions[0].service, "turn_off")
        self.assertTrue(boiler.is_shed)
        self.assertFalse(boiler.is_heating)

        # 2. While shed and in cooldown (30s after shed), water is still 58°C: cannot restore yet
        t_soon = self.now + timedelta(seconds=30)
        self.assertFalse(boiler.can_restore(t_soon))

        # 3. Emergency condition: water temp plunges to 48.0°C (< 50.0°C floor)
        # Even though cooldown is active, can_restore overrides cooldown to protect hot water!
        boiler.update_water_heater_state(is_heating=False, current_water_temp=48.0)
        self.assertTrue(boiler.can_restore(t_soon))

        # Restore boiler
        restore_actions = boiler.plan_restore(t_soon)
        self.assertEqual(len(restore_actions), 1)
        self.assertEqual(restore_actions[0].service, "turn_on")
        self.assertFalse(boiler.is_shed)
        self.assertTrue(boiler.is_heating)

        # 4. If boiler is already cold (45°C <= 50°C), shedding is blocked completely
        boiler.update_water_heater_state(is_heating=True, current_water_temp=45.0)
        t_later = self.now + timedelta(seconds=600)
        self.assertFalse(boiler.can_shed(t_later))

    def test_factory_creation(self):
        """Test factory instantiate correct classes."""
        c = create_device_from_config({
            CONF_DEVICE_ID: "ac1",
            CONF_DEVICE_TYPE: DEVICE_TYPE_CLIMATE,
            CONF_CLIMATE_ENTITY: "climate.test",
        })
        self.assertIsInstance(c, ClimateDevice)

        s = create_device_from_config({
            CONF_DEVICE_ID: "sw1",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.test",
        })
        self.assertIsInstance(s, SwitchDevice)

        e = create_device_from_config({
            CONF_DEVICE_ID: "ev1",
            CONF_DEVICE_TYPE: DEVICE_TYPE_EV,
            CONF_EV_CURRENT_ENTITY: "number.test",
        })
        self.assertIsInstance(e, EVChargerDevice)

        w = create_device_from_config({
            CONF_DEVICE_ID: "wb1",
            CONF_DEVICE_TYPE: DEVICE_TYPE_WATER_HEATER,
            CONF_WATER_HEATER_ENTITY: "switch.boiler",
        })
        self.assertIsInstance(w, WaterHeaterDevice)


if __name__ == "__main__":
    unittest.main()
