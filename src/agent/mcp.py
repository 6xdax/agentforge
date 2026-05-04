"""MCP (Model Context Protocol) client for connecting to MCP servers."""

import asyncio
import json
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

from .registry import ToolRegistry, tool_result, tool_error
from .errors import ToolError


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    command: str
    args: list[str] = None
    env: dict[str, str] = None


class MCPClient:
    """Client for connecting to MCP servers and exposing their tools.

    Supports stdio-based MCP servers. Tools are registered with a
    ToolRegistry instance for use by the Agent.

    Example:
        config = MCPServerConfig(command="npx", args=["-y", "@anthropic/mcp-server filesystem"])
        async with MCPClient(config) as client:
            client.register_tools(registry)
            agent = Agent(provider=provider, registry=registry)
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._tools: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to the MCP server and discover available tools."""
        cmd = self.config.command
        args = self.config.args or []
        env = self.config.env or {}

        # Merge environment
        full_env = {**dict(self.config.env)} if self.config.env else {}
        if "PATH" not in full_env:
            import os
            full_env["PATH"] = os.environ.get("PATH", "")

        self._process = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            env=full_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Initialize and discover tools
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "agentforge", "version": "0.1.0"},
        })

        # Read initial response
        await self._read_response()

        # Send initialized notification
        await self._send_notification("notifications/initialized", {
            "capabilities": {"tools": {}},
        })

        # Discover tools
        await self._discover_tools()

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None

    async def _send_request(self, method: str, params: dict = None) -> dict:
        """Send a JSON-RPC request and wait for response."""
        if not self._process or self._process.stdin is None or self._process.stdout is None:
            raise ToolError("Not connected to MCP server")

        self._request_id += 1
        req_id = self._request_id

        request = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            request["params"] = params

        req_json = json.dumps(request) + "\n"
        self._process.stdin.write(req_json.encode())
        await self._process.stdin.drain()

        return await self._read_response()

    async def _send_notification(self, method: str, params: dict = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or self._process.stdin is None:
            raise ToolError("Not connected to MCP server")

        notification = {"jsonrpc": "2.0", "method": method}
        if params:
            notification["params"] = params

        notif_json = json.dumps(notification) + "\n"
        self._process.stdin.write(notif_json.encode())
        await self._process.stdin.drain()

    async def _read_response(self) -> dict:
        """Read a JSON-RPC response from stdout."""
        if not self._process or self._process.stdout is None:
            raise ToolError("Not connected to MCP server")

        line = await self._process.stdout.readline()
        if not line:
            raise ToolError("MCP server disconnected")
        return json.loads(line.decode())

    async def _discover_tools(self) -> None:
        """Discover available tools from the MCP server."""
        try:
            response = await self._send_request("tools/list")
            if "result" in response and "tools" in response["result"]:
                for tool in response["result"]["tools"]:
                    self._tools[tool["name"]] = tool
        except Exception:
            pass  # Server may not support tools/list

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call an MCP tool by name with arguments.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            JSON string result
        """
        async with self._lock:
            try:
                response = await self._send_request("tools/call", {
                    "name": name,
                    "arguments": arguments,
                })
                if "result" in response:
                    result = response["result"]
                    if isinstance(result, dict) and "content" in result:
                        # Return the content as JSON
                        return json.dumps(result["content"])
                    return json.dumps(result)
                elif "error" in response:
                    return tool_error(response["error"].get("message", "Unknown error"))
                return tool_result({"status": "ok"})
            except Exception as e:
                return tool_error(f"MCP tool call failed: {e}")

    def get_schemas(self) -> list[dict]:
        """Get OpenAI-format schemas for all discovered MCP tools."""
        schemas = []
        for name, tool in self._tools.items():
            input_schema = tool.get("inputSchema", {})
            if isinstance(input_schema, str):
                input_schema = json.loads(input_schema)
            schemas.append({
                "name": name,
                "description": tool.get("description", ""),
                "parameters": input_schema,
            })
        return schemas

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register all discovered MCP tools with a ToolRegistry.

        Args:
            registry: ToolRegistry instance to register tools with
        """
        for name, tool in self._tools.items():
            schema = self.get_tool_schema(name)
            registry.register(
                name=name,
                schema=schema,
                handler=lambda args, n=name: self.call_tool(n, args),
                description=tool.get("description", ""),
            )

    def get_tool_schema(self, name: str) -> dict:
        """Get OpenAI-format schema for a specific tool."""
        tool = self._tools.get(name)
        if not tool:
            return {}
        input_schema = tool.get("inputSchema", {})
        if isinstance(input_schema, str):
            input_schema = json.loads(input_schema)
        return {
            "name": name,
            "description": tool.get("description", ""),
            "parameters": input_schema,
        }


class MCPToolProvider:
    """Mock provider that returns MCP tool calls for testing.

    Use this to test agent flows with MCP tools without a real server.
    First call returns tool_calls (if tools provided), subsequent calls return final response.
    """

    def __init__(
        self,
        tools: list[dict],
        response_final: str = "Done",
        tool_to_call: str = None,
        tool_args: dict = None,
    ):
        self.tools = tools
        self.response_final = response_final
        self.tool_to_call = tool_to_call
        self.tool_args = tool_args or {}
        self._call_count = 0
        self._tool_called = False

    async def chat(self, messages: list[dict], tools: list[dict] = None, thinking: Any = None) -> dict:
        """Return a response, optionally with a tool call."""
        self._call_count += 1

        # On first call with tools and tool_to_call, return tool call
        if tools and self.tool_to_call and not self._tool_called:
            self._tool_called = True
            return {
                "content": f"Calling tool: {self.tool_to_call}",
                "tool_calls": [{
                    "name": self.tool_to_call,
                    "arguments": self.tool_args,
                }],
            }
        # Subsequent calls return final response
        return {"content": self.response_final}
