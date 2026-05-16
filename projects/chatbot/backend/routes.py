import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent import Agent
from agent.types import ThinkingLevel
from models import ChatRequest, HistoryMessage, ToolCall
from session import session_manager
from auth import verify_token

logger = logging.getLogger("chatbot")

router = APIRouter()

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

INDEX_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.get("/")
async def root():
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        return FileResponse(frontend_dist / "index.html", headers=INDEX_HEADERS)
    return {"message": "Frontend not built. Run 'npm run build' in frontend directory."}


@router.post("/api/chat")
async def chat_post(req: ChatRequest, request: Request):
    logger.info(f"[POST /api/chat] Input: {req}")
    # Authenticate
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    user_id = None
    if auth_header and auth_header.lower().startswith("bearer "):
        parts = auth_header.split(None, 1)
        if len(parts) == 2:
            token = parts[1]
            user_id = verify_token(token)
    if not user_id:
        logger.warning("[POST /api/chat] Unauthorized request")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    session_key = f"{user_id}:{req.chat_id}"
    session = session_manager.get_session(session_key)
    if not session:
        session_manager.create_session(session_key)
        session = session_manager.get_session(session_key)
    if not session:
        logger.warning("[POST /api/chat] No session available")
        if req.stream:
            return StreamingResponse(
                iter([f"event: error\ndata: {json.dumps({'message': 'No session available', 'code': 'SESSION_NOT_FOUND'})}\n\n"]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"}
            )
        return {"response": "No session available"}

    agent: Agent = session["agent"]

    if req.stream:
        async def stream_generator():
            thinking_content = ""
            tool_calls: list[ToolCall] = []
            full_content = ""

            try:
                async for chunk in agent.run_stream(req.message, ThinkingLevel.ADAPTIVE if req.thinking else ThinkingLevel.OFF):
                    logger.info(f"[POST /api/chat] Stream chunk: {chunk if isinstance(chunk, str) else json.dumps(chunk, ensure_ascii=False)}")
                    chunk_type = chunk.get("type")
                    if chunk_type == "thinking":
                        if req.thinking:
                            thinking_text = chunk.get("content", "")
                            if thinking_text:
                                thinking_content += thinking_text
                                yield f"event: thinking\ndata: {json.dumps({'content': thinking_text}, ensure_ascii=False)}\n\n"
                    elif chunk_type == "text":
                        text = chunk.get("content", "")
                        full_content += text
                        yield f"event: content\ndata: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
                    elif chunk_type == "tool_use":
                        tool_name = chunk.get("tool_name")
                        tool_call_id = chunk.get("tool_call_id")
                        args = chunk.get("arguments", {})
                        if tool_name:
                            tool_calls.append(ToolCall(call_id=tool_call_id, name=tool_name, arguments=args))
                            yield f"event: tool_call\ndata: {json.dumps({'tool_name': tool_name, 'tool_call_id': tool_call_id, 'arguments': args}, ensure_ascii=False)}\n\n"
                    elif chunk_type == "tool_result":
                        tool_name = chunk.get("tool_name")
                        result = chunk.get("result")
                        tool_call_id = chunk.get("tool_call_id")
                        # Update the tool call with result
                        for tc in tool_calls:
                            if tc.call_id == tool_call_id:
                                tc.result = result
                                tc.status = "completed"
                                break
                        yield f"event: tool_result\ndata: {json.dumps({'tool_name': tool_name, 'result': result, 'tool_call_id': tool_call_id}, ensure_ascii=False)}\n\n"
                    elif chunk_type == "done":
                        logger.info(f"[POST /api/chat] Output: {full_content}")
                        yield f"event: done\ndata: {json.dumps({'content': full_content, 'tool_calls': [{'name': tc.name, 'call_id': tc.call_id} for tc in tool_calls], 'thinking': thinking_content if req.thinking else None, 'usage': {'input_tokens': chunk.get('input_tokens'), 'output_tokens': chunk.get('output_tokens'), 'cache_write_tokens': chunk.get('cache_write_tokens'), 'cache_read_tokens': chunk.get('cache_read_tokens')}}, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error(f"[POST /api/chat] Stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'message': str(e), 'code': type(e).__name__}, ensure_ascii=False)}\n\n"
            finally:
                # Store user message
                await session_manager.add_to_history(
                    session_key,
                    HistoryMessage(role="user", content=req.message)
                )
                # Store assistant response with thinking and tool_calls
                await session_manager.add_to_history(
                    session_key,
                    HistoryMessage(
                        role="assistant",
                        content=full_content,
                        thinking=thinking_content if req.thinking else None,
                        tool_calls=tool_calls if tool_calls else None
                    )
                )

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        try:
            response = await agent.run(req.message, ThinkingLevel.ADAPTIVE if req.thinking else ThinkingLevel.OFF)
            content = response.get("content", "") or ""
            tool_calls_data = response.get("tool_calls") or []
            thinking = response.get("thinking")
            logger.info(f"[POST /api/chat] Output: {content}")
            result = {"response": content, "thinking": thinking, "tool_calls": tool_calls_data}
        except Exception as e:
            logger.error(f"[POST /api/chat] Error: {e}")
            result = {"response": f"Error: {str(e)}"}
            content = f"Error: {str(e)}"
            thinking = None
            tool_calls_data = []
        # Store user message
        await session_manager.add_to_history(
            session_key,
            HistoryMessage(role="user", content=req.message)
        )
        # Store assistant response with thinking and tool_calls
        tool_calls = [
            ToolCall(
                call_id=tc.get("call_id", f"call_{i}"),
                name=tc.get("name", "unknown"),
                status="completed"
            )
            for i, tc in enumerate(tool_calls_data)
        ] if tool_calls_data else None
        await session_manager.add_to_history(
            session_key,
            HistoryMessage(
                role="assistant",
                content=content,
                thinking=thinking if req.thinking else None,
                tool_calls=tool_calls
            )
        )
        return result


@router.delete("/api/session/{chat_id}")
async def delete_session(chat_id: str, request: Request):
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    user_id = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(None, 1)[1]
        user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session_id = f"{user_id}:{chat_id}"
    success = session_manager.delete_session(session_id)
    return {"success": success}


@router.get("/api/sessions")
async def list_sessions(request: Request):
    """List all sessions for the current user."""
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    user_id = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(None, 1)[1]
        user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    sessions = await session_manager.list_sessions(user_id)
    return {"sessions": sessions}


@router.get("/api/history")
async def get_history(request: Request, limit: int = 100, chat_id: str = ...):
    """Get history for a specific chat session (lazy loading)."""
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    user_id = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(None, 1)[1]
        user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session_id = f"{user_id}:{chat_id}"
    history = await session_manager.get_history(session_id, limit=limit)
    return {"history": history}


@router.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("assets/") or full_path.startswith("ws/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        return FileResponse(frontend_dist / "index.html", headers=INDEX_HEADERS)
    return {"message": "Frontend not built. Run 'npm run build' in frontend directory."}
