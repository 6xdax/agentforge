import time
import os
import uuid
import hashlib
import base64
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select

from dotenv import load_dotenv
load_dotenv()

from db.database import create_sessionmaker_for, init_database
from db.models import User

DB_PATH = "db/data/app.db"
_APP_KEY = os.getenv("APP_KEY", "dev-secret-change-me")
bearer_scheme = HTTPBearer(auto_error=False)


async def _init_db(database_url: str | None = None):
    await init_database(database_url or DB_PATH)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


async def create_user(username: str, password: str, database_url: str | None = None) -> tuple[str, str] | None:
    await _init_db(database_url)
    user_id = str(uuid.uuid4())
    salt = base64.urlsafe_b64encode(hashlib.sha1(user_id.encode()).digest()).decode()[:16]
    pw = _hash_password(password, salt)
    sessionmaker = create_sessionmaker_for(database_url or DB_PATH)
    async with sessionmaker() as session:
        existing = await session.scalar(select(User.user_id).where(User.username == username))
        if existing is not None:
            return None
        session.add(
            User(
                user_id=user_id,
                username=username,
                password_hash=pw,
                salt=salt,
                created_at=int(time.time()),
            )
        )
        await session.commit()
        return user_id, password


async def verify_user(username: str, password: str, database_url: str | None = None) -> str | None:
    await _init_db(database_url)
    sessionmaker = create_sessionmaker_for(database_url or DB_PATH)
    async with sessionmaker() as session:
        row = await session.scalar(select(User).where(User.username == username))
    if not row:
        return None
    if row.password_hash != _hash_password(password, row.salt):
        return None
    return row.user_id


async def get_user_id_by_username(username: str, database_url: str | None = None) -> str | None:
    await _init_db(database_url)
    sessionmaker = create_sessionmaker_for(database_url or DB_PATH)
    async with sessionmaker() as session:
        return await session.scalar(select(User.user_id).where(User.username == username))


def generate_token(user_id: str, expires_in: int = 60 * 60 * 24) -> str:
    """Generate JWT token for user."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=expires_in)
    payload = {
        "user_id": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, _APP_KEY, algorithm="HS256")


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
) -> str:
    """FastAPI Security dependency for bearer token verification.

    Usage:
        async def endpoint(auth_payload: dict = Security(verify_token)):

    Returns:
        user_id string from verified token

    Raises:
        HTTPException 401 if missing or invalid
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")

    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Missing token value")

    try:
        payload = jwt.decode(token, _APP_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token signature")


router = APIRouter()


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/api/register")
async def register(body: AuthRequest):
    username = body.username
    password = body.password
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    result = await create_user(username, password)
    if not result:
        raise HTTPException(status_code=400, detail="user exists")
    user_id, _ = result
    token = generate_token(user_id)
    return {"token": token}


@router.post("/api/login")
async def login(body: AuthRequest):
    username = body.username
    password = body.password
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    user_id = await verify_user(username, password)
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = generate_token(user_id)
    return {"token": token}