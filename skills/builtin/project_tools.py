"""Project analysis tools: dependency scan, tree summary, lint, format."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from skills.builtin.file_ops import _clip_output as _clip, _get_workspace_root as _workspace_root


def tool_project_tree_summary(max_depth: int = 3) -> str:
    """Generate a summary tree of the project structure to avoid blind exploration."""
    ws = _workspace_root()
    lines = [f"Project: {ws}"]
    _walk(ws, lines, depth=0, max_depth=max_depth, prefix="")
    return "\n".join(lines)


def _walk(path: Path, lines: list, depth: int, max_depth: int, prefix: str) -> None:
    if depth > max_depth:
        return
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return
    dirs_first = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file()]
    for i, entry in enumerate(dirs_first + files):
        is_last = i == len(dirs_first) + len(files) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir() and depth < max_depth:
            extension = "    " if is_last else "│   "
            _walk(entry, lines, depth + 1, max_depth, prefix + extension)


def tool_dependency_scan() -> str:
    """Scan requirements.txt / pyproject.toml / package.json for missing dependencies."""
    ws = _workspace_root()
    results = []
    for fname in ["requirements.txt", "pyproject.toml", "package.json"]:
        fp = ws / fname
        if not fp.exists():
            continue
        results.append(f"--- {fname} ---")
        if fname == "requirements.txt":
            for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
                try:
                    __import__(pkg.replace("-", "_"))
                except ImportError:
                    results.append(f"  MISSING: {line}")
                else:
                    results.append(f"  OK: {line}")
        elif fname == "pyproject.toml":
            content = fp.read_text(encoding="utf-8", errors="replace")
            results.append(_clip(content, 3000))
        elif fname == "package.json":
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for name, ver in deps.items():
                    node_mod = ws / "node_modules" / name
                    results.append(f"  {'OK' if node_mod.exists() else 'MISSING'}: {name}@{ver}")
            except Exception as e:
                results.append(f"  Error parsing: {e}")
    return "\n".join(results) if results else "No dependency files found"


def tool_code_lint(file_path: str) -> str:
    """Run linting on a Python file using ruff or flake8."""
    target = (_workspace_root() / file_path).resolve()
    if not target.exists():
        return f"Error: file not found: {file_path}"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(target)],
            capture_output=True, text=True, timeout=30, cwd=str(_workspace_root()),
        )
        if proc.returncode == 0:
            return f"No issues found in {file_path}"
        return _clip(proc.stdout + proc.stderr, 5000)
    except FileNotFoundError:
        return "ruff not installed. Run: pip install ruff"
    except Exception as e:
        return f"Error: {e}"


def tool_code_format(file_path: str, check_only: bool = False) -> str:
    """Format a Python file with ruff format."""
    target = (_workspace_root() / file_path).resolve()
    if not target.exists():
        return f"Error: file not found: {file_path}"
    try:
        cmd = [sys.executable, "-m", "ruff", "format"]
        if check_only:
            cmd.append("--check")
        cmd.append(str(target))
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, cwd=str(_workspace_root()),
        )
        if proc.returncode == 0:
            if check_only:
                return f"ruff format check: {target.name} is already formatted"
            return f"ruff format: {target.name} formatted successfully\n{_clip(proc.stdout, 2000)}"
        return f"ruff format result:\n{_clip(proc.stdout + proc.stderr, 5000)}"
    except Exception as e:
        return f"Error: {e}"
