"""One-Person Company tab — office visualization, projects, department management."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from data.company_store import (
    get_company_structure, list_departments, save_department, delete_department,
    list_projects, get_project, save_project, delete_project,
    save_assignment, list_assignments, get_company_setting, set_company_setting,
)
from data.soul_store import list_soul_agents, get_soul_agent
from core.company_workflow import (
    create_company_project, get_project_status,
    ceo_decompose_task, chairman_approve,
)


def render_company_tab() -> None:
    st.header("🏢 一人公司")

    tab_viz, tab_projects, tab_settings = st.tabs([
        "🏢 办公室", "📋 项目管理", "⚙️ 公司设置"
    ])

    with tab_viz:
        _render_office_viz()

    with tab_projects:
        _render_projects()

    with tab_settings:
        _render_company_settings()


def _render_office_viz() -> None:
    """Render the animated office visualization."""
    st.caption("走动汇报 · 办公动画 · 实时状态")

    structure = get_company_structure()

    # Build viz data
    viz_data = _build_viz_data(structure)

    # Read the HTML template
    template_path = Path(__file__).parent / "templates" / "company_viz.html"
    if template_path.exists():
        html_template = template_path.read_text(encoding="utf-8")
        # Inject data
        html_template = html_template.replace(
            "// __VIZ_DATA_PLACEHOLDER__",
            f"const VIZ_DATA = {json.dumps(viz_data, ensure_ascii=False)};"
        )
        components.html(html_template, height=650, scrolling=False)
    else:
        st.warning("公司可视化模板未找到，请创建 ui/templates/company_viz.html")

    # Quick actions
    st.divider()
    st.caption("公司状态总览")

    depts = structure.get("departments", [])
    agents = structure.get("agents", [])

    cols = st.columns(max(len(depts) + 2, 3))
    with cols[0]:
        st.markdown("### 👤 董事长办公室")
        st.caption("我（董事长）")
        st.caption(f"管辖: {len(depts)} 个部门")
        st.caption(f"团队: {len(agents)} 个 Agent")

    # CEO
    ceos = [a for a in agents if a.get("position") == "ceo"]
    with cols[1]:
        if ceos:
            ceo = ceos[0]
            st.markdown(f"### {ceo.get('avatar', '🤖')} 总经理")
            st.caption(ceo.get("name", "未任命"))
            thought = ceo.get("worker_thought", "")
            if thought:
                st.caption(f"💬 _{thought}_")
        else:
            st.markdown("### ❓ 总经理")
            st.caption("未任命 - 请在设置中配置")

    # Departments
    for i, dept in enumerate(depts):
        if i + 2 < len(cols):
            with cols[i + 2]:
                head = dept.get("head_agent")
                head_avatar = head.get("avatar", "❓") if head else "❓"
                head_name = head.get("name", "未指定") if head else "未指定"
                st.markdown(f"### {head_avatar} {dept.get('name','?')}")
                st.caption(f"负责人: {head_name}")
                members = dept.get("members", [])
                if members:
                    member_str = " ".join(m.get("avatar", "🧑‍💻") for m in members[:5])
                    st.caption(f"成员: {member_str}")
                thought = (head or {}).get("worker_thought", "")
                if thought:
                    st.caption(f"💬 _{thought}_")


def _render_projects() -> None:
    st.subheader("📋 项目管理")

    # New project
    with st.expander("➕ 新建项目", expanded=False):
        proj_name = st.text_input("项目名称", key="new_proj_name")
        proj_desc = st.text_area("项目描述", key="new_proj_desc", height=80)

        # Select CEO
        agents = list_soul_agents()
        ceo_options = {a["id"]: f"{a['avatar']} {a['name']}" for a in agents
                      if a.get("position") in ("ceo", "")}
        ceo_sel = st.selectbox(
            "总经理", list(ceo_options.keys()),
            format_func=lambda x: ceo_options.get(x, x),
            key="new_proj_ceo",
        ) if ceo_options else None

        if st.button("创建项目", key="create_proj"):
            if proj_name.strip():
                proj = create_company_project(
                    proj_name.strip(),
                    proj_desc.strip(),
                    ceo_agent_id=ceo_sel or "",
                )
                st.success(f"项目已创建: {proj.get('name', '')}")

                # Auto-decompose task via CEO
                if ceo_sel:
                    with st.spinner("CEO 正在分析任务..."):
                        assignments = ceo_decompose_task(
                            proj["id"], proj_desc.strip(), ceo_sel
                        )
                    if assignments:
                        st.success(f"CEO 已分配任务给 {len(assignments)} 个部门")
            else:
                st.warning("请输入项目名称")

    # Project list
    projects = list_projects()
    if not projects:
        st.info("暂无项目")
        return

    for proj in projects:
        status_emoji = {
            "pending": "⏳", "in_progress": "🔄", "review": "👁",
            "done": "✅", "cancelled": "❌",
        }
        emoji = status_emoji.get(proj.get("status", ""), "❓")

        with st.expander(f"{emoji} {proj.get('name','?')} — {proj.get('status','?')}", expanded=False):
            st.caption(proj.get("description", ""))
            st.caption(f"总经理: {proj.get('ceo_name', proj.get('ceo_agent_id', '未指定'))}")

            # Assignments
            full = get_project_status(proj["id"])
            assignments = full.get("assignments", [])
            if assignments:
                st.markdown("**📋 任务分配：**")
                for a in assignments:
                    a_emoji = {"pending": "⏳", "in_progress": "🔄", "done": "✅"}
                    st.caption(
                        f"{a_emoji.get(a['status'], '❓')} {a.get('agent_avatar','?')} "
                        f"{a.get('agent_name','?')} ← {a.get('from_agent_name','?')}: "
                        f"{a.get('task_description','')[:100]}"
                    )
                    if a.get("report_text"):
                        st.caption(f"   汇报: {a['report_text'][:200]}")

            # Actions
            c1, c2 = st.columns(2)
            with c1:
                if proj["status"] == "review":
                    if st.button("✅ 批准（董事长）", key=f"approve_{proj['id']}"):
                        chairman_approve(proj["id"])
                        st.rerun()
                if proj["status"] == "in_progress":
                    if st.button("📩 模拟CEO汇报", key=f"ceo_report_{proj['id']}"):
                        from core.company_workflow import ceo_report_to_chairman
                        ceo_report_to_chairman(proj["id"], "各部门已完成任务，请董事长审阅。")
                        st.rerun()
            with c2:
                if st.button("🗑 删除", key=f"del_proj_{proj['id']}"):
                    delete_project(proj["id"])
                    st.rerun()


def _render_company_settings() -> None:
    st.subheader("⚙️ 公司设置")

    # CEO setting
    agents = list_soul_agents()
    agent_options = {"": "(未设置)"}
    agent_options.update({a["id"]: f"{a['avatar']} {a['name']}" for a in agents})

    current_ceo = get_company_setting("ceo_agent_id", "")
    ceo_sel = st.selectbox(
        "任命总经理 (CEO)",
        list(agent_options.keys()),
        format_func=lambda x: agent_options.get(x, x),
        index=list(agent_options.keys()).index(current_ceo) if current_ceo in agent_options else 0,
        key="company_ceo",
    )
    if ceo_sel != current_ceo:
        set_company_setting("ceo_agent_id", ceo_sel)
        if ceo_sel:
            from data.soul_store import save_soul_agent
            agent = get_soul_agent(ceo_sel)
            if agent:
                save_soul_agent({**agent, "position": "ceo"})
        st.rerun()

    st.divider()

    # Department management
    st.markdown("**🏢 部门管理**")

    depts = list_departments()
    for dept in depts:
        with st.expander(f"{dept.get('name','?')} — 负责人: {dept.get('head_agent_id','未指定')}", expanded=False):
            c1, c2 = st.columns([3, 1])
            with c1:
                new_name = st.text_input("部门名称", value=dept.get("name", ""), key=f"dept_name_{dept['id']}")
                new_desc = st.text_area("描述", value=dept.get("description", ""), height=60, key=f"dept_desc_{dept['id']}")
                # Head selection (only dept_head or unassigned agents)
                head_options = {"": "(未指定)"}
                head_options.update({
                    a["id"]: f"{a['avatar']} {a['name']}"
                    for a in agents
                    if a.get("position") in ("dept_head", "")
                })
                cur_head = dept.get("head_agent_id", "")
                new_head = st.selectbox(
                    "部门负责人",
                    list(head_options.keys()),
                    format_func=lambda x: head_options.get(x, x),
                    index=list(head_options.keys()).index(cur_head) if cur_head in head_options else 0,
                    key=f"dept_head_{dept['id']}",
                )
                if st.button("💾 保存", key=f"save_dept_{dept['id']}"):
                    save_department({"id": dept["id"], "name": new_name, "description": new_desc, "head_agent_id": new_head or None})
                    if new_head:
                        from data.soul_store import save_soul_agent
                        agent = get_soul_agent(new_head)
                        if agent:
                            save_soul_agent({**agent, "position": "dept_head", "department_id": dept["id"]})
                    st.rerun()
            with c2:
                if st.button("🗑 删除", key=f"del_dept_{dept['id']}"):
                    delete_department(dept["id"])
                    st.rerun()

    # Add department
    with st.form("add_dept_form"):
        st.markdown("**➕ 新增部门**")
        new_dept_name = st.text_input("部门名称", key="new_dept_name", placeholder="如: 研发部、市场部、运营部")
        new_dept_desc = st.text_area("描述", key="new_dept_desc", height=60)
        if st.form_submit_button("创建部门"):
            if new_dept_name.strip():
                dept_id = save_department({"name": new_dept_name.strip(), "description": new_dept_desc.strip()})
                st.success(f"部门已创建: {new_dept_name}")
                st.rerun()
            else:
                st.warning("请输入部门名称")


def _build_viz_data(structure: dict) -> dict:
    """Build visualization data for the office HTML."""
    agents = structure.get("agents", [])
    depts = structure.get("departments", [])
    projects = structure.get("projects", [])

    # Determine CEO
    ceo = next((a for a in agents if a.get("position") == "ceo"), None)
    ceo_id = get_company_setting("ceo_agent_id", "")
    if not ceo and ceo_id:
        ceo = get_soul_agent(ceo_id)

    # Active project statuses
    active_proj = next((p for p in projects if p.get("status") in ("pending", "in_progress")), None)
    proj_status = active_proj.get("status", "idle") if active_proj else "idle"

    # Assignments for active project
    assignments = []
    if active_proj:
        assignments = list_assignments(project_id=active_proj["id"])

    # Build office layout
    offices = []

    # Chairman office
    offices.append({
        "id": "chairman",
        "label": "董事长办公室",
        "avatar": "👤",
        "name": "我 (董事长)",
        "thought": "今天公司运转如何？",
        "status": "reviewing" if proj_status == "review" else "idle",
        "position": {"x": 50, "y": 10},
        "type": "chairman",
    })

    # CEO office
    if ceo:
        offices.append({
            "id": ceo.get("id", "ceo"),
            "label": "总经理办公室",
            "avatar": ceo.get("avatar", "🤖"),
            "name": ceo.get("name", "CEO"),
            "thought": ceo.get("worker_thought", ""),
            "status": "working" if proj_status in ("pending", "in_progress") else "idle",
            "position": {"x": 50, "y": 28},
            "type": "ceo",
        })

    # Department offices
    for i, dept in enumerate(depts):
        head = dept.get("head_agent")
        members = dept.get("members", [])
        dept_assign = next((a for a in assignments if a.get("to_agent_id") == dept.get("head_agent_id")), None)

        offices.append({
            "id": dept["id"],
            "label": dept.get("name", "?"),
            "avatar": head.get("avatar", "❓") if head else "❓",
            "name": head.get("name", "未指定") if head else "未指定",
            "thought": (head or {}).get("worker_thought", ""),
            "status": _map_assign_status(dept_assign.get("status") if dept_assign else "idle"),
            "position": {"x": 15 + i * 30, "y": 55},
            "type": "department",
            "members": [{"avatar": m.get("avatar", "🧑‍💻"), "name": m.get("name", "?")}
                       for m in members[:6]],
        })

    # Reporting lines
    reports = []
    if ceo:
        reports.append({"from": "ceo", "to": "chairman", "active": proj_status == "review"})
    for dept in depts:
        if dept.get("head_agent_id"):
            dept_assign = next((a for a in assignments if a.get("to_agent_id") == dept.get("head_agent_id")), None)
            reports.append({
                "from": dept["id"], "to": "ceo",
                "active": dept_assign is not None and dept_assign.get("status") == "done",
            })

    return {
        "offices": offices,
        "reports": reports,
        "project": {
            "name": active_proj.get("name", "") if active_proj else "",
            "status": proj_status,
        },
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }


def _map_assign_status(s: str) -> str:
    return {"pending": "idle", "in_progress": "working", "done": "reporting"}.get(s, "idle")
