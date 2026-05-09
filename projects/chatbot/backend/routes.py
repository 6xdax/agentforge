import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent import Agent
from agent.types import ThinkingLevel
from models import ChatRequest
from session import session_manager
from agent_setup import default_agent

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
async def chat_post(req: ChatRequest):
    logger.info(f"[POST /api/chat] Input: {req}")
    session = session_manager.get_session("default")
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
            tool_calls = []
            full_content = ""

            try:
                async for chunk in agent.run_stream(req.message, ThinkingLevel.ADAPTIVE if req.thinking else ThinkingLevel.OFF):
                    logger.info(f"[POST /api/chat] Stream chunk: {chunk if isinstance(chunk, str) else json.dumps(chunk, ensure_ascii=False)}")
                    chunk_type = chunk.get("type")
                    if chunk_type == "thinking":
                        if req.thinking:
                            thinking_text = chunk.get("content", "")
                            if thinking_text:
                                thinking_content = thinking_text
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
                            tool_calls.append({"name": tool_name, "call_id": tool_call_id})
                            yield f"event: tool_call\ndata: {json.dumps({'tool_name': tool_name, 'tool_call_id': tool_call_id, 'args': args}, ensure_ascii=False)}\n\n"
                    elif chunk_type == "tool_result":
                        tool_name = chunk.get("tool_name")
                        result = chunk.get("result")
                        tool_call_id = chunk.get("tool_call_id")
                        yield f"event: tool_result\ndata: {json.dumps({'tool_name': tool_name, 'result': result, 'tool_call_id': tool_call_id}, ensure_ascii=False)}\n\n"
                    elif chunk_type == "done":
                        logger.info(f"[POST /api/chat] Output: {full_content}")
                        yield f"event: done\ndata: {json.dumps({'content': full_content, 'tool_calls': tool_calls, 'thinking': thinking_content if req.thinking else None, 'usage': {'input_tokens': chunk.get('input_tokens'), 'output_tokens': chunk.get('output_tokens'), 'cache_write_tokens': chunk.get('cache_write_tokens'), 'cache_read_tokens': chunk.get('cache_read_tokens')}}, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error(f"[POST /api/chat] Stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'message': str(e), 'code': type(e).__name__}, ensure_ascii=False)}\n\n"
            finally:
                await session_manager.add_to_history("default", "user", req.message)
                await session_manager.add_to_history("default", "assistant", full_content)

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
            tool_calls = response.get("tool_calls") or []
            thinking = response.get("thinking")
            logger.info(f"[POST /api/chat] Output: {content}")
            result = {"response": content, "thinking": thinking, "tool_calls": tool_calls}
        except Exception as e:
            logger.error(f"[POST /api/chat] Error: {e}")
            result = {"response": f"Error: {str(e)}"}
        await session_manager.add_to_history("default", "user", req.message)
        await session_manager.add_to_history("default", "assistant", content)
        return result


@router.get("/api/history")
async def get_history(limit: int = 100):
    history = await session_manager.get_history("default", limit=limit)
    return {"history": history}


@router.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("assets/") or full_path.startswith("ws/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        return FileResponse(frontend_dist / "index.html", headers=INDEX_HEADERS)
    return {"message": "Frontend not built. Run 'npm run build' in frontend directory."}
