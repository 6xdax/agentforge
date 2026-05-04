"""Re-export SlidingWindowMemory from agent.memory."""

# This module exists for backwards compatibility.
# New code should import from agent directly:
#   from agent import SlidingWindowMemory

from agent.memory import SlidingWindowMemory

__all__ = ["SlidingWindowMemory"]
