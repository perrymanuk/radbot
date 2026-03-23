"""Tests for radbot.tools.shared utilities."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from radbot.tools.shared.client_utils import client_or_error
from radbot.tools.shared.errors import truncate_error
from radbot.tools.shared.retry import retry_on_error
from radbot.tools.shared.serialization import serialize_row, serialize_rows
from radbot.tools.shared.tool_decorator import tool_error_handler
from radbot.tools.shared.validation import validate_uuid

# ── serialization ────────────────────────────────────────────────────────────


class TestSerializeRow:
    def test_uuid_converted_to_str(self):
        uid = uuid.uuid4()
        assert serialize_row({"id": uid}) == {"id": str(uid)}

    def test_datetime_converted_to_isoformat(self):
        dt = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        assert serialize_row({"ts": dt}) == {"ts": dt.isoformat()}

    def test_plain_values_unchanged(self):
        row = {"name": "hello", "count": 42, "flag": True}
        assert serialize_row(row) == row

    def test_mask_fields_truthy(self):
        row = {"secret": "mysecret", "name": "hook"}
        result = serialize_row(row, mask_fields={"secret": "***"})
        assert result == {"secret": "***", "name": "hook"}

    def test_mask_fields_falsy(self):
        row = {"secret": None, "name": "hook"}
        result = serialize_row(row, mask_fields={"secret": "***"})
        assert result == {"secret": None, "name": "hook"}

    def test_mixed_types(self):
        uid = uuid.uuid4()
        dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        row = {"id": uid, "ts": dt, "name": "test", "count": 5}
        result = serialize_row(row)
        assert result == {
            "id": str(uid),
            "ts": dt.isoformat(),
            "name": "test",
            "count": 5,
        }


class TestSerializeRows:
    def test_empty_list(self):
        assert serialize_rows([]) == []

    def test_multiple_rows(self):
        uid1, uid2 = uuid.uuid4(), uuid.uuid4()
        rows = [{"id": uid1}, {"id": uid2}]
        result = serialize_rows(rows)
        assert result == [{"id": str(uid1)}, {"id": str(uid2)}]

    def test_mask_fields_propagated(self):
        rows = [{"secret": "a"}, {"secret": None}]
        result = serialize_rows(rows, mask_fields={"secret": "***"})
        assert result == [{"secret": "***"}, {"secret": None}]


# ── validation ───────────────────────────────────────────────────────────────


class TestValidateUuid:
    def test_valid_uuid(self):
        uid = str(uuid.uuid4())
        parsed, err = validate_uuid(uid)
        assert err is None
        assert isinstance(parsed, uuid.UUID)
        assert str(parsed) == uid

    def test_invalid_uuid(self):
        parsed, err = validate_uuid("not-a-uuid", "task ID")
        assert parsed is None
        assert err["status"] == "error"
        assert "task ID" in err["message"]

    def test_empty_string(self):
        parsed, err = validate_uuid("")
        assert parsed is None
        assert err is not None


# ── errors ───────────────────────────────────────────────────────────────────


class TestTruncateError:
    def test_short_message_unchanged(self):
        assert truncate_error("short") == "short"

    def test_exact_limit(self):
        msg = "x" * 200
        assert truncate_error(msg) == msg

    def test_over_limit_truncated(self):
        msg = "x" * 250
        result = truncate_error(msg)
        assert len(result) == 200
        assert result.endswith("...")

    def test_custom_limit(self):
        msg = "x" * 50
        result = truncate_error(msg, max_length=20)
        assert len(result) == 20
        assert result.endswith("...")


# ---------------------------------------------------------------------------
# config_helper.py
# ---------------------------------------------------------------------------


class TestGetIntegrationConfig:
    """Tests for get_integration_config()."""

    FIELDS = {"url": "MY_SVC_URL", "api_key": "MY_SVC_API_KEY"}
    CRED_KEYS = {"api_key": "my_svc_api_key"}

    def _call(self, **kwargs):
        from radbot.tools.shared.config_helper import get_integration_config

        return get_integration_config("my_svc", self.FIELDS, **kwargs)

    @patch("radbot.tools.shared.config_helper.os.environ", {})
    def test_loads_from_config_loader(self):
        """Config values are loaded from config_loader when available."""
        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {
            "my_svc": {"url": "http://from-config", "api_key": "key-from-config"}
        }
        with patch.dict(
            "sys.modules",
            {"radbot.config.config_loader": MagicMock(config_loader=mock_loader)},
        ):
            result = self._call()

        assert result["url"] == "http://from-config"
        assert result["api_key"] == "key-from-config"

    @patch(
        "radbot.tools.shared.config_helper.os.environ",
        {"MY_SVC_URL": "http://from-env"},
    )
    def test_falls_back_to_env_vars(self):
        """Falls back to environment variables when config_loader has no value."""
        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}
        with patch.dict(
            "sys.modules",
            {"radbot.config.config_loader": MagicMock(config_loader=mock_loader)},
        ):
            result = self._call()

        assert result["url"] == "http://from-env"

    @patch("radbot.tools.shared.config_helper.os.environ", {})
    def test_falls_back_to_credential_store(self):
        """Falls back to credential store when env vars are not set."""
        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}

        mock_store = MagicMock()
        mock_store.get.return_value = "secret-from-creds"
        mock_get_store = MagicMock(return_value=mock_store)

        with patch.dict(
            "sys.modules",
            {
                "radbot.config.config_loader": MagicMock(config_loader=mock_loader),
                "radbot.credentials.store": MagicMock(
                    get_credential_store=mock_get_store
                ),
            },
        ):
            result = self._call(credential_keys=self.CRED_KEYS)

        assert result["api_key"] == "secret-from-creds"
        mock_store.get.assert_called_once_with("my_svc_api_key")

    @patch("radbot.tools.shared.config_helper.os.environ", {})
    def test_returns_none_for_unconfigured_fields(self):
        """Returns None for fields with no config, env, or credential value."""
        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}

        with patch.dict(
            "sys.modules",
            {"radbot.config.config_loader": MagicMock(config_loader=mock_loader)},
        ):
            result = self._call()

        assert result["url"] is None
        assert result["api_key"] is None

    @patch("radbot.tools.shared.config_helper.os.environ", {})
    def test_handles_config_loader_import_failure(self):
        """Gracefully handles import failure of config_loader."""
        with patch.dict(
            "sys.modules",
            {"radbot.config.config_loader": None},
        ):
            result = self._call()

        assert result["url"] is None
        assert result["api_key"] is None

    @patch("radbot.tools.shared.config_helper.os.environ", {})
    def test_enabled_defaults_to_true(self):
        """The enabled flag defaults to True when not specified in config."""
        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}

        with patch.dict(
            "sys.modules",
            {"radbot.config.config_loader": MagicMock(config_loader=mock_loader)},
        ):
            result = self._call()

        assert result["enabled"] is True

    @patch("radbot.tools.shared.config_helper.os.environ", {})
    def test_enabled_from_config(self):
        """The enabled flag is read from config when present."""
        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {
            "my_svc": {"enabled": False}
        }
        with patch.dict(
            "sys.modules",
            {"radbot.config.config_loader": MagicMock(config_loader=mock_loader)},
        ):
            result = self._call()

        assert result["enabled"] is False


# ---------------------------------------------------------------------------
# client_utils.py
# ---------------------------------------------------------------------------


class TestClientOrError:
    """Tests for client_or_error()."""

    def test_returns_client_when_available(self):
        """Returns (client, None) when the client callable returns an object."""
        fake_client = MagicMock()
        client, err = client_or_error(lambda: fake_client, "FooService")

        assert client is fake_client
        assert err is None

    def test_returns_error_when_client_is_none(self):
        """Returns (None, error_dict) when the client callable returns None."""
        client, err = client_or_error(lambda: None, "FooService")

        assert client is None
        assert err is not None
        assert err["status"] == "error"
        assert "FooService" in err["message"]
        assert "not configured" in err["message"]

    def test_error_dict_has_correct_fields(self):
        """Error dict contains exactly status and message."""
        _, err = client_or_error(lambda: None, "My Service")

        assert set(err.keys()) == {"status", "message"}
        assert err["status"] == "error"


# ---------------------------------------------------------------------------
# tool_decorator.py
# ---------------------------------------------------------------------------


class TestToolErrorHandler:
    """Tests for tool_error_handler()."""

    def test_returns_result_on_success(self):
        """Decorated function returns its result when no exception occurs."""

        @tool_error_handler("do something")
        def good_func():
            return {"status": "success", "data": 42}

        assert good_func() == {"status": "success", "data": 42}

    def test_returns_error_dict_on_exception(self):
        """Decorated function returns error dict when exception is raised."""

        @tool_error_handler("frobnicate")
        def bad_func():
            raise ValueError("kaboom")

        result = bad_func()
        assert result["status"] == "error"
        assert "Failed to frobnicate" in result["message"]
        assert "kaboom" in result["message"]

    def test_error_message_truncated_to_300_chars(self):
        """Error message is truncated to 300 characters."""

        @tool_error_handler("process")
        def verbose_error():
            raise RuntimeError("x" * 500)

        result = verbose_error()
        assert len(result["message"]) <= 300

    def test_preserves_function_name_and_docstring(self):
        """functools.wraps preserves __name__ and __doc__."""

        @tool_error_handler("test op")
        def my_function():
            """My docstring."""
            return {}

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


# ---------------------------------------------------------------------------
# retry.py
# ---------------------------------------------------------------------------


class TestRetryOnError:
    """Tests for retry_on_error()."""

    @patch("radbot.tools.shared.retry.time.sleep")
    def test_no_retry_on_success(self, mock_sleep):
        """Function is called once and returns without retrying."""
        call_count = 0

        @retry_on_error(max_retries=3)
        def ok():
            nonlocal call_count
            call_count += 1
            return "done"

        assert ok() == "done"
        assert call_count == 1
        mock_sleep.assert_not_called()

    @patch("radbot.tools.shared.retry.time.sleep")
    def test_retries_on_retryable_exception(self, mock_sleep):
        """Retries on retryable exceptions and succeeds after transient failures."""
        attempts = 0

        @retry_on_error(max_retries=3, retryable_exceptions=(ConnectionError,))
        def flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("transient")
            return "recovered"

        assert flaky() == "recovered"
        assert attempts == 3
        assert mock_sleep.call_count == 2

    @patch("radbot.tools.shared.retry.time.sleep")
    def test_raises_after_max_retries_exhausted(self, mock_sleep):
        """Raises the last exception after all retries are exhausted."""

        @retry_on_error(max_retries=2, retryable_exceptions=(TimeoutError,))
        def always_fails():
            raise TimeoutError("still broken")

        with pytest.raises(TimeoutError, match="still broken"):
            always_fails()

        # initial call + 2 retries = 3 total; sleep before retry 1 and 2
        assert mock_sleep.call_count == 2

    @patch("radbot.tools.shared.retry.time.sleep")
    def test_no_retry_on_non_retryable_exception(self, mock_sleep):
        """Non-retryable exceptions propagate immediately without retrying."""

        @retry_on_error(max_retries=3, retryable_exceptions=(ConnectionError,))
        def bad():
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            bad()

        mock_sleep.assert_not_called()

    @patch("radbot.tools.shared.retry.time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep):
        """Sleep durations follow exponential backoff: base * 2^attempt."""

        @retry_on_error(
            max_retries=3,
            backoff_base=2.0,
            retryable_exceptions=(OSError,),
        )
        def always_fails():
            raise OSError("fail")

        with pytest.raises(OSError):
            always_fails()

        # delays: 2*2^0=2, 2*2^1=4, 2*2^2=8
        expected_delays = [2.0, 4.0, 8.0]
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays
