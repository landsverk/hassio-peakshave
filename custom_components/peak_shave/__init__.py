"""The Peak Shaving (Nettleie) integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import PeakShaveCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

SERVICE_RESTORE_ALL: Final = "restore_all"
SERVICE_RECALCULATE: Final = "recalculate"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Peak Shaving from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = PeakShaveCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options flow updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register services
    async def handle_restore_all(call: ServiceCall) -> None:
        """Service to restore all shed devices immediately."""
        _LOGGER.info("Service restore_all called")
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, PeakShaveCoordinator):
                await coord.async_restore_all()

    async def handle_recalculate(call: ServiceCall) -> None:
        """Service to trigger immediate recalculation."""
        _LOGGER.info("Service recalculate called")
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, PeakShaveCoordinator):
                await coord.async_refresh()

    hass.services.async_register(DOMAIN, SERVICE_RESTORE_ALL, handle_restore_all)
    hass.services.async_register(DOMAIN, SERVICE_RECALCULATE, handle_recalculate)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: PeakShaveCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Cancel any active listeners
        for unsub in coordinator._unsub_trackers:
            unsub()

    # If no more entries, unregister services
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_RESTORE_ALL)
        hass.services.async_remove(DOMAIN, SERVICE_RECALCULATE)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options flow update."""
    coordinator: PeakShaveCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        coordinator.update_config()
        await coordinator.async_refresh()
