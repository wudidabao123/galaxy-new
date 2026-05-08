"""Git tools — status, diff, and version control operations."""

from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import datetime


def _clip_output(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


def _get_workspace_root() -> Path:
    from skills.builtin.file_ops import _get_workspace_root as _r
    return _r()


def tool_git_diff(path: str = ".", max_chars: int = 20000) -> str:
    """Return git status and diff for the workspace path. Use to check changes before committing."""
    root = _get_workspace_root()
    try:
        status = subprocess.run(
            ["git", "status", "--short", "--", path],
            cwd=str(root), text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=20,
        )
        diff = subprocess.run(
            ["git", "diff", "--", path],
            cwd=str(root), text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=20,
        )
        output = [
            "[status]",
            status.stdout or status.stderr or "(clean)",
            "[diff]",
            diff.stdout or diff.stderr or "(no diff)",
        ]
        return _clip_output("\n".join(output), max(2000, min(int(max_chars), 80000)))
    except Exception as e:
        return f"Error: {e}"


def tool_git_status() -> str:
    """Show git status summary for the workspace."""
    root = _get_workspace_root()
    try:
        proc = subprocess.run(
            ["git", "status"],
            cwd=str(root), text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=15,
        )
        return _clip_output(f"exit_code={proc.returncode}\n\n{proc.stdout}{proc.stderr}")
    except Exception as e:
        return f"Error: {e}"


def tool_project_tree_summary(max_depth: int = 3, max_files: int = 200) -> str:
    """Generate a summary of the workspace directory structure. Use before starting work
    to understand the project layout without listing every file."""
    root = _get_workspace_root()
    skipped = {".git", ".venv", "node_modules", "__pycache__", "dist", "build",
               ".next", "runs", "generated", "backups", ".trash"}

    lines = [f"# Project Tree: {root.name}"]
    count = 0

    def _walk(current: Path, depth: int, prefix: str = ""):
        nonlocal count
        if depth > max_depth or count >= max_files:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            if count >= max_files:
                break
            if entry.name in skipped:
                continue
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            rel = entry.relative_to(root)
            count += 1
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, depth + 1, prefix + extension)

    _walk(root, 0)
    if count >= max_files:
        lines.append(f"... (truncated at {max_files} entries)")
    return "\n".join(lines)


def tool_dependency_scan() -> str:
    """Scan the workspace for dependency files (requirements.txt, pyproject.toml, package.json)
    and summarize what's declared."""
    root = _get_workspace_root()
    results = []

    # requirements.txt
    req_file = root / "requirements.txt"
    if req_file.exists():
        try:
            deps = [l.strip() for l in req_file.read_text(encoding="utf-8", errors="replace").splitlines()
                    if l.strip() and not l.strip().startswith("#")]
            results.append(f"## requirements.txt ({len(deps)} deps)")
            results.extend(f"- {d}" for d in deps[:50])
        except Exception as e:
            results.append(f"requirements.txt: error reading - {e}")

    # pyproject.toml
    pyproj = root / "pyproject.toml"
    if pyproj.exists():
        try:
            content = pyproj.read_text(encoding="utf-8", errors="replace")
            results.append(f"## pyproject.toml ({len(content)} chars)")
            results.append("(present, use read_file for details)")
        except Exception:
            pass

    # package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            content = pkg_json.read_text(encoding="utf-8", errors="replace")
            import json
            data = json.loads(content)
            deps = data.get("dependencies", {})
            dev_deps = data.get("devDependencies", {})
            results.append(f"## package.json (deps: {len(deps)}, devDeps: {len(dev_deps)})")
            results.extend(f"- {k}: {v}" for k, v in list(deps.items())[:30])
        except Exception as e:
            results.append(f"package.json: error - {e}")

    return "\n".join(results) if results else "No dependency files found in workspace root."
