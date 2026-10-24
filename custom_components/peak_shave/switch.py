"""Switch entity for Peak Shaving (Nettleie) integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import PeakShaveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Peak Shaving switch platform."""
    coordinator: PeakShaveCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PeakShaveMasterSwitch(coordinator)])


class PeakShaveMasterSwitch(
    CoordinatorEntity[PeakShaveCoordinator], SwitchEntity
):
    """Master switch to enable/disable peak shaving automation."""

    _attr_has_entity_name = True
    _attr_name = "Automation Enabled"
    _attr_icon = "mdi:power-cycle"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_master_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_hub")},
            name=NAME,
            manufacturer="Home Assistant Peak Shaver",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )

    @property
    def is_on(self) -> bool:
        """Return True if peak shaving automation is enabled."""
        return self.coordinator.engine.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the peak shaving automation."""
        await self.coordinator.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the peak shaving automation and restore shed devices."""
        await self.coordinator.async_set_enabled(False)
        await self.coordinator.async_restore_all()
