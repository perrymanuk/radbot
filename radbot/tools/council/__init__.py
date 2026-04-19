"""Scout's plan council — multi-critic structured plan review.

Three core critics (+ one on-demand) review a plan from complementary lenses
and return priority-tagged findings (P0–P3). Scout orchestrates the rounds,
respects blocker semantics (P0/P1 must be resolved before approval), and
preserves honest disagreement instead of forcing consensus.

Background: the shape is adapted from Perry's DevOps Initiative Council
(3-round structured review, persona-scoped lenses) + GitHub Copilot CLI's
"Rubber Duck" cross-family review pattern + OpenCode's Momus/`@check` strict
reviewer discipline + Pi's priority-tagged `report_finding` format. See
`specs/agents.md` § Scout Plan Council and the PR discussion for design
rationale.

All critics currently run on scout's model (Gemini 3.1 Pro). Cross-family
routing via LiteLLM is tracked as PRJ1/PT18.
"""

from radbot.tools.council.critics import (
    COUNCIL_TOOLS,
    critique_architecture_tool,
    critique_feasibility_tool,
    critique_safety_tool,
    critique_ux_dx_tool,
)
from radbot.tools.council.triggers import (
    should_convene_council_tool,
)

__all__ = [
    "COUNCIL_TOOLS",
    "critique_architecture_tool",
    "critique_feasibility_tool",
    "critique_safety_tool",
    "critique_ux_dx_tool",
    "should_convene_council_tool",
]
