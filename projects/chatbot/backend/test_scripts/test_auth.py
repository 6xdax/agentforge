"""测试用户认证：注册、登录和Token验证。"""

import sys
import asyncio
import sqlite3
import time
import uuid
from pathlib import Path

# Add parent directory and workspace root to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent.parent.parent))  # workspace root

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from auth import create_user, verify_user, generate_token, verify_token
from db.database import DEFAULT_DB_PATH

TEST_RUN_ID = uuid.uuid4().hex[:8]
TEST_USER_PREFIX = f"test-auth-{TEST_RUN_ID}"


def make_username(label: str) -> str:
    return f"{TEST_USER_PREFIX}-{label}"


def cleanup_real_test_users() -> None:
    conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    conn.execute("DELETE FROM users WHERE username LIKE ?", (f"{TEST_USER_PREFIX}%",))
    conn.commit()
    conn.close()


async def test_user_registration():
    """测试用户注册。"""
    print("测试用户注册...")
    username = make_username("register")
    
    # 创建测试用户
    success = await create_user(username, "password123")
    assert success, "创建用户失败"
    print("  ✓ 用户注册成功")
    
    # 尝试创建重复的用户
    success = await create_user(username, "anotherpassword")
    assert not success, "不应该允许重复用户"
    print("  ✓ 拒绝重复用户")


async def test_password_verification():
    """测试密码验证。"""
    print("测试密码验证...")
    username = make_username("alice")
    
    await create_user(username, "secret123")
    
    # 正确的密码
    assert await verify_user(username, "secret123"), "有效密码应该通过验证"
    print("  ✓ 有效密码通过验证")
    
    # 错误的密码
    assert not await verify_user(username, "wrongpassword"), "无效密码应该失败"
    print("  ✓ 无效密码被拒绝")
    
    # 不存在的用户
    assert not await verify_user(make_username("nonexistent"), "anypassword"), "不存在的用户应该失败"
    print("  ✓ 不存在的用户被拒绝")


async def test_token_generation_and_verification():
    """测试Token生成和验证。"""
    print("测试Token生成和验证...")
    
    username = make_username("bob")
    result = await create_user(username, "pwd")
    assert result is not None, "创建用户失败"
    user_id, _ = result
    
    # 生成Token
    token = generate_token(user_id)
    assert token, "应该生成Token"
    assert isinstance(token, str), "Token应该是字符串"
    assert "." in token, "Token应该包含句号分隔符"
    print("  ✓ Token生成成功")
    
    # 验证Token
    verified = verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert verified == user_id, f"Token应该验证为用户ID{user_id}"
    print("  ✓ Token验证正确")
    
    # 无效的Token
    try:
        verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token"))
        raise AssertionError("无效Token应该被拒绝")
    except HTTPException:
        print("  ✓ 无效Token被拒绝")
    
    # 被篡改的Token
    parts = token.split(".")
    tampered = parts[0] + ".invalidsignature"
    try:
        verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=tampered))
        raise AssertionError("被篡改的Token应该被拒绝")
    except HTTPException:
        print("  ✓ 被篡改的Token被拒绝")


async def test_token_expiry():
    """测试Token过期。"""
    print("测试Token过期...")
    
    username = make_username("charlie")
    result = await create_user(username, "pwd")
    assert result is not None, "创建用户失败"
    user_id, _ = result
    
    # 生成1秒后过期的Token
    token = generate_token(user_id, expires_in=1)
    
    # 应该立即有效
    assert verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)) == user_id, "Token应该立即有效"
    print("  ✓ 新Token有效")
    
    # 等待过期
    time.sleep(2)
    
    # 应该已过期
    try:
        verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
        raise AssertionError("已过期的Token应该被拒绝")
    except HTTPException:
        print("  ✓ 过期Token被拒绝")


if __name__ == "__main__":
    print("=" * 60)
    print("测试认证系统")
    print("=" * 60)
    cleanup_real_test_users()
    
    try:
        asyncio.run(test_user_registration())
        asyncio.run(test_password_verification())
        asyncio.run(test_token_generation_and_verification())
        asyncio.run(test_token_expiry())
        
        print("\n" + "=" * 60)
        print("所有认证测试通过！✓")
        print("=" * 60)
        cleanup_real_test_users()
    except AssertionError as e:
        cleanup_real_test_users()
        print(f"\n❌ 测试失败：{e}")
        sys.exit(1)
    except Exception as e:
        cleanup_real_test_users()
        print(f"\n❌ 意外错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
