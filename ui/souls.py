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

    # Prefill values — from editing agent, or from AI-generated session state
    defaults = editing_agent or {}
    if not editing_agent:
        # Pop AI-generated prefill values (consumed once)
        for key, skey in [
            ("name", "_soul_name_prefill"),
            ("avatar", "_soul_avatar_prefill"),
            ("soul_md", "_soul_md_prefill"),
            ("worker_thought", "_soul_wt_prefill"),
            ("position", "_soul_pos_prefill"),
            ("model_id", "_soul_model_prefill"),
            ("skills", "_soul_skills_prefill"),
            ("lifespan_budget", "_soul_lifespan_prefill"),
        ]:
            val = st.session_state.pop(skey, None)
            if val is not None and val != "":
                defaults[key] = val

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
    st.caption("描述你想要的 Agent，AI 自动生成完整的灵魂 Agent（含人格、头像、技能、职位等全部配置）。")

    # Model selector for AI generation
    from data.model_store import list_models
    models = list_models()
    model_options = {m["id"]: f"{m['name']} ({m.get('model','')})" for m in models}
    if not model_options:
        st.warning("请先在模型配置中添加模型")
        return

    gen_col1, gen_col2 = st.columns([2, 1])
    with gen_col1:
        ai_desc = st.text_area(
            "描述",
            placeholder="例如：一个幽默的资深全栈工程师，喜欢写测试，讨厌没注释的代码，擅长Python和React",
            height=80,
            key="ai_soul_agent_desc",
        )
    with gen_col2:
        gen_model = st.selectbox(
            "生成模型",
            list(model_options.keys()),
            format_func=lambda x: model_options[x],
            key="ai_soul_agent_model",
        )

    if st.button("🤖 生成完整灵魂 Agent", key="ai_gen_soul_agent_btn", use_container_width=True):
        if ai_desc.strip():
            with st.spinner("AI 正在生成灵魂 Agent..."):
                try:
                    result = _ai_generate_soul_agent(ai_desc, gen_model)
                    st.session_state["ai_soul_agent_result"] = result
                    st.success("已生成！")
                except Exception as e:
                    st.error(f"生成失败: {e}")
        else:
            st.warning("请输入描述")

    if "ai_soul_agent_result" in st.session_state:
        r = st.session_state["ai_soul_agent_result"]
        st.divider()
        st.markdown("### 生成预览")

        prev_col1, prev_col2 = st.columns(2)
        with prev_col1:
            st.text_input("名称", value=r.get("name", ""), key="ai_sa_name_preview")
            st.text_input("头像", value=r.get("avatar", "🤖"), key="ai_sa_avatar_preview")
            st.text_input("碎碎念", value=r.get("worker_thought", ""), key="ai_sa_wt_preview")
            position_preview = r.get("position", "")
            st.selectbox(
                "职位", ["", "ceo", "dept_head", "member"],
                index=["", "ceo", "dept_head", "member"].index(position_preview) if position_preview in ["ceo", "dept_head", "member"] else 0,
                format_func=_position_label,
                key="ai_sa_pos_preview",
            )
        with prev_col2:
            st.text_input("绑定模型", value=r.get("model_id", ""), key="ai_sa_model_preview",
                         placeholder="留空使用默认")
            skills = r.get("skills", [])
            st.caption(f"推荐技能 ({len(skills)}): {', '.join(skills[:8])}")
            st.number_input("寿命预算", value=r.get("lifespan_budget", 128000),
                          min_value=16000, max_value=2000000, step=16000, key="ai_sa_ls_preview")

        st.text_area("灵魂 MD", value=r.get("soul_md", ""), height=200, key="ai_sa_md_preview")

        # Auto-fill button — writes to session state so the form picks it up
        if st.button("📋 一键填入创建表单", use_container_width=True, key="ai_sa_fill_btn"):
            st.session_state["_soul_name_prefill"] = r.get("name", "")
            st.session_state["_soul_avatar_prefill"] = r.get("avatar", "🤖")
            st.session_state["_soul_md_prefill"] = r.get("soul_md", "")
            st.session_state["_soul_wt_prefill"] = r.get("worker_thought", "")
            st.session_state["_soul_pos_prefill"] = r.get("position", "")
            st.session_state["_soul_model_prefill"] = r.get("model_id", "")
            st.session_state["_soul_skills_prefill"] = r.get("skills", [])
            st.session_state["_soul_lifespan_prefill"] = r.get("lifespan_budget", 128000)
            st.success("已填入表单，切换到「创建/编辑」标签页查看")
            st.rerun()


# ── AI Generator ────────────────────────────────────

def _ai_generate_soul_agent(user_desc: str, model_id: str = "") -> dict:
    """AI generate a complete soul agent config: name, avatar, soul_md,
    worker_thought, position, recommended skills, lifespan, model preference."""
    from ui.skills import _ai_call_to_text
    from skills.registry import get_registry as _get_reg
    import json as _json, re as _re

    # Collect available skill IDs for the AI to pick from
    registry = _get_reg()
    all_skills = registry.list_all()
    skill_list = "\n".join(
        f"- {sid}: {info.name} — {info.desc[:80]}"
        for sid, info in list(all_skills.items())[:60]
    )

    prompt = f"""根据以下描述生成一个完整的灵魂 Agent 配置。

## 用户描述
{user_desc}

## 可用工具列表（从下面选最合适的 4-8 个技能 ID）
{skill_list}

## 必须生成的字段
- name: 简洁中文名（5-12字）
- avatar: 一个最贴切这个角色的 emoji（单字符最佳）
- soul_md: 完整Markdown人格档案，包含以下板块：
  # 角色名
  ## 我是谁（一句话身份定位）
  ## 性格（3-5条核心特质）
  ## 行事风格（工作方法和偏好）
  ## 底线（绝对不能做的事）
  ## 对话风格（怎么说话）
- worker_thought: 打工人今日心情碎碎念（≤20字，带幽默感）
- position: 合适职位，选 ceo|dept_head|member 其一
  - ceo: 统筹全局的总经理
  - dept_head: 某领域负责人，能带队
  - member: 专业执行者
- skills: 从上面列表里挑最合适的 skill IDs 列表（4-8个）
- lifespan_budget: 寿命预算推荐值，16000-256000，普通角色 128000
- model_id: 留空 ""（用户自己绑定模型）

## 输出格式（严格JSON，不要Markdown代码块）
{{
  "name": "名称",
  "avatar": "🐱",
  "soul_md": "# 角色名\\n\\n## 我是谁\\n...\\n\\n## 性格\\n- ...",
  "worker_thought": "心情",
  "position": "member",
  "skills": ["read_file", "write_file", "terminal"],
  "lifespan_budget": 128000,
  "model_id": ""
}}

现在请输出JSON。"""

    raw = _ai_call_to_text(
        prompt,
        system="你是专业的Agent灵魂设计师。你只输出严格JSON，不要任何markdown代码块，不要解释。",
        model_id=model_id,
    )

    # Extract JSON
    m = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, _re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        a, b = raw.find('{'), raw.rfind('}')
        if a >= 0 and b > a:
            raw = raw[a:b+1]

    result = _json.loads(raw)

    # Validate and clean up
    if not isinstance(result.get("name"), str) or not result["name"].strip():
        result["name"] = "未命名Agent"
    if not isinstance(result.get("soul_md"), str) or len(result["soul_md"].strip()) < 20:
        result["soul_md"] = f"# {result.get('name', 'Agent')}\n\n## 我是谁\n{user_desc[:200]}\n\n## 性格\n- 专业可靠\n\n## 行事风格\n- 按任务执行\n\n## 底线\n- 不做破坏性操作\n\n## 对话风格\n- 简洁专业"
    if not isinstance(result.get("worker_thought"), str):
        result["worker_thought"] = "今天认真干活"
    if result.get("position") not in ("ceo", "dept_head", "member"):
        result["position"] = "member"
    if not isinstance(result.get("skills"), list):
        result["skills"] = ["read_file", "write_file", "terminal", "list_files"]
    # Filter to only valid skill IDs
    valid_ids = set(all_skills.keys())
    result["skills"] = [s for s in result["skills"] if s in valid_ids][:8]
    if not result["skills"]:
        result["skills"] = ["read_file", "write_file", "terminal", "list_files"]
    if not isinstance(result.get("lifespan_budget"), (int, float)):
        result["lifespan_budget"] = 128000
    result["lifespan_budget"] = max(16000, min(2000000, int(result["lifespan_budget"])))
    result["model_id"] = result.get("model_id", "") or ""

    return result


# ── Helpers ─────────────────────────────────────────

def _position_label(pos: str) -> str:
    return {"ceo": "总经理", "dept_head": "部门负责人", "member": "成员"}.get(pos, pos or "未分配")
