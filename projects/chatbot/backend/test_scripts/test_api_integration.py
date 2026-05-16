"""用户系统 API的集成测试。"""

import sys
import os
import time
import subprocess
import requests
import json
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:8000/chatbot"
SERVER_STARTUP_TIMEOUT = 10
CLEANUP_DBS = True


def cleanup_databases():
    """删除测试数据库以便从新开始。"""
    if CLEANUP_DBS:
        for db_file in ["db/users.db", "db/chatbot_memory.db"]:
            if os.path.exists(db_file):
                os.remove(db_file)
                print(f"  清理{db_file}")

        # 清理旧数据库文件（可能存在于多个位置）
        for path in [".", "..", "../..", "../../.."]:
            for db in ["users.db", "chatbot_memory.db"]:
                full_path = os.path.join(path, db)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                        print(f"  清理{full_path}")
                    except:
                        pass


def wait_for_server(timeout=SERVER_STARTUP_TIMEOUT):
    """等待服务器就绪。"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{BASE_URL}/")
            if response.status_code in [200, 404]:  # 404 is fine for API
                print("  ✓ 服务器就绪")
                return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)
    raise TimeoutError(f"服务器未能在{timeout}秒内启动")


def test_user_registration():
    """测试用户注册端点。"""
    print("测试用户注册 API...")

    # 注册新用户
    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "testuser",
        "password": "password123"
    })
    if resp.status_code == 400 and "user exists" in resp.text:
        print("  ℹ 用户已存在，跳过注册（这是预期的）")
    else:
        assert resp.status_code == 200, f"注册失败：{resp.status_code} {resp.text}"
        assert resp.json().get("ok") == True, "应用程序需要ok=true"
        print("  ✓ 用户注册成功")
    
    # 尝试注册重复的用户
    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "testuser",
        "password": "otherpassword"
    })
    assert resp.status_code == 400, f"应该拒绝重复，得到{resp.status_code}"
    print("  ✓ 拒绝重复用户")
    
    # 缺少字段
    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "onlyuser"
    })
    assert resp.status_code == 400, "应该拒绝缺少密码"
    print("  ✓ 拒绝缺少密码")


def test_user_login():
    """测试用户登录端点。"""
    print("测试用户登录 API...")

    # 先注册用户（如果不存在）
    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "alice",
        "password": "alicepass"
    })
    if resp.status_code == 400 and "user exists" in resp.text:
        print("  ℹ 用户已存在")
    else:
        assert resp.status_code == 200, f"注册失败：{resp.status_code} {resp.text}"
        print("  ✓ 用户注册成功")
    
    # 有效登录
    resp = requests.post(f"{BASE_URL}/api/login", json={
        "username": "alice",
        "password": "alicepass"
    })
    assert resp.status_code == 200, f"登录失败：{resp.text}"
    data = resp.json()
    assert "token" in data, "响应应包含token"
    assert isinstance(data["token"], str), "Token应是字符串"
    assert "." in data["token"], "Token应包含句号"
    token = data["token"]
    print(f"  ✓ 用户登录成功，token：{token[:20]}...")
    
    # 错误的密码
    resp = requests.post(f"{BASE_URL}/api/login", json={
        "username": "alice",
        "password": "wrongpassword"
    })
    assert resp.status_code == 401, f"错误密码应该失败，得到{resp.status_code}"
    print("  ✓ 错误密码被拒绝")
    
    # 不存在的用户
    resp = requests.post(f"{BASE_URL}/api/login", json={
        "username": "nonexistent",
        "password": "anypass"
    })
    assert resp.status_code == 401, "不存在的用户应该失败"
    print("  ✓ 不存在的用户被拒绝")
    
    return token


def test_chat_without_auth():
    """测试聊天需要认证。"""
    print("测试聊天认证要求...")

    # 不使token聊天（需要chat_id）
    resp = requests.post(f"{BASE_URL}/api/chat", json={
        "chat_id": "testchat",
        "message": "你好",
        "stream": False
    })
    assert resp.status_code == 401, f"应该要求认证，得到{resp.status_code}"
    print("  ✓ 不使token的聊天被拒绝（401）")

    # 无效token聊天
    resp = requests.post(
        f"{BASE_URL}/api/chat",
        json={"chat_id": "testchat", "message": "你好", "stream": False},
        headers={"Authorization": "Bearer invalid.token"}
    )
    assert resp.status_code == 401, "无效token应该被拒绝"
    print("  ✓ 无效token的聊天被拒绝")


def test_chat_with_auth(token):
    """测试使token聊天。"""
    print("测试用token聊天...")

    # 使token聊天
    resp = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "chat_id": "testchat",
            "message": "2+2是多少？",
            "stream": False,
            "thinking": False
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"聊天失败：{resp.status_code} {resp.text}"
    data = resp.json()
    assert "response" in data, "响应应包含'response'字段"
    print(f"  ✓ 聊天成功，答复：{data['response'][:50]}...")


def test_history_without_auth():
    """测试历史需要认证。"""
    print("测试历史认证要求...")

    # 不使token查询历史（需要chat_id参数）
    resp = requests.get(f"{BASE_URL}/api/history?chat_id=test")
    assert resp.status_code == 401, f"应该要求认证，得到{resp.status_code}"
    print("  ✓ 不使token的历史被拒绝")

    # 无效token查询历史
    resp = requests.get(
        f"{BASE_URL}/api/history?chat_id=test",
        headers={"Authorization": "Bearer invalid.token"}
    )
    assert resp.status_code == 401, "无效token应该被拒绝"
    print("  ✓ 无效token的历史被拒绝")


def test_history_with_auth():
    """测试有token的历史查询。"""
    print("Testing authenticated history...")

    # Register and login
    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "bob",
        "password": "bobpass"
    })
    if resp.status_code == 400 and "user exists" in resp.text:
        print("  ℹ 用户已存在")

    resp = requests.post(f"{BASE_URL}/api/login", json={
        "username": "bob",
        "password": "bobpass"
    })
    token = resp.json()["token"]

    # Get empty history
    resp = requests.get(
        f"{BASE_URL}/api/history?chat_id=bobchat",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, "History request should succeed"
    data = resp.json()
    assert "history" in data, "Response should contain history"
    assert isinstance(data["history"], list), "History should be a list"
    print("  ✓ Empty history retrieved")

    # Send a message
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"chat_id": "bobchat", "message": "Test message", "stream": False},
        headers={"Authorization": f"Bearer {token}"}
    )

    # Get history again
    resp = requests.get(
        f"{BASE_URL}/api/history?chat_id=bobchat",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = resp.json()
    history = data["history"]
    # Should have at least user message and assistant response
    assert len(history) >= 1, f"Should have messages in history, got {len(history)}"
    print(f"  ✓ Message history retrieved ({len(history)} messages)")


def test_history_structured_format():
    """测试历史记录的结构化格式（thinking、tool_calls等）。"""
    print("测试历史记录结构化格式...")

    # 注册并登录
    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "structtest",
        "password": "pass"
    })
    if resp.status_code == 400 and "user exists" in resp.text:
        print("  ℹ 用户已存在")

    resp = requests.post(f"{BASE_URL}/api/login", json={
        "username": "structtest",
        "password": "pass"
    })
    token = resp.json()["token"]

    # 清空现有历史
    resp = requests.get(
        f"{BASE_URL}/api/history?chat_id=structchat",
        headers={"Authorization": f"Bearer {token}"}
    )
    old_count = len(resp.json().get("history", []))

    # 发送消息（要求思考）
    resp = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "chat_id": "structchat",
            "message": "计算 10+20 等于多少，用计算器分开算",
            "stream": False,
            "thinking": True
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"发送消息失败：{resp.status_code} {resp.text}"
    print("  ✓ 消息发送成功")

    # 获取历史
    resp = requests.get(
        f"{BASE_URL}/api/history?chat_id=structchat",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = resp.json()
    history = data["history"]

    # 验证新消息已添加
    assert len(history) > old_count, f"历史记录应该增加，之前{old_count}条"
    print(f"  ✓ 历史记录已更新（共{len(history)}条）")

    # 找到assistant的消息
    assistant_msgs = [h for h in history if h.get("role") == "assistant"]
    assert len(assistant_msgs) > 0, "应该有assistant消息"

    # 验证结构化字段存在
    last_msg = assistant_msgs[-1]
    assert "thinking" in last_msg, "消息应有thinking字段"
    assert "thinking_completed" in last_msg, "消息应有thinking_completed字段"
    assert "tool_calls" in last_msg, "消息应有tool_calls字段"
    assert "content" in last_msg, "消息应有content字段"
    print(f"  ✓ 字段完整: thinking={last_msg.get('thinking') is not None}, tool_calls={last_msg.get('tool_calls') is not None}")

    # 如果有tool_calls，验证其结构
    if last_msg.get("tool_calls"):
        tc = last_msg["tool_calls"][0]
        assert "call_id" in tc or "name" in tc, f"tool_call应包含call_id或name，实际：{tc}"
        print(f"  ✓ tool_calls结构正确: {tc.get('name')} (call_id: {tc.get('call_id', 'N/A')})")

    print("  ✓ 历史记录结构化格式验证通过")


def test_user_message_isolation():
    """测试不同用户之间的消息隔离。"""
    print("测试不同用户的消息隔离...")

    # 注册两个用户
    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "charlie",
        "password": "pass"
    })
    if resp.status_code == 400 and "user exists" in resp.text:
        print("  ℹ charlie用户已存在")

    resp = requests.post(f"{BASE_URL}/api/register", json={
        "username": "diana",
        "password": "pass"
    })
    if resp.status_code == 400 and "user exists" in resp.text:
        print("  ℹ diana用户已存在")
    
    # 获取token
    resp1 = requests.post(f"{BASE_URL}/api/login", json={
        "username": "charlie",
        "password": "pass"
    })
    token1 = resp1.json()["token"]
    
    resp2 = requests.post(f"{BASE_URL}/api/login", json={
        "username": "diana",
        "password": "pass"
    })
    token2 = resp2.json()["token"]
    
    # Charlie发送消息
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"chat_id": "charliechat", "message": "我是Charlie", "stream": False},
        headers={"Authorization": f"Bearer {token1}"}
    )

    # Diana发送消息
    requests.post(
        f"{BASE_URL}/api/chat",
        json={"chat_id": "dianachat", "message": "我是Diana", "stream": False},
        headers={"Authorization": f"Bearer {token2}"}
    )

    # 检查Charlie的历史
    resp1 = requests.get(
        f"{BASE_URL}/api/history?chat_id=charliechat",
        headers={"Authorization": f"Bearer {token1}"}
    )
    charlie_history = resp1.json()["history"]

    # 检查Diana的历史
    resp2 = requests.get(
        f"{BASE_URL}/api/history?chat_id=dianachat",
        headers={"Authorization": f"Bearer {token2}"}
    )
    diana_history = resp2.json()["history"]
    
    # 验证消息是否正确分隔
    charlie_msgs = [m["content"] for m in charlie_history if m.get("content")]
    diana_msgs = [m["content"] for m in diana_history if m.get("content")]
    
    assert "我是Charlie" in charlie_msgs, "Charlie应该看到自己的消息"
    assert "我是Diana" not in charlie_msgs, "Charlie不应该看到Diana的消息"
    assert "我是Diana" in diana_msgs, "Diana应该看到自己的消息"
    assert "我是Charlie" not in diana_msgs, "Diana不应该看到Charlie的消息"
    
    print("  ✓ 消息正确隔离不同用户之间")


if __name__ == "__main__":
    print("=" * 60)
    print("用户系统 API 的集成测试")
    print("=" * 60)
    print()
    print("注意：这个测试需要后端服务器正在运行！")
    print(f"预认 URL：{BASE_URL}")
    print()
    
    try:
        # 清理
        cleanup_databases()
        print()
        
        # 等待服务器
        print("等待服务器就绪...")
        wait_for_server()
        print()
        
        # 运行测试
        test_user_registration()
        print()
        token = test_user_login()
        print()
        test_chat_without_auth()
        print()
        test_chat_with_auth(token)
        print()
        test_history_without_auth()
        print()
        test_history_with_auth()
        print()
        test_history_structured_format()
        print()
        test_user_message_isolation()
        
        print()
        print("=" * 60)
        print("所有集成测试通过！✓")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 意外错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
