"""Pydantic Settings for AgentForge.

Loads from environment variables and YAML config.
YAML provides non-sensitive defaults; env vars override.
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")


def _load_yaml_config() -> dict:
    """Load defaults from YAML config files."""
    config_dir = Path(__file__).parent
    defaults = {}
    for yaml_file in ["llm.yml", "agent.yml"]:
        path = config_dir / yaml_file
        if path.exists():
            with open(path) as f:
                defaults.update(yaml.safe_load(f) or {})
    return defaults


_yaml_defaults = _load_yaml_config()


class LLMProviderSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="MINIMAX_")

    api_key: str = ""
    base_url: str = "https://api.minimaxi.com/anthropic"
    model: str = "MiniMax-M2.7"


class AgentSettings(BaseSettings):
    """Agent runtime configuration."""

    model_config = SettingsConfigDict(env_prefix="AGENTFORGE_AGENT_")

    max_iterations: int = 20


class ToolSettings:
    """Tool enable/disable switches loaded from config/tools.yml.

    Each tool entry can be overridden via env:
        AGENTFORGE_TOOL_<NAME>_ENABLED=false
    """

    def __init__(self, tools_yaml: dict):
        self._tools: dict[str, bool] = {}
        for name, cfg in (tools_yaml or {}).items():
            env_key = f"AGENTFORGE_TOOL_{name.upper()}_ENABLED"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                self._tools[name] = env_val.lower() not in ("0", "false", "no")
            else:
                self._tools[name] = bool((cfg or {}).get("enabled", True))

    def is_enabled(self, name: str) -> bool:
        """Return True if the tool is enabled (unknown tools default to True)."""
        return self._tools.get(name, True)

    def all_tools(self) -> list[str]:
        """Return all tool names defined in config."""
        return list(self._tools.keys())

    def enabled_tools(self) -> list[str]:
        """Return list of enabled tool names."""
        return [name for name, on in self._tools.items() if on]


class Settings:
    """Application settings container."""

    llm: LLMProviderSettings = LLMProviderSettings()
    agent: AgentSettings = AgentSettings()
    tools: ToolSettings

    def __init__(self):
        # Reload YAML defaults if present
        self.llm = LLMProviderSettings()
        self.agent = AgentSettings()

        config_dir = Path(__file__).parent

        tools_path = config_dir / "tools.yml"
        tools_yaml: dict = {}
        if tools_path.exists():
            with open(tools_path) as f:
                data = yaml.safe_load(f) or {}
                tools_yaml = data.get("tools", {})
        self.tools = ToolSettings(tools_yaml)

    def load_all_into_registry(self, registry) -> None:
        """Load all configured tools (AgentForge + optionally Hermes) into registry.

        This is the single call-site for wiring up a registry at startup.
        Hermes tools are loaded when config/hermes_tools.yaml exists.
        """
        from tools import load_all_tools  # avoid circular import

        load_all_tools(registry)


# Global settings instance
settings = Settings()
