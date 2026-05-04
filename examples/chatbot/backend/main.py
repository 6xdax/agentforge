"""
AgentForge Chatbot Backend - FastAPI server with MiniMax provider and streaming support.
"""

import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import json
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("chatbot")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

# Add project root and src to path for imports
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent import Agent, ToolRegistry, InMemoryMemory, SlidingWindowMemory, tracker
from agent.provider import LLMProvider
from agent.types import LLMResponse, ThinkingLevel
from agent.registry import tool_result
from providers.minimax import MiniMaxProvider
from tools.calculator import register as register_calculator
from tools.file_ops import register as register_file_ops


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    thinking: bool = False
    stream: bool = True


class ChatResponse(BaseModel):
    response: str
    thinking: Optional[str] = None
    tool_calls: Optional[list] = None


# Simple in-memory session manager
class SessionManager:
    def __init__(self):
        self.sessions: dict[str, dict] = {}

    def create_session(self, session_id: str, agent: Agent):
        self.sessions[session_id] = {"agent": agent, "history": []}

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    def add_to_history(self, session_id: str, role: str, content: str):
        if session_id in self.sessions:
            self.sessions[session_id]["history"].append({"role": role, "content": content})


session_manager = SessionManager()


# Global registry and tools
registry = ToolRegistry()
memory = SlidingWindowMemory(window_size=20)


def setup_tools():
    """Register demo tools."""
    register_calculator(registry)
    register_file_ops(registry)

    def echo_handler(args: dict) -> str:
        return tool_result({"echoed": args.get("message", ""), "original": True})

    registry.register(
        name="echo",
        schema={
            "name": "echo",
            "description": "Echo back a message with metadata",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to echo back"},
                },
                "required": ["message"],
            },
        },
        handler=echo_handler,
    )

    def time_handler(args: dict) -> str:
        from datetime import datetime
        return tool_result({"current_time": datetime.now().isoformat()})

    registry.register(
        name="get_time",
        schema={
            "name": "get_time",
            "description": "Get the current time",
            "parameters": {"type": "object", "properties": {}},
        },
        handler=time_handler,
    )


setup_tools()


def create_agent(thinking: bool = False) -> Agent:
    """Create agent with MiniMax provider."""
    thinking_level = ThinkingLevel.ADAPTIVE if thinking else None
    provider = MiniMaxProvider(thinking=thinking_level)
    return Agent(provider=provider, registry=registry, memory=memory)


# Create default agent
default_agent = create_agent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_manager.create_session("default", default_agent)
    logger.info("Chatbot backend started with MiniMax provider!")
    yield
    logger.info("Chatbot backend shutting down!")

# Frontend build output directory (relative to project root)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

app = FastAPI(title="AgentForge Chatbot", lifespan=lifespan)

# Mount static files
app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")


@app.get("/")
async def root():
    # Serve React app from frontend build
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        return FileResponse(frontend_dist / "index.html")
    return {"message": "Frontend not built. Run 'npm run build' in frontend directory."}


@app.post("/api/chat")
async def chat_post(req: ChatRequest):
    """POST endpoint with optional streaming."""
    logger.info(f"[POST /api/chat] message={req.message[:50]!r}... stream={req.stream} thinking={req.thinking}")
    session = session_manager.get_session("default")
    if not session:
        logger.warning("[POST /api/chat] No session available")
        return ChatResponse(response="No session available")

    agent = session["agent"]

    if req.stream:
        async def stream_generator():
            thinking_content = ""
            tool_calls = []

            # Send thinking indicator if enabled
            if req.thinking:
                yield "🔍 思考中...\n\n"

            try:
                # Use agent's run_stream to properly handle tool calls and thinking
                async for chunk in agent.run_stream(req.message):
                    if isinstance(chunk, dict):
                        # Handle structured chunks
                        chunk_type = chunk.get("type")
                        if chunk_type == "thinking":
                            # Only send thinking content if thinking is enabled
                            if req.thinking:
                                thinking_text = chunk.get("content", "")
                                if thinking_text:
                                    thinking_content = thinking_text
                                    # Send truncated preview
                                    preview = thinking_text[:200] + ("..." if len(thinking_text) > 200 else "")
                                    yield f"💭 {preview}\n\n"
                        elif chunk_type == "tool_use":
                            tool_name = chunk.get("tool_name")
                            if tool_name and tool_name not in tool_calls:
                                tool_calls.append(tool_name)
                                yield f"🔧 调用工具: {tool_name}\n"
                        elif chunk_type == "done":
                            # Done chunk - thinking is complete
                            pass
                    else:
                        # String content chunk
                        yield chunk

                # Send completion signal only if thinking was enabled
                if req.thinking:
                    yield f"\n✅ DONE:{thinking_content}\n"

            except Exception as e:
                yield f"Error: {str(e)}"

        return StreamingResponse(
            stream_generator(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache"}
        )
    else:
        try:
            logger.info("[POST /api/chat] Using non-streaming response")
            response = await agent.run(req.message)
            content = response.get("content", "") or ""
            tool_calls = response.get("tool_calls") or []
            logger.info(f"[POST /api/chat] Response complete: {content[:50]!r}... tool_calls={len(tool_calls)}")
            return ChatResponse(
                response=content,
                tool_calls=tool_calls
            )
        except Exception as e:
            logger.error(f"[POST /api/chat] Error: {e}")
            return ChatResponse(response=f"Error: {str(e)}")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket for real-time chat with tool and thinking display."""
    await websocket.accept()
    logger.info("[WS] Client connected")

    session = session_manager.get_session("default")
    if not session:
        logger.warning("[WS] No session available")
        await websocket.send_json({"error": "No session available"})
        await websocket.close()
        return

    agent = session["agent"]

    try:
        while True:
            data = await websocket.receive_text()
            msg_data = json.loads(data)
            message = msg_data.get("message", "")
            thinking = msg_data.get("thinking", False)
            stream = msg_data.get("stream", True)

            if not message:
                continue

            logger.info(f"[WS] Received message: {message[:50]!r}... stream={stream} thinking={thinking}")

            try:
                if stream:
                    await websocket.send_json({"type": "start", "content": ""})

                    full_content = ""
                    tool_calls = []
                    thinking_content = ""

                    async for chunk in agent.run_stream(message):
                        if isinstance(chunk, dict):
                            chunk_type = chunk.get("type")
                            if chunk_type == "thinking":
                                thinking_content = chunk.get("content", "")
                                # Send thinking update
                                await websocket.send_json({
                                    "type": "thinking",
                                    "content": thinking_content
                                })
                            elif chunk_type == "tool_use":
                                tool_name = chunk.get("tool_name")
                                if tool_name:
                                    tool_calls.append(tool_name)
                                    await websocket.send_json({
                                        "type": "tool_use",
                                        "tool_name": tool_name,
                                        "tool_call_id": chunk.get("tool_call_id")
                                    })
                            elif chunk_type == "done":
                                # Final usage stats
                                pass
                        else:
                            full_content += chunk
                            await websocket.send_json({"type": "chunk", "content": chunk})

                    # Send completion with tool calls
                    logger.info(f"[WS] Response complete: {full_content[:50]!r}... tool_calls={tool_calls}")
                    await websocket.send_json({
                        "type": "done",
                        "content": full_content,
                        "tool_calls": tool_calls if tool_calls else None,
                        "thinking": thinking_content if thinking_content else None
                    })
                else:
                    response = await agent.run(message)
                    logger.info(f"[WS] Non-streaming response: {response.get('content', '')[:50]!r}...")
                    await websocket.send_json({
                        "type": "response",
                        "content": response.get("content", ""),
                        "tool_calls": response.get("tool_calls", [])
                    })

            except Exception as e:
                logger.error(f"[WS] Error: {e}")
                await websocket.send_json({"type": "error", "content": f"Error: {str(e)}"})

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")


@app.get("/api/usage")
async def get_usage():
    """Get token usage statistics."""
    summary = tracker.summary()
    total = tracker.total_cost()
    logger.info(f"[GET /api/usage] providers={list(summary.keys())} total_cost={total}")
    return {
        "providers": summary,
        "total_cost": total
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)