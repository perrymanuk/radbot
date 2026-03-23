"""Tests for radbot.agent.factory_utils.load_tools()."""

import logging
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from radbot.agent.factory_utils import load_tools


@pytest.fixture
def fake_tools():
    """Create a list of mock FunctionTool objects."""
    t1 = MagicMock()
    t1.name = "tool_a"
    t2 = MagicMock()
    t2.name = "tool_b"
    return [t1, t2]


@pytest.fixture
def fake_module(fake_tools):
    """Create a fake module with a TOOLS attribute."""
    mod = ModuleType("radbot.tools.fake")
    mod.FAKE_TOOLS = fake_tools
    return mod


class TestLoadToolsSuccess:
    """Tests for the successful import path."""

    def test_returns_tools_from_valid_module(self, fake_module, fake_tools):
        with patch("radbot.agent.factory_utils.importlib.import_module", return_value=fake_module):
            result = load_tools("radbot.tools.fake", "FAKE_TOOLS", "test_agent", "Fake")

        assert result == fake_tools
        assert len(result) == 2

    def test_returns_new_list_not_original(self, fake_module, fake_tools):
        with patch("radbot.agent.factory_utils.importlib.import_module", return_value=fake_module):
            result = load_tools("radbot.tools.fake", "FAKE_TOOLS", "test_agent", "Fake")

        assert result is not fake_tools
        assert result == fake_tools

    def test_logs_info_on_success(self, fake_module, caplog):
        with patch("radbot.agent.factory_utils.importlib.import_module", return_value=fake_module):
            with caplog.at_level(logging.INFO, logger="radbot.agent.factory_utils"):
                load_tools("radbot.tools.fake", "FAKE_TOOLS", "test_agent", "Fake")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "INFO"
        assert "2" in record.message
        assert "Fake" in record.message
        assert "test_agent" in record.message


class TestLoadToolsFailure:
    """Tests for the failure / fallback paths."""

    def test_returns_empty_list_when_module_not_found(self):
        with patch(
            "radbot.agent.factory_utils.importlib.import_module",
            side_effect=ModuleNotFoundError("No module named 'radbot.tools.bogus'"),
        ):
            result = load_tools("radbot.tools.bogus", "TOOLS", "test_agent", "Bogus")

        assert result == []

    def test_returns_empty_list_when_attribute_missing(self):
        mod = ModuleType("radbot.tools.noattr")
        with patch("radbot.agent.factory_utils.importlib.import_module", return_value=mod):
            result = load_tools("radbot.tools.noattr", "MISSING_ATTR", "test_agent", "NoAttr")

        assert result == []

    def test_returns_empty_list_on_import_error(self):
        with patch(
            "radbot.agent.factory_utils.importlib.import_module",
            side_effect=ImportError("some dependency missing"),
        ):
            result = load_tools("radbot.tools.broken", "TOOLS", "test_agent", "Broken")

        assert result == []

    def test_returns_empty_list_on_generic_exception(self):
        with patch(
            "radbot.agent.factory_utils.importlib.import_module",
            side_effect=RuntimeError("unexpected"),
        ):
            result = load_tools("radbot.tools.boom", "TOOLS", "test_agent", "Boom")

        assert result == []

    def test_logs_warning_on_module_not_found(self, caplog):
        with patch(
            "radbot.agent.factory_utils.importlib.import_module",
            side_effect=ModuleNotFoundError("No module named 'radbot.tools.bogus'"),
        ):
            with caplog.at_level(logging.WARNING, logger="radbot.agent.factory_utils"):
                load_tools("radbot.tools.bogus", "TOOLS", "test_agent", "Bogus")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert "Bogus" in record.message
        assert "test_agent" in record.message

    def test_logs_warning_on_attribute_error(self, caplog):
        mod = ModuleType("radbot.tools.noattr")
        with patch("radbot.agent.factory_utils.importlib.import_module", return_value=mod):
            with caplog.at_level(logging.WARNING, logger="radbot.agent.factory_utils"):
                load_tools("radbot.tools.noattr", "MISSING_ATTR", "test_agent", "NoAttr")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert "NoAttr" in record.message
        assert "test_agent" in record.message
