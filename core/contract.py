"""Task Contract system for concurrent engineering.

The contract defines:
  - Overall goal
  - Global constraints (files not to touch)
  - Per-agent responsibilities, allowed paths, forbidden paths
  - Integration points (files only integration_agent can touch)
  - Test commands

Generated as generated/contracts/{run_id}_contract.md
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from config import CONTRACTS_DIR


def create_contract(
    run_id: str,
    task: str,
    team: dict[str, Any],
    stage_roles: list[list[str]] | None = None,
) -> Path:
    """Generate a task contract for a parallel run.
    Returns the path to the contract file.
    """
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Galaxy 并发任务契约",
        f"",
        f"## 基本信息",
        f"- run_id: {run_id}",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"",
        f"## 总目标",
        f"{task}",
        f"",
        f"## 全局约束",
    ]

    # Identify forbidden files across all agents
    global_forbidden = {"app.py", "config.py"}  # always protect these
    lines.append("- 以下文件任何 Developer Agent 不得修改：")
    for f in sorted(global_forbidden):
        lines.append(f"  - `{f}`")

    lines.extend([
        "",
        "## Agent 分工",
    ])

    roles = team.get("roles", [])
    for role in roles:
        name = role.get("name", "unknown")
        prompt = role.get("prompt", "")
        skills = role.get("skills", [])

        lines.append(f"### {name}")
        lines.append(f"- 职责: {prompt[:200]}")
        if skills:
            lines.append(f"- 可用工具: {', '.join(skills)}")
        lines.append(f"- 禁止修改: `app.py`, `config.py`（仅 integration_agent 可改）")
        lines.append(f"- 修改 Python 文件后必须运行 `code_compile` 自测")
        lines.append(f"- 必须输出: structured JSON（status, files_changed, tests, risks, handoff_summary）")

    lines.extend([
        "",
        "## 集成点",
        "- 只有 `integration_agent` 可以修改：`app.py`, `config.py`",
        "- 只有 `integration_agent` 可以注册新工具/import",
        "- 各 Developer 的输出由 `integration_agent` 统一接入",
        "",
        "## 测试命令",
        "- 每个 Developer 修改代码后运行: `code_compile <modified_file>`",
        "- Tester 最终运行: `run_tests pytest`",
    ])

    path = CONTRACTS_DIR / f"{run_id}_contract.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def get_contract_path(run_id: str) -> Path:
    return CONTRACTS_DIR / f"{run_id}_contract.md"


def contract_exists(run_id: str) -> bool:
    return get_contract_path(run_id).exists()
