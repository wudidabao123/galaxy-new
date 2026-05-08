"""Cross-platform shell execution tools.

Auto-detects the best available shell (bash > powershell > cmd).
Dangerous commands (rm -rf, format, shutdown, etc.) are always blocked.
All commands run in the workspace root directory.
"""

from __future__ import annotations

import re as _re
import subprocess
import sys
from pathlib import Path

from config import DANGEROUS_SHELL_PATTERNS


def _clip_output(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


def detect_shell() -> str:
    """Return the best available shell for the current platform."""
    if sys.platform == "win32":
        # Check for Git Bash first
        try:
            r = subprocess.run(["bash", "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return "bash"
        except Exception:
            pass
        # Check for PowerShell
        try:
            r = subprocess.run(["powershell", "-Command", "echo test"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                return "powershell"
        except Exception:
            pass
        return "cmd"
    else:
        return "bash"


def _build_shell_command(command: str, shell: str) -> list[str]:
    """Build the subprocess invocation list for the given shell."""
    if shell == "bash":
        return ["bash", "-c", command]
    elif shell == "powershell":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
    else:  # cmd
        return ["cmd", "/c", command]


def is_dangerous_command(command: str) -> tuple[bool, str]:
    """Check if a shell command is dangerous. Returns (is_dangerous, reason)."""
    lowered = (command or "").lower()
    for pattern, label in DANGEROUS_SHELL_PATTERNS:
        if _re.search(pattern, lowered):
            return True, f"Dangerous shell command blocked: {label}"
    return False, ""


def tool_terminal(command: str, timeout_seconds: int = 60, shell: str = "") -> str:
    """Execute a shell command in the workspace root. Auto-detects bash/powershell/cmd.
    Returns exit_code, stdout, stderr. Max timeout 120s.
    """
    from skills.builtin.file_ops import _get_workspace_root

    try:
        timeout = max(1, min(int(timeout_seconds), 120))
    except Exception:
        timeout = 60

    dangerous, reason = is_dangerous_command(command)
    if dangerous:
        return f"Error: {reason}"

    _shell = shell or detect_shell()
    args = _build_shell_command(command, _shell)
    workspace = _get_workspace_root()

    try:
        proc = subprocess.run(
            args,
            cwd=str(workspace),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        output = [f"shell={_shell}", f"exit_code={proc.returncode}"]
        if proc.stdout:
            output.append("[stdout]\n" + proc.stdout)
        if proc.stderr:
            output.append("[stderr]\n" + proc.stderr)
        return _clip_output("\n".join(output))
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def tool_run_script(script_path: str, timeout_seconds: int = 120) -> str:
    """Run a script (.py/.sh/.ps1) from the workspace. Auto-detects interpreter."""
    from skills.builtin.file_ops import _get_workspace_root
    import os

    workspace = _get_workspace_root()
    full_path = workspace / script_path
    if not full_path.exists():
        return f"Error: script not found: {script_path}"

    try:
        timeout = max(1, min(int(timeout_seconds), 300))
    except Exception:
        timeout = 120

    ext = full_path.suffix.lower()
    if ext == ".py":
        args = [sys.executable, str(full_path)]
        shell_name = "python"
    elif ext == ".ps1":
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(full_path)]
        shell_name = "powershell"
    elif ext == ".sh":
        args = ["bash", str(full_path)]
        shell_name = "bash"
    else:
        # Try shell execution
        return tool_terminal(f'"{full_path}"', timeout_seconds=timeout_seconds)

    try:
        proc = subprocess.run(
            args,
            cwd=str(workspace),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        output = [f"interpreter={shell_name}", f"exit_code={proc.returncode}"]
        if proc.stdout:
            output.append("[stdout]\n" + proc.stdout)
        if proc.stderr:
            output.append("[stderr]\n" + proc.stderr)
        return _clip_output("\n".join(output))
    except subprocess.TimeoutExpired:
        return f"Error: script timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
