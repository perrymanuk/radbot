"""Unit tests for the ADK Replay Interceptor (tests/e2e/cassettes.py).

Tests cover:
- Hashing is deterministic and differs for different inputs
- Scrubbing removes sensitive keys
- Cassette save/load round-trip
- Missing cassette raises FileNotFoundError
- InterceptorClient.vertexai returns False in replay mode
- generate_content replay reconstructs a GenerateContentResponse
- generate_content_stream replay yields the correct chunks
- RECORD mode is not exercised (requires live API key)
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — import cassettes with CASSETTES_DIR pointed at a tmp dir
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_cassettes_dir(tmp_path, monkeypatch):
    """Redirect cassette I/O to a temporary directory."""
    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    monkeypatch.setattr(cmod, "CASSETTES_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# _to_jsonable
# ---------------------------------------------------------------------------


def test_to_jsonable_primitives():
    from tests.e2e.cassettes import _to_jsonable

    assert _to_jsonable(None) is None
    assert _to_jsonable(42) == 42
    assert _to_jsonable("hello") == "hello"
    assert _to_jsonable(True) is True


def test_to_jsonable_list():
    from tests.e2e.cassettes import _to_jsonable

    assert _to_jsonable([1, "a", None]) == [1, "a", None]


def test_to_jsonable_dict():
    from tests.e2e.cassettes import _to_jsonable

    assert _to_jsonable({"x": 1, "y": [2, 3]}) == {"x": 1, "y": [2, 3]}


def test_to_jsonable_pydantic_like():
    from tests.e2e.cassettes import _to_jsonable

    class FakePydantic:
        def model_dump(self, mode="python"):
            return {"field": "value"}

    result = _to_jsonable(FakePydantic())
    assert result == {"field": "value"}


def test_to_jsonable_plain_object_fallback():
    from tests.e2e.cassettes import _to_jsonable

    class Plain:
        def __init__(self):
            self.x = 10
            self._private = "skip"

    result = _to_jsonable(Plain())
    assert result == {"x": 10}


# ---------------------------------------------------------------------------
# _cassette_id — determinism and sensitivity
# ---------------------------------------------------------------------------


def test_cassette_id_deterministic():
    from tests.e2e.cassettes import _cassette_id

    id1 = _cassette_id("gen", "gemini-flash", ["hello"], None)
    id2 = _cassette_id("gen", "gemini-flash", ["hello"], None)
    assert id1 == id2


def test_cassette_id_prefix():
    from tests.e2e.cassettes import _cassette_id

    assert _cassette_id("gen", "m", [], None).startswith("gen_")
    assert _cassette_id("stream", "m", [], None).startswith("stream_")


def test_cassette_id_differs_by_model():
    from tests.e2e.cassettes import _cassette_id

    a = _cassette_id("gen", "gemini-flash", [], None)
    b = _cassette_id("gen", "gemini-pro", [], None)
    assert a != b


def test_cassette_id_differs_by_contents():
    from tests.e2e.cassettes import _cassette_id

    a = _cassette_id("gen", "m", ["prompt A"], None)
    b = _cassette_id("gen", "m", ["prompt B"], None)
    assert a != b


def test_cassette_id_length():
    from tests.e2e.cassettes import _cassette_id

    cid = _cassette_id("gen", "m", [], None)
    # prefix "gen_" (4) + 32 hex chars
    assert len(cid) == 36


# ---------------------------------------------------------------------------
# _scrub
# ---------------------------------------------------------------------------


def test_scrub_removes_api_key():
    from tests.e2e.cassettes import _scrub

    data = {"api_key": "sk-secret123", "model": "gemini-flash"}
    result = _scrub(data)
    assert result["api_key"] == "***SCRUBBED***"
    assert result["model"] == "gemini-flash"


def test_scrub_removes_authorization():
    from tests.e2e.cassettes import _scrub

    data = {"authorization": "Bearer tok", "other": "keep"}
    result = _scrub(data)
    assert result["authorization"] == "***SCRUBBED***"
    assert result["other"] == "keep"


def test_scrub_normalises_hyphen():
    from tests.e2e.cassettes import _scrub

    data = {"x-goog-api-key": "goog-key", "safe": "yes"}
    result = _scrub(data)
    assert result["x-goog-api-key"] == "***SCRUBBED***"


def test_scrub_nested():
    from tests.e2e.cassettes import _scrub

    data = {"headers": {"api_key": "secret", "content_type": "application/json"}}
    result = _scrub(data)
    assert result["headers"]["api_key"] == "***SCRUBBED***"
    assert result["headers"]["content_type"] == "application/json"


def test_scrub_list():
    from tests.e2e.cassettes import _scrub

    data = [{"api_key": "s"}, {"safe": "yes"}]
    result = _scrub(data)
    assert result[0]["api_key"] == "***SCRUBBED***"
    assert result[1]["safe"] == "yes"


def test_scrub_passthrough_non_sensitive():
    from tests.e2e.cassettes import _scrub

    data = {"model": "gemini", "text": "hello"}
    assert _scrub(data) == data


# ---------------------------------------------------------------------------
# Cassette I/O
# ---------------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_cassettes_dir):
    from tests.e2e.cassettes import _load, _save

    payload = {"type": "generate_content", "response": {"text": "hi"}}
    _save("test_abc123", payload)

    loaded = _load("test_abc123")
    assert loaded == payload


def test_save_creates_directory(tmp_path, monkeypatch):
    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    nested = tmp_path / "sub" / "cassettes"
    monkeypatch.setattr(cmod, "CASSETTES_DIR", nested)

    from tests.e2e.cassettes import _save  # noqa: PLC0415

    _save("x", {"data": 1})
    assert (nested / "x.json").exists()


def test_load_missing_cassette_raises(tmp_cassettes_dir):
    from tests.e2e.cassettes import _load

    with pytest.raises(FileNotFoundError, match="Cassette missing"):
        _load("nonexistent_hash")


def test_save_scrubs_api_key(tmp_cassettes_dir):
    from tests.e2e.cassettes import _save

    _save("scrub_test", {"api_key": "real-secret", "data": "ok"})
    raw = json.loads((tmp_cassettes_dir / "scrub_test.json").read_text())
    assert raw["api_key"] == "***SCRUBBED***"
    assert raw["data"] == "ok"


# ---------------------------------------------------------------------------
# InterceptorClient (replay mode)
# ---------------------------------------------------------------------------


def test_interceptor_client_vertexai_false_in_replay():
    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    with patch.object(cmod, "RECORD", False):
        client = cmod.InterceptorClient(http_options={})
        assert client.vertexai is False


def test_interceptor_client_has_aio_models():
    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    with patch.object(cmod, "RECORD", False):
        client = cmod.InterceptorClient()
        assert hasattr(client.aio, "models")
        assert hasattr(client.aio.models, "generate_content")
        assert hasattr(client.aio.models, "generate_content_stream")


# ---------------------------------------------------------------------------
# generate_content replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_content_replay(tmp_cassettes_dir, monkeypatch):
    from google.genai import types as _gt  # noqa: PLC0415

    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    # Build a minimal serialisable response
    fake_resp = _gt.GenerateContentResponse(
        candidates=[
            _gt.Candidate(
                content=_gt.Content(
                    parts=[_gt.Part(text="Hello from cassette")],
                    role="model",
                ),
                finish_reason=_gt.FinishReason.STOP,
                index=0,
            )
        ]
    )
    resp_dict = json.loads(fake_resp.model_dump_json())

    # Write cassette manually
    cassette_id = cmod._cassette_id("gen", "test-model", ["hi"], None)
    cmod._save(cassette_id, {"type": "generate_content", "response": resp_dict})

    # Replay
    with patch.object(cmod, "RECORD", False):
        client = cmod.InterceptorClient()
        result = await client.aio.models.generate_content(
            model="test-model", contents=["hi"], config=None
        )

    assert isinstance(result, _gt.GenerateContentResponse)
    assert result.candidates[0].content.parts[0].text == "Hello from cassette"


# ---------------------------------------------------------------------------
# generate_content_stream replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_content_stream_replay(tmp_cassettes_dir, monkeypatch):
    from google.genai import types as _gt  # noqa: PLC0415

    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    def _make_chunk(text: str) -> dict:
        chunk = _gt.GenerateContentResponse(
            candidates=[
                _gt.Candidate(
                    content=_gt.Content(
                        parts=[_gt.Part(text=text)],
                        role="model",
                    ),
                    index=0,
                )
            ]
        )
        return json.loads(chunk.model_dump_json())

    chunks_data = [_make_chunk("chunk1"), _make_chunk("chunk2")]
    cassette_id = cmod._cassette_id("stream", "test-model", ["hi"], None)
    cmod._save(cassette_id, {"type": "generate_content_stream", "chunks": chunks_data})

    with patch.object(cmod, "RECORD", False):
        client = cmod.InterceptorClient()
        stream = await client.aio.models.generate_content_stream(
            model="test-model", contents=["hi"], config=None
        )
        texts = []
        async for chunk in stream:
            texts.append(chunk.candidates[0].content.parts[0].text)

    assert texts == ["chunk1", "chunk2"]


# ---------------------------------------------------------------------------
# Missing cassette raises in replay mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_content_missing_cassette_raises(tmp_cassettes_dir):
    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    with patch.object(cmod, "RECORD", False):
        client = cmod.InterceptorClient()
        with pytest.raises(FileNotFoundError, match="Cassette missing"):
            await client.aio.models.generate_content(
                model="no-cassette-model", contents=["unseen prompt"], config=None
            )


@pytest.mark.asyncio
async def test_generate_content_stream_missing_cassette_raises(tmp_cassettes_dir):
    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    with patch.object(cmod, "RECORD", False):
        client = cmod.InterceptorClient()
        with pytest.raises(FileNotFoundError, match="Cassette missing"):
            await client.aio.models.generate_content_stream(
                model="no-cassette-model", contents=["unseen prompt"], config=None
            )


# ---------------------------------------------------------------------------
# patch_genai_client context manager
# ---------------------------------------------------------------------------


def test_patch_genai_client_replaces_client_class():
    import google.genai as _genai  # noqa: PLC0415

    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    original = _genai.Client
    with cmod.patch_genai_client():
        assert _genai.Client is cmod.InterceptorClient

    # Restored after exit
    assert _genai.Client is original


def test_patch_genai_client_sets_real_class():
    import google.genai as _genai  # noqa: PLC0415

    import tests.e2e.cassettes as cmod  # noqa: PLC0415

    original = _genai.Client
    with cmod.patch_genai_client():
        assert cmod._REAL_CLIENT_CLASS is original

    # Cleaned up
    assert cmod._REAL_CLIENT_CLASS is None
