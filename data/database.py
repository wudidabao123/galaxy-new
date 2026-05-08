"""SQLite database connection and migration management."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from config import DB_PATH as DATABASE_PATH, RUNTIME_DIRS


_local = threading.local()


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        for d in RUNTIME_DIRS:
            d.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
    conn = get_db()
    _thread_id = threading.get_ident()
    try:
        yield conn
        if threading.get_ident() != _thread_id:
            raise RuntimeError(
                "db_transaction: thread changed during transaction. "
                "SQLite connections are per-thread; do not cross threads."
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            model_name TEXT NOT NULL DEFAULT '',
            key_ref TEXT NOT NULL DEFAULT '',
            base_url TEXT NOT NULL DEFAULT '',
            context_length INTEGER NOT NULL DEFAULT 128000,
            capabilities TEXT NOT NULL DEFAULT '{}',
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '未分类',
            chat_style TEXT NOT NULL DEFAULT 'round',
            max_turns INTEGER NOT NULL DEFAULT 10,
            roles_json TEXT NOT NULL DEFAULT '[]',
            parallel_stages_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            team_id TEXT NOT NULL DEFAULT '',
            user_name TEXT NOT NULL DEFAULT '我',
            user_identity TEXT NOT NULL DEFAULT '',
            history_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS run_states (
            run_id TEXT PRIMARY KEY,
            task TEXT NOT NULL DEFAULT '',
            team_id TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL DEFAULT '',
            state_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT '',
            agent TEXT NOT NULL DEFAULT '',
            structured_json TEXT NOT NULL DEFAULT '{}',
            guard_json TEXT NOT NULL DEFAULT '{}',
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tool_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            agent_name TEXT NOT NULL DEFAULT '',
            tool_name TEXT NOT NULL DEFAULT '',
            args_preview TEXT NOT NULL DEFAULT '',
            target_path TEXT NOT NULL DEFAULT '',
            allowed INTEGER NOT NULL DEFAULT 1,
            result_status TEXT NOT NULL DEFAULT 'unknown',
            error TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS custom_skills (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'knowledge',
            overview TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS soul_presets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            overview TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS project_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS model_usage (
            model_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL DEFAULT '',
            calls INTEGER NOT NULL DEFAULT 0,
            input_tokens_est INTEGER NOT NULL DEFAULT 0,
            output_tokens_est INTEGER NOT NULL DEFAULT 0,
            total_tokens_est INTEGER NOT NULL DEFAULT 0,
            last_used TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS custom_tools (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            code TEXT DEFAULT '',
            parameters_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_stage_logs_run ON stage_logs(run_id);
        CREATE INDEX IF NOT EXISTS idx_tool_logs_run ON tool_logs(run_id);
        CREATE INDEX IF NOT EXISTS idx_teams_category ON teams(category);
    """)
    conn.commit()
    # B3: periodic WAL checkpoint to prevent unchecked WAL file growth
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
