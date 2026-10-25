"""DataUpdateCoordinator for the Peak Shaving integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICES,
    CONF_ENABLED,
    CONF_GRID_ENERGY_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_HYSTERESIS_POWER,
    CONF_PERSISTENCE_SECONDS,
    CONF_SAFETY_MARGIN,
    CONF_TARGET_LIMIT,
    CONF_TARIFF_PRESET,
    DEFAULT_EVALUATION_INTERVAL,
    DEFAULT_HYSTERESIS_POWER,
    DEFAULT_PERSISTENCE_SECONDS,
    DEFAULT_SAFETY_MARGIN,
    DEFAULT_TARGET_LIMIT,
    DEFAULT_TARIFF_PRESET,
    DOMAIN,
    TARIFF_PRESETS,
)
from .devices import (
    BaseDevice,
    ClimateDevice,
    EVChargerDevice,
    SwitchDevice,
    WaterHeaterDevice,
    create_device_from_config,
)
from .engine import EngineMetrics, PeakShavingEngine
from .storage import PeakShaveStorage

_LOGGER = logging.getLogger(__name__)


def _parse_float(state_value: Any) -> Optional[float]:
    """Safely parse float from state value."""
    if state_value in (None, "unknown", "unavailable"):
        return None
    try:
        return float(state_value)
    except (ValueError, TypeError):
        return None


class PeakShaveCoordinator(DataUpdateCoordinator[EngineMetrics]):
    """Coordinates peak shaving evaluations and device dispatch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self._unsub_trackers: List[Any] = []

        # Get combined options and data
        cfg = {**entry.data, **entry.options}
        self.grid_power_sensor: str = cfg[CONF_GRID_POWER_SENSOR]
        self.grid_energy_sensor: Optional[str] = cfg.get(CONF_GRID_ENERGY_SENSOR)

        target_limit = float(cfg.get(CONF_TARGET_LIMIT, DEFAULT_TARGET_LIMIT))
        safety_margin = float(cfg.get(CONF_SAFETY_MARGIN, DEFAULT_SAFETY_MARGIN))
        persistence = int(cfg.get(CONF_PERSISTENCE_SECONDS, DEFAULT_PERSISTENCE_SECONDS))
        hysteresis = float(cfg.get(CONF_HYSTERESIS_POWER, DEFAULT_HYSTERESIS_POWER))

        self.engine = PeakShavingEngine(
            target_limit_kw=target_limit,
            safety_margin_kw=safety_margin,
            persistence_seconds=persistence,
            hysteresis_power_kw=hysteresis,
        )
        self.engine.enabled = cfg.get(CONF_ENABLED, True)

        preset_key = cfg.get(CONF_TARIFF_PRESET, DEFAULT_TARIFF_PRESET)
        if preset_key in TARIFF_PRESETS:
            self.engine.tier_name = TARIFF_PRESETS[preset_key]["name"]

        # Instantiate devices
        self._reload_devices(cfg.get(CONF_DEVICES, []))

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_EVALUATION_INTERVAL),
        )

    def _reload_devices(self, raw_device_configs: List[Dict[str, Any]]) -> None:
        """Instantiate and register device controllers."""
        self.engine.clear_devices()
        for dev_cfg in raw_device_configs:
            try:
                device = create_device_from_config(dev_cfg)
                self.engine.add_device(device)
                _LOGGER.debug("Loaded device: %s (%s)", device.name, device.device_type)
            except Exception as ex:
                _LOGGER.error("Failed to load device config %s: %s", dev_cfg, ex)

    def update_config(self) -> None:
        """Update coordinator when options flow or controls change."""
        cfg = {**self.entry.data, **self.entry.options}
        self.grid_power_sensor = cfg[CONF_GRID_POWER_SENSOR]
        self.grid_energy_sensor = cfg.get(CONF_GRID_ENERGY_SENSOR)

        target_limit = float(cfg.get(CONF_TARGET_LIMIT, DEFAULT_TARGET_LIMIT))
        safety_margin = float(cfg.get(CONF_SAFETY_MARGIN, DEFAULT_SAFETY_MARGIN))
        persistence = int(cfg.get(CONF_PERSISTENCE_SECONDS, DEFAULT_PERSISTENCE_SECONDS))
        hysteresis = float(cfg.get(CONF_HYSTERESIS_POWER, DEFAULT_HYSTERESIS_POWER))

        self.engine.set_target(target_limit, safety_margin)
        self.engine.persistence_seconds = persistence
        self.engine.hysteresis_power_kw = hysteresis
        self.engine.enabled = cfg.get(CONF_ENABLED, True)

        preset_key = cfg.get(CONF_TARIFF_PRESET, DEFAULT_TARIFF_PRESET)
        if preset_key in TARIFF_PRESETS:
            self.engine.tier_name = TARIFF_PRESETS[preset_key]["name"]

        self._reload_devices(cfg.get(CONF_DEVICES, []))

    def _read_power_sensor_kw(self, entity_id: str) -> Optional[float]:
        """Read a power sensor, auto-converting Watts to kW if necessary."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        val = _parse_float(state.state)
        if val is None:
            return None

        # Check unit of measurement
        unit = state.attributes.get("unit_of_measurement", "").strip()
        if unit.lower() in ("w", "va", "var"):
            return val / 1000.0
        return val

    def _read_energy_sensor_kwh(self, entity_id: str) -> Optional[float]:
        """Read an energy sensor, auto-converting Wh to kWh if necessary."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        val = _parse_float(state.state)
        if val is None:
            return None

        unit = state.attributes.get("unit_of_measurement", "").strip()
        if unit.lower() == "wh":
            return val / 1000.0
        return val

    def _update_device_states(self) -> None:
        """Sync Home Assistant entity states into device controller models."""
        for device in self.engine.get_devices():
            # Update power sensor reading if defined
            if device.power_sensor:
                p_kw = self._read_power_sensor_kw(device.power_sensor)
                device.update_power_reading(p_kw)

            if isinstance(device, ClimateDevice):
                state = self.hass.states.get(device.climate_entity)
                if state:
                    cur_temp = _parse_float(state.attributes.get("current_temperature"))
                    tgt_temp = _parse_float(state.attributes.get("temperature"))
                    hvac_mode = state.state
                    hvac_action = state.attributes.get("hvac_action")
                    device.update_climate_state(
                        cur_temp, tgt_temp, hvac_mode, hvac_action
                    )

            elif isinstance(device, EVChargerDevice):
                # Read current entity
                curr_state = self.hass.states.get(device.current_entity)
                amps = _parse_float(curr_state.state) if curr_state else None

                # Read switch entity if configured
                is_charging = True
                if device.switch_entity:
                    sw_state = self.hass.states.get(device.switch_entity)
                    if sw_state:
                        is_charging = sw_state.state == "on"

                # Read SoC sensor if configured
                soc: Optional[float] = None
                if device.soc_sensor:
                    soc_state = self.hass.states.get(device.soc_sensor)
                    if soc_state:
                        soc = _parse_float(soc_state.state)

                device.update_ev_state(amps, is_charging, soc)

            elif isinstance(device, SwitchDevice):
                sw_state = self.hass.states.get(device.switch_entity)
                if sw_state:
                    device.update_switch_state(sw_state.state == "on")

            elif isinstance(device, WaterHeaterDevice):
                # Read boiler temperature from sensor or entity attribute
                temp: Optional[float] = None
                if device.temp_sensor:
                    t_state = self.hass.states.get(device.temp_sensor)
                    if t_state:
                        temp = _parse_float(t_state.state)

                heater_state = self.hass.states.get(device.heater_entity)
                is_heating = True
                op_mode: Optional[str] = None
                if heater_state:
                    if temp is None:
                        temp = _parse_float(
                            heater_state.attributes.get("current_temperature")
                        )
                    op_mode = heater_state.state
                    domain = device.heater_entity.split(".")[0]
                    if domain == "water_heater":
                        is_heating = op_mode not in ("off", "eco", "away")
                    else:
                        is_heating = op_mode == "on"

                device.update_water_heater_state(is_heating, temp, op_mode)

    async def _async_update_data(self) -> EngineMetrics:
        """Fetch latest state, run evaluation, and dispatch any control actions."""
        # 1. Read main grid power
        grid_power_kw = self._read_power_sensor_kw(self.grid_power_sensor)
        if grid_power_kw is None:
            _LOGGER.debug(
                "Grid power sensor %s is currently unavailable or non-numeric",
                self.grid_power_sensor,
            )
            return self.engine.metrics

        # 2. Read optional hourly energy sensor
        hourly_energy_kwh: Optional[float] = None
        if self.grid_energy_sensor:
            hourly_energy_kwh = self._read_energy_sensor_kwh(self.grid_energy_sensor)

        # 3. Synchronize device states
        self._update_device_states()

        # 4. Run peak shaving evaluation
        now = datetime.now(timezone.utc)
        metrics, actions = self.engine.evaluate(
            now=now,
            grid_power_kw=grid_power_kw,
            external_hourly_energy_kwh=hourly_energy_kwh,
        )

        # 5. Dispatch generated actions
        for action in actions:
            try:
                _LOGGER.info(
                    "Executing peak shave action: %s.%s on %s (data: %s)",
                    action.domain,
                    action.service,
                    action.target_entity,
                    action.service_data,
                )
                service_data = dict(action.service_data)
                service_data["entity_id"] = action.target_entity
                await self.hass.services.async_call(
                    action.domain,
                    action.service,
                    service_data,
                    blocking=False,
                )
                # Fire an event so user automations can notify (e.g. push notification to phone)
                self.hass.bus.async_fire(
                    f"{DOMAIN}_action",
                    {
                        "domain": action.domain,
                        "service": action.service,
                        "entity_id": action.target_entity,
                        "description": action.description,
                        "status": metrics.status,
                    },
                )
            except Exception as ex:
                _LOGGER.error(
                    "Error executing action %s on %s: %s",
                    action.service,
                    action.target_entity,
                    ex,
                )

        return metrics

    async def async_restore_all(self) -> None:
        """Manually restore all shed devices."""
        now = datetime.now(timezone.utc)
        actions = self.engine.restore_all(now)
        for action in actions:
            try:
                service_data = dict(action.service_data)
                service_data["entity_id"] = action.target_entity
                await self.hass.services.async_call(
                    action.domain, action.service, service_data, blocking=False
                )
            except Exception as ex:
                _LOGGER.error("Error restoring %s: %s", action.target_entity, ex)
        await self.async_refresh()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Enable or disable peak shaving engine."""
        self.engine.enabled = enabled
        options = dict(self.entry.options or self.entry.data)
        options[CONF_ENABLED] = enabled
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.async_refresh()

    async def async_set_target(
        self, target_limit_kw: float, safety_margin_kw: Optional[float] = None
    ) -> None:
        """Dynamically set target limit and safety margin."""
        self.engine.set_target(target_limit_kw, safety_margin_kw)
        options = dict(self.entry.options or self.entry.data)
        options[CONF_TARGET_LIMIT] = target_limit_kw
        if safety_margin_kw is not None:
            options[CONF_SAFETY_MARGIN] = safety_margin_kw
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.async_refresh()

    async def async_set_tariff_preset(self, preset_key: str) -> None:
        """Change tariff preset directly."""
        if preset_key in TARIFF_PRESETS:
            preset = TARIFF_PRESETS[preset_key]
            self.engine.tier_name = preset["name"]
            if preset_key != "custom":
                self.engine.set_target(preset["limit"])

            options = dict(self.entry.options or self.entry.data)
            options[CONF_TARIFF_PRESET] = preset_key
            if preset_key != "custom":
                options[CONF_TARGET_LIMIT] = preset["limit"]
            self.hass.config_entries.async_update_entry(self.entry, options=options)
            await self.async_refresh()

    async def async_update_device_setting(
        self, device_id: str, setting_key: str, value: Any
    ) -> None:
        """Update a specific setting for a device directly."""
        options = dict(self.entry.options or self.entry.data)
        devices = list(options.get(CONF_DEVICES, []))
        updated = False
        for d in devices:
            if d.get("id") == device_id:
                d[setting_key] = value
                updated = True
                break
        if updated:
            options[CONF_DEVICES] = devices
            self.hass.config_entries.async_update_entry(self.entry, options=options)
            self.update_config()
            await self.async_refresh()

    async def async_remove_device_by_id(self, device_id: str) -> None:
        """Remove a device by ID."""
        options = dict(self.entry.options or self.entry.data)
        devices = [d for d in options.get(CONF_DEVICES, []) if d.get("id") != device_id]
        options[CONF_DEVICES] = devices
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.update_config()
        await self.async_refresh()
