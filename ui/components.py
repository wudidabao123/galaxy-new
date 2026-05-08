"""Shared UI components — agent bubbles, tool panels, permission mode selector."""
from __future__ import annotations

import html
import re as _re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import AGENT_COLORS, DATA_DIR

# ── Bubbles ──────────────────────────────────────────────

def render_agent_bubble(display_name: str, content: str, color: str, avatar: str,
                        stage_name: str = "") -> None:
    """Render a premium chat bubble for an agent message (history display)."""
    safe_content = html.escape(content)
    avatar_display = avatar_for_chat(avatar)
    stage_prefix = f"{stage_name} · " if stage_name else ""

    bubble_html = f"""<div style="
        background: linear-gradient(135deg, {color}15 0%, {color}08 100%);
        border-left: 3px solid {color};
        border-radius: 4px 12px 12px 12px;
        padding: 10px 14px;
        margin: 4px 0;
        font-size: 0.95rem;
        line-height: 1.6;
        color: #e2e8f0;
    ">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="font-size:1.1rem;">{avatar_display}</span>
        <strong style="color:{color};font-size:0.9rem;">{stage_prefix}{display_name}</strong>
    </div>
    <div style="white-space:pre-wrap;word-break:break-word;color:#cbd5e1;">{safe_content}</div>
    </div>"""
    st.markdown(bubble_html, unsafe_allow_html=True)


def render_user_bubble(user_name: str, content: str) -> None:
    safe_content = html.escape(content)
    bubble_html = f"""<div style="
        background: linear-gradient(135deg, #334155 0%, #1e293b 100%);
        border-radius: 12px 4px 12px 12px;
        padding: 10px 14px; margin: 4px 0;
        font-size: 0.95rem; line-height: 1.6; color: #e2e8f0;
    ">{safe_content}</div>"""
    st.markdown(bubble_html, unsafe_allow_html=True)


def render_streaming_bubble(display_name: str, full_text: str, color: str,
                            chat_avatar: str) -> str:
    """Build the HTML for a live-streaming bubble. Returns HTML string."""
    safe = html.escape(full_text)
    return f"""<div style="
        background: linear-gradient(135deg, {color}15 0%, {color}08 100%);
        border-left: 3px solid {color};
        border-radius: 4px 12px 12px 12px;
        padding: 10px 14px; margin: 4px 0;
        font-size: 0.95rem; line-height: 1.6; color: #e2e8f0;
    ">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="font-size:1.1rem;">{chat_avatar}</span>
        <strong style="color:{color};font-size:0.9rem;">{display_name}</strong>
    </div>
    <div style="white-space:pre-wrap;word-break:break-word;color:#cbd5e1;">{safe}</div>
    </div>"""


# ── Tool events ──────────────────────────────────────────

def render_tool_events(events: list[str]) -> str:
    """Render tool call/result events as an HTML panel."""
    if not events:
        return ""
    rows = []
    for ev in events[-12:]:
        ev_str = str(ev).strip()
        if ev_str.startswith("[TOOL]"):
            icon = "→"
            text = ev_str[6:].strip()
        elif ev_str.startswith("🔧"):
            icon = "→"
            text = ev_str
        elif ev_str.startswith("✅"):
            icon = "✓"
            text = ev_str
        else:
            icon = "*"
            text = ev_str
        rows.append(
            f"<div class='galaxy-tool-row'>"
            f"<span style='color:#a78bfa;font-weight:bold;'>{icon}</span>"
            f"<span>{html.escape(text)}</span></div>"
        )
    return "<div class='galaxy-tool-panel'>" + "".join(rows) + "</div>"


# ── Rich message content ─────────────────────────────────

_MD_IMAGE_RE = _re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

def _resolve_image_paths(content: str) -> str:
    """Convert relative image paths to absolute for st.markdown rendering."""
    def _resolve(m):
        alt = m.group(1)
        raw_path = m.group(2).strip()
        if raw_path.startswith(('http://', 'https://', 'data:', '/')):
            return m.group(0)
        try:
            p = (DATA_DIR / raw_path).resolve()
            if p.exists():
                return f'![{alt}]({p.as_posix()})'
        except Exception:
            pass
        try:
            from config import GENERATED_DIR
            p = (GENERATED_DIR / raw_path).resolve()
            if p.exists():
                return f'![{alt}]({p.as_posix()})'
        except Exception:
            pass
        try:
            p = Path(raw_path).resolve()
            if p.exists():
                return f'![{alt}]({p.as_posix()})'
        except Exception:
            pass
        return m.group(0)
    return _MD_IMAGE_RE.sub(_resolve, content)


def render_mermaid_content(content: str) -> None:
    """Render Mermaid diagrams + markdown in a message."""
    pattern = _re.compile(r"```mermaid\s*(.*?)```", _re.DOTALL | _re.IGNORECASE)
    pos = 0
    rendered = False
    for match in pattern.finditer(content or ""):
        before = content[pos:match.start()]
        if before.strip():
            st.markdown(_resolve_image_paths(before))
        diagram = match.group(1).strip()
        if diagram:
            rendered = True
            safe_diagram = html.escape(diagram)
            components.html(
                f"""<div class="mermaid">{safe_diagram}</div>
                <script type="module">
                import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
                mermaid.initialize({{ startOnLoad: true, securityLevel: "loose", theme: "dark" }});
                </script>""",
                height=460, scrolling=True,
            )
        pos = match.end()
    rest = (content or "")[pos:]
    if rest.strip() or not rendered:
        st.markdown(_resolve_image_paths(rest or ""))


def render_message_content(content: str) -> None:
    """Render a message: Mermaid diagrams + markdown tables + inline images."""
    render_mermaid_content(content)


def render_attachments(attachments: list[dict]) -> None:
    """Render uploaded file attachments."""
    for att in attachments or []:
        path = DATA_DIR / att.get("path", "")
        if att.get("kind") == "image" and path.exists():
            st.image(str(path),
                     caption=f"{att.get('name')} · {att.get('size', 0)} bytes",
                     use_container_width=False)
        else:
            st.caption(f"📎 {att.get('name')} · {att.get('mime') or 'file'} · "
                       f"{att.get('size', 0)} bytes · {att.get('path')}")


# ── Controls ─────────────────────────────────────────────

def render_permission_selector() -> str:
    """Render the permission mode selector. Returns selected mode string."""
    from core.enums import PermissionMode
    st.markdown("**🔐 权限模式**")
    mode = st.radio(
        "permission_mode",
        ["ask", "guard", "auto"],
        horizontal=True,
        label_visibility="collapsed",
        format_func=lambda m: {
            "ask": "🛡 询问", "guard": "🔍 审查", "auto": "🔓 自动",
        }[m],
        key="chat_permission_mode",
    )
    if mode == "ask":
        st.caption("每次工具调用前确认")
    elif mode == "guard":
        st.caption("自动执行，事后审查")
    else:
        st.caption("放行 (危险命令仍拦截)")
    return mode


def render_guard_result(guard, retry_count: int = 0, structured=None) -> None:
    """Render guard check results in an expander."""
    if not guard:
        return
    decision = getattr(guard, "decision", None)
    decision_str = decision.value if hasattr(decision, "value") else str(decision)
    score = getattr(guard, "score", 0)
    label = f"🛡 Guard: {decision_str}，分数 {score}"
    with st.expander(label, expanded=decision_str != "pass"):
        st.caption(f"retry_count: {retry_count}")
        blocking = getattr(guard, "blocking_issues", [])
        warnings = getattr(guard, "warnings", [])
        if blocking:
            st.markdown("**阻塞问题**")
            for item in blocking:
                st.markdown(f"- {item}")
        if warnings:
            st.markdown("**警告**")
            for item in warnings:
                st.markdown(f"- {item}")


# ── Avatars & flow ───────────────────────────────────────

def avatar_for_chat(avatar: str) -> str:
    """Return a display avatar (emoji or image marker)."""
    if isinstance(avatar, str) and avatar.startswith("image:"):
        return "🖼️"
    return avatar or "💬"


def render_agent_flow(roles: list[dict], user_name: str, user_avatar: str = "👤") -> None:
    """Render a visual flow diagram of the agent team."""
    all_names = [user_name] + [r.get("name", "?") for r in roles]
    all_colors = ["#888888"] + [AGENT_COLORS[i % len(AGENT_COLORS)] for i in range(len(roles))]
    flow_cols = st.columns(len(all_names))
    for i, (name, col) in enumerate(zip(all_names, flow_cols)):
        with col:
            st.markdown(
                f"""<div style="background:{all_colors[i]};color:white;padding:8px 4px;
                border-radius:10px;text-align:center;font-weight:bold;font-size:12px;">
                {name}</div>""",
                unsafe_allow_html=True,
            )


# ── Global CSS ───────────────────────────────────────────

def inject_clean_ui() -> None:
    """Inject Galaxy New dark theme with clean readability."""
    st.markdown("""
    <style>
    /* ── Galaxy New Dark Theme ── */

    /* === GLOBAL READABILITY === */
    .stApp, .main, [data-testid="stAppViewContainer"] {
        background: #0f0e17;
    }
    
    .stMarkdown, .stMarkdown p, .stMarkdown li,
    .stMarkdown span, .stMarkdown div,
    .stCaption, .stText, label, .stSelectbox label,
    .st-emotion-cache {
        color: #e2e8f0 !important;
    }
    
    h1, h2, h3, h4, h5, h6 { color: #f1f5f9 !important; }
    
    h1 {
        font-family: 'Segoe UI', system-ui, sans-serif;
        background: linear-gradient(135deg, #a855f7, #ec4899);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.2rem !important;
        font-weight: 700 !important;
    }
    
    /* === SIDEBAR === */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1932 0%, #1e1b3a 100%) !important;
        border-right: 1px solid rgba(108,92,231,0.25);
    }
    section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    
    section[data-testid="stSidebar"] h1 {
        background: linear-gradient(135deg, #06b6d4, #a855f7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 1.5rem !important;
    }
    
    /* === EXPANDERS / CARDS === */
    div[data-testid="stExpander"] {
        background: rgba(30,28,50,0.8) !important;
        border: 1px solid rgba(108,92,231,0.25) !important;
        border-radius: 10px !important;
    }
    div[data-testid="stExpander"] * { color: #e2e8f0 !important; }
    div[data-testid="stExpander"]:hover {
        border-color: rgba(168,85,247,0.5) !important;
    }
    
    /* === BUTTONS === */
    .stButton > button, .stDownloadButton > button {
        background: linear-gradient(135deg, #6C5CE7, #a855f7) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        min-height: 2.35rem;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #7c6cf7, #b865ff) !important;
        box-shadow: 0 0 12px rgba(108,92,231,0.4);
    }
    
    /* === TABS === */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; background: transparent !important; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(30,28,50,0.6) !important;
        color: #94a3b8 !important;
        border-radius: 8px 8px 0 0 !important;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(108,92,231,0.3) !important;
        color: #f1f5f9 !important;
        border-bottom: 3px solid #a855f7 !important;
    }
    
    /* === METRICS === */
    [data-testid="stMetric"] {
        background: rgba(30,28,50,0.7) !important;
        border: 1px solid rgba(108,92,231,0.2) !important;
        border-radius: 10px !important;
        padding: 12px !important;
    }
    [data-testid="stMetricValue"] { color: #06b6d4 !important; }
    [data-testid="stMetricLabel"] { color: #94a3b8 !important; }
    
    /* === INPUTS === */
    input, textarea, [data-baseweb="input"], [data-baseweb="textarea"] {
        background: rgba(30,28,50,0.8) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(108,92,231,0.3) !important;
        border-radius: 8px !important;
    }
    input:focus, textarea:focus {
        border-color: #a855f7 !important;
        box-shadow: 0 0 8px rgba(168,85,247,0.2) !important;
    }
    [data-baseweb="select"] {
        background: rgba(30,28,50,0.8) !important;
        color: #e2e8f0 !important;
    }
    
    /* === CODE === */
    code, pre, [data-testid="stCodeBlock"] {
        background: rgba(15,14,23,0.9) !important;
        color: #e2e8f0 !important;
        border-radius: 8px !important;
    }
    
    /* === TABLES === */
    [data-testid="stTable"] th {
        background: rgba(108,92,231,0.3) !important;
        color: #f1f5f9 !important;
    }
    [data-testid="stTable"] td {
        color: #e2e8f0 !important;
        background: rgba(30,28,50,0.5) !important;
    }
    
    /* === STATUS MESSAGES === */
    .stSuccess {
        background: rgba(16,185,129,0.15) !important;
        color: #6ee7b7 !important;
        border: 1px solid rgba(16,185,129,0.3) !important;
        border-radius: 8px !important;
    }
    .stWarning {
        background: rgba(245,158,11,0.15) !important;
        color: #fcd34d !important;
        border: 1px solid rgba(245,158,11,0.3) !important;
        border-radius: 8px !important;
    }
    .stError {
        background: rgba(239,68,68,0.15) !important;
        color: #fca5a5 !important;
        border: 1px solid rgba(239,68,68,0.3) !important;
        border-radius: 8px !important;
    }
    .stInfo {
        background: rgba(59,130,246,0.15) !important;
        color: #93c5fd !important;
        border: 1px solid rgba(59,130,246,0.3) !important;
        border-radius: 8px !important;
    }
    
    /* === TOOL PANELS === */
    .galaxy-tool-panel {
        background: rgba(30,28,50,0.8) !important;
        border: 1px solid rgba(108,92,231,0.3) !important;
        border-radius: 8px !important;
        padding: 8px 10px;
        margin: 6px 0 8px 0;
        color: #cbd5e1 !important;
        font-size: 0.86rem;
    }
    .galaxy-tool-row {
        display: flex; gap: 8px; align-items: center; padding: 3px 0;
        border-bottom: 1px solid rgba(108,92,231,0.15);
        color: #cbd5e1 !important;
    }
    .galaxy-tool-row:last-child { border-bottom: 0; }
    
    /* === LAYOUT === */
    .block-container { padding-top: 1.5rem; padding-bottom: 2.5rem; max-width: 1380px; }
    
    /* === PULSE ANIMATION === */
    .galaxy-pulse { animation: pulse 2s ease-in-out infinite; }
    @keyframes pulse {
        0%, 100% { opacity: 0.7; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.05); }
    }
    </style>
    """, unsafe_allow_html=True)
