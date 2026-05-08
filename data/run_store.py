"""Run store — RunState, stage logs, tool logs persistence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from data.database import db_transaction, get_db


# ── Run State ─────────────────────────────────────────

def save_run_state(run_id: str, task: str, team_id: str, mode: str,
                   state: dict | None = None) -> None:
    """Save run state. Accepts a dict for state, serializes internally."""
    now = datetime.now().isoformat(timespec="seconds")
    state_json = json.dumps(state or {}, ensure_ascii=False, default=str)
    # Enforce length limit to prevent DB bloat (max 500KB)
    if len(state_json) > 500_000:
        import logging
        logging.warning(
            "save_run_state: state_json too large (%d chars), truncating", len(state_json)
        )
        state_json = state_json[:500_000]
    with db_transaction() as conn:
        existing = conn.execute(
            "SELECT 1 FROM run_states WHERE run_id = ?", (run_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE run_states SET task=?, team_id=?, mode=?, state_json=?, "
                "updated_at=? WHERE run_id=?",
                (task, team_id, mode, state_json, now, run_id),
            )
        else:
            conn.execute(
                "INSERT INTO run_states (run_id, task, team_id, mode, state_json, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, task, team_id, mode, state_json, now, now),
            )


def load_run_state(run_id: str) -> dict[str, Any] | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM run_states WHERE run_id = ?", (run_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["state"] = json.loads(d.pop("state_json", "{}"))
    except (json.JSONDecodeError, TypeError) as e:
        import logging
        logging.warning(
            "load_run_state: failed to parse state_json for run_id=%s: %s",
            run_id, e,
        )
        d["state"] = {}
    return d


def list_run_states(limit: int = 100) -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT run_id, task, team_id, mode, created_at, updated_at "
        "FROM run_states ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Stage Logs ────────────────────────────────────────

def append_stage_log(run_id: str, stage: str, agent: str,
                     structured: dict, guard: dict, retry_count: int = 0) -> None:
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO stage_logs (run_id, stage, agent, structured_json, "
            "guard_json, retry_count) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, stage, agent,
             json.dumps(structured, ensure_ascii=False, default=str),
             json.dumps(guard, ensure_ascii=False, default=str),
             retry_count),
        )


def get_stage_logs(run_id: str) -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM stage_logs WHERE run_id = ? ORDER BY id ASC",
        (run_id,),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["structured"] = json.loads(d.pop("structured_json", "{}"))
        except Exception:
            d["structured"] = {}
        try:
            d["guard"] = json.loads(d.pop("guard_json", "{}"))
        except Exception:
            d["guard"] = {}
        result.append(d)
    return result


# ── Tool Logs ─────────────────────────────────────────

def append_tool_log(
    run_id: str, agent_name: str, tool_name: str, args_preview: str,
    target_path: str = "", allowed: bool = True,
    result_status: str = "unknown", error: str = "", duration_ms: int = 0,
) -> None:
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO tool_logs (run_id, agent_name, tool_name, args_preview, "
            "target_path, allowed, result_status, error, duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, agent_name, tool_name, args_preview, target_path,
             1 if allowed else 0, result_status, error, duration_ms),
        )


def get_tool_logs(run_id: str, limit: int = 500) -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM tool_logs WHERE run_id = ? ORDER BY id DESC LIMIT ?",
        (run_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
