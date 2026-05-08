"""File write conflict lock — prevent multiple agents from writing the same file in one run."""
from __future__ import annotations

from pathlib import Path

# {run_id:path → agent_name}
FILE_WRITE_LOCKS: dict[str, str] = {}


def check_file_write_conflict(run_id: str, agent_name: str, path: str) -> tuple[bool, str]:
    """Check if a file is already claimed by another agent in this run.
    Returns (allowed, reason).

    - Same agent can write the same file multiple times.
    - Different agents cannot write the same file.
    """
    if not run_id or not path:
        return True, ""

    normalized = str(Path(path)).replace("\\", "/").lower()
    key = f"{run_id}:{normalized}"
    owner = FILE_WRITE_LOCKS.get(key)

    if owner and owner != agent_name:
        return False, f"Write conflict: {path} is already owned by {owner} in run {run_id}"

    FILE_WRITE_LOCKS[key] = agent_name
    return True, ""


def reset_file_write_locks(run_id: str | None = None) -> None:
    """Clear locks for a specific run, or all if run_id is None."""
    if not run_id:
        FILE_WRITE_LOCKS.clear()
        return
    prefix = f"{run_id}:"
    for key in list(FILE_WRITE_LOCKS):
        if key.startswith(prefix):
            FILE_WRITE_LOCKS.pop(key, None)
