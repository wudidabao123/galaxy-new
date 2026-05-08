
"""Skills management tab — view, test, and manage all registered skills."""
from __future__ import annotations
import streamlit as st
import json, ssl, os as _os, re, uuid
from urllib.request import Request, urlopen

from skills.registry import get_registry
from data.database import get_db, db_transaction


# ── Shared AI call helpers ────────────────────────────────────

def _ai_call_json(prompt: str, system: str = "你是精确的JSON生成器，只输出JSON。") -> dict:
    """Call the default LLM, return parsed JSON dict."""
    from data.model_store import get_default_model, get_model_api_key

    default = get_default_model()
    if not default:
        raise RuntimeError("没有配置默认模型")

    api_key = get_model_api_key(default["id"])
    if not api_key:
        raise RuntimeError(f"模型 '{default['name']}' 未配置 API Key")

    base_url = default.get("base_url", "https://api.deepseek.com")
    model_name = default.get("model", "deepseek-chat")

    ctx = ssl.create_default_context()
    if _os.environ.get("GALAXY_SSL_VERIFY", "").lower() == "false":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps({"model": model_name, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ], "temperature": 0.3, "max_tokens": 2048}).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    resp = urlopen(req, context=ctx, timeout=30)
    data = json.loads(resp.read().decode())
    content = data["choices"][0]["message"]["content"]
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if m:
        content = m.group(1)
    return json.loads(content)


def _ai_call_to_text(prompt: str, system: str = "你是一个专业的 AI 助手。",
                     model_id: str = "") -> str:
    """Call an LLM (default or specified), return raw text content."""
    from data.model_store import get_default_model, get_model_api_key, get_model

    if model_id:
        model_cfg = get_model(model_id)
        if not model_cfg:
            raise RuntimeError(f"模型 '{model_id}' 不存在")
    else:
        model_cfg = get_default_model()

    if not model_cfg:
        raise RuntimeError("没有配置默认模型")

    api_key = get_model_api_key(model_cfg["id"])
    if not api_key:
        raise RuntimeError(f"模型 '{model_cfg['name']}' 未配置 API Key")

    base_url = model_cfg.get("base_url", "https://api.deepseek.com")
    model_name = model_cfg.get("model", "deepseek-chat")

    ctx = ssl.create_default_context()
    if _os.environ.get("GALAXY_SSL_VERIFY", "").lower() == "false":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps({"model": model_name, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ], "temperature": 0.5, "max_tokens": 2048}).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    resp = urlopen(req, context=ctx, timeout=30)
    data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def render_skills_tab():
    st.header("🛠️ 工具和技能管理")
    st.caption("🌟 查看、测试和管理所有已注册的工具。自定义 Python 工具可直接注入为 Agent 技能。")
    
    registry = get_registry()
    all_skills = registry.list_all()
    
    from core.tool_manager import list_custom_tools
    custom = list_custom_tools()

    from data.model_store import get_model_usage
    usage = get_model_usage()
    total_calls = sum(u.get("calls", 0) for u in usage) if usage else 0
    
    # Builtin skills grouped by category
    categories = {
        "文件操作": ["read_file", "write_file", "write_base64_file", "list_files",
                     "search_text", "read_many_files", "replace_in_file", "file_info",
                     "make_directory", "safe_delete"],
        "Shell/Python": ["terminal", "run_script", "python", "calculator", "json",
                        "text", "code_compile", "run_tests"],
        "Web": ["current_datetime", "fetch_url", "web_search", "extract_links_from_url",
                "download_file", "download_image"],
        "环境/Git": ["env_check", "env_install", "git_diff", "git_status",
                    "project_tree_summary", "dependency_scan"],
        "Patch/Contract": ["patch_preview", "patch_apply", "patch_reject",
                         "contract_write", "contract_read", "contract_summary",
                         "handoff_write", "handoff_read"],
        "快照": ["workspace_snapshot", "conflict_check", "mermaid_mindmap"],
        "学术论文": ["academic_project_create", "academic_section_save",
                    "academic_markdown_save", "academic_outline_generate",
                    "academic_table_generate", "academic_reference_add",
                    "citation_check", "paper_assets_list", "figure_caption_generate",
                    "doc_outline_extract"],
        "图表": ["chart_line", "chart_bar", "chart_confusion_matrix", "chart_training_curves"],
        "导出": ["export_docx", "export_markdown_pdf", "export_latex_article",
                "export_latex_pdf", "export_paper_zip"],
    }
    
    with st.expander("📊 工具概览", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🚀 已注册", len(all_skills))
        c2.metric("⚡ 自定义", len(custom))
        c3.metric("📞 API调用", total_calls)
        c4.metric("📦 工具分类", len(categories))

    with st.expander("📋 工具", expanded=True):
        for cat_name, cat_ids in categories.items():
            cat_skills = {sid: all_skills.get(sid) for sid in cat_ids if all_skills.get(sid)}
            if not cat_skills:
                continue
            with st.expander(f"📁 {cat_name} ({len(cat_skills)})", expanded=False):
                for sid, skill in cat_skills.items():
                    st.markdown(f"**`{sid}`** — {skill.desc}")
                    st.caption(f"函数: `{skill.fn.__name__}`")

    with st.expander("🔧 创建工具", expanded=False):
        st.subheader("🔧 自定义 Python 工具")
        st.caption("编写 Python 函数作为 Agent 工具。函数名必须是 `run`，接收 dict 参数，返回 str。")
        
        from core.tool_manager import list_custom_tools, save_custom_tool, delete_custom_tool, test_custom_tool
        
        # List existing
        ctools = list_custom_tools()
        if ctools:
            for ct in ctools:
                with st.expander(f"⚡ {ct['name']} — `{ct['id']}`", expanded=False):
                    new_name = st.text_input("名称", value=ct["name"], key=f"ct_name_{ct['id']}")
                    new_desc = st.text_area("描述", value=ct.get("description", ""), key=f"ct_desc_{ct['id']}", height=70)
                    new_code = st.text_area("Python 代码", value=ct.get("code", ""), key=f"ct_code_{ct['id']}", height=200,
                                           help="必须定义 def run(params): 函数")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if st.button("💾 保存", key=f"save_ct_{ct['id']}", use_container_width=True):
                            save_custom_tool(ct['id'], new_name, new_desc, new_code)
                            st.success("已保存")
                            st.rerun()
                    with c2:
                        if st.button("🧪 测试", key=f"test_ct_{ct['id']}", use_container_width=True):
                            result = test_custom_tool(new_code, {"test": "hello"})
                            if result["ok"]:
                                st.success(f"✅ {result['result'][:500]}")
                            else:
                                st.error(f"❌ {result['result'][:500]}")
                    with c3:
                        if st.button("🗑 删除", key=f"del_ct_{ct['id']}", use_container_width=True):
                            delete_custom_tool(ct['id'])
                            st.rerun()
        
        # ── AI 生成工具 ──
        from data.model_store import list_models as _list_models
        _models = _list_models()
        _model_options = {m["id"]: f"{m['name']} ({m['model']})" for m in _models}

        with st.expander("🤖 AI 生成工具", expanded=False):
            st.caption("用自然语言描述你想创建的工具，AI 自动生成 Python 代码。")
            ai_tool_desc = st.text_area(
                "工具描述",
                placeholder="例如：一个工具，输入两个数字返回它们的乘积",
                height=80,
                key="ai_tool_desc"
            )
            ai_tool_model_col, ai_tool_btn_col = st.columns([2, 1])
            with ai_tool_model_col:
                if _model_options:
                    ai_tool_model = st.selectbox(
                        "模型", list(_model_options.keys()),
                        format_func=lambda x: _model_options[x],
                        key="ai_tool_model"
                    )
                else:
                    ai_tool_model = ""
                    st.warning("请先在模型配置中添加模型")
            with ai_tool_btn_col:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🤖 生成代码", use_container_width=True, key="ai_gen_tool_btn"):
                    if not ai_tool_desc.strip():
                        st.warning("请输入工具描述")
                    elif not _model_options:
                        st.warning("请先在模型配置中添加模型")
                    else:
                        with st.spinner("AI 正在生成工具代码..."):
                            try:
                                result = _ai_generate_tool(ai_tool_desc, ai_tool_model)
                                st.session_state["ai_tool_result"] = result
                                st.success("代码已生成，请查看并确认后填入表单")
                            except Exception as e:
                                st.error(f"生成失败: {e}")

            # Show generated result and allow auto-fill
            if "ai_tool_result" in st.session_state and st.session_state["ai_tool_result"]:
                r = st.session_state["ai_tool_result"]
                st.text_area("生成的 Python 代码", value=r.get("code", ""), height=180, key="ai_tool_code_preview")
                st.text_input("工具名称", value=r.get("name", ""), key="ai_tool_name_preview")
                st.text_area("描述", value=r.get("desc", ""), height=70, key="ai_tool_desc_preview")
                if st.button("📋 填入新建表单", use_container_width=True, key="ai_tool_fill"):
                    st.session_state["_ct_name_prefill"] = r.get("name", "")
                    st.session_state["_ct_desc_prefill"] = r.get("desc", "")
                    st.session_state["_ct_code_prefill"] = r.get("code", "")
                    st.rerun()

        # New tool form
        st.divider()
        with st.form("new_custom_tool", clear_on_submit=True):
            st.markdown("**➕ 新建工具**")
            ct_name = st.text_input("工具名称",
                value=st.session_state.pop("_ct_name_prefill", ""),
                key="ct_name_input")
            ct_desc = st.text_area("描述", height=70,
                value=st.session_state.pop("_ct_desc_prefill", ""),
                key="ct_desc_input")
            ct_code = st.text_area("代码", height=180,
                value=st.session_state.pop("_ct_code_prefill", ""),
                placeholder='def run(city: str, days: int = 3) -> str:\n    """Get weather forecast for a city."""\n    return f"Weather for {city}: sunny, {days} days"')
            if st.form_submit_button("创建工具", use_container_width=True):
                if ct_name.strip() and ct_code.strip():
                    tid = save_custom_tool("", ct_name, ct_desc, ct_code)
                    # Register into global registry so agents can use it
                    from core.tool_manager import register_custom_tool_to_registry
                    ok = register_custom_tool_to_registry(tid)
                    if ok:
                        st.success(f"工具 '{ct_name}' 已创建并注册 (ID: {tid})")
                    else:
                        st.error(f"工具保存成功但注册失败，请检查代码是否有 type hints")
                    st.rerun()
                else:
                    st.error("请填写名称和代码")

    with st.expander("📝 技能", expanded=False):
        st.subheader("📝 技能")
        st.caption("自定义知识技能会注入到 Agent 的 System Prompt 中。")

        conn = get_db()
        skills = conn.execute("SELECT * FROM custom_skills ORDER BY name").fetchall()

        if skills:
            for sk in skills:
                with st.expander(f"{sk['name']} — {sk['overview'][:60]}", expanded=False):
                    sk_name = st.text_input("名称", value=sk["name"], key=f"sk_name_{sk['id']}")
                    sk_overview = st.text_area("概述 (界面显示)", value=sk["overview"], height=70,
                                               key=f"sk_overview_{sk['id']}")
                    sk_content = st.text_area("内容 (注入 Prompt)", value=sk["content"], height=220,
                                              key=f"sk_content_{sk['id']}")
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        if st.button("保存", key=f"save_sk_{sk['id']}", use_container_width=True):
                            with db_transaction() as conn2:
                                conn2.execute(
                                    "UPDATE custom_skills SET name=?, overview=?, content=?, "
                                    "updated_at=datetime('now') WHERE id=?",
                                    (sk_name.strip(), sk_overview.strip(), sk_content.strip(), sk["id"]),
                                )
                            st.success("已更新")
                            st.rerun()
                    with c2:
                        if st.button("删除", key=f"del_sk_{sk['id']}", use_container_width=True):
                            with db_transaction() as conn2:
                                conn2.execute("DELETE FROM custom_skills WHERE id=?", (sk["id"],))
                            st.rerun()
        else:
            st.caption("还没有自定义技能")

        from data.model_store import list_models as _list_models
        _models = _list_models()
        _model_options = {m["id"]: f"{m['name']} ({m['model']})" for m in _models}

        with st.expander("🤖 AI 生成技能", expanded=False):
            st.caption("描述你需要的技能，AI 自动生成适用场景、流程、约束和输出格式。")
            ai_skill_desc = st.text_area(
                "技能描述",
                placeholder="例如：一个代码审查技能，检查Python代码的PEP8规范、潜在安全漏洞和性能问题",
                height=80,
                key="ai_skill_desc"
            )
            ai_skill_model_col, ai_skill_btn_col = st.columns([2, 1])
            with ai_skill_model_col:
                if _model_options:
                    ai_skill_model = st.selectbox(
                        "模型", list(_model_options.keys()),
                        format_func=lambda x: _model_options[x],
                        key="ai_skill_model"
                    )
                else:
                    ai_skill_model = ""
                    st.warning("请先在模型配置中添加模型")
            with ai_skill_btn_col:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🤖 生成技能", use_container_width=True, key="ai_gen_skill_btn"):
                    if not ai_skill_desc.strip():
                        st.warning("请输入技能描述")
                    elif not _model_options:
                        st.warning("请先在模型配置中添加模型")
                    else:
                        with st.spinner("AI 正在生成技能定义..."):
                            try:
                                result = _ai_generate_skill(ai_skill_desc, ai_skill_model)
                                st.session_state["ai_skill_result"] = result
                                st.success("技能定义已生成，请查看并确认后填入表单")
                            except Exception as e:
                                st.error(f"生成失败: {e}")

            if "ai_skill_result" in st.session_state and st.session_state["ai_skill_result"]:
                r = st.session_state["ai_skill_result"]
                st.text_input("技能名称", value=r.get("name", ""), key="ai_skill_name_preview")
                st.text_area("概述", value=r.get("overview", ""), height=70, key="ai_skill_overview_preview")
                st.text_area("主要内容", value=r.get("content", ""), height=180, key="ai_skill_content_preview")
                if st.button("📋 填入新建表单", use_container_width=True, key="ai_skill_fill"):
                    st.session_state["_sk_name_prefill"] = r.get("name", "")
                    st.session_state["_sk_overview_prefill"] = r.get("overview", "")
                    st.session_state["_sk_content_prefill"] = r.get("content", "")
                    st.rerun()

        with st.form("add_skill", clear_on_submit=True):
            st.markdown("**➕ 新建技能**")
            sk_name = st.text_input("技能名称", placeholder="如: SQL 查询优化",
                value=st.session_state.pop("_sk_name_prefill", ""),
                key="sk_name_input")
            sk_overview = st.text_area("概述", height=70, placeholder="一句话概述",
                value=st.session_state.pop("_sk_overview_prefill", ""),
                key="sk_overview_input")
            sk_content = st.text_area("主要内容", height=180, placeholder="适用场景、流程、约束、输出格式...",
                value=st.session_state.pop("_sk_content_prefill", ""),
                key="sk_content_input")
            if st.form_submit_button("创建技能", use_container_width=True):
                if sk_name.strip() and sk_content.strip():
                    sk_id = f"custom_{uuid.uuid4().hex[:6]}"
                    with db_transaction() as conn2:
                        conn2.execute(
                            "INSERT INTO custom_skills (id, name, type, overview, content) "
                            "VALUES (?, ?, 'knowledge', ?, ?)",
                            (sk_id, sk_name.strip(), sk_overview.strip(), sk_content.strip()),
                        )
                    st.success(f"技能 '{sk_name}' 已创建!")
                    st.rerun()
                else:
                    st.error("请填写名称和内容")
    
    with st.expander("🧪 测试工具", expanded=False):
        st.subheader("🧪 测试工具")
        st.caption("选择一个工具，输入参数 JSON 进行测试")
        
        test_skill_id = st.selectbox("选择技能", list(all_skills.keys()), 
                                     format_func=lambda x: f"{x} — {all_skills[x].desc}")
        
        if test_skill_id:
            skill = all_skills[test_skill_id]
            import inspect
            sig = inspect.signature(skill.fn)
            params_template = _default_params_json(sig)
            params_text = st.text_area(
                "参数 (JSON)", height=100,
                value=params_template,
                key=f"test_params_{test_skill_id}",
                help=f"函数签名: {sig}"
            )
            
            if st.button("▶️ 执行测试", use_container_width=True):
                try:
                    params = json.loads(params_text) if params_text.strip() else {}
                    result = skill.fn(**params)
                    st.success(f"✅ 执行成功\n```\n{str(result)[:2000]}\n```")
                except json.JSONDecodeError:
                    st.error("JSON 格式错误")
                except Exception as e:
                    st.error(f"❌ 执行错误: {e}")


# ── AI Tool Generator ────────────────────────────────────

def _default_params_json(sig) -> str:
    import inspect

    def value_for(param) -> object:
        if param.default is not inspect._empty:
            return param.default
        annotation = param.annotation
        if annotation is inspect._empty:
            return ""
        annotation_text = getattr(annotation, "__name__", str(annotation)).lower()
        if "bool" in annotation_text:
            return False
        if "int" in annotation_text:
            return 0
        if "float" in annotation_text:
            return 0.0
        if "list" in annotation_text or "tuple" in annotation_text or "set" in annotation_text:
            return []
        if "dict" in annotation_text:
            return {}
        if "path" in annotation_text:
            return "path/to/file"
        return ""

    params = {}
    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        params[name] = value_for(param)
    return json.dumps(params, ensure_ascii=False, indent=2)


def _ai_generate_tool(user_desc: str, model_id: str) -> dict:
    """Generate a custom tool Python function via LLM."""
    from data.model_store import get_model

    model_cfg = get_model(model_id) if model_id else None
    if not model_cfg:
        raise RuntimeError("未找到指定模型")

    prompt = f"""根据用户描述生成一个Python工具函数。

## 用户描述
{user_desc}

## 代码规范（严格遵守）
- 函数名必须是 `run`
- **所有参数必须有 Python type hint**（如 str, int, float, bool, list）
- 返回值类型标注为 -> str
- 参数要有合理的默认值（default value）
- 函数内做参数校验，返回友好的错误信息
- 示例格式: def run(city: str, days: int = 3) -> str:
- 仅输出 JSON，不要任何解释文字

## 输出格式（严格JSON）
{{"name":"工具英文id","desc":"一句话中文描述","code":"完整的Python代码"}}

现在请输出。"""

    raw = _ai_call_to_text(prompt, system="你是精确的Python工具代码生成器。只输出JSON。", model_id=model_id)
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        a, b = raw.find('{'), raw.rfind('}')
        if a >= 0 and b > a:
            raw = raw[a:b+1]
    return json.loads(raw)


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

    raw = _ai_call_to_text(prompt, system="你是专业的Agent技能设计师。只输出JSON格式。", model_id=model_id)
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if m:
        raw = m.group(1)
    else:
        a, b = raw.find('{'), raw.rfind('}')
        if a >= 0 and b > a:
            raw = raw[a:b+1]
    return json.loads(raw)
