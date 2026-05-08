"""Galaxy New — Multi-agent coding workspace with concurrent engineering.

Run: .venv/Scripts/python.exe -m streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from config import DATA_DIR

# Initialize database
from data.database import init_db
init_db()

# Session state
if "quick_task" not in st.session_state:
    st.session_state.quick_task = ""
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "💬 对话"


# Register all skills
from skills import register_all_skills
register_all_skills()

# Import UI tabs
from ui.chat import render_chat_tab
from ui.teams import render_teams_tab
from ui.models import render_models_tab
from ui.runs import render_runs_tab
from ui.config_ui import render_config_tab
from ui.skills import render_skills_tab
from ui.souls import render_souls_tab
from ui.company import render_company_tab
from ui.components import inject_clean_ui

# ── Page config ──────────────────────────────────────
st.set_page_config(
    page_title="Galaxy New",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_clean_ui()

# ── Sidebar ──────────────────────────────────────────
with st.sidebar:
    st.title("⚡ Galaxy 控制台")
    from data.model_store import list_models, get_default_model
    models = list_models()
    default = get_default_model()
    if default:
        st.markdown(f"**默认模型:** {default['name']}")
        st.caption(f"`{default['model']}`")
    else:
        st.warning("未配置模型")
    st.divider()
    st.caption(f"模型: {len(models)}")
    from data.team_store import list_teams
    st.caption(f"团队: {len(list_teams())}")
    from data.soul_store import list_soul_agents
    st.caption(f"灵魂Agent: {len(list_soul_agents())}")
    from data.company_store import list_departments
    st.caption(f"部门: {len(list_departments())}")
    from data.session_store import list_sessions
    st.caption(f"聊天记录: {len(list_sessions())}")

    st.divider()
    st.markdown('<p class="galaxy-pulse" style="text-align:center;font-size:3rem;">🌌</p>', unsafe_allow_html=True)
    st.caption("Galaxy New v2.1 高欣宇，牛马虾，Hermes和codex携手制作")
    
    # Quick stats
    from data.model_store import get_model_usage
    usage = get_model_usage()
    total_calls = sum(u.get("calls", 0) for u in usage) if usage else 0
    total_est = sum(u.get("total_tokens_est", 0) for u in usage) if usage else 0
    st.caption(f"⚡ {total_calls} calls · ~{total_est//1000}k tokens")

# ── Main Title ───────────────────────────────────────
st.title("🌌 Galaxy New")
st.caption("多 Agent 编码工作台 · 并发工程 · 跨平台工具 · 多模型")

# ── Navigation ──────────────────────────────────────
if st.session_state.active_tab == "🛠️ 技能":
    st.session_state.active_tab = "🛠️ 工具和技能"

tab_options = ["💬 对话", "👥 团队", "🧬 灵魂Agent", "🏢 一人公司", "🔑 模型", "🛠️ 工具和技能", "📊 运行记录", "⚙️ 配置"]
if st.session_state.active_tab not in tab_options:
    st.session_state.active_tab = tab_options[0]

active_tab = st.radio(
    "导航",
    tab_options,
    horizontal=True,
    key="active_tab",
    label_visibility="collapsed",
)

if active_tab == "💬 对话":
    render_chat_tab()
elif active_tab == "👥 团队":
    render_teams_tab()
elif active_tab == "🧬 灵魂Agent":
    render_souls_tab()
elif active_tab == "🏢 一人公司":
    render_company_tab()
elif active_tab == "🔑 模型":
    render_models_tab()
elif active_tab == "🛠️ 工具和技能":
    render_skills_tab()
elif active_tab == "📊 运行记录":
    render_runs_tab()
elif active_tab == "⚙️ 配置":
    render_config_tab()
