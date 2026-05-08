"""Handoff system — stage-to-stage handoff documents for concurrent engineering."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from config import HANDOFFS_DIR


def generate_handoff(
    run_id: str,
    stage_name: str,
    results: dict[str, dict[str, Any]],
) -> Path:
    """Generate a stage handoff document from parallel agent results.
    Returns the path to the handoff file.
    """
    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = stage_name.replace(" ", "_").replace("/", "_")

    lines = [
        f"# 阶段交接: {stage_name}",
        f"",
        f"- run_id: {run_id}",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"",
        f"## Agent 结果",
    ]

    files_changed_all: set[str] = set()
    risks_all: list[str] = []

    for agent_name, payload in results.items():
        structured = payload.get("structured")
        guard = payload.get("guard")

        # Mark failed/blocked agents clearly so next stage knows to skip them
        status_raw = getattr(structured, "status", None) if structured else None
        status_str = status_raw.value if hasattr(status_raw, "value") else str(status_raw or "unknown")
        status_label = ""
        if status_str in ("failed", "blocked"):
            status_label = f" [WARNING {status_str.upper()}]"
        elif status_str == "needs_retry":
            status_label = " [WARNING NEEDS RETRY]"

        lines.append(f"### {agent_name}{status_label}")

        if structured:
            status_raw = getattr(structured, "status", "unknown")
            status = status_raw.value if hasattr(status_raw, "value") else str(status_raw)
            summary = getattr(structured, "summary", "")
            fc = getattr(structured, "files_changed", [])
            tests = getattr(structured, "tests", [])
            risks = getattr(structured, "risks", [])
            handoff = getattr(structured, "handoff_summary", "")

            lines.append(f"- 状态: {status}")
            if summary:
                lines.append(f"- 摘要: {summary}")
            if fc:
                lines.append(f"- 修改文件: {', '.join(fc)}")
                files_changed_all.update(fc)
            if tests:
                for t in tests:
                    tr = getattr(t, "result", "unknown")
                    tc = getattr(t, "command", "")
                    lines.append(f"  - 测试: `{tc}` → {tr}")
            if risks:
                lines.append(f"- 风险: {'; '.join(risks)}")
                risks_all.extend(risks)
            if handoff:
                lines.append(f"- 交接: {handoff}")

        if guard:
            gd = getattr(guard, "decision", "unknown")
            gs = getattr(guard, "score", 0)
            lines.append(f"- Guard: {gd} (分数 {gs})")

    lines.extend([
        "",
        "## 汇总文件变更",
    ])
    for f in sorted(files_changed_all):
        lines.append(f"- `{f}`")
    if not files_changed_all:
        lines.append("- (无文件变更)")

    if risks_all:
        lines.append("")
        lines.append("## 汇总风险")
        for r in sorted(set(risks_all)):
            lines.append(f"- {r}")

    lines.extend([
        "",
        "## 下一阶段注意",
        "- 如果有文件变更，integration_agent 需要统一接入 app.py",
        "- Tester 需要根据变更文件运行对应测试",
        "- Reviewer 需要读取 diff 和 Guard 结果",
    ])

    path = HANDOFFS_DIR / f"{run_id}_{safe_name}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
