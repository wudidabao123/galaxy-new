"""Patch tools — preview, apply, and reject unified diffs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import datetime


def _get_workspace_root() -> Path:
    from skills.builtin.file_ops import _get_workspace_root as _r
    return _r()


def tool_patch_preview(patch_content: str) -> str:
    """Preview what a unified diff patch would change. Pass the full patch text.
    Returns file list and change summary without applying."""
    lines = (patch_content or "").splitlines()
    files: dict[str, dict] = {}

    current_file = ""
    for line in lines:
        if line.startswith("--- ") or line.startswith("+++ "):
            pass
        elif line.startswith("diff --git "):
            parts = line.split(" ")
            if len(parts) >= 4:
                current_file = parts[3][2:]  # b/path
                files[current_file] = {"added": 0, "removed": 0}
        elif line.startswith("+") and not line.startswith("+++"):
            if current_file:
                files[current_file]["added"] += 1
        elif line.startswith("-") and not line.startswith("---"):
            if current_file:
                files[current_file]["removed"] += 1

    if not files:
        return "No changes detected in patch."

    result = ["# Patch Preview"]
    for fname, counts in files.items():
        result.append(f"- {fname}: +{counts['added']}/-{counts['removed']}")
    result.append(f"\nTotal files: {len(files)}")
    return "\n".join(result)


def tool_patch_apply(patch_content: str, dry_run: bool = False) -> str:
    """Apply a unified diff patch to the workspace. Set dry_run=true to check without modifying.
    The patch must use paths relative to the workspace root."""
    root = _get_workspace_root()

    if dry_run:
        try:
            proc = subprocess.run(
                ["git", "apply", "--check", "--verbose"],
                input=patch_content,
                cwd=str(root),
                text=True, encoding="utf-8", errors="replace",
                capture_output=True, timeout=15,
            )
            if proc.returncode == 0:
                return "Dry run passed — patch can be applied cleanly.\n" + (proc.stdout or "")
            else:
                return f"Dry run FAILED:\n{proc.stderr or proc.stdout or 'unknown error'}"
        except Exception as e:
            return f"Error: {e}"

    try:
        proc = subprocess.run(
            ["git", "apply", "--verbose"],
            input=patch_content,
            cwd=str(root),
            text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=15,
        )
        if proc.returncode == 0:
            return "Patch applied successfully.\n" + (proc.stdout or "")
        else:
            return f"Patch apply FAILED:\n{proc.stderr or proc.stdout or 'unknown error'}"
    except Exception as e:
        return f"Error: {e}"


def tool_patch_reject(patch_content: str, reason: str = "") -> str:
    """Save a rejected patch to generated/patches/ for later review. Does NOT apply it."""
    from config import PATCHES_DIR

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    patch_file = PATCHES_DIR / f"rejected_{ts}.diff"
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)

    content = f"# Rejected: {reason or 'no reason given'}\n# {ts}\n\n{patch_content}"
    patch_file.write_text(content, encoding="utf-8")
    return f"Patch rejected and saved to {patch_file}. Reason: {reason or '(none)'}"
