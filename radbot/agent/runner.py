"""Custom Runner that fixes ADK 2.0.0a3 transfer_to_agent with V1_LLM_AGENT disabled.

Bug: Runner.run_async() unconditionally wraps LlmAgent in _V1LlmAgentWrapper,
even when V1_LLM_AGENT is disabled and LlmAgent is a _Mesh (BaseNode subclass).
The wrapper intercepts transfer_to_agent events and breaks the _Mesh generator
before it can route to the target node. Sub-agents also get silently converted
from mode='chat' to mode='single_turn' with no history.

Fix: When V1 is disabled, skip the wrapper and let the _Mesh handle its own
orchestration via the BaseNode path (which calls _run_node_async without a
wrapper node).

This subclass should be removed once ADK fixes this upstream.
"""

import logging
from typing import Any, AsyncGenerator, Optional

from google.adk.runners import Runner, RunConfig
from google.genai import types

logger = logging.getLogger(__name__)


def _patch_mesh_logging():
    """Monkey-patch _Mesh.run_node_impl to add transfer debug logging.

    Temporary diagnostic — remove once transfer routing is confirmed working.
    """
    try:
        from google.adk.agents.llm._mesh import _Mesh
        from google.adk.events.event import Event

        _original_run_node_impl = _Mesh.run_node_impl

        async def _logged_run_node_impl(self, *, ctx, node_input):
            logger.info(
                "_Mesh[%s]: run_node_impl started, nodes=%s",
                self.name,
                [n.name for n in self.nodes],
            )
            async for event in _original_run_node_impl(self, ctx=ctx, node_input=node_input):
                if isinstance(event, Event):
                    transfer = getattr(event.actions, "transfer_to_agent", None) if hasattr(event, "actions") else None
                    author = getattr(event, "author", "?")
                    has_fc = False
                    has_text = False
                    if hasattr(event, "content") and event.content and hasattr(event.content, "parts") and event.content.parts:
                        for p in event.content.parts:
                            if hasattr(p, "function_call") and p.function_call:
                                has_fc = getattr(p.function_call, "name", True)
                            if hasattr(p, "text") and p.text:
                                has_text = True
                    logger.info(
                        "_Mesh[%s]: yield event author=%s transfer=%s fc=%s text=%s",
                        self.name, author, transfer, has_fc, has_text,
                    )
                yield event
            logger.info("_Mesh[%s]: run_node_impl ended", self.name)

        _Mesh.run_node_impl = _logged_run_node_impl
        logger.info("_Mesh.run_node_impl patched with transfer debug logging")
    except Exception as e:
        logger.warning("Failed to patch _Mesh logging: %s", e)


# Apply patch at import time
_patch_mesh_logging()


class RadbotRunner(Runner):
    """Runner subclass that correctly handles the V2 workflow LlmAgent."""

    async def run_async(
        self,
        *,
        user_id: str,
        session_id: str,
        invocation_id: Optional[str] = None,
        new_message: Optional[types.Content] = None,
        state_delta: Optional[dict[str, Any]] = None,
        run_config: Optional[RunConfig] = None,
        yield_user_message: bool = False,
    ) -> AsyncGenerator:
        from google.adk.agents.llm_agent import LlmAgent
        from google.adk.features import FeatureName, is_feature_enabled
        from google.adk.workflow._base_node import BaseNode

        # When V1 is disabled, LlmAgent is a _Mesh (BaseNode subclass).
        # Route it through the BaseNode path instead of wrapping it.
        v1_enabled = is_feature_enabled(FeatureName.V1_LLM_AGENT)
        is_llm = isinstance(self.agent, LlmAgent)
        is_node = isinstance(self.agent, BaseNode)

        if is_llm and not v1_enabled and is_node:
            logger.info(
                "RadbotRunner: V1 disabled, routing %s (_Mesh) through BaseNode path",
                self.agent.name,
            )
            run_config = run_config or RunConfig()
            if new_message and not new_message.role:
                new_message.role = "user"

            # Ensure chat mode is set (the _Mesh needs it for transfer routing)
            if self.agent.mode is None:
                self.agent.mode = "chat"

            async for event in self._run_node_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
                run_config=run_config,
                yield_user_message=yield_user_message,
            ):
                yield event
            return

        logger.info(
            "RadbotRunner: using standard path (V1=%s, LlmAgent=%s, BaseNode=%s)",
            v1_enabled, is_llm, is_node,
        )
        # Fall through to standard Runner.run_async for all other cases
        async for event in super().run_async(
            user_id=user_id,
            session_id=session_id,
            invocation_id=invocation_id,
            new_message=new_message,
            state_delta=state_delta,
            run_config=run_config,
            yield_user_message=yield_user_message,
        ):
            yield event
