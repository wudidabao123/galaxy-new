"""Permission system for Galaxy New.

Simplified model:
  - Tool assignment = permission. Whatever tools a role has checked, it can use.
  - All file tools are sandboxed to the workspace root.
  - Dangerous shell commands (rm -rf, format, etc.) are always blocked.
  - Optionally, chat-level PermissionMode (ask/guard/auto) controls confirmation flow.
  - FILE_WRITE_LOCKS is maintained by core.conflict (single source of truth).
"""

from __future__ import annotations

import re as _re

from core.enums import PermissionMode
from config import DANGEROUS_SHELL_PATTERNS

# Re-export from conflict.py (single source of truth for FILE_WRITE_LOCKS)
from core.conflict import check_file_write_conflict, reset_file_write_locks, FILE_WRITE_LOCKS  # noqa: F401


def is_dangerous_shell_command(command: str) -> tuple[bool, str]:
    """Always-blocked dangerous shell patterns.

    Matches common variants including long-form flags (rm --recursive --force),
    Windows commands, and PowerShell aliases. Whitespace is normalized to foil
    multi-space / tab bypass attempts.
    """
    lowered = (command or "").lower()
    # Normalize whitespace to catch multi-space / tab bypass attempts
    normalized = " ".join(lowered.split())
    for pattern, label in DANGEROUS_SHELL_PATTERNS:
        if _re.search(pattern, normalized):
            return True, f"Dangerous shell command blocked: {label}"
    return False, ""


def should_ask_permission(mode: PermissionMode) -> bool:
    """Whether the current permission mode requires user confirmation."""
    return mode == PermissionMode.ASK
