"""Soul Agent management tab — CRUD, lifespan, notes, project history."""

from __future__ import annotations

import uuid
import streamlit as st

from data.soul_store import (
    list_soul_agents, get_soul_agent, save_soul_agent, delete_soul_agent,
    add_agent_note, compress_agent_context, build_soul_agent_context,
)
from data.model_store import list_models
from skills.registry import get_registry


def render_souls_tab() -> None:
    st.header("🧬 灵魂 Agent")

    tab_souls, tab_create = st.tabs(["📋 Agent 列表", "➕ 创建/编辑"])

    with tab_souls:
        _render_soul_list()

    with tab_create:
        _render_soul_form()


def _render_soul_list() -> None:
    agents = list_soul_agents()

    if not agents:
        st.info("还没有灵魂 Agent，点击「创建/编辑」标签页来创建第一个。")
        return

    st.caption(f"共 {len(agents)} 个灵魂 Agent")

    for agent in agents:
        with st.expander(
            f"{agent['avatar']} {agent['name']} "
            f"{'· ' + _position_label(agent.get('position','')) if agent.get('position') else ''}",
            expanded=False,
        ):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**灵魂MD:** {agent.get('soul_md','')[:200]}..." if len(agent.get('soul_md','')) > 200
                           else f"**灵魂MD:** {agent.get('soul_md','(空)')}")
                st.caption(f"模型: {agent.get('model_id','(未绑定)')}")
                st.caption(f"打工人碎碎念: {agent.get('worker_thought','(无)')}")
                st.caption(f"寿命预算: {agent['lifespan_budget']} tokens | "
                          f"职位: {_position_label(agent.get('position','未分配'))}")

                # Skills list
                skills = agent.get("skills", [])
                if skills:
                    st.caption(f"技能: {', '.join(skills[:10])}"
                              f"{' ...' if len(skills) > 10 else ''}")

                # Notes preview
                notes = agent.get("notes", "")
                if notes:
                    with st.expander(f"📝 笔记 ({len(notes)} 字符)", expanded=False):
                        st.text(notes[-2000:])

                # Projects
                projects = agent.get("projects", [])
                if projects:
                    with st.expander(f"📂 参与项目 ({len(projects)})", expanded=False):
                        for p in projects:
                            st.caption(f"- [{p.get('role','?')}] {p.get('project_id','?')}: "
                                      f"{p.get('summary','')[:100]}")

            with col2:
                # Longevity medicine
                if st.button("💊 长生药", key=f"longevity_{agent['id']}",
                             help="压缩笔记和项目历史，释放上下文空间"):
                    with st.spinner("压缩中..."):
                        result = compress_agent_context(agent["id"])
                        st.success(
                            f"压缩完成！笔记节省 {result['notes_saved']} 字符，"
                            f"项目节省 {result['projects_saved']} 字符"
                        )
                        st.rerun()

                # Edit button
                if st.button("✏️ 编辑", key=f"edit_{agent['id']}"):
                    st.session_state["edit_soul_agent"] = agent["id"]
                    st.rerun()

                # Delete
                if st.button("🗑 删除", key=f"delete_{agent['id']}"):
                    delete_soul_agent(agent["id"])
                    st.rerun()

                # Add note
                with st.form(key=f"note_{agent['id']}"):
                    new_note = st.text_input("添加笔记", key=f"note_input_{agent['id']}",
                                            placeholder="记录经验或观察...")
                    if st.form_submit_button("📝"):
                        if new_note.strip():
                            add_agent_note(agent["id"], new_note)
                            st.rerun()

                # Context preview
                if st.button("👁 查看上下文", key=f"ctx_{agent['id']}"):
                    ctx = build_soul_agent_context(agent["id"])
                    st.session_state[f"ctx_preview_{agent['id']}"] = ctx

            if f"ctx_preview_{agent['id']}" in st.session_state:
                with st.expander("📄 完整上下文（发送给模型的内容）", expanded=True):
                    st.text_area(
                        "系统上下文", value=st.session_state[f"ctx_preview_{agent['id']}"],
                        height=400, key=f"ctx_area_{agent['id']}"
                    )
                    if st.button("关闭", key=f"close_ctx_{agent['id']}"):
                        del st.session_state[f"ctx_preview_{agent['id']}"]
                        st.rerun()


def _render_soul_form() -> None:
    # Check if editing
    edit_id = st.session_state.pop("edit_soul_agent", None)
    editing_agent = get_soul_agent(edit_id) if edit_id else None

    if editing_agent:
        st.subheader(f"编辑: {editing_agent['name']}")
    else:
        st.subheader("创建新灵魂 Agent")

    # Prefill values
    defaults = editing_agent or {}

    with st.form("soul_agent_form", clear_on_submit=not editing_agent):
        name = st.text_input("名称 *", value=defaults.get("name", ""),
                            placeholder="如: 首席架构师张三")
        avatar = st.text_input("头像", value=defaults.get("avatar", "🤖"),
                              placeholder="emoji 或 image:avatars/xxx.png")

        soul_md = st.text_area(
            "灵魂 MD *",
            value=defaults.get("soul_md", ""),
            height=200,
            placeholder="定义 agent 的人格、工作风格、底线、对话风格...\n\n## 我是谁\n...\n## 性格\n...\n## 行事风格\n...",
        )

        worker_thought = st.text_input(
            "打工人碎碎念 (≤20字)",
            value=defaults.get("worker_thought", ""),
            max_chars=20,
            placeholder="如: 今天只想摸鱼...",
        )

        col1, col2 = st.columns(2)
        with col1:
            lifespan = st.number_input(
                "寿命预算 (tokens)", value=defaults.get("lifespan_budget", 128000),
                min_value=16000, max_value=2000000, step=16000,
                help="上下文长度上限，超过后需服用长生药压缩",
            )

            position = st.selectbox(
                "公司职位",
                ["", "ceo", "dept_head", "member"],
                index=["", "ceo", "dept_head", "member"].index(defaults.get("position", "")) if defaults.get("position", "") in ["ceo", "dept_head", "member"] else 0,
                format_func=_position_label,
            )

        with col2:
            # Model selection
            models = list_models()
            model_options = {m["id"]: f"{m['name']} ({m.get('model','')})" for m in models}
            model_options[""] = "(使用默认模型)"
            current_model = defaults.get("model_id", "")
            if current_model not in model_options:
                current_model = ""
            model_sel = st.selectbox(
                "绑定模型",
                list(model_options.keys()),
                format_func=lambda x: model_options[x],
                index=list(model_options.keys()).index(current_model),
            )

            # Skills selection
            registry = get_registry()
            all_skills = registry.list_all()
            skill_options = {sid: f"{info.name} ({sid})" for sid, info in all_skills.items()}
            current_skills = defaults.get("skills", [])
            valid_current = [s for s in current_skills if s in skill_options]
            skills_sel = st.multiselect(
                "工具技能",
                list(skill_options.keys()),
                default=valid_current,
                format_func=lambda x: skill_options.get(x, x),
            )

        submitted = st.form_submit_button(
            "💾 保存" if not editing_agent else "💾 更新",
            use_container_width=True,
        )

        if submitted:
            if not name.strip():
                st.error("请填写名称")
            elif not soul_md.strip():
                st.error("请填写灵魂 MD")
            else:
                data = {
                    "id": edit_id if editing_agent else "",
                    "name": name.strip(),
                    "avatar": avatar.strip() or "🤖",
                    "soul_md": soul_md.strip(),
                    "worker_thought": worker_thought.strip()[:20],
                    "lifespan_budget": lifespan,
                    "position": position,
                    "department_id": editing_agent.get("department_id", ""),
                    "model_id": model_sel,
                    "skills": skills_sel,
                    "notes": editing_agent.get("notes", ""),
                    "projects": editing_agent.get("projects", []),
                }
                saved_id = save_soul_agent(data)
                if editing_agent:
                    st.success(f"已更新: {name}")
                else:
                    st.success(f"已创建: {name} (id: {saved_id})")
                st.rerun()

    # Cancel editing
    if editing_agent and st.button("❌ 取消编辑"):
        st.rerun()

    # AI Generate
    st.divider()
    with st.expander("🤖 AI 生成灵魂 Agent", expanded=False):
        _render_ai_generate()


def _render_ai_generate() -> None:
    st.caption("描述你想要的 Agent 人格，AI 自动生成灵魂 MD。")
    ai_desc = st.text_area(
        "描述",
        placeholder="例如：一个幽默的资深全栈工程师，喜欢写测试，讨厌没注释的代码",
        height=80,
        key="ai_soul_agent_desc",
    )
    if st.button("🤖 生成灵魂 MD", key="ai_gen_soul_agent_btn"):
        if ai_desc.strip():
            with st.spinner("AI 生成中..."):
                try:
                    result = _ai_generate_soul_agent(ai_desc)
                    st.session_state["ai_soul_agent_result"] = result
                except Exception as e:
                    st.error(f"生成失败: {e}")
        else:
            st.warning("请输入描述")

    if "ai_soul_agent_result" in st.session_state:
        r = st.session_state["ai_soul_agent_result"]
        st.text_input("预填名称", value=r.get("name", ""), key="ai_sa_name")
        st.text_area("预填灵魂 MD", value=r.get("soul_md", ""), height=200, key="ai_sa_md")
        st.text_input("预填碎碎念", value=r.get("worker_thought", ""), key="ai_sa_wt")
        if st.button("📋 填入表单"):
            st.session_state["edit_soul_agent"] = ""  # clear edit mode
            st.rerun()


# ── AI Generator ────────────────────────────────────

def _ai_generate_soul_agent(user_desc: str) -> dict:
    from ui.skills import _ai_call_to_text
    import json as _json, re as _re

    prompt = f"""根据以下描述生成一个灵魂 Agent 的配置。

## 用户描述
{user_desc}

## 要求
- name: 简洁中文名（5-10字）
- soul_md: 完整Markdown，包含# 角色名、## 性格、## 行事风格、## 底线、## 对话风格
- worker_thought: 打工人今日心情（≤20字）

## 输出格式（严格JSON）
{{"name":"名称","soul_md":"完整Markdown","worker_thought":"心情"}}

现在请输出JSON。"""

    raw = _ai_call_to_text(prompt, system="你是灵魂设计师。只输出JSON，不要markdown代码块。")
    m = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, _re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        a, b = raw.find('{'), raw.rfind('}')
        if a >= 0 and b > a:
            raw = raw[a:b+1]
    return _json.loads(raw)


# ── Helpers ─────────────────────────────────────────

def _position_label(pos: str) -> str:
    return {"ceo": "总经理", "dept_head": "部门负责人", "member": "成员"}.get(pos, pos or "未分配")
