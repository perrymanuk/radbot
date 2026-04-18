"""
Factory function for creating the KidsVid YouTube curation agent.

KidsVid searches YouTube for safe, educational, age-appropriate videos
for children, acting as a trusted curator and digital librarian.
"""

import logging
from typing import Optional

from google.adk.agents import Agent

from radbot.agent.factory_utils import load_tools
from radbot.agent.shared import load_agent_instruction, resolve_agent_model

logger = logging.getLogger(__name__)


def create_youtube_agent() -> Optional[Agent]:
    """Create the KidsVid agent for children's video curation.

    Returns:
        The created KidsVid ADK Agent, or None if creation failed.
    """
    try:
        model = resolve_agent_model("kidsvid_agent")
        logger.info(f"KidsVid agent model: {model}")

        instruction = load_agent_instruction(
            "kidsvid",
            "You are KidsVid, a children's video curator. "
            "Search YouTube for safe, educational, age-appropriate videos for children.",
        )

        # Build tools list
        tools = []

        # YouTube search tools
        tools.extend(
            load_tools(
                "radbot.tools.youtube",
                "YOUTUBE_TOOLS",
                "KidsVid",
                "YouTube",
            )
        )

        # CuriosityStream search tools
        tools.extend(
            load_tools(
                "radbot.tools.youtube.curiositystream_tools",
                "CURIOSITYSTREAM_TOOLS",
                "KidsVid",
                "CuriosityStream",
            )
        )

        # Kideo library tools (add videos to safe offline player)
        tools.extend(
            load_tools(
                "radbot.tools.youtube",
                "KIDEO_TOOLS",
                "KidsVid",
                "Kideo",
            )
        )

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("kidsvid")
        tools.extend(memory_tools)

        # Card-rendering tool — emits a fenced ```radbot:video block the
        # frontend renders as <VideoCard /> with an ADD TO KIDEO button.
        from radbot.tools.shared.card_protocol import show_video_card_tool

        tools.append(show_video_card_tool)

        agent = Agent(
            name="kidsvid",
            model=model,
            description=(
                "Children's video curator — searches YouTube for safe, educational, "
                "age-appropriate videos for kids. Handles all requests about finding "
                "videos for children, educational content, kids' shows, and learning videos."
            ),
            instruction=instruction,
            tools=tools,
        )

        logger.info(f"Created KidsVid agent with {len(tools)} tools")
        return agent

    except Exception as e:
        logger.error(f"Failed to create KidsVid agent: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None
