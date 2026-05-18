"""测试用户级工具、MCP、Skill 配置。"""

import asyncio
import sqlite3
import sys
import uuid
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent.parent.parent))

from user_config import (
    get_mcp_config,
    get_skill_config,
    get_tool_config,
    update_mcp_config,
    update_skill_config,
    update_tool_config,
)
from db.database import DEFAULT_DB_PATH, get_agent_memory_db_path
from session import SessionManager

TEST_USER_ID = f"test-config-{uuid.uuid4().hex[:8]}"


def cleanup_real_test_data() -> None:
    app_conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    app_conn.execute("DELETE FROM user_item_configs WHERE user_id = ?", (TEST_USER_ID,))
    app_conn.execute("DELETE FROM messages WHERE session_id LIKE ?", (f"{TEST_USER_ID}:%",))
    app_conn.commit()
    app_conn.close()

    agent_conn = sqlite3.connect(str(get_agent_memory_db_path()))
    agent_conn.execute("DELETE FROM messages WHERE session_id LIKE ?", (f"{TEST_USER_ID}:%",))
    agent_conn.commit()
    agent_conn.close()


async def test_tool_config_and_session_registry() -> None:
    print("测试用户级 Tool 配置...")
    config_before = await get_tool_config(TEST_USER_ID)
    tool_names = config_before["tools"]
    assert tool_names, "应该至少有一个工具"
    first_tool = tool_names[0]

    updated = await update_tool_config(TEST_USER_ID, {first_tool: False})
    assert first_tool not in updated["enabled"], "禁用后工具不应出现在 enabled 列表"
    print(f"  ✓ 已禁用工具: {first_tool}")

    manager = SessionManager()
    session_id = f"{TEST_USER_ID}:chat"
    await manager.create_session(session_id)
    session = manager.get_session(session_id)
    assert session is not None, "会话应成功创建"
    names = session["agent"].registry.get_names()
    assert first_tool not in names, "新会话 registry 应应用用户工具配置"
    print("  ✓ 新会话已应用用户工具配置")


async def test_mcp_config() -> None:
    print("测试用户级 MCP 配置...")
    mcp_config = await get_mcp_config(TEST_USER_ID)
    if not mcp_config["items"]:
        print("  ✓ 当前无 MCP 服务，接口仍返回空配置")
        return
    first_server = mcp_config["items"][0]["name"]
    updated = await update_mcp_config(TEST_USER_ID, {first_server: {"enabled": False, "config": {"scope": "user"}}})
    item = next(server for server in updated["items"] if server["name"] == first_server)
    assert item["enabled"] is False, "MCP 服务应可被用户禁用"
    assert item.get("config", {}).get("scope") == "user", "MCP 用户配置应持久化"
    print(f"  ✓ 已保存 MCP 配置: {first_server}")


async def test_skill_config() -> None:
    print("测试用户级 Skill 配置...")
    skill_config = await get_skill_config(TEST_USER_ID)
    assert skill_config["items"], "应该至少发现一个 skill"
    first_skill = skill_config["items"][0]["name"]

    updated = await update_skill_config(TEST_USER_ID, {first_skill: False})
    assert first_skill not in updated["enabled"], "禁用后 skill 不应出现在 enabled 列表"
    print(f"  ✓ 已禁用 Skill: {first_skill}")

    manager = SessionManager()
    session_id = f"{TEST_USER_ID}:skill-chat"
    await manager.create_session(session_id)
    session = manager.get_session(session_id)
    result = await session["agent"].registry.dispatch("load_skill", {"name": first_skill})
    assert "Skill disabled for user" in result, "禁用的 skill 不应可被加载"
    print("  ✓ load_skill 已应用用户 skill 配置")


async def main() -> None:
    cleanup_real_test_data()
    await test_tool_config_and_session_registry()
    await test_mcp_config()
    await test_skill_config()
    cleanup_real_test_data()


if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("\n所有配置测试通过！✓")
    except AssertionError as e:
        cleanup_real_test_data()
        print(f"\n❌ 测试失败：{e}")
        raise
    except Exception:
        cleanup_real_test_data()
        raise
