"""Mock Home Assistant modules for standalone test execution when HA is not installed."""
import sys
from unittest.mock import MagicMock


class MockSelectOptionDict(dict):
    def __init__(self, value, label):
        super().__init__(value=value, label=label)
        self.value = value
        self.label = label


class MockOptionsFlow:
    def __init__(self, *args, **kwargs):
        pass

    def async_show_form(self, step_id, data_schema=None, errors=None, description_placeholders=None):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": description_placeholders,
        }

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_menu(self, step_id, menu_options, description_placeholders=None):
        return {"type": "menu", "step_id": step_id, "menu_options": menu_options}

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}


class MockConfigFlow(MockOptionsFlow):
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)


# Prepare mock modules
config_entries_mock = MagicMock()
config_entries_mock.OptionsFlow = MockOptionsFlow
config_entries_mock.ConfigFlow = MockConfigFlow

class MockSelectSelectorConfig(dict):
    def __init__(self, options=None, mode=None, **kwargs):
        super().__init__(options=options or [], mode=mode, **kwargs)
        self.options = options or []
        self.config = self


class MockSelectSelector:
    def __init__(self, config=None):
        self.config = config or {}


selector_mock = MagicMock()
selector_mock.SelectOptionDict = MockSelectOptionDict
selector_mock.SelectSelectorConfig = MockSelectSelectorConfig
selector_mock.SelectSelector = MockSelectSelector

helpers_mock = MagicMock()
helpers_mock.selector = selector_mock

ha_mock = MagicMock()
ha_mock.config_entries = config_entries_mock
ha_mock.helpers = helpers_mock

sys.modules["homeassistant"] = ha_mock
sys.modules["homeassistant.config_entries"] = config_entries_mock
sys.modules["homeassistant.helpers"] = helpers_mock
sys.modules["homeassistant.helpers.selector"] = selector_mock

class MockSchema:
    def __init__(self, schema):
        self.schema = schema


vol_mock = MagicMock()
vol_mock.Schema = MockSchema
sys.modules["voluptuous"] = vol_mock

for mod in [
    "homeassistant.components",
    "homeassistant.components.climate",
    "homeassistant.components.number",
    "homeassistant.components.select",
    "homeassistant.components.sensor",
    "homeassistant.components.switch",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.data_entry_flow",
    "voluptuous",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
