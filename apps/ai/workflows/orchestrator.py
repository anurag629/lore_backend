"""
Agent Orchestration System

Coordinates multiple AI agents to execute complex workflows.
"""
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import time

from apps.ai.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """
    Represents a single step in a workflow.

    Attributes:
        agent_name: Name of the agent to run
        description: Human-readable description
        required: Whether this step must succeed
        condition: Optional function to determine if step should run
        timeout: Maximum execution time in seconds
    """
    agent_name: str
    description: str
    required: bool = True
    condition: Optional[Callable[[Dict[str, Any], Dict[str, AgentResult]], bool]] = None
    timeout: int = 60


@dataclass
class WorkflowResult:
    """
    Result of executing a workflow.

    Attributes:
        success: Whether workflow completed successfully
        steps_completed: List of completed step names
        agent_results: Results from each agent
        total_time: Total execution time
        errors: List of errors
        warnings: List of warnings
    """
    success: bool
    steps_completed: List[str] = field(default_factory=list)
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)
    total_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'steps_completed': self.steps_completed,
            'agent_results': {
                name: result.to_dict()
                for name, result in self.agent_results.items()
            },
            'total_time': self.total_time,
            'errors': self.errors,
            'warnings': self.warnings,
        }


class Workflow:
    """
    Defines a multi-agent workflow.

    Workflows consist of ordered steps that execute agents in sequence,
    with optional conditional logic and error handling.
    """

    def __init__(
        self,
        name: str,
        steps: List[WorkflowStep],
        description: str = ""
    ):
        """
        Initialize workflow.

        Args:
            name: Workflow name
            steps: List of workflow steps
            description: Human-readable description
        """
        self.name = name
        self.steps = steps
        self.description = description

    def execute(
        self,
        orchestrator: 'AgentOrchestrator',
        input_data: Dict[str, Any]
    ) -> WorkflowResult:
        """
        Execute the workflow.

        Args:
            orchestrator: The orchestrator managing agents
            input_data: Input data for the workflow

        Returns:
            WorkflowResult with execution results
        """
        logger.info(f"Starting workflow: {self.name}")
        start_time = time.time()

        result = WorkflowResult(success=True)
        agent_results = {}

        for step in self.steps:
            step_name = f"{step.agent_name}:{step.description}"

            # Check if step should run based on condition
            if step.condition and not step.condition(input_data, agent_results):
                logger.info(f"Skipping step {step_name} (condition not met)")
                result.warnings.append(f"Skipped {step_name}: condition not met")
                continue

            # Execute the step
            logger.info(f"Executing step: {step_name}")

            try:
                step_result = orchestrator.run_agent(
                    step.agent_name,
                    **input_data
                )

                agent_results[step.agent_name] = step_result
                result.agent_results[step.agent_name] = step_result
                result.steps_completed.append(step.agent_name)

                # Check if step succeeded
                if not step_result.success:
                    error_msg = f"Step {step_name} failed: {', '.join(step_result.errors)}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)

                    if step.required:
                        result.success = False
                        break
                else:
                    logger.info(
                        f"Step {step_name} completed successfully "
                        f"(confidence: {step_result.confidence:.2f})"
                    )

                # Collect warnings
                if step_result.warnings:
                    result.warnings.extend(step_result.warnings)

            except Exception as e:
                error_msg = f"Step {step_name} raised exception: {str(e)}"
                logger.error(error_msg, exc_info=True)
                result.errors.append(error_msg)

                if step.required:
                    result.success = False
                    break

        result.total_time = time.time() - start_time
        logger.info(
            f"Workflow {self.name} completed in {result.total_time:.2f}s "
            f"(success: {result.success}, steps: {len(result.steps_completed)})"
        )

        return result


class AgentOrchestrator:
    """
    Orchestrates multiple AI agents and manages workflows.

    Provides a centralized registry for agents and workflows,
    and handles their execution.
    """

    def __init__(self):
        """Initialize the orchestrator."""
        self.agents: Dict[str, BaseAgent] = {}
        self.workflows: Dict[str, Workflow] = {}
        self.logger = logging.getLogger(__name__)

    def register_agent(self, name: str, agent: BaseAgent) -> None:
        """
        Register an agent with the orchestrator.

        Args:
            name: Agent name (used for lookup)
            agent: Agent instance
        """
        self.agents[name] = agent
        self.logger.info(f"Registered agent: {name}")

    def register_workflow(self, workflow: Workflow) -> None:
        """
        Register a workflow with the orchestrator.

        Args:
            workflow: Workflow instance
        """
        self.workflows[workflow.name] = workflow
        self.logger.info(f"Registered workflow: {workflow.name}")

    def run_agent(self, agent_name: str, **kwargs) -> AgentResult:
        """
        Run a single agent.

        Args:
            agent_name: Name of the agent to run
            **kwargs: Arguments to pass to the agent

        Returns:
            AgentResult from the agent

        Raises:
            ValueError: If agent not found
        """
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not registered")

        agent = self.agents[agent_name]
        return agent.run(**kwargs)

    def run_workflow(
        self,
        workflow_name: str,
        input_data: Dict[str, Any]
    ) -> WorkflowResult:
        """
        Run a workflow by name.

        Args:
            workflow_name: Name of the workflow to run
            input_data: Input data for the workflow

        Returns:
            WorkflowResult with execution results

        Raises:
            ValueError: If workflow not found
        """
        if workflow_name not in self.workflows:
            raise ValueError(f"Workflow '{workflow_name}' not registered")

        workflow = self.workflows[workflow_name]
        return workflow.execute(self, input_data)

    def get_available_agents(self) -> List[str]:
        """
        Get list of registered agent names.

        Returns:
            List of agent names
        """
        return list(self.agents.keys())

    def get_available_workflows(self) -> List[str]:
        """
        Get list of registered workflow names.

        Returns:
            List of workflow names
        """
        return list(self.workflows.keys())
