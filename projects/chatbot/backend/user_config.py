"""Per-user configuration for chatbot backend."""

from __future__ import annotations

import importlib
import json
import time
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from agent.registry import ToolRegistry
from db.database import create_sessionmaker_for, init_database
from db.models import UserItemConfig

CATEGORY_TOOL = "tool"
CATEGORY_MCP = "mcp"
CATEGORY_SKILL = "skill"

BACKEND_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = BACKEND_ROOT.parent.parent.parent
AGENTFORGE_CONFIG = WORKSPACE_ROOT / "config"
TOOLS_YAML = AGENTFORGE_CONFIG / "tools.yml"
SKILLS_DIR = WORKSPACE_ROOT / "src" / "skills"


def _load_tools_yaml() -> dict[str, dict]:
    if not TOOLS_YAML.exists():
        return {}
    with open(TOOLS_YAML) as f:
        data = yaml.safe_load(f) or {}
    return data.get("tools", {})


@lru_cache(maxsize=1)
def _build_tool_assets() -> tuple[ToolRegistry, dict[str, dict[str, Any]]]:
    registry = ToolRegistry()
    catalog: dict[str, dict[str, Any]] = {}

    for module_name, cfg in _load_tools_yaml().items():
        before_names = set(registry.get_names())
        try:
            module = importlib.import_module(f"tools.{module_name}")
        except ImportError:
            continue
        if not hasattr(module, "register"):
            continue
        module.register(registry)
        default_enabled = bool((cfg or {}).get("enabled", True))
        module_description = (cfg or {}).get("description", "")
        for tool_name in set(registry.get_names()) - before_names:
            entry = registry.get_entry(tool_name)
            catalog[tool_name] = {
                "name": tool_name,
                "enabled": default_enabled,
                "description": entry.description or module_description,
                "module": module_name,
            }
    return registry, dict(sorted(catalog.items()))


@lru_cache(maxsize=1)
def _load_tool_catalog() -> dict[str, dict[str, Any]]:
    _, catalog = _build_tool_assets()
    return catalog


@lru_cache(maxsize=1)
def _load_full_tool_registry() -> ToolRegistry:
    registry, _ = _build_tool_assets()
    return registry


@lru_cache(maxsize=1)
def _load_mcp_catalog() -> dict[str, dict[str, Any]]:
    import os

    mcp_servers_str = os.environ.get("MCP_SERVERS", "{}")
    try:
        servers = json.loads(mcp_servers_str)
    except Exception:
        servers = {}

    catalog: dict[str, dict[str, Any]] = {}
    for name, cfg in servers.items():
        config = deepcopy(cfg or {})
        enabled = bool(config.pop("enabled", True))
        catalog[name] = {
            "name": name,
            "enabled": enabled,
            "config": config,
        }
    return dict(sorted(catalog.items()))


@lru_cache(maxsize=1)
def _load_skill_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    if not SKILLS_DIR.exists():
        return catalog
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        name = skill_file.parent.name
        catalog[name] = {
            "name": name,
            "enabled": True,
            "path": str(skill_file),
        }
    return catalog


def _category_catalog(category: str) -> dict[str, dict[str, Any]]:
    if category == CATEGORY_TOOL:
        return _load_tool_catalog()
    if category == CATEGORY_MCP:
        return _load_mcp_catalog()
    if category == CATEGORY_SKILL:
        return _load_skill_catalog()
    raise ValueError(f"Unsupported category: {category}")


async def _ensure_config_storage() -> None:
    await init_database()


async def _get_override_rows(user_id: str, category: str) -> dict[str, UserItemConfig]:
    await _ensure_config_storage()
    sessionmaker = create_sessionmaker_for()
    async with sessionmaker() as session:
        result = await session.scalars(
            select(UserItemConfig).where(
                UserItemConfig.user_id == user_id,
                UserItemConfig.category == category,
            )
        )
        rows = result.all()
    return {row.item_name: row for row in rows}


def _decode_config(config_json: str | None) -> dict[str, Any]:
    if not config_json:
        return {}
    try:
        data = json.loads(config_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_update_payload(req: dict[str, Any]) -> list[dict[str, Any]]:
    updates: dict[str, dict[str, Any]] = {}

    def ensure(name: str) -> dict[str, Any]:
        if name not in updates:
            updates[name] = {
                "name": name,
                "has_enabled": False,
                "enabled": None,
                "has_config": False,
                "config": None,
            }
        return updates[name]

    items = req.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            entry = ensure(name)
            if "enabled" in item:
                entry["has_enabled"] = True
                entry["enabled"] = bool(item.get("enabled"))
            if "config" in item:
                entry["has_config"] = True
                config = item.get("config")
                entry["config"] = config if isinstance(config, dict) else {}

    for field, enabled in (("enabled", True), ("disabled", False)):
        names = req.get(field)
        if isinstance(names, list):
            for name in names:
                if not isinstance(name, str) or not name:
                    continue
                entry = ensure(name)
                entry["has_enabled"] = True
                entry["enabled"] = enabled

    for name, value in req.items():
        if name in {"items", "enabled", "disabled"}:
            continue
        if not isinstance(name, str) or not name:
            continue
        entry = ensure(name)
        if isinstance(value, bool):
            entry["has_enabled"] = True
            entry["enabled"] = value
            continue
        if isinstance(value, dict):
            if "enabled" in value:
                entry["has_enabled"] = True
                entry["enabled"] = bool(value.get("enabled"))
            if "config" in value:
                entry["has_config"] = True
                config = value.get("config")
                entry["config"] = config if isinstance(config, dict) else {}
            elif "enabled" not in value:
                entry["has_config"] = True
                entry["config"] = value

    return list(updates.values())


def _merge_items(
    catalog: dict[str, dict[str, Any]],
    overrides: dict[str, UserItemConfig],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, base in catalog.items():
        override = overrides.get(name)
        item = deepcopy(base)
        if override is not None:
            item["enabled"] = override.enabled
            override_config = _decode_config(override.config_json)
            if override_config:
                base_config = item.get("config") or {}
                if isinstance(base_config, dict):
                    item["config"] = {**base_config, **override_config}
                else:
                    item["config"] = override_config
        items.append(item)
    return items


async def _get_category_config(user_id: str, category: str) -> dict[str, Any]:
    catalog = _category_catalog(category)
    overrides = await _get_override_rows(user_id, category)
    items = _merge_items(catalog, overrides)
    enabled_names = [item["name"] for item in items if item.get("enabled", True)]

    if category == CATEGORY_TOOL:
        return {
            "items": items,
            "tools": [item["name"] for item in items],
            "enabled": enabled_names,
        }
    if category == CATEGORY_MCP:
        return {
            "items": items,
            "servers": items,
            "enabled": enabled_names,
        }
    return {
        "items": items,
        "skills": items,
        "enabled": enabled_names,
    }


async def _update_category_config(user_id: str, category: str, req: dict[str, Any]) -> dict[str, Any]:
    catalog = _category_catalog(category)
    updates = _normalize_update_payload(req)
    unknown = sorted(update["name"] for update in updates if update["name"] not in catalog)
    if unknown:
        raise ValueError(f"Unknown {category} item(s): {', '.join(unknown)}")

    await _ensure_config_storage()
    sessionmaker = create_sessionmaker_for()
    async with sessionmaker() as session:
        result = await session.scalars(
            select(UserItemConfig).where(
                UserItemConfig.user_id == user_id,
                UserItemConfig.category == category,
            )
        )
        rows = {row.item_name: row for row in result.all()}
        now = int(time.time())

        for update in updates:
            name = update["name"]
            base = catalog[name]
            row = rows.get(name)
            current_enabled = row.enabled if row is not None else bool(base.get("enabled", True))
            current_config = _decode_config(row.config_json) if row is not None else {}

            if update["has_enabled"]:
                current_enabled = bool(update["enabled"])
            if update["has_config"]:
                current_config = update["config"] or {}

            default_enabled = bool(base.get("enabled", True))
            should_persist = current_enabled != default_enabled or bool(current_config)

            if should_persist:
                if row is None:
                    row = UserItemConfig(
                        user_id=user_id,
                        category=category,
                        item_name=name,
                        enabled=current_enabled,
                        config_json=json.dumps(current_config, ensure_ascii=False) if current_config else None,
                        updated_at=now,
                    )
                    session.add(row)
                    rows[name] = row
                else:
                    row.enabled = current_enabled
                    row.config_json = json.dumps(current_config, ensure_ascii=False) if current_config else None
                    row.updated_at = now
            elif row is not None:
                await session.delete(row)
                rows.pop(name, None)

        await session.commit()

    return await _get_category_config(user_id, category)


async def get_tool_config(user_id: str) -> dict[str, Any]:
    return await _get_category_config(user_id, CATEGORY_TOOL)


async def update_tool_config(user_id: str, req: dict[str, Any]) -> dict[str, Any]:
    return await _update_category_config(user_id, CATEGORY_TOOL, req)


async def get_mcp_config(user_id: str) -> dict[str, Any]:
    return await _get_category_config(user_id, CATEGORY_MCP)


async def update_mcp_config(user_id: str, req: dict[str, Any]) -> dict[str, Any]:
    return await _update_category_config(user_id, CATEGORY_MCP, req)


async def get_skill_config(user_id: str) -> dict[str, Any]:
    return await _get_category_config(user_id, CATEGORY_SKILL)


async def update_skill_config(user_id: str, req: dict[str, Any]) -> dict[str, Any]:
    return await _update_category_config(user_id, CATEGORY_SKILL, req)


async def get_enabled_tool_names(user_id: str) -> set[str]:
    tool_config = await get_tool_config(user_id)
    return set(tool_config.get("enabled", []))


async def get_enabled_skill_names(user_id: str) -> set[str]:
    skill_config = await get_skill_config(user_id)
    return set(skill_config.get("enabled", []))


async def build_tool_registry_for_user(user_id: str) -> ToolRegistry:
    enabled_tools = await get_enabled_tool_names(user_id)
    enabled_skills = await get_enabled_skill_names(user_id)
    full_registry = _load_full_tool_registry()
    registry = ToolRegistry()

    for tool_name in sorted(enabled_tools):
        entry = full_registry.get_entry(tool_name)
        if entry is None:
            continue
        handler = entry.handler
        if tool_name == "load_skill":
            allowed_skills = set(enabled_skills)

            def guarded_handler(args: dict, original_handler=entry.handler, allowed=allowed_skills):
                skill_name = args.get("name", "")
                if not skill_name:
                    return '{"error": "skill name is required"}'
                if skill_name not in allowed:
                    return json.dumps({"error": f"Skill disabled for user: {skill_name}"}, ensure_ascii=False)
                return original_handler(args)

            handler = guarded_handler
        registry.register(
            name=entry.name,
            schema=deepcopy(entry.schema),
            handler=handler,
            description=entry.description,
        )

    return registry
