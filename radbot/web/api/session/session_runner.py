"""
Session runner for RadBot web interface.

This module provides the SessionRunner class for managing ADK Runner instances.
"""

import asyncio
import json
import logging
import os
import sys

# Add repo root to sys.path so `import agent` (root-level agent.py) resolves.
# Must happen before any radbot/agent imports below.
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../../")
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from google.adk.artifacts import InMemoryArtifactService  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai.types import Content, Part  # noqa: E402

# Registry of available session roots (keyed by agent_name stored on
# chat_sessions). get_root_agent imports agent.py transitively, which sets
# up the agent tree; unknown names fall back to beto.
from radbot.agent.agent_core import get_root_agent  # noqa: E402
from radbot.agent.runner import RadbotRunner as Runner  # noqa: E402
from radbot.web.api.malformed_function_handler import (  # noqa: E402
    extract_text_from_malformed_function,
)
from radbot.web.api.session.event_processing import (  # noqa: E402
    _process_agent_transfer_event,
    _process_generic_event,
    _process_model_response_event,
    _process_planner_event,
    _process_tool_call_event,
)
from radbot.web.api.session.utils import (  # noqa: E402
    _extract_response_from_event,
    _get_current_timestamp,
    _get_event_type,
)

logger = logging.getLogger(__name__)


class SessionRunner:
    """Enhanced ADK Runner for web sessions."""

    def __init__(self, user_id: str, session_id: str, agent_name: str = "beto"):
        """Initialize a SessionRunner for a specific user.

        Args:
            user_id: Unique user identifier
            session_id: Session identifier
            agent_name: Root agent name for this session. ``"beto"`` (default)
                routes through the general-purpose orchestrator; ``"scout"``
                boots a planning-focused session that skips beto's routing
                layer. Unknown names fall back to beto.
        """
        self.user_id = user_id
        self.session_id = session_id
        self.agent_name = agent_name
        self.session_service = InMemorySessionService()

        # Resolve the session's root agent. ``get_root_agent`` falls back to
        # beto on any unknown name (so legacy rows or typos don't strand
        # sessions).
        self._root_agent = get_root_agent(agent_name)

        # Create artifact service for this session
        self.artifact_service = InMemoryArtifactService()
        logger.debug("Created InMemoryArtifactService for the session")

        # Log agent tree structure
        self._log_agent_tree()

        # Create the ADK Runner with app_name matching the selected root
        app_name = (
            self._root_agent.name if hasattr(self._root_agent, "name") else agent_name
        )
        logger.info(
            "SessionRunner session=%s user=%s root=%s app_name=%s",
            session_id,
            user_id,
            app_name,
            app_name,
        )

        # Get memory service from the selected root agent if available
        memory_service = None
        if hasattr(self._root_agent, "_memory_service"):
            memory_service = self._root_agent._memory_service
            logger.debug("Using memory service from root agent")
        elif hasattr(self._root_agent, "memory_service"):
            memory_service = self._root_agent.memory_service
            logger.debug("Using memory service from root agent")

        # Store memory_service in the global ToolContext class so memory tools can find it
        if memory_service:
            from google.adk.tools.tool_context import ToolContext

            # Set memory_service in the ToolContext class for tools to access
            setattr(ToolContext, "memory_service", memory_service)
            logger.debug("Set memory_service in global ToolContext class")

        # Create the Runner with artifact service and memory service
        self.runner = Runner(
            agent=self._root_agent,
            app_name=app_name,
            session_service=self.session_service,
            artifact_service=self.artifact_service,  # Pass artifact service to Runner
            memory_service=memory_service,  # Pass memory service to Runner
        )

        # Enable ADK context caching to reduce API costs.
        # System instructions + tool schemas are identical across requests,
        # so cached tokens (billed at 10% rate) approach 100% hit rate.
        try:
            from google.adk.agents.context_cache_config import ContextCacheConfig

            self.runner.context_cache_config = ContextCacheConfig(
                cache_intervals=20,
                ttl_seconds=3600,
                min_tokens=2048,
            )
            logger.debug(
                "Enabled context caching on web Runner (intervals=20, ttl=3600s, min_tokens=2048)"
            )
        except Exception as e:
            logger.warning(f"Could not enable context caching: {e}")

    def _log_agent_tree(self):
        """Log the agent tree structure for debugging."""
        logger.debug("===== AGENT TREE STRUCTURE =====")

        agent = self._root_agent
        # Check root agent
        if hasattr(agent, "name"):
            logger.debug(f"ROOT AGENT: name='{agent.name}'")
        else:
            logger.warning("ROOT AGENT: No name attribute")

        # Check sub-agents
        if hasattr(agent, "sub_agents") and agent.sub_agents:
            sub_agent_names = [
                sa.name for sa in agent.sub_agents if hasattr(sa, "name")
            ]
            logger.debug(f"SUB-AGENTS: {sub_agent_names}")

            # Check each sub-agent
            for i, sa in enumerate(agent.sub_agents):
                sa_name = sa.name if hasattr(sa, "name") else f"unnamed-{i}"
                logger.debug(f"SUB-AGENT {i}: name='{sa_name}'")

                # Check if sub-agent has its own sub-agents
                if hasattr(sa, "sub_agents") and sa.sub_agents:
                    sa_sub_names = [
                        ssa.name for ssa in sa.sub_agents if hasattr(ssa, "name")
                    ]
                    logger.debug(f"  SUB-AGENTS OF '{sa_name}': {sa_sub_names}")
        else:
            logger.warning("ROOT AGENT: No sub_agents found")

        logger.debug("===============================")

    async def process_message(self, message: str, run_config=None) -> dict:
        """Process a user message and return the agent's response with event data.

        Args:
            message: The user's message text
            run_config: Optional ``RunConfig`` passed through to ``runner.run_async()``.
                        Use to set ``max_llm_calls`` or other per-request limits.

        Returns:
            Dictionary containing the agent's response text and event data
        """
        try:
            # Create Content object with the user's message
            user_message = Content(parts=[Part(text=message)], role="user")

            # Get the app_name from the runner
            app_name = (
                self.runner.app_name if hasattr(self.runner, "app_name") else "beto"
            )

            # Get or create a session with the user_id and session_id
            session = await self.session_service.get_session(
                app_name=app_name, user_id=self.user_id, session_id=self.session_id
            )

            if not session:
                logger.debug(
                    f"Creating new session for user {self.user_id} with app_name='{app_name}'"
                )
                session = await self.session_service.create_session(
                    app_name=app_name, user_id=self.user_id, session_id=self.session_id
                )
                # Load conversation history from DB into the new ADK session
                await self._load_history_into_session(session)

            # OPTIMIZATION: Limit event history to reduce context size.
            # Priority-based: keep conversation events (user/model text)
            # over tool events (function_call/function_response), since
            # stale tool results consume the most tokens with the least value.
            try:
                event_count = len(session.events) if hasattr(session, "events") else 0
                MAX_EVENTS = 20

                if event_count > MAX_EVENTS:
                    conversation_events = []
                    tool_events = []
                    for ev in session.events:
                        is_tool = False
                        if (
                            hasattr(ev, "content")
                            and ev.content
                            and hasattr(ev.content, "parts")
                            and ev.content.parts
                        ):
                            for part in ev.content.parts:
                                if (
                                    hasattr(part, "function_call")
                                    and part.function_call
                                ) or (
                                    hasattr(part, "function_response")
                                    and part.function_response
                                ):
                                    is_tool = True
                                    break
                        if is_tool:
                            tool_events.append(ev)
                        else:
                            conversation_events.append(ev)

                    # Keep all recent conversation events, fill remaining with tool events
                    kept_conversation = conversation_events[-MAX_EVENTS:]
                    remaining_slots = MAX_EVENTS - len(kept_conversation)
                    kept_tools = (
                        tool_events[-remaining_slots:] if remaining_slots > 0 else []
                    )

                    # Merge and sort by original position to preserve ordering
                    original_order = {id(ev): i for i, ev in enumerate(session.events)}
                    merged = kept_conversation + kept_tools
                    merged.sort(key=lambda ev: original_order.get(id(ev), 0))

                    session.events[:] = merged
                    logger.debug(
                        f"Optimized event history: {event_count} -> {len(merged)} events "
                        f"({len(kept_conversation)} conversation, {len(kept_tools)} tool)"
                    )
            except Exception as e:
                logger.warning(f"Could not optimize event history: {e}")

            # Use the runner to process the message
            logger.info(
                f"Running agent with message: {message[:50]}{'...' if len(message) > 50 else ''}"
            )

            # Set user_id in ToolContext for memory tools
            if hasattr(self.runner, "memory_service") and self.runner.memory_service:
                from google.adk.tools.tool_context import ToolContext

                setattr(ToolContext, "user_id", self.user_id)

            # Run with consistent parameters (use run_async to avoid blocking the event loop)
            MAX_RETRIES = 3
            events = []
            for attempt in range(MAX_RETRIES):
                events = []
                async for event in self.runner.run_async(
                    user_id=self.user_id,
                    session_id=session.id,
                    new_message=user_message,
                    run_config=run_config,
                ):
                    events.append(event)

                # Check if any event has actual text content (not just function calls/transfers).
                # Function call parts (transfer_to_agent etc.) don't count — we need real text.
                has_text = False
                for ev in events:
                    if (
                        hasattr(ev, "content")
                        and ev.content
                        and hasattr(ev.content, "parts")
                        and ev.content.parts
                    ):
                        for part in ev.content.parts:
                            if hasattr(part, "text") and part.text:
                                has_text = True
                                break
                    if has_text:
                        break

                if has_text or attempt == MAX_RETRIES - 1:
                    break

                # Empty text response — the model returned function calls (e.g. transfer_to_agent)
                # but the target agent produced no text.  Reset the session to avoid poisoning
                # and retry with a fresh session.
                logger.warning(
                    "No text in model response on attempt %d/%d (got %d events with function calls only) "
                    "— resetting session and retrying",
                    attempt + 1,
                    MAX_RETRIES,
                    len(events),
                )
                try:
                    app_name = (
                        self.runner.app_name
                        if hasattr(self.runner, "app_name")
                        else "beto"
                    )
                    await self.session_service.delete_session(
                        app_name=app_name, user_id=self.user_id, session_id=session.id
                    )
                    session = await self.session_service.create_session(
                        app_name=app_name,
                        user_id=self.user_id,
                        session_id=self.session_id,
                    )
                    # Don't reload history on retry — it may contain the
                    # poisoned empty-content event that caused the failure.
                    # A clean session with just the current message is safer.
                except Exception as e:
                    logger.warning("Failed to reset session for retry: %s", e)

                # Brief backoff before next attempt — gives Gemini API time to recover
                await asyncio.sleep(0.5 * (attempt + 1))

            # Process events
            logger.debug(
                f"Received {len(events)} events from runner: {[type(e).__name__ for e in events]}"
            )

            # Log detailed information about each event
            for i, event in enumerate(events):
                # Log is_final_response
                is_final = False
                if hasattr(event, "is_final_response"):
                    if callable(getattr(event, "is_final_response")):
                        is_final = event.is_final_response()
                    else:
                        is_final = event.is_final_response
                logger.debug(
                    f"Event {i}: is_final={is_final}, content={type(event.content).__name__ if hasattr(event, 'content') else 'N/A'}"  # noqa: E501
                )

                # Log content parts detail to diagnose text extraction
                if hasattr(event, "content") and event.content:
                    if hasattr(event.content, "parts") and event.content.parts:
                        for j, part in enumerate(event.content.parts):
                            part_attrs = []
                            if hasattr(part, "text") and part.text:
                                part_attrs.append(f"text={part.text[:80]}...")
                            if hasattr(part, "function_call") and part.function_call:
                                fc = part.function_call
                                name = getattr(fc, "name", "unknown")
                                part_attrs.append(f"function_call={name}")
                            if (
                                hasattr(part, "function_response")
                                and part.function_response
                            ):
                                fr = part.function_response
                                name = getattr(fr, "name", "unknown")
                                part_attrs.append(f"function_response={name}")
                            if not part_attrs:
                                part_attrs.append(
                                    f"type={type(part).__name__}, attrs={[a for a in dir(part) if not a.startswith('_')]}"  # noqa: E501
                                )
                            logger.debug(
                                f"  Event {i} part {j}: {', '.join(part_attrs)}"
                            )
                    else:
                        # Detailed diagnostics for empty content (no parts)
                        role = getattr(event.content, "role", "unknown")
                        parts_val = getattr(event.content, "parts", "MISSING")
                        is_final = False
                        if hasattr(event, "is_final_response") and callable(
                            getattr(event, "is_final_response")
                        ):
                            is_final = event.is_final_response()
                        logger.warning(
                            "  Event %d: EMPTY CONTENT — role=%s, parts=%r, is_final=%s, author=%s. "
                            "This may cause session poisoning (subsequent requests can also return empty).",
                            i,
                            role,
                            parts_val,
                            is_final,
                            getattr(event, "author", "unknown"),
                        )
                        # Inspect content object for any non-standard attributes
                        content_attrs = {
                            a: repr(getattr(event.content, a, None))[:120]
                            for a in dir(event.content)
                            if not a.startswith("_")
                            and a not in ("parts", "role")
                            and getattr(event.content, a, None) is not None
                        }
                        if content_attrs:
                            logger.warning(
                                "  Event %d: content attrs: %s", i, content_attrs
                            )

                # Log actions (agent transfers) for debugging
                if hasattr(event, "actions") and event.actions:
                    actions = event.actions
                    if (
                        hasattr(actions, "transfer_to_agent")
                        and actions.transfer_to_agent
                    ):
                        logger.debug(
                            f"  Event {i}: TRANSFER_TO_AGENT={actions.transfer_to_agent}"
                        )
                    if hasattr(actions, "escalate") and actions.escalate:
                        logger.debug(f"  Event {i}: ESCALATE=True")

                # Log author for debugging
                if hasattr(event, "author"):
                    logger.debug(f"  Event {i}: author={event.author}")

            # Initialize variables for collecting event data
            final_response = None
            last_text_response = None  # Track last non-empty text from any model event
            processed_events = []
            raw_response = None
            handoffs: list[dict] = []  # collected agent transfers for inline chips

            for event in events:
                # Extract event type and create a base event object
                event_type = _get_event_type(event)
                event_data = {"type": event_type, "timestamp": _get_current_timestamp()}

                # Process based on event type
                if event_type == "tool_call":
                    event_data.update(_process_tool_call_event(event))
                elif event_type == "agent_transfer":
                    event_data.update(_process_agent_transfer_event(event))
                    # Capture {from, to} for inline handoff chip injection.
                    to_agent = event_data.get("to_agent")
                    if to_agent:
                        handoffs.append(
                            {
                                "from": (
                                    event_data.get("from_agent") or "BETO"
                                ).upper(),
                                "to": str(to_agent).upper(),
                            }
                        )
                elif event_type == "planner":
                    event_data.update(_process_planner_event(event))
                elif event_type == "model_response":
                    event_data.update(_process_model_response_event(event))
                    text = event_data.get("text", "")
                    # Track the last non-empty text from any model response event
                    if text:
                        last_text_response = text
                    # Check if this is the final response - only set if there's actual text
                    if (
                        hasattr(event, "is_final_response")
                        and event.is_final_response()
                    ):
                        if text:
                            final_response = text
                        # Save raw response for later use if needed
                        if hasattr(event, "raw_response"):
                            raw_response = event.raw_response
                else:
                    # Generic event processing
                    event_data.update(_process_generic_event(event))

                    # Get raw response if available
                    if hasattr(event, "raw_response"):
                        raw_response = event.raw_response

                processed_events.append(event_data)

                # Store the event in the events storage
                # Import here to avoid circular imports
                from radbot.web.api.events import add_event

                add_event(self.session_id, event_data)

                # If no final response has been found yet, try to extract it
                if not final_response:
                    extracted = _extract_response_from_event(event)
                    if extracted:
                        final_response = extracted

            # If we still don't have a response, check for malformed function calls
            if not final_response and raw_response:
                try:
                    if isinstance(raw_response, str):
                        # Try to parse the raw response as JSON
                        try:
                            raw_response_data = json.loads(raw_response)
                        except json.JSONDecodeError:
                            logger.warning("Could not parse raw response as JSON")
                            raw_response_data = {"raw_text": raw_response}
                    else:
                        raw_response_data = raw_response

                    # Extract text from malformed function call
                    extracted_text = extract_text_from_malformed_function(
                        raw_response_data
                    )
                    if extracted_text:
                        logger.debug(
                            f"Recovered text from malformed function call: {extracted_text[:100]}..."
                        )
                        final_response = extracted_text

                        # Create a synthetic model response event
                        model_event = {
                            "type": "model_response",
                            "category": "model_response",
                            "timestamp": _get_current_timestamp(),
                            "summary": "Recovered Response from Malformed Function",
                            "text": extracted_text,
                            "is_final": True,
                            "details": {
                                "recovered_from": "malformed_function_call",
                                "session_id": self.session_id,
                            },
                        }
                        processed_events.append(model_event)

                        # Add this event to the event storage
                        from radbot.web.api.events import add_event

                        add_event(self.session_id, model_event)
                except Exception as e:
                    logger.error(
                        f"Error processing malformed function call: {str(e)}",
                        exc_info=True,
                    )

            # Fall back to last non-empty text from any model response event
            if not final_response and last_text_response:
                logger.debug(
                    "Using last non-empty text from intermediate model response events"
                )
                final_response = last_text_response

            if not final_response:
                # Build a summary of what the model actually returned
                event_summary = []
                for idx, ev in enumerate(events):
                    etype = type(ev).__name__
                    has_content = hasattr(ev, "content") and ev.content is not None
                    has_parts = (
                        has_content
                        and hasattr(ev.content, "parts")
                        and ev.content.parts
                    )
                    parts_count = len(ev.content.parts) if has_parts else 0
                    role = getattr(ev.content, "role", "?") if has_content else "?"
                    author = getattr(ev, "author", "?")
                    is_final = False
                    if hasattr(ev, "is_final_response") and callable(
                        getattr(ev, "is_final_response")
                    ):
                        is_final = ev.is_final_response()
                    event_summary.append(
                        f"  [{idx}] {etype}: author={author}, role={role}, "
                        f"parts={parts_count}, is_final={is_final}"
                    )
                logger.warning(
                    "NO TEXT RESPONSE found in %d events (session=%s). "
                    "This usually means the model returned empty content which will poison "
                    "the session history — all future requests in this session may also fail.\n"
                    "Event breakdown:\n%s",
                    len(events),
                    self.session_id,
                    "\n".join(event_summary) if event_summary else "  (no events)",
                )
                final_response = "I apologize, but I couldn't generate a response."

            # Prepend handoff chips so the frontend can render inline "BETO → PLANNER"
            # markers. Deduplicate consecutive identical handoffs (ADK can emit the
            # same transfer twice on retry) and skip reflexive beto→beto entries.
            if handoffs and final_response:
                seen: set[tuple[str, str]] = set()
                chips: list[str] = []
                for h in handoffs:
                    key = (h["from"], h["to"])
                    if key in seen or h["from"] == h["to"]:
                        continue
                    seen.add(key)
                    chips.append(f"```radbot:handoff\n{json.dumps(h)}\n```")
                if chips:
                    final_response = "\n".join(chips) + "\n\n" + final_response

            # Filter events: keep non-model events (tool_call, agent_transfer, etc.)
            # but only include the FINAL model_response to avoid duplicate chat messages
            # and unnecessary API-driven display.
            filtered_events = []
            last_model_event = None
            for ev in processed_events:
                if (
                    ev.get("type") == "model_response"
                    or ev.get("category") == "model_response"
                ):
                    # Track the latest; prefer one marked as final
                    if ev.get("is_final") or last_model_event is None:
                        last_model_event = ev
                else:
                    filtered_events.append(ev)
            if last_model_event:
                filtered_events.append(last_model_event)

            # Return both the text response and the filtered events
            return {"response": final_response, "events": filtered_events}

        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}", exc_info=True)
            error_message = f"I apologize, but I encountered an error processing your message. Please try again. Error: {str(e)}"  # noqa: E501
            return {"response": error_message, "events": []}

    def _extract_response_from_event(self, event):
        """Extract response text from various event types."""
        # Method 1: Check content.parts for text (works for both final and non-final)
        if hasattr(event, "content") and event.content:
            if hasattr(event.content, "parts") and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        return self._process_response_text(part.text)

        # Method 2: Check for content.text directly
        if hasattr(event, "content"):
            if hasattr(event.content, "text") and event.content.text:
                return self._process_response_text(event.content.text)

        # Method 3: Check for message attribute
        if hasattr(event, "message"):
            if hasattr(event.message, "content"):
                return self._process_response_text(event.message.content)

        return None

    def _process_response_text(self, text):
        """
        Process response text to handle special content types using web standards approach.

        This identifies special content like JSON and wraps it with appropriate
        data attributes for proper rendering in the frontend.

        Args:
            text: The text to process

        Returns:
            Processed text with content type annotations
        """
        import json
        import re
        from html import escape

        try:
            # First check if this is already HTML content with data attributes
            # If so, return it as is to avoid double-processing
            if "<pre data-content-type=" in text:
                return text

            # Check for special JSON responses that need to be preserved as-is
            special_patterns = [
                r'{"call_search_agent_response":',
                r'{"call_web_search_response":',
                r'{"function_call_response":',
            ]

            # First, check if the entire text is a special JSON response
            is_special_json = False
            for pattern in special_patterns:
                if re.search(pattern, text):
                    is_special_json = True
                    break

            if is_special_json:
                try:
                    # For special JSON that appears to be the full response, wrap the entire thing
                    if text.strip().startswith("{") and text.strip().endswith("}"):
                        # Validate it's actually valid JSON first
                        json.loads(text)

                        # Escape HTML entities
                        safe_json = escape(text)

                        # Wrap in our content-type element
                        return f'<pre data-content-type="json-raw" class="content-json-raw">{safe_json}</pre>'
                    else:
                        # Look for JSON object in the text
                        json_obj_match = re.search(r"({.*})", text, re.DOTALL)
                        if json_obj_match:
                            full_text = text
                            json_str = json_obj_match.group(1)

                            # Validate JSON
                            json.loads(json_str)

                            # Replace the JSON part with wrapped version
                            safe_json = escape(json_str)
                            wrapped_json = f'<pre data-content-type="json-raw" class="content-json-raw">{safe_json}</pre>'  # noqa: E501

                            # If the JSON is embedded in other text, preserve it
                            result = full_text.replace(json_str, wrapped_json)
                            return result
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Error processing special JSON: {str(e)}")
                    # If parsing fails, just return the original text
                    return text

            # Process regular JSON code blocks in markdown
            code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
            modified_text = text

            # Find all JSON code blocks
            matches = list(re.finditer(code_block_pattern, text))

            # Process in reverse order to avoid index issues when replacing
            for match in reversed(matches):
                block_content = match.group(1)
                # Check if this looks like JSON
                if (
                    block_content.strip().startswith("{")
                    and block_content.strip().endswith("}")
                ) or (
                    block_content.strip().startswith("[")
                    and block_content.strip().endswith("]")
                ):
                    try:
                        # Try to parse as JSON
                        json_obj = json.loads(block_content)

                        # Check if it's a special JSON content
                        block_text = json.dumps(json_obj)
                        is_special = any(
                            pattern.replace(r"{", "").replace(":", "") in block_text
                            for pattern in special_patterns
                        )

                        if is_special:
                            # For special API responses, preserve exact formatting
                            safe_content = escape(block_content)
                            wrapped_content = f'<pre data-content-type="json-raw" class="content-json-raw">{safe_content}</pre>'  # noqa: E501
                        else:
                            # For regular JSON, format it nicely
                            formatted = json.dumps(json_obj, indent=2)
                            safe_content = escape(formatted)
                            wrapped_content = f'<pre data-content-type="json-formatted" class="content-json-formatted">{safe_content}</pre>'  # noqa: E501

                        # Replace the code block with our data-attribute version
                        start, end = match.span()
                        modified_text = (
                            modified_text[:start]
                            + wrapped_content
                            + modified_text[end:]
                        )
                    except json.JSONDecodeError:
                        # Not valid JSON, leave as is
                        pass

            return modified_text

        except Exception as e:
            logger.warning(f"Error processing response text: {str(e)}")
            # Return original text if any processing error occurs
            return text

    def _get_current_timestamp(self):
        """Get the current timestamp in ISO format."""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _get_event_type(self, event):
        """Determine the type of event."""
        # For tool events in ADK 0.4.0, check for function_call / tool_calls attribute
        if hasattr(event, "function_call") or hasattr(event, "tool_calls"):
            return "tool_call"

        # Check for tool result event
        if hasattr(event, "function_response") or hasattr(event, "tool_results"):
            return "tool_call"

        # Try to get type attribute
        if hasattr(event, "type"):
            return str(event.type)

        # Check for tool call events
        if hasattr(event, "tool_name") or (
            hasattr(event, "payload")
            and isinstance(event.payload, dict)
            and "toolName" in event.payload
        ):
            return "tool_call"

        # Check for agent transfer events
        if hasattr(event, "to_agent") or (
            hasattr(event, "payload")
            and isinstance(event.payload, dict)
            and "toAgent" in event.payload
        ):
            return "agent_transfer"

        # Check for planner events
        if hasattr(event, "plan") or (
            hasattr(event, "payload")
            and isinstance(event.payload, dict)
            and ("plan" in event.payload or "planStep" in event.payload)
        ):
            return "planner"

        # Check for model response events
        if hasattr(event, "is_final_response"):
            return "model_response"

        # Check for content which indicates model response (ADK 0.4.0+)
        if hasattr(event, "content") or hasattr(event, "message"):
            return "model_response"

        # Default category
        return "other"

    def _process_tool_call_event(self, event):
        """Process a tool call event."""
        event_data = {"category": "tool_call", "summary": "Tool Call"}

        # Process function call events (ADK 0.4.0+)
        if hasattr(event, "function_call"):
            function_call = event.function_call
            if hasattr(function_call, "name"):
                event_data["tool_name"] = function_call.name
                event_data["summary"] = f"Tool Call: {function_call.name}"

            if hasattr(function_call, "args"):
                event_data["input"] = self._safely_serialize(function_call.args)

        # Process tool_calls (ADK 0.4.0+)
        elif hasattr(event, "tool_calls") and event.tool_calls:
            # Use first tool call for display
            tool_call = event.tool_calls[0]
            if hasattr(tool_call, "name"):
                event_data["tool_name"] = tool_call.name
                event_data["summary"] = f"Tool Call: {tool_call.name}"

            if hasattr(tool_call, "args"):
                event_data["input"] = self._safely_serialize(tool_call.args)

        # Process function response / tool results (ADK 0.4.0+)
        elif hasattr(event, "function_response"):
            if hasattr(event.function_response, "name"):
                event_data["tool_name"] = event.function_response.name
                event_data["summary"] = f"Tool Response: {event.function_response.name}"

            if hasattr(event.function_response, "response"):
                event_data["output"] = self._safely_serialize(
                    event.function_response.response
                )

        elif hasattr(event, "tool_results") and event.tool_results:
            # Use first tool result for display
            tool_result = event.tool_results[0]
            if hasattr(tool_result, "name"):
                event_data["tool_name"] = tool_result.name
                event_data["summary"] = f"Tool Response: {tool_result.name}"

            if hasattr(tool_result, "output"):
                event_data["output"] = self._safely_serialize(tool_result.output)

        # Legacy tool call formats
        else:
            # Extract tool name
            if hasattr(event, "tool_name"):
                event_data["tool_name"] = event.tool_name
                event_data["summary"] = f"Tool Call: {event.tool_name}"
            elif (
                hasattr(event, "payload")
                and isinstance(event.payload, dict)
                and "toolName" in event.payload
            ):
                event_data["tool_name"] = event.payload["toolName"]
                event_data["summary"] = f"Tool Call: {event.payload['toolName']}"

            # Extract input
            if hasattr(event, "input"):
                event_data["input"] = self._safely_serialize(event.input)
            elif (
                hasattr(event, "payload")
                and isinstance(event.payload, dict)
                and "input" in event.payload
            ):
                event_data["input"] = self._safely_serialize(event.payload["input"])

            # Extract output
            if hasattr(event, "output"):
                event_data["output"] = self._safely_serialize(event.output)
            elif (
                hasattr(event, "payload")
                and isinstance(event.payload, dict)
                and "output" in event.payload
            ):
                event_data["output"] = self._safely_serialize(event.payload["output"])

        # Get the full event for details
        event_data["details"] = self._get_event_details(event)

        return event_data

    def _process_agent_transfer_event(self, event):
        """Process an agent transfer event."""
        event_data = {"category": "agent_transfer", "summary": "Agent Transfer"}

        # Extract to_agent
        to_agent = None
        if hasattr(event, "to_agent"):
            to_agent = str(event.to_agent)
            event_data["to_agent"] = to_agent
            event_data["summary"] = f"Transfer to: {to_agent}"
        elif (
            hasattr(event, "payload")
            and isinstance(event.payload, dict)
            and "toAgent" in event.payload
        ):
            to_agent = str(event.payload["toAgent"])
            event_data["to_agent"] = to_agent
            event_data["summary"] = f"Transfer to: {to_agent}"

        # Extract from_agent if available
        if hasattr(event, "from_agent"):
            event_data["from_agent"] = str(event.from_agent)
        elif (
            hasattr(event, "payload")
            and isinstance(event.payload, dict)
            and "fromAgent" in event.payload
        ):
            event_data["from_agent"] = str(event.payload["fromAgent"])

        # Get the basic event details
        event_details = self._get_event_details(event)

        # Add model information for the transferred-to agent
        if to_agent:
            # Import here to avoid circular imports
            from radbot.config import config_manager

            # Convert agent name to the format expected by config_manager
            agent_config_name = to_agent.lower()
            if agent_config_name == "scout":
                agent_config_name = "scout_agent"
                event_details["model"] = config_manager.get_agent_model(
                    agent_config_name
                )
            elif agent_config_name in [
                "code_execution_agent",
                "search_agent",
                "todo_agent",
            ]:
                event_details["model"] = config_manager.get_agent_model(
                    agent_config_name
                )
            elif agent_config_name in ["beto", "radbot"]:
                # Use main model for the root agent
                event_details["model"] = config_manager.get_main_model()

        # Add the updated details to the event data
        event_data["details"] = event_details

        return event_data

    def _process_planner_event(self, event):
        """Process a planner event."""
        event_data = {"category": "planner", "summary": "Planner Event"}

        # Extract plan
        if hasattr(event, "plan"):
            event_data["plan"] = self._safely_serialize(event.plan)
            event_data["summary"] = "Plan Created"
        elif (
            hasattr(event, "payload")
            and isinstance(event.payload, dict)
            and "plan" in event.payload
        ):
            event_data["plan"] = self._safely_serialize(event.payload["plan"])
            event_data["summary"] = "Plan Created"

        # Extract plan step
        if hasattr(event, "plan_step"):
            event_data["plan_step"] = self._safely_serialize(event.plan_step)
            event_data["summary"] = (
                f"Plan Step: {self._get_plan_step_summary(event.plan_step)}"
            )
        elif (
            hasattr(event, "payload")
            and isinstance(event.payload, dict)
            and "planStep" in event.payload
        ):
            event_data["plan_step"] = self._safely_serialize(event.payload["planStep"])
            event_data["summary"] = (
                f"Plan Step: {self._get_plan_step_summary(event.payload['planStep'])}"
            )

        # Get the full event for details
        event_data["details"] = self._get_event_details(event)

        return event_data

    def _process_model_response_event(self, event):
        """Process a model response event."""
        event_data = {"category": "model_response", "summary": "Model Response"}

        # Extract text from content
        text = ""
        if hasattr(event, "content") and event.content:
            if hasattr(event.content, "parts") and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text
            elif hasattr(event.content, "text") and event.content.text:
                text = event.content.text

        # Extract text from message
        if not text and hasattr(event, "message"):
            if hasattr(event.message, "content"):
                text = event.message.content

        event_data["text"] = text

        # Check if it's a final response
        if hasattr(event, "is_final_response") and event.is_final_response():
            event_data["is_final"] = True
            event_data["summary"] = "Final Response"
        else:
            event_data["is_final"] = False
            event_data["summary"] = "Intermediate Response"

        # Save raw response if available
        if hasattr(event, "raw_response"):
            event_data["raw_response"] = event.raw_response

        # Try to extract raw response from event internals if not directly available
        if not hasattr(event, "raw_response"):
            if hasattr(event, "_raw_response"):
                event_data["raw_response"] = event._raw_response
            elif hasattr(event, "_response"):
                event_data["raw_response"] = event._response
            elif hasattr(event, "response"):
                event_data["raw_response"] = event.response

        # Get the basic event details
        event_details = self._get_event_details(event)

        # Add model information if not already present
        if "model" not in event_details:
            # Check if this event is from a specific agent and add its model information
            agent_name = None
            if hasattr(event, "agent_name"):
                agent_name = event.agent_name
            elif hasattr(event, "agent"):
                agent_name = event.agent

            # Set model information based on agent name
            if agent_name:
                # Import here to avoid circular imports
                from radbot.config import config_manager

                # Convert agent name to the format expected by config_manager
                agent_config_name = agent_name.lower()
                if agent_config_name == "scout":
                    agent_config_name = "scout_agent"
                elif agent_config_name in ["beto", "radbot"]:
                    # Use main model for the root agent
                    event_details["model"] = config_manager.get_main_model()

                # For specialized agents, get their specific model
                if agent_config_name in [
                    "code_execution_agent",
                    "search_agent",
                    "scout_agent",
                    "todo_agent",
                ]:
                    event_details["model"] = config_manager.get_agent_model(
                        agent_config_name
                    )

        # Add the updated details to the event data
        event_data["details"] = event_details

        return event_data

    def _process_generic_event(self, event):
        """Process a generic event."""
        event_data = {"category": "other", "summary": "Other Event"}

        # Try to get a more descriptive summary
        if hasattr(event, "__class__"):
            event_data["summary"] = f"Event: {event.__class__.__name__}"

        # Get the full event for details
        event_data["details"] = self._get_event_details(event)

        return event_data

    def _get_plan_step_summary(self, plan_step):
        """Get a summary string for a plan step."""
        if isinstance(plan_step, dict):
            if "description" in plan_step:
                return plan_step["description"]
            elif "action" in plan_step:
                return plan_step["action"]

        # Fallback summary
        return "Plan Step"

    def _get_event_details(self, event):
        """Get detailed information about the event."""
        # Try to convert to dict first
        try:
            if hasattr(event, "__dict__"):
                return self._safely_serialize(event.__dict__)
            elif hasattr(event, "to_dict"):
                return self._safely_serialize(event.to_dict())
            elif hasattr(event, "__str__"):
                return str(event)
        except Exception:
            logger.debug("Failed to extract event details, falling back to str()")

        # Fallback to string representation
        return str(event)

    def _safely_serialize(self, obj):
        """Safely serialize objects to JSON-compatible structures."""
        import json

        try:
            # Try direct JSON serialization
            json.dumps(obj)
            return obj
        except (TypeError, OverflowError, ValueError):
            # If that fails, try converting to string
            try:
                if hasattr(obj, "__dict__"):
                    return str(obj.__dict__)
                elif hasattr(obj, "to_dict"):
                    return str(obj.to_dict())
                else:
                    return str(obj)
            except Exception:
                return f"<Unserializable object of type {type(obj).__name__}>"

    async def _load_history_into_session(self, session):
        """Load conversation history from the database into an ADK session.

        Seeds the in-memory ADK session with past events so the agent
        retains context across reconnects and page refreshes.
        """
        try:
            import uuid

            from google.adk.events import Event

            from radbot.web.db import chat_operations

            db_messages = chat_operations.get_messages_by_session_id(
                self.session_id, limit=30
            )
            if not db_messages:
                logger.debug("No DB history found for session %s", self.session_id)
                return

            agent_name = (
                self._root_agent.name
                if hasattr(self._root_agent, "name")
                else self.agent_name
            )
            MAX_HISTORY = 15
            recent = db_messages[-MAX_HISTORY:]

            loaded = 0
            current_invocation_id = str(uuid.uuid4())
            for msg in recent:
                role = msg.get("role", "")
                content_text = msg.get("content", "")
                if not content_text:
                    continue

                if role == "user":
                    current_invocation_id = str(uuid.uuid4())
                    event = Event(
                        invocation_id=current_invocation_id,
                        author="user",
                        content=Content(parts=[Part(text=content_text)], role="user"),
                    )
                elif role == "assistant":
                    event = Event(
                        invocation_id=current_invocation_id,
                        author=agent_name,
                        content=Content(parts=[Part(text=content_text)], role="model"),
                    )
                else:
                    continue

                await self.session_service.append_event(session, event)
                loaded += 1

            if loaded:
                logger.debug(
                    "Loaded %d events from DB into ADK session %s",
                    loaded,
                    self.session_id,
                )
        except Exception as e:
            logger.warning(
                "Failed to load history from DB into session: %s", e, exc_info=True
            )

    async def reset_session(self):
        """Reset the session conversation history."""
        try:
            # Get the app_name from the runner
            app_name = (
                self.runner.app_name if hasattr(self.runner, "app_name") else "beto"
            )

            # Delete and recreate the session
            await self.session_service.delete_session(
                app_name=app_name, user_id=self.user_id, session_id=self.session_id
            )

            # Create a new session
            await self.session_service.create_session(
                app_name=app_name, user_id=self.user_id, session_id=self.session_id
            )

            logger.info(f"Reset session for user {self.user_id}")
            return True
        except Exception as e:
            logger.error(f"Error resetting session: {str(e)}")
            return False
