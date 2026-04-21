"""Auto-name a chat session from its recent message history.

PT63: Core Auto-Naming Service. Pulls the last ~20 messages, asks a cheap LLM
for a short human-friendly title, persists it via `chat_operations`, and
returns `(ok, message)` so callers (CLI `/name`, web `/name` intercept) can
report cleanly without exposing internal errors.
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Optional, Tuple

from radbot.web.db import chat_operations

logger = logging.getLogger(__name__)

HISTORY_WINDOW = 20
MIN_MESSAGES_FOR_NAMING = 2
LLM_TIMEOUT_SECONDS = 10.0
MAX_NAME_LENGTH = 80

_NAMING_PROMPT = (
    "You are naming a chat conversation for a sidebar list. "
    "Read the excerpt and produce ONE short, human-friendly title "
    "(max 6 words, Title Case, no quotes, no trailing punctuation). "
    'Return strict JSON: {"name": "..."}. '
    "Do not wrap the JSON in markdown fences.\n\n"
    "Conversation excerpt:\n"
    "-----\n"
    "{transcript}\n"
    "-----"
)


def _get_api_key() -> Optional[str]:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        return api_key
    try:
        from radbot.config.config_loader import config_loader

        return config_loader.get_config().get("api_keys", {}).get("google")
    except Exception as e:
        logger.debug("Could not read Google API key from config: %s", e)
        return None


def _resolve_naming_model() -> str:
    """Prefer an explicit cheap/naming model; fall back to the primary model."""
    env = os.getenv("RADBOT_NAMING_MODEL")
    if env:
        return env
    try:
        from radbot.config import config_manager

        agent_models = (
            getattr(config_manager, "model_config", {}).get("agent_models", {}) or {}
        )
        for key in ("naming_model", "cheap_model", "session_naming"):
            if agent_models.get(key):
                return agent_models[key]
        return config_manager.get_main_model()
    except Exception as e:
        logger.debug("Model resolution fell through to default: %s", e)
        return os.getenv("RADBOT_MAIN_MODEL", "gemini-2.5-flash")


def _strip_json_fences(text: str) -> str:
    stripped = text.strip()
    fence = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL | re.IGNORECASE
    )
    if fence:
        return fence.group(1).strip()
    return stripped


def _parse_name(raw: str) -> Optional[str]:
    cleaned = _strip_json_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str):
        return None
    name = name.strip().strip('"').strip("'")
    if not name:
        return None
    return name[:MAX_NAME_LENGTH]


def _build_transcript(messages: list) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "?")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _call_llm(model: str, prompt: str, api_key: str) -> str:
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return getattr(response, "text", "") or ""


def auto_name_session(session_id: str) -> Tuple[bool, str]:
    """Generate and persist a short name for `session_id`.

    Returns `(ok, message)`. On success, `message` is the new name. On
    failure it's a human-readable reason safe to show the user.
    """
    try:
        messages = chat_operations.get_messages_by_session_id(
            session_id=session_id, limit=HISTORY_WINDOW, offset=0
        )
    except Exception as e:
        logger.error("Failed to load history for session %s: %s", session_id, e)
        return False, "Could not load session history"

    if len(messages) < MIN_MESSAGES_FOR_NAMING:
        return False, "Not enough history to name session"

    api_key = _get_api_key()
    if not api_key:
        return False, "No Google API key configured"

    transcript = _build_transcript(messages)
    if not transcript:
        return False, "Not enough history to name session"

    prompt = _NAMING_PROMPT.replace("{transcript}", transcript)
    model = _resolve_naming_model()

    raw = ""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call_llm, model, prompt, api_key)
            raw = future.result(timeout=LLM_TIMEOUT_SECONDS)
    except FuturesTimeout:
        logger.warning(
            "Session naming LLM call timed out after %ss", LLM_TIMEOUT_SECONDS
        )
        return False, "Naming timed out"
    except Exception as e:
        logger.error("Session naming LLM call failed: %s", e)
        return False, "Naming model call failed"

    name = _parse_name(raw)
    if not name:
        logger.warning("Could not parse name from LLM output: %r", raw[:200])
        return False, "Could not parse naming response"

    try:
        ok = chat_operations.create_or_update_session(session_id=session_id, name=name)
    except Exception as e:
        logger.error("Failed to persist session name for %s: %s", session_id, e)
        return False, "Could not save session name"

    if not ok:
        return False, "Could not save session name"

    return True, name
