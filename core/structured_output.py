"""Structured output parsing — extract AgentStageResult from agent text."""

from __future__ import annotations

import json
import re as _re
from dataclasses import asdict
from typing import Any

from core.enums import AgentStatus, TestStatus
from core.schemas import AgentStageResult, CommandResult


def extract_json_object(text: str) -> dict | None:
    """Extract the first valid JSON object from text or markdown fences."""
    raw = (text or "").strip()
    if not raw:
        return None

    fence = _re.search(r"```(?:json)?\s*(\{[^`]*?\})\s*```", raw, _re.I | _re.S)
    candidates: list[str] = []
    if fence:
        candidates.append(fence.group(1))
    if raw.startswith("{") and raw.endswith("}"):
        candidates.append(raw)

    starts = [m.start() for m in _re.finditer(r"\{", raw)]
    for start in starts:
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(raw)):
            ch = raw[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(raw[start:idx + 1])
                    break

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


def _command_from_any(value: Any) -> CommandResult:
    if isinstance(value, CommandResult):
        return value
    if isinstance(value, dict):
        return CommandResult(
            command=str(value.get("command", "")),
            result=TestStatus(value.get("result", "unknown")) if value.get("result") in {
                "passed", "failed", "not_run", "unknown"
            } else TestStatus.UNKNOWN,
            evidence=str(value.get("evidence", "")),
            exit_code=value.get("exit_code") if isinstance(value.get("exit_code"), int) else None,
        )
    return CommandResult(command=str(value), result=TestStatus.UNKNOWN)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_agent_stage_result(text: str, role: str) -> AgentStageResult:
    """Parse an AgentStageResult from JSON, falling back to safe text result."""
    data = extract_json_object(text)
    if not data:
        return AgentStageResult(
            role=role,
            status=AgentStatus.DONE,
            summary=(text or "")[:1500],
            risks=["Agent output was not valid structured JSON"],
            raw_output=text or "",
            parsed_json_ok=False,
        )

    status_str = data.get("status", "done")
    try:
        status = AgentStatus(status_str)
    except ValueError:
        status = AgentStatus.DONE

    return AgentStageResult(
        role=str(data.get("role") or role),
        status=status,
        task_scope=str(data.get("task_scope", "")),
        summary=str(data.get("summary", "")),
        files_read=_string_list(data.get("files_read", [])),
        files_changed=_string_list(data.get("files_changed", [])),
        commands_run=[_command_from_any(item) for item in data.get("commands_run", []) or []],
        tests=[_command_from_any(item) for item in data.get("tests", []) or []],
        risks=_string_list(data.get("risks", [])),
        handoff_summary=str(data.get("handoff_summary", "")),
        raw_output=text or "",
        parsed_json_ok=True,
    )


def agent_result_to_markdown(result: AgentStageResult) -> str:
    """Convert structured stage result to compact markdown."""
    lines = [
        f"### {result.role}",
        f"- 状态: {result.status.value}",
        f"- 范围: {result.task_scope or '(未说明)'}",
        f"- 摘要: {result.summary or '(无摘要)'}",
    ]
    if result.files_read:
        lines.append("- 读取文件: " + ", ".join(result.files_read))
    if result.files_changed:
        lines.append("- 修改文件: " + ", ".join(result.files_changed))
    if result.tests:
        lines.append("- 测试:")
        for test in result.tests:
            lines.append(f"  - `{test.command}`: {test.result.value} {test.evidence}".rstrip())
    if result.risks:
        lines.append("- 风险:")
        lines.extend(f"  - {risk}" for risk in result.risks)
    if result.handoff_summary:
        lines.append("- 交接摘要: " + result.handoff_summary)
    return "\n".join(lines)
