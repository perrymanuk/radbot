"""Unit tests for Gmail quota-project resolution (gmail_auth._get_quota_project).

Tokens minted against Google's built-in gcloud OAuth client are rejected by the
Gmail API unless a quota project is supplied. Production has no env vars or
ADC file, so the DB config entry ``agent.google_cloud_project`` (via
``config_manager.get_google_cloud_project()``) must be honoured, with env vars
still taking precedence.
"""

from unittest.mock import MagicMock, patch

import pytest

from radbot.tools.gmail import gmail_auth

_ENV_VARS = (
    "GOOGLE_CLOUD_QUOTA_PROJECT",
    "GOOGLE_CLOUD_PROJECT",
    "GCLOUD_PROJECT",
    "DEVSHELL_PROJECT_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    # Arrange: no env vars, no ADC file, no gcloud config on disk.
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    monkeypatch.setenv("HOME", str(tmp_path))
    yield


def _config_manager_with(project) -> MagicMock:
    cm = MagicMock()
    cm.get_google_cloud_project.return_value = project
    return cm


def test_get_quota_project_returns_config_value_when_no_env(clean_env):
    # Arrange
    cm = _config_manager_with("homelab-proj")
    with patch("radbot.config.config_manager", cm):
        # Act
        result = gmail_auth._get_quota_project()
    # Assert
    assert result == "homelab-proj"


def test_get_quota_project_prefers_env_over_config(clean_env, monkeypatch):
    # Arrange
    monkeypatch.setenv("GOOGLE_CLOUD_QUOTA_PROJECT", "env-proj")
    cm = _config_manager_with("config-proj")
    with patch("radbot.config.config_manager", cm):
        # Act
        result = gmail_auth._get_quota_project()
    # Assert
    assert result == "env-proj"


def test_get_quota_project_returns_none_when_config_blank(clean_env):
    # Arrange
    cm = _config_manager_with("   ")
    with patch("radbot.config.config_manager", cm):
        # Act
        result = gmail_auth._get_quota_project()
    # Assert
    assert result is None


def test_get_quota_project_survives_config_manager_failure(clean_env):
    # Arrange
    cm = MagicMock()
    cm.get_google_cloud_project.side_effect = RuntimeError("db down")
    with patch("radbot.config.config_manager", cm):
        # Act
        result = gmail_auth._get_quota_project()
    # Assert
    assert result is None


def test_apply_quota_project_calls_with_quota_project(clean_env):
    # Arrange
    cm = _config_manager_with("homelab-proj")
    creds = MagicMock()
    creds.with_quota_project.return_value = "scoped-creds"
    with patch("radbot.config.config_manager", cm):
        # Act
        result = gmail_auth._apply_quota_project(creds)
    # Assert
    creds.with_quota_project.assert_called_once_with("homelab-proj")
    assert result == "scoped-creds"
