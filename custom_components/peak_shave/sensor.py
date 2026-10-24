"""Sensors for Peak Shaving (Nettleie) integration."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    NAME,
    STATUS_DISABLED,
    STATUS_LIMIT_EXCEEDED,
    STATUS_NORMAL,
    STATUS_SHEDDING,
    STATUS_WARNING,
)
from .coordinator import PeakShaveCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Peak Shaving sensors from a config entry."""
    coordinator: PeakShaveCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: List[SensorEntity] = [
        PeakShaveStatusSensor(coordinator),
        PeakShaveGridPowerSensor(coordinator),
        PeakShaveTargetLimitSensor(coordinator),
        PeakShaveHourEnergySensor(coordinator),
        PeakShaveRemainingEnergySensor(coordinator),
        PeakShaveProjectedHourPeakSensor(coordinator),
        PeakShaveMaxAllowablePowerSensor(coordinator),
        PeakShaveHeadroomSensor(coordinator),
        PeakShaveActiveShedDevicesSensor(coordinator),
    ]

    async_add_entities(entities)


class PeakShaveBaseSensor(CoordinatorEntity[PeakShaveCoordinator], SensorEntity):
    """Base class for peak shaving sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeakShaveCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=NAME,
            manufacturer="Home Assistant Peak Shaver",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )


class PeakShaveStatusSensor(PeakShaveBaseSensor):
    """Overall operating status of peak shaving."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        """Initialize the status sensor."""
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="status",
                name="Status",
            ),
        )

    @property
    def native_value(self) -> str:
        """Return the current operating status."""
        return self.coordinator.data.status

    @property
    def icon(self) -> str:
        """Dynamic icon depending on peak shaving status."""
        status = self.coordinator.data.status
        if status == STATUS_NORMAL:
            return "mdi:shield-check"
        elif status == STATUS_WARNING:
            return "mdi:shield-alert"
        elif status == STATUS_SHEDDING:
            return "mdi:flash-alert"
        elif status == STATUS_LIMIT_EXCEEDED:
            return "mdi:alert-octagon"
        elif status == STATUS_DISABLED:
            return "mdi:shield-off"
        return "mdi:shield"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return diagnostic metrics and device states."""
        m = self.coordinator.data
        return {
            "tier_name": m.current_tier_name,
            "target_limit_kw": m.target_limit_kw,
            "safety_margin_kw": m.safety_margin_kw,
            "effective_limit_kw": m.effective_limit_kw,
            "excess_power_kw": m.excess_power_kw,
            "headroom_kw": m.headroom_kw,
            "minutes_elapsed_this_hour": m.minutes_elapsed,
            "minutes_remaining_this_hour": m.minutes_remaining,
            "active_shed_devices": m.active_shed_devices,
            "configured_devices": [
                d.to_dict() for d in self.coordinator.engine.get_devices()
            ],
        }


class PeakShaveGridPowerSensor(PeakShaveBaseSensor):
    """Monitored total grid power."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="grid_power",
                name="Grid Power",
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.grid_power_kw


class PeakShaveTargetLimitSensor(PeakShaveBaseSensor):
    """Effective power limit after subtracting safety margin."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="effective_limit",
                name="Effective Limit",
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
            ),
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.effective_limit_kw


class PeakShaveHourEnergySensor(PeakShaveBaseSensor):
    """Accumulated energy consumed so far this clock hour."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="hour_energy_consumed",
                name="Hour Energy Consumed",
                device_class=SensorDeviceClass.ENERGY,
                native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.hour_energy_consumed_kwh


class PeakShaveRemainingEnergySensor(PeakShaveBaseSensor):
    """Remaining energy allowance before exceeding tariff limit this hour."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="hour_energy_remaining",
                name="Hour Budget Remaining",
                device_class=SensorDeviceClass.ENERGY,
                native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            ),
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.hour_energy_remaining_kwh


class PeakShaveProjectedHourPeakSensor(PeakShaveBaseSensor):
    """Projected end-of-hour average power (kW) based on current trajectory."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="projected_hour_peak",
                name="Projected Hour Average",
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.projected_hour_peak_kw


class PeakShaveMaxAllowablePowerSensor(PeakShaveBaseSensor):
    """Maximum allowable power draw for the rest of this hour."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="max_allowable_power",
                name="Max Allowable Power",
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.max_allowable_power_kw


class PeakShaveHeadroomSensor(PeakShaveBaseSensor):
    """Headroom between max allowable power and current power."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="headroom",
                name="Headroom",
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data.headroom_kw


class PeakShaveActiveShedDevicesSensor(PeakShaveBaseSensor):
    """Count and list of devices currently shed or throttled."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="active_shed_devices",
                name="Active Shed Devices",
                icon="mdi:power-plug-off",
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.active_shed_devices)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            "device_names": self.coordinator.data.active_shed_devices,
            "shed_devices_count": len(self.coordinator.data.active_shed_devices),
        }
