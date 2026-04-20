"""Scout's divergent_ideation tool — three-persona parallel ideation.

Runs three persona-scoped LLM calls (Pragmatic, Contrarian, Wildcard) in
parallel and returns their distinct perspectives on a problem statement.
Inspired by neuroscience patterns of lateral inhibition and Default Mode
Network exploration. See `explorations: EX5` in Telos for the full design.
"""

from radbot.tools.divergent_ideation.tool import (
    divergent_ideation,
    divergent_ideation_tool,
)

__all__ = ["divergent_ideation", "divergent_ideation_tool"]
