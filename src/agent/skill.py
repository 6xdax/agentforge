"""Skill loading system with two-layer injection.

Layer 1 (cheap): skill names in system prompt (~100 tokens/skill)
Layer 2 (on demand): full skill body in tool_result

    System prompt:
    +--------------------------------------+
    | Skills available:                    |
    |   - pdf: Process PDF files...        |  <-- Layer 1: metadata only
    |   - code-review: Review code...      |
    +--------------------------------------+

    When model calls load_skill("pdf"):
    +--------------------------------------+
    | tool_result:                         |
    | <skill>                              |
    |   Full PDF processing instructions   |  <-- Layer 2: full body
    | </skill>                             |
    +--------------------------------------+

Key insight: "Don't put everything in the system prompt. Load on demand."
"""

import re
from pathlib import Path
from typing import Optional

import yaml


class SkillLoader:
    """Loads skills from skills/<name>/SKILL.md with YAML frontmatter.

    Skills follow a two-layer injection pattern:
    - Layer 1: Only metadata (name, description) goes in system prompt
    - Layer 2: Full body loaded on demand via load_skill tool
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir
        self.skills: dict[str, dict] = {}
        if skills_dir:
            self._load_all()

    def _load_all(self) -> None:
        """Scan skills_dir for SKILL.md files and load them."""
        if not self.skills_dir or not self.skills_dir.exists():
            return
        for f in sorted(self.skills_dir.rglob("SKILL.md")):
            text = f.read_text()
            meta, body = self._parse_frontmatter(text)
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body, "path": str(f)}

    def _parse_frontmatter(self, text: str) -> tuple[dict, str]:
        """Parse YAML frontmatter between --- delimiters."""
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, match.group(2).strip()

    def get_descriptions(self) -> str:
        """Layer 1: short descriptions for the system prompt."""
        if not self.skills:
            return "(no skills available)"
        lines = []
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "No description")
            tags = skill["meta"].get("tags", "")
            line = f"  - {name}: {desc}"
            if tags:
                line += f" [{tags}]"
            lines.append(line)
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        """Layer 2: full skill body returned in tool_result."""
        skill = self.skills.get(name)
        if not skill:
            available = ", ".join(self.skills.keys()) if self.skills else "none"
            return f"Error: Unknown skill '{name}'. Available: {available}"
        return f'<skill name="{name}">\n{skill["body"]}\n</skill>'

    def add_skill(self, name: str, body: str, description: str = "", tags: str = "") -> None:
        """Add a skill programmatically."""
        self.skills[name] = {
            "meta": {"name": name, "description": description, "tags": tags},
            "body": body,
            "path": "<memory>",
        }

    def get_skill_schema(self) -> dict:
        """Return OpenAI-format tool schema for load_skill."""
        return {
            "name": "load_skill",
            "description": "Load specialized knowledge by name. Returns full skill body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name to load",
                    }
                },
                "required": ["name"],
            },
        }
