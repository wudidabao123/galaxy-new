"""Company store — departments, projects, assignments, company structure."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from data.database import get_db, db_transaction


# ── Departments ──────────────────────────────────────

def list_departments() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM company_departments ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_department(dept_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM company_departments WHERE id = ?", (dept_id,)).fetchone()
    return dict(row) if row else None


def save_department(data: dict) -> str:
    dept_id = data.get("id", "") or f"dept_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with db_transaction() as conn:
        existing = conn.execute("SELECT id FROM company_departments WHERE id = ?", (dept_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE company_departments SET name=?, description=?, head_agent_id=?,
                   updated_at=? WHERE id=?""",
                (data.get("name", ""), data.get("description", ""),
                 data.get("head_agent_id") or None, now, dept_id),
            )
        else:
            conn.execute(
                """INSERT INTO company_departments (id, name, description, head_agent_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (dept_id, data.get("name", ""), data.get("description", ""),
                 data.get("head_agent_id") or None, now, now),
            )
    return dept_id


def delete_department(dept_id: str) -> None:
    with db_transaction() as conn:
        conn.execute("DELETE FROM company_departments WHERE id = ?", (dept_id,))
        conn.execute("UPDATE soul_agents SET department_id = NULL WHERE department_id = ?", (dept_id,))


# ── Projects ────────────────────────────────────────

def list_projects(status: str = "") -> list[dict]:
    conn = get_db()
    if status:
        rows = conn.execute("SELECT * FROM company_projects WHERE status = ? ORDER BY created_at DESC",
                            (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM company_projects ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM company_projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def save_project(data: dict) -> str:
    proj_id = data.get("id", "") or f"proj_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with db_transaction() as conn:
        existing = conn.execute("SELECT id FROM company_projects WHERE id = ?", (proj_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE company_projects SET name=?, description=?, status=?,
                   chairman_id=?, ceo_agent_id=?, run_id=?, updated_at=? WHERE id=?""",
                (data.get("name", ""), data.get("description", ""), data.get("status", "pending"),
                 data.get("chairman_id") or None, data.get("ceo_agent_id") or None,
                 data.get("run_id") or None, now, proj_id),
            )
        else:
            conn.execute(
                """INSERT INTO company_projects (id, name, description, status,
                   chairman_id, ceo_agent_id, run_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (proj_id, data.get("name", ""), data.get("description", ""),
                 data.get("status", "pending"), data.get("chairman_id") or None,
                 data.get("ceo_agent_id") or None, data.get("run_id") or None,
                 now, now),
            )
    return proj_id


def delete_project(project_id: str) -> None:
    with db_transaction() as conn:
        conn.execute("DELETE FROM project_assignments WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM company_projects WHERE id = ?", (project_id,))


# ── Assignments ──────────────────────────────────────

def list_assignments(project_id: str = "", agent_id: str = "") -> list[dict]:
    conn = get_db()
    if project_id:
        rows = conn.execute(
            "SELECT * FROM project_assignments WHERE project_id = ? ORDER BY created_at",
            (project_id,)).fetchall()
    elif agent_id:
        rows = conn.execute(
            "SELECT * FROM project_assignments WHERE to_agent_id = ? ORDER BY created_at DESC",
            (agent_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM project_assignments ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def save_assignment(data: dict) -> str:
    assign_id = data.get("id", "") or f"assign_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with db_transaction() as conn:
        existing = conn.execute("SELECT id FROM project_assignments WHERE id = ?", (assign_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE project_assignments SET project_id=?, from_agent_id=?,
                   to_agent_id=?, task_description=?, status=?, report_text=?,
                   updated_at=? WHERE id=?""",
                (data.get("project_id", ""), data.get("from_agent_id") or None,
                 data.get("to_agent_id", ""), data.get("task_description", ""),
                 data.get("status", "pending"), data.get("report_text", ""),
                 now, assign_id),
            )
        else:
            conn.execute(
                """INSERT INTO project_assignments (id, project_id, from_agent_id,
                   to_agent_id, task_description, status, report_text, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (assign_id, data.get("project_id", ""), data.get("from_agent_id") or None,
                 data.get("to_agent_id", ""), data.get("task_description", ""),
                 data.get("status", "pending"), data.get("report_text", ""),
                 now, now),
            )
    return assign_id


# ── Company Structure ────────────────────────────────

def get_company_structure() -> dict:
    """Return the full company hierarchy: departments, agents by position, projects."""
    departments = list_departments()
    from data.soul_store import list_soul_agents
    agents = list_soul_agents()

    # Enrich departments with head agent info
    for dept in departments:
        head_id = dept.get("head_agent_id")
        if head_id:
            dept["head_agent"] = next((a for a in agents if a["id"] == head_id), None)
        else:
            dept["head_agent"] = None
        # Members in this department
        dept["members"] = [a for a in agents if a.get("department_id") == dept["id"]]

    # Group agents by position
    positions = {
        "ceo": [a for a in agents if a.get("position") == "ceo"],
        "dept_head": [a for a in agents if a.get("position") == "dept_head"],
        "member": [a for a in agents if a.get("position") == "member"],
        "unassigned": [a for a in agents if not a.get("position")],
    }

    projects = list_projects()

    # Enrich projects with assignments
    for proj in projects:
        proj["assignments"] = list_assignments(project_id=proj["id"])
        if proj.get("ceo_agent_id"):
            proj["ceo_agent"] = next((a for a in agents if a["id"] == proj["ceo_agent_id"]), None)

    return {
        "departments": departments,
        "agents": agents,
        "positions": positions,
        "projects": projects,
    }


# ── Company Settings ─────────────────────────────────

def get_company_setting(key: str, default: str = "") -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM company_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_company_setting(key: str, value: str) -> None:
    with db_transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO company_settings (key, value) VALUES (?, ?)", (key, value))
