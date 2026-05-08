"""Config tab — project root, soul MD presets, custom skills, advanced settings."""

from __future__ import annotations

import uuid
from pathlib import Path

import streamlit as st

from config import DATA_DIR, SOUL_MD_NAMES
from data.database import get_db, db_transaction
from data.model_store import list_models
from ui.skills import _ai_call_to_text


def _get_workspace_root() -> Path:
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM project_state WHERE key = 'root'").fetchone()
        if row and row[0]:
            p = Path(row[0]).expanduser().resolve()
            if p.exists() and p.is_dir():
                return p
    except Exception:
        pass
    return DATA_DIR.resolve()


def _get_project_enabled() -> bool:
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM project_state WHERE key = 'enabled'").fetchone()
        return row and row[0] == "1"
    except Exception:
        return False


def _get_soul_md_paths() -> list[str]:
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM project_state WHERE key = 'soul_md_paths'").fetchone()
        if row and row[0]:
            return [p for p in row[0].split("\n") if p.strip()]
    except Exception:
        pass
    return []


def render_config_tab() -> None:
    st.header("⚙️ 配置")

    # ── Project workspace ──
    st.subheader("📁 工作区根目录")
    root = _get_workspace_root()
    enabled = _get_project_enabled()

    c1, c2, c3 = st.columns([1, 3, 1.5])
    with c1:
        new_enabled = st.toggle("启用", value=enabled, help="启用后终端和文件工具默认在此目录内运行")
        if new_enabled != enabled:
            with db_transaction() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO project_state (key, value) VALUES ('enabled', ?)",
                    ("1" if new_enabled else "0",),
                )
            st.rerun()
    with c2:
        new_root = st.text_input("项目根目录", value=str(root),
                                 placeholder=r"E:\projects\myproject")
    with c3:
        if st.button("应用工作区", use_container_width=True):
            p = Path(new_root).expanduser()
            if p.exists() and p.is_dir():
                with db_transaction() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO project_state (key, value) VALUES ('root', ?)",
                        (str(p.resolve()),),
                    )
                st.success(f"工作区已切换到: {p}")
                st.rerun()
            else:
                st.error("目录不存在")

    st.caption(f"当前工作区: `{root}`")

    # Browse subdirectories
    if root.exists():
        try:
            subdirs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
            if subdirs:
                choices = ["(保持当前)"] + [p.name for p in subdirs[:100]]
                picked = st.selectbox("快速切换到子目录", choices, key="config_subdir")
                if picked != "(保持当前)" and st.button("切换到选中目录"):
                    p = root / picked
                    with db_transaction() as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO project_state (key, value) VALUES ('root', ?)",
                            (str(p.resolve()),),
                        )
                    st.rerun()
        except Exception:
            pass

    # ── Soul MD file paths ──
    st.caption("灵魂 MD 文件路径 (每行一个，留空自动查找 CLAUDE.md/AGENTS.md 等)")
    soul_paths = _get_soul_md_paths()
    new_soul_paths = st.text_area(
        "灵魂 MD 路径",
        value="\n".join(soul_paths),
        height=78,
        placeholder="CLAUDE.md\n.docs/agent-rules.md",
        key="soul_paths_input",
    )
    if st.button("保存灵魂 MD 路径", key="save_soul_paths"):
        paths_str = "\n".join(line.strip() for line in new_soul_paths.splitlines() if line.strip())
        with db_transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO project_state (key, value) VALUES ('soul_md_paths', ?)",
                (paths_str,),
            )
        st.success("已保存")

    st.divider()

    # ── Guard / Multimodal model settings ──
    st.subheader("⚙️ 高级模型设置")
    models = list_models()
    model_map = {m["id"]: m for m in models}

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**🛡 Guard 审查模型**")
        st.caption("LLM-as-Judge 深度审查，留空则只用启发式 Guard")
        conn = get_db()
        guard_row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'guard_model_id'"
        ).fetchone()
        guard_mid = guard_row[0] if guard_row else ""
        guard_options = {m["id"]: f"{m['name']} ({m['model']})" for m in models}
        guard_options[""] = "(不使用 LLM Guard)"
        guard_sel = st.selectbox(
            "Guard 模型", list(guard_options.keys()),
            index=list(guard_options.keys()).index(guard_mid) if guard_mid in guard_options else 0,
            format_func=lambda x: guard_options[x],
            key="config_guard_sel",
        )
        if guard_sel != guard_mid:
            with db_transaction() as conn2:
                conn2.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('guard_model_id', ?)",
                    (guard_sel,),
                )
            st.rerun()

    with g2:
        st.markdown("**👁 多模态视觉模型**")
        st.caption("上传图片时先做 OCR/描述再给语言模型，留空则跳过")
        vision_row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'vision_model_id'"
        ).fetchone()
        vision_mid = vision_row[0] if vision_row else ""
        vision_options = {m["id"]: f"{m['name']} ({m['model']})" for m in models}
        vision_options[""] = "(不启用多模态管道)"
        vision_sel = st.selectbox(
            "视觉模型", list(vision_options.keys()),
            index=list(vision_options.keys()).index(vision_mid) if vision_mid in vision_options else 0,
            format_func=lambda x: vision_options[x],
            key="config_vision_sel",
        )
        if vision_sel != vision_mid:
            with db_transaction() as conn2:
                conn2.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('vision_model_id', ?)",
                    (vision_sel,),
                )
            st.rerun()

    st.divider()

    # ── Soul MD presets ──
    st.subheader("🧬 灵魂 MD 预设")
    st.caption("可复用的灵魂 MD 正文。创建后在对话页可勾选注入 Agent。")

    presets = conn.execute("SELECT * FROM soul_presets ORDER BY name").fetchall()

    if presets:
        for preset in presets:
            with st.expander(f"{preset['name']} — {preset['overview'][:60]}", expanded=False):
                name = st.text_input("名称", value=preset["name"], key=f"soul_name_{preset['id']}")
                overview = st.text_area("概述", value=preset["overview"], height=70,
                                        key=f"soul_overview_{preset['id']}")
                content = st.text_area("内容/Markdown", value=preset["content"], height=260,
                                       key=f"soul_content_{preset['id']}")
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("保存", key=f"save_soul_{preset['id']}", use_container_width=True):
                        with db_transaction() as conn2:
                            conn2.execute(
                                "UPDATE soul_presets SET name=?, overview=?, content=?, "
                                "updated_at=datetime('now') WHERE id=?",
                                (name.strip(), overview.strip(), content.strip(), preset["id"]),
                            )
                        st.success("已更新")
                        st.rerun()
                with c2:
                    if st.button("删除", key=f"del_soul_{preset['id']}", use_container_width=True):
                        with db_transaction() as conn2:
                            conn2.execute("DELETE FROM soul_presets WHERE id=?", (preset["id"],))
                        st.rerun()
    else:
        st.caption("还没有灵魂 MD 预设")

    st.divider()

    # ── AI 生成灵魂 MD ──
    _models = list_models()
    _model_options = {m["id"]: f"{m['name']} ({m['model']})" for m in _models}

    with st.expander("🤖 AI 生成灵魂 MD", expanded=False):
        st.caption("描述你想要的 Agent 灵魂/人格，AI 自动生成 SOUL.md 内容。")
        ai_soul_desc = st.text_area(
            "灵魂描述",
            placeholder="例如：一个严格追求代码质量的资深架构师，注重设计模式和SOLID原则",
            height=80,
            key="ai_soul_desc"
        )
        ai_soul_model_col, ai_soul_btn_col = st.columns([2, 1])
        with ai_soul_model_col:
            if _model_options:
                ai_soul_model = st.selectbox(
                    "模型", list(_model_options.keys()),
                    format_func=lambda x: _model_options[x],
                    key="ai_soul_model"
                )
            else:
                ai_soul_model = ""
                st.warning("请先在模型配置中添加模型")
        with ai_soul_btn_col:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🤖 生成内容", use_container_width=True, key="ai_gen_soul_btn"):
                if not ai_soul_desc.strip():
                    st.warning("请输入灵魂描述")
                elif not _model_options:
                    st.warning("请先在模型配置中添加模型")
                else:
                    with st.spinner("AI 正在生成灵魂 MD..."):
                        try:
                            result = _ai_generate_soul(ai_soul_desc, ai_soul_model)
                            st.session_state["ai_soul_result"] = result
                            st.success("灵魂 MD 已生成，请查看并确认后填入表单")
                        except Exception as e:
                            st.error(f"生成失败: {e}")

        if "ai_soul_result" in st.session_state and st.session_state["ai_soul_result"]:
            r = st.session_state["ai_soul_result"]
            st.text_input("名称", value=r.get("name", ""), key="ai_soul_name_preview")
            st.text_area("概述", value=r.get("overview", ""), height=70, key="ai_soul_overview_preview")
            st.text_area("内容/Markdown", value=r.get("content", ""), height=180, key="ai_soul_content_preview")
            if st.button("📋 填入新建表单", use_container_width=True, key="ai_soul_fill"):
                st.session_state["_soul_name_prefill"] = r.get("name", "")
                st.session_state["_soul_overview_prefill"] = r.get("overview", "")
                st.session_state["_soul_content_prefill"] = r.get("content", "")
                st.rerun()

    with st.form("add_soul", clear_on_submit=True):
        st.markdown("**➕ 新增灵魂 MD**")
        name = st.text_input("名称", placeholder="如: 团队代码规范",
            value=st.session_state.pop("_soul_name_prefill", ""),
            key="soul_name_input")
        overview = st.text_area("概述", height=70, placeholder="一句话说明用途",
            value=st.session_state.pop("_soul_overview_prefill", ""),
            key="soul_overview_input")
        content = st.text_area("内容/Markdown", height=180, placeholder="写入完整规则...",
            value=st.session_state.pop("_soul_content_prefill", ""),
            key="soul_content_input")
        if st.form_submit_button("创建", use_container_width=True):
            if name.strip() and content.strip():
                sid = f"soul_{uuid.uuid4().hex[:8]}"
                with db_transaction() as conn2:
                    conn2.execute(
                        "INSERT INTO soul_presets (id, name, overview, content) VALUES (?, ?, ?, ?)",
                        (sid, name.strip(), overview.strip(), content.strip()),
                    )
                st.success("已创建")
                st.rerun()
            else:
                st.error("请填写名称和内容")


# ── AI Soul MD Generator ────────────────────────────────

def _ai_generate_soul(user_desc: str, model_id: str) -> dict:
    """Generate SOUL.md content via LLM."""
    prompt = f"""根据以下描述生成一个 Agent 灵魂配置（SOUL.md）。

## 用户描述
{user_desc}

## 要求
- 名称：一个简洁的中文名称（5-10字）
- 概述：一句话概括灵魂特点
- 内容：完整的 Markdown 格式灵魂档案，包含身份、性格、行事风格、底线、对话风格等
- 参考格式：SOUL.md 通常包含"我是谁"、"性格"、"行事风格"、"底线"、"对话风格"等板块

## 输出格式（严格JSON）
{{"name":"灵魂名称","overview":"一句话概述","content":"完整的Markdown内容"}}

现在请输出。"""

    import json as _json, re as _re
    raw = _ai_call_to_text(prompt, system="你是专业的Agent灵魂设计师。只输出JSON格式。", model_id=model_id)
    m = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, _re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        a, b = raw.find('{'), raw.rfind('}')
        if a >= 0 and b > a:
            raw = raw[a:b+1]
    return _json.loads(raw)


# ── AI Custom Skill Generator ────────────────────────────

def _ai_generate_skill(user_desc: str, model_id: str) -> dict:
    """Generate custom skill definition via LLM."""
    prompt = f"""根据以下描述生成一个自定义技能的定义。

## 用户描述
{user_desc}

## 要求
- 名称：一个简洁的中文技能名称（5-15字）
- 概述：一句话概述这个技能的功能
- 内容：详细描述，包含以下部分：
  - **适用场景**：什么情况下使用
  - **工作流程**：步骤和方法
  - **约束条件**：不能做什么、必须遵循的规则
  - **输出格式**：产出什么样的结果

## 输出格式（严格JSON）
{{"name":"技能名称","overview":"一句话概述","content":"完整的技能定义（Markdown格式）"}}

现在请输出。"""

    import json as _json, re as _re
    raw = _ai_call_to_text(prompt, system="你是专业的Agent技能设计师。只输出JSON格式。", model_id=model_id)
    m = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, _re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        a, b = raw.find('{'), raw.rfind('}')
        if a >= 0 and b > a:
            raw = raw[a:b+1]
    return _json.loads(raw)
