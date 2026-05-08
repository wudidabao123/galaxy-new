"""Handoff tools — stage-to-stage handoff documents for concurrent engineering."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import HANDOFFS_DIR


def tool_handoff_write(run_id: str, stage_name: str, content: str) -> str:
    """Write a stage handoff document. Called at the end of each parallel stage.
    Content should include: agent results, files changed, test results, risks, next-stage notes.
    Args: run_id, stage_name (e.g. '1. task contract'), content (Markdown).
    """
    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = stage_name.replace(" ", "_").replace("/", "_")
    path = HANDOFFS_DIR / f"{run_id}_{safe_name}.md"
    header = f"# Stage Handoff: {stage_name}\nRun: {run_id}\nGenerated: {datetime.now().isoformat(timespec='seconds')}\n\n"
    path.write_text(header + content, encoding="utf-8")
    return f"Handoff written: {path} ({len(content)} chars)"


def tool_handoff_read(run_id: str, stage_name: str = "") -> str:
    """Read the most recent handoff document for a run.
    If stage_name is empty, reads the latest stage handoff.
    Args: run_id, stage_name (optional, e.g. '2. module_dev').
    """
    if stage_name:
        safe_name = stage_name.replace(" ", "_").replace("/", "_")
        path = HANDOFFS_DIR / f"{run_id}_{safe_name}.md"
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return f"Handoff not found: {path}"

    # Find latest handoff for this run
    files = sorted(HANDOFFS_DIR.glob(f"{run_id}_*.md"), reverse=True)
    if not files:
        return f"No handoffs found for run {run_id}."
    return files[0].read_text(encoding="utf-8", errors="replace")
