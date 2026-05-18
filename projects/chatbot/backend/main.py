"""
AgentForge Chatbot Backend - FastAPI entry point.
"""

import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Add workspace root to Python path so we can import config, agent, etc.
workspace_root = Path(__file__).parent.parent.parent
src_dir = workspace_root / "src"
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from session import session_manager
from routes import router
from ai_news import run_daily_ai_news_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("chatbot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await session_manager.create_session("default")
    ai_news_task = asyncio.create_task(run_daily_ai_news_job())
    logger.info("Chatbot backend started!")
    yield
    ai_news_task.cancel()
    try:
        await ai_news_task
    except asyncio.CancelledError:
        pass
    logger.info("Chatbot backend shutting down!")


app = FastAPI(title="AgentForge Chatbot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://enxhub\.online.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
app.mount("/chatbot/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

# Serve agentforge docs
from fastapi.responses import FileResponse
docs_dir = Path(__file__).parent.parent.parent.parent / "docs"

@app.get("/agentdocs", include_in_schema=False)
@app.get("/agentdocs/", include_in_schema=False)
async def agentdocs_index():
    return FileResponse(str(docs_dir / "index.html"))

@app.get("/agentdocs/{path:path}", include_in_schema=False)
async def agentdocs_static(path: str):
    file_path = docs_dir / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(docs_dir / "index.html"))

app.include_router(router, prefix="/chatbot")

# Mount auth endpoints
from auth import router as auth_router
app.include_router(auth_router, prefix="/chatbot")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
