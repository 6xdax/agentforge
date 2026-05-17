"""Configuration for chatbot backend."""
import os
from pathlib import Path

import yaml

# Path to main agentforge config
AGENTFORGE_CONFIG = Path(__file__).parent.parent.parent / "config"
TOOLS_YAML = AGENTFORGE_CONFIG / "tools.yml"


def load_tool_config() -> dict:
    """Load tool config from tools.yml."""
    if TOOLS_YAML.exists():
        with open(TOOLS_YAML) as f:
            data = yaml.safe_load(f) or {}
            return data.get("tools", {})
    return {}


def get_tool_config() -> dict:
    """Get current tool configuration."""
    tools = load_tool_config()
    all_tools = list(tools.keys())
    enabled = [name for name, cfg in tools.items() if cfg.get("enabled", True)]
    return {"tools": all_tools, "enabled": enabled}


def get_mcp_config() -> dict:
    """Get MCP server configuration from env."""
    # MCP servers can be configured via env vars
    # Format: MCP_SERVERS='{"server1": {"command": "...", "args": [...]}}'
    mcp_servers_str = os.environ.get("MCP_SERVERS", "{}")
    try:
        import json
        servers = json.loads(mcp_servers_str)
    except Exception:
        servers = {}
    return {"servers": [{"name": k, "enabled": v.get("enabled", True)} for k, v in servers.items()]}


def get_skill_config() -> dict:
    """Get skill configuration from skills directory."""
    skills_dir = AGENTFORGE_CONFIG.parent / "src" / "agent" / "skills"
    skills = []
    if skills_dir.exists():
        for f in sorted(skills_dir.rglob("SKILL.md")):
            skills.append({"name": f.parent.name, "path": str(f)})
    return {"skills": skills}