"""Constants for the Peak Shaving (Nettleie) integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "peak_shave"
NAME: Final = "Peak Shaving (Nettleie)"
VERSION: Final = "0.5.0"

# Configuration Keys - General
CONF_GRID_POWER_SENSOR: Final = "grid_power_sensor"
CONF_GRID_ENERGY_SENSOR: Final = "grid_energy_sensor"
CONF_TARIFF_PRESET: Final = "tariff_preset"
CONF_TARGET_LIMIT: Final = "target_limit"
CONF_SAFETY_MARGIN: Final = "safety_margin"
CONF_DEVICES: Final = "devices"
CONF_ENABLED: Final = "enabled"
CONF_EVALUATION_INTERVAL: Final = "evaluation_interval"
CONF_PERSISTENCE_SECONDS: Final = "persistence_seconds"
CONF_HYSTERESIS_POWER: Final = "hysteresis_power"
CONF_MIN_COOLDOWN_SECONDS: Final = "min_cooldown_seconds"

# Device Configuration Keys
CONF_DEVICE_ID: Final = "id"
CONF_DEVICE_NAME: Final = "name"
CONF_DEVICE_TYPE: Final = "type"
CONF_PRIORITY: Final = "priority"
CONF_POWER_SENSOR: Final = "power_sensor"
CONF_ESTIMATED_POWER: Final = "estimated_power"
CONF_MIN_COOLDOWN: Final = "cooldown_seconds"

# Climate Device Configuration Keys
CONF_CLIMATE_ENTITY: Final = "climate_entity"
CONF_MIN_TEMPERATURE: Final = "min_temperature"
CONF_MAX_TEMPERATURE: Final = "max_temperature"
CONF_CLIMATE_ACTION: Final = "climate_action"
CONF_SETBACK_DELTA: Final = "setback_delta"

# EV Charger Device Configuration Keys
CONF_EV_CURRENT_ENTITY: Final = "ev_current_entity"
CONF_EV_SWITCH_ENTITY: Final = "ev_switch_entity"
CONF_EV_SOC_SENSOR: Final = "ev_soc_sensor"
CONF_EV_MIN_SOC: Final = "min_soc"
CONF_EV_MIN_CURRENT: Final = "min_current"
CONF_EV_MAX_CURRENT: Final = "max_current"
CONF_EV_PHASES: Final = "phases"
CONF_EV_VOLTAGE: Final = "voltage"
# Backwards compatibility aliases
CONF_MIN_SOC: Final = CONF_EV_MIN_SOC
CONF_MIN_CURRENT: Final = CONF_EV_MIN_CURRENT
CONF_MAX_CURRENT: Final = CONF_EV_MAX_CURRENT
CONF_PHASES: Final = CONF_EV_PHASES
CONF_VOLTAGE: Final = CONF_EV_VOLTAGE

# Switch Device Configuration Keys
CONF_SWITCH_ENTITY: Final = "switch_entity"

# Water Heater / Boiler Device Configuration Keys
CONF_WATER_HEATER_ENTITY: Final = "water_heater_entity"
CONF_WATER_TEMP_SENSOR: Final = "water_temp_sensor"
CONF_MIN_WATER_TEMP: Final = "min_water_temp"
CONF_TARGET_WATER_TEMP: Final = "target_water_temp"

# Device Types
DEVICE_TYPE_CLIMATE: Final = "climate"
DEVICE_TYPE_SWITCH: Final = "switch"
DEVICE_TYPE_EV: Final = "ev"
DEVICE_TYPE_WATER_HEATER: Final = "water_heater"

DEVICE_TYPES: Final = [
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_SWITCH,
    DEVICE_TYPE_EV,
    DEVICE_TYPE_WATER_HEATER,
]

# Climate Action Types
ACTION_SETBACK: Final = "setback"
ACTION_TURN_OFF: Final = "turn_off"

# Status States
STATUS_NORMAL: Final = "normal"
STATUS_WARNING: Final = "warning"
STATUS_SHEDDING: Final = "shedding"
STATUS_LIMIT_EXCEEDED: Final = "limit_exceeded"
STATUS_DISABLED: Final = "disabled"

# Defaults
DEFAULT_SAFETY_MARGIN: Final = 0.3  # kW buffer
DEFAULT_TARGET_LIMIT: Final = 5.0  # kW (Lede Tier 1)
DEFAULT_TARIFF_PRESET: Final = "lede_tier_1"
DEFAULT_EVALUATION_INTERVAL: Final = 5  # seconds
DEFAULT_PERSISTENCE_SECONDS: Final = 15  # seconds
DEFAULT_HYSTERESIS_POWER: Final = 0.2  # kW
DEFAULT_MIN_COOLDOWN_SECONDS: Final = 180  # 3 minutes

# Default per device
DEFAULT_CLIMATE_MIN_TEMP: Final = 18.0  # °C
DEFAULT_CLIMATE_MAX_TEMP: Final = 26.0  # °C
DEFAULT_CLIMATE_SETBACK: Final = 2.0  # °C
DEFAULT_CLIMATE_ACTION: Final = ACTION_SETBACK
DEFAULT_CLIMATE_COOLDOWN: Final = 300  # 5 minutes for AC compressor

DEFAULT_EV_MIN_SOC: Final = 40  # %
DEFAULT_EV_MIN_CURRENT: Final = 6  # A (Standard J1772/IEC minimum)
DEFAULT_EV_MAX_CURRENT: Final = 16  # A
DEFAULT_EV_PHASES: Final = 3
DEFAULT_EV_VOLTAGE: Final = 230  # V
DEFAULT_EV_COOLDOWN: Final = 60  # seconds

DEFAULT_SWITCH_ESTIMATED_POWER: Final = 1.5  # kW (e.g. general plug)
DEFAULT_SWITCH_COOLDOWN: Final = 120  # 2 minutes

DEFAULT_WATER_HEATER_MIN_TEMP: Final = 50.0  # °C (frost/legionella safe floor)
DEFAULT_WATER_HEATER_TARGET_TEMP: Final = 65.0  # °C
DEFAULT_WATER_HEATER_ESTIMATED_POWER: Final = 2.0  # kW (typical Norwegian 200L/300L boiler)
DEFAULT_WATER_HEATER_COOLDOWN: Final = 180  # 3 minutes for relay contact protection

# Tariff Presets (specifically targeting Lede and standard Norwegian capacity tariffs)
TARIFF_PRESETS: Final = {
    "lede_tier_1": {
        "name": "Lede Trinn 1: 0 – 5 kW",
        "limit": 5.0,
        "description": "Lede kapasitetsledd 0-5 kW (kr 268,75/mnd)",
    },
    "lede_tier_2": {
        "name": "Lede Trinn 2: 5 – 10 kW",
        "limit": 10.0,
        "description": "Lede kapasitetsledd 5-10 kW (kr 458,75/mnd)",
    },
    "lede_tier_3": {
        "name": "Lede Trinn 3: 10 – 15 kW",
        "limit": 15.0,
        "description": "Lede kapasitetsledd 10-15 kW (kr 647,50/mnd)",
    },
    "lede_tier_4": {
        "name": "Lede Trinn 4: 15 – 20 kW",
        "limit": 20.0,
        "description": "Lede kapasitetsledd 15-20 kW (kr 837,50/mnd)",
    },
    "lede_tier_5": {
        "name": "Lede Trinn 5: 20 – 25 kW",
        "limit": 25.0,
        "description": "Lede kapasitetsledd 20-25 kW (kr 1 027,50/mnd)",
    },
    "norway_tier_0": {
        "name": "Standard Nettleie: 0 – 2 kW",
        "limit": 2.0,
        "description": "Standard lavt trinn 0-2 kW (f.eks. hytter / Elvia)",
    },
    "custom": {
        "name": "Egendefinert grense (Custom kW)",
        "limit": 5.0,
        "description": "Angi valgfri kW-grense manuelt",
    },
}
