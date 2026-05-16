"""测试用户认证：注册、登录和Token验证。"""

import sys
import os
from pathlib import Path

# Add parent directory and workspace root to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent.parent.parent))  # workspace root

import sqlite3
import time
from auth import create_user, verify_user, generate_token, verify_token, _init_db

# Clean up test database
TEST_DB = "db/test_users.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)


def test_user_registration():
    """测试用户注册。"""
    print("测试用户注册...")
    
    # 覆盖DB路径用于测试
    from auth import DB_PATH
    
    # 创建测试用户
    success = create_user("testuser1", "password123")
    assert success, "创建用户失败"
    print("  ✓ 用户注册成功")
    
    # 尝试创建重复的用户
    success = create_user("testuser1", "anotherpassword")
    assert not success, "不应该允许重复用户"
    print("  ✓ 拒绝重复用户")


def test_password_verification():
    """测试密码验证。"""
    print("测试密码验证...")
    
    create_user("alice", "secret123")
    
    # 正确的密码
    assert verify_user("alice", "secret123"), "有效密码应该通过验证"
    print("  ✓ 有效密码通过验证")
    
    # 错误的密码
    assert not verify_user("alice", "wrongpassword"), "无效密码应该失败"
    print("  ✓ 无效密码被拒绝")
    
    # 不存在的用户
    assert not verify_user("nonexistent", "anypassword"), "不存在的用户应该失败"
    print("  ✓ 不存在的用户被拒绝")


def test_token_generation_and_verification():
    """测试Token生成和验证。"""
    print("测试Token生成和验证...")
    
    username = "bob"
    create_user(username, "pwd")
    
    # 生成Token
    token = generate_token(username)
    assert token, "应该生成Token"
    assert isinstance(token, str), "Token应该是字符串"
    assert "." in token, "Token应该包含句号分隔符"
    print("  ✓ Token生成成功")
    
    # 验证Token
    verified = verify_token(token)
    assert verified == username, f"Token应该验证为用户名{username}"
    print("  ✓ Token验证正确")
    
    # 无效的Token
    assert verify_token("invalid.token") is None, "无效Token应该返回None"
    print("  ✓ 无效Token被拒绝")
    
    # 被篡改的Token
    parts = token.split(".")
    tampered = parts[0] + ".invalidsignature"
    assert verify_token(tampered) is None, "被篡改的Token应该被拒绝"
    print("  ✓ 被篡改的Token被拒绝")


def test_token_expiry():
    """测试Token过期。"""
    print("测试Token过期...")
    
    username = "charlie"
    create_user(username, "pwd")
    
    # 生成1秒后过期的Token
    token = generate_token(username, expires_in=1)
    
    # 应该立即有效
    assert verify_token(token) == username, "Token应该立即有效"
    print("  ✓ 新Token有效")
    
    # 等待过期
    time.sleep(2)
    
    # 应该已过期
    assert verify_token(token) is None, "已过期的Token应该返回None"
    print("  ✓ 过期Token被拒绝")


if __name__ == "__main__":
    print("=" * 60)
    print("测试认证系统")
    print("=" * 60)
    
    try:
        test_user_registration()
        test_password_verification()
        test_token_generation_and_verification()
        test_token_expiry()
        
        print("\n" + "=" * 60)
        print("所有认证测试通过！✓")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 意外错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
