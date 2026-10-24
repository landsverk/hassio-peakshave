"""Select entity for Peak Shaving (Nettleie) integration."""
from __future__ import annotations

from typing import List

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TARIFF_PRESET, DEFAULT_TARIFF_PRESET, DOMAIN, NAME, TARIFF_PRESETS
from .coordinator import PeakShaveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Peak Shaving select platform."""
    coordinator: PeakShaveCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PeakShaveTariffTierSelect(coordinator)])


class PeakShaveTariffTierSelect(
    CoordinatorEntity[PeakShaveCoordinator], SelectEntity
):
    """Dropdown to select the active Norwegian tariff tier."""

    _attr_has_entity_name = True
    _attr_name = "Tariff Tier"
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_tariff_tier_select"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_hub")},
            name=NAME,
            manufacturer="Home Assistant Peak Shaver",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )
        self._options_map = {k: v["name"] for k, v in TARIFF_PRESETS.items()}
        self._reverse_map = {v["name"]: k for k, v in TARIFF_PRESETS.items()}
        self._attr_options: List[str] = list(self._options_map.values())

    @property
    def current_option(self) -> str:
        """Return the current selected tariff tier name."""
        cfg = {**self.coordinator.entry.data, **self.coordinator.entry.options}
        preset_key = cfg.get(CONF_TARIFF_PRESET, DEFAULT_TARIFF_PRESET)
        return self._options_map.get(preset_key, list(self._options_map.values())[0])

    async def async_select_option(self, option: str) -> None:
        """Update active tariff tier preset."""
        preset_key = self._reverse_map.get(option)
        if preset_key:
            await self.coordinator.async_set_tariff_preset(preset_key)
