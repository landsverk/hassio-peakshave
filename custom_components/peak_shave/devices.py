"""Device models and controllers for the Peak Shaving integration."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .const import (
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
    CONF_EV_SOC_SENSOR,
    CONF_EV_SWITCH_ENTITY,
    CONF_EV_VOLTAGE,
    CONF_MAX_TEMPERATURE,
    CONF_MIN_COOLDOWN,
    CONF_MIN_TEMPERATURE,
    CONF_POWER_SENSOR,
    CONF_PRIORITY,
    CONF_SETBACK_DELTA,
    CONF_SWITCH_ENTITY,
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
    DEFAULT_SWITCH_COOLDOWN,
    DEFAULT_SWITCH_ESTIMATED_POWER,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_EV,
    DEVICE_TYPE_SWITCH,
)

_LOGGER = logging.getLogger(__name__)


class ShedAction:
    """Represents an action to be executed by Home Assistant for a device."""

    def __init__(
        self,
        domain: str,
        service: str,
        target_entity: str,
        service_data: Optional[Dict[str, Any]] = None,
        description: str = "",
    ):
        self.domain = domain
        self.service = service
        self.target_entity = target_entity
        self.service_data = service_data or {}
        self.description = description

    def __repr__(self) -> str:
        return f"<ShedAction {self.domain}.{self.service} -> {self.target_entity}: {self.description}>"


class BaseDevice(ABC):
    """Abstract base class for all peak-shaving controllable devices."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.device_id: str = config.get(CONF_DEVICE_ID, "")
        self.name: str = config.get(CONF_DEVICE_NAME, self.device_id)
        self.device_type: str = config.get(CONF_DEVICE_TYPE, "")
        self.priority: int = int(config.get(CONF_PRIORITY, 5))
        self.power_sensor: Optional[str] = config.get(CONF_POWER_SENSOR)
        self.estimated_power: float = float(config.get(CONF_ESTIMATED_POWER, 1.0))
        self.cooldown_seconds: int = int(config.get(CONF_MIN_COOLDOWN, 180))

        # Operational state
        self.is_shed: bool = False
        self.shed_stage: int = 0  # 0: normal, 1+: throttled/shed stages
        self.last_state_change: Optional[datetime] = None
        self.current_power_kw: float = 0.0
        self.last_action_description: str = ""

        # Saved state before shedding to restore accurately
        self.saved_state: Dict[str, Any] = {}

    def update_power_reading(self, power_kw: Optional[float]) -> None:
        """Update current measured or fallback estimated power in kW."""
        if power_kw is not None and power_kw >= 0.0:
            self.current_power_kw = power_kw
        else:
            self.current_power_kw = self.estimated_power

    def in_cooldown(self, now: datetime) -> bool:
        """Check if device is currently within its cooldown period."""
        if self.last_state_change is None:
            return False
        elapsed = (now - self.last_state_change).total_seconds()
        return elapsed < self.cooldown_seconds

    def seconds_until_available(self, now: datetime) -> float:
        """Seconds remaining before device can change state again."""
        if self.last_state_change is None:
            return 0.0
        elapsed = (now - self.last_state_change).total_seconds()
        return max(0.0, self.cooldown_seconds - elapsed)

    @abstractmethod
    def can_shed(self, now: datetime) -> bool:
        """Return True if device can safely shed or throttle at this moment."""
        pass

    @abstractmethod
    def plan_shed(self, now: datetime) -> list[ShedAction]:
        """Generate Home Assistant actions to shed or throttle this device."""
        pass

    @abstractmethod
    def can_restore(self, now: datetime) -> bool:
        """Return True if device can safely be restored at this moment."""
        pass

    @abstractmethod
    def plan_restore(self, now: datetime) -> list[ShedAction]:
        """Generate Home Assistant actions to restore this device to previous state."""
        pass

    @abstractmethod
    def estimated_shed_power_reduction(self) -> float:
        """Estimated power reduction in kW if this device sheds one step."""
        pass

    @abstractmethod
    def estimated_restore_power_increase(self) -> float:
        """Estimated power increase in kW if this device restores one step."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize device state for diagnostic sensors and UI."""
        return {
            "id": self.device_id,
            "name": self.name,
            "type": self.device_type,
            "priority": self.priority,
            "is_shed": self.is_shed,
            "shed_stage": self.shed_stage,
            "current_power_kw": round(self.current_power_kw, 3),
            "last_action": self.last_action_description,
            "last_state_change": (
                self.last_state_change.isoformat() if self.last_state_change else None
            ),
        }


class ClimateDevice(BaseDevice):
    """Controller for heat pumps and air conditioning units (climate.*)."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.climate_entity: str = config.get(CONF_CLIMATE_ENTITY, "")
        self.min_temperature: float = float(
            config.get(CONF_MIN_TEMPERATURE, DEFAULT_CLIMATE_MIN_TEMP)
        )
        self.max_temperature: float = float(
            config.get(CONF_MAX_TEMPERATURE, DEFAULT_CLIMATE_MAX_TEMP)
        )
        self.action_mode: str = config.get(CONF_CLIMATE_ACTION, DEFAULT_CLIMATE_ACTION)
        self.setback_delta: float = float(
            config.get(CONF_SETBACK_DELTA, DEFAULT_CLIMATE_SETBACK)
        )
        self.cooldown_seconds = int(
            config.get(CONF_MIN_COOLDOWN, DEFAULT_CLIMATE_COOLDOWN)
        )

        # Dynamic state updated from HA
        self.current_temp: Optional[float] = None
        self.target_temp: Optional[float] = None
        self.hvac_mode: str = "off"
        self.hvac_action: Optional[str] = None

    def update_climate_state(
        self,
        current_temp: Optional[float],
        target_temp: Optional[float],
        hvac_mode: str,
        hvac_action: Optional[str] = None,
    ) -> None:
        """Update climate readings from Home Assistant entity."""
        self.current_temp = current_temp
        self.target_temp = target_temp
        self.hvac_mode = hvac_mode
        self.hvac_action = hvac_action

    def can_shed(self, now: datetime) -> bool:
        """AC can shed if it's currently heating/cooling, not already shed, and within temp safety limits."""
        if self.is_shed:
            return False
        if self.in_cooldown(now):
            return False
        if self.hvac_mode in ("off", "unavailable", "unknown"):
            return False

        # In heating mode: if room temperature is already at or below min_temperature, protect comfort
        if self.hvac_mode == "heat" or self.hvac_action == "heating":
            if self.current_temp is not None and self.current_temp <= self.min_temperature:
                _LOGGER.debug(
                    "Climate %s at %.1f°C <= min %.1f°C. Skipping shed to protect heating.",
                    self.name,
                    self.current_temp,
                    self.min_temperature,
                )
                return False

        # In cooling mode: if room temperature is already at or above max_temperature, protect cooling
        if self.hvac_mode == "cool" or self.hvac_action == "cooling":
            if self.current_temp is not None and self.current_temp >= self.max_temperature:
                _LOGGER.debug(
                    "Climate %s at %.1f°C >= max %.1f°C. Skipping shed to protect cooling.",
                    self.name,
                    self.current_temp,
                    self.max_temperature,
                )
                return False

        return True

    def plan_shed(self, now: datetime) -> list[ShedAction]:
        """Plan shedding actions: either setback temperature or turn off."""
        actions: list[ShedAction] = []
        self.saved_state = {
            "hvac_mode": self.hvac_mode,
            "target_temp": self.target_temp,
        }

        if self.action_mode == ACTION_SETBACK and self.target_temp is not None:
            # Setback target temperature
            new_target: float
            if self.hvac_mode == "cool":
                new_target = min(self.max_temperature, self.target_temp + self.setback_delta)
            else:
                new_target = max(self.min_temperature, self.target_temp - self.setback_delta)

            actions.append(
                ShedAction(
                    domain="climate",
                    service="set_temperature",
                    target_entity=self.climate_entity,
                    service_data={"temperature": new_target},
                    description=f"Setback temperature from {self.target_temp}°C to {new_target}°C",
                )
            )
            self.last_action_description = f"Setback to {new_target}°C"
        else:
            # Turn off climate unit
            actions.append(
                ShedAction(
                    domain="climate",
                    service="set_hvac_mode",
                    target_entity=self.climate_entity,
                    service_data={"hvac_mode": "off"},
                    description="Turned off HVAC to shed load",
                )
            )
            self.last_action_description = "Turned off"

        self.is_shed = True
        self.shed_stage = 1
        self.last_state_change = now
        return actions

    def can_restore(self, now: datetime) -> bool:
        """Can restore if currently shed and cooldown has expired."""
        if not self.is_shed:
            return False
        return not self.in_cooldown(now)

    def plan_restore(self, now: datetime) -> list[ShedAction]:
        """Restore previous target temperature and HVAC mode."""
        actions: list[ShedAction] = []
        saved_mode = self.saved_state.get("hvac_mode", "heat")
        saved_temp = self.saved_state.get("target_temp")

        if self.action_mode == ACTION_TURN_OFF:
            actions.append(
                ShedAction(
                    domain="climate",
                    service="set_hvac_mode",
                    target_entity=self.climate_entity,
                    service_data={"hvac_mode": saved_mode},
                    description=f"Restored HVAC mode to {saved_mode}",
                )
            )

        if saved_temp is not None:
            actions.append(
                ShedAction(
                    domain="climate",
                    service="set_temperature",
                    target_entity=self.climate_entity,
                    service_data={"temperature": saved_temp},
                    description=f"Restored target temperature to {saved_temp}°C",
                )
            )

        self.last_action_description = "Restored to normal"
        self.is_shed = False
        self.shed_stage = 0
        self.last_state_change = now
        return actions

    def estimated_shed_power_reduction(self) -> float:
        """Power saved by setback or turn-off."""
        if self.current_power_kw > 0.05:
            # If turning off, full power saved. If setback, save ~50% of compressor draw
            if self.action_mode == ACTION_TURN_OFF:
                return self.current_power_kw
            return max(0.3, self.current_power_kw * 0.5)
        return self.estimated_power

    def estimated_restore_power_increase(self) -> float:
        """Estimated power drawn when restored."""
        return max(0.5, self.estimated_power)


class EVChargerDevice(BaseDevice):
    """Controller for electric vehicle chargers (current modulation + pause switch)."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.current_entity: str = config.get(CONF_EV_CURRENT_ENTITY, "")
        self.switch_entity: Optional[str] = config.get(CONF_EV_SWITCH_ENTITY)
        self.soc_sensor: Optional[str] = config.get(CONF_EV_SOC_SENSOR)
        self.min_soc: float = float(config.get(CONF_EV_MIN_SOC, DEFAULT_EV_MIN_SOC))
        self.min_current: float = float(
            config.get(CONF_EV_MIN_CURRENT, DEFAULT_EV_MIN_CURRENT)
        )
        self.max_current: float = float(
            config.get(CONF_EV_MAX_CURRENT, DEFAULT_EV_MAX_CURRENT)
        )
        self.phases: int = int(config.get(CONF_EV_PHASES, DEFAULT_EV_PHASES))
        self.voltage: float = float(config.get(CONF_EV_VOLTAGE, DEFAULT_EV_VOLTAGE))
        self.cooldown_seconds = int(config.get(CONF_MIN_COOLDOWN, DEFAULT_EV_COOLDOWN))

        # Dynamic state
        self.current_amps: float = self.max_current
        self.is_charging: bool = True
        self.battery_soc: Optional[float] = None
        self.nominal_amps: float = self.max_current

    def update_ev_state(
        self,
        current_amps: Optional[float],
        is_charging: bool,
        battery_soc: Optional[float],
    ) -> None:
        """Update EV charger readings from Home Assistant."""
        if current_amps is not None and current_amps > 0:
            self.current_amps = current_amps
        self.is_charging = is_charging
        self.battery_soc = battery_soc

    def _amps_to_kw(self, amps: float) -> float:
        """Calculate approximate power in kW from amps, voltage, and phases."""
        if self.phases == 3:
            # 3-phase 400V TN (sqrt(3)*400*I) or 3-phase 230V IT (sqrt(3)*230*I)
            if self.voltage >= 380:
                return (1.732 * self.voltage * amps) / 1000.0
            return (1.732 * 230.0 * amps) / 1000.0
        return (self.voltage * amps) / 1000.0

    def can_shed(self, now: datetime) -> bool:
        """EV can shed if charging, SoC >= min_soc, not locked by cooldown, and not fully shed."""
        if not self.is_charging:
            return False
        if self.in_cooldown(now):
            return False
        if self.battery_soc is not None and self.battery_soc < self.min_soc:
            _LOGGER.debug(
                "EV %s SoC %.0f%% is below min requirement %.0f%%. Preserving charge.",
                self.name,
                self.battery_soc,
                self.min_soc,
            )
            return False

        # Can shed if we can reduce current or pause
        if self.current_amps > self.min_current:
            return True
        if self.switch_entity and self.is_charging and self.shed_stage < 2:
            return True
        return False

    def plan_shed(self, now: datetime) -> list[ShedAction]:
        """Shed in progressive stages: Stage 1 = throttle current, Stage 2 = pause."""
        actions: list[ShedAction] = []

        if not self.is_shed:
            self.saved_state = {
                "nominal_amps": self.current_amps,
                "is_charging": self.is_charging,
            }

        # Stage 1: Step down current
        if self.current_amps > self.min_current:
            # Step down by half the distance to min_current, or down to min_current
            step = max(2.0, (self.current_amps - self.min_current) / 2.0)
            new_amps = max(self.min_current, round(self.current_amps - step))

            actions.append(
                ShedAction(
                    domain="number",
                    service="set_value",
                    target_entity=self.current_entity,
                    service_data={"value": new_amps},
                    description=f"Reduced charging current from {self.current_amps}A to {new_amps}A",
                )
            )
            self.last_action_description = f"Throttled to {new_amps}A"
            self.current_amps = new_amps
            self.is_shed = True
            self.shed_stage = 1
        elif self.switch_entity and self.is_charging:
            # Stage 2: Pause charging switch
            actions.append(
                ShedAction(
                    domain="switch",
                    service="turn_off",
                    target_entity=self.switch_entity,
                    description="Paused EV charging switch",
                )
            )
            self.last_action_description = "Paused charging"
            self.is_charging = False
            self.is_shed = True
            self.shed_stage = 2

        self.last_state_change = now
        return actions

    def can_restore(self, now: datetime) -> bool:
        """Can restore if currently shed/throttled and not in cooldown."""
        if not self.is_shed:
            return False
        return not self.in_cooldown(now)

    def plan_restore(self, now: datetime) -> list[ShedAction]:
        """Restore EV charging progressively or fully."""
        actions: list[ShedAction] = []
        nominal_amps = self.saved_state.get("nominal_amps", self.max_current)

        if self.shed_stage == 2 and self.switch_entity:
            # Unpause charging first at min_current
            actions.append(
                ShedAction(
                    domain="switch",
                    service="turn_on",
                    target_entity=self.switch_entity,
                    description="Resumed EV charging switch",
                )
            )
            self.is_charging = True
            self.shed_stage = 1
            self.last_action_description = "Resumed at minimum current"
        else:
            # Restore current to nominal
            actions.append(
                ShedAction(
                    domain="number",
                    service="set_value",
                    target_entity=self.current_entity,
                    service_data={"value": nominal_amps},
                    description=f"Restored charging current to {nominal_amps}A",
                )
            )
            self.current_amps = nominal_amps
            self.is_shed = False
            self.shed_stage = 0
            self.last_action_description = f"Restored to {nominal_amps}A"

        self.last_state_change = now
        return actions

    def estimated_shed_power_reduction(self) -> float:
        """Estimated power saved by next shed step."""
        if self.current_amps > self.min_current:
            diff_amps = min(6.0, self.current_amps - self.min_current)
            return self._amps_to_kw(diff_amps)
        if self.switch_entity and self.is_charging:
            return self._amps_to_kw(self.current_amps)
        return 1.0

    def estimated_restore_power_increase(self) -> float:
        """Estimated power increase on restore step."""
        if self.shed_stage == 2:
            return self._amps_to_kw(self.min_current)
        nominal_amps = self.saved_state.get("nominal_amps", self.max_current)
        diff_amps = max(2.0, nominal_amps - self.current_amps)
        return self._amps_to_kw(diff_amps)


class SwitchDevice(BaseDevice):
    """Controller for smart plugs and relays controlling water heaters, floor heating, etc."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.switch_entity: str = config.get(CONF_SWITCH_ENTITY, "")
        self.cooldown_seconds = int(
            config.get(CONF_MIN_COOLDOWN, DEFAULT_SWITCH_COOLDOWN)
        )
        self.estimated_power = float(
            config.get(CONF_ESTIMATED_POWER, DEFAULT_SWITCH_ESTIMATED_POWER)
        )

        # Dynamic state
        self.is_on: bool = True

    def update_switch_state(self, is_on: bool) -> None:
        """Update switch on/off state from Home Assistant."""
        self.is_on = is_on

    def can_shed(self, now: datetime) -> bool:
        """Switch can shed if currently ON, not already shed, and not in cooldown."""
        if self.is_shed:
            return False
        if not self.is_on:
            return False
        return not self.in_cooldown(now)

    def plan_shed(self, now: datetime) -> list[ShedAction]:
        """Turn off switch to shed load."""
        actions: list[ShedAction] = [
            ShedAction(
                domain="switch",
                service="turn_off",
                target_entity=self.switch_entity,
                description=f"Turned off switch {self.name} to shed load",
            )
        ]
        self.saved_state = {"was_on": self.is_on}
        self.is_shed = True
        self.shed_stage = 1
        self.is_on = False
        self.last_action_description = "Turned off"
        self.last_state_change = now
        return actions

    def can_restore(self, now: datetime) -> bool:
        """Switch can restore if currently shed and not in cooldown."""
        if not self.is_shed:
            return False
        return not self.in_cooldown(now)

    def plan_restore(self, now: datetime) -> list[ShedAction]:
        """Turn on switch to restore load."""
        actions: list[ShedAction] = [
            ShedAction(
                domain="switch",
                service="turn_on",
                target_entity=self.switch_entity,
                description=f"Turned on switch {self.name} to restore load",
            )
        ]
        self.is_shed = False
        self.shed_stage = 0
        self.is_on = True
        self.last_action_description = "Turned on"
        self.last_state_change = now
        return actions

    def estimated_shed_power_reduction(self) -> float:
        """Estimated power saved by turning off."""
        if self.current_power_kw > 0.05:
            return self.current_power_kw
        return self.estimated_power

    def estimated_restore_power_increase(self) -> float:
        """Estimated power drawn when turned back on."""
        return self.estimated_power


def create_device_from_config(config: Dict[str, Any]) -> BaseDevice:
    """Factory function to instantiate the correct device controller."""
    device_type = config.get(CONF_DEVICE_TYPE)
    if device_type == DEVICE_TYPE_CLIMATE:
        return ClimateDevice(config)
    elif device_type == DEVICE_TYPE_EV:
        return EVChargerDevice(config)
    elif device_type == DEVICE_TYPE_SWITCH:
        return SwitchDevice(config)
    else:
        raise ValueError(f"Unknown device type: {device_type}")
