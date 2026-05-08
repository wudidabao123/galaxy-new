"""Chat tab — streaming multi-agent conversation with rich content (Mermaid, images, tables)."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import streamlit as st
from config import (DATA_DIR, UPLOADS_DIR, GENERATED_DIR, RUNS_DIR,
                    CHAT_ATTACHMENT_TYPES, AGENT_COLORS, AGENT_AVATARS)
from core.enums import ChatStyle, PermissionMode
from core.orchestrator import (run_round_robin_stream, run_parallel_stages,
                               run_parallel_stages_stream,
                               _sync_agent_stream, _build_task_payload,
                               _is_tool_event_chunk, _split_tool_events)
from core.agent_factory import create_agents_for_team
from core.context import history_for_model_context
from core.patch_manager import save_agent_diff
from core.guard import enhanced_guard_check
from core.structured_output import parse_agent_stage_result, agent_result_to_markdown
from data.team_store import list_teams, get_team
from data.session_store import list_sessions, get_session, save_session
from data.run_store import save_run_state
from data.model_store import record_model_usage
from ui.components import (render_user_bubble, render_agent_bubble, render_tool_events,
                           render_message_content, render_attachments, render_permission_selector,
                           render_guard_result, render_agent_flow, avatar_for_chat,
                           render_streaming_bubble)
from skills.registry import get_registry

_TIMEZONE = timezone(timedelta(hours=8))
HIDDEN_TEAM_CATEGORIES = {"未分类", "Uncategorized", ""}

# ── Helpers ───────────────────────────────────────────────

def _clip_output(text: str, limit: int = 12000) -> str:
    """Re-export from core.context for local use."""
    from core.context import _clip_output as _co
    return _co(text, limit)

def _ensure_runtime_dirs() -> None:
    for d in [UPLOADS_DIR, GENERATED_DIR, RUNS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def _split_chat_input_value(value: Any) -> tuple[str, list]:
    if not value: return "", []
    if isinstance(value, str): return value, []
    if isinstance(value, dict):
        text = value.get("text") or value.get("message") or ""
        files = value.get("files") or []
        return str(text), list(files)
    text = getattr(value, "text", None)
    if text is None: text = getattr(value, "message", "")
    files = getattr(value, "files", []) or []
    return str(text or ""), list(files)

def _save_uploaded_files(uploaded_files: list) -> list[dict]:
    _ensure_runtime_dirs()
    attachments = []
    for uploaded in uploaded_files or []:
        raw = uploaded.getvalue()
        safe_name = Path(uploaded.name).name.replace(" ", "_")
        save_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}_{safe_name}"
        path = UPLOADS_DIR / save_name
        path.write_bytes(raw)
        mime = uploaded.type or ""
        is_image = mime.startswith("image/") or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        attachments.append({"name": uploaded.name, "path": str(path.relative_to(DATA_DIR)).replace("\\", "/"),
                            "mime": mime, "size": len(raw), "kind": "image" if is_image else "file"})
    return attachments

def _init_chat_state() -> None:
    for key, default in [
        ("chat_history", []), ("user_name", "Me"), ("user_identity", ""),
        ("_chat_team_id", ""), ("_pending_agents", False), ("save_chat_history", False),
        ("_chat_session_id", ""), ("_upload_key_id", 0), ("chat_permission_mode", "auto"),
        ("_auto_search", False),
    ]:
        if key not in st.session_state: st.session_state[key] = default

def _get_workspace_root() -> Path:
    try:
        from data.database import get_db
        conn = get_db()
        row = conn.execute("SELECT value FROM project_state WHERE key = 'root'").fetchone()
        if row and row[0]:
            p = Path(row[0]).expanduser().resolve()
            if p.exists() and p.is_dir(): return p
    except Exception: pass
    return DATA_DIR.resolve()

# ── Auto context (FAST — datetime only, no blocking web search) ──

def _needs_current_datetime(prompt: str) -> bool:
    text = (prompt or "").lower()
    keywords = {"today", "now", "date", "time", "今天", "现在", "日期", "时间"}
    return any(k in text for k in keywords)

def _get_current_datetime() -> str:
    import json as _json
    now = datetime.now(_TIMEZONE)
    weekday = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]
    return _json.dumps({"timezone": "Asia/Shanghai", "date": now.strftime("%Y-%m-%d"),
                        "time": now.strftime("%H:%M:%S"), "weekday": weekday,
                        "zh": now.strftime("%Y-%m-%d %H:%M:%S")},
                       ensure_ascii=False, indent=2)

def _build_auto_context(prompt: str, role_skills: list[list[str]],
                        auto_search: bool = False) -> tuple[str, list[str]]:
    """Inject current datetime (instant). Web search only with auto_search ON."""
    events, blocks = [], []
    all_skills = set()
    for skills in role_skills: all_skills.update(skills)

    if "current_datetime" in all_skills and _needs_current_datetime(prompt):
        events.append("[TOOL] auto: current_datetime")
        now_result = _get_current_datetime()
        events.append("[TOOL] current_datetime OK")
        blocks.append("## Current Date/Time\n```json\n" + now_result + "\n```")

    if auto_search and "web_search" in all_skills:
        text = (prompt or "").lower()
        search_triggers = {"latest", "news", "search", "market", "stock", "price",
                          "tourism", "travel", "economy", "最新", "新闻", "搜索", "市场",
                          "旅游", "经济", "研究", "论文", "数据", "资料"}
        if any(t in text for t in search_triggers):
            events.append("[TOOL] auto: web_search")
            date_hint = datetime.now(_TIMEZONE).strftime("%Y-%m-%d")
            from skills.builtin.web import tool_web_search
            sr = tool_web_search(f"{prompt} {date_hint}", max_results=3, fetch_pages=True, max_chars_per_page=800)
            events.append(f"[TOOL] web_search {'OK' if not sr.startswith('Error:') else 'ERROR'}")
            blocks.append("## Web Search Results\n" + _clip_output(sr, 6000))

    if not blocks: return "", []
    content = "\n".join([
        "Galaxy auto-context (before agents respond).",
        "Agents MUST use these results; do NOT claim lack of web access or date.",
        *blocks,
    ])
    return content, events

# ── Main Chat Tab ─────────────────────────────────────────

def render_chat_tab() -> None:
    _init_chat_state()
    _ensure_runtime_dirs()
    teams = list_teams()
    if not teams:
        st.warning("Please create a team in the Teams tab first")
        return

    user_name = st.session_state.user_name or "Me"

    # Compact team/session settings
    cat_map = _get_all_categories()
    by_cat: dict[str, list] = {}
    for t in teams:
        cat = t.get("category", "Uncategorized")
        if cat in HIDDEN_TEAM_CATEGORIES:
            continue
        by_cat.setdefault(cat, []).append(t)
    cat_names = sorted(by_cat.keys())

    if not cat_names:
        st.warning("Please create a team in the Teams tab first")
        return

    selected_team_id = st.session_state.get("_chat_team_id", "")
    available_ids = [t["id"] for group in by_cat.values() for t in group]
    if selected_team_id not in available_ids:
        selected_team_id = available_ids[0]
        st.session_state["_chat_team_id"] = selected_team_id

    with st.expander("团队与会话设置", expanded=False):
        st.caption("Select Team")
        c_cat, c_team = st.columns([1, 2])
        with c_cat:
            cur_cat = st.session_state.get("_chat_cat", cat_names[0] if cat_names else "")
            if cur_cat not in cat_names:
                cur_cat = next((cat for cat, items in by_cat.items() if selected_team_id in [t["id"] for t in items]), cat_names[0])
            picked_cat = st.selectbox("Category", cat_names,
                index=cat_names.index(cur_cat) if cur_cat in cat_names else 0,
                format_func=lambda c: f"{cat_map.get(c, '')} {c}", key="chat_cat_sel")
            st.session_state["_chat_cat"] = picked_cat
        with c_team:
            cat_teams = by_cat.get(picked_cat, [])
            tid_options = [t["id"] for t in cat_teams]
            if tid_options:
                cur_sel = st.session_state.get("_chat_team_id", "")
                if cur_sel not in tid_options: cur_sel = tid_options[0]
                picked_tid = st.selectbox("Team", tid_options,
                    index=tid_options.index(cur_sel) if cur_sel in tid_options else 0,
                    format_func=lambda tid: next(
                        (f"{t.get('name', tid)} - {t.get('desc', '')}" for t in cat_teams if t["id"] == tid), tid),
                    key="chat_team_sel")
                st.session_state["_chat_team_id"] = picked_tid
                selected_team_id = picked_tid

        # Controls row: permission mode + auto-search
        ctrl1, ctrl2 = st.columns([2, 1])
        with ctrl1: permission_mode = render_permission_selector()
        with ctrl2:
            auto_search = st.toggle("Auto Search", value=st.session_state.get("_auto_search", False),
                                    help="Search web before each message (adds latency)", key="auto_search_toggle")
            st.session_state["_auto_search"] = auto_search

        # Session & history controls
        sessions = {s["id"]: s for s in list_sessions()}
        s1, s2, s3, s4 = st.columns([1.3, 2.4, 1, 1])
        with s1:
            st.session_state.save_chat_history = st.checkbox("Save history", value=bool(st.session_state.save_chat_history))
        with s2:
            session_ids = [""] + sorted(sessions.keys(),
                key=lambda sid: sessions[sid].get("updated_at", ""), reverse=True)
            picked_session = st.selectbox("History", session_ids,
                format_func=lambda sid: "No history" if not sid else (
                    f"{sessions[sid].get('title', sid)} - {sessions[sid].get('updated_at', '')[:19]}"),
                key="chat_session_picker")
        with s3:
            if st.button("Load", use_container_width=True, disabled=not picked_session):
                sess = sessions.get(picked_session, {})
                st.session_state.chat_history = sess.get("history", [])
                st.session_state.user_name = sess.get("user_name", st.session_state.user_name)
                st.session_state.user_identity = sess.get("user_identity", "")
                st.session_state["_chat_session_id"] = picked_session
                st.session_state["save_chat_history"] = True
                if sess.get("team_id"): st.session_state["_chat_team_id"] = sess["team_id"]
                st.rerun()
        with s4:
            if st.button("Reset", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state["_chat_session_id"] = ""
                st.session_state["_current_run_id"] = ""
                st.session_state["_upload_key_id"] += 1
                st.rerun()

        # User profile
        c1, c2 = st.columns(2)
        with c1: st.session_state.user_name = st.text_input("Your name", value=st.session_state.user_name, key="uname")
        with c2: st.session_state.user_identity = st.text_input("Identity (optional)",
            value=st.session_state.user_identity, key="uid", placeholder="e.g. Product Manager")

    if not selected_team_id: st.info("Select a team above"); return
    team = get_team(selected_team_id)
    if not team: st.warning("Team not found"); return
    roles = team.get("roles", [])
    if not roles: st.warning("No roles in this team"); return

    # Chat style
    team_chat_style = team.get("chat_style", "round")
    if team_chat_style == "parallel":
        chat_style = "parallel"
        with st.expander("对话模式", expanded=False):
            st.caption("⚡ Parallel - stages run concurrently via ThreadPool")
            render_agent_flow(roles, st.session_state.user_name or user_name)
    else:
        default_mode = team_chat_style if team_chat_style in {"round", "free"} else "round"
        mode_key = f"chat_runtime_mode_{selected_team_id}"
        if st.session_state.get(mode_key) not in {"round", "free"}:
            st.session_state[mode_key] = default_mode
        with st.expander("对话模式", expanded=False):
            chat_style = st.radio("Mode", ["round", "free"], horizontal=True,
                format_func=lambda s: {"round": "Round-robin (one-by-one streaming)", "free": "Free chat"}[s],
                key=mode_key, label_visibility="collapsed")
            render_agent_flow(roles, st.session_state.user_name or user_name)
    auto_search = st.session_state.get("_auto_search", False)
    st.caption(f"当前团队：{team.get('name', selected_team_id)} · {len(roles)} agents · {chat_style}")
    st.divider()

    # ── HISTORY DISPLAY (rich: Mermaid + images + tables) ──
    history = st.session_state.chat_history
    for msg in history:
        if msg.get("hidden"): continue
        avatar = msg.get("avatar", "")
        display_avatar = avatar_for_chat(avatar)
        source = msg["source"]
        with st.chat_message(source, avatar=display_avatar):
            # 🔥 Agent name header — fix missing name display in history
            stage_tag = f" · {msg['stage']}" if msg.get("stage") else ""
            st.caption(f"🐙 **{source}**{stage_tag}")
            render_message_content(msg.get("content", ""))
            render_attachments(msg.get("attachments", []))

    if st.session_state["_pending_agents"]:
        st.info("Agents responding..."); return

    # Continue button (round mode)
    prompt = None
    pending_uploads = []
    role_names = [r["name"] for r in roles]
    if chat_style == "round" and history:
        last_src = history[-1].get("source", "")
        if last_src in role_names:
            cc1, cc2 = st.columns([1, 5])
            with cc1:
                if st.button("Continue", use_container_width=True, key="ctn_btn"): prompt = "(continue)"
            with cc2: st.caption("Click Continue or type below to interject")

    # Chat input
    if not prompt:
        # Check for quick task
        if st.session_state.get("quick_task"):
            default_prompt = st.session_state.quick_task
            st.session_state.quick_task = ""
        else:
            default_prompt = "请输入任务..."
        chat_value = st.chat_input(f"{user_name}: type message...",
            accept_file="multiple", file_type=CHAT_ATTACHMENT_TYPES,
            max_upload_size=200, key=f"chat_input_{st.session_state['_upload_key_id']}")
        prompt, pending_uploads = _split_chat_input_value(chat_value)
    if pending_uploads and not prompt: prompt = "(analyze attachments)"
    if not prompt: return

    # ── RUN SETUP ──
    user_content = prompt if prompt != "(continue)" else "(continue discussion)"
    cur_history = list(history)
    if prompt != "(continue)" or not st.session_state.get("_current_run_id"):
        run_id = uuid.uuid4().hex[:12]
        st.session_state["_current_run_id"] = run_id
        save_run_state(run_id, user_content, selected_team_id, chat_style)
    run_id = st.session_state.get("_current_run_id", "")
    st.caption(f"run_id: `{run_id}`")

    # User message
    attachments = _save_uploaded_files(pending_uploads or [])
    with st.chat_message(user_name):
        render_user_bubble(user_name, user_content)
        render_attachments(attachments)
    cur_history.append({"source": user_name, "content": user_content, "avatar": "", "attachments": attachments})

    # Auto context (FAST: datetime only)
    all_role_skills = [role.get("skills", []) for role in roles]
    auto_ctx, auto_events = _build_auto_context(user_content, all_role_skills, auto_search=auto_search)
    if auto_ctx:
        cur_history.append({"source": "Galaxy Context", "content": auto_ctx,
                            "avatar": "", "tool_events": auto_events, "hidden": True})

    st.session_state["_pending_agents"] = True

    # Create agents
    try:
        agent_infos = create_agents_for_team(team, run_id=run_id)
    except RuntimeError as e:
        st.error(str(e))
        st.info("Tip: check model API key in Models tab")
        st.session_state["_pending_agents"] = False; return
    workspace_root = _get_workspace_root()
    if not agent_infos:
        st.error("Cannot create agents - check model/key config")
        st.session_state["_pending_agents"] = False; return

    max_turns = int(team.get("max_turns", 10) or 10)
    prior_turns = sum(1 for h in cur_history if h.get("source") in role_names)
    remaining_turns = max(0, max_turns - prior_turns)
    if remaining_turns <= 0:
        st.warning(f"Reached max turns ({max_turns}). Reset to start new chat.")
        st.session_state["_pending_agents"] = False; return

    # ══════════════════════════════════════════════════
    # PARALLEL MODE (generator — render each agent as it finishes)
    # ══════════════════════════════════════════════════
    if chat_style == "parallel" and remaining_turns > 0:
        for ainfo, payload, stage_name in run_parallel_stages_stream(
            team, cur_history, user_name, remaining_turns,
            workspace_root=workspace_root, run_id=run_id,
        ):
            # Stage completion marker (None agent = handoff done)
            if ainfo is None:
                continue

            agent_name = ainfo["display_name"]
            full = str(payload.get("content", "")).strip()
            tool_events = payload.get("events", []) or []
            guard = payload.get("guard")
            structured = payload.get("structured")
            chat_avatar = avatar_for_chat(ainfo["avatar"])

            with st.chat_message(agent_name, avatar=chat_avatar):
                # 🔥 Agent name header — fix missing name display
                st.caption(f"🐙 **{agent_name}** · {stage_name}")
                if tool_events:
                    st.markdown(render_tool_events(tool_events), unsafe_allow_html=True)
                render_agent_bubble(agent_name, full, ainfo["color"], ainfo["avatar"], stage_name)
                render_message_content(full)
                if guard:
                    render_guard_result(guard, payload.get("retry_count", 0), structured)

            if full:
                cur_history.append({"source": agent_name, "content": full,
                                    "avatar": ainfo["avatar"], "stage": stage_name})
                remaining_turns -= 1

            save_agent_diff(run_id, agent_name, workspace_root)
            raw_for_usage = "\n".join(payload.get("raw_outputs", []))
            record_model_usage(ainfo.get("model_id", ""), ainfo.get("model_cfg", {}),
                               str(payload.get("structured", "")), raw_for_usage)

    # ══════════════════════════════════════════════════
    # ROUND-ROBIN / FREE MODE (streaming, word by word)
    # ══════════════════════════════════════════════════
    else:
        passes = 1 if chat_style == "round" else max_turns
        for _pass in range(passes):
            if remaining_turns <= 0: break
            for ainfo in agent_infos:
                if remaining_turns <= 0: break
                display_name = ainfo["display_name"]
                avatar = ainfo["avatar"]
                color = ainfo["color"]
                chat_avatar = avatar_for_chat(avatar)

                task_history = history_for_model_context(cur_history, ainfo.get("context_length", 128000))
                task = _build_task_payload(task_history, display_name, user_name)

                with st.chat_message(display_name, avatar=chat_avatar):
                    # 🔥 Agent name header — fix missing name display
                    st.caption(f"🐙 **{display_name}**")
                    tool_placeholder = st.empty()
                    stream_placeholder = st.empty()
                    full = ""
                    tool_events: list[str] = []
                    for chunk in _sync_agent_stream(ainfo, task):
                        if _is_tool_event_chunk(chunk):
                            tool_events.append(str(chunk).strip())
                            tool_placeholder.markdown(
                                render_tool_events(tool_events), unsafe_allow_html=True)
                            continue
                        full += chunk
                        stream_placeholder.markdown(
                            render_streaming_bubble(display_name, full, color, chat_avatar),
                            unsafe_allow_html=True)

                full = full.strip()
                if full:
                    record_model_usage(ainfo.get("model_id", ""), ainfo.get("model_cfg", {}), task, full)
                    cur_history.append({"source": display_name, "content": full, "avatar": avatar})
                    remaining_turns -= 1

    # ── Save and rerun ──
    st.session_state.chat_history = cur_history
    if st.session_state.save_chat_history:
        save_session(st.session_state.get("_chat_session_id"),
                     _clip_output(user_content.replace("\n", " "), 48) or f"Chat {run_id[:6]}",
                     selected_team_id, st.session_state.user_name,
                     st.session_state.user_identity, cur_history)
    st.session_state["_pending_agents"] = False
    st.session_state["_upload_key_id"] += 1
    st.rerun()


def _get_all_categories() -> dict:
    from presets.teams import CATEGORIES
    cats = dict(CATEGORIES)
    cats.setdefault("Parallel Work", "⚡")
    cats.setdefault("Uncategorized", "📁")
    return cats
