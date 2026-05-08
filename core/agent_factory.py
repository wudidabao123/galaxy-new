"""Agent factory — create AutoGen AssistantAgent instances from team role configs."""

from __future__ import annotations

from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.models.openai._model_info import ModelFamily

from config import KNOWN_OPENAI, MANUAL_TOOL_MODELS, AGENT_COLORS, AGENT_AVATARS
from data.model_store import get_model, get_model_api_key, get_default_model
from skills.registry import get_registry


def _ascii_name(display_name: str, idx: int, used_names: set | None = None) -> str:
    """AutoGen requires ASCII agent names.
    
    Returns a unique ASCII-safe name. If used_names is provided, appends
    a suffix to avoid collisions within the set.
    """
    import re
    safe = re.sub(r'[^a-zA-Z0-9_-]', '', display_name)
    base = safe if len(safe) >= 2 else f"agent_{idx:03d}"
    if used_names is None:
        return base
    # Ensure uniqueness within the team
    candidate = base
    suffix = 2
    while candidate in used_names:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def _uses_manual_tool_protocol(model_name: str) -> bool:
    """Check if this model needs the manual (text-based) tool protocol.

    Uses EXACT model_id match (not substring) to avoid false positives
    like "my-deepseek-model" matching "deepseek-v4-pro".
    """
    name = (model_name or "").lower()
    return name in MANUAL_TOOL_MODELS


def create_agents_for_team(
    team: dict[str, Any],
    run_id: str = "",
) -> list[dict[str, Any]]:
    """Create agent instances for all roles in a team.

    Returns list of agent info dicts: {name, display_name, agent, model_id,
    model_cfg, role_config, context_length, system_prompt, manual_tools,
    color_idx, avatar, color}.
    """
    registry = get_registry()
    agents = []
    used_names: set[str] = set()

    for i, role in enumerate(team.get("roles", [])):
        mid = role.get("model_id", "")
        model_data = get_model(mid) if mid else None

        if not model_data:
            model_data = get_default_model()

        if not model_data:
            import logging
            logging.warning(
                "create_agents_for_team: skipping role '%s' — no model config found "
                "(tried model_id='%s' and default)",
                role.get("name", f"agent_{i}"), mid,
            )
            continue

        mid_to_use = model_data["id"]
        api_key = get_model_api_key(mid_to_use)
        if not api_key:
            raise RuntimeError(
                f"Role '{role.get('name','?')}' model '{model_data.get('name', mid_to_use)}' "
                f"is missing API Key.\n"
                f"Add a Key on the Models page or set GALAXY_DEFAULT_API_KEY env var."
            )

        # NOTE: model_cfg has 'model' field (auto-renamed from 'model_name' by _row_to_dict)
        model_id_str = model_data.get("model", "")

        client_kwargs = {
            "model": model_id_str,
            "api_key": api_key,
            "base_url": model_data.get("base_url", ""),
        }

        # For non-OpenAI models, read capabilities from model config.
        # If capabilities have explicit tool/vision settings, use them.
        # Otherwise fall back to conservative defaults (function_calling=True is safe for most).
        if client_kwargs["model"] not in KNOWN_OPENAI:
            caps = model_data.get("capabilities", {})
            if isinstance(caps, dict) and "tools" in caps:
                # Explicit capabilities configured — use them
                client_kwargs["model_info"] = {
                    "vision": caps.get("vision", False),
                    "function_calling": caps.get("tools", True),
                    "json_output": caps.get("json_mode", True),
                    "family": caps.get("model_family", ModelFamily.ANY),
                    "structured_output": caps.get("structured_output", False),
                }
            else:
                # No explicit tool capability configured — use safe defaults
                client_kwargs["model_info"] = {
                    "vision": caps.get("vision", False) if isinstance(caps, dict) else False,
                    "function_calling": True,
                    "json_output": True,
                    "family": ModelFamily.ANY,
                    "structured_output": False,
                }

        model_client = OpenAIChatCompletionClient(**client_kwargs)

        skill_ids = role.get("skills", [])
        tools = registry.build_tools(skill_ids)

        manual_tools = _uses_manual_tool_protocol(model_id_str)

        system_prompt = _build_system_prompt(role)
        display_name = role.get("name", f"agent_{i}")
        safe = _ascii_name(display_name, i, used_names)

        agents.append({
            "name": safe,
            "display_name": display_name,
            "agent": AssistantAgent(
                name=safe,
                system_message=system_prompt,
                model_client=model_client,
                tools=None if manual_tools else (tools if tools else None),
                reflect_on_tool_use=False if manual_tools else bool(tools),
                model_client_stream=True,
                max_tool_iterations=8,
            ),
            "model_id": mid_to_use,
            "model_cfg": model_data,
            "role_config": role,
            "run_id": run_id,
            "context_length": int(model_data.get("context_length", 128000)),
            "system_prompt": system_prompt,
            "manual_tools": manual_tools,
            "color_idx": i,
            "avatar": role.get("avatar", AGENT_AVATARS[i % len(AGENT_AVATARS)]),
            "color": AGENT_COLORS[i % len(AGENT_COLORS)],
        })

    return agents


def _build_system_prompt(role: dict) -> str:
    """Build the system prompt for a role, including custom skills as knowledge."""
    prompt = role.get("prompt", "You are a helpful assistant.")

    # Inject advanced role profile
    advanced = role.get("advanced", {})
    if advanced:
        profile_parts = []
        field_map = [
            ("character_name", "Name"),
            ("gender", "Gender"),
            ("age", "Age"),
            ("identity", "Identity"),
            ("personality", "Personality"),
            ("background", "Background"),
            ("experience", "Experience"),
            ("social", "Social"),
            ("style", "Language Style"),
            ("values", "Values"),
        ]
        for key, label in field_map:
            val = advanced.get(key, "")
            if val and isinstance(val, str) and val.strip():
                profile_parts.append(f"{label}: {val.strip()}")
        if profile_parts:
            prompt += "\n\n## Role Profile\n" + "\n".join(profile_parts)

    # Inject custom skill content as knowledge
    registry = get_registry()
    custom_skill_ids = [
        sid for sid in role.get("skills", [])
        if not registry.get(sid)
    ]
    if custom_skill_ids:
        from data.database import get_db
        # Single DB connection reused for all skills
        conn = get_db()
        for sid in custom_skill_ids:
            # Validate sid format before query (prevent injection)
            if not isinstance(sid, str) or len(sid) > 128:
                continue
            row = conn.execute(
                "SELECT content FROM custom_skills WHERE id = ?", (sid,)
            ).fetchone()
            if row:
                prompt += f"\n\n---\n## Custom Skill\n{row[0]}"

    return prompt
