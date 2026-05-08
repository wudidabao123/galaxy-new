"""Runs tab — view run history, stage logs, tool logs, reports."""

from __future__ import annotations

import streamlit as st

from data.run_store import list_run_states, load_run_state, get_stage_logs, get_tool_logs
from data.database import get_db


def _clip_output(text: str, limit: int = 100) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def render_runs_tab() -> None:
    st.header("📊 运行记录")
    st.caption("查看每次任务的 RunState、阶段日志、Guard 结果、工具审计。")

    runs = list_run_states(limit=100)
    if not runs:
        st.info("还没有运行记录。发起一次 Agent 任务后会在这里显示。")
        return

    st.dataframe(
        [{
            "run_id": r["run_id"],
            "task": _clip_output(r.get("task", "")),
            "team": r.get("team_id", ""),
            "mode": r.get("mode", ""),
            "updated": r.get("updated_at", "")[:19],
        } for r in runs],
        use_container_width=True,
    )

    selected = st.selectbox(
        "选择 run",
        [r["run_id"] for r in runs],
        format_func=lambda rid: next(
            (f"{rid} · {r['updated_at'][:19]} · {r['task'][:60]}" for r in runs if r["run_id"] == rid),
            rid,
        ),
    )

    st.subheader("Stage Logs")
    stage_logs = get_stage_logs(selected)
    if stage_logs:
        st.dataframe([{
            "stage": sl.get("stage"), "agent": sl.get("agent"),
            "retry": sl.get("retry_count"),
            "guard_decision": sl.get("guard", {}).get("decision", ""),
        } for sl in stage_logs], use_container_width=True)
    else:
        st.caption("暂无阶段日志")

    st.subheader("Tool Logs")
    tool_logs = get_tool_logs(selected, limit=200)
    if tool_logs:
        st.dataframe([{
            "agent": tl.get("agent_name"), "tool": tl.get("tool_name"),
            "status": tl.get("result_status"), "duration_ms": tl.get("duration_ms"),
            "target": tl.get("target_path", "")[:60],
        } for tl in tool_logs], use_container_width=True)
    else:
        st.caption("暂无工具审计日志")
