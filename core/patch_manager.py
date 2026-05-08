"""Patch manager — save/load agent diffs for concurrent engineering."""

from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import datetime

from config import DIFFS_DIR


def save_agent_diff(run_id: str, agent_name: str, workspace_root: Path | None = None) -> Path | None:
    """Save the current git diff as a patch for this agent.
    Returns the diff file path, or None if no changes or not a git repo.
    """
    DIFFS_DIR.mkdir(parents=True, exist_ok=True)
    root = workspace_root or DIFFS_DIR.parent

    try:
        proc = subprocess.run(
            ["git", "diff"],
            cwd=str(root),
            text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=15,
        )
        if proc.returncode != 0:
            return None

        diff_text = proc.stdout.strip()
        if not diff_text:
            return None  # no changes

        safe_name = agent_name.replace(" ", "_").replace("/", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = DIFFS_DIR / f"{run_id}_{safe_name}_{ts}.diff"

        header = f"# Agent: {agent_name}\n# Run: {run_id}\n# Time: {ts}\n\n"
        path.write_text(header + diff_text, encoding="utf-8")
        return path
    except Exception:
        return None


def list_agent_diffs(run_id: str) -> list[Path]:
    """List all diff files for a run."""
    DIFFS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DIFFS_DIR.glob(f"{run_id}_*.diff"))


def read_agent_diff(path: str | Path) -> str | None:
    """Read a diff file. Returns content or None."""
    p = Path(path) if isinstance(path, str) else path
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")
