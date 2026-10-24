"""Mock Home Assistant modules for standalone test execution when HA is not installed."""
import sys
from unittest.mock import MagicMock

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
    "voluptuous",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


class MockSelectOptionDict(dict):
    def __init__(self, value, label):
        super().__init__(value=value, label=label)
        self.value = value
        self.label = label


selector_mock = MagicMock()
selector_mock.SelectOptionDict = MockSelectOptionDict

helpers_mock = MagicMock()
helpers_mock.selector = selector_mock

sys.modules["homeassistant.helpers"] = helpers_mock
sys.modules["homeassistant.helpers.selector"] = selector_mock
