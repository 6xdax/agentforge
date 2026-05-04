"""
AgentForge Chatbot Backend - FastAPI server with WebSocket support.
"""

from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import json
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import Agent, ToolRegistry, InMemoryMemory
from agent.provider import LLMProvider
from agent.types import LLMResponse
from agent.registry import tool_result


# Request/Response models
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
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


# Demo provider for testing (no real LLM calls)
class DemoProvider(LLMProvider):
    """Demo provider that responds with canned responses for testing."""

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        thinking: Optional = None,
    ) -> LLMResponse:
        last_msg = messages[-1]["content"] if messages else ""

        # Simple echo for demo
        if "hello" in last_msg.lower():
            content = "Hello! I'm a demo chatbot. How can I help you today?"
        elif "bye" in last_msg.lower() or "goodbye" in last_msg.lower():
            content = "Goodbye! Have a great day!"
        elif "capabilities" in last_msg.lower() or "what can you do" in last_msg.lower():
            content = "I can chat with you and help answer questions. I'm running on the AgentForge framework with FastAPI!"
        else:
            content = f"I received your message: '{last_msg}'. This is a demo chatbot powered by AgentForge + FastAPI."

        return {
            "content": content,
            "tool_calls": None,
            "thinking": None,
            "usage": {"input_tokens": 50, "output_tokens": 100},
        }


# Global registry and agent
registry = ToolRegistry()
memory = InMemoryMemory()


def setup_demo_tools():
    """Register some demo tools."""

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


# Setup tools on startup
setup_demo_tools()

# Create demo agent
demo_agent = Agent(provider=DemoProvider(), registry=registry, memory=memory)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    session_manager.create_session("default", demo_agent)
    print("Chatbot backend started!")
    yield
    # Shutdown
    print("Chatbot backend shutting down!")


static_dir = Path(__file__).parent / "static"

app = FastAPI(title="AgentForge Chatbot", lifespan=lifespan)

# Mount static files directory
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(static_dir / "index.html")


@app.get("/api/chat")
async def chat_get(q: str):
    """Simple GET endpoint for testing."""
    session = session_manager.get_session("default")
    if not session:
        return {"response": "No session available"}

    agent = session["agent"]
    try:
        response = await agent.run(q)
        return {
            "response": response.get("content", ""),
            "tool_calls": response.get("tool_calls", []),
        }
    except Exception as e:
        return {"response": f"Error: {str(e)}", "tool_calls": []}


@app.post("/api/chat")
async def chat_post(req: ChatRequest):
    """POST endpoint for chat."""
    session = session_manager.get_session("default")
    if not session:
        return ChatResponse(response="No session available")

    agent = session["agent"]
    try:
        response = await agent.run(req.message)
        session_manager.add_to_history("default", "user", req.message)
        session_manager.add_to_history("default", "assistant", response.get("content", ""))

        return ChatResponse(
            response=response.get("content", ""),
            tool_calls=response.get("tool_calls"),
        )
    except Exception as e:
        return ChatResponse(response=f"Error: {str(e)}")


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat."""
    await websocket.accept()

    # Use default session
    session = session_manager.get_session("default")
    if not session:
        await websocket.send_json({"error": "No session available"})
        await websocket.close()
        return

    agent = session["agent"]

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            msg_data = json.loads(data)
            message = msg_data.get("message", "")

            if not message:
                continue

            # Run agent
            try:
                response = await agent.run(message)
                content = response.get("content", "")

                # Send response
                await websocket.send_json({
                    "type": "response",
                    "content": content,
                    "tool_calls": response.get("tool_calls", []),
                })

                # Add to history
                session_manager.add_to_history("default", "user", message)
                session_manager.add_to_history("default", "assistant", content)

            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Error: {str(e)}",
                })

    except WebSocketDisconnect:
        print("WebSocket disconnected")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)