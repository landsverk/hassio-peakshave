"""Sensors for Peak Shaving (Nettleie) integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
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
    """Set up Peak Shaving sensors from a config entry."""
    coordinator: PeakShaveCoordinator = hass.data[DOMAIN][entry.entry_id]

    # 1. Main Hub Sensors
    hub_entities: List[SensorEntity] = [
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
    async_add_entities(hub_entities)

    # 2. Per-Device Sensors (Registering each device as an HA Device in the registry)
    known_devices: Set[str] = set()

    @callback
    def _add_device_entities() -> None:
        new_entities: List[SensorEntity] = []
        for dev in coordinator.engine.get_devices():
            if dev.device_id not in known_devices:
                known_devices.add(dev.device_id)
                new_entities.append(PeakShaveDeviceStatusSensor(coordinator, dev))
                if isinstance(dev, WaterHeaterDevice):
                    new_entities.append(PeakShaveDeviceWaterTempSensor(coordinator, dev))
                elif isinstance(dev, EVChargerDevice):
                    new_entities.append(PeakShaveDeviceEVCurrentSensor(coordinator, dev))
                    if dev.soc_sensor:
                        new_entities.append(PeakShaveDeviceEVSocSensor(coordinator, dev))
                elif isinstance(dev, ClimateDevice):
                    new_entities.append(PeakShaveDeviceClimateTempSensor(coordinator, dev))

        if new_entities:
            async_add_entities(new_entities)

    _add_device_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_device_entities))


class PeakShaveHubSensor(CoordinatorEntity[PeakShaveCoordinator], SensorEntity):
    """Base class for peak shaving hub sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeakShaveCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the hub sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_hub")},
            name=NAME,
            manufacturer="Daniel Landsverk",
            model="Norwegian Capacity Tariff Optimizer",
            sw_version="1.0.0",
        )


class PeakShaveStatusSensor(PeakShaveHubSensor):
    """Overall operating status of peak shaving."""

    def __init__(self, coordinator: PeakShaveCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="status",
                name="Status",
            ),
        )

    @property
    def native_value(self) -> str:
        return self.coordinator.data.status

    @property
    def icon(self) -> str:
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


class PeakShaveGridPowerSensor(PeakShaveHubSensor):
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


class PeakShaveTargetLimitSensor(PeakShaveHubSensor):
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


class PeakShaveHourEnergySensor(PeakShaveHubSensor):
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


class PeakShaveRemainingEnergySensor(PeakShaveHubSensor):
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


class PeakShaveProjectedHourPeakSensor(PeakShaveHubSensor):
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


class PeakShaveMaxAllowablePowerSensor(PeakShaveHubSensor):
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


class PeakShaveHeadroomSensor(PeakShaveHubSensor):
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


class PeakShaveActiveShedDevicesSensor(PeakShaveHubSensor):
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


# =========================================================================
# PER-DEVICE SENSORS (Appear directly under each device in the HA Devices list)
# =========================================================================


class PeakShaveDeviceStatusSensor(CoordinatorEntity[PeakShaveCoordinator], SensorEntity):
    """Operating status of an individual controllable device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PeakShaveCoordinator, device: BaseDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_name = "Status"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model=f"{device.device_type.capitalize()} Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    def _get_device(self) -> Optional[BaseDevice]:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id:
                return d
        return None

    @property
    def native_value(self) -> str:
        d = self._get_device()
        if not d:
            return "Unknown"
        if not self.coordinator.engine.enabled:
            return "Disabled"
        if d.is_shed:
            return f"Shed ({d.last_action_description})"
        return "Normal"

    @property
    def icon(self) -> str:
        d = self._get_device()
        if d and d.is_shed:
            return "mdi:power-plug-off"
        return "mdi:power-plug"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        d = self._get_device()
        if not d:
            return {}
        return d.to_dict()


class PeakShaveDeviceWaterTempSensor(CoordinatorEntity[PeakShaveCoordinator], SensorEntity):
    """Water temperature sensor for domestic water boilers."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PeakShaveCoordinator, device: WaterHeaterDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_name = "Water Temperature"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_water_temp"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Water_heater Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> Optional[float]:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, WaterHeaterDevice):
                return d.current_water_temp
        return None


class PeakShaveDeviceClimateTempSensor(CoordinatorEntity[PeakShaveCoordinator], SensorEntity):
    """Room temperature sensor for AC / heat pumps."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PeakShaveCoordinator, device: ClimateDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_name = "Room Temperature"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_room_temp"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Climate Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> Optional[float]:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, ClimateDevice):
                return d.current_temp
        return None


class PeakShaveDeviceEVCurrentSensor(CoordinatorEntity[PeakShaveCoordinator], SensorEntity):
    """Charging current sensor for EV chargers."""

    _attr_has_entity_name = True
    _attr_name = "Charging Current"
    _attr_native_unit_of_measurement = "A"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PeakShaveCoordinator, device: EVChargerDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_current_amps"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Ev Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> Optional[float]:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, EVChargerDevice):
                return d.current_amps
        return None


class PeakShaveDeviceEVSocSensor(CoordinatorEntity[PeakShaveCoordinator], SensorEntity):
    """Battery state of charge sensor for EV chargers."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_name = "Battery State of Charge"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PeakShaveCoordinator, device: EVChargerDevice) -> None:
        super().__init__(coordinator)
        self.device_id = device.device_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device.device_id}_battery_soc"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{device.device_id}")},
            name=device.name,
            manufacturer="Peak Shaver",
            model="Ev Controller",
            via_device=(DOMAIN, f"{coordinator.entry.entry_id}_hub"),
        )

    @property
    def native_value(self) -> Optional[float]:
        for d in self.coordinator.engine.get_devices():
            if d.device_id == self.device_id and isinstance(d, EVChargerDevice):
                return d.battery_soc
        return None
