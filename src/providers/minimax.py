"""MiniMax provider using Anthropic SDK."""

import os
from typing import Optional, AsyncIterator, Union

from anthropic import AsyncAnthropic

from agent.provider import LLMProvider, ThinkingLevel
from agent.types import LLMResponse, StreamChunk


# Thinking effort → Anthropic budget_tokens mapping
_THINKING_BUDGETS = {
    ThinkingLevel.OFF: None,
    ThinkingLevel.MINIMAL: 100,
    ThinkingLevel.LOW: 500,
    ThinkingLevel.MEDIUM: 1000,
    ThinkingLevel.HIGH: 2000,
    ThinkingLevel.XHIGH: 4000,
    ThinkingLevel.ADAPTIVE: {"type": "auto"},
    ThinkingLevel.MAX: 8000,
}


def _convert_messages(messages: list[dict]) -> list[dict]:
    """Convert messages to Anthropic format with prompt caching.

    Cache strategy:
    - system messages: always cached (stable context)
    - last human turn: cached to reuse KV across tool-loop iterations
    """
    anthropic_messages = []
    # Separate system messages and conversation messages
    system_msgs = [m for m in messages if m["role"] == "system"]
    conv_msgs = [m for m in messages if m["role"] != "system"]

    # Inject system messages as the first user turn with cache_control
    for i, msg in enumerate(system_msgs):
        is_last_system = (i == len(system_msgs) - 1)
        content_block = {"type": "text", "text": msg["content"]}
        if is_last_system:
            content_block["cache_control"] = {"type": "ephemeral"}
        anthropic_messages.append({"role": "user", "content": [content_block]})

    # Find index of last user/human message in conv_msgs for cache marking
    last_human_idx = -1
    for i, msg in enumerate(conv_msgs):
        if msg["role"] == "user":
            last_human_idx = i

    for i, msg in enumerate(conv_msgs):
        is_last_human = (msg["role"] == "user" and i == last_human_idx)
        if msg["role"] == "tool":
            anthropic_messages.append({
                "role": "user",
                "content": f"Tool result: {msg['content']}"
            })
        else:
            text = msg["content"] or ""
            if is_last_human:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}],
                })
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": text,
                })
    return anthropic_messages


def _convert_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tools to Anthropic format.

    Marks the last tool with cache_control so Anthropic caches the entire
    tool list prefix (all tools before it are cached automatically).
    """
    anthropic_tools = []
    for i, tool in enumerate(tools):
        func = tool.get("function", tool)
        entry = {
            "name": func.get("name"),
            "description": func.get("description"),
            "input_schema": func.get("parameters", {}),
        }
        if i == len(tools) - 1:
            entry["cache_control"] = {"type": "ephemeral"}
        anthropic_tools.append(entry)
    return anthropic_tools


class MiniMaxProvider(LLMProvider):
    """MiniMax LLM provider using Anthropic SDK.

    Reads config from environment variables or uses provided overrides.
    Tracks token usage via UsageTracker.
    """

    supports_streaming = True

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        thinking: Optional[ThinkingLevel] = None,
    ):
        try:
            from config import settings
            cfg = settings.llm
            self.model = model or cfg.model
            self.api_key = api_key or cfg.api_key
            self.base_url = base_url or cfg.base_url
        except ImportError:
            self.model = model or "MiniMax-M2.7"
            self.api_key = api_key or os.getenv("MINIMAX_API_KEY", "")
            self.base_url = base_url or "https://api.minimaxi.com/anthropic"

        api_key = self.api_key.strip() if self.api_key else None
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=self.base_url if self.base_url != "https://api.anthropic.com" else None,
        )
        self._max_tokens = 8192
        # Default thinking config, can be overridden per-request
        self._thinking = self._make_thinking_config(thinking)

    def _make_thinking_config(self, thinking: Optional[ThinkingLevel]) -> Optional[dict]:
        """Build thinking config dict from ThinkingLevel."""
        budget = _THINKING_BUDGETS.get(thinking)
        if budget is None:
            return None
        if isinstance(budget, dict):
            return budget
        return {"type": "enabled", "budget_tokens": budget}

    def _record_usage(self, response) -> None:
        """Record token usage to tracker."""
        try:
            from agent.usage import tracker
            usage = response.usage
            tracker.record(
                provider="minimax",
                model=self.model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_tokens", 0) or 0,
            )
        except Exception:
            pass

    def _thinking_config(self, thinking: Optional[ThinkingLevel]) -> Optional[dict]:
        """Get thinking config, using instance default if not specified."""
        if thinking is not None:
            return self._make_thinking_config(thinking)
        return self._thinking

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        thinking: Optional[ThinkingLevel] = None,
    ) -> LLMResponse:
        anthropic_messages = _convert_messages(messages)

        params = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self._max_tokens,
        }

        if tools:
            params["tools"] = _convert_tools(tools)

        thinking_cfg = self._thinking_config(thinking)
        if thinking_cfg:
            params["thinking"] = thinking_cfg

        response = await self.client.messages.create(**params)
        self._record_usage(response)

        # Convert response to LLMResponse format
        tool_calls = None
        content_text = ""
        thinking_content = ""

        for block in response.content:
            if hasattr(block, 'type'):
                if block.type == "text":
                    content_text = block.text
                elif block.type == "tool_use":
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append({
                        "name": block.name,
                        "arguments": block.input,
                    })
                elif block.type == "thinking":
                    thinking_content += block.thinking if hasattr(block, 'thinking') else ""

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "thinking": thinking_content if thinking_content else None,
            "input_tokens": response.usage.input_tokens if response.usage else None,
            "output_tokens": response.usage.output_tokens if response.usage else None,
            "cache_write_tokens": getattr(response.usage, "cache_creation_input_tokens", None) if response.usage else None,
            "cache_read_tokens": getattr(response.usage, "cache_read_tokens", None) if response.usage else None,
        }

    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        thinking: Optional[ThinkingLevel] = None,
    ) -> AsyncIterator[Union[str, StreamChunk]]:
        """Stream chat response as text chunks, thinking, and tool events.

        Yields:
        - str: Text content chunks
        - StreamChunk: {"type": "thinking", "content": "..."} for reasoning
        - StreamChunk: {"type": "tool_use", "tool_call_id": "...", "tool_name": "..."} for tool start
        - StreamChunk: {"type": "tool_use", "arguments": {"partial": "..."}} for tool args delta
        """
        anthropic_messages = _convert_messages(messages)

        params = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self._max_tokens,
        }

        if tools:
            params["tools"] = _convert_tools(tools)

        thinking_cfg = self._thinking_config(thinking)
        if thinking_cfg:
            params["thinking"] = thinking_cfg

        current_thinking = ""
        in_thinking_block = False
        current_tool_name: Optional[str] = None
        current_tool_id: Optional[str] = None
        current_tool_args = ""
        in_tool_use_block = False

        async with self.client.messages.stream(**params) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event, 'content_block') and hasattr(event.content_block, 'type'):
                        if event.content_block.type == "thinking":
                            in_thinking_block = True
                            current_thinking = ""
                        elif event.content_block.type == "tool_use":
                            in_tool_use_block = True
                            current_tool_name = getattr(event.content_block, 'name', None)
                            current_tool_id = getattr(event.content_block, 'id', None)
                            current_tool_args = ""
                elif event.type == "content_block_delta":
                    if hasattr(event, 'delta'):
                        delta = event.delta
                        if hasattr(delta, 'thinking'):
                            current_thinking += delta.thinking
                            yield {"type": "thinking", "content": delta.thinking}
                        elif hasattr(delta, 'text') and hasattr(delta, 'text'):
                            yield delta.text
                        elif hasattr(delta, 'partial_json'):
                            # Anthropic SDK InputJSONDelta uses .partial_json
                            current_tool_args += delta.partial_json
                        elif hasattr(delta, 'input_json_delta'):
                            current_tool_args += delta.input_json_delta
                elif event.type == "content_block_stop":
                    if in_thinking_block:
                        in_thinking_block = False
                    elif in_tool_use_block:
                        in_tool_use_block = False
                        # Yield complete tool_use chunk with fully parsed arguments
                        try:
                            import json as _json
                            parsed_args = _json.loads(current_tool_args) if current_tool_args else {}
                        except Exception:
                            parsed_args = {}
                        yield {
                            "type": "tool_use",
                            "tool_call_id": current_tool_id,
                            "tool_name": current_tool_name,
                            "arguments": parsed_args,
                        }

        # After stream completes, record usage from final message
        final_message = await stream.get_final_message()
        if final_message:
            self._record_usage(final_message)
            # Extract content and thinking from final message
            final_content = ""
            final_thinking = ""
            for block in final_message.content:
                if hasattr(block, 'type'):
                    if block.type == "text":
                        final_content = getattr(block, 'text', '')
                    elif block.type == "thinking":
                        final_thinking += getattr(block, 'thinking', '')
            # Yield done chunk with full response and token usage
            # Skip done when stop_reason is tool_use — core handles continuation
            if getattr(final_message, 'stop_reason', None) != 'tool_use':
                done_chunk: StreamChunk = {
                    "type": "done",
                    "content": final_content,
                    "thinking": final_thinking if final_thinking else None,
                    "input_tokens": getattr(getattr(final_message, 'usage', None), 'input_tokens', None),
                    "output_tokens": getattr(getattr(final_message, 'usage', None), 'output_tokens', None),
                    "cache_write_tokens": getattr(getattr(final_message, 'usage', None), 'cache_creation_input_tokens', None),
                    "cache_read_tokens": getattr(getattr(final_message, 'usage', None), 'cache_read_tokens', None),
                }
                yield done_chunk
        else:
            # MiniMax streaming may not return usage in get_final_message
            done_chunk: StreamChunk = {"type": "done", "content": "", "input_tokens": None, "output_tokens": None, "cache_write_tokens": None, "cache_read_tokens": None}
            yield done_chunk