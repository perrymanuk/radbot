"""Nomad integration tools for infrastructure management.

Provides FunctionTool wrappers for the Nomad HTTP API, enabling the agent
to list jobs, check allocation health, view logs, restart allocations,
and submit job updates.
"""

from radbot.tools.nomad.nomad_tools import NOMAD_TOOLS

__all__ = ["NOMAD_TOOLS"]
