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


class Settings:
    """Application settings container."""

    llm: LLMProviderSettings = LLMProviderSettings()
    agent: AgentSettings = AgentSettings()

    def __init__(self):
        # Reload YAML defaults if present
        self.llm = LLMProviderSettings()
        self.agent = AgentSettings()


# Global settings instance
settings = Settings()
