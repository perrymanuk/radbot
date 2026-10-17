"""
Session runner for RadBot web interface.

This module provides the SessionRunner class for managing ADK Runner instances.
"""

import asyncio
import json
import logging

from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# Registry of available session roots (keyed by agent_name stored on
# chat_sessions). get_root_agent resolves through the cached Assembly
# (built during web startup); unknown names fall back to beto.
from radbot.agent.assembly import get_root_agent
from radbot.config.adk_config import get_thinking_config
from radbot.web.api.session.event_processing import (
    _process_agent_transfer_event,
    _process_generic_event,
    _process_model_response_event,
    _process_planner_event,
    _process_tool_call_event,
)
from radbot.web.api.session.utils import (
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

        # Optionally enable Gemini Chain-of-Thought streaming. Gated by
        # config:agent.thinking_enabled + a model allowlist; returns None
        # when disabled or unsupported, so this is a no-op for older models
        # or when the flag is off.
        self._apply_thinking_config(self._root_agent)

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

        # Enable ADK context caching to reduce API costs. System instructions
        # + tool schemas are identical across requests, so cached tokens
        # (billed at 10% rate) approach 100% hit rate. ADK >= 2.7 keys the
        # cache per agent across transfers, but only when the config is set on
        # the App at construction time (setting it on the Runner afterwards
        # logs an "uncached agent transfer" warning and misses the per-agent
        # cache wiring).
        context_cache_config = None
        try:
            from google.adk.agents.context_cache_config import ContextCacheConfig

            context_cache_config = ContextCacheConfig(
                cache_intervals=20,
                ttl_seconds=3600,
                min_tokens=2048,
            )
        except Exception as e:
            logger.warning(f"Could not enable context caching: {e}")

        # Create the Runner with artifact service and memory service
        from google.adk.apps import App

        self.runner = Runner(
            app=App(
                name=app_name,
                root_agent=self._root_agent,
                context_cache_config=context_cache_config,
            ),
            session_service=self.session_service,
            artifact_service=self.artifact_service,  # Pass artifact service to Runner
            memory_service=memory_service,  # Pass memory service to Runner
        )
        if context_cache_config is not None:
            logger.debug(
                "Enabled context caching on web Runner (intervals=20, ttl=3600s, min_tokens=2048)"
            )

    def _apply_thinking_config(self, agent):
        """Attach a ``ThinkingConfig`` to ``agent.generate_content_config``
        when CoT streaming is enabled and the agent's model supports it.

        We mutate the existing ``GenerateContentConfig`` (preserving fields
        like ``temperature``) rather than replacing it. If the agent has no
        config object, we leave it alone — the gate is opt-in and we want
        zero behavior change when off.
        """
        try:
            from google.genai.types import GenerateContentConfig

            model = getattr(agent, "model", None) or ""
            thinking = get_thinking_config(model)
            if not thinking:
                return
            existing = getattr(agent, "generate_content_config", None)
            if isinstance(existing, GenerateContentConfig):
                # Pydantic model — copy with the new field merged.
                agent.generate_content_config = existing.model_copy(
                    update={"thinking_config": thinking}
                )
            else:
                agent.generate_content_config = GenerateContentConfig(
                    thinking_config=thinking
                )
            logger.info(
                "Enabled Gemini CoT (include_thoughts=True) for agent=%s model=%s",
                getattr(agent, "name", "?"),
                model,
            )
        except Exception as e:
            logger.warning("Failed to apply ThinkingConfig: %s", e)

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
                is_final = event.is_final_response()
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
            root_final_response = None  # Prefer text authored by the root agent
            last_text_response = None  # Track last non-empty text from any model event
            processed_events = []
            handoffs: list[dict] = []  # collected agent transfers for inline chips
            thought_chunks: list[str] = []  # Gemini CoT chunks (part.thought=True)
            root_agent_name = (self.agent_name or "beto").lower()

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
                    thought = event_data.get("thought_text", "")
                    if thought:
                        thought_chunks.append(thought)
                    # Track the last non-empty text from any model response event
                    if text:
                        last_text_response = text
                    # Check if this is the final response - only set if there's actual text
                    if event.is_final_response():
                        if text:
                            final_response = text
                            author = str(getattr(event, "author", "")).lower()
                            if author == root_agent_name:
                                root_final_response = text
                else:
                    # Generic event processing
                    event_data.update(_process_generic_event(event))

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

            # Prefer the root agent's final response over a sub-agent's stray
            # final text (e.g. a greeting from a transferred-to agent that
            # never returned control to the root).
            if root_final_response:
                final_response = root_final_response

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

            # Prepend Chain-of-Thought block. We use an XML-like tag rather
            # than a triple-backtick fence because thoughts often contain
            # their own code fences which would prematurely close it.
            # Emit before the handoff chips so handoff badges still render
            # at the top of the message body.
            if thought_chunks and final_response:
                thoughts_block = (
                    "<radbot:thoughts>\n"
                    + "".join(thought_chunks).rstrip()
                    + "\n</radbot:thoughts>"
                )
                final_response = thoughts_block + "\n\n" + final_response

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

    async def _load_history_into_session(self, session):
        """Load conversation history from the database into an ADK session.

        Seeds the in-memory ADK session with past events so the agent
        retains context across reconnects and page refreshes.
        """
        try:
            import uuid

            from google.adk.events import Event

            from radbot.web.db import chat_operations

            MAX_HISTORY = 15
            db_messages = chat_operations.get_recent_messages_by_session_id(
                self.session_id, limit=MAX_HISTORY
            )
            if not db_messages:
                logger.debug("No DB history found for session %s", self.session_id)
                return

            agent_name = (
                self._root_agent.name
                if hasattr(self._root_agent, "name")
                else self.agent_name
            )
            recent = db_messages

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
