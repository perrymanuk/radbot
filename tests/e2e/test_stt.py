"""STT API e2e tests.

Auto-skipped if Google Cloud STT is not available.
"""

import io
import struct
import wave

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session"), pytest.mark.requires_stt]


def _create_test_wav() -> bytes:
    """Create a minimal WAV file with silence (valid audio for STT)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        # 0.5 seconds of silence
        wf.writeframes(b"\x00\x00" * 8000)
    return buf.getvalue()


class TestSTTAPI:
    async def test_transcribe_audio(self, client):
        """POST /api/stt/transcribe should return transcription."""
        wav_data = _create_test_wav()

        resp = await client.post(
            "/api/stt/transcribe",
            files={"audio": ("test.wav", wav_data, "audio/wav")},
        )
        # Accept 200 (transcription) or 400 (no speech detected in silence)
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            data = resp.json()
            assert "text" in data

    async def test_transcribe_no_file(self, client):
        """POST /api/stt/transcribe without file should return 422."""
        resp = await client.post("/api/stt/transcribe")
        assert resp.status_code == 422
