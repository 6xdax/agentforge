"""Error classes and retry utilities for agentcore."""

import random
import time
from typing import Callable, Any


class ToolError(Exception):
    """Base exception for tool errors."""
    pass


class ToolNotFoundError(ToolError):
    """Raised when tool name is not found in registry."""
    pass


class MaxIterationsError(Exception):
    """Raised when max iterations reached."""
    pass


def jittered_backoff(
    attempt: int,
    base: float = 1.0,
    max_delay: float = 60.0,
    jitter: float = 0.1,
) -> float:
    """Exponential backoff with random jitter.
    
    Args:
        attempt: Current attempt number (0-indexed)
        base: Base delay in seconds
        max_delay: Maximum delay cap
        jitter: Jitter factor (0.1 = 10% random variation)
    
    Returns:
        Delay in seconds before next retry
    """
    delay = min(base * (2 ** attempt), max_delay)
    jitter_amount = delay * jitter * random.uniform(-1, 1)
    return max(0, delay + jitter_amount)


def retry_with_backoff(
    fn: Callable[[], Any],
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Retry a function with exponential backoff.
    
    Args:
        fn: Function to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds
    
    Returns:
        Result of successful function call
    
    Raises:
        Last exception if all attempts fail
    """
    last_error = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(jittered_backoff(attempt, base=base_delay))
    raise last_error
