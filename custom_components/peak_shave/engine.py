"""Peak shaving and Norwegian capacity tariff engine."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .const import (
    DEFAULT_HYSTERESIS_POWER,
    DEFAULT_PERSISTENCE_SECONDS,
    DEFAULT_SAFETY_MARGIN,
    DEFAULT_TARGET_LIMIT,
    STATUS_DISABLED,
    STATUS_LIMIT_EXCEEDED,
    STATUS_NORMAL,
    STATUS_SHEDDING,
    STATUS_WARNING,
)
from .devices import BaseDevice, ShedAction

_LOGGER = logging.getLogger(__name__)


class EngineMetrics:
    """Snapshot of calculations produced at each evaluation."""

    def __init__(self) -> None:
        self.timestamp: Optional[datetime] = None
        self.grid_power_kw: float = 0.0
        self.target_limit_kw: float = DEFAULT_TARGET_LIMIT
        self.safety_margin_kw: float = DEFAULT_SAFETY_MARGIN
        self.effective_limit_kw: float = DEFAULT_TARGET_LIMIT - DEFAULT_SAFETY_MARGIN
        self.hour_energy_consumed_kwh: float = 0.0
        self.hour_energy_target_kwh: float = self.effective_limit_kw
        self.hour_energy_remaining_kwh: float = self.effective_limit_kw
        self.minutes_elapsed: float = 0.0
        self.minutes_remaining: float = 60.0
        self.fraction_remaining: float = 1.0
        self.max_allowable_power_kw: float = self.effective_limit_kw
        self.projected_hour_peak_kw: float = 0.0
        self.excess_power_kw: float = 0.0
        self.headroom_kw: float = 0.0
        self.status: str = STATUS_NORMAL
        self.active_shed_devices: List[str] = []
        self.current_tier_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for HA entity states & attributes."""
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "grid_power_kw": round(self.grid_power_kw, 3),
            "target_limit_kw": round(self.target_limit_kw, 2),
            "safety_margin_kw": round(self.safety_margin_kw, 2),
            "effective_limit_kw": round(self.effective_limit_kw, 2),
            "hour_energy_consumed_kwh": round(self.hour_energy_consumed_kwh, 3),
            "hour_energy_target_kwh": round(self.hour_energy_target_kwh, 3),
            "hour_energy_remaining_kwh": round(self.hour_energy_remaining_kwh, 3),
            "minutes_elapsed": round(self.minutes_elapsed, 1),
            "minutes_remaining": round(self.minutes_remaining, 1),
            "max_allowable_power_kw": round(self.max_allowable_power_kw, 3),
            "projected_hour_peak_kw": round(self.projected_hour_peak_kw, 3),
            "excess_power_kw": round(self.excess_power_kw, 3),
            "headroom_kw": round(self.headroom_kw, 3),
            "status": self.status,
            "active_shed_devices": self.active_shed_devices,
            "current_tier_name": self.current_tier_name,
        }


class PeakShavingEngine:
    """Core mathematical engine for Norwegian capacity tariff peak shaving."""

    def __init__(
        self,
        target_limit_kw: float = DEFAULT_TARGET_LIMIT,
        safety_margin_kw: float = DEFAULT_SAFETY_MARGIN,
        persistence_seconds: int = DEFAULT_PERSISTENCE_SECONDS,
        hysteresis_power_kw: float = DEFAULT_HYSTERESIS_POWER,
    ) -> None:
        self.target_limit_kw = target_limit_kw
        self.safety_margin_kw = safety_margin_kw
        self.persistence_seconds = persistence_seconds
        self.hysteresis_power_kw = hysteresis_power_kw
        self.enabled: bool = True
        self.tier_name: str = "Lede Trinn 1: 0 – 5 kW"

        # Controllable devices list
        self.devices: List[BaseDevice] = []

        # Internal energy integrator state
        self._last_hour: Optional[int] = None
        self._last_eval_time: Optional[datetime] = None
        self._last_grid_power: float = 0.0
        self._internal_hour_energy_kwh: float = 0.0

        # Persistence tracking for shedding
        self._excess_start_time: Optional[datetime] = None

        # Metrics snapshot
        self.metrics = EngineMetrics()

    def set_target(self, target_limit_kw: float, safety_margin_kw: Optional[float] = None) -> None:
        """Update target limit and safety margin dynamically."""
        self.target_limit_kw = max(0.5, float(target_limit_kw))
        if safety_margin_kw is not None:
            self.safety_margin_kw = max(0.0, float(safety_margin_kw))

    def add_device(self, device: BaseDevice) -> None:
        """Register a controllable device."""
        self.devices = [d for d in self.devices if d.device_id != device.device_id]
        self.devices.append(device)

    def remove_device(self, device_id: str) -> None:
        """Remove a controllable device by ID."""
        self.devices = [d for d in self.devices if d.device_id != device_id]

    def clear_devices(self) -> None:
        """Clear all registered devices."""
        self.devices.clear()

    def get_devices(self) -> List[BaseDevice]:
        """Return registered devices."""
        return list(self.devices)

    def device_led(self, device: BaseDevice) -> str:
        """red = shed/throttled, yellow = at risk of being shed, green = ok."""
        if device.is_shed:
            return "red"
        if not self.enabled:
            return "green"
        if self.metrics.status in (STATUS_WARNING, STATUS_SHEDDING, STATUS_LIMIT_EXCEEDED):
            now = self.metrics.timestamp or datetime.now(timezone.utc)
            try:
                if device.can_shed(now):
                    return "yellow"
            except TypeError:
                pass
        return "green"

    def _check_hour_rollover(self, now: datetime) -> bool:
        """Detect new clock hour boundary and reset hourly accumulators."""
        if self._last_hour is None:
            self._last_hour = now.hour
            return False

        if now.hour != self._last_hour:
            _LOGGER.info(
                "Clock hour rollover detected (%d:00 -> %d:00). Resetting hourly accumulator.",
                self._last_hour,
                now.hour,
            )
            self._last_hour = now.hour
            self._internal_hour_energy_kwh = 0.0
            self._excess_start_time = None
            return True

        return False

    def _integrate_power(self, now: datetime, current_power_kw: float) -> float:
        """Numerically integrate instantaneous power to calculate kWh this hour."""
        if self._last_eval_time is not None:
            dt = (now - self._last_eval_time).total_seconds()
            if 0 < dt < 300:  # Ignore gaps > 5 mins (e.g. system restarts)
                # Trapezoidal integration: avg power (kW) * hours (dt/3600)
                avg_power = (self._last_grid_power + current_power_kw) / 2.0
                delta_kwh = avg_power * (dt / 3600.0)
                self._internal_hour_energy_kwh += delta_kwh

        self._last_eval_time = now
        self._last_grid_power = current_power_kw
        return self._internal_hour_energy_kwh

    def evaluate(
        self,
        now: datetime,
        grid_power_kw: float,
        external_hourly_energy_kwh: Optional[float] = None,
    ) -> Tuple[EngineMetrics, List[ShedAction]]:
        """
        Main evaluation cycle.
        
        Evaluates grid load against hourly tariff limit, forecasts trajectory,
        and generates load shedding or restoration actions.
        """
        actions: List[ShedAction] = []
        is_rollover = self._check_hour_rollover(now)

        # 1. Energy consumption so far this hour
        if external_hourly_energy_kwh is not None and external_hourly_energy_kwh >= 0:
            energy_consumed = float(external_hourly_energy_kwh)
            self._internal_hour_energy_kwh = energy_consumed
            self._last_eval_time = now
            self._last_grid_power = grid_power_kw
        else:
            energy_consumed = self._integrate_power(now, grid_power_kw)

        # 2. Time progression in current clock hour
        minutes_elapsed = now.minute + (now.second / 60.0) + (now.microsecond / 3600000.0)
        minutes_remaining = max(0.1, 60.0 - minutes_elapsed)
        frac_remaining = max(0.001667, minutes_remaining / 60.0)  # at least ~6 seconds

        # 3. Tariff limits & budgets
        effective_limit = max(0.5, self.target_limit_kw - self.safety_margin_kw)
        energy_target = effective_limit * 1.0  # 1 hour at effective limit = effective_limit kWh
        energy_remaining = energy_target - energy_consumed

        # 4. Projections & Allowable power
        if energy_remaining <= 0:
            # Hour limit already exhausted!
            max_allowable_power = 0.0
            excess_power = grid_power_kw
            headroom = -excess_power
            projected_hour_peak = energy_consumed / max(0.01, minutes_elapsed / 60.0)
        else:
            max_allowable_power = energy_remaining / frac_remaining
            projected_energy = energy_consumed + (grid_power_kw * frac_remaining)
            projected_hour_peak = projected_energy  # / 1 hour
            excess_power = grid_power_kw - max_allowable_power
            headroom = max_allowable_power - grid_power_kw

        # 5. Determine system state and control action needed
        need_shed = False
        excess_persisted = False

        if not self.enabled:
            status = STATUS_DISABLED
        elif energy_remaining <= 0:
            status = STATUS_LIMIT_EXCEEDED
            need_shed = True
        elif excess_power > 0:
            if self._excess_start_time is None:
                self._excess_start_time = now

            excess_duration = (now - self._excess_start_time).total_seconds()
            # Fast trigger if spike is massive (> 1.5x target) or near end of hour
            is_urgent = (grid_power_kw > effective_limit * 1.5) or (minutes_remaining < 5.0)

            if is_urgent or excess_duration >= self.persistence_seconds:
                status = STATUS_SHEDDING
                need_shed = True
                excess_persisted = True
            else:
                status = STATUS_WARNING
        else:
            self._excess_start_time = None
            any_shed = any(d.is_shed for d in self.devices)
            if any_shed:
                status = STATUS_SHEDDING
            elif projected_hour_peak >= effective_limit * 0.90:
                status = STATUS_WARNING
            else:
                status = STATUS_NORMAL

        # 6. Action Execution: Shedding vs Restoration
        if self.enabled:
            if need_shed:
                # We need to shed load!
                # Prioritize devices: Priority 1 (lowest/shed first) to Priority 10 (highest/shed last)
                sorted_devices = sorted(self.devices, key=lambda d: d.priority)
                remaining_excess = max(0.0, excess_power)
                if status == STATUS_LIMIT_EXCEEDED:
                    remaining_excess = grid_power_kw  # shed as much as possible

                for device in sorted_devices:
                    if remaining_excess <= 0 and status != STATUS_LIMIT_EXCEEDED:
                        break
                    if device.can_shed(now):
                        shed_actions = device.plan_shed(now)
                        if shed_actions:
                            actions.extend(shed_actions)
                            power_reduced = device.estimated_shed_power_reduction()
                            remaining_excess -= power_reduced
                            _LOGGER.info(
                                "Shedding device '%s' (Priority %d, saved ~%.2f kW). Remaining excess: %.2f kW",
                                device.name,
                                device.priority,
                                power_reduced,
                                max(0.0, remaining_excess),
                            )

            elif excess_power <= 0 and headroom > self.hysteresis_power_kw:
                # We have ample headroom! Check if we can restore any shed device.
                # Prioritize devices in reverse: Priority 10 (highest/restore first) down to Priority 1
                sorted_devices = sorted(self.devices, key=lambda d: d.priority, reverse=True)

                for device in sorted_devices:
                    if device.is_shed and device.can_restore(now):
                        expected_increase = device.estimated_restore_power_increase()
                        # Crucial anti-hunting check:
                        # Only restore if headroom exceeds expected draw PLUS hysteresis margin
                        if headroom >= (expected_increase + self.hysteresis_power_kw):
                            restore_actions = device.plan_restore(now)
                            if restore_actions:
                                actions.extend(restore_actions)
                                _LOGGER.info(
                                    "Restoring device '%s' (Priority %d, adds ~%.2f kW, headroom was %.2f kW)",
                                    device.name,
                                    device.priority,
                                    expected_increase,
                                    headroom,
                                )
                                # Stagger restoration: restore only ONE device per evaluation cycle
                                break

        # 7. Update metrics snapshot
        self.metrics.timestamp = now
        self.metrics.grid_power_kw = grid_power_kw
        self.metrics.target_limit_kw = self.target_limit_kw
        self.metrics.safety_margin_kw = self.safety_margin_kw
        self.metrics.effective_limit_kw = effective_limit
        self.metrics.hour_energy_consumed_kwh = energy_consumed
        self.metrics.hour_energy_target_kwh = energy_target
        self.metrics.hour_energy_remaining_kwh = energy_remaining
        self.metrics.minutes_elapsed = minutes_elapsed
        self.metrics.minutes_remaining = minutes_remaining
        self.metrics.fraction_remaining = frac_remaining
        self.metrics.max_allowable_power_kw = max_allowable_power
        self.metrics.projected_hour_peak_kw = projected_hour_peak
        self.metrics.excess_power_kw = excess_power
        self.metrics.headroom_kw = headroom
        self.metrics.status = status
        self.metrics.active_shed_devices = [d.name for d in self.devices if d.is_shed]
        self.metrics.current_tier_name = self.tier_name

        return self.metrics, actions

    def restore_all(self, now: datetime) -> List[ShedAction]:
        """Emergency override: restore all currently shed devices immediately."""
        actions: List[ShedAction] = []
        for device in sorted(self.devices, key=lambda d: d.priority, reverse=True):
            if device.is_shed:
                restore_actions = device.plan_restore(now)
                actions.extend(restore_actions)
        return actions
