"""Company workflow — hierarchical reporting: Chairman → CEO → Dept Heads → Teams."""

from __future__ import annotations

import json
import uuid
from typing import Any

from data.company_store import (
    get_project, save_project, save_assignment, get_company_structure,
)
from data.soul_store import get_soul_agent, add_agent_project


def create_company_project(name: str, description: str = "", ceo_agent_id: str = "") -> dict:
    """Create a new company project. CEO agent is optional — will use first available."""
    proj_id = save_project({
        "id": "",
        "name": name,
        "description": description,
        "status": "pending",
        "ceo_agent_id": ceo_agent_id,
    })
    return get_project(proj_id) or {"id": proj_id}


def ceo_decompose_task(project_id: str, task: str, ceo_agent_id: str) -> list[dict]:
    """CEO decomposes a task into department assignments.

    In production, this would call the CEO agent via LLM to analyze the task
    and assign sub-tasks to department heads. For now, it uses the company
    structure to create assignments.
    """
    structure = get_company_structure()
    departments = structure.get("departments", [])

    # Find departments with heads
    active_depts = [d for d in departments if d.get("head_agent_id")]
    if not active_depts:
        return []

    # Create assignments for each department with a head
    assignments = []
    for dept in active_depts:
        assign_id = save_assignment({
            "id": "",
            "project_id": project_id,
            "from_agent_id": ceo_agent_id,
            "to_agent_id": dept["head_agent_id"],
            "task_description": f"[{dept.get('name', '?')}] {task}",
            "status": "pending",
        })
        assignments.append({
            "id": assign_id,
            "department": dept.get("name", ""),
            "head_agent_id": dept["head_agent_id"],
            "task": task,
        })

    # Update project status
    save_project({"id": project_id, "status": "in_progress"})

    return assignments


def dept_head_execute(assignment_id: str, dept_agent_id: str) -> dict:
    """Department head executes a task.

    In production, this would:
    1. Have the dept head analyze the task
    2. Either pick an existing team or AI-generate a team
    3. Execute the team in parallel
    4. Compile results and report back
    """
    # For now, mark as in_progress
    save_assignment({
        "id": assignment_id,
        "to_agent_id": dept_agent_id,
        "status": "in_progress",
    })
    return {"assignment_id": assignment_id, "status": "in_progress"}


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
    from data.company_store import list_assignments
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

    from data.company_store import list_assignments
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
