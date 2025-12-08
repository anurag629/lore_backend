"""
Retry Logic Utilities

Provides configurable retry decorators with exponential backoff for handling
transient failures in external service calls (IPFS, blockchain, APIs).
"""
from typing import Callable, Type, Tuple, Optional, Any
from functools import wraps
import time
import logging
import random

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        exponential_base: float = 2.0,
        max_delay: float = 60.0,
        jitter: bool = True
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts (default: 3)
            base_delay: Initial delay in seconds before first retry (default: 1.0)
            exponential_base: Base for exponential backoff calculation (default: 2.0)
            max_delay: Maximum delay between retries in seconds (default: 60.0)
            jitter: Whether to add random jitter to delays (default: True)
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if base_delay < 0:
            raise ValueError("base_delay must be non-negative")
        if exponential_base < 1:
            raise ValueError("exponential_base must be at least 1")
        if max_delay < base_delay:
            raise ValueError("max_delay must be >= base_delay")

        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.exponential_base = exponential_base
        self.max_delay = max_delay
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number using exponential backoff.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Calculate exponential delay: base_delay * (exponential_base ^ attempt)
        delay = self.base_delay * (self.exponential_base ** attempt)

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        if self.jitter:
            # Random jitter between 0% and 25% of the delay
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount

        return delay


def retry_with_backoff(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int, float], None]] = None
):
    """
    Decorator to retry a function with exponential backoff on specific exceptions.

    Args:
        exceptions: Tuple of exception types to catch and retry on
        config: RetryConfig instance (uses default if not provided)
        on_retry: Optional callback function(exception, attempt, delay) called before each retry

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(
            exceptions=(requests.RequestException, TimeoutError),
            config=RetryConfig(max_attempts=5, base_delay=2.0)
        )
        def upload_to_ipfs(file_data):
            # ... upload logic
            pass
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    # Attempt the function call
                    result = func(*args, **kwargs)

                    # Log success if this wasn't the first attempt
                    if attempt > 0:
                        logger.info(
                            f"{func.__name__} succeeded on attempt {attempt + 1}/{config.max_attempts}"
                        )

                    return result

                except exceptions as e:
                    last_exception = e

                    # Check if we have more attempts left
                    if attempt < config.max_attempts - 1:
                        delay = config.calculate_delay(attempt)

                        logger.warning(
                            f"{func.__name__} failed on attempt {attempt + 1}/{config.max_attempts}: "
                            f"{type(e).__name__}: {str(e)}. Retrying in {delay:.2f}s..."
                        )

                        # Call optional callback
                        if on_retry:
                            try:
                                on_retry(e, attempt + 1, delay)
                            except Exception as callback_error:
                                logger.error(f"Error in on_retry callback: {callback_error}")

                        # Wait before retrying
                        time.sleep(delay)
                    else:
                        # No more attempts left
                        logger.error(
                            f"{func.__name__} failed after {config.max_attempts} attempts: "
                            f"{type(e).__name__}: {str(e)}"
                        )

            # All attempts exhausted, raise the last exception
            raise last_exception

        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry logic with exponential backoff.

    Useful when you need more control than the decorator provides.

    Example:
        retry = RetryContext(
            exceptions=(RequestException,),
            config=RetryConfig(max_attempts=3)
        )

        for attempt in retry:
            try:
                with attempt:
                    result = risky_operation()
                    break  # Success, exit retry loop
            except RequestException as e:
                if retry.should_retry:
                    continue
                else:
                    raise
    """

    def __init__(
        self,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        config: Optional[RetryConfig] = None
    ):
        """
        Initialize retry context.

        Args:
            exceptions: Tuple of exception types to catch and retry on
            config: RetryConfig instance (uses default if not provided)
        """
        self.exceptions = exceptions
        self.config = config or RetryConfig()
        self.attempt = 0
        self.last_exception = None

    def __iter__(self):
        """Iterate over retry attempts."""
        self.attempt = 0
        return self

    def __next__(self):
        """Get next retry attempt."""
        if self.attempt >= self.config.max_attempts:
            raise StopIteration

        self.attempt += 1
        return self

    @property
    def should_retry(self) -> bool:
        """Check if we should retry after current attempt."""
        return self.attempt < self.config.max_attempts

    def __enter__(self):
        """Enter context for current attempt."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and handle retry logic."""
        # If no exception or not a retryable exception, don't retry
        if exc_type is None or not issubclass(exc_type, self.exceptions):
            return False

        self.last_exception = exc_val

        # If we have more attempts, sleep and continue
        if self.should_retry:
            delay = self.config.calculate_delay(self.attempt - 1)

            logger.warning(
                f"Attempt {self.attempt}/{self.config.max_attempts} failed: "
                f"{exc_type.__name__}: {str(exc_val)}. Retrying in {delay:.2f}s..."
            )

            time.sleep(delay)
            return True  # Suppress the exception
        else:
            # No more attempts, let exception propagate
            logger.error(
                f"All {self.config.max_attempts} attempts failed: "
                f"{exc_type.__name__}: {str(exc_val)}"
            )
            return False


# Common retry configurations
RETRY_CONFIG_AGGRESSIVE = RetryConfig(
    max_attempts=5,
    base_delay=1.0,
    exponential_base=2.0,
    max_delay=30.0
)

RETRY_CONFIG_MODERATE = RetryConfig(
    max_attempts=3,
    base_delay=2.0,
    exponential_base=2.0,
    max_delay=60.0
)

RETRY_CONFIG_CONSERVATIVE = RetryConfig(
    max_attempts=2,
    base_delay=3.0,
    exponential_base=1.5,
    max_delay=60.0
)
