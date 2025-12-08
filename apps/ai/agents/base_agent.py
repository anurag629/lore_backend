"""
Base Agent Class for AI Agents

Provides common functionality for all AI agents including:
- Standardized result format
- Error handling
- Logging
- Performance tracking
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """
    Standardized result format for all agents.

    Attributes:
        success: Whether the analysis completed successfully
        data: The analysis results (format varies by agent)
        confidence: Confidence score 0.0-1.0
        processing_time: Time taken in seconds
        errors: List of errors encountered
        warnings: List of warnings
        metadata: Additional metadata
    """
    success: bool
    data: Dict[str, Any]
    confidence: float = 1.0
    processing_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'data': self.data,
            'confidence': self.confidence,
            'processing_time': self.processing_time,
            'errors': self.errors,
            'warnings': self.warnings,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat(),
        }


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.

    All agents must implement:
    - analyze(): Core analysis method
    - get_name(): Agent name for logging
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize agent with optional configuration.

        Args:
            config: Agent-specific configuration
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.{self.get_name()}")

    @abstractmethod
    def analyze(self, **kwargs) -> AgentResult:
        """
        Perform analysis. Must be implemented by subclasses.

        Returns:
            AgentResult with analysis results
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the agent name."""
        pass

    def run(self, **kwargs) -> AgentResult:
        """
        Execute the agent with error handling and timing.

        This wrapper:
        - Tracks execution time
        - Handles errors gracefully
        - Logs execution details

        Args:
            **kwargs: Arguments passed to analyze()

        Returns:
            AgentResult with analysis results
        """
        agent_name = self.get_name()
        self.logger.info(f"Starting {agent_name} analysis")
        start_time = time.time()

        try:
            # Run the analysis
            result = self.analyze(**kwargs)

            # Update processing time
            result.processing_time = time.time() - start_time

            self.logger.info(
                f"{agent_name} completed in {result.processing_time:.2f}s "
                f"(confidence: {result.confidence:.2f})"
            )

            return result

        except Exception as e:
            # Handle errors gracefully
            processing_time = time.time() - start_time
            error_msg = f"{agent_name} failed: {str(e)}"

            self.logger.error(error_msg, exc_info=True)

            return AgentResult(
                success=False,
                data={},
                confidence=0.0,
                processing_time=processing_time,
                errors=[error_msg],
                metadata={'agent': agent_name}
            )

    def validate_input(self, required_fields: List[str], **kwargs) -> Optional[str]:
        """
        Validate required input fields.

        Args:
            required_fields: List of required field names
            **kwargs: Input data

        Returns:
            Error message if validation fails, None otherwise
        """
        missing = [field for field in required_fields if field not in kwargs or kwargs[field] is None]

        if missing:
            return f"Missing required fields: {', '.join(missing)}"

        return None
