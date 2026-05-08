"""Soul agent persistence — CRUD, notes, project tracking, lifespan management."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from data.database import get_db, db_transaction
from skills.registry import build_skills_summary_for


# ── CRUD ─────────────────────────────────────────────

def list_soul_agents() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM soul_agents ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_soul_agent(agent_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM soul_agents WHERE id = ?", (agent_id,)).fetchone()
    return _row_to_dict(row) if row else None


def save_soul_agent(data: dict) -> str:
    """Create or update a soul agent. Returns the agent id."""
    agent_id = data.get("id", "") or f"soul_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with db_transaction() as conn:
        existing = conn.execute("SELECT id FROM soul_agents WHERE id = ?", (agent_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE soul_agents SET name=?, avatar=?, soul_md=?, worker_thought=?,
                   notes=?, projects_json=?, lifespan_budget=?, position=?,
                   department_id=?, model_id=?, skills_json=?, updated_at=?
                   WHERE id=?""",
                (
                    data.get("name", ""),
                    data.get("avatar", "🤖"),
                    data.get("soul_md", ""),
                    data.get("worker_thought", ""),
                    data.get("notes", ""),
                    json.dumps(data.get("projects", []), ensure_ascii=False),
                    data.get("lifespan_budget", 128000),
                    data.get("position", ""),
                    data.get("department_id") or None,
                    data.get("model_id", ""),
                    json.dumps(data.get("skills", []), ensure_ascii=False),
                    now,
                    agent_id,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO soul_agents (id, name, avatar, soul_md, worker_thought,
                   notes, projects_json, lifespan_budget, position, department_id,
                   model_id, skills_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    data.get("name", ""),
                    data.get("avatar", "🤖"),
                    data.get("soul_md", ""),
                    data.get("worker_thought", ""),
                    data.get("notes", ""),
                    json.dumps(data.get("projects", []), ensure_ascii=False),
                    data.get("lifespan_budget", 128000),
                    data.get("position", ""),
                    data.get("department_id") or None,
                    data.get("model_id", ""),
                    json.dumps(data.get("skills", []), ensure_ascii=False),
                    now,
                    now,
                ),
            )
    return agent_id


def delete_soul_agent(agent_id: str) -> None:
    with db_transaction() as conn:
        conn.execute("DELETE FROM soul_agents WHERE id = ?", (agent_id,))
        conn.execute("UPDATE company_departments SET head_agent_id = NULL WHERE head_agent_id = ?", (agent_id,))
        conn.execute("UPDATE company_projects SET ceo_agent_id = NULL WHERE ceo_agent_id = ?", (agent_id,))


# ── Notes & Projects ─────────────────────────────────

def add_agent_note(agent_id: str, note: str) -> None:
    """Append a timestamped note to the agent's notes."""
    agent = get_soul_agent(agent_id)
    if not agent:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n[{ts}] {note.strip()}"
    new_notes = agent["notes"] + entry
    with db_transaction() as conn:
        conn.execute("UPDATE soul_agents SET notes=?, updated_at=? WHERE id=?",
                     (new_notes, datetime.now().isoformat(), agent_id))


def add_agent_project(agent_id: str, project_id: str, role: str, summary: str) -> None:
    agent = get_soul_agent(agent_id)
    if not agent:
        return
    projects = agent.get("projects", [])
    projects.append({
        "project_id": project_id,
        "role": role,
        "summary": summary,
        "completed_at": datetime.now().isoformat(),
    })
    with db_transaction() as conn:
        conn.execute("UPDATE soul_agents SET projects_json=?, updated_at=? WHERE id=?",
                     (json.dumps(projects, ensure_ascii=False), datetime.now().isoformat(), agent_id))


# ── Lifespan / Context ───────────────────────────────

def compress_agent_context(agent_id: str, compress_ratio: float = 0.55) -> dict:
    """Longevity medicine: compress notes and project history.
    Returns dict with before/after stats."""
    agent = get_soul_agent(agent_id)
    if not agent:
        return {"error": "Agent not found"}

    from core.context import _clip_output

    notes_before = len(agent.get("notes", ""))
    projects_before = len(json.dumps(agent.get("projects", []), ensure_ascii=False))

    # Compress notes: keep first 500 chars, compress middle
    notes = agent.get("notes", "")
    if len(notes) > 1200:
        recent_notes = notes[-800:]
        old_notes = notes[:max(400, int(len(notes) * (1 - compress_ratio)))]
        compressed_notes = (
            f"[Compressed memory — {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n"
            f"Early experience summary: {_clip_output(old_notes, 600)}\n"
            f"---\nRecent notes: {recent_notes}"
        )
    else:
        compressed_notes = notes

    # Compress projects: summarize if many
    projects = agent.get("projects", [])
    if len(projects) > 8:
        recent_projects = projects[-4:]
        old_projects = projects[:-4]
        old_summary = "; ".join(
            f"{p.get('role','?')} in {p.get('project_id','?')}: {p.get('summary','')[:80]}"
            for p in old_projects
        )
        compressed_projects = recent_projects + [{
            "project_id": "_compressed",
            "role": "summary",
            "summary": f"[Compressed {len(old_projects)} earlier projects] {old_summary}",
            "completed_at": datetime.now().isoformat(),
        }]
    else:
        compressed_projects = projects

    with db_transaction() as conn:
        conn.execute(
            "UPDATE soul_agents SET notes=?, projects_json=?, updated_at=? WHERE id=?",
            (compressed_notes, json.dumps(compressed_projects, ensure_ascii=False),
             datetime.now().isoformat(), agent_id),
        )

    notes_after = len(compressed_notes)
    projects_after = len(json.dumps(compressed_projects, ensure_ascii=False))

    return {
        "notes_before": notes_before,
        "notes_after": notes_after,
        "projects_before": projects_before,
        "projects_after": projects_after,
        "notes_saved": notes_before - notes_after,
        "projects_saved": projects_before - projects_after,
    }


def build_soul_agent_context(agent_id: str, task: str = "") -> str:
    """Build the full system context for a soul agent.
    Includes: soul MD, notes summary, project history, available tools, and task.
    """
    agent = get_soul_agent(agent_id)
    if not agent:
        return ""

    parts = []

    # Soul MD (personality definition)
    if agent.get("soul_md"):
        parts.append(f"## Soul Identity\n{agent['soul_md']}")

    # Worker thought
    if agent.get("worker_thought"):
        parts.append(f"\n## 今日心情\n{agent['worker_thought']}")

    # Available tools — only the skills assigned to THIS agent
    agent_skills = agent.get("skills", [])
    tools_summary = build_skills_summary_for(agent_skills)
    parts.append(f"\n## Available Tools & Skills\n{tools_summary}")

    # Agent notes (accumulated experience)
    notes = agent.get("notes", "")
    if notes:
        notes_brief = notes if len(notes) <= 3000 else notes[-3000:]
        parts.append(f"\n## Your Notes & Experience\n{notes_brief}")

    # Project history
    projects = agent.get("projects", [])
    if projects:
        proj_lines = []
        for p in projects[-8:]:
            proj_lines.append(
                f"- [{p.get('role','?')}] {p.get('project_id','?')}: "
                f"{p.get('summary','')[:120]}"
            )
        parts.append(f"\n## Past Projects\n" + "\n".join(proj_lines))

    # Lifespan info
    total_chars = sum(len(p) for p in parts)
    budget = agent.get("lifespan_budget", 128000)
    usage_pct = int(total_chars / max(budget, 1) * 100)
    parts.append(
        f"\n## Lifespan\nContext budget: {budget} tokens. "
        f"Current usage: ~{usage_pct}%. "
        f"(tip: 服用长生药可压缩笔记和项目历史，释放上下文空间)"
    )

    # Current task
    if task:
        parts.append(f"\n## Current Task\n{task}")

    return "\n\n".join(parts)


# ── Helpers ──────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    d["projects"] = _safe_json_loads(d.pop("projects_json", "[]"), [])
    d["skills"] = _safe_json_loads(d.pop("skills_json", "[]"), [])
    return d


def _safe_json_loads(text, default):
    try:
        return json.loads(text) if text else default
    except (json.JSONDecodeError, TypeError):
        return default
