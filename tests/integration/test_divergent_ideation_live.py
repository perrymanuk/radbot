"""Live-API integration test for divergent ideation.

Skipped by default. Run explicitly with::

    RADBOT_RUN_LIVE_LLM_TESTS=1 uv run pytest tests/integration/test_divergent_ideation_live.py
"""

from __future__ import annotations

import os

import pytest

from radbot.tools.divergent_ideation import execute_divergent_ideation

pytestmark = pytest.mark.skipif(
    os.environ.get("RADBOT_RUN_LIVE_LLM_TESTS") != "1",
    reason="Live LLM test — set RADBOT_RUN_LIVE_LLM_TESTS=1 to run.",
)


def test_divergent_ideation_live_returns_structured_output():
    result = execute_divergent_ideation("how to scale a websocket server")

    assert isinstance(result, dict)
    assert result["status"] in ("success", "error")
    assert "standard" in result
    assert "contrarian" in result
    assert "wildcard" in result
    if result["status"] == "success":
        # At least one stream should be a non-empty string.
        assert any(isinstance(result[k], str) and result[k] for k in ("standard", "contrarian", "wildcard"))
