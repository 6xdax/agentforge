# AgentForge

AgentForge is a modular agent project built around a minimal core package: agent.

## Install

```bash
uv sync
```

## Quick Start

```python
import asyncio

from agent import Agent, LLMProvider


class HelloProvider(LLMProvider):
    async def chat(self, messages, tools=None, thinking=None):
        return {"content": "Hello!"}


async def main() -> None:
    agent = Agent(provider=HelloProvider())
    print(await agent.run("Say hello"))


asyncio.run(main())
```

## With Tools

```python
from agent import Agent, ToolRegistry

registry = ToolRegistry()

agent = Agent(provider=my_llm_provider, registry=registry)
```

Repo examples are intended to be run from this repository checkout with `uv run`.

## Architecture

- **Core**: ~60 lines, fully understandable
- **Pluggable**: Tools, Memory, LLM Provider all injectable
- **Minimal runtime**: clear abstraction boundaries for provider/tools/memory

## Reliable Tool Calling

LLM tool calling is inherently probabilistic—models can hallucinate parameters even when explicitly told not to. AgentForge ships agent with a three-layer approach to reliable tool calling:

### Layer 1: Clear Prompt + Few-shot (Soft Constraint)

Write prompts as "operation contracts" with explicit type/boundary/not-allowed examples:

```python
WEATHER_PROMPT = """
city 必须是标准英文城市名，如 Beijing, Shanghai
禁止传入：中文城市名、空字符串、自然语言短语
date 必须是 YYYY-MM-DD 格式，仅支持今天或明天
"""
```

### Layer 2: JSON Schema (Hard Constraint)

Define machine-verifiable schemas with `additionalProperties: false`:

```python
from agent.schema_validator import create_tool_schema

schema = create_tool_schema(
    name="get_weather",
    properties={
        "city": {"type": "string", "pattern": "^[A-Z][a-zA-Z]+$"},
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    },
    required=["city", "date"],
    additional_properties=False,  # Reject unknown fields
)
```

### Layer 3: Validate-Clean-Retry Loop (Fallback)

Automatically clean LLM output artifacts (markdown, trailing commas) and retry on failure:

```python
from agent.schema_validator import SchemaValidator

validator = SchemaValidator(schema, max_retries=3)
validated = validator.validate_and_retries(raw_model_output)
```

Install validation support with `uv sync --extra validation`.

See [docs/reliable_tool_calling.md](docs/reliable_tool_calling.md) for a complete tutorial, and [examples/reliable_tool_call.py](examples/reliable_tool_call.py) for a runnable demo.

For architecture notes inspired by agent harness engineering, see [docs/learn_from_learn_claude_code.md](docs/learn_from_learn_claude_code.md).

