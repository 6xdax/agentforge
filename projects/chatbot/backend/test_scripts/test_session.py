"""测试每个用户的会话隔离和消息历史。"""

import sys
import os
import asyncio
import json
from pathlib import Path

# Add parent directory and workspace root to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent.parent.parent))  # workspace root

from session import SessionManager
from models import HistoryMessage, ToolCall


async def test_per_user_sessions():
    """测试每个用户的每个会话隔离。"""
    print("测试每个用户的会话隔离...")

    manager = SessionManager(db_path="db/test_session.db")

    # 为两个用户创建会话
    manager.create_session("user1")
    manager.create_session("user2")

    # 验证两个会话都存在
    session1 = manager.get_session("user1")
    session2 = manager.get_session("user2")

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

    manager = SessionManager(db_path="db/test_history.db")

    # 创建会话并添加消息
    manager.create_session("alice")
    manager.create_session("bob")

    # Alice添加消息
    await manager.add_to_history("alice", HistoryMessage(role="user", content="你好，我是Alice"))
    await manager.add_to_history("alice", HistoryMessage(role="assistant", content="你好 Alice！"))

    # Bob添加消息
    await manager.add_to_history("bob", HistoryMessage(role="user", content="你好，我是Bob"))
    await manager.add_to_history("bob", HistoryMessage(role="assistant", content="你好 Bob！"))

    print("  ✓ 两个用户的消息已添加")

    # 获取Alice的历史
    alice_history = await manager.get_history("alice", limit=10)
    assert len(alice_history) == 2, f"Alice应该2条消息，实际{len(alice_history)}"
    assert alice_history[0]["content"] == "你好，我是Alice", "第一条消息应该是Alice的"
    assert alice_history[1]["role"] == "assistant", "第二条消息应该是助手"
    print("  ✓ Alice的历史正常且隔离")

    # 获取Bob的历史
    bob_history = await manager.get_history("bob", limit=10)
    assert len(bob_history) == 2, f"Bob应该2条消息，实际{len(bob_history)}"
    assert bob_history[0]["content"] == "你好，我是Bob", "第一条消息应该是Bob的"
    print("  ✓ Bob的历史正常且隔离")

    # 验证两个用户的历史不同
    assert alice_history[0]["content"] != bob_history[0]["content"], "不同用户的消息应该不同"
    print("  ✓ 消息历史正确按用户隔离")


async def test_thinking_and_tool_calls():
    """测试思考内容和工具调用记录。"""
    print("测试思考内容和工具调用记录...")

    manager = SessionManager(db_path="db/test_thinking.db")
    manager.create_session("test_thinking")

    tool_calls = [
        ToolCall(call_id="call_1", name="calculator", arguments={"expr": "1+1"}, result="2", status="completed"),
        ToolCall(call_id="call_2", name="calculator", arguments={"expr": "2+2"}, result="4", status="completed"),
    ]

    await manager.add_to_history(
        "test_thinking",
        HistoryMessage(
            role="user",
            content="计算1+1和2+2"
        )
    )

    await manager.add_to_history(
        "test_thinking",
        HistoryMessage(
            role="assistant",
            content="结果分别是2和4",
            thinking="用户要求计算简单数学题",
            thinking_completed=True,
            tool_calls=tool_calls
        )
    )

    history = await manager.get_history("test_thinking", limit=10)
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

    # 清理
    import sqlite3
    conn = sqlite3.connect("db/test_thinking.db")
    conn.execute("DROP TABLE IF EXISTS messages")
    conn.close()


async def test_memory_persistence():
    """测试数据跨会话重建的持久性。"""
    print("测试数据持久性...")

    # 使用相同的DB路径来测试持久性
    db_path = "db/test_persistence.db"

    # 第一个管理器：添加消息
    manager1 = SessionManager(db_path=db_path)
    manager1.create_session("charlie")
    await manager1.add_to_history("charlie", HistoryMessage(role="user", content="消息1"))
    await manager1.add_to_history("charlie", HistoryMessage(role="assistant", content="回复1"))

    history1 = await manager1.get_history("charlie", limit=10)
    assert len(history1) == 2, "第一个管理器应该2条消息"
    print("  ✓ 第一个管理器已保存消息")

    # 第二个管理器：检索相同的会话
    manager2 = SessionManager(db_path=db_path)
    manager2.create_session("charlie")

    history2 = await manager2.get_history("charlie", limit=10)
    assert len(history2) == 2, "第二个管理器应该2条消息"
    assert history1[0]["content"] == history2[0]["content"], "内容应该保持不变"
    print("  ✓ 第二个管理器从永久存储中检索消息")

    # 在第二个管理器中添加新消息
    await manager2.add_to_history("charlie", HistoryMessage(role="user", content="消息2"))
    history3 = await manager2.get_history("charlie", limit=10)
    assert len(history3) == 3, "添加后应该3条消息"
    print("  ✓ 新消息深码不变且保持")


async def test_history_limit():
    """测试历史限制参数。"""
    print("测试历史限制参数...")

    manager = SessionManager(db_path="db/test_limit.db")
    manager.create_session("user_many_msgs")

    # 添加10条消息
    for i in range(10):
        await manager.add_to_history(
            "user_many_msgs",
            HistoryMessage(role="user" if i % 2 == 0 else "assistant", content=f"消息{i}")
        )

    # 获取所有消息
    all_msgs = await manager.get_history("user_many_msgs", limit=100)
    assert len(all_msgs) == 10, f"应该检索10条消息，实际{len(all_msgs)}"
    print("  ✓ 以limit=100获取所有消息")

    # 获取限制数量的消息（按id ASC排序：最旧在前）
    limited = await manager.get_history("user_many_msgs", limit=3)
    assert len(limited) == 3, f"应该仅检索3条消息，实际{len(limited)}"
    assert limited[-1]["content"] == "消息2", "应该获取最旧的消息"
    print("  ✓ 以limit=3仅获取3条最旧消息")


if __name__ == "__main__":
    # 清理旧测试数据库
    import sqlite3
    for db_file in ["db/test_session.db", "db/test_history.db", "db/test_thinking.db", "db/test_persistence.db", "db/test_limit.db"]:
        try:
            conn = sqlite3.connect(db_file)
            conn.execute("DROP TABLE IF EXISTS messages")
            conn.close()
        except:
            pass

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
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 意外错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)