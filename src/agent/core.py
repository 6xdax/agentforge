"""Minimal Agent engine core implementation."""

from collections.abc import AsyncIterator
from typing import Optional

from .errors import MaxIterationsError, ToolNotFoundError
from .message import Message
from .registry import ToolRegistry
from .registry import tool_error
from .memory import InMemoryMemory, MemoryBackend
from .provider import LLMProvider
from .types import LLMResponse
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
    ):
        self.provider = provider
        self.registry = registry or ToolRegistry()
        self.memory = memory
        self.max_iterations = max_iterations

        # Register built-in parse_document tool if registry is new
        if registry is None:
            self.registry.register(
                name="parse_document",
                schema=get_document_schema(),
                handler=parse_document,
            )

    async def run(self, user_message: str) -> LLMResponse:
        """Run agent with user message.

        Returns:
            LLMResponse with content, tool_calls (executed), thinking, and token usage
        """
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

    async def run_stream(self, user_message: str) -> AsyncIterator[str]:
        """Run agent with streaming response.

        Yields:
            Text chunks from the LLM response
        """
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
            # Check if provider supports streaming
            if not hasattr(self.provider, 'chat_stream'):
                # Fall back to non-streaming
                response: LLMResponse = await self.provider.chat(
                    messages,
                    tools=self.registry.get_schemas() or None,
                )
                if not response.get("tool_calls"):
                    final_content = response.get("content", "")
                    if self.memory:
                        await self.memory.add({"role": "user", "content": user_message, "name": None})
                        await self.memory.add({"role": "assistant", "content": final_content, "name": None})
                    yield final_content
                    return
                # Handle tool calls (simplified - collect and execute)
                for call in response["tool_calls"]:
                    tool_name = call["name"]
                    tool_args = call.get("arguments", {})
                    result = await self.registry.dispatch(tool_name, tool_args)
                    messages.append({"role": "tool", "content": result, "name": tool_name})
                continue

            # Stream the response
            full_content = ""
            tool_calls_found = []
            async for chunk in self.provider.chat_stream(
                messages,
                tools=self.registry.get_schemas() or None,
            ):
                # print(f"Received chunk: {chunk}")
                if isinstance(chunk, dict):
                    chunk_type = chunk.get("type")
                    if chunk_type == "thinking":
                        # print(f"[Thinking]: {chunk.get('content', '')[:100]}...")
                        pass
                    elif chunk_type == "tool_use":
                        tool_name = chunk.get("tool_name")
                        tool_args = chunk.get("args", {})
                        tool_call_id = chunk.get("tool_call_id")
                        if tool_name:
                            print(f"[Tool Call]: {tool_name}")
                            tool_calls_found.append({"name": tool_name, "args": tool_args, "call_id": tool_call_id})
                            result = await self.registry.dispatch(tool_name, tool_args)
                            messages.append({"role": "tool", "content": result, "name": tool_name})
                            yield {
                                "type": "tool_result",
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "result": result
                            }
                    elif chunk_type == "done":
                        # done chunk - end this iteration
                        break
                else:
                    full_content += chunk
                    yield chunk

            # After streaming, execute any tool calls using non-streaming chat
            # (streaming doesn't return tool call results in the stream itself)
            if tool_calls_found:
                # Re-run with non-streaming to get tool calls and execute them
                response = await self.provider.chat(
                    messages,
                    tools=self.registry.get_schemas() or None,
                )
                if response.get("tool_calls"):
                    for call in response["tool_calls"]:
                        tool_name = call["name"]
                        tool_args = call.get("arguments", {})
                        result = await self.registry.dispatch(tool_name, tool_args)
                        messages.append({"role": "tool", "content": result, "name": tool_name})
                    # Continue the loop to get final response after tools
                    continue

            # No tool calls - store in memory and return
            if self.memory:
                await self.memory.add({"role": "user", "content": user_message, "name": None})
                await self.memory.add({"role": "assistant", "content": full_content, "name": None})

            return
