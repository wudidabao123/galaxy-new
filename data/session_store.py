"""Session store — chat session persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from data.database import db_transaction, get_db


def list_sessions() -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, team_id, user_name, user_identity, created_at, updated_at "
        "FROM chat_sessions ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_session(sid: str) -> dict[str, Any] | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (sid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["history"] = json.loads(d.pop("history_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["history"] = []
    return d


def save_session(
    sid: str | None,
    title: str,
    team_id: str,
    user_name: str,
    user_identity: str,
    history: list[dict],
) -> str:
    sid = sid or f"chat_{uuid.uuid4().hex[:10]}"
    now = datetime.now().isoformat(timespec="seconds")
    hist_json = json.dumps(history, ensure_ascii=False, default=str)
    # Enforce length limit to prevent DB bloat (max 2MB)
    if len(hist_json) > 2_000_000:
        import logging
        logging.warning(
            "save_session: history too large (%d chars), truncating", len(hist_json)
        )
        hist_json = hist_json[:2_000_000]

    with db_transaction() as conn:
        existing = conn.execute(
            "SELECT created_at FROM chat_sessions WHERE id = ?", (sid,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE chat_sessions SET title=?, team_id=?, user_name=?, "
                "user_identity=?, history_json=?, updated_at=? WHERE id=?",
                (title, team_id, user_name, user_identity, hist_json, now, sid),
            )
        else:
            conn.execute(
                "INSERT INTO chat_sessions (id, title, team_id, user_name, "
                "user_identity, history_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, title, team_id, user_name, user_identity, hist_json, now, now),
            )
    return sid


def delete_session(sid: str) -> bool:
    with db_transaction() as conn:
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (sid,))
    return True
