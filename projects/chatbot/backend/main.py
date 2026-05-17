"""
AgentForge Chatbot Backend - FastAPI entry point.
"""

import sys
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("chatbot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await session_manager.create_session("default")
    logger.info("Chatbot backend started!")
    yield
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

app.include_router(router, prefix="/chatbot")

# Mount auth endpoints
from auth import router as auth_router
app.include_router(auth_router, prefix="/chatbot")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
