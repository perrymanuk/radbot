"""ADK Replay Interceptor for in-process e2e tests.

Monkeypatches ``google.genai.Client`` so Gemini API calls can be
recorded once and replayed deterministically without a live API key.

Recording (requires live GOOGLE_API_KEY / GEMINI_API_KEY):
    RADBOT_RECORD_CASSETTES=1 pytest tests/e2e/

Replay (default when RADBOT_TEST_URL is not set):
    pytest tests/e2e/

Cassettes are stored as JSON files under ``tests/e2e/cassettes/``.
Each file is keyed by a SHA-256 hash of (model, serialised contents,
serialised config), prefixed by call type:

    gen_<32-hex>.json     — generate_content (unary)
    stream_<32-hex>.json  — generate_content_stream (SSE/streaming)

Scrubbing: api_key, authorization, and related fields are replaced
with ``***SCRUBBED***`` before any cassette is written to disk.

Fixture ``genai_interceptor`` (session-scoped) is NOT autouse; activate
it by depending on it from an ``asgi_app`` fixture in conftest.py so the
patch is in place before the FastAPI app is imported and started.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
from contextlib import contextmanager
from typing import Any, AsyncIterator
from unittest.mock import patch

import pytest

logger = logging.getLogger(__name__)

CASSETTES_DIR = pathlib.Path(__file__).parent / "cassettes"
RECORD = os.environ.get("RADBOT_RECORD_CASSETTES", "").strip() == "1"

# Keys whose values are scrubbed before saving cassettes (case-insensitive,
# hyphens normalised to underscores).
_SCRUB_KEYS = frozenset(
    {"api_key", "key", "authorization", "x_goog_api_key", "token", "secret"}
)

# Holds the real google.genai.Client class captured before patching so that
# RECORD mode can still reach the live API.
_REAL_CLIENT_CLASS: type | None = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert ADK/genai pydantic objects to JSON-serialisable form."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {
            k: _to_jsonable(v) for k, v in vars(obj).items() if not k.startswith("_")
        }
    return str(obj)


def _cassette_id(prefix: str, model: str, contents: Any, config: Any) -> str:
    payload = json.dumps(
        {
            "model": model,
            "contents": _to_jsonable(contents),
            "config": _to_jsonable(config),
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:32]
    return f"{prefix}_{digest}"


# ---------------------------------------------------------------------------
# Scrubbing
# ---------------------------------------------------------------------------


def _normalise_key(k: str) -> str:
    return k.lower().replace("-", "_")


def _scrub(data: Any) -> Any:
    """Remove sensitive values from a data structure before writing to disk."""
    if isinstance(data, dict):
        return {
            k: ("***SCRUBBED***" if _normalise_key(k) in _SCRUB_KEYS else _scrub(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_scrub(i) for i in data]
    return data


# ---------------------------------------------------------------------------
# Cassette I/O
# ---------------------------------------------------------------------------


def _save(cassette_id: str, data: dict) -> None:
    CASSETTES_DIR.mkdir(parents=True, exist_ok=True)
    path = CASSETTES_DIR / f"{cassette_id}.json"
    with open(path, "w") as f:
        json.dump(_scrub(data), f, indent=2, default=str)
    logger.info("cassette saved: %s", path.name)


def _load(cassette_id: str) -> dict:
    path = CASSETTES_DIR / f"{cassette_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Cassette missing: {path.name}\n"
            "Re-run with RADBOT_RECORD_CASSETTES=1 to record it.\n"
            f"(expected at {path})"
        )
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Mock aio.models surface
# ---------------------------------------------------------------------------


class _MockAioModels:
    """Drop-in for ``client.aio.models`` that reads/writes cassettes."""

    def __init__(self, real_models: Any = None) -> None:
        self._real = real_models  # None in replay mode

    async def generate_content(
        self,
        *,
        model: str,
        contents: Any,
        config: Any = None,
    ) -> Any:
        from google.genai import types as _gt

        cassette_id = _cassette_id("gen", model, contents, config)

        if RECORD:
            if self._real is None:
                raise RuntimeError(
                    "generate_content: real aio.models required in RECORD mode"
                )
            real_resp = await self._real.generate_content(
                model=model, contents=contents, config=config
            )
            _save(
                cassette_id,
                {
                    "type": "generate_content",
                    "response": json.loads(real_resp.model_dump_json()),
                },
            )
            return real_resp

        data = _load(cassette_id)
        return _gt.GenerateContentResponse.model_validate(data["response"])

    async def generate_content_stream(
        self,
        *,
        model: str,
        contents: Any,
        config: Any = None,
    ) -> AsyncIterator[Any]:
        """Return an async iterator of response chunks (record or replay)."""
        cassette_id = _cassette_id("stream", model, contents, config)

        if RECORD:
            if self._real is None:
                raise RuntimeError(
                    "generate_content_stream: real aio.models required in RECORD mode"
                )
            real_iter = await self._real.generate_content_stream(
                model=model, contents=contents, config=config
            )
            return self._record_stream(cassette_id, real_iter)

        data = _load(cassette_id)
        return self._replay_stream(data["chunks"])

    async def _record_stream(self, cassette_id: str, real_iter: Any) -> Any:
        """Async generator that proxies real chunks and saves cassette on exit."""
        chunks_data: list[dict] = []
        async for chunk in real_iter:
            chunks_data.append(json.loads(chunk.model_dump_json()))
            yield chunk
        _save(cassette_id, {"type": "generate_content_stream", "chunks": chunks_data})

    async def _replay_stream(self, chunks_data: list[dict]) -> Any:
        """Async generator that replays chunks from a cassette."""
        from google.genai import types as _gt

        for chunk_data in chunks_data:
            yield _gt.GenerateContentResponse.model_validate(chunk_data)


class _MockAio:
    """Drop-in for ``client.aio``."""

    def __init__(self, real_aio: Any = None) -> None:
        self.models = _MockAioModels(real_aio.models if real_aio is not None else None)


class InterceptorClient:
    """Replacement for ``google.genai.Client`` used by the ADK ``Gemini`` model.

    In RECORD mode a real ``_REAL_CLIENT_CLASS`` is instantiated and
    proxied so live responses are captured to disk.  In REPLAY mode only
    the cassette is used and no network calls are made.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._real_client: Any = None
        if RECORD:
            if _REAL_CLIENT_CLASS is None:
                raise RuntimeError(
                    "InterceptorClient: patch_genai_client() must be entered "
                    "before any RECORD-mode client is created."
                )
            self._real_client = _REAL_CLIENT_CLASS(**kwargs)
        self.aio = _MockAio(
            self._real_client.aio if self._real_client is not None else None
        )

    @property
    def vertexai(self) -> bool:
        if self._real_client is not None:
            return bool(self._real_client.vertexai)
        return False


# ---------------------------------------------------------------------------
# Public patch context manager
# ---------------------------------------------------------------------------


@contextmanager
def patch_genai_client():
    """Context manager that replaces ``google.genai.Client`` with
    ``InterceptorClient`` for the duration of the block.

    Must be entered BEFORE the FastAPI app is imported/started so that
    ``Gemini.api_client`` (a cached_property) is initialised with the mock.
    """
    global _REAL_CLIENT_CLASS  # noqa: PLW0603

    # Capture the real class before any patching so RECORD mode can reach it.
    from google.genai import Client as _orig  # noqa: PLC0415

    _REAL_CLIENT_CLASS = _orig
    try:
        with patch("google.genai.Client", InterceptorClient):
            # ADK imports Client via a local `from google.genai import Client`
            # inside Gemini.api_client — patching the module attribute above is
            # sufficient because Python re-evaluates the import each time (it is
            # not a module-level cached import on the ADK side).
            mode = "RECORD" if RECORD else "REPLAY"
            logger.info(
                "genai_interceptor active (%s) — cassettes at %s",
                mode,
                CASSETTES_DIR,
            )
            yield
    finally:
        _REAL_CLIENT_CLASS = None


# ---------------------------------------------------------------------------
# Pytest fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def genai_interceptor():
    """Session-scoped fixture that activates the cassette interceptor.

    Add this as a dependency of the ``asgi_app`` fixture in conftest.py so
    the patch is in place before any ADK model is created.
    """
    with patch_genai_client():
        yield
