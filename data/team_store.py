"""Team store — CRUD for agent teams."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from data.database import db_transaction, get_db


def list_teams() -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM teams ORDER BY category ASC, name ASC"
    ).fetchall()
    return [_row_to_team(r) for r in rows]


def get_team(team_id: str) -> dict[str, Any] | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    return _row_to_team(row) if row else None


def save_team(team: dict[str, Any]) -> str:
    """Save or update a team. Returns the team_id."""
    tid = team.get("id") or str(uuid.uuid4())[:6]
    now = datetime.now().isoformat(timespec="seconds")
    roles_json = json.dumps(team.get("roles", []), ensure_ascii=False)
    stages_json = json.dumps(team.get("parallel_stages", []), ensure_ascii=False)

    with db_transaction() as conn:
        existing = conn.execute("SELECT 1 FROM teams WHERE id = ?", (tid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE teams SET name=?, category=?, chat_style=?, max_turns=?, "
                "roles_json=?, parallel_stages_json=?, updated_at=? WHERE id=?",
                (team.get("name", ""), team.get("category", "未分类"),
                 team.get("chat_style", "round"), team.get("max_turns", 10),
                 roles_json, stages_json, now, tid),
            )
        else:
            conn.execute(
                "INSERT INTO teams (id, name, category, chat_style, max_turns, "
                "roles_json, parallel_stages_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tid, team.get("name", ""), team.get("category", "未分类"),
                 team.get("chat_style", "round"), team.get("max_turns", 10),
                 roles_json, stages_json, now, now),
            )
    return tid


def delete_team(team_id: str) -> bool:
    with db_transaction() as conn:
        # Cascade-delete related sessions and runs to avoid orphan data
        conn.execute("DELETE FROM chat_sessions WHERE team_id = ?", (team_id,))
        conn.execute("DELETE FROM run_states WHERE team_id = ?", (team_id,))
        conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    return True


# ── Helpers ───────────────────────────────────────────

def _row_to_team(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    d = dict(row)
    try:
        d["roles"] = json.loads(d.pop("roles_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["roles"] = []
    try:
        d["parallel_stages"] = json.loads(d.pop("parallel_stages_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["parallel_stages"] = []
    return d
