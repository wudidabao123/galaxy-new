"""Contract tools — task contract read/write for concurrent engineering."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import CONTRACTS_DIR


def tool_contract_write(run_id: str, content: str) -> str:
    """Write a task contract for concurrent agent work.
    PM/planner should call this before developers start.
    Content should be Markdown with: goal, global constraints, per-agent responsibilities,
    allowed/forbidden paths, integration points, test commands.
    Args: run_id (from the current run), content (Markdown contract body).
    """
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONTRACTS_DIR / f"{run_id}_contract.md"
    header = f"# Task Contract — {run_id}\nGenerated: {datetime.now().isoformat(timespec='seconds')}\n\n"
    path.write_text(header + content, encoding="utf-8")
    return f"Contract written: {path} ({len(content)} chars)"


def tool_contract_read(run_id: str) -> str:
    """Read the task contract for the current run.
    All developer agents should call this before starting work.
    Args: run_id (from the current run).
    """
    path = CONTRACTS_DIR / f"{run_id}_contract.md"
    if not path.exists():
        return f"Error: contract not found at {path}. Ask PM to create one first."
    return path.read_text(encoding="utf-8", errors="replace")


def tool_contract_summary(run_id: str) -> str:
    """Return a brief summary of the contract: agent names and their responsibilities.
    Use this to quickly check who should do what without reading the full contract."""
    path = CONTRACTS_DIR / f"{run_id}_contract.md"
    if not path.exists():
        return f"No contract found for run {run_id}."

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    agents = []
    current_agent = None
    for line in lines:
        line = line.strip()
        if line.startswith("### ") and not line.startswith("### Agent"):
            agents.append({"name": line[4:], "responsibilities": []})
            current_agent = agents[-1]
        elif line.startswith("- ") and current_agent is not None:
            current_agent["responsibilities"].append(line[2:])

    if not agents:
        return f"Contract exists ({len(text)} chars) but could not parse agent sections."

    summary = ["# Contract Summary"]
    for a in agents:
        summary.append(f"\n## {a['name']}")
        for r in a["responsibilities"]:
            summary.append(f"- {r}")
    return "\n".join(summary)
