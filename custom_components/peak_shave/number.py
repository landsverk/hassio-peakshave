"""Number entities for Peak Shaving (Nettleie) integration."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SAFETY_MARGIN,
    CONF_TARGET_LIMIT,
    DEFAULT_SAFETY_MARGIN,
    DEFAULT_TARGET_LIMIT,
    DOMAIN,
    NAME,
)
from .coordinator import PeakShaveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Peak Shaving number entities."""
    coordinator: PeakShaveCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PeakShaveTargetLimitNumber(coordinator),
            PeakShaveSafetyMarginNumber(coordinator),
        ]
    )


class PeakShaveTargetLimitNumber(
    CoordinatorEntity[PeakShaveCoordinator], NumberEntity
):
    """Number slider to set target kW limit."""

    _attr_has_entity_name = True
    _attr_name = "Target Limit"
    _attr_icon = "mdi:speedometer"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_native_min_value = 0.5
    _attr_native_max_value = 50.0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_target_limit_number"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=NAME,
            manufacturer="Home Assistant Peak Shaver",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )

    @property
    def native_value(self) -> float:
        """Return the target limit in kW."""
        return self.coordinator.data.target_limit_kw

    async def async_set_native_value(self, value: float) -> None:
        """Update target limit."""
        await self.coordinator.async_set_target(value)


class PeakShaveSafetyMarginNumber(
    CoordinatorEntity[PeakShaveCoordinator], NumberEntity
):
    """Number slider to set safety buffer in kW."""

    _attr_has_entity_name = True
    _attr_name = "Safety Margin"
    _attr_icon = "mdi:shield-half-full"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_native_min_value = 0.0
    _attr_native_max_value = 2.0
    _attr_native_step = 0.05
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_safety_margin_number"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=NAME,
            manufacturer="Home Assistant Peak Shaver",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )

    @property
    def native_value(self) -> float:
        """Return current safety margin in kW."""
        return self.coordinator.data.safety_margin_kw

    async def async_set_native_value(self, value: float) -> None:
        """Update safety margin."""
        await self.coordinator.async_set_target(
            self.coordinator.data.target_limit_kw, safety_margin_kw=value
        )
