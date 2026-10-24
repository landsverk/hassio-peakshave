"""Config and Options flows for Peak Shaving (Nettleie) integration."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    ACTION_SETBACK,
    ACTION_TURN_OFF,
    CONF_CLIMATE_ACTION,
    CONF_CLIMATE_ENTITY,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_DEVICES,
    CONF_ENABLED,
    CONF_ESTIMATED_POWER,
    CONF_EV_CURRENT_ENTITY,
    CONF_EV_MAX_CURRENT,
    CONF_EV_MIN_CURRENT,
    CONF_EV_MIN_SOC,
    CONF_EV_PHASES,
    CONF_EV_SOC_SENSOR,
    CONF_EV_SWITCH_ENTITY,
    CONF_EV_VOLTAGE,
    CONF_GRID_ENERGY_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_HYSTERESIS_POWER,
    CONF_MAX_TEMPERATURE,
    CONF_MIN_COOLDOWN,
    CONF_MIN_TEMPERATURE,
    CONF_PERSISTENCE_SECONDS,
    CONF_POWER_SENSOR,
    CONF_PRIORITY,
    CONF_SAFETY_MARGIN,
    CONF_SETBACK_DELTA,
    CONF_SWITCH_ENTITY,
    CONF_TARGET_LIMIT,
    CONF_TARIFF_PRESET,
    DEFAULT_CLIMATE_ACTION,
    DEFAULT_CLIMATE_COOLDOWN,
    DEFAULT_CLIMATE_MAX_TEMP,
    DEFAULT_CLIMATE_MIN_TEMP,
    DEFAULT_CLIMATE_SETBACK,
    DEFAULT_EV_COOLDOWN,
    DEFAULT_EV_MAX_CURRENT,
    DEFAULT_EV_MIN_CURRENT,
    DEFAULT_EV_MIN_SOC,
    DEFAULT_EV_PHASES,
    DEFAULT_EV_VOLTAGE,
    DEFAULT_HYSTERESIS_POWER,
    DEFAULT_PERSISTENCE_SECONDS,
    DEFAULT_SAFETY_MARGIN,
    DEFAULT_SWITCH_COOLDOWN,
    DEFAULT_SWITCH_ESTIMATED_POWER,
    DEFAULT_TARGET_LIMIT,
    DEFAULT_TARIFF_PRESET,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_EV,
    DEVICE_TYPE_SWITCH,
    DOMAIN,
    NAME,
    TARIFF_PRESETS,
)

_LOGGER = logging.getLogger(__name__)


def _build_tariff_options() -> List[selector.SelectOptionDict]:
    """Build list of tariff options for the UI select dropdown."""
    options = []
    for key, val in TARIFF_PRESETS.items():
        options.append(
            selector.SelectOptionDict(
                value=key,
                label=f"{val['name']} ({val['limit']} kW)",
            )
        )
    return options


class PeakShaveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Peak Shaving (Nettleie)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: Dict[str, str] = {}

        # Allow only one instance of peak_shave
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # Sync target limit with selected preset if preset is not custom
            preset_key = user_input.get(CONF_TARIFF_PRESET, DEFAULT_TARIFF_PRESET)
            if preset_key in TARIFF_PRESETS and preset_key != "custom":
                user_input[CONF_TARGET_LIMIT] = TARIFF_PRESETS[preset_key]["limit"]

            # Initialize empty devices list and enabled flag
            data = {
                CONF_GRID_POWER_SENSOR: user_input[CONF_GRID_POWER_SENSOR],
                CONF_GRID_ENERGY_SENSOR: user_input.get(CONF_GRID_ENERGY_SENSOR),
                CONF_TARIFF_PRESET: preset_key,
                CONF_TARGET_LIMIT: user_input[CONF_TARGET_LIMIT],
                CONF_SAFETY_MARGIN: user_input.get(
                    CONF_SAFETY_MARGIN, DEFAULT_SAFETY_MARGIN
                ),
                CONF_ENABLED: True,
                CONF_DEVICES: [],
            }
            return self.async_create_entry(title=NAME, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_GRID_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_GRID_ENERGY_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_TARIFF_PRESET, default=DEFAULT_TARIFF_PRESET
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_build_tariff_options(),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_TARGET_LIMIT, default=DEFAULT_TARGET_LIMIT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=50.0,
                        step=0.1,
                        unit_of_measurement="kW",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SAFETY_MARGIN, default=DEFAULT_SAFETY_MARGIN
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=2.0,
                        step=0.05,
                        unit_of_measurement="kW",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"name": NAME},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return PeakShaveOptionsFlowHandler(config_entry)


class PeakShaveOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow to manage controllable devices and settings via GUI."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._options = dict(config_entry.options or config_entry.data)
        if CONF_DEVICES not in self._options:
            self._options[CONF_DEVICES] = list(
                config_entry.data.get(CONF_DEVICES, [])
            )

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Show main options menu with device count and actions."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "menu_add_ac",
                "menu_add_ev",
                "menu_add_switch",
                "menu_remove_device",
                "menu_general",
            ],
        )

    async def async_step_menu_add_ac(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Add an AC / Heat Pump climate device."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            device_id = f"ac_{uuid.uuid4().hex[:6]}"
            new_device = {
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: user_input.get(
                    CONF_DEVICE_NAME, user_input[CONF_CLIMATE_ENTITY]
                ),
                CONF_DEVICE_TYPE: DEVICE_TYPE_CLIMATE,
                CONF_CLIMATE_ENTITY: user_input[CONF_CLIMATE_ENTITY],
                CONF_POWER_SENSOR: user_input.get(CONF_POWER_SENSOR),
                CONF_ESTIMATED_POWER: user_input.get(CONF_ESTIMATED_POWER, 1.2),
                CONF_PRIORITY: user_input.get(CONF_PRIORITY, 5),
                CONF_MIN_TEMPERATURE: user_input.get(
                    CONF_MIN_TEMPERATURE, DEFAULT_CLIMATE_MIN_TEMP
                ),
                CONF_MAX_TEMPERATURE: user_input.get(
                    CONF_MAX_TEMPERATURE, DEFAULT_CLIMATE_MAX_TEMP
                ),
                CONF_CLIMATE_ACTION: user_input.get(
                    CONF_CLIMATE_ACTION, DEFAULT_CLIMATE_ACTION
                ),
                CONF_SETBACK_DELTA: user_input.get(
                    CONF_SETBACK_DELTA, DEFAULT_CLIMATE_SETBACK
                ),
                CONF_MIN_COOLDOWN: user_input.get(
                    CONF_MIN_COOLDOWN, DEFAULT_CLIMATE_COOLDOWN
                ),
            }
            devices = list(self._options.get(CONF_DEVICES, []))
            devices.append(new_device)
            self._options[CONF_DEVICES] = devices
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_CLIMATE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Optional(CONF_DEVICE_NAME): selector.TextSelector(),
                vol.Optional(CONF_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_ESTIMATED_POWER, default=1.2
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=10.0,
                        step=0.1,
                        unit_of_measurement="kW",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_PRIORITY, default=5): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=10,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_CLIMATE_ACTION, default=DEFAULT_CLIMATE_ACTION
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=ACTION_SETBACK,
                                label="Temperatursenkning (Setback) - Beholder ventilasjon",
                            ),
                            selector.SelectOptionDict(
                                value=ACTION_TURN_OFF,
                                label="Slå helt av (Turn Off HVAC)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SETBACK_DELTA, default=DEFAULT_CLIMATE_SETBACK
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0,
                        max=5.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MIN_TEMPERATURE, default=DEFAULT_CLIMATE_MIN_TEMP
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10.0,
                        max=24.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MAX_TEMPERATURE, default=DEFAULT_CLIMATE_MAX_TEMP
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=20.0,
                        max=30.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MIN_COOLDOWN, default=DEFAULT_CLIMATE_COOLDOWN
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=60,
                        max=900,
                        step=30,
                        unit_of_measurement="sekunder",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="menu_add_ac", data_schema=schema, errors=errors
        )

    async def async_step_menu_add_ev(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Add an EV Charger device."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            device_id = f"ev_{uuid.uuid4().hex[:6]}"
            new_device = {
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: user_input.get(
                    CONF_DEVICE_NAME, user_input[CONF_EV_CURRENT_ENTITY]
                ),
                CONF_DEVICE_TYPE: DEVICE_TYPE_EV,
                CONF_EV_CURRENT_ENTITY: user_input[CONF_EV_CURRENT_ENTITY],
                CONF_EV_SWITCH_ENTITY: user_input.get(CONF_EV_SWITCH_ENTITY),
                CONF_EV_SOC_SENSOR: user_input.get(CONF_EV_SOC_SENSOR),
                CONF_POWER_SENSOR: user_input.get(CONF_POWER_SENSOR),
                CONF_PRIORITY: user_input.get(CONF_PRIORITY, 2),
                CONF_EV_MIN_SOC: user_input.get(CONF_EV_MIN_SOC, DEFAULT_EV_MIN_SOC),
                CONF_EV_MIN_CURRENT: user_input.get(
                    CONF_EV_MIN_CURRENT, DEFAULT_EV_MIN_CURRENT
                ),
                CONF_EV_MAX_CURRENT: user_input.get(
                    CONF_EV_MAX_CURRENT, DEFAULT_EV_MAX_CURRENT
                ),
                CONF_EV_PHASES: user_input.get(CONF_EV_PHASES, DEFAULT_EV_PHASES),
                CONF_EV_VOLTAGE: user_input.get(CONF_EV_VOLTAGE, DEFAULT_EV_VOLTAGE),
                CONF_MIN_COOLDOWN: user_input.get(
                    CONF_MIN_COOLDOWN, DEFAULT_EV_COOLDOWN
                ),
            }
            devices = list(self._options.get(CONF_DEVICES, []))
            devices.append(new_device)
            self._options[CONF_DEVICES] = devices
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_EV_CURRENT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Optional(CONF_DEVICE_NAME): selector.TextSelector(),
                vol.Optional(CONF_EV_SWITCH_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Optional(CONF_EV_SOC_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_PRIORITY, default=2): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=10,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_EV_MIN_SOC, default=DEFAULT_EV_MIN_SOC
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=90,
                        step=5,
                        unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_EV_MIN_CURRENT, default=DEFAULT_EV_MIN_CURRENT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=6,
                        max=16,
                        step=1,
                        unit_of_measurement="A",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_EV_MAX_CURRENT, default=DEFAULT_EV_MAX_CURRENT
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=32,
                        step=1,
                        unit_of_measurement="A",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(CONF_EV_PHASES, default=DEFAULT_EV_PHASES): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="1", label="1-fase"),
                            selector.SelectOptionDict(value="3", label="3-fase"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_MIN_COOLDOWN, default=DEFAULT_EV_COOLDOWN
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=300,
                        step=10,
                        unit_of_measurement="sekunder",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="menu_add_ev", data_schema=schema, errors=errors
        )

    async def async_step_menu_add_switch(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Add a Smart Plug / Relay / Switch device."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            device_id = f"switch_{uuid.uuid4().hex[:6]}"
            new_device = {
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: user_input.get(
                    CONF_DEVICE_NAME, user_input[CONF_SWITCH_ENTITY]
                ),
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_SWITCH_ENTITY: user_input[CONF_SWITCH_ENTITY],
                CONF_POWER_SENSOR: user_input.get(CONF_POWER_SENSOR),
                CONF_ESTIMATED_POWER: user_input.get(
                    CONF_ESTIMATED_POWER, DEFAULT_SWITCH_ESTIMATED_POWER
                ),
                CONF_PRIORITY: user_input.get(CONF_PRIORITY, 3),
                CONF_MIN_COOLDOWN: user_input.get(
                    CONF_MIN_COOLDOWN, DEFAULT_SWITCH_COOLDOWN
                ),
            }
            devices = list(self._options.get(CONF_DEVICES, []))
            devices.append(new_device)
            self._options[CONF_DEVICES] = devices
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_SWITCH_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Optional(CONF_DEVICE_NAME): selector.TextSelector(),
                vol.Optional(CONF_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_ESTIMATED_POWER, default=DEFAULT_SWITCH_ESTIMATED_POWER
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=10.0,
                        step=0.1,
                        unit_of_measurement="kW",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_PRIORITY, default=3): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=10,
                        step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MIN_COOLDOWN, default=DEFAULT_SWITCH_COOLDOWN
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=600,
                        step=30,
                        unit_of_measurement="sekunder",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="menu_add_switch", data_schema=schema, errors=errors
        )

    async def async_step_menu_remove_device(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Remove a controllable device."""
        errors: Dict[str, str] = {}
        devices = list(self._options.get(CONF_DEVICES, []))

        if not devices:
            return self.async_abort(reason="no_devices_configured")

        if user_input is not None:
            dev_id_to_remove = user_input["device_to_remove"]
            self._options[CONF_DEVICES] = [
                d for d in devices if d.get(CONF_DEVICE_ID) != dev_id_to_remove
            ]
            return self.async_create_entry(title="", data=self._options)

        device_options = [
            selector.SelectOptionDict(
                value=d.get(CONF_DEVICE_ID, ""),
                label=f"{d.get(CONF_DEVICE_NAME, d.get(CONF_DEVICE_ID))} (Prioritet {d.get(CONF_PRIORITY, 5)}, {d.get(CONF_DEVICE_TYPE)})",
            )
            for d in devices
        ]

        schema = vol.Schema(
            {
                vol.Required("device_to_remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="menu_remove_device", data_schema=schema, errors=errors
        )

    async def async_step_menu_general(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Configure general tariff settings and limits."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            preset_key = user_input.get(CONF_TARIFF_PRESET, DEFAULT_TARIFF_PRESET)
            if preset_key in TARIFF_PRESETS and preset_key != "custom":
                user_input[CONF_TARGET_LIMIT] = TARIFF_PRESETS[preset_key]["limit"]

            self._options[CONF_GRID_POWER_SENSOR] = user_input[CONF_GRID_POWER_SENSOR]
            self._options[CONF_GRID_ENERGY_SENSOR] = user_input.get(
                CONF_GRID_ENERGY_SENSOR
            )
            self._options[CONF_TARIFF_PRESET] = preset_key
            self._options[CONF_TARGET_LIMIT] = user_input[CONF_TARGET_LIMIT]
            self._options[CONF_SAFETY_MARGIN] = user_input[CONF_SAFETY_MARGIN]
            self._options[CONF_PERSISTENCE_SECONDS] = user_input[
                CONF_PERSISTENCE_SECONDS
            ]
            self._options[CONF_HYSTERESIS_POWER] = user_input[CONF_HYSTERESIS_POWER]

            return self.async_create_entry(title="", data=self._options)

        current_preset = self._options.get(CONF_TARIFF_PRESET, DEFAULT_TARIFF_PRESET)
        current_limit = self._options.get(CONF_TARGET_LIMIT, DEFAULT_TARGET_LIMIT)
        current_margin = self._options.get(CONF_SAFETY_MARGIN, DEFAULT_SAFETY_MARGIN)
        current_persistence = self._options.get(
            CONF_PERSISTENCE_SECONDS, DEFAULT_PERSISTENCE_SECONDS
        )
        current_hysteresis = self._options.get(
            CONF_HYSTERESIS_POWER, DEFAULT_HYSTERESIS_POWER
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_GRID_POWER_SENSOR,
                    default=self._options.get(CONF_GRID_POWER_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_GRID_ENERGY_SENSOR,
                    default=self._options.get(CONF_GRID_ENERGY_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_TARIFF_PRESET, default=current_preset
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_build_tariff_options(),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_TARGET_LIMIT, default=current_limit
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=50.0,
                        step=0.1,
                        unit_of_measurement="kW",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SAFETY_MARGIN, default=current_margin
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=2.0,
                        step=0.05,
                        unit_of_measurement="kW",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_PERSISTENCE_SECONDS, default=current_persistence
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=60,
                        step=5,
                        unit_of_measurement="sekunder",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_HYSTERESIS_POWER, default=current_hysteresis
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.05,
                        max=1.0,
                        step=0.05,
                        unit_of_measurement="kW",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="menu_general", data_schema=schema, errors=errors
        )
