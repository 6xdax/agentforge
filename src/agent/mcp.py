"""MCP (Model Context Protocol) client for connecting to MCP servers."""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

from .registry import ToolRegistry, tool_error
from .errors import ToolError

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    command: str
    args: list[str] = None
    env: dict[str, str] = None


class MCPClient:
    """Production-grade async JSON-RPC client for MCP servers.

    Features:
    - Request-id based routing with pending futures
    - Independent reader loop (background task)
    - Notification handling
    - stderr log streaming
    - Thread-safe request-id generation (no global lock on operations)
    - Proper cleanup on disconnect (cancels pending tasks)
    - Timeout support for tool calls
    - Strict error checking for initialize and tools/list
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None

        # Request-id counter and pending responses
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._id_lock = asyncio.Lock()

        # Tool cache
        self._tools: dict[str, dict] = {}

        # Control flags
        self._running = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to the MCP server and discover available tools."""
        if self._running:
            return

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

        self._running = True

        # Start background tasks
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._stderr_task = asyncio.create_task(self._stderr_reader())

        # Initialize - strict error checking
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "agentforge", "version": "0.1.0"},
        })
        if "error" in result:
            raise ToolError(f"initialize failed: {result['error']}")

        # Send initialized notification
        await self._send_notification("notifications/initialized")

        # Discover tools - strict error checking
        await self._discover_tools()

    async def disconnect(self) -> None:
        """Disconnect from the MCP server and clean up all pending tasks."""
        if not self._running:
            return

        self._running = False

        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Cancel stderr reader
        if self._stderr_task:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

        # Fail all pending requests with disconnect error
        async with self._id_lock:
            for req_id, future in self._pending.items():
                if not future.done():
                    future.set_exception(ToolError("MCP server disconnected"))
            self._pending.clear()

        # Terminate process
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None

    async def _stderr_reader(self) -> None:
        """Background task to read stderr and log server output."""
        if not self._process or not self._process.stderr:
            return

        try:
            while self._running:
                try:
                    line = await self._process.stderr.readline()
                    if line:
                        logger.debug("MCP server stderr: %s", line.decode().strip())
                    else:
                        break
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if self._running:
                        logger.warning("MCP stderr reader error: %s", e)
                    break
        except Exception as e:
            logger.warning("MCP stderr reader failed: %s", e)

    async def _reader_loop(self) -> None:
        """Background reader loop that routes responses to pending futures."""
        if not self._process or not self._process.stdout:
            return

        try:
            while self._running:
                try:
                    line = await self._process.stdout.readline()
                except asyncio.CancelledError:
                    break

                if not line:
                    # Server disconnected - fail all pending
                    logger.warning("MCP server disconnected")
                    break

                try:
                    msg = json.loads(line.decode())
                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON from MCP server: %s", e)
                    continue

                # Route message
                await self._route_message(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("MCP reader loop error: %s", e)
        finally:
            # On disconnect, fail all pending with disconnect error
            async with self._id_lock:
                for _, future in self._pending.items():
                    if not future.done():
                        future.set_exception(ToolError("MCP server disconnected"))
                self._pending.clear()

    async def _route_message(self, msg: dict) -> None:
        """Route a JSON-RPC message to the appropriate handler."""
        if "id" not in msg:
            # Notification - handle if needed
            await self._handle_notification(msg)
            return

        msg_id = msg["id"]

        async with self._id_lock:
            future = self._pending.pop(msg_id, None)

        if future is None:
            logger.warning("Received response for unknown request id: %s", msg_id)
            return

        if not future.done():
            if "error" in msg:
                future.set_result(msg)
            elif "result" in msg:
                future.set_result(msg)
            else:
                future.set_result(msg)

    async def _handle_notification(self, msg: dict) -> None:
        """Handle incoming notifications."""
        method = msg.get("method", "")

        if method == "tools/list_changed":
            # Server notified that tools changed, rediscover
            try:
                await self._discover_tools()
            except Exception as e:
                logger.warning("Failed to rediscover tools: %s", e)

    async def _next_id(self) -> int:
        """Get next request ID (thread-safe)."""
        async with self._id_lock:
            self._request_id += 1
            return self._request_id

    async def _send_request(self, method: str, params: dict = None, timeout: float = 30.0) -> dict:
        """Send a JSON-RPC request and wait for response with timeout."""
        if not self._running or not self._process or self._process.stdin is None:
            raise ToolError("Not connected to MCP server")

        req_id = await self._next_id()
        loop = asyncio.get_running_loop()

        request = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            request["params"] = params

        future = loop.create_future()
        async with self._id_lock:
            self._pending[req_id] = future

        try:
            req_json = json.dumps(request) + "\n"
            try:
                self._process.stdin.write(req_json.encode())
                await self._process.stdin.drain()
            except BrokenPipeError:
                async with self._id_lock:
                    self._pending.pop(req_id, None)
                raise ToolError("MCP server stdin pipe broken")

            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            async with self._id_lock:
                self._pending.pop(req_id, None)
            raise ToolError(f"Request {method} timed out after {timeout}s")
        except asyncio.CancelledError:
            async with self._id_lock:
                self._pending.pop(req_id, None)
            raise
        except ToolError:
            raise

    async def _send_notification(self, method: str, params: dict = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._running or not self._process or self._process.stdin is None:
            return  # Silently ignore notifications when disconnected

        notification = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            notification["params"] = params

        try:
            notif_json = json.dumps(notification) + "\n"
            self._process.stdin.write(notif_json.encode())
            await self._process.stdin.drain()
        except BrokenPipeError:
            pass  # Server disconnected, notification not critical

    async def _discover_tools(self) -> None:
        """Discover available tools from the MCP server with strict error checking."""
        response = await self._send_request("tools/list")

        if "error" in response:
            raise ToolError(f"tools/list failed: {response['error']}")

        if "result" not in response or "tools" not in response.get("result", {}):
            raise ToolError("Invalid tools/list response: missing result.tools")

        tools = response["result"]["tools"]
        self._tools.clear()
        for tool in tools:
            # Skip tools without name to prevent crash
            if "name" not in tool:
                logger.warning("Skipping tool without name: %s", tool)
                continue
            self._tools[tool["name"]] = tool

    async def call_tool(self, name: str, arguments: dict, timeout: float = 60.0) -> str:
        """Call an MCP tool by name with arguments.

        Args:
            name: Tool name
            arguments: Tool arguments
            timeout: Operation timeout in seconds (default 60s)

        Returns:
            JSON string result
        """
        if not self._running:
            return tool_error("Not connected to MCP server")

        try:
            response = await self._send_request("tools/call", {
                "name": name,
                "arguments": arguments,
            }, timeout=timeout)

            if "error" in response:
                return tool_error(response["error"].get("message", "Unknown error"))

            if "result" in response:
                result = response["result"]
                if isinstance(result, dict) and "content" in result:
                    return json.dumps(result["content"])
                return json.dumps(result) if isinstance(result, dict) else json.dumps({"content": result})

            return json.dumps({"status": "ok"})

        except ToolError:
            raise
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
                handler=self._make_tool_handler(name),
                description=tool.get("description", ""),
            )

    def _make_tool_handler(self, name: str):
        """Create an async handler for a tool."""
        async def handler(args: dict) -> dict:
            return await self.call_tool(name, args)
        return handler

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