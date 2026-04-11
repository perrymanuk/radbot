"""Custom Runner for RadBot with V2 workflow support.

ADK 2.0.0a3's _Mesh.run_node_impl has a bug where it breaks out of
the coordinator's event loop after call_llm events before execute_tools
can run. This prevents any tool execution (including RequestTaskTool for
task-mode agents).

Fix: bypass the _Mesh entirely and drive the Workflow execution directly.
We call the LlmAgent's _run_async_impl which creates the proper context,
but instead of going through _Mesh.run_node_impl (which breaks early),
we run the coordinator _SingleLlmAgent's run_async directly and handle
the request_task/transfer routing ourselves.
"""

import logging
from typing import Any, AsyncGenerator, Optional

from google.adk.runners import Runner, RunConfig
from google.genai import types

logger = logging.getLogger(__name__)


class RadbotRunner(Runner):
    """Runner that handles V2 LlmAgent tool execution correctly."""

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

            # Get the coordinator (_SingleLlmAgent) from the _Mesh nodes.
            # The coordinator is the agent with the same name as the root.
            coordinator = None
            request_task_agents = {}
            if hasattr(self.agent, "nodes"):
                for node in self.agent.nodes:
                    if node.name == self.agent.name:
                        coordinator = node
                    else:
                        request_task_agents[node.name] = node

            if coordinator is None:
                logger.warning(
                    "RadbotRunner: no coordinator found in _Mesh, falling back to standard path"
                )
                async for event in super().run_async(
                    user_id=user_id, session_id=session_id,
                    new_message=new_message, run_config=run_config,
                    yield_user_message=yield_user_message,
                ):
                    yield event
                return

            logger.info(
                "RadbotRunner: V2 path — running coordinator %s directly "
                "(bypassing _Mesh), task agents: %s",
                coordinator.name, list(request_task_agents.keys()),
            )

            # Run the coordinator's full Workflow (call_llm → execute_tools)
            # This properly executes tools including RequestTaskTool.
            async for event in coordinator.run_async(parent_context=ic):
                yield event

                # Check if the coordinator delegated to a task agent
                if (
                    hasattr(event, "actions")
                    and event.actions.request_task
                ):
                    # request_task is a dict keyed by fc_id -> task request info
                    for fc_id, task_req in event.actions.request_task.items():
                        agent_name = getattr(task_req, "agent_name", None) or (
                            task_req.get("agent_name") if isinstance(task_req, dict) else None
                        )
                        if agent_name and agent_name in request_task_agents:
                            target = request_task_agents[agent_name]
                            logger.info(
                                "RadbotRunner: task delegation to %s",
                                agent_name,
                            )
                            async for sub_event in target.run_async(parent_context=ic):
                                yield sub_event

                # Check for transfer_to_agent (chat mode agents like search_agent)
                if (
                    hasattr(event, "actions")
                    and event.actions.transfer_to_agent
                ):
                    target_name = event.actions.transfer_to_agent
                    if target_name in request_task_agents:
                        target = request_task_agents[target_name]
                        logger.info(
                            "RadbotRunner: transfer to %s", target_name,
                        )
                        async for sub_event in target.run_async(parent_context=ic):
                            yield sub_event

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
