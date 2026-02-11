"""
ExecutionAgent implementation for Axel.

This module provides the ExecutionAgent class that implements the Axel agent,
specialized for execution tasks and implementing specifications from Scout.
"""

import asyncio
import logging
import secrets
from typing import Any, ClassVar, Dict, List, Optional, Union

from google.adk.agents import BaseAgent, ParallelAgent
from google.adk.events import Event, EventActions
from google.genai import types

from radbot.agent.execution_agent.models import (
    TaskInstruction,
    TaskResult,
    TaskStatus,
    TaskType,
)

# Set up logging
logger = logging.getLogger(__name__)


class WorkerAgent(BaseAgent):
    """Worker agent that executes a specific task."""

    def __init__(self, *, name: str, task_id: str, task_instruction: TaskInstruction):
        """
        Initialize a worker agent.

        Args:
            name: Unique name for this worker agent
            task_id: ID of the task this agent will execute
            task_instruction: Detailed instructions for the task
        """
        super().__init__(name=name)
        self._task_id = task_id
        self._task_instruction = task_instruction

    async def _run_async_impl(self, ctx):
        """
        Run the worker agent implementation.

        Args:
            ctx: The execution context

        Yields:
            Event: Worker agent events
        """
        # Initialize with a status event
        yield Event(
            author=self.name,
            content=types.Content(
                role="assistant",
                parts=[
                    types.Part(
                        text=f"Starting task {self._task_id} of type {self._task_instruction.task_type}"
                    )
                ],
            ),
        )

        # Execute with timeout protection
        try:
            result = await asyncio.wait_for(
                self._execute_task(self._task_instruction),
                timeout=15 * 60,  # 15 minutes
            )
        except asyncio.TimeoutError:
            logger.error(f"Worker {self.name} timed out on task {self._task_id}")
            result = TaskResult(
                task_id=self._task_id,
                task_type=self._task_instruction.task_type,
                status=TaskStatus.FAILED,
                summary="Task execution timed out after 15 minutes",
                details="The worker agent did not complete within the allocated time limit.",
                error_message="Execution timeout (15 minutes)",
            )
        except Exception as e:
            logger.error(f"Worker {self.name} failed on task {self._task_id}: {str(e)}")
            result = TaskResult(
                task_id=self._task_id,
                task_type=self._task_instruction.task_type,
                status=TaskStatus.FAILED,
                summary=f"Task execution failed with error: {str(e)}",
                details=f"Error details: {str(e)}",
                error_message=str(e),
            )

        # Store result in state
        result_key = f"result:{self._task_id}"
        ctx.session.state[result_key] = result

        # Return completion event with state delta
        yield Event(
            author=self.name,
            content=types.Content(
                role="assistant",
                parts=[
                    types.Part(
                        text=f"Completed task {self._task_id} with status: {result.status}"
                    )
                ],
            ),
            actions=EventActions(state_delta={"task_completed": True}),
        )

    async def _execute_task(self, task_instruction: TaskInstruction) -> TaskResult:
        """
        Execute the specific task based on instruction type.

        Args:
            task_instruction: The task instructions

        Returns:
            TaskResult: The result of the task execution

        Raises:
            ValueError: If the task type is unknown
        """
        if task_instruction.task_type == TaskType.CODE_IMPLEMENTATION:
            return await self._execute_implementation_task(task_instruction)
        elif task_instruction.task_type == TaskType.DOCUMENTATION:
            return await self._execute_documentation_task(task_instruction)
        elif task_instruction.task_type == TaskType.TESTING:
            return await self._execute_testing_task(task_instruction)
        else:
            raise ValueError(f"Unknown task type: {task_instruction.task_type}")

    async def _execute_implementation_task(
        self, task_instruction: TaskInstruction
    ) -> TaskResult:
        """
        Execute a code implementation task.

        Args:
            task_instruction: The task instructions

        Returns:
            TaskResult: The result of the implementation task
        """
        # Implementation-specific logic
        # Use LLM to process the specification and generate code
        # This is a placeholder implementation
        return TaskResult(
            task_id=task_instruction.task_id,
            task_type=task_instruction.task_type,
            status=TaskStatus.COMPLETED,
            summary="Implemented code according to specification",
            details="Detailed implementation report...",
            artifacts={"implementation.py": "# Generated code..."},
        )

    async def _execute_documentation_task(
        self, task_instruction: TaskInstruction
    ) -> TaskResult:
        """
        Execute a documentation task.

        Args:
            task_instruction: The task instructions

        Returns:
            TaskResult: The result of the documentation task
        """
        # Documentation-specific logic
        # This is a placeholder implementation
        return TaskResult(
            task_id=task_instruction.task_id,
            task_type=task_instruction.task_type,
            status=TaskStatus.COMPLETED,
            summary="Created documentation according to specification",
            details="Detailed documentation report...",
            artifacts={"README.md": "# Documentation..."},
        )

    async def _execute_testing_task(
        self, task_instruction: TaskInstruction
    ) -> TaskResult:
        """
        Execute a testing task.

        Args:
            task_instruction: The task instructions

        Returns:
            TaskResult: The result of the testing task
        """
        # Testing-specific logic
        # This is a placeholder implementation
        return TaskResult(
            task_id=task_instruction.task_id,
            task_type=task_instruction.task_type,
            status=TaskStatus.COMPLETED,
            summary="Created tests according to specification",
            details="Detailed testing report...",
            artifacts={"test_implementation.py": "# Test code..."},
        )


class ExecutionAgent:
    """
    Agent specialized in executing and implementing specifications.

    This agent is the implementation-focused counterpart to the Scout agent.
    While Scout focuses on research and design, Axel focuses on execution
    and implementation of the designs created by Scout.
    """

    def __init__(
        self,
        name: str = "axel",
        model: Optional[str] = None,
        instruction: Optional[str] = None,
        description: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        enable_code_execution: bool = True,
        app_name: str = "beto",
        agent_factory: Optional[Any] = None,
    ):
        """
        Initialize the execution agent.

        Args:
            name: Name of the agent (should be "axel" for consistent transfers)
            model: LLM model to use
            instruction: Custom instruction for this agent
            description: Description of this agent's capabilities
            tools: List of tools available to this agent
            enable_code_execution: Whether to enable code execution
            app_name: Application name for ADK integration
            agent_factory: Optional agent factory for creating the underlying agent
        """
        self.name = name
        self.model = model
        self.instruction = instruction
        self.description = (
            description or "Execution agent specialized in implementing specifications"
        )
        self.tools = tools or []
        self.enable_code_execution = enable_code_execution
        self.app_name = app_name
        self.agent_factory = agent_factory

        # The underlying ADK agent
        self._adk_agent = None

        # List of agents this agent can transfer to
        self.allowed_transfer_targets = []

    def create_adk_agent(self):
        """
        Create the underlying ADK agent.

        Returns:
            BaseAgent: The created ADK agent
        """
        if self._adk_agent is not None:
            return self._adk_agent

        if self.agent_factory:
            # Use the factory to create the agent
            self._adk_agent = self.agent_factory.create_axel_agent(
                name=self.name,
                model=self.model,
                tools=self.tools,
                instruction=self.instruction,
                app_name=self.app_name,
            )
        else:
            # Create a basic ADK agent
            # This is a simplified implementation
            # The full implementation would create an AxelExecutionAgent
            self._adk_agent = BaseAgent(
                name=self.name,
                model=self.model,
                instruction=self.instruction,
                tools=self.tools,
            )

        return self._adk_agent

    def add_specific_transfer_target(self, agent):
        """
        Add a specific agent that this agent can transfer to.

        Args:
            agent: The agent this agent can transfer to
        """
        self.allowed_transfer_targets.append(agent)
        logger.info(f"Added {agent.name} as a specific transfer target for {self.name}")

    def can_transfer_to(self, agent_name):
        """
        Check if this agent can transfer to the specified agent.

        Args:
            agent_name: Name of the agent to check

        Returns:
            bool: True if this agent can transfer to the specified agent
        """
        # Can always transfer back to parent if we have one
        if (
            hasattr(self, "parent_agent")
            and self.parent_agent
            and self.parent_agent.name == agent_name
        ):
            return True

        # Check specific allowed targets
        for agent in self.allowed_transfer_targets:
            if agent.name == agent_name:
                return True

        return False


class AxelExecutionAgent(BaseAgent):
    """
    Axel agent that can dynamically spawn worker agents.

    This is the ADK implementation of the Axel execution agent,
    which can create and manage worker agents for parallel task execution.
    """

    # Class constants
    MAX_WORKERS: ClassVar[int] = 3
    WORKER_TIMEOUT_MS: ClassVar[int] = 15 * 60 * 1000  # 15 minutes

    async def _run_async_impl(self, ctx):
        """
        Run the Axel execution agent implementation.

        Args:
            ctx: The execution context

        Yields:
            Event: Agent events
        """
        # Extract the specification from the request
        specification = self._extract_specification(ctx.request)

        # Create an execution ID for this run
        execution_id = secrets.token_hex(4)

        # Divide the work into tasks
        tasks = await self._divide_work(specification)

        # Limit to MAX_WORKERS
        if len(tasks) > self.MAX_WORKERS:
            tasks = self._prioritize_tasks(tasks)[: self.MAX_WORKERS]

        # Create worker agents
        workers = []
        for i, task in enumerate(tasks):
            worker = WorkerAgent(
                name=f"thing{i}", task_id=task.task_id, task_instruction=task
            )
            workers.append(worker)

        # Yield initial event
        yield Event(
            author=self.name,
            content=types.Content(
                role="assistant",
                parts=[
                    types.Part(text=f"Starting execution with {len(workers)} workers")
                ],
            ),
        )

        # Create a ParallelAgent with these workers
        parallel_executor = ParallelAgent(
            name=f"axel_executor_{execution_id}", sub_agents=workers
        )

        # Execute all workers in parallel with progress tracking
        completed = 0
        failed_tasks = []

        # Run the parallel executor
        async for event in parallel_executor.run_async(ctx):
            # Forward events
            yield Event(
                author=self.name,
                content=types.Content(
                    role="assistant",
                    parts=[types.Part(text=f"Worker progress: {event.content}")],
                ),
            )

            # Check for completion events
            if (
                hasattr(event, "actions")
                and hasattr(event.actions, "state_delta")
                and event.actions.state_delta
                and "task_completed" in event.actions.state_delta
            ):
                completed += 1
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="assistant",
                        parts=[
                            types.Part(
                                text=f"Progress: {completed}/{len(workers)} tasks completed"
                            )
                        ],
                    ),
                )

        # Collect results
        results = []
        for worker in workers:
            result_key = f"result:{worker._task_id}"
            if result_key in ctx.session.state:
                result = ctx.session.state[result_key]
                results.append(result)
                if result.status == TaskStatus.FAILED:
                    failed_tasks.append(result)

        # Handle failures if any
        if failed_tasks:
            failure_report = await self._handle_failures(failed_tasks)
            yield Event(
                author=self.name,
                content=types.Content(
                    role="assistant", parts=[types.Part(text=failure_report)]
                ),
            )

        # Aggregate results
        final_summary = await self._aggregate_results(results)

        # Return final summary
        yield Event(
            author=self.name,
            content=types.Content(
                role="assistant", parts=[types.Part(text=final_summary)]
            ),
        )

    async def _divide_work(self, specification: str) -> List[TaskInstruction]:
        """
        Divide work from specification into domain-specific tasks.

        Args:
            specification: The markdown specification to divide

        Returns:
            List[TaskInstruction]: The divided work tasks
        """
        tasks = []

        # Create implementation task
        tasks.append(
            TaskInstruction(
                task_id=f"impl_{secrets.token_hex(4)}",
                task_type=TaskType.CODE_IMPLEMENTATION,
                specification=self._extract_implementation_specs(specification),
                context={},
            )
        )

        # Create documentation task
        tasks.append(
            TaskInstruction(
                task_id=f"docs_{secrets.token_hex(4)}",
                task_type=TaskType.DOCUMENTATION,
                specification=self._extract_documentation_specs(specification),
                context={},
            )
        )

        # Create testing task
        tasks.append(
            TaskInstruction(
                task_id=f"test_{secrets.token_hex(4)}",
                task_type=TaskType.TESTING,
                specification=self._extract_testing_specs(specification),
                context={},
            )
        )

        return tasks

    def _prioritize_tasks(self, tasks: List[TaskInstruction]) -> List[TaskInstruction]:
        """
        Prioritize tasks if we exceed MAX_WORKERS.

        Args:
            tasks: The tasks to prioritize

        Returns:
            List[TaskInstruction]: The prioritized tasks
        """
        # For now, just return the first MAX_WORKERS tasks
        # This could be extended with more sophisticated prioritization
        return tasks[: self.MAX_WORKERS]

    def _extract_specification(self, request) -> str:
        """
        Extract the specification from the user request.

        Args:
            request: The user request

        Returns:
            str: The extracted specification
        """
        # Implementation depends on request format
        # Return the markdown specification text
        return request.content.text

    def _extract_implementation_specs(self, specification: str) -> str:
        """
        Extract implementation-specific parts of the specification.

        Args:
            specification: The full specification

        Returns:
            str: The implementation-specific parts
        """
        # Implementation-specific logic to extract relevant parts
        # Could use LLM to intelligently divide the spec
        return specification

    def _extract_documentation_specs(self, specification: str) -> str:
        """
        Extract documentation-specific parts of the specification.

        Args:
            specification: The full specification

        Returns:
            str: The documentation-specific parts
        """
        # Documentation-specific logic to extract relevant parts
        return specification

    def _extract_testing_specs(self, specification: str) -> str:
        """
        Extract testing-specific parts of the specification.

        Args:
            specification: The full specification

        Returns:
            str: The testing-specific parts
        """
        # Testing-specific logic to extract relevant parts
        return specification

    async def _handle_failures(self, failed_tasks: List[TaskResult]) -> str:
        """
        Handle and report failed tasks.

        Args:
            failed_tasks: The list of failed tasks

        Returns:
            str: The failure report
        """
        failure_report = "## Task Execution Failures\n\n"

        for task in failed_tasks:
            failure_report += f"### Failed Task: {task.task_id}\n"
            failure_report += f"**Type:** {task.task_type}\n"
            failure_report += f"**Error:** {task.error_message}\n\n"
            failure_report += "**Instructions that failed:**\n```\n"
            failure_report += task.details + "\n```\n\n"

        return failure_report

    async def _aggregate_results(self, results: List[TaskResult]) -> str:
        """
        Aggregate results from all workers into a comprehensive summary.

        Args:
            results: The list of task results

        Returns:
            str: The aggregated results summary
        """
        summary = "# Execution Summary\n\n"

        # Group results by task type
        by_type = {}
        for result in results:
            if result.task_type not in by_type:
                by_type[result.task_type] = []
            by_type[result.task_type].append(result)

        # Summarize each task type
        for task_type, type_results in by_type.items():
            summary += f"## {task_type} Results\n\n"

            for result in type_results:
                summary += f"### {result.task_id}\n"
                summary += f"{result.summary}\n\n"

            # Add overall summary for this type
            summary += f"**Overall {task_type} progress:** "
            summary += f"{len([r for r in type_results if r.status == TaskStatus.COMPLETED])} completed, "
            summary += f"{len([r for r in type_results if r.status == TaskStatus.FAILED])} failed, "
            summary += f"{len([r for r in type_results if r.status == TaskStatus.PARTIAL])} partial\n\n"

        return summary
