"""Mock Home Assistant modules for standalone test execution when HA is not installed."""
import sys
from unittest.mock import MagicMock


class MockModule(MagicMock):
    @classmethod
    def __getattr__(cls, name):
        return MagicMock()


for mod in [
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.climate",
    "homeassistant.components.number",
    "homeassistant.components.select",
    "homeassistant.components.sensor",
    "homeassistant.components.switch",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.data_entry_flow",
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.event",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.update_coordinator",
    "voluptuous",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MockModule()
