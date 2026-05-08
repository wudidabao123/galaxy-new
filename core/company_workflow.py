"""Company workflow — hierarchical reporting: Chairman → CEO → Dept Heads → Teams.

All workflow steps now call real LLM agents (via _run_agent_to_text)
instead of being empty shells.
"""

from __future__ import annotations

import json
import re as _re
import uuid
from typing import Any

from data.company_store import (
    get_project, save_project, save_assignment, get_company_structure,
    list_assignments,
)
from data.soul_store import get_soul_agent, add_agent_project, build_soul_agent_context
from data.model_store import get_model, get_model_api_key, get_default_model
from skills.registry import get_registry
from core.orchestrator import _run_agent_to_text


# ── JSON extraction helper ──────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract the first valid JSON object from text or markdown fences."""
    raw = (text or "").strip()
    if not raw:
        return {}
    fence = _re.search(r"```(?:json)?\s*(\{[^`]*?\})\s*```", raw, _re.I | _re.S)
    candidates: list[str] = []
    if fence:
        candidates.append(fence.group(1))
    if raw.startswith("{") and raw.endswith("}"):
        candidates.append(raw)
    starts = [m.start() for m in _re.finditer(r"\{", raw)]
    for start in starts:
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(raw)):
            ch = raw[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(raw[start:idx + 1])
                    break
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


# ── Soul agent → agent_info adapter ────────────────────

def _soul_agent_to_info(soul_agent: dict, run_id: str = "") -> dict | None:
    """Convert a soul_agent DB row into an agent_info dict compatible
    with _run_agent_to_text / _sync_agent_stream."""
    mid = soul_agent.get("model_id", "")
    model_data = get_model(mid) if mid else None
    if not model_data:
        model_data = get_default_model()
    if not model_data:
        return None

    mid_to_use = model_data["id"]
    api_key = get_model_api_key(mid_to_use)
    if not api_key:
        return None

    model_id_str = model_data.get("model", "")
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    from autogen_ext.models.openai._model_info import ModelFamily
    from config import KNOWN_OPENAI, MANUAL_TOOL_MODELS, AGENT_COLORS

    client_kwargs = {
        "model": model_id_str,
        "api_key": api_key,
        "base_url": model_data.get("base_url", ""),
    }
    if client_kwargs["model"] not in KNOWN_OPENAI:
        caps = model_data.get("capabilities", {})
        if isinstance(caps, dict) and "tools" in caps:
            client_kwargs["model_info"] = {
                "vision": caps.get("vision", False),
                "function_calling": caps.get("tools", True),
                "json_output": caps.get("json_mode", True),
                "family": caps.get("model_family", ModelFamily.ANY),
                "structured_output": caps.get("structured_output", False),
            }
        else:
            client_kwargs["model_info"] = {
                "vision": False, "function_calling": True,
                "json_output": True, "family": ModelFamily.ANY,
                "structured_output": False,
            }

    model_client = OpenAIChatCompletionClient(**client_kwargs)
    skill_ids = soul_agent.get("skills", [])
    registry = get_registry()
    tools = registry.build_tools(skill_ids)

    manual_tools = model_id_str.lower() in MANUAL_TOOL_MODELS
    display_name = soul_agent.get("name", "Agent")
    safe_name = _re.sub(r'[^a-zA-Z0-9_-]', '', display_name)
    if len(safe_name) < 2:
        safe_name = f"agent_{uuid.uuid4().hex[:6]}"

    system_prompt = build_soul_agent_context(soul_agent["id"], task="")

    return {
        "name": safe_name,
        "display_name": display_name,
        "agent": AssistantAgent(
            name=safe_name,
            system_message=system_prompt,
            model_client=model_client,
            tools=None if manual_tools else (tools if tools else None),
            reflect_on_tool_use=False if manual_tools else bool(tools),
            model_client_stream=True,
            max_tool_iterations=8,
        ),
        "model_id": mid_to_use,
        "model_cfg": model_data,
        "role_config": {
            "name": display_name,
            "skills": skill_ids,
            "soul_agent_id": soul_agent["id"],
        },
        "run_id": run_id,
        "context_length": int(model_data.get("context_length", 128000)),
        "system_prompt": system_prompt,
        "manual_tools": manual_tools,
        "color_idx": 0,
        "avatar": soul_agent.get("avatar", "🤖"),
        "color": AGENT_COLORS[hash(soul_agent["id"]) % len(AGENT_COLORS)],
    }


# ── Workflow steps ─────────────────────────────────────

def create_company_project(name: str, description: str = "", ceo_agent_id: str = "") -> dict:
    """Create a new company project."""
    proj_id = save_project({
        "id": "",
        "name": name,
        "description": description,
        "status": "pending",
        "ceo_agent_id": ceo_agent_id,
    })
    return get_project(proj_id) or {"id": proj_id}


def ceo_decompose_task(project_id: str, task: str, ceo_agent_id: str) -> list[dict]:
    """CEO decomposes a task into department assignments via LLM.

    The CEO agent analyzes the task and company structure, then decides
    which departments should handle which sub-tasks.
    Returns list of assignment dicts.
    """
    ceo = get_soul_agent(ceo_agent_id)
    if not ceo:
        return []

    agent_info = _soul_agent_to_info(ceo, run_id=project_id)
    if not agent_info:
        return []

    structure = get_company_structure()
    departments = structure.get("departments", [])
    active_depts = [d for d in departments if d.get("head_agent_id")]

    if not active_depts:
        return []

    # Build department summary for CEO to analyze
    dept_summary = []
    for d in active_depts:
        head = d.get("head_agent") or {}
        members = d.get("members", [])
        line = f"- {d.get('name', '?')} (head_id={d.get('head_agent_id','?')}"
        if head.get("name"):
            line += f", head_name={head['name']}"
        if head.get("worker_thought"):
            line += f", vibe={head['worker_thought']}"
        line += ")"
        if members:
            line += f" | members: {', '.join(m.get('name','?') for m in members[:5])}"
        dept_summary.append(line)

    ceo_task = f"""## CEO Task: Decompose Project

**Project**: {project_id}
**Task from Chairman**: {task}

**Company Departments**:
{chr(10).join(dept_summary)}

Your job as CEO:
1. Analyze the Chairman's task.
2. Decide which departments should handle which sub-tasks.
3. For each department, write a concrete task description that the department head can execute.

Output a JSON object with NO markdown blocks:
{{
  "analysis": "brief analysis of the task",
  "assignments": [
    {{
      "department": "department name",
      "head_agent_id": "agent-id-from-list-above",
      "task": "specific task description with expected deliverable"
    }}
  ]
}}"""

    raw = _run_agent_to_text(agent_info, ceo_task)

    # Parse CEO's JSON output
    try:
        data = _extract_json(raw)
        assignments_raw = data.get("assignments", [])
    except Exception:
        # Fallback: assign to all active departments equally
        assignments_raw = [
            {"department": d.get("name", "?"), "head_agent_id": d["head_agent_id"],
             "task": f"[{d.get('name', '?')}] {task[:200]}"}
            for d in active_depts
        ]

    # Persist assignments
    assignments = []
    for a in assignments_raw[:8]:  # max 8 departments per project
        head_id = a.get("head_agent_id", "")
        dept = next((d for d in active_depts if d.get("head_agent_id") == head_id), None)
        if not dept:
            continue
        assign_id = save_assignment({
            "id": "",
            "project_id": project_id,
            "from_agent_id": ceo_agent_id,
            "to_agent_id": head_id,
            "task_description": str(a.get("task", "") or a.get("task_description", "")),
            "status": "pending",
        })
        assignments.append({
            "id": assign_id,
            "department": dept.get("name", ""),
            "head_agent_id": head_id,
            "task": a.get("task", ""),
        })

    # Update project status
    save_project({"id": project_id, "status": "in_progress"})

    # Record CEO's work
    add_agent_project(ceo_agent_id, project_id, "CEO",
                      f"Decomposed '{task[:100]}' into {len(assignments)} assignments")

    return assignments


def dept_head_execute(assignment_id: str, dept_agent_id: str) -> dict:
    """Department head executes an assigned task via LLM.

    1. Gets the assignment details
    2. Calls the department head agent with the task
    3. Auto-reports results back to CEO
    """
    all_assigns = list_assignments()
    assignment = next((a for a in all_assigns if a.get("id") == assignment_id), None)
    if not assignment:
        return {"error": f"Assignment {assignment_id} not found"}

    dept_agent = get_soul_agent(dept_agent_id)
    if not dept_agent:
        return {"error": f"Agent {dept_agent_id} not found"}

    agent_info = _soul_agent_to_info(dept_agent, run_id=assignment.get("project_id", ""))
    if not agent_info:
        return {"error": "Failed to create agent — check model/key config"}

    # Mark as in_progress
    save_assignment({
        "id": assignment_id,
        "status": "in_progress",
    })

    task_desc = assignment.get("task_description", "")
    exec_task = f"""## Department Task

**Assignment**: {task_desc}
**Project**: {assignment.get("project_id", "")}

You are the department head. Execute this task now.

Guidelines:
1. Read any relevant project files and context first.
2. Produce concrete deliverables — write files, run commands, generate outputs.
3. When done, summarize what you accomplished and what files you created/changed.
4. Keep your output clear and actionable.

Your final output MUST include a JSON summary:
{{
  "status": "done | needs_input | blocked",
  "summary": "what you accomplished",
  "files_changed": [],
  "commands_run": [],
  "handoff_note": "anything the CEO needs to know"
}}"""

    raw = _run_agent_to_text(agent_info, exec_task)

    # Try to extract structured result, fall back to raw text
    try:
        result = _extract_json(raw)
        report = result.get("summary", raw[:500])
        status = result.get("status", "done")
    except Exception:
        report = raw[:500]
        status = "done"

    # Report back to CEO
    full_report = f"[{status}] {report}"
    dept_head_report(assignment_id, full_report)

    # Record participation
    add_agent_project(
        dept_agent_id,
        assignment.get("project_id", ""),
        "Department Head",
        f"Executed: {task_desc[:200]} — {report[:200]}",
    )

    return {
        "assignment_id": assignment_id,
        "agent": dept_agent.get("name", "?"),
        "status": status,
        "report": report,
        "raw_output": raw,
    }


def dept_head_report(assignment_id: str, report: str) -> dict:
    """Department head reports results back to CEO."""
    save_assignment({
        "id": assignment_id,
        "status": "done",
        "report_text": report,
    })
    return {"assignment_id": assignment_id, "status": "done"}


def ceo_report_to_chairman(project_id: str, report: str) -> dict:
    """CEO compiles department reports and reports to Chairman."""
    save_project({
        "id": project_id,
        "status": "review",
    })

    # Record project participation for CEO
    proj = get_project(project_id)
    if proj and proj.get("ceo_agent_id"):
        add_agent_project(
            proj["ceo_agent_id"],
            project_id,
            "CEO",
            f"Managed project: {report[:200]}",
        )

    # Record for department heads
    assignments = list_assignments(project_id=project_id)
    for a in assignments:
        if a.get("status") == "done":
            add_agent_project(
                a["to_agent_id"],
                project_id,
                "Department Head",
                f"Completed: {a.get('task_description', '')[:200]}",
            )

    return {"project_id": project_id, "status": "review"}


def chairman_approve(project_id: str) -> dict:
    """Chairman approves the project."""
    save_project({"id": project_id, "status": "done"})
    return {"project_id": project_id, "status": "done"}


def get_project_status(project_id: str) -> dict:
    """Get full project status including all assignments."""
    project = get_project(project_id)
    if not project:
        return {"error": "Project not found"}

    assignments = list_assignments(project_id=project_id)

    # Enrich assignments with agent names
    for a in assignments:
        agent = get_soul_agent(a.get("to_agent_id", ""))
        a["agent_name"] = agent["name"] if agent else "Unknown"
        a["agent_avatar"] = agent["avatar"] if agent else "?"
        from_agent = get_soul_agent(a.get("from_agent_id", ""))
        a["from_agent_name"] = from_agent["name"] if from_agent else "Unknown"

    project["assignments"] = assignments
    if project.get("ceo_agent_id"):
        ceo = get_soul_agent(project["ceo_agent_id"])
        project["ceo_name"] = ceo["name"] if ceo else "Unknown"
        project["ceo_avatar"] = ceo["avatar"] if ceo else "?"

    return project
