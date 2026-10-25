"""Storage manager for Peak Shaving persistent device backup."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "peak_shave_persistent_backup"
STORAGE_VERSION = 1


class PeakShaveStorage:
    """Manages persistent storage independent of ConfigEntry lifecycle.

    Ensures that configured devices and settings survive even if the user
    deletes and re-installs the integration entry in Home Assistant.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the storage manager."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_load(self) -> Dict[str, Any]:
        """Load stored devices and configuration."""
        try:
            data = await self._store.async_load()
            if not data or not isinstance(data, dict):
                return {"devices": []}
            return data
        except Exception as ex:
            _LOGGER.warning("Could not load persistent backup from storage: %s", ex)
            return {"devices": []}

    async def async_save(
        self,
        devices: List[Dict[str, Any]],
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist devices and settings to .storage/peak_shave_persistent_backup."""
        try:
            payload: Dict[str, Any] = {
                "devices": devices,
                "version": STORAGE_VERSION,
            }
            if extra_meta:
                payload.update(extra_meta)
            await self._store.async_save(payload)
            _LOGGER.debug(
                "Persisted %d devices to independent storage (%s)",
                len(devices),
                STORAGE_KEY,
            )
        except Exception as ex:
            _LOGGER.error("Failed to save devices to persistent storage: %s", ex)
