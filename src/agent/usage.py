"""Token usage tracking and cost calculation."""

from dataclasses import dataclass, field
from typing import Optional

import yaml
from pathlib import Path


@dataclass
class TokenUsage:
    """Token usage for a single request."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass
class TokenPricing:
    """Token pricing for a provider (per 1K tokens)."""
    input: float = 0.0
    output: float = 0.0
    cache_write: float = 0.0
    cache_read: float = 0.0


@dataclass
class UsageRecord:
    """A record of token usage and cost."""
    provider: str
    model: str
    usage: TokenUsage
    cost: float


class UsageTracker:
    """Track token usage and calculate costs across providers."""

    def __init__(self):
        self._records: list[UsageRecord] = []
        self._pricing: dict[str, TokenPricing] = {}
        self._load_pricing()

    def _load_pricing(self) -> None:
        """Load pricing from llm.yml."""
        config_path = Path(__file__).parent.parent.parent / "config" / "llm.yml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            for name, cfg in config.get("providers", {}).items():
                pricing = cfg.get("pricing", {})
                self._pricing[name] = TokenPricing(
                    input=pricing.get("input", 0),
                    output=pricing.get("output", 0),
                    cache_write=pricing.get("cache_write", 0),
                    cache_read=pricing.get("cache_read", 0),
                )

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Record token usage and return cost."""
        pricing = self._pricing.get(provider, TokenPricing())
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
        )
        cost = (
            usage.input_tokens * pricing.input / 1000
            + usage.output_tokens * pricing.output / 1000
            + usage.cache_write_tokens * pricing.cache_write / 1000
            + usage.cache_read_tokens * pricing.cache_read / 1000
        )
        record = UsageRecord(provider=provider, model=model, usage=usage, cost=cost)
        self._records.append(record)
        return cost

    def total_cost(self) -> float:
        """Get total cost across all records."""
        return sum(r.cost for r in self._records)

    def summary(self) -> dict:
        """Get usage summary grouped by provider."""
        summary = {}
        for r in self._records:
            if r.provider not in summary:
                summary[r.provider] = {
                    "model": r.model,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_write_tokens": 0,
                    "cache_read_tokens": 0,
                    "cost": 0.0,
                }
            s = summary[r.provider]
            s["input_tokens"] += r.usage.input_tokens
            s["output_tokens"] += r.usage.output_tokens
            s["cache_write_tokens"] += r.usage.cache_write_tokens
            s["cache_read_tokens"] += r.usage.cache_read_tokens
            s["cost"] += r.cost
        return summary

    def reset(self) -> None:
        """Reset all records."""
        self._records.clear()


# Global usage tracker
tracker = UsageTracker()
