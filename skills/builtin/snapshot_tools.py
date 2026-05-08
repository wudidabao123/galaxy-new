"""Snapshot & conflict tools for concurrent engineering."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


def _get_workspace_root() -> Path:
    from skills.builtin.file_ops import _get_workspace_root as _r
    return _r()


def tool_workspace_snapshot(path_glob: str = "**/*") -> str:
    """Take a snapshot of the current workspace file state (path, size, sha256, modified time).
    Use this before and after changes to track what actually changed.
    Args: path_glob — glob pattern, defaults to all files.
    Excludes: .git, .venv, node_modules, __pycache__, runs, generated, .trash.
    """
    root = _get_workspace_root()
    skipped = {".git", ".venv", "node_modules", "__pycache__", "dist", "build",
               ".next", "runs", "generated", "backups", ".trash", "__pycache__"}
    files = []

    for p in root.glob(path_glob):
        if not p.is_file():
            continue
        if any(part in skipped for part in p.parts):
            continue
        try:
            stat = p.stat()
            rel = str(p.relative_to(root)).replace("\\", "/")
            files.append({
                "path": rel,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            })
        except Exception:
            continue

    files.sort(key=lambda f: f["path"])
    return json.dumps({
        "root": str(root),
        "file_count": len(files),
        "files": files[:200],
        "truncated": len(files) > 200,
    }, ensure_ascii=False, indent=2)


def tool_conflict_check(agent_a: str, path_a: str, agent_b: str, path_b: str) -> str:
    """Check if two agents would conflict on the same file.
    Use before starting concurrent work to verify file boundaries.
    Args: agent_a, path_a, agent_b, path_b — two agents and their intended write paths.
    """
    norm_a = path_a.replace("\\", "/").strip("/")
    norm_b = path_b.replace("\\", "/").strip("/")

    if norm_a == norm_b:
        return json.dumps({
            "conflict": True,
            "severity": "high",
            "message": f"{agent_a} and {agent_b} both want to write {norm_a}. Assign to one agent only.",
        }, ensure_ascii=False, indent=2)

    # Check if one path contains the other
    if norm_a.startswith(norm_b.rstrip("/") + "/") or norm_b.startswith(norm_a.rstrip("/") + "/"):
        return json.dumps({
            "conflict": True,
            "severity": "medium",
            "message": f"Path overlap: {agent_a} has {norm_a}, {agent_b} has {norm_b}. These directories overlap.",
        }, ensure_ascii=False, indent=2)

    return json.dumps({
        "conflict": False,
        "message": f"No conflict: {agent_a}->{norm_a}, {agent_b}->{norm_b}",
    }, ensure_ascii=False, indent=2)
