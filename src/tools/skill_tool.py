"""Skill loading tool for on-demand knowledge injection.

This tool enables the two-layer skill pattern:
- Layer 1: Skill metadata in system prompt (cheap)
- Layer 2: Full skill body loaded on demand (when model asks)
"""

from pathlib import Path
from typing import Optional

from agent.skill import SkillLoader


# Global skill loader instance
_skill_loader: Optional[SkillLoader] = None


def get_skill_loader(skills_dir: Optional[Path] = None) -> SkillLoader:
    """Get or create the global SkillLoader instance."""
    global _skill_loader
    if _skill_loader is None:
        if skills_dir is None:
            skills_dir = Path(__file__).parent.parent / "skills"
        _skill_loader = SkillLoader(skills_dir)
    return _skill_loader


def _handle(args: dict) -> str:
    """Handle load_skill calls."""
    loader = get_skill_loader()
    name = args.get("name", "")
    if not name:
        return '{"error": "skill name is required"}'
    return loader.get_content(name)


def get_skill_schema() -> dict:
    """Return the tool schema for load_skill."""
    return {
        "name": "load_skill",
        "description": "Load specialized knowledge by name. Returns full skill body with instructions.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill name to load (e.g., 'pdf', 'code-review', 'agent-builder')",
                }
            },
            "required": ["name"],
        },
    }


# Self-registration
def register(registry):
    """Register the load_skill tool with the registry."""
    registry.register(
        name="load_skill",
        schema=get_skill_schema(),
        handler=_handle,
    )


register_load_skill = register

__all__ = ["register", "register_load_skill", "get_skill_loader", "SkillLoader"]