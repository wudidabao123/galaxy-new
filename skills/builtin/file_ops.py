"""File operation tools — read, write, list, search, safe delete."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
import re as _re


def _clip_output(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


def _safe_workspace_path(path: str, *, root: Path) -> Path:
    # Block paths containing '..' to prevent directory traversal
    raw = (path or "").replace("\\", "/")
    if ".." in raw:
        raise ValueError(f"Path traversal blocked: '..' not allowed in path")
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path must stay inside workspace: {root}")
    return candidate


# ── Tools ─────────────────────────────────────────────

def tool_read_file(path: str, max_chars: int = 20000) -> str:
    """Read a UTF-8 text file from the workspace and return its content.
    Args: path (relative to workspace), max_chars (default 20000, max 80000).
    """
    from config import DATA_DIR  # dynamic import avoids circular
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        limit = max(1000, min(int(max_chars), 80000))
        return _clip_output(target.read_text(encoding="utf-8", errors="replace"), limit)
    except Exception as e:
        return f"Error: {e}"


def tool_write_file(path: str, content: str, overwrite: bool = True) -> str:
    """Write a UTF-8 text file inside the workspace. Creates parent folders as needed."""
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        if target.exists() and not overwrite:
            return f"Error: file already exists: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {target}"
    except Exception as e:
        return f"Error: {e}"


def tool_write_base64_file(path: str, base64_content: str, overwrite: bool = True) -> str:
    """Write a binary file from base64. Useful for images, archives, etc."""
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        if target.exists() and not overwrite:
            return f"Error: file already exists: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(base64_content)
        target.write_bytes(data)
        return f"Wrote {len(data)} bytes to {target}"
    except Exception as e:
        return f"Error: {e}"


def tool_list_files(path: str = ".", pattern: str = "*", max_results: int = 200) -> str:
    """List files under a workspace path. Supports glob patterns like *.py or **/*.json."""
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        limit = max(1, min(int(max_results), 1000))
        files = []
        for p in target.glob(pattern):
            with contextlib.suppress(Exception):
                rel = p.relative_to(root)
                suffix = "/" if p.is_dir() else ""
                files.append(str(rel).replace("\\", "/") + suffix)
            if len(files) >= limit:
                break
        return "\n".join(files) if files else "(no files)"
    except Exception as e:
        return f"Error: {e}"


def tool_search_text(query: str, path: str = ".", file_pattern: str = "**/*",
                     case_sensitive: bool = False, regex: bool = False,
                     max_results: int = 100) -> str:
    """Search text in workspace files. Use for code navigation before editing.
    Set regex=true only when query is a regular expression."""
    import re as _local_re
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        flags = 0 if case_sensitive else _local_re.IGNORECASE
        pattern = _local_re.compile(query if regex else _local_re.escape(query), flags)
        limit = max(1, min(int(max_results), 500))
        skipped = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".next", "runs"}
        matches: list[str] = []
        for p in target.glob(file_pattern):
            if len(matches) >= limit:
                break
            if not p.is_file() or any(part in skipped for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    matches.append(f"{rel}:{lineno}: {line[:240]}")
                    if len(matches) >= limit:
                        break
        return "\n".join(matches) if matches else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


def tool_read_many_files(paths: str, max_chars_per_file: int = 8000) -> str:
    """Read multiple workspace text files. Pass newline/comma separated paths."""
    root = _get_workspace_root()
    try:
        limit = max(1000, min(int(max_chars_per_file), 30000))
        raw_paths = [p.strip() for part in paths.splitlines() for p in part.split(",")]
        chunks = []
        for raw in [p for p in raw_paths if p]:
            target = _safe_workspace_path(raw, root=root)
            text = target.read_text(encoding="utf-8", errors="replace")
            rel = str(target.relative_to(root)).replace("\\", "/")
            chunks.append(f"## {rel}\n{_clip_output(text, limit)}")
        return "\n\n".join(chunks) if chunks else "Error: no paths provided"
    except Exception as e:
        return f"Error: {e}"


def tool_replace_in_file(path: str, old: str, new: str, count: int = 0) -> str:
    """Replace exact text in one workspace file. Use after reading the file.
    count=0 replaces all occurrences."""
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        text = target.read_text(encoding="utf-8", errors="replace")
        if old not in text:
            return "Error: old text not found"
        n = int(count or 0)
        updated = text.replace(old, new, n if n > 0 else -1)
        target.write_text(updated, encoding="utf-8")
        return f"Replaced {text.count(old) if n <= 0 else min(text.count(old), n)} occurrence(s) in {target}"
    except Exception as e:
        return f"Error: {e}"


def tool_file_info(path: str) -> str:
    """Return file or directory metadata inside the workspace."""
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        stat = target.stat()
        info = {
            "path": str(target),
            "is_dir": target.is_dir(),
            "is_file": target.is_file(),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
        if target.is_file():
            data = target.read_bytes()
            info["sha256"] = hashlib.sha256(data).hexdigest()
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"


def tool_make_directory(path: str) -> str:
    """Create a directory inside the workspace, including parents."""
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        target.mkdir(parents=True, exist_ok=True)
        return f"Directory ready: {target}"
    except Exception as e:
        return f"Error: {e}"


def tool_safe_delete(path: str) -> str:
    """Move a file to .trash/ instead of permanently deleting. Safe undo-able delete."""
    from config import DATA_DIR
    root = _get_workspace_root()
    try:
        target = _safe_workspace_path(path, root=root)
        if not target.exists():
            return f"Error: file not found: {target}"
        trash_dir = DATA_DIR / ".trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = trash_dir / f"{ts}_{target.name}"
        import shutil
        shutil.move(str(target), str(dest))
        return f"Moved to trash: {dest}"
    except Exception as e:
        return f"Error: {e}"


# ── Workspace root resolution ─────────────────────────

def _get_workspace_root() -> Path:
    """Get the current active workspace root from project state.
    Falls back to config DATA_DIR."""
    from config import DATA_DIR
    try:
        from data.database import get_db
        conn = get_db()
        row = conn.execute(
            "SELECT value FROM project_state WHERE key = 'root'"
        ).fetchone()
        if row and row[0]:
            p = Path(row[0]).expanduser().resolve()
            if p.exists() and p.is_dir():
                return p
    except Exception:
        pass
    return DATA_DIR.resolve()
