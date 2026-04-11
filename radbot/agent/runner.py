"""Runner module for RadBot.

Re-exports the stock ADK Runner as RadbotRunner. The stock Runner
correctly handles V2 LlmAgent via _V1LlmAgentWrapper, which delegates
to the _Mesh orchestration loop for proper multi-agent routing.

All Runner imports in the codebase use:
    from radbot.agent.runner import RadbotRunner as Runner

This indirection keeps a single point of change if we ever need to
customize Runner behavior.
"""

from google.adk.runners import Runner as RadbotRunner  # noqa: F401

__all__ = ["RadbotRunner"]
