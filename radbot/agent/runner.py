"""Custom Runner for RadBot with V2 workflow support.

Overrides run_async to use the _run_async_impl path (which goes through
the LlmAgent's own _Mesh orchestration) instead of the _run_node_async
path (which wraps the agent in a NodeRunner that doesn't support multi-
agent transfer).

The ADK 2.0.0a3 Runner has a bug where it always wraps LlmAgent in
_V1LlmAgentWrapper. When V1 is disabled, the wrapper breaks transfer
routing. This subclass bypasses the wrapper entirely by calling
_run_async_impl directly, which enters the _Mesh orchestration loop.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

from google.adk.runners import Runner, RunConfig
from google.genai import types

logger = logging.getLogger(__name__)


class RadbotRunner(Runner):
    """Runner that uses LlmAgent's native _run_async_impl for V2."""

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

        if (
            isinstance(self.agent, LlmAgent)
            and not is_feature_enabled(FeatureName.V1_LLM_AGENT)
        ):
            # V2 path: call the agent's run_async directly, which goes through
            # _Mesh.run_node_impl for proper multi-agent orchestration.
            run_config = run_config or RunConfig()
            if new_message and not new_message.role:
                new_message.role = "user"
            if self.agent.mode is None:
                self.agent.mode = "chat"

            session = await self._get_or_create_session(
                user_id=user_id, session_id=session_id
            )

            ic = self._new_invocation_context(
                session,
                new_message=new_message,
                run_config=run_config,
            )

            # Append user message to session
            if new_message:
                from google.adk.events.event import Event as AdkEvent
                ic.session.events.append(
                    AdkEvent(
                        invocation_id=ic.invocation_id,
                        author="user",
                        content=new_message,
                    )
                )

            logger.info(
                "RadbotRunner: V2 path — calling %s.run_async directly",
                self.agent.name,
            )
            async for event in self.agent.run_async(parent_context=ic):
                yield event
            return

        # V1 path: standard Runner behavior
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
