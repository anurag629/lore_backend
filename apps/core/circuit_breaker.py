"""
Circuit Breaker Pattern Implementation

Prevents cascading failures by temporarily blocking calls to failing services.
Useful for external services (IPFS, blockchain RPC, AI APIs) that may become unavailable.
"""
from typing import Callable, Optional, Any
from enum import Enum
import time
import logging
from functools import wraps
from threading import Lock

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"      # Too many failures, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures detected, requests are blocked
    - HALF_OPEN: After recovery timeout, allow test requests

    Args:
        name: Identifier for this circuit breaker
        failure_threshold: Number of failures before opening circuit (default: 5)
        recovery_timeout: Seconds before trying again after opening (default: 60)
        expected_exception: Exception type to count as failure (default: Exception)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        """Initialize circuit breaker."""
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED

        self._lock = Lock()

        logger.info(
            f"Circuit breaker '{name}' initialized: "
            f"threshold={failure_threshold}, timeout={recovery_timeout}s"
        )

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Call a function through the circuit breaker.

        Args:
            func: Function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by func
        """
        with self._lock:
            # Check current state
            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
                    self.state = CircuitState.HALF_OPEN
                else:
                    # Still in OPEN state, reject request
                    raise CircuitBreakerError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Service unavailable. Try again in "
                        f"{self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s"
                    )

        # Try to call the function
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result

        except self.expected_exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call"""
        with self._lock:
            self.success_count += 1

            if self.state == CircuitState.HALF_OPEN:
                # Successful test call, close the circuit
                logger.info(
                    f"Circuit breaker '{self.name}' closing after successful test call"
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.last_failure_time = None

            # Reset failure count after success in CLOSED state
            if self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def _on_failure(self):
        """Handle failed call"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Test call failed, reopen circuit
                logger.warning(
                    f"Circuit breaker '{self.name}' reopening after failed test call"
                )
                self.state = CircuitState.OPEN

            elif self.failure_count >= self.failure_threshold:
                # Too many failures, open circuit
                logger.error(
                    f"Circuit breaker '{self.name}' opening after "
                    f"{self.failure_count} consecutive failures"
                )
                self.state = CircuitState.OPEN

    def reset(self):
        """Manually reset the circuit breaker to CLOSED state"""
        with self._lock:
            logger.info(f"Circuit breaker '{self.name}' manually reset")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None

    @property
    def is_open(self) -> bool:
        """Check if circuit is open"""
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed"""
        return self.state == CircuitState.CLOSED

    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        with self._lock:
            return {
                'name': self.name,
                'state': self.state.value,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'failure_threshold': self.failure_threshold,
                'recovery_timeout': self.recovery_timeout,
                'last_failure_time': self.last_failure_time,
            }


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: type = Exception
):
    """
    Decorator to apply circuit breaker pattern to a function.

    Args:
        name: Identifier for this circuit breaker
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds before trying again after opening
        expected_exception: Exception type to count as failure

    Example:
        @circuit_breaker(
            name='ipfs_upload',
            failure_threshold=3,
            recovery_timeout=30.0
        )
        def upload_to_ipfs(file):
            # ... upload logic
            pass
    """
    # Create a shared circuit breaker instance for this decorator
    cb = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception
    )

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return cb.call(func, *args, **kwargs)

        # Attach circuit breaker instance to wrapper for introspection
        wrapper.circuit_breaker = cb
        return wrapper

    return decorator


# Registry of circuit breakers for monitoring
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: type = Exception
) -> CircuitBreaker:
    """
    Get or create a named circuit breaker.

    Useful for sharing circuit breakers across multiple function calls.

    Args:
        name: Identifier for this circuit breaker
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds before trying again after opening
        expected_exception: Exception type to count as failure

    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception
        )

    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers for monitoring"""
    return _circuit_breakers.copy()


def reset_all_circuit_breakers():
    """Reset all circuit breakers (useful for testing)"""
    for cb in _circuit_breakers.values():
        cb.reset()


# Common circuit breaker configurations
CIRCUIT_BREAKER_IPFS = {
    'name': 'ipfs',
    'failure_threshold': 3,
    'recovery_timeout': 30.0,
}

CIRCUIT_BREAKER_BLOCKCHAIN = {
    'name': 'blockchain_rpc',
    'failure_threshold': 5,
    'recovery_timeout': 60.0,
}

CIRCUIT_BREAKER_AI = {
    'name': 'ai_service',
    'failure_threshold': 3,
    'recovery_timeout': 45.0,
}
