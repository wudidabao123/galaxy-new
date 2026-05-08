"""Teams tab — create and manage Agent teams with avatars, advanced profiles."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import streamlit as st

from config import DATA_DIR, AGENT_COLORS, AGENT_AVATARS, AVATAR_EMOJIS
from data.team_store import list_teams, get_team, save_team, delete_team
from data.model_store import list_models
from skills.registry import get_registry
from presets.teams import CATEGORIES, PRESET_TEAMS
from ui.skills import _ai_call_json

ROLE_ADVANCED_FIELDS = [
    ("character_name", "姓名", "角色的名字"),
    ("gender", "性别", "男/女/不限"),
    ("age", "年龄", "角色的年龄"),
    ("identity", "身份/职业", "如: 资深软件工程师、产品经理"),
    ("personality", "性格特征", "如: 严谨细致、幽默风趣、果断直接"),
    ("background", "背景", "教育背景、成长环境等"),
    ("experience", "经历", "重要经历、项目经验等"),
    ("social", "社交关系", "在团队中的角色、与其他人的关系"),
    ("style", "语言风格", "如: 正式专业、口语化、简洁干练"),
    ("values", "价值观/信念", "如: 用户至上、数据驱动、极简主义"),
]

AVATARS_DIR = DATA_DIR / "avatars"
HIDDEN_TEAM_CATEGORIES = {"未分类", "Uncategorized", ""}


def _render_ai_team_creator(model_options: dict, skill_options: list, all_skills: dict) -> None:
    with st.expander("🤖 AI 自动创建团队（推荐）", expanded=True):
        st.caption("用自然语言描述你的需求，AI 自动生成角色、分工、工具配置，并按任务情况决定是否启用并行模式。")
        ai_desc = st.text_area(
            "任务描述",
            placeholder="例如：我需要一个写学术论文的团队，有项目经理负责规划、两个研究员负责写不同章节、一个编辑负责整合和导出PDF...",
            height=100,
            key="ai_team_desc"
        )
        if st.button("🤖 生成团队配置", use_container_width=True, key="ai_gen_team"):
            if ai_desc.strip() and model_options:
                with st.spinner("AI 正在分析需求，生成团队配置..."):
                    result = _ai_generate_team(ai_desc, model_options, skill_options, list(all_skills.values()))
                if result.get("ok"):
                    new_id = f"ai_{uuid.uuid4().hex[:8]}"
                    team_cfg = result["team"]
                    team_cfg["id"] = new_id
                    _normalize_ai_team_config(team_cfg, model_options)
                    save_team(team_cfg)
                    st.success(f"✅ 团队 '{team_cfg.get('name', new_id)}' 已创建！{len(team_cfg.get('roles', []))} 个角色。")
                    st.session_state["team_selector"] = new_id
                    with st.expander("📋 查看配置详情"):
                        st.json(team_cfg)
                    st.rerun()
                else:
                    st.error(f"生成失败: {result.get('error', '未知错误')}")
            elif not model_options:
                st.warning("请先在模型配置中添加模型")


def _normalize_ai_team_config(team: dict, model_options: dict) -> dict:
    default_mid = list(model_options.keys())[0] if model_options else ""
    roles = team.get("roles") or []
    normalized_roles = []
    role_names = []
    for idx, role in enumerate(roles):
        if not isinstance(role, dict):
            continue
        role.setdefault("name", f"agent_{idx + 1}")
        role["name"] = str(role.get("name") or f"agent_{idx + 1}").strip() or f"agent_{idx + 1}"
        role_names.append(role["name"])
        if not role.get("model_id"):
            role["model_id"] = default_mid
        role.setdefault("skills", [])
        role.setdefault("avatar", "")
        role.setdefault("advanced", {})
        normalized_roles.append(role)
    team["roles"] = normalized_roles

    chat_style = str(team.get("chat_style", "round")).lower().replace("round_robin", "round")
    if chat_style not in {"round", "parallel"}:
        chat_style = "round"
    team["chat_style"] = chat_style

    if chat_style == "parallel":
        normalized_stages = []
        for idx, stage in enumerate(team.get("parallel_stages") or []):
            if not isinstance(stage, dict):
                continue
            stage_roles = stage.get("roles", [])
            if isinstance(stage_roles, str):
                stage_roles = [stage_roles]
            selected = [name for name in stage_roles if name in role_names]
            if selected:
                normalized_stages.append({
                    "name": stage.get("name") or f"阶段 {idx + 1}",
                    "roles": selected,
                })
        covered = {name for stage in normalized_stages for name in stage["roles"]}
        missing = [name for name in role_names if name not in covered]
        if missing:
            normalized_stages.append({"name": "补充协作", "roles": missing})
        team["parallel_stages"] = normalized_stages or [{"name": "并行执行", "roles": role_names}]
    else:
        team["parallel_stages"] = []

    return team


def render_teams_tab() -> None:
    st.header("👥 Agent 团队管理")
    st.caption("推荐使用 AI 自动创建团队：描述需求后自动生成角色、工具和协作流程。已有团队也可以用 AI 匹配快速选择。")

    teams_data = list_teams()
    teams = {
        t["id"]: t for t in teams_data
        if t.get("category", "未分类") not in HIDDEN_TEAM_CATEGORIES
    }
    models_data = list_models()
    model_options = {m["id"]: f"{m['name']} ({m['model']})" for m in models_data}
    if not model_options:
        model_options[""] = "(请先在模型配置中添加模型)"

    # Pre-load skills for AI team generator and role editor
    registry = get_registry()
    all_skills = registry.list_all()
    skill_options = list(all_skills.keys())

    _render_ai_team_creator(model_options, skill_options, all_skills)

    # ── AI 自动匹配团队 ──
    with st.expander("🤖 AI 匹配团队", expanded=False):
        st.caption("输入任务描述，AI 从已有团队中推荐最合适的 1-3 个。")
        ai_match_desc = st.text_area(
            "任务描述",
            placeholder="描述你的任务需求，AI 会推荐最匹配的团队...",
            height=80,
            key="ai_match_desc"
        )
        ai_match_btn_col, _ = st.columns([1, 2])
        with ai_match_btn_col:
            if st.button("🤖 匹配团队", use_container_width=True, key="ai_match_btn"):
                if not ai_match_desc.strip():
                    st.warning("请输入任务描述")
                elif not model_options:
                    st.warning("请先在模型配置中添加模型")
                else:
                    with st.spinner("AI 正在分析任务，匹配合适的团队..."):
                        try:
                            result = _ai_match_team(ai_match_desc, teams)
                            st.session_state["ai_match_result"] = result
                        except Exception as e:
                            st.error(f"匹配失败: {e}")

        if "ai_match_result" in st.session_state and st.session_state["ai_match_result"]:
            r = st.session_state["ai_match_result"]
            if r.get("matches"):
                st.markdown("**🎯 推荐团队：**")
                for m in r["matches"]:
                    tid = m["id"]
                    tname = m.get("name", tid)
                    reason = m.get("reason", "")
                    with st.container(border=True):
                        mc1, mc2 = st.columns([3, 1])
                        with mc1:
                            st.markdown(f"**{tname}**")
                            if reason:
                                st.caption(f"💡 {reason}")
                        with mc2:
                            if st.button("✅ 选择", key=f"match_sel_{tid}", use_container_width=True):
                                st.session_state["team_selector"] = tid
                                st.session_state["_chat_team_id"] = tid
                                st.session_state["_chat_cat"] = teams[tid].get("category", "")
                                st.session_state["active_tab"] = "💬 对话"
                                st.rerun()
            if r.get("suggestion"):
                st.info(r["suggestion"])
    
    st.divider()
    st.caption("创建和管理 Agent 团队，自定义角色、工具、协作模式。勾什么工具就能用什么工具。")

    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("团队列表")
        cat_map = dict(CATEGORIES)
        cat_map.setdefault("并发工作", "⚡")

        all_cats = sorted(set(cat_map.keys()) | set(
            t.get("category", "团队协作") for t in teams.values()
        ) - HIDDEN_TEAM_CATEGORIES)
        cat_filter = st.selectbox("分类筛选", ["全部"] + all_cats, key="team_cat_filter")

        grouped: dict[str, list] = {}
        for tid, t in teams.items():
            cat = t.get("category", "团队协作")
            if cat in HIDDEN_TEAM_CATEGORIES:
                continue
            if cat_filter == "全部" or cat == cat_filter:
                grouped.setdefault(cat, []).append((tid, t))

        for cat in sorted(grouped.keys()):
            cat_teams = grouped[cat]
            with st.expander(f"{cat_map.get(cat, '📁')} {cat} ({len(cat_teams)})",
                             expanded=cat_filter != "全部" or len(grouped) <= 3):
                for tid, t in cat_teams:
                    desc = t.get("desc", "")
                    label = f"{t.get('name', tid)}"
                    if desc:
                        label += f" — {desc[:40]}"
                    if st.button(label, key=f"sel_team_{tid}", use_container_width=True):
                        st.session_state["team_selector"] = tid
                        st.rerun()

        selected_team_id = st.session_state.get("team_selector", None)

        if st.button("➕ 新建团队", use_container_width=True):
            new_id = f"team_{str(uuid.uuid4())[:6]}"
            teams[new_id] = {
                "id": new_id, "name": "新团队", "category": "团队协作",
                "roles": [], "chat_style": "round", "max_turns": 10,
                "parallel_stages": [],
            }
            save_team(teams[new_id])
            st.rerun()

        with st.expander("📥 导入预设团队", expanded=False):
            for cat, preset_list in PRESET_TEAMS.items():
                st.markdown(f"**{cat_map.get(cat, cat)}**")
                for pt in preset_list:
                    if st.button(f"{pt['name']} — {pt.get('desc', '')}", key=f"import_{pt['id']}"):
                        if pt["id"] not in teams:
                            # Auto-bind default model to roles without model_id
                            default_mid = list(model_options.keys())[0] if model_options else ""
                            imported = {
                                "id": pt["id"], "name": pt["name"],
                                "desc": pt.get("desc", ""), "category": cat,
                                "roles": [
                                    {**r, "model_id": r.get("model_id") or default_mid,
                                     "skills": r.get("skills", []),
                                     "advanced": r.get("advanced", {}), "avatar": ""}
                                    for r in pt["roles"]
                                ],
                                "chat_style": (pt.get("chat_style") or pt.get("mode")
                                              or "round").replace("round_robin", "round"),
                                "max_turns": pt.get("max_turns", 6),
                                "parallel_stages": pt.get("parallel_stages", []),
                            }
                            teams[pt["id"]] = imported
                            save_team(imported)
                            st.success(f"已导入 {pt['name']}")
                            st.rerun()
                        else:
                            st.info("已存在")

    with c2:
        if selected_team_id and selected_team_id in teams:
            team = teams[selected_team_id]
            st.subheader(f"编辑: {team.get('name', selected_team_id)}")

            c_name, c_cat, c_style, c_turns = st.columns([2, 1.5, 1.5, 1])
            with c_name:
                team["name"] = st.text_input("团队名称", value=team.get("name", ""),
                                             key=f"team_name_{selected_team_id}")
            with c_cat:
                cat_list = list(cat_map.keys())
                cur_cat = team.get("category", "未分类")
                if cur_cat in HIDDEN_TEAM_CATEGORIES:
                    cur_cat = "团队协作" if "团队协作" in cat_list else cat_list[0]
                team["category"] = st.selectbox(
                    "分类", cat_list,
                    index=cat_list.index(cur_cat) if cur_cat in cat_list else 0,
                    key=f"cat_{selected_team_id}",
                )
            with c_style:
                style_options = ["round", "free", "parallel"]
                style_map = {"round_robin": "round"}
                current_style = team.get("chat_style", "round")
                current_style = style_map.get(current_style, current_style)
                if current_style not in style_options:
                    current_style = "round"
                team["chat_style"] = st.selectbox(
                    "对话模式", style_options,
                    index=style_options.index(current_style),
                    format_func=lambda s: {"round": "🔄 一轮一轮", "free": "💬 自由对话", "parallel": "⚡ 并发协作"}[s],
                    key=f"chatstyle_{selected_team_id}",
                )
            with c_turns:
                team["max_turns"] = st.slider("最大轮数", 2, 200,
                                              int(team.get("max_turns", 10)),
                                              key=f"turns_{selected_team_id}")

            st.divider()
            st.caption("Agent 角色 (勾什么工具就能用什么工具)")

            roles = team.get("roles", [])

            for i, role in enumerate(roles):
                with st.container():
                    rc1, rc2, rc3, rc4 = st.columns([1.5, 2, 1.5, 0.5])
                    with rc1:
                        role["name"] = st.text_input("角色名", value=role.get("name", ""),
                                                     key=f"role_name_{selected_team_id}_{i}")
                    with rc2:
                        role["prompt"] = st.text_area("System Prompt", value=role.get("prompt", ""),
                                                      key=f"role_prompt_{selected_team_id}_{i}", height=80)
                    with rc3:
                        mid = role.get("model_id", "")
                        role["model_id"] = st.selectbox(
                            "模型", list(model_options.keys()),
                            index=list(model_options.keys()).index(mid) if mid in model_options else 0,
                            format_func=lambda x: model_options.get(x, x),
                            key=f"role_model_{selected_team_id}_{i}",
                        )
                    with rc4:
                        if st.button("🗑", key=f"del_role_{selected_team_id}_{i}"):
                            roles.pop(i)
                            team["roles"] = roles
                            save_team(team)
                            st.rerun()

                    current_skills = role.get("skills", [])
                    role["skills"] = st.multiselect(
                        "🛠 技能/工具 (勾什么就能用什么)",
                        skill_options,
                        default=[s for s in current_skills if s in skill_options],
                        format_func=lambda x: f"{all_skills[x].name} — {all_skills[x].desc[:50]}",
                        key=f"role_skills_{selected_team_id}_{i}",
                    )

                    # ── Advanced role settings ──
                    with st.expander(f"🔧 {role.get('name','?')} 高级设定", expanded=False):
                        _render_avatar_picker(role, selected_team_id, i, team, teams)

                        st.divider()
                        st.markdown("**📝 角色高级设定**")
                        advanced = role.get("advanced", {})
                        adv_cols = st.columns(2)
                        for j, (key, label, hint) in enumerate(ROLE_ADVANCED_FIELDS):
                            with adv_cols[j % 2]:
                                advanced[key] = st.text_input(
                                    f"{label}", value=advanced.get(key, ""),
                                    placeholder=hint,
                                    key=f"adv_{key}_{selected_team_id}_{i}",
                                )
                        role["advanced"] = advanced

            if st.button("➕ 添加角色", key=f"add_role_{selected_team_id}"):
                default_mid = list(model_options.keys())[0] if model_options else ""
                roles.append({
                    "name": f"agent_{len(roles)+1}", "prompt": "你是一个有用的助手。",
                    "model_id": default_mid,
                    "skills": [], "avatar": "", "advanced": {},
                })
                team["roles"] = roles
                save_team(team)
                st.rerun()

            # Parallel stages
            if team.get("chat_style") == "parallel":
                st.divider()
                st.markdown("**⚡ 并发阶段编排**")
                role_names_list = [r.get("name", "") for r in roles if r.get("name")]
                stages = team.get("parallel_stages") or [{"name": "阶段 1", "roles": role_names_list}]
                new_stages = []
                for si, stage in enumerate(stages):
                    with st.container(border=True):
                        sc1, sc2, sc3 = st.columns([1.3, 3, 0.6])
                        with sc1:
                            sn = st.text_input("阶段名", value=stage.get("name", f"阶段 {si+1}"),
                                              key=f"stage_name_{selected_team_id}_{si}")
                        with sc2:
                            sr = st.multiselect("并发角色", role_names_list,
                                               default=[r for r in stage.get("roles", []) if r in role_names_list],
                                               key=f"stage_roles_{selected_team_id}_{si}")
                        with sc3:
                            drop = st.button("删除", key=f"drop_stage_{selected_team_id}_{si}")
                        if not drop and sr:
                            new_stages.append({"name": sn or f"阶段 {si+1}", "roles": sr})
                if st.button("添加阶段", key=f"add_stage_{selected_team_id}"):
                    new_stages.append({"name": f"阶段 {len(new_stages)+1}", "roles": []})
                team["parallel_stages"] = new_stages

            st.divider()
            if st.button("💾 保存团队", use_container_width=True, key=f"save_team_{selected_team_id}"):
                team["roles"] = roles
                save_team(team)
                st.success("团队已保存!")

            if st.button("🗑 删除此团队", key=f"delete_team_{selected_team_id}"):
                delete_team(selected_team_id)
                st.rerun()


def _render_avatar_picker(role: dict, selected_team_id: str, i: int, team: dict, teams: dict) -> None:
    """Render avatar/emoji picker for a role."""
    st.markdown("**🎭 头像/图标**")
    cur_avatar = role.get("avatar", "")

    av_c1, av_c2 = st.columns([1, 3])
    with av_c1:
        if cur_avatar:
            st.markdown(f"### {cur_avatar}")
        else:
            st.markdown(f"### {AGENT_AVATARS[i % len(AGENT_AVATARS)]}")
    with av_c2:
        emoji_input = st.text_input(
            "输入表情符号", value=cur_avatar if cur_avatar else "",
            placeholder="直接粘贴表情，如 🤖",
            key=f"emoji_{selected_team_id}_{i}",
        )
        if emoji_input and emoji_input != cur_avatar:
            role["avatar"] = emoji_input.strip()

        uploaded = st.file_uploader(
            "或上传图片", type=["png", "jpg", "jpeg", "gif", "webp"],
            key=f"avup_{selected_team_id}_{i}",
            label_visibility="collapsed",
        )
        if uploaded:
            raw = uploaded.getvalue()
            digest = hashlib.sha256(raw).hexdigest()
            AVATARS_DIR.mkdir(parents=True, exist_ok=True)
            ext = Path(uploaded.name).suffix.lower() or ".png"
            save_name = f"avatar_{selected_team_id}_{i}_{digest[:12]}{ext}"
            save_path = AVATARS_DIR / save_name
            if not save_path.exists():
                save_path.write_bytes(raw)
            role["avatar"] = f"image:avatars/{save_name}"
            team["roles"] = team.get("roles", [])
            save_team(team)
            st.rerun()

    # Emoji grid
    st.markdown("**选择表情图标:**")
    emoji_cols = st.columns(14)
    for ei, emoji in enumerate(AVATAR_EMOJIS):
        with emoji_cols[ei % 14]:
            if st.button(emoji, key=f"avemoji_{selected_team_id}_{i}_{ei}",
                        help=emoji, use_container_width=True):
                role["avatar"] = emoji
                team["roles"] = team.get("roles", [])
                save_team(team)
                st.rerun()


# ── AI Team Generator ────────────────────────────────────

def _ai_generate_team(user_desc: str, model_options: dict,
                      skill_ids: list, skill_infos: list) -> dict:
    import json, ssl, os as _os, re
    from urllib.request import Request, urlopen
    from data.model_store import get_default_model, get_model_api_key

    default = get_default_model()
    if not default:
        return {"ok": False, "team": {}, "error": "no default model"}

    api_key = get_model_api_key(default["id"])
    if not api_key:
        return {"ok": False, "team": {}, "error": "no API key"}

    base_url = default.get("base_url", "https://api.deepseek.com")
    model_name = default.get("model", "deepseek-chat")

    tool_list = []
    for sid in skill_ids:
        for si in skill_infos:
            if si.name == sid:
                tool_list.append(f"- {sid}: {si.desc[:60]}")
                break
    tools_text = "\n".join(tool_list[:80])

    prompt = f"""你是一个团队架构师。严格根据用户需求，从可用工具列表中挑选最合适的工具分配给每个角色，并判断是否应该启用并行模式。

## 用户需求
{user_desc}

## 可用工具（ID + 描述）
{tools_text}

    ## 任务
    设计一个Agent团队。每个角色必须从上述工具列表中精挑细选，只选该角色真正需要的工具，不要滥选。
    你必须根据任务结构选择 chat_style：
    - 如果角色之间需要严格前后传递、先计划再执行再整合，使用 "round"
    - 如果多个角色可以同时处理不同子任务，或可以分成“并行收集/并行实现 -> 汇总整合”这样的阶段，使用 "parallel"

### 工具选择原则
- 读文件类（read_file, list_files, search_text, read_many_files, file_info）：给所有需要理解项目/代码的角色
- 写文件类（write_file, write_base64_file, replace_in_file, make_directory）：给需要产出文件的角色
- Shell/Python（terminal, run_script, python, calculator, code_compile, run_tests）：给需要编码/测试的角色
- Web类（web_search, fetch_url, download_file, download_image）：给需要调研/收集资料的角色
- 学术类（academic_project_create, academic_section_save, academic_markdown_save, academic_outline_generate, academic_table_generate, academic_reference_add, citation_check, paper_assets_list, figure_caption_generate, doc_outline_extract）：给论文写作相关角色
- 图表类（chart_line, chart_bar, chart_confusion_matrix, chart_training_curves）：给需要数据可视化的角色
- 导出类（export_docx, export_markdown_pdf, export_latex_article, export_latex_pdf, export_paper_zip）：给需要输出文档的角色
- 项目管理类（contract_write, contract_read, contract_summary, handoff_write, handoff_read, workspace_snapshot, conflict_check）：给PM/协调者角色
- Git类（git_diff, git_status, project_tree_summary, dependency_scan）：给需要了解项目结构的角色
- 环境类（env_check, env_install）：给可能需要安装依赖的角色
- 文本类（text, json）：通用，可分配给所有角色

### 团队协作原则（非常重要）
每个角色的 prompt 中必须包含一个"团队协作"段落，格式如下：
```
## 团队协作
你所在的团队有N名成员：
- {{role_id_1}}（角色名）：负责什么、有什么工具、产出什么
- {{role_id_2}}（角色名）：负责什么、有什么工具、产出什么
...
你的职责是：具体的要求
你将接收来自谁的消息、向谁交付
```
每个角色必须清楚知道：谁做前面的事、谁做后面的事、自己能做什么、不能做什么、不要抢别人的活。

    ### chat_style 与 parallel_stages 选择指南
    - round：角色之间有严格的前后依赖、需要轮流传球（如PM分配→研究员执行→编辑整合→导出）
    - parallel：多个角色可以在同一阶段同时工作（如多个研究人员查不同方向、多个工程师改不同模块、多个分析师从不同角度评估）
    - parallel_stages 是并行模式的阶段编排：阶段按数组顺序执行；同一阶段 roles 里的角色会并行执行；roles 必须精确匹配 roles 数组中的角色 name
    - 如果 chat_style 是 "parallel"，parallel_stages 必须至少包含1个阶段，并尽量覆盖所有角色
    - 如果 chat_style 是 "round"，parallel_stages 必须是 []
    - 典型并行阶段：
      1) "任务拆解"：pm/lead 单独拆解
      2) "并行执行"：researcher_a、researcher_b、developer_a、developer_b 等同时处理不同子任务
      3) "整合交付"：editor/reviewer/integrator 汇总、审查、导出

### 角色高级设定（advanced字段，可选——一般不用填）
每个角色可以有一个可选的 advanced 对象，包含以下字段（填""表示不设置）：
character_name（姓名）、gender（性别）、age（年龄）、identity（身份/职业）、personality（性格特征）、background（背景）、experience（经历）、social（社交关系）、style（语言风格）、values（价值观/信念）
**重要：只有角色有鲜明特色时才填 advanced，一般留空 {{}} 即可。**

    ### 输出格式（严格JSON，不要任何其他文字）
    {{"name":"团队英文ID","desc":"一句话描述","category":"分类","chat_style":"parallel|round","max_turns":6,"parallel_stages":[{{"name":"阶段名","roles":["role_id_1","role_id_2"]}}],"roles":[{{"name":"role_id","prompt":"详细的中文系统提示词——必须包含: 1)角色职责 2)工作流程 3)团队协作段落 4)产出要求","skills":["工具ID"],"model_id":"","advanced":{{}}}}]}}

### 完整示例
如果用户需要"写千山旅游论文的团队"：
    {{"name":"qianshan_paper_team","desc":"千山旅游研究论文写作团队","category":"学术写作","chat_style":"parallel","max_turns":8,"parallel_stages":[{{"name":"规划大纲","roles":["pm"]}},{{"name":"并行资料收集","roles":["researcher_a","researcher_b"]}},{{"name":"整合导出","roles":["editor"]}}],"roles":[{{"name":"pm","prompt":"你是项目经理。\\n## 团队协作\\n你的团队有4名成员：\\n- researcher_a：负责搜索千山旅游背景资料、文化历史\\n- researcher_b：负责搜索千山旅游产业数据、经济影响\\n- editor：负责整合各章节、格式化markdown、导出最终PDF\\n你的职责：规划大纲、分配任务、跟踪进度、最终审核。接收用户需求，向研究人员下发任务，收集成果后交给editor。","skills":["web_search","academic_project_create","academic_outline_generate","contract_write","handoff_write","text"],"model_id":"","advanced":{{}}}},{{"name":"researcher_a","prompt":"你是研究员A，负责文化和背景调查。\\n## 团队协作\\n你的团队有4名成员：\\n- pm：规划大纲、分配任务\\n- researcher_b：负责产业数据和经济影响\\n- editor：整合和导出\\n你的职责：搜索千山的历史文化、地理位置、景点特色等背景资料，产出对应章节。接收pm的任务分配，成果通过academic_section_save保存。","skills":["web_search","fetch_url","academic_section_save","academic_reference_add","text"],"model_id":"","advanced":{{}}}},{{"name":"researcher_b","prompt":"你是研究员B，负责产业数据。\\n## 团队协作\\n你的团队有4名成员：\\n- pm：规划大纲、分配任务\\n- researcher_a：负责文化和背景\\n- editor：整合和导出\\n你的职责：搜索千山旅游产业数据、游客量、经济贡献等，绘制图表。接收pm的任务分配。","skills":["web_search","fetch_url","academic_section_save","academic_table_generate","chart_bar","text"],"model_id":"","advanced":{{}}}},{{"name":"editor","prompt":"你是主编，负责整合和排版。\\n## 团队协作\\n你的团队有4名成员：\\n- pm：规划分配任务\\n- researcher_a：文化背景材料\\n- researcher_b：产业数据材料\\n你的职责：收集各研究者产出的章节，统一格式、确保引用完整、检查内容一致性，最终导出PDF和DOCX。","skills":["academic_markdown_save","paper_assets_list","export_markdown_pdf","export_docx","text","read_file"],"model_id":"","advanced":{{}}}}]}}

现在请为用户需求设计团队。只输出JSON。"""

    ctx = ssl.create_default_context()
    if _os.environ.get("GALAXY_SSL_VERIFY", "").lower() == "false":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        req = Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=json.dumps({
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "你是一个精确的团队配置架构师。你只输出符合格式的JSON，不输出任何解释、评论或其他文字。你对工具选择非常严谨——只给每个角色分配其真正需要的工具。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            }).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        resp = urlopen(req, context=ctx, timeout=30)
        data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]

        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if m:
            content = m.group(1)
        else:
            a, b = content.find('{'), content.rfind('}')
            if a >= 0 and b > a:
                content = content[a:b+1]

        team = json.loads(content)
        team.setdefault("desc", "")
        team.setdefault("category", "AI Generated")
        team.setdefault("chat_style", "round")
        team.setdefault("max_turns", 6)
        _normalize_ai_team_config(team, model_options)
        if not team.get("roles"):
            return {"ok": False, "team": {}, "error": "no roles generated"}
        return {"ok": True, "team": team, "error": ""}
    except Exception as e:
        return {"ok": False, "team": {}, "error": str(e)[:200]}


# ── AI Team Matcher ─────────────────────────────────────

def _ai_match_team(user_desc: str, teams: dict) -> dict:
    """Match user task description to existing teams via LLM."""
    import json as _json

    # Build team summary
    team_lines = []
    for tid, t in teams.items():
        name = t.get("name", tid)
        desc = t.get("desc", "")
        category = t.get("category", "未分类")
        roles = [r.get("name", "?") for r in t.get("roles", [])]
        roles_str = ", ".join(roles[:8])
        team_lines.append(f"- {tid}: {name} | 分类:{category} | {desc[:80]} | 角色:{roles_str}")
    teams_text = "\n".join(team_lines)

    prompt = f"""根据任务描述，从已有团队中推荐最合适的1-3个团队。

## 任务描述
{user_desc}

## 已有团队列表
{teams_text}

## 要求
- 如果已有团队都不合适，suggestion字段说明原因并建议使用"AI 自动创建团队"功能
- match_score: 1-10，10分为最匹配

## 输出格式（严格JSON）
{{"matches":[{{"id":"team_id","reason":"一句话推荐理由"}}],"suggestion":"如果没有匹配的团队，这里说明原因并建议使用AI创建团队，否则留空"}}

现在请分析并输出。"""

    return _ai_call_json(prompt, "你是精确的团队匹配分析器。只输出JSON。")
