"""Runner module for RadBot.

Re-exports the stock ADK ``Runner`` as ``RadbotRunner``.

All Runner imports in the codebase use::

    from radbot.agent.runner import RadbotRunner as Runner

This indirection keeps a single point of change if we ever need to
customize Runner behaviour.
"""

from google.adk.runners import Runner as RadbotRunner  # noqa: F401

__all__ = ["RadbotRunner"]
