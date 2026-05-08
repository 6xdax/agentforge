"""
AgentForge Chatbot Backend - FastAPI server with MiniMax provider and streaming support.
"""

import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import json
from typing import Optional, AsyncGenerator, Union
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("chatbot")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel


# =============================================================================
# SSE Message Protocol - 统一的事件类型定义
# =============================================================================

class SSEEventType(str, Enum):
    """SSE 事件类型枚举"""
    THINKING = "thinking"       # AI 思考过程
    TOOL_CALL = "tool_call"     # 工具调用开始
    TOOL_RESULT = "tool_result" # 工具调用结果
    CONTENT = "content"         # 普通文本内容
    DONE = "done"              # 完成信号
    ERROR = "error"            # 错误


@dataclass
class SSEMessage:
    """SSE 消息结构"""
    event: SSEEventType
    data: dict

    def to_sse_format(self) -> str:
        """转换为 SSE 格式字符串"""
        lines = [f"event: {self.event.value}", f"data: {json.dumps(self.data, ensure_ascii=False)}", ""]
        return "\n".join(lines) + "\n"


def sse_event(event: SSEEventType, data: dict) -> str:
    """快捷函数：生成 SSE 格式字符串"""
    return SSEMessage(event=event, data=data).to_sse_format()


def sse_content(content: str) -> str:
    """文本内容事件"""
    return sse_event(SSEEventType.CONTENT, {"content": content})


def sse_thinking(content: str) -> str:
    """思考事件"""
    return sse_event(SSEEventType.THINKING, {"content": content})


def sse_tool_call(tool_name: str, tool_call_id: str = None, args: dict = None) -> str:
    """工具调用事件"""
    return sse_event(SSEEventType.TOOL_CALL, {
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "args": args or {}
    })


def sse_tool_result(tool_name: str, result: str, tool_call_id: str = None) -> str:
    """工具结果事件"""
    return sse_event(SSEEventType.TOOL_RESULT, {
        "tool_name": tool_name,
        "result": result,
        "tool_call_id": tool_call_id
    })


def sse_done(content: str = "", tool_calls: list = None, thinking: str = None, usage: dict = None) -> str:
    """完成事件"""
    return sse_event(SSEEventType.DONE, {
        "content": content,
        "tool_calls": tool_calls or [],
        "thinking": thinking,
        "usage": usage or {}
    })


def sse_error(message: str, code: str = None) -> str:
    """错误事件"""
    return sse_event(SSEEventType.ERROR, {
        "message": message,
        "code": code
    })

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
    """POST endpoint with SSE streaming support.

    SSE event types:
    - thinking: AI 思考过程 (当 thinking=true 时)
    - tool_call: 工具调用开始
    - tool_result: 工具调用结果
    - content: 普通文本内容
    - done: 完成信号 (包含最终内容和统计)
    - error: 错误信息
    """
    logger.info(f"[POST /api/chat] message={req.message[:50]!r}... stream={req.stream} thinking={req.thinking}")
    session = session_manager.get_session("default")
    if not session:
        logger.warning("[POST /api/chat] No session available")
        if req.stream:
            return StreamingResponse(
                iter([sse_error("No session available", "SESSION_NOT_FOUND")]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"}
            )
        return ChatResponse(response="No session available")

    agent = session["agent"]

    if req.stream:
        async def stream_generator():
            thinking_content = ""
            tool_calls = []
            full_content = ""

            try:
                async for chunk in agent.run_stream(req.message):
                    logger.info(f"[POST /api/chat] Stream chunk: {chunk}")
                    if isinstance(chunk, dict):
                        chunk_type = chunk.get("type")
                        if chunk_type == "thinking":
                            if req.thinking:
                                thinking_text = chunk.get("content", "")
                                if thinking_text:
                                    thinking_content = thinking_text
                                    yield sse_thinking(thinking_text)
                        elif chunk_type == "tool_call":
                            tool_name = chunk.get("tool_name")
                            tool_call_id = chunk.get("tool_call_id")
                            args = chunk.get("args")
                            if tool_name:
                                tool_calls.append({"name": tool_name, "call_id": tool_call_id})
                                yield sse_tool_call(tool_name, tool_call_id, args)
                        elif chunk_type == "tool_result":
                            tool_name = chunk.get("tool_name")
                            result = chunk.get("result")
                            tool_call_id = chunk.get("tool_call_id")
                            yield sse_tool_result(tool_name, result, tool_call_id)
                        elif chunk_type == "done":
                            # Done chunk - usage stats available
                            usage = chunk.get("usage", {})
                            yield sse_done(
                                content=full_content,
                                tool_calls=tool_calls,
                                thinking=thinking_content if req.thinking else None,
                                usage=usage
                            )
                    else:
                        # String content chunk
                        full_content += chunk
                        yield sse_content(chunk)

            except Exception as e:
                logger.error(f"[POST /api/chat] Stream error: {e}")
                yield sse_error(str(e), type(e).__name__)

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
            }
        )
    else:
        try:
            logger.info("[POST /api/chat] Using non-streaming response")
            response = await agent.run(req.message)
            content = response.get("content", "") or ""
            tool_calls = response.get("tool_calls") or []
            thinking = response.get("thinking")
            logger.info(f"[POST /api/chat] Response complete: {content[:50]!r}... tool_calls={len(tool_calls)}")
            return ChatResponse(
                response=content,
                thinking=thinking,
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
    uvicorn.run(app, host="0.0.0.0", port=9000)