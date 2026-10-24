"""Unit tests for the Peak Shaving Engine and Device Controllers."""
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
    CONF_MIN_COOLDOWN,
    CONF_MIN_TEMPERATURE,
    CONF_PRIORITY,
    CONF_SETBACK_DELTA,
    CONF_SWITCH_ENTITY,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_EV,
    DEVICE_TYPE_SWITCH,
    STATUS_LIMIT_EXCEEDED,
    STATUS_NORMAL,
    STATUS_SHEDDING,
    STATUS_WARNING,
)
from custom_components.peak_shave.devices import (
    ClimateDevice,
    EVChargerDevice,
    SwitchDevice,
    create_device_from_config,
)
from custom_components.peak_shave.engine import PeakShavingEngine


class TestPeakShavingEngine(unittest.TestCase):
    """Test suite for the mathematical peak shaving engine."""

    def setUp(self):
        # Target limit: 5.0 kW (Lede Tier 1), Safety Margin: 0.3 kW => Effective limit 4.7 kW
        self.engine = PeakShavingEngine(
            target_limit_kw=5.0,
            safety_margin_kw=0.3,
            persistence_seconds=15,
            hysteresis_power_kw=0.2,
        )
        self.base_time = datetime(2026, 10, 24, 14, 10, 0, tzinfo=timezone.utc)

    def test_normal_consumption_no_shedding(self):
        """Under normal consumption (e.g. 2.5 kW), status should be normal and 0 actions."""
        # 10 minutes into the hour, 2.5 kW consumed so far is 2.5 * (10/60) = 0.416 kWh
        metrics, actions = self.engine.evaluate(
            now=self.base_time,
            grid_power_kw=2.5,
            external_hourly_energy_kwh=0.416,
        )
        self.assertEqual(metrics.status, STATUS_NORMAL)
        self.assertEqual(len(actions), 0)
        self.assertAlmostEqual(metrics.effective_limit_kw, 4.7, places=2)
        self.assertGreater(metrics.headroom_kw, 0)
        self.assertLess(metrics.projected_hour_peak_kw, 4.7)

    def test_persistence_and_shedding(self):
        """Excess power should warn first, then shed after persistence time elapsed."""
        # Setup a switch device (e.g. water heater, 2 kW, priority 1)
        switch = SwitchDevice({
            CONF_DEVICE_ID: "heater",
            CONF_DEVICE_NAME: "Water Heater",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.water_heater",
            CONF_PRIORITY: 1,
            CONF_ESTIMATED_POWER: 2.0,
            CONF_MIN_COOLDOWN: 60,
        })
        switch.update_switch_state(True)
        self.engine.add_device(switch)

        # Minute 30, consumed 2.5 kWh so far.
        # Budget = 4.7 kWh. Remaining budget = 4.7 - 2.5 = 2.2 kWh.
        # Remaining time = 30 min (0.5 h).
        # Max allowable power = 2.2 / 0.5 = 4.4 kW.
        # Current power spikes to 6.0 kW (> 4.4 kW => excess = 1.6 kW).
        t0 = self.base_time.replace(minute=30, second=0)
        metrics0, actions0 = self.engine.evaluate(
            now=t0,
            grid_power_kw=6.0,
            external_hourly_energy_kwh=2.5,
        )
        # Should be in WARNING state initially because persistence is 15 seconds
        self.assertEqual(metrics0.status, STATUS_WARNING)
        self.assertEqual(len(actions0), 0)
        self.assertFalse(switch.is_shed)

        # 5 seconds later: still warning
        t1 = t0 + timedelta(seconds=5)
        metrics1, actions1 = self.engine.evaluate(
            now=t1,
            grid_power_kw=6.0,
            external_hourly_energy_kwh=2.51,
        )
        self.assertEqual(metrics1.status, STATUS_WARNING)
        self.assertEqual(len(actions1), 0)

        # 20 seconds later (past 15s persistence): SHEDDING triggers!
        t2 = t0 + timedelta(seconds=20)
        metrics2, actions2 = self.engine.evaluate(
            now=t2,
            grid_power_kw=6.0,
            external_hourly_energy_kwh=2.53,
        )
        self.assertEqual(metrics2.status, STATUS_SHEDDING)
        self.assertEqual(len(actions2), 1)
        self.assertEqual(actions2[0].service, "turn_off")
        self.assertEqual(actions2[0].target_entity, "switch.water_heater")
        self.assertTrue(switch.is_shed)

    def test_priority_ordering(self):
        """Lower priority devices must shed before higher priority devices."""
        # Device 1: Priority 1 (shed first)
        dev1 = SwitchDevice({
            CONF_DEVICE_ID: "plug_p1",
            CONF_DEVICE_NAME: "Guest Room Heater",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.guest_heater",
            CONF_PRIORITY: 1,
            CONF_ESTIMATED_POWER: 1.0,
            CONF_MIN_COOLDOWN: 10,
        })
        dev1.update_switch_state(True)

        # Device 2: Priority 3 (shed second)
        dev2 = SwitchDevice({
            CONF_DEVICE_ID: "plug_p3",
            CONF_DEVICE_NAME: "Living Room Heater",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.living_heater",
            CONF_PRIORITY: 3,
            CONF_ESTIMATED_POWER: 1.5,
            CONF_MIN_COOLDOWN: 10,
        })
        dev2.update_switch_state(True)

        # Device 3: Priority 7 (shed last)
        dev3 = SwitchDevice({
            CONF_DEVICE_ID: "plug_p7",
            CONF_DEVICE_NAME: "Kitchen Heater",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.kitchen_heater",
            CONF_PRIORITY: 7,
            CONF_ESTIMATED_POWER: 1.0,
            CONF_MIN_COOLDOWN: 10,
        })
        dev3.update_switch_state(True)

        self.engine.add_device(dev1)
        self.engine.add_device(dev2)
        self.engine.add_device(dev3)

        # Massive surge at min 30: grid power = 8.0 kW (> 1.5x limit => triggers immediately!)
        # Max allowed = 4.4 kW, excess = 3.6 kW.
        # Shedding dev1 saves 1.0 kW (excess remaining: 2.6 kW)
        # Shedding dev2 saves 1.5 kW (excess remaining: 1.1 kW)
        # Shedding dev3 saves 1.0 kW (excess remaining: 0.1 kW)
        t = self.base_time.replace(minute=30, second=0)
        metrics, actions = self.engine.evaluate(
            now=t,
            grid_power_kw=8.0,
            external_hourly_energy_kwh=2.5,
        )

        self.assertEqual(metrics.status, STATUS_SHEDDING)
        # Verify order of executed actions matches priority 1, then 3, then 7
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0].target_entity, "switch.guest_heater")
        self.assertEqual(actions[1].target_entity, "switch.living_heater")
        self.assertEqual(actions[2].target_entity, "switch.kitchen_heater")

    def test_restoration_order_and_hysteresis(self):
        """Restoration must occur in reverse priority (highest priority first) and respect hysteresis."""
        dev1 = SwitchDevice({
            CONF_DEVICE_ID: "plug_low",
            CONF_DEVICE_NAME: "Low Priority",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.low",
            CONF_PRIORITY: 1,
            CONF_ESTIMATED_POWER: 1.0,
            CONF_MIN_COOLDOWN: 10,
        })
        dev2 = SwitchDevice({
            CONF_DEVICE_ID: "plug_high",
            CONF_DEVICE_NAME: "High Priority",
            CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
            CONF_SWITCH_ENTITY: "switch.high",
            CONF_PRIORITY: 5,
            CONF_ESTIMATED_POWER: 1.0,
            CONF_MIN_COOLDOWN: 10,
        })

        self.engine.add_device(dev1)
        self.engine.add_device(dev2)

        # Manually mark both as shed 20 seconds ago
        past_time = self.base_time - timedelta(seconds=20)
        dev1.is_shed = True
        dev1.last_state_change = past_time
        dev2.is_shed = True
        dev2.last_state_change = past_time

        # At minute 40, consumed 2.0 kWh.
        # Remaining budget: 4.7 - 2.0 = 2.7 kWh.
        # Remaining time = 20 min (0.333 h).
        # Max allowable power = 2.7 / 0.333 = 8.1 kW.
        # Current grid power is 2.0 kW => Headroom = 6.1 kW!
        # Headroom (6.1 kW) >> dev2 power (1.0 kW) + hysteresis (0.2 kW).
        metrics, actions = self.engine.evaluate(
            now=self.base_time.replace(minute=40),
            grid_power_kw=2.0,
            external_hourly_energy_kwh=2.0,
        )

        # Should restore ONLY ONE device (dev2, high priority) in this cycle (staggered restoration)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].target_entity, "switch.high")
        self.assertFalse(dev2.is_shed)
        self.assertTrue(dev1.is_shed)

    def test_climate_min_temperature_protection(self):
        """AC unit must NOT shed if room temperature is at or below minimum threshold."""
        ac = ClimateDevice({
            CONF_DEVICE_ID: "living_ac",
            CONF_DEVICE_NAME: "Living Room AC",
            CONF_DEVICE_TYPE: DEVICE_TYPE_CLIMATE,
            CONF_CLIMATE_ENTITY: "climate.living_room",
            CONF_PRIORITY: 2,
            CONF_MIN_TEMPERATURE: 19.0,
            CONF_CLIMATE_ACTION: ACTION_SETBACK,
            CONF_SETBACK_DELTA: 2.0,
            CONF_MIN_COOLDOWN: 60,
        })
        # Heating mode, but room temp is 18.5°C (<= min_temperature 19.0°C)
        ac.update_climate_state(
            current_temp=18.5,
            target_temp=21.0,
            hvac_mode="heat",
            hvac_action="heating",
        )
        self.engine.add_device(ac)

        t = self.base_time.replace(minute=30)
        # Power surge requiring shed
        metrics, actions = self.engine.evaluate(
            now=t,
            grid_power_kw=8.0,
            external_hourly_energy_kwh=2.5,
        )
        # AC must be protected from shedding!
        self.assertEqual(len(actions), 0)
        self.assertFalse(ac.is_shed)

        # Now test when temperature is comfortably at 22°C (> 19°C)
        ac.update_climate_state(
            current_temp=22.0,
            target_temp=22.0,
            hvac_mode="heat",
            hvac_action="heating",
        )
        metrics2, actions2 = self.engine.evaluate(
            now=t,
            grid_power_kw=8.0,
            external_hourly_energy_kwh=2.5,
        )
        # AC can now safely shed via setback
        self.assertEqual(len(actions2), 1)
        self.assertEqual(actions2[0].service, "set_temperature")
        self.assertEqual(actions2[0].service_data["temperature"], 20.0)  # 22 - 2
        self.assertTrue(ac.is_shed)

    def test_ev_charger_min_soc_and_modulation(self):
        """EV Charger must protect low SoC and modulate current in steps before pausing."""
        ev = EVChargerDevice({
            CONF_DEVICE_ID: "ev_charger",
            CONF_DEVICE_NAME: "Easee EV Charger",
            CONF_DEVICE_TYPE: DEVICE_TYPE_EV,
            CONF_EV_CURRENT_ENTITY: "number.easee_charger_circuit_limit",
            CONF_EV_SWITCH_ENTITY: "switch.easee_charger_is_enabled",
            CONF_EV_MIN_SOC: 40,
            CONF_EV_MIN_CURRENT: 6,
            CONF_EV_MAX_CURRENT: 16,
            CONF_EV_PHASES: 3,
            CONF_PRIORITY: 1,
            CONF_MIN_COOLDOWN: 10,
        })
        self.engine.add_device(ev)

        # Case 1: Battery is at 25% (< min_soc 40%) -> Must NOT shed!
        ev.update_ev_state(current_amps=16, is_charging=True, battery_soc=25)
        t = self.base_time.replace(minute=30)
        metrics, actions = self.engine.evaluate(
            now=t,
            grid_power_kw=8.0,
            external_hourly_energy_kwh=2.5,
        )
        self.assertEqual(len(actions), 0)
        self.assertFalse(ev.is_shed)

        # Case 2: Battery is at 60% (>= min_soc 40%) -> Throttles current step-down!
        ev.update_ev_state(current_amps=16, is_charging=True, battery_soc=60)
        metrics2, actions2 = self.engine.evaluate(
            now=t,
            grid_power_kw=8.0,
            external_hourly_energy_kwh=2.5,
        )
        self.assertEqual(len(actions2), 1)
        self.assertEqual(actions2[0].domain, "number")
        self.assertEqual(actions2[0].service, "set_value")
        self.assertEqual(actions2[0].service_data["value"], 11)  # Stepped down from 16 to 11
        self.assertTrue(ev.is_shed)
        self.assertEqual(ev.shed_stage, 1)

    def test_hour_rollover(self):
        """At :00:00 rollover, internal hourly energy resets."""
        t_55 = datetime(2026, 10, 24, 14, 55, 0, tzinfo=timezone.utc)
        metrics1, _ = self.engine.evaluate(now=t_55, grid_power_kw=3.0)

        t_02 = datetime(2026, 10, 24, 15, 2, 0, tzinfo=timezone.utc)
        metrics2, _ = self.engine.evaluate(now=t_02, grid_power_kw=3.0)

        # After rollover at 15:02, minutes elapsed should be ~2 min, not 62 min
        self.assertAlmostEqual(metrics2.minutes_elapsed, 2.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
