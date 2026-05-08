"""Context management — history compaction, soul MD injection, contract/handoff injection."""

from __future__ import annotations

import re as _re
from typing import Any

from config import CONTEXT_COMPACT_RATIO, DEFAULT_CONTEXT_LENGTH


def _clip_output(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


def _is_tool_event_chunk(chunk: str) -> bool:
    stripped = (chunk or "").strip()
    return stripped.startswith("[TOOL]")


def _split_tool_events(text: str) -> tuple[str, list[str]]:
    body: list[str] = []
    events: list[str] = []
    for line in (text or "").splitlines():
        if _is_tool_event_chunk(line):
            events.append(line.strip())
        else:
            body.append(line)
    return "\n".join(body).strip(), events


def _history_text_size(history: list[dict]) -> int:
    return sum(len(str(msg.get("content", ""))) for msg in history)


def _context_budget_chars(context_length: int) -> int:
    return max(12000, int(context_length * CONTEXT_COMPACT_RATIO * 3.2))


def _extract_artifact_lines(text: str, limit: int = 30) -> list[str]:
    interesting: list[str] = []
    path_re = _re.compile(
        r"[\w./\\-]+\.(?:py|js|ts|tsx|html|css|json|md|txt|yml|yaml|toml|csv|png|jpg|jpeg|webp)",
        _re.I,
    )
    for line in (text or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        lower = clean.lower()
        if any(key in lower for key in [
            "wrote ", "created ", "modified ", "test", "error",
            "failed", "passed", "path=", "文件", "测试", "失败", "通过",
        ]):
            interesting.append(clean[:260])
        else:
            match = path_re.search(clean)
            if match:
                interesting.append(clean[:260])
        if len(interesting) >= limit:
            break
    return interesting


def compact_history(history: list[dict], max_chars: int = 1800) -> list[dict]:
    """Compress long messages in history for agent context."""
    compacted: list[dict] = []
    for msg in history:
        content, events = _split_tool_events(str(msg.get("content", "")))
        if len(content) > max_chars:
            artifact_lines = _extract_artifact_lines(content)
            parts = [
                _clip_output(content, max_chars),
                "",
                "【压缩说明】原消息较长，已保留开头和关键产物线索。",
            ]
            if artifact_lines:
                parts.append("【文件/命令线索】")
                parts.extend(f"- {line}" for line in artifact_lines[:20])
            if events:
                parts.append(f"【工具事件】{len(events)} 条，已从模型上下文中折叠。")
            content = "\n".join(parts)
        copied = dict(msg)
        copied["content"] = content
        compacted.append(copied)
    return compacted


def history_for_model_context(
    history: list[dict],
    context_length: int = DEFAULT_CONTEXT_LENGTH,
) -> list[dict]:
    """Return history fit for the model's context window.
    Compacts old messages, keeps recent 6 intact."""
    budget = _context_budget_chars(context_length)
    if _history_text_size(history) <= budget:
        return history

    recent_limit = max(2500, min(6000, budget // 3))
    keep_recent = []
    for msg in history[-6:]:
        if len(str(msg.get("content", ""))) > recent_limit:
            keep_recent.extend(compact_history([msg], max_chars=2500))
        else:
            keep_recent.append(msg)

    older = history[:-6]
    compacted_older = compact_history(older, max_chars=900)

    summary_lines = [
        "## Galaxy 自动上下文压缩",
        f"触发原因: 历史上下文超过当前模型预算。",
        "已压缩旧消息，保留目标、文件线索、测试结果；最近 6 条消息保持完整。",
    ]
    for msg in compacted_older[-20:]:
        src = msg.get("source", "?")
        summary_lines.append(f"\n### {src}")
        summary_lines.append(_clip_output(str(msg.get("content", "")), 1200))

    return [{
        "source": "Galaxy Context",
        "content": "\n".join(summary_lines),
        "avatar": "🧠",
    }] + keep_recent
# NOTE: Old soul MD file system removed. Use data/soul_store.py for soul agents.
