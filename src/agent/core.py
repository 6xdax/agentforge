"""Minimal Agent engine core implementation."""

from collections.abc import AsyncIterator
from typing import Optional

from .errors import MaxIterationsError, ToolNotFoundError
from .message import Message
from .registry import ToolRegistry
from .registry import tool_error
from .memory import InMemoryMemory, MemoryBackend
from .provider import LLMProvider
from .types import LLMResponse, ThinkingLevel
from .message import StreamChunk
from tools.file_parser import parse_document, get_document_schema


class Agent:
    """Minimal Agent engine.

    Core loop: receive message -> call LLM -> if tool_calls, execute tools
    -> repeat until no tool calls -> return final response.

    This is the entire agent core in ~80 lines.
    """

    def __init__(
        self,
        provider: LLMProvider,
        registry: Optional[ToolRegistry] = None,
        memory: Optional[MemoryBackend] = InMemoryMemory(),
        max_iterations: int = 20,
        thinking: Optional[ThinkingLevel] = None,
    ):
        self.provider = provider
        self.registry = registry or ToolRegistry()
        self.memory = memory
        self.max_iterations = max_iterations
        self.thinking = thinking

        # Register built-in parse_document tool if registry is new
        if registry is None:
            self.registry.register(
                name="parse_document",
                schema=get_document_schema(),
                handler=parse_document,
            )

    async def run(self, user_message: str, thinking: Optional[ThinkingLevel] = None) -> LLMResponse:
        """Run agent with user message.

        Args:
            user_message: The user input message
            thinking: Thinking effort level, overrides Agent-level setting if provided

        Returns:
            LLMResponse with content, tool_calls (executed), thinking, and token usage
        """
        thinking_level = thinking if thinking is not None else self.thinking

        messages: list[Message] = [
            {"role": "user", "content": user_message, "name": None}
        ]

        # Track all executed tool calls
        executed_tools: list[dict] = []

        # Add memory context if available
        if self.memory:
            ctx = await self.memory.get_context()
            if ctx:
                messages.insert(
                    0,
                    {"role": "system", "content": f"Context:\n{ctx}", "name": None}
                )

        for _ in range(self.max_iterations):
            # Get LLM response with tools
            response: LLMResponse = await self.provider.chat(
                messages,
                tools=self.registry.get_schemas() or None,
                thinking=thinking_level,
            )

            # No tool calls - return final response
            if not response.get("tool_calls"):
                # Store in memory if available
                if self.memory:
                    await self.memory.add({"role": "user", "content": user_message, "name": None})
                    await self.memory.add({"role": "assistant", "content": response.get("content", ""), "name": None})
                # Add executed tools to response
                if executed_tools:
                    response["tool_calls"] = executed_tools
                return response

            # Execute each tool call
            for call in response["tool_calls"]:
                tool_name = call["name"]
                tool_args = call.get("arguments", {})

                # Execute tool
                try:
                    result = await self.registry.dispatch(tool_name, tool_args)
                except ToolNotFoundError as exc:
                    raise exc

                # Track executed tool
                executed_tools.append({"name": tool_name, "arguments": tool_args, "result": result})

                # Add assistant message with tool call
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "name": tool_name,
                })
                if self.memory:
                    await self.memory.add({
                        "role": "assistant",
                        "content": "",
                        "name": tool_name,
                    })

                # Add tool result message
                messages.append({
                    "role": "tool",
                    "content": result,
                    "name": tool_name,
                })
                if self.memory:
                    await self.memory.add({
                        "role": "tool",
                        "content": result,
                        "name": tool_name,
                    })

        raise MaxIterationsError(tool_error("Max iterations reached"))

    async def run_stream(self, user_message: str, thinking: Optional[ThinkingLevel] = None) -> AsyncIterator[StreamChunk]:
        """Run agent with streaming response.

        Args:
            user_message: The user input message
            thinking: Thinking effort level, overrides Agent-level setting if provided

        Yields:
            StreamChunk dicts with type, content, tool_use, tool_result, or done
        """
        thinking_level = thinking if thinking is not None else self.thinking

        messages: list[Message] = [
            {"role": "user", "content": user_message, "name": None}
        ]

        # Add memory context if available
        if self.memory:
            ctx = await self.memory.get_context()
            if ctx:
                messages.insert(
                    0,
                    {"role": "system", "content": f"Context:\n{ctx}", "name": None}
                )

        for _ in range(self.max_iterations):
            # Stream the response
            full_content = ""
            tool_calls_found = []
            async for chunk in self.provider.chat_stream(
                messages,
                tools=self.registry.get_schemas() or None,
                thinking=thinking_level,
            ):
                # print(f"Received chunk: {chunk}")
                if isinstance(chunk, dict):
                    chunk_type = chunk.get("type")
                    if chunk_type == "thinking":
                        yield {"type": "thinking", "content": chunk.get("content", "")}
                    elif chunk_type == "tool_use":
                        tool_name = chunk.get("tool_name")
                        tool_args = chunk.get("arguments", {})
                        tool_call_id = chunk.get("tool_call_id")
                        if tool_name:
                            # Surface tool_use to callers before execution.
                            yield {
                                "type": "tool_use",
                                "tool_call_id": tool_call_id,
                                "tool_name": tool_name,
                                "arguments": tool_args,
                            }
                            # Execute tool
                            try:
                                result = await self.registry.dispatch(tool_name, tool_args)
                            except ToolNotFoundError as exc:
                                raise exc

                            messages.append({"role": "tool", "content": f"args: {tool_args} result: {result}", "name": tool_name})
                            yield {
                                "type": "tool_result",
                                "tool_call_id": tool_call_id,
                                "tool_name": tool_name,
                                "result": result,
                            }
                            tool_calls_found.append(tool_name)
                    elif chunk_type == "done":
                        yield {
                            "type": "done",
                            "content": full_content,
                            "input_tokens": chunk.get("input_tokens"),
                            "output_tokens": chunk.get("output_tokens"),
                            "cache_write_tokens": chunk.get("cache_write_tokens"),
                            "cache_read_tokens": chunk.get("cache_read_tokens"),
                        }
                        break
                else:
                    full_content += chunk
                    yield {"type": "text", "content": chunk}

            if tool_calls_found:
                tool_calls_found = []
                continue

            # No tool calls - store in memory and return
            if self.memory:
                await self.memory.add({"role": "user", "content": user_message, "name": None})
                await self.memory.add({"role": "assistant", "content": full_content, "name": None})

            return
