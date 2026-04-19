"""Tests for the /setup/claude-code.md bootstrap endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    # Late import so any previously-instantiated app is reused, and environment
    # mutations from other tests don't bleed in.
    from radbot.web.app import app

    return TestClient(app)


def test_setup_endpoint_returns_200_plaintext():
    r = _client().get("/setup/claude-code.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_setup_endpoint_templates_base_url():
    r = _client().get("/setup/claude-code.md")
    # TestClient uses http://testserver as base
    assert "http://testserver" in r.text
    assert "{base_url}" not in r.text  # placeholder must be substituted


def test_setup_endpoint_includes_required_sections():
    r = _client().get("/setup/claude-code.md")
    for header in [
        "# Configure Claude Code for radbot",
        "## 1. Get the MCP token",
        "## 2. Add the MCP server",
        "## 3. Install the `SessionStart` hook",
        "## 6. Verify",
    ]:
        assert header in r.text, f"missing section: {header}"


def test_setup_endpoint_is_unauthenticated():
    # No Authorization header — should still return 200
    r = _client().get("/setup/claude-code.md")
    assert r.status_code == 200
