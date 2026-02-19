"""
Sequential Thinking module for the Research Agent.

This module implements a sequential thinking approach inspired by the MCP
Sequential Thinking server (https://github.com/modelcontextprotocol/servers/blob/main/src/sequentialthinking/index.ts)
to help the agent break down complex problems into steps and work through them logically.
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ThoughtStep:
    """Represents a single step in the sequential thinking process."""

    def __init__(
        self,
        content: str,
        step_number: int,
        branch_from: Optional[int] = None,
        is_revision: bool = False,
    ):
        """
        Initialize a thought step.

        Args:
            content: The content of the thought
            step_number: The sequential number of this thought
            branch_from: If this is a branch, the step it branches from
            is_revision: Whether this thought revises a previous one
        """
        self.content = content
        self.step_number = step_number
        self.branch_from = branch_from
        self.is_revision = is_revision
        self.timestamp = None  # Can be added if needed

    def __str__(self) -> str:
        prefix = "REVISION - " if self.is_revision else ""
        branch_info = (
            f" (branch from step {self.branch_from})"
            if self.branch_from is not None
            else ""
        )
        return f"Step {self.step_number}{branch_info}: {prefix}{self.content}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_number": self.step_number,
            "content": self.content,
            "branch_from": self.branch_from,
            "is_revision": self.is_revision,
            "timestamp": self.timestamp,
        }


class SequentialThinking:
    """
    Implements a flexible sequential thinking process that can adapt and evolve.

    This class helps break down complex problems into steps and allows for:
    - Sequential thinking steps
    - Revising previous thoughts
    - Branching into alternative lines of reasoning
    - Dynamic adjustment of thinking steps
    """

    def __init__(self, max_steps: int = 10):
        """
        Initialize the sequential thinking process.

        Args:
            max_steps: Maximum number of thinking steps allowed
        """
        self.thoughts: List[ThoughtStep] = []
        self.max_steps = max_steps
        self.current_step = 0
        self.complete = False
        self.conclusion: Optional[str] = None

    def add_thought(
        self,
        content: str,
        revise_step: Optional[int] = None,
        branch_from: Optional[int] = None,
    ) -> ThoughtStep:
        """
        Add a new thought to the sequence.

        Args:
            content: The content of the thought
            revise_step: If provided, this thought revises the specified step
            branch_from: If provided, this thought branches from the specified step

        Returns:
            The created thought step
        """
        # Handle revision
        is_revision = revise_step is not None

        if is_revision and revise_step < len(self.thoughts):
            # Remove all thoughts after the revised one
            self.thoughts = self.thoughts[:revise_step]
            self.current_step = revise_step

        # Create new thought
        self.current_step += 1
        thought = ThoughtStep(
            content=content,
            step_number=self.current_step,
            branch_from=branch_from,
            is_revision=is_revision,
        )

        self.thoughts.append(thought)
        return thought

    def set_conclusion(self, conclusion: str) -> None:
        """
        Set the final conclusion of the thinking process.

        Args:
            conclusion: The conclusion text
        """
        self.conclusion = conclusion
        self.complete = True

    def get_formatted_thoughts(self) -> str:
        """
        Get a formatted string representation of all thoughts.

        Returns:
            A formatted string with numbered thought steps
        """
        result = "# Sequential Thinking Process\n\n"

        for thought in self.thoughts:
            result += f"{str(thought)}\n\n"

        if self.conclusion:
            result += f"\n## Conclusion\n{self.conclusion}\n"

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "thoughts": [t.to_dict() for t in self.thoughts],
            "current_step": self.current_step,
            "complete": self.complete,
            "conclusion": self.conclusion,
            "max_steps": self.max_steps,
        }


def detect_thinking_trigger(prompt: str) -> bool:
    """
    Detect if the prompt should trigger sequential thinking.

    Args:
        prompt: The user's input prompt

    Returns:
        True if sequential thinking should be triggered
    """
    # Look for explicit "think" keyword
    thinking_patterns = [
        r"\bthink\b",
        r"\bthink through\b",
        r"\bthink about\b",
        r"\bstep by step\b",
        r"\bthinking process\b",
        r"\breason through\b",
    ]

    for pattern in thinking_patterns:
        if re.search(pattern, prompt.lower()):
            return True

    return False


def process_thinking(
    prompt: str, model_fn: Callable[[str], str], max_steps: int = 6
) -> Dict[str, Any]:
    """
    Process a thinking request by breaking it down into steps.

    Args:
        prompt: The user's input prompt
        model_fn: A function that takes a prompt and returns a model response
        max_steps: Maximum number of thinking steps

    Returns:
        A dictionary with the thinking process results
    """
    thinking = SequentialThinking(max_steps=max_steps)

    # Initial system prompt for thinking
    system_prompt = f"""
    I'll help you think through this problem step by step.
    
    The problem to solve is: {prompt}
    
    Break this down into logical steps. For each step:
    1. Think carefully about the current stage of reasoning
    2. Consider what information you have and what you need
    3. Identify any assumptions you're making
    4. Determine what follows logically from your current understanding
    
    Start with "Step 1:" and proceed through each step of reasoning.
    After you've thought through the steps, provide a final conclusion.
    
    Format your response like this:
    
    Step 1: [Your first step of reasoning]
    
    Step 2: [Your second step of reasoning]
    
    ...
    
    Conclusion: [Your final answer or conclusion]
    """

    # Get initial thinking process
    thinking_response = model_fn(system_prompt)

    # Extract steps and conclusion using regex
    step_pattern = r"Step (\d+):(.*?)(?=Step \d+:|Conclusion:|$)"
    conclusion_pattern = r"Conclusion:(.*?)(?=$)"

    steps = re.findall(step_pattern, thinking_response, re.DOTALL)
    conclusions = re.findall(conclusion_pattern, thinking_response, re.DOTALL)

    # Add each step to the thinking process
    for step_num, content in steps:
        thinking.add_thought(content.strip())

    # Add conclusion if found
    if conclusions:
        thinking.set_conclusion(conclusions[0].strip())

    return {
        "thinking_process": thinking.get_formatted_thoughts(),
        "structured_thinking": thinking.to_dict(),
        "raw_response": thinking_response,
    }
