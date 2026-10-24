"""Number entities for Peak Shaving (Nettleie) integration."""
from __future__ import annotations

import logging
from typing import List, Optional, Set

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MIN_TEMPERATURE,
    CONF_MIN_WATER_TEMP,
    CONF_PRIORITY,
    CONF_SAFETY_MARGIN,
    CONF_SETBACK_DELTA,
    CONF_TARGET_LIMIT,
    DEFAULT_SAFETY_MARGIN,
    DEFAULT_TARGET_LIMIT,
    DOMAIN,
    NAME,
)
from .coordinator import PeakShaveCoordinator
from .devices import (
    BaseDevice,
    ClimateDevice,
    EVChargerDevice,
    SwitchDevice,
    WaterHeaterDevice,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Peak Shaving number entities."""
    coordinator: PeakShaveCoordinator = hass.data[DOMAIN][entry.entry_id]

    # 1. Main Hub Number Sliders
    hub_numbers: List[NumberEntity] = [
        PeakShaveTargetLimitNumber(coordinator),
        PeakShaveSafetyMarginNumber(coordinator),
    ]
    async_add_entities(hub_numbers)

    # 2. Per-Device Number Sliders (appear on the device's native HA page)
    known_devices: Set[str] = set()

    @callback
    def _add_device_entities() -> None:
        new_entities: List[NumberEntity] = []
        for dev in coordinator.engine.get_devices():
            if dev.device_id not in known_devices:
                known_devices.add(dev.device_id)
                # Every device has an interactive priority slider
                new_entities.append(PeakShaveDevicePriorityNumber(coordinator, dev))

                if isinstance(dev, WaterHeaterDevice):
                    new_entities.append(PeakShaveDeviceMinWaterTempNumber(coordinator, dev))
                elif isinstance(dev, ClimateDevice):
                    new_entities.append(PeakShaveDeviceMinRoomTempNumber(coordinator, dev))
                    new_entities.append(PeakShaveDeviceSetbackDeltaNumber(coordinator, dev))
                elif isinstance(dev, EVChargerDevice):
                    new_entities.append(PeakShaveDeviceMinSocNumber(coordinator, dev))

        if new_entities:
            async_add_entities(new_entities)

    _add_device_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_device_entities))


# =========================================================================
# HUB NUMBER ENTITIES
# =========================================================================


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
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_target_limit_number"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_hub")},
            name=NAME,
            manufacturer="Home Assistant Peak Shaver",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.target_limit_kw

    async def async_set_native_value(self, value: float) -> None:
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
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_safety_margin_number"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_hub")},
            name=NAME,
            manufacturer="Home Assistant Peak Shaver",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.safety_margin_kw

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_target(
            self.coordinator.data.target_limit_kw, safety_margin_kw=value
        )


# =========================================================================
# PER-DEVICE NUMBER ENTITIES (Directly on each device's HA page)
# =========================================================================


class PeakShaveDevicePriorityNumber(
    CoordinatorEntity[PeakShaveCoordinator], NumberEntity
):
    """Interactive priority slider (1-10) for a controllable device."""

    _attr_has_entity_name = True
    _attr_name = "Priority"
    _attr_icon = "mdi:numeric"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PeakShaveCoordinator, device: BaseDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_priority"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model=f"{device.device_type.capitalize()} Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> int:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id:
                return d.priority
        return 5

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_device_setting(
            self.device_id, CONF_PRIORITY, int(value)
        )


class PeakShaveDeviceMinWaterTempNumber(
    CoordinatorEntity[PeakShaveCoordinator], NumberEntity
):
    """Minimum water temperature floor for domestic water boilers."""

    _attr_has_entity_name = True
    _attr_name = "Min Water Temperature Floor"
    _attr_icon = "mdi:thermometer-alert"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 35.0
    _attr_native_max_value = 70.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PeakShaveCoordinator, device: WaterHeaterDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_min_water_temp"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Water_heater Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> float:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, WaterHeaterDevice):
                return d.min_water_temp
        return 50.0

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_device_setting(
            self.device_id, CONF_MIN_WATER_TEMP, float(value)
        )


class PeakShaveDeviceMinRoomTempNumber(
    CoordinatorEntity[PeakShaveCoordinator], NumberEntity
):
    """Minimum room temperature floor for AC / heat pumps."""

    _attr_has_entity_name = True
    _attr_name = "Min Room Temperature Floor"
    _attr_icon = "mdi:thermometer-chevron-down"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 10.0
    _attr_native_max_value = 24.0
    _attr_native_step = 0.5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PeakShaveCoordinator, device: ClimateDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_min_room_temp"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Climate Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> float:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, ClimateDevice):
                return d.min_temperature
        return 18.0

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_device_setting(
            self.device_id, CONF_MIN_TEMPERATURE, float(value)
        )


class PeakShaveDeviceSetbackDeltaNumber(
    CoordinatorEntity[PeakShaveCoordinator], NumberEntity
):
    """Setback temperature delta for AC / heat pumps."""

    _attr_has_entity_name = True
    _attr_name = "Setback Delta"
    _attr_icon = "mdi:thermometer-minus"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 1.0
    _attr_native_max_value = 5.0
    _attr_native_step = 0.5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PeakShaveCoordinator, device: ClimateDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_setback_delta"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Climate Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> float:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, ClimateDevice):
                return d.setback_delta
        return 2.0

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_device_setting(
            self.device_id, CONF_SETBACK_DELTA, float(value)
        )


class PeakShaveDeviceMinSocNumber(
    CoordinatorEntity[PeakShaveCoordinator], NumberEntity
):
    """Minimum battery reserve percentage for EV chargers."""

    _attr_has_entity_name = True
    _attr_name = "Min Battery Reserve (SoC)"
    _attr_icon = "mdi:battery-heart-variant"
    _attr_native_unit_of_measurement = "%"
    _attr_native_min_value = 10
    _attr_native_max_value = 90
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PeakShaveCoordinator, device: EVChargerDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_min_soc"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Ev Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> int:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, EVChargerDevice):
                return int(d.min_soc)
        return 40

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_device_setting(
            self.device_id, "min_soc", int(value)
        )
