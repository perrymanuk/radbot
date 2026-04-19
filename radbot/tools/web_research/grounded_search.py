"""Grounded Google Search as a direct FunctionTool for scout.

Why this exists — scout-as-root needs a way to do grounded Google Search
without a sub-agent hop. ADK's ``search_agent`` builds it as a separate
agent with ``disallow_transfer_to_parent=True`` (Google Search grounding
can't be mixed with function declarations in the same model call). That
flag works fine when ``search_agent`` is a *peer* of the orchestrator
(beto's tree), because control naturally returns to the root above. But
when scout is the root and ``search_agent`` is her *child*, the flag
means control never returns to scout after the search — the workflow
just terminates without a synthesis turn. Users see a silent hang.

This tool sidesteps the sub-agent dance entirely. Scout calls it like
any other tool, gets the grounded answer + citations back as a plain
dict, and keeps going in her turn to synthesize the final response.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from google.adk.tools import FunctionTool
from google.genai import types as genai_types

from radbot.config.adk_config import create_client_with_config_settings
from radbot.tools.shared.sanitize import sanitize_external_content

logger = logging.getLogger(__name__)

# Google Search grounding requires a Gemini 2+ model. Pinned to Flash to
# keep the tool cheap — grounded search is a "fetch facts" op, the
# synthesis happens in scout's main Pro turn.
_GROUNDED_SEARCH_MODEL = "gemini-2.5-flash"


def _extract_citations(response: Any) -> List[Dict[str, str]]:
    """Pull ``[{title, url}]`` out of a grounded response's metadata.

    The grounding chunk shape is technically ``grounding_metadata.grounding_chunks[].web``
    on candidates — but the SDK surface has shifted across genai versions,
    so we navigate defensively and silently skip shapes we don't recognize.
    """
    cites: List[Dict[str, str]] = []
    for cand in getattr(response, "candidates", None) or []:
        meta = getattr(cand, "grounding_metadata", None)
        for chunk in getattr(meta, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            if web:
                cites.append(
                    {
                        "title": getattr(web, "title", "") or "",
                        "url": getattr(web, "uri", "") or "",
                    }
                )
    # Dedupe by URL, preserve order
    seen: set[str] = set()
    unique: List[Dict[str, str]] = []
    for c in cites:
        key = c["url"]
        if key and key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


async def grounded_search(query: str) -> Dict[str, Any]:
    """Perform a grounded Google Search and return the synthesized answer.

    This is scout's stateless alternative to the ``search_agent`` sub-agent
    — same backing capability (Gemini + Google Search grounding), but as
    a FunctionTool so control stays with scout through the turn.

    Args:
        query: Natural-language search query. Prefer primary-source framing
            ("official docs for X", "arxiv paper on Y") over listicle-bait.

    Returns:
        ``{"status": "success", "query": str, "answer": str,
           "citations": [{"title": str, "url": str}], "model": str}``
        on success; ``{"status": "error", "message": str}`` on failure.
        The answer text is already sanitized at the external-content boundary.
    """
    if not query or not isinstance(query, str):
        return {"status": "error", "message": "query must be a non-empty string"}

    try:
        client = create_client_with_config_settings()
    except Exception as e:
        logger.error("grounded_search: genai client unavailable: %s", e)
        return {"status": "error", "message": f"genai client unavailable: {e}"}

    config = genai_types.GenerateContentConfig(
        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
    )

    try:
        response = await client.aio.models.generate_content(
            model=_GROUNDED_SEARCH_MODEL,
            contents=query,
            config=config,
        )
    except Exception as e:
        logger.exception("grounded_search failed for query=%r", query)
        return {"status": "error", "query": query, "message": str(e)}

    raw = getattr(response, "text", "") or ""
    answer = sanitize_external_content(
        raw, source="grounded_search", strictness="strict"
    )
    citations = _extract_citations(response)

    logger.info(
        "grounded_search ok query=%r answer_chars=%d citations=%d",
        query,
        len(answer),
        len(citations),
    )
    return {
        "status": "success",
        "query": query,
        "answer": answer,
        "citations": citations,
        "model": _GROUNDED_SEARCH_MODEL,
    }


grounded_search_tool = FunctionTool(grounded_search)
