import sqlite3
import time
import hmac
import hashlib
import base64
import os
from typing import Optional

from fastapi import APIRouter, HTTPException

DB_PATH = "db/users.db"
_SECRET = os.environ.get("AGENTFORGE_AUTH_SECRET", "dev-secret-change-me")


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


def create_user(username: str, password: str) -> Optional[str]:
    _init_db()
    import uuid
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
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def verify_user(username: str, password: str) -> Optional[str]:
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


def get_user_id_by_username(username: str) -> Optional[str]:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def generate_token(user_id: str, expires_in: int = 60 * 60 * 24) -> str:
    exp = int(time.time()) + expires_in
    payload = f"{user_id}|{exp}"
    sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(payload.encode()).decode() + "." + base64.urlsafe_b64encode(sig).decode()
    return token


def verify_token(token: str) -> Optional[str]:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b, sig_b = parts
        payload = base64.urlsafe_b64decode(payload_b.encode()).decode()
        expected_sig = base64.urlsafe_b64encode(hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(expected_sig, sig_b):
            return None
        user_id, exp_s = payload.split("|")
        if int(exp_s) < int(time.time()):
            return None
        return user_id
    except Exception:
        return None


router = APIRouter()


@router.post("/api/register")
async def register(body: dict):
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    user_id = create_user(username, password)
    if not user_id:
        raise HTTPException(status_code=400, detail="user exists")
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
