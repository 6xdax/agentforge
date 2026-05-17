import sqlite3
import time
import os
import uuid
import hashlib
import base64
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from dotenv import load_dotenv
load_dotenv()

DB_PATH = "db/users.db"
_APP_KEY = os.getenv("APP_KEY", "dev-secret-change-me")
bearer_scheme = HTTPBearer()


def _init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at INTEGER
        )
    """
    )
    conn.commit()
    conn.close()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def create_user(username: str, password: str) -> tuple[str, str] | None:
    _init_db()
    user_id = str(uuid.uuid4())
    salt = base64.urlsafe_b64encode(hashlib.sha1(user_id.encode()).digest()).decode()[:16]
    pw = _hash_password(password, salt)
    now = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, pw, salt, now),
        )
        conn.commit()
        return user_id, password
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def verify_user(username: str, password: str) -> str | None:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT user_id, password_hash, salt FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    user_id, pw_hash, salt = row
    if pw_hash != _hash_password(password, salt):
        return None
    return user_id


def get_user_id_by_username(username: str) -> str | None:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


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


@router.post("/api/register")
async def register(body: dict):
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    result = create_user(username, password)
    if not result:
        raise HTTPException(status_code=400, detail="user exists")
    user_id, _ = result
    token = generate_token(user_id)
    return {"token": token}


@router.post("/api/login")
async def login(body: dict):
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    user_id = verify_user(username, password)
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = generate_token(user_id)
    return {"token": token}