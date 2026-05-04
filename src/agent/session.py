"""Session management for tracking token usage across multiple agent conversations."""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator
import time

from .usage import UsageTracker, TokenUsage, TokenPricing


@dataclass
class TurnRecord:
    """A single turn (user message + assistant response) in a session."""
    turn_id: int
    timestamp: float
    user_message: str
    assistant_message: str
    usage: TokenUsage
    cost: float


@dataclass
class ConversationRecord:
    """A conversation (one run() call) within a session."""
    conversation_id: int
    turns: list[TurnRecord] = field(default_factory=list)
    total_usage: TokenUsage = field(default_factory=TokenUsage)
    total_cost: float = 0.0

    def add_turn(self, turn: TurnRecord) -> None:
        self.turns.append(turn)
        self.total_usage.input_tokens += turn.usage.input_tokens
        self.total_usage.output_tokens += turn.usage.output_tokens
        self.total_usage.cache_write_tokens += turn.usage.cache_write_tokens
        self.total_usage.cache_read_tokens += turn.usage.cache_read_tokens
        self.total_cost += turn.cost


class Session:
    """Session wrapper around Agent that tracks token usage per conversation.

    Automatically snapshots tracker before/after each run() to calculate
    per-turn token usage and cost.

    Usage:
        from agent import Session
        from providers.minimax import MiniMaxProvider

        provider = MiniMaxProvider()
        agent = Agent(provider=provider)
        session = Session(agent)

        result = await session.run("What is 2 + 2?")
        result = await session.run("What is 3 + 3?")

        session.print_summary()
    """

    def __init__(
        self,
        agent,
        tracker: Optional[UsageTracker] = None,
        provider_name: str = "minimax",
    ):
        self.agent = agent
        self.provider_name = provider_name
        # Use provided tracker or import global tracker
        if tracker is None:
            from .usage import tracker as global_tracker
            self.tracker = global_tracker
        else:
            self.tracker = tracker
        self.conversations: list[ConversationRecord] = []
        self._current_conversation: Optional[ConversationRecord] = None
        self._turn_count: int = 0

    def _snapshot_usage(self) -> TokenUsage:
        """Get current total usage snapshot from tracker."""
        summary = self.tracker.summary()
        provider_stats = summary.get(self.provider_name, {})
        return TokenUsage(
            input_tokens=provider_stats.get("input_tokens", 0),
            output_tokens=provider_stats.get("output_tokens", 0),
            cache_write_tokens=provider_stats.get("cache_write_tokens", 0),
            cache_read_tokens=provider_stats.get("cache_read_tokens", 0),
        )

    def _diff_usage(self, before: TokenUsage, after: TokenUsage) -> TokenUsage:
        """Calculate diff between two usage snapshots."""
        return TokenUsage(
            input_tokens=after.input_tokens - before.input_tokens,
            output_tokens=after.output_tokens - before.output_tokens,
            cache_write_tokens=after.cache_write_tokens - before.cache_write_tokens,
            cache_read_tokens=after.cache_read_tokens - before.cache_read_tokens,
        )

    def _calculate_cost(self, usage: TokenUsage) -> float:
        """Calculate cost for given usage against tracker pricing."""
        pricing = self.tracker._pricing.get(self.provider_name, TokenPricing())
        return (
            usage.input_tokens * pricing.input / 1000
            + usage.output_tokens * pricing.output / 1000
            + usage.cache_write_tokens * pricing.cache_write / 1000
            + usage.cache_read_tokens * pricing.cache_read / 1000
        )

    def start_conversation(self) -> None:
        """Start a new conversation within the session."""
        conv_id = len(self.conversations)
        self._current_conversation = ConversationRecord(conversation_id=conv_id)

    def end_conversation(self) -> Optional[ConversationRecord]:
        """End the current conversation."""
        if self._current_conversation is None:
            return None

        conv = self._current_conversation
        self.conversations.append(conv)
        self._current_conversation = None
        return conv

    async def run(
        self,
        user_message: str,
    ) -> str:
        """Run agent and track token usage for this turn."""
        self.start_conversation()

        before = self._snapshot_usage()
        result = await self.agent.run(user_message)
        after = self._snapshot_usage()

        usage = self._diff_usage(before, after)
        cost = self._calculate_cost(usage)

        self._turn_count += 1
        turn = TurnRecord(
            turn_id=self._turn_count,
            timestamp=time.time(),
            user_message=user_message,
            assistant_message=result,
            usage=usage,
            cost=cost,
        )

        self._current_conversation.add_turn(turn)
        self.end_conversation()

        return result

    async def run_stream(
        self,
        user_message: str,
    ) -> AsyncIterator[str]:
        """Run agent with streaming and track token usage."""
        self.start_conversation()

        before = self._snapshot_usage()

        # Collect streamed response
        chunks = []
        async for chunk in self.agent.run_stream(user_message):
            chunks.append(chunk)
            yield chunk

        result = "".join(chunks)
        after = self._snapshot_usage()

        usage = self._diff_usage(before, after)
        cost = self._calculate_cost(usage)

        self._turn_count += 1
        turn = TurnRecord(
            turn_id=self._turn_count,
            timestamp=time.time(),
            user_message=user_message,
            assistant_message=result,
            usage=usage,
            cost=cost,
        )

        self._current_conversation.add_turn(turn)
        self.end_conversation()

    def session_total(self) -> TokenUsage:
        """Get total token usage across all conversations in session."""
        total = TokenUsage()
        for conv in self.conversations:
            total.input_tokens += conv.total_usage.input_tokens
            total.output_tokens += conv.total_usage.output_tokens
            total.cache_write_tokens += conv.total_usage.cache_write_tokens
            total.cache_read_tokens += conv.total_usage.cache_read_tokens
        return total

    def session_total_cost(self) -> float:
        """Get total cost across all conversations in session."""
        return sum(conv.total_cost for conv in self.conversations)

    def print_summary(self) -> None:
        """Print summary of all conversations and session totals."""
        for conv in self.conversations:
            print(f"\nConversation {conv.conversation_id}:")
            print(f"  turns: {len(conv.turns)}")
            print(f"  input_tokens: {conv.total_usage.input_tokens}")
            print(f"  output_tokens: {conv.total_usage.output_tokens}")
            print(f"  cache_write_tokens: {conv.total_usage.cache_write_tokens}")
            print(f"  cache_read_tokens: {conv.total_usage.cache_read_tokens}")
            print(f"  cost: ${conv.total_cost:.6f}")

        total = self.session_total()
        print(f"\n=== Session Total ===")
        print(f"  conversations: {len(self.conversations)}")
        print(f"  input_tokens: {total.input_tokens}")
        print(f"  output_tokens: {total.output_tokens}")
        print(f"  cache_write_tokens: {total.cache_write_tokens}")
        print(f"  cache_read_tokens: {total.cache_read_tokens}")
        print(f"  cost: ${self.session_total_cost():.6f}")
