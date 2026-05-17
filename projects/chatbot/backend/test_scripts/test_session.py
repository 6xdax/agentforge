"""测试每个用户的会话隔离和消息历史。"""

import sys
import asyncio
import json
import sqlite3
import uuid
from pathlib import Path

# Add parent directory and workspace root to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent.parent.parent))  # workspace root

from session import SessionManager
from models import HistoryMessage, ToolCall
from db.database import DEFAULT_DB_PATH, get_agent_memory_db_path


TEST_RUN_ID = uuid.uuid4().hex[:8]
TEST_SESSION_PREFIX = f"test-session-{TEST_RUN_ID}"


def session_id(label: str) -> str:
    return f"{TEST_SESSION_PREFIX}-{label}"


def cleanup_real_test_data() -> None:
    app_conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    app_conn.execute("DELETE FROM messages WHERE session_id LIKE ?", (f"{TEST_SESSION_PREFIX}%",))
    app_conn.commit()
    app_conn.close()

    agent_conn = sqlite3.connect(str(get_agent_memory_db_path()))
    agent_conn.execute("DELETE FROM messages WHERE session_id LIKE ?", (f"{TEST_SESSION_PREFIX}%",))
    agent_conn.commit()
    agent_conn.close()


async def test_per_user_sessions():
    """测试每个用户的每个会话隔离。"""
    print("测试每个用户的会话隔离...")

    manager = SessionManager()
    user1 = session_id("user1")
    user2 = session_id("user2")

    # 为两个用户创建会话
    await manager.create_session(user1)
    await manager.create_session(user2)

    # 验证两个会话都存在
    session1 = manager.get_session(user1)
    session2 = manager.get_session(user2)

    assert session1 is not None, "user1的会话应该存在"
    assert session2 is not None, "user2的会话应该存在"
    print("  ✓ 两个用户的会话已创建")

    # 验证它们是不同的Agent实例
    assert session1["agent"] is not session2["agent"], "每个用户应该有独立的agent实例"
    assert session1["memory"] is not session2["memory"], "每个用户应该有独立的memory实例"
    print("  ✓ 每个用户有一个Agent和Memory隔离")


async def test_message_history_isolation():
    """测试消息历史按用户隔离。"""
    print("测试消息历史按用户隔离...")

    manager = SessionManager()
    alice = session_id("alice")
    bob = session_id("bob")

    # 创建会话并添加消息
    await manager.create_session(alice)
    await manager.create_session(bob)

    # Alice添加消息
    await manager.add_to_history(alice, HistoryMessage(role="user", content="你好，我是Alice"))
    await manager.add_to_history(alice, HistoryMessage(role="assistant", content="你好 Alice！"))

    # Bob添加消息
    await manager.add_to_history(bob, HistoryMessage(role="user", content="你好，我是Bob"))
    await manager.add_to_history(bob, HistoryMessage(role="assistant", content="你好 Bob！"))

    print("  ✓ 两个用户的消息已添加")

    # 获取Alice的历史
    alice_history = await manager.get_history(alice, limit=10)
    assert len(alice_history) == 2, f"Alice应该2条消息，实际{len(alice_history)}"
    assert alice_history[0]["content"] == "你好，我是Alice", "第一条消息应该是Alice的"
    assert alice_history[1]["role"] == "assistant", "第二条消息应该是助手"
    print("  ✓ Alice的历史正常且隔离")

    # 获取Bob的历史
    bob_history = await manager.get_history(bob, limit=10)
    assert len(bob_history) == 2, f"Bob应该2条消息，实际{len(bob_history)}"
    assert bob_history[0]["content"] == "你好，我是Bob", "第一条消息应该是Bob的"
    print("  ✓ Bob的历史正常且隔离")

    # 验证两个用户的历史不同
    assert alice_history[0]["content"] != bob_history[0]["content"], "不同用户的消息应该不同"
    print("  ✓ 消息历史正确按用户隔离")


async def test_thinking_and_tool_calls():
    """测试思考内容和工具调用记录。"""
    print("测试思考内容和工具调用记录...")

    manager = SessionManager()
    thinking_session = session_id("thinking")
    await manager.create_session(thinking_session)

    tool_calls = [
        ToolCall(call_id="call_1", name="calculator", arguments={"expr": "1+1"}, result="2", status="completed"),
        ToolCall(call_id="call_2", name="calculator", arguments={"expr": "2+2"}, result="4", status="completed"),
    ]

    await manager.add_to_history(
        thinking_session,
        HistoryMessage(
            role="user",
            content="计算1+1和2+2"
        )
    )

    await manager.add_to_history(
        thinking_session,
        HistoryMessage(
            role="assistant",
            content="结果分别是2和4",
            thinking="用户要求计算简单数学题",
            thinking_completed=True,
            tool_calls=tool_calls
        )
    )

    history = await manager.get_history(thinking_session, limit=10)
    assert len(history) == 2, f"应该有2条消息，实际{len(history)}"

    # 验证第二条消息（assistant）的结构
    assistant_msg = history[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "结果分别是2和4"
    assert assistant_msg["thinking"] == "用户要求计算简单数学题"
    assert assistant_msg["thinking_completed"] is True
    assert assistant_msg["tool_calls"] is not None
    assert len(assistant_msg["tool_calls"]) == 2
    assert assistant_msg["tool_calls"][0].name == "calculator"
    assert assistant_msg["tool_calls"][0].result == "2"
    print("  ✓ 思考内容和工具调用记录正确保存")


async def test_memory_persistence():
    """测试数据跨会话重建的持久性。"""
    print("测试数据持久性...")

    persist_session = session_id("persistence")

    # 第一个管理器：添加消息
    manager1 = SessionManager()
    await manager1.create_session(persist_session)
    await manager1.add_to_history(persist_session, HistoryMessage(role="user", content="消息1"))
    await manager1.add_to_history(persist_session, HistoryMessage(role="assistant", content="回复1"))

    history1 = await manager1.get_history(persist_session, limit=10)
    assert len(history1) == 2, "第一个管理器应该2条消息"
    print("  ✓ 第一个管理器已保存消息")

    # 第二个管理器：检索相同的会话
    manager2 = SessionManager()
    await manager2.create_session(persist_session)

    history2 = await manager2.get_history(persist_session, limit=10)
    assert len(history2) == 2, "第二个管理器应该2条消息"
    assert history1[0]["content"] == history2[0]["content"], "内容应该保持不变"
    print("  ✓ 第二个管理器从永久存储中检索消息")

    # 在第二个管理器中添加新消息
    await manager2.add_to_history(persist_session, HistoryMessage(role="user", content="消息2"))
    history3 = await manager2.get_history(persist_session, limit=10)
    assert len(history3) == 3, "添加后应该3条消息"
    print("  ✓ 新消息深码不变且保持")


async def test_history_limit():
    """测试历史限制参数。"""
    print("测试历史限制参数...")

    manager = SessionManager()
    many_msgs_session = session_id("many_msgs")
    await manager.create_session(many_msgs_session)

    # 添加10条消息
    for i in range(10):
        await manager.add_to_history(
            many_msgs_session,
            HistoryMessage(role="user" if i % 2 == 0 else "assistant", content=f"消息{i}")
        )

    # 获取所有消息
    all_msgs = await manager.get_history(many_msgs_session, limit=100)
    assert len(all_msgs) == 10, f"应该检索10条消息，实际{len(all_msgs)}"
    print("  ✓ 以limit=100获取所有消息")

    # 获取限制数量的消息（按id ASC排序：最旧在前）
    limited = await manager.get_history(many_msgs_session, limit=3)
    assert len(limited) == 3, f"应该仅检索3条消息，实际{len(limited)}"
    assert limited[-1]["content"] == "消息2", "应该获取最旧的消息"
    print("  ✓ 以limit=3仅获取3条最旧消息")


if __name__ == "__main__":
    cleanup_real_test_data()

    print("=" * 60)
    print("测试会话与消息隔离")
    print("=" * 60)

    try:
        asyncio.run(test_per_user_sessions())
        asyncio.run(test_message_history_isolation())
        asyncio.run(test_thinking_and_tool_calls())
        asyncio.run(test_memory_persistence())
        asyncio.run(test_history_limit())

        print("\n" + "=" * 60)
        print("所有会话测试通过！✓")
        print("=" * 60)
        cleanup_real_test_data()
    except AssertionError as e:
        cleanup_real_test_data()
        print(f"\n❌ 测试失败：{e}")
        sys.exit(1)
    except Exception as e:
        cleanup_real_test_data()
        print(f"\n❌ 意外错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)