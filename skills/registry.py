"""Skill Registry — centralized tool registration for Galaxy New.

Tools are registered with a unique ID, display name, function, and description.
The system prompt and tool list for each agent are built from this registry.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Callable

from autogen_core.tools import FunctionTool


class SkillInfo:
    __slots__ = ("name", "fn", "desc")

    def __init__(self, name: str, fn: Callable, desc: str):
        self.name = name
        self.fn = fn
        self.desc = desc


class SkillRegistry:
    """Global registry of all available built-in tools."""

    def __init__(self) -> None:
        self._skills: OrderedDict[str, SkillInfo] = OrderedDict()

    def register(self, sid: str, name: str, fn: Callable, desc: str) -> None:
        self._skills[sid] = SkillInfo(name=name, fn=fn, desc=desc)

    def list_all(self) -> OrderedDict[str, SkillInfo]:
        return self._skills

    def get(self, sid: str) -> SkillInfo | None:
        return self._skills.get(sid)

    def build_tools(self, skill_ids: list[str]) -> list[FunctionTool]:
        """Build a list of FunctionTool objects from skill IDs.
        Returns tools in registry order, filtered by the given IDs.
        First checks the in-memory registry, then falls back to custom_tools DB.
        """
        tools = []
        seen = set()
        for sid in skill_ids:
            if sid in seen:
                continue
            seen.add(sid)
            skill = self._skills.get(sid)
            if skill is not None:
                tools.append(FunctionTool(
                    skill.fn,
                    name=sid,
                    description=skill.desc or skill.fn.__doc__ or "",
                ))
                continue
            # Fallback: try loading from custom_tools DB
            try:
                from core.tool_manager import get_custom_tools_for_agent
                custom_tools = get_custom_tools_for_agent([sid])
                tools.extend(custom_tools)
            except Exception:
                pass
        return tools

    def build_tool_specs(self, skill_ids: list[str]) -> str:
        """Build a text description of tool specs (for manual tool protocol)."""
        import inspect
        lines = []
        seen = set()
        for sid in skill_ids:
            if sid in seen:
                continue
            skill = self._skills.get(sid)
            if skill is None:
                continue
            seen.add(sid)
            try:
                sig = str(inspect.signature(skill.fn))
            except Exception:
                sig = "(...)"
            doc = (skill.fn.__doc__ or skill.desc).strip().splitlines()[0]
            lines.append(f"- {sid}{sig}: {doc}")
        return ("\n".join(lines) if lines else "(no tools available)")[:8000]


# ── Global singleton ──────────────────────────────────
_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


def register_skill(sid: str, name: str, fn: Callable, desc: str) -> None:
    get_registry().register(sid, name, fn, desc)


def build_skills_summary_for(skill_ids: list[str]) -> str:
    """Build a text summary for a specific set of skill IDs.
    Only lists tools the agent actually has access to, saving tokens."""
    registry = get_registry()
    if not skill_ids:
        return "(No tools assigned)"

    lines = ["## Available Tools & Skills"]
    seen = set()
    for sid in skill_ids:
        if sid in seen:
            continue
        seen.add(sid)
        info = registry.get(sid)
        if not info:
            continue
        import inspect
        try:
            sig = str(inspect.signature(info.fn))
            sig_short = sig if len(sig) <= 120 else sig[:117] + "..."
        except Exception:
            sig_short = "(...)"
        lines.append(f"- **{sid}** ({info.name}): {info.desc} — `{sig_short}`")
    return "\n".join(lines)


def build_all_skills_summary() -> str:
    """Build a text summary of all registered tools (for admin preview, NOT for agent context).
    Prefer build_skills_summary_for() when injecting context into soul agents."""
    registry = get_registry()
    skills = registry.list_all()
    return build_skills_summary_for(list(skills.keys()))
