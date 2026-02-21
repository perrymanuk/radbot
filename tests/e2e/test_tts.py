"""TTS API e2e tests.

Auto-skipped if Google Cloud TTS is not available.
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session"), pytest.mark.requires_tts]


class TestTTSAPI:
    async def test_synthesize_text(self, client):
        """POST /api/tts/synthesize should return audio data."""
        resp = await client.post(
            "/api/tts/synthesize",
            json={"text": "Hello world, this is an end to end test."},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("audio/")
        assert len(resp.content) > 0

    async def test_synthesize_empty(self, client):
        """POST /api/tts/synthesize with empty text should return 400."""
        resp = await client.post(
            "/api/tts/synthesize",
            json={"text": ""},
        )
        assert resp.status_code == 400
