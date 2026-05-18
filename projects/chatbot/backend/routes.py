import json
import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Security
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent import Agent
from agent.types import ThinkingLevel
from user_config import (
    get_mcp_config as load_user_mcp_config,
    get_skill_config as load_user_skill_config,
    get_tool_config as load_user_tool_config,
    update_mcp_config as save_user_mcp_config,
    update_skill_config as save_user_skill_config,
    update_tool_config as save_user_tool_config,
)
from models import AttachmentRef, ChatRequest, HistoryMessage, ToolCall, LinkSquareCreateRequest, LinkSquareUpdateRequest
from session import session_manager
from auth import verify_token
from tools.file_parser import parse_document
from db.database import create_sessionmaker_for, init_database
from db.models import LinkSquare, User, AiNewsItem
from sqlalchemy import select
from ai_news import crawl_and_store_ai_news

logger = logging.getLogger("chatbot")

router = APIRouter()

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
user_data_root = Path(__file__).parent / "user_data"

INDEX_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


DB_PATH = "db/data/app.db"


def _validate_link_payload(name: str, url: str) -> tuple[str, str]:
    normalized_name = name.strip()
    normalized_url = url.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Link name is required")
    if len(normalized_name) > 128:
        raise HTTPException(status_code=400, detail="Link name must be <= 128 chars")
    if not normalized_url:
        raise HTTPException(status_code=400, detail="Link url is required")
    if len(normalized_url) > 2048:
        raise HTTPException(status_code=400, detail="Link url must be <= 2048 chars")
    if not (normalized_url.startswith("/") or re.match(r"^https?://", normalized_url, flags=re.IGNORECASE)):
        raise HTTPException(status_code=400, detail="Link url must start with / or http(s)://")
    return normalized_name, normalized_url


@router.get("/")
async def root():
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        return FileResponse(frontend_dist / "index.html", headers=INDEX_HEADERS)
    return {"message": "Frontend not built. Run 'npm run build' in frontend directory."}


@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Security(verify_token),
):

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    original_name = Path(file.filename).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name) or "uploaded_file"

    user_dir = user_data_root / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{int(time.time() * 1000)}_{safe_name}"
    saved_path = user_dir / stored_name
    relative_saved_path = (Path(user_id) / stored_name).as_posix()

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    saved_path.write_bytes(file_bytes)

    return {
        "file_name": original_name,
        "stored_name": stored_name,
        "saved_path": relative_saved_path,
        "size": len(file_bytes),
    }


@router.post("/api/chat")
async def chat_post(req: ChatRequest, user_id: str = Security(verify_token)):
    
    session_key = f"{user_id}:{req.chat_id}"
    user_dir = (user_data_root / user_id).resolve()

    file_attachments: list[AttachmentRef] = []
    if req.file_attachments:
        file_attachments = [
            AttachmentRef(
                file_name=item.file_name,
                saved_path=item.saved_path,
                size=item.size,
            )
            for item in req.file_attachments
            if item.saved_path
        ]
    elif req.file_paths:
        file_attachments = [
            AttachmentRef(
                file_name=Path(raw_path).name,
                saved_path=raw_path,
            )
            for raw_path in req.file_paths
            if raw_path
        ]

    file_paths = [item.saved_path for item in file_attachments]

    parsed_file_blocks: list[str] = []
    for raw_path in file_paths:
        try:
            raw_candidate = Path(raw_path)
            if raw_candidate.is_absolute():
                candidate_resolved = raw_candidate.resolve()
            else:
                candidate_resolved = (user_data_root / raw_candidate).resolve()
            if user_dir not in candidate_resolved.parents and candidate_resolved != user_dir:
                parsed_file_blocks.append(f"[File parse skipped] {raw_candidate.name}: invalid file path")
                continue
            if not candidate_resolved.exists() or not candidate_resolved.is_file():
                parsed_file_blocks.append(f"[File parse skipped] {raw_candidate.name}: file not found")
                continue

            parsed_text = await parse_document(str(candidate_resolved), max_text_length=12000)
            parsed_file_blocks.append(
                f"File: {candidate_resolved.name}\n"
                f"Path: {candidate_resolved}\n"
                "Content:\n"
                f"{parsed_text}"
            )
        except Exception as exc:
            file_name = Path(raw_path).name if raw_path else "unknown"
            parsed_file_blocks.append(f"[File parse failed] {file_name}: {exc}")

    agent_message = req.message
    if parsed_file_blocks:
        files_context = "\n\n".join(parsed_file_blocks)
        agent_message = (
            f"{req.message}\n\n"
            "The user has uploaded file(s). Use the following extracted content as additional context:\n\n"
            f"{files_context}"
        )
    session = session_manager.get_session(session_key)
    if not session:
        await session_manager.create_session(session_key)
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
                async for chunk in agent.run_stream(agent_message, ThinkingLevel.ADAPTIVE if req.thinking else ThinkingLevel.OFF):
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
                    HistoryMessage(role="user", content=req.message, attachments=file_attachments or None)
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
            response = await agent.run(agent_message, ThinkingLevel.ADAPTIVE if req.thinking else ThinkingLevel.OFF)
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
            HistoryMessage(role="user", content=req.message, attachments=file_attachments or None)
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
async def delete_session(chat_id: str, user_id: str = Security(verify_token)):
    session_id = f"{user_id}:{chat_id}"
    session_attachment_paths = await session_manager.get_session_attachment_paths(session_id)
    other_attachment_paths = await session_manager.get_attachment_paths_for_other_sessions(user_id, session_id)
    success = await session_manager.delete_session(session_id)

    to_delete = session_attachment_paths - other_attachment_paths
    user_dir = (user_data_root / user_id).resolve()

    for saved_path in to_delete:
        try:
            target = (user_data_root / saved_path).resolve()
            if user_dir not in target.parents or not target.is_file():
                continue
            target.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning(f"Failed to delete uploaded file for session {session_id}: {saved_path}, error={exc}")

    return {"success": success}


@router.get("/api/sessions")
async def list_sessions(user_id: str = Security(verify_token)):
    sessions = await session_manager.list_sessions(user_id)
    return {"sessions": sessions}


@router.get("/api/history")
async def get_history(limit: int = 100, chat_id: str = ..., user_id: str = Security(verify_token)):
    session_id = f"{user_id}:{chat_id}"
    history = await session_manager.get_history(session_id, limit=limit)
    return {"history": history}


@router.get("/api/square-links")
async def list_square_links(user_id: str = Security(verify_token)):
    await init_database(DB_PATH)
    sessionmaker = create_sessionmaker_for(DB_PATH)
    async with sessionmaker() as session:
        rows = await session.scalars(select(LinkSquare).order_by(LinkSquare.created_at.desc(), LinkSquare.id.desc()))
        links = [
            {
                "id": row.id,
                "name": row.name,
                "url": row.url,
                "owner_user_id": row.owner_user_id,
                "owner_username": row.owner_username,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "is_mine": row.owner_user_id == user_id,
            }
            for row in rows.all()
        ]
    return {"links": links}


@router.post("/api/square-links")
async def create_square_link(req: LinkSquareCreateRequest, user_id: str = Security(verify_token)):
    name, url = _validate_link_payload(req.name, req.url)
    await init_database(DB_PATH)
    sessionmaker = create_sessionmaker_for(DB_PATH)
    async with sessionmaker() as session:
        owner_username = await session.scalar(select(User.username).where(User.user_id == user_id))
        if not owner_username:
            raise HTTPException(status_code=401, detail="User not found")
        now = int(time.time())
        link = LinkSquare(
            name=name,
            url=url,
            owner_user_id=user_id,
            owner_username=owner_username,
            created_at=now,
            updated_at=now,
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
    return {
        "link": {
            "id": link.id,
            "name": link.name,
            "url": link.url,
            "owner_user_id": link.owner_user_id,
            "owner_username": link.owner_username,
            "created_at": link.created_at,
            "updated_at": link.updated_at,
            "is_mine": True,
        }
    }


@router.put("/api/square-links/{link_id}")
async def update_square_link(link_id: int, req: LinkSquareUpdateRequest, user_id: str = Security(verify_token)):
    name, url = _validate_link_payload(req.name, req.url)
    await init_database(DB_PATH)
    sessionmaker = create_sessionmaker_for(DB_PATH)
    async with sessionmaker() as session:
        link = await session.scalar(select(LinkSquare).where(LinkSquare.id == link_id))
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")
        if link.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="You can only edit your own links")
        link.name = name
        link.url = url
        link.updated_at = int(time.time())
        await session.commit()
        await session.refresh(link)
    return {
        "link": {
            "id": link.id,
            "name": link.name,
            "url": link.url,
            "owner_user_id": link.owner_user_id,
            "owner_username": link.owner_username,
            "created_at": link.created_at,
            "updated_at": link.updated_at,
            "is_mine": True,
        }
    }


@router.delete("/api/square-links/{link_id}")
async def delete_square_link(link_id: int, user_id: str = Security(verify_token)):
    await init_database(DB_PATH)
    sessionmaker = create_sessionmaker_for(DB_PATH)
    async with sessionmaker() as session:
        link = await session.scalar(select(LinkSquare).where(LinkSquare.id == link_id))
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")
        if link.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="You can only delete your own links")
        await session.delete(link)
        await session.commit()
    return {"success": True}


@router.get("/api/config/tools")
async def get_tool_config(user_id: str = Security(verify_token)):
    return await load_user_tool_config(user_id)


@router.post("/api/config/tools")
async def update_tool_config(req: dict, user_id: str = Security(verify_token)):
    try:
        result = await save_user_tool_config(user_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session_manager.reset_user_sessions(user_id)
    return {"status": "ok", "config": result}


@router.get("/api/config/mcp")
async def get_mcp_config(user_id: str = Security(verify_token)):
    return await load_user_mcp_config(user_id)


@router.post("/api/config/mcp")
async def update_mcp_config(req: dict, user_id: str = Security(verify_token)):
    try:
        result = await save_user_mcp_config(user_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session_manager.reset_user_sessions(user_id)
    return {"status": "ok", "config": result}


@router.get("/api/config/skills")
async def get_skill_config(user_id: str = Security(verify_token)):
    return await load_user_skill_config(user_id)


@router.post("/api/config/skills")
async def update_skill_config(req: dict, user_id: str = Security(verify_token)):
    try:
        result = await save_user_skill_config(user_id, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session_manager.reset_user_sessions(user_id)
    return {"status": "ok", "config": result}


@router.get("/api/ai-news")
async def list_ai_news(limit: int = 50, user_id: str = Security(verify_token)):
    safe_limit = max(1, min(limit, 200))
    await init_database(DB_PATH)
    sessionmaker = create_sessionmaker_for(DB_PATH)
    async with sessionmaker() as session:
        rows = await session.scalars(
            select(AiNewsItem)
            .order_by(AiNewsItem.published_at.desc(), AiNewsItem.id.desc())
            .limit(safe_limit)
        )
        items = [
            {
                "id": row.id,
                "title": row.title,
                "url": row.url,
                "source": row.source,
                "summary": row.summary,
                "published_at": row.published_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows.all()
        ]
    return {"items": items}


@router.post("/api/ai-news/refresh")
async def refresh_ai_news(user_id: str = Security(verify_token)):
    stats = await crawl_and_store_ai_news()
    return {"status": "ok", "stats": stats}


@router.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("assets/") or full_path.startswith("ws/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        return FileResponse(frontend_dist / "index.html", headers=INDEX_HEADERS)
    return {"message": "Frontend not built. Run 'npm run build' in frontend directory."}
