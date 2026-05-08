"""Models tab — manage model configurations, capabilities, guard/multimodal models."""

from __future__ import annotations

import uuid

import streamlit as st

from data.model_store import (
    list_models, save_model, delete_model, set_default_model,
    get_model_api_key, get_model_usage,
)
from data.database import get_db, db_transaction
from presets.models import PRESET_MODELS


def render_models_tab() -> None:
    st.header("🔑 模型配置")
    st.caption("管理你的模型。API Key 加密存储在系统密钥环中。")

    models = list_models()
    tab1, tab2, tab3, tab4 = st.tabs(["📋 已保存", "➕ 预设", "🆕 自定义", "📊 用量统计"])

    with tab1:
        if not models:
            st.info("还没有模型，从预设中添加或新建")
        else:
            for m in models:
                mid = m["id"]
                caps = m.get("capabilities", {})
                with st.expander(
                    f"{m['name']} — `{m['model']}` — {m.get('base_url','')[:50]}",
                    expanded=False,
                ):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        ctx = st.number_input(
                            "上下文长度", min_value=1024, max_value=2_000_000,
                            value=int(m.get("context_length", 128000)), step=1024,
                            key=f"ctx_{mid}",
                        )
                    with c2:
                        if st.button("⭐ 默认", key=f"def_{mid}"):
                            set_default_model(mid)
                            st.rerun()
                    with c3:
                        if st.button("🗑", key=f"del_{mid}"):
                            delete_model(mid)
                            st.rerun()

                    # Capabilities
                    cap_options = ["vision", "long_context", "reasoning", "coding", "fast", "cheap", "tool_calling"]
                    selected = [c for c in cap_options if caps.get(c)]
                    new_caps = st.multiselect(
                        "能力标签", cap_options, default=selected,
                        key=f"caps_{mid}",
                        help="仅用于团队配置时提示模型能力。",
                    )
                    caps_dict = {c: c in new_caps for c in cap_options}

                    # API Key
                    current_key = get_model_api_key(mid)
                    new_key = st.text_input(
                        "API Key", value="", type="password",
                        key=f"key_{mid}",
                        placeholder="输入新 Key 覆盖，留空不修改" + (" (已存储)" if current_key else ""),
                    )
                    c4, c5 = st.columns([1, 3])
                    with c4:
                        if st.button("💾 保存", key=f"save_{mid}", use_container_width=True):
                            save_model(
                                mid, m["name"], m["model"], m.get("base_url", ""),
                                new_key or current_key, ctx,
                                capabilities=caps_dict,
                                is_default=m.get("is_default", False),
                            )
                            st.success("已保存")

    with tab2:
        st.caption("选择一个预设模型添加。API Key 稍后填入。")
        for p in PRESET_MODELS:
            with st.expander(f"{p['name']} — `{p['model']}` — {p['desc']}"):
                api_key = st.text_input("API Key", type="password", key=f"preset_key_{p['name']}")
                ctx_len = st.number_input("上下文长度", value=p.get("context_length", 128000),
                                          min_value=1024, max_value=2_000_000, step=1024,
                                          key=f"preset_ctx_{p['name']}")
                if st.button("➕ 添加", key=f"add_preset_{p['name']}"):
                    mid = str(uuid.uuid4())[:8]
                    save_model(mid, p["name"], p["model"], p["base_url"],
                              api_key, ctx_len,
                              capabilities=p.get("capabilities", {}))
                    st.success(f"已添加 {p['name']}")
                    st.rerun()

    with tab3:
        with st.form("add_custom_model"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("显示名称", placeholder="如: 我的 DeepSeek")
                model_name = st.text_input("模型名", placeholder="如: deepseek-v4-pro")
            with c2:
                api_key = st.text_input("API Key", type="password")
                base_url = st.text_input("Base URL", placeholder="https://api.deepseek.com")
                ctx_len = st.number_input("上下文长度", min_value=1024, max_value=2_000_000, value=64000)
            if st.form_submit_button("💾 保存", use_container_width=True):
                if not name or not model_name:
                    st.error("请填写名称和模型名")
                else:
                    mid = str(uuid.uuid4())[:8]
                    save_model(mid, name, model_name, base_url, api_key, ctx_len)
                    st.success("保存成功!")
                    st.rerun()

    with tab4:
        usage = get_model_usage()
        if not usage:
            st.info("还没有模型调用记录。开始聊天后会自动统计。")
        else:
            total_calls = sum(u.get("calls", 0) for u in usage)
            total_tokens = sum(u.get("total_tokens_est", 0) for u in usage)
            m1, m2 = st.columns(2)
            m1.metric("调用次数", total_calls)
            m2.metric("估算总 tokens", f"{total_tokens:,}")
            st.dataframe([
                {
                    "模型": u.get("name", u.get("model_name", "")),
                    "调用": u.get("calls", 0),
                    "输入估算": u.get("input_tokens_est", 0),
                    "输出估算": u.get("output_tokens_est", 0),
                    "总估算": u.get("total_tokens_est", 0),
                    "最近使用": u.get("last_used", ""),
                }
                for u in usage
            ], use_container_width=True, hide_index=True)

    # ── Guard / Multimodal model settings ──
    st.divider()
    st.subheader("💰 余额查询")
    if st.button("🔍 查询所有模型余额", use_container_width=True):
        from core.balance import get_balance_for_all_models
        with st.spinner("查询中..."):
            results = get_balance_for_all_models()
        if not results:
            st.info("没有配置模型或查询失败")
        else:
            for r in results:
                status = "✅" if r.get("ok") else "❌"
                if r.get("ok"):
                    currency = r.get("currency", "")
                    topup = r.get("topup_balance", "")
                    granted = r.get("granted_balance", "")
                    detail = f"总额: {r['balance']} {currency}"
                    if topup:
                        detail += f" | 充值: {topup}"
                    if granted:
                        detail += f" | 赠送: {granted}"
                    st.success(f"{status} **{r['name']}** — {detail}")
                else:
                    st.error(f"{status} **{r['name']}** — {r.get('error', '查询失败')}")

    st.divider()
    st.subheader("⚙️ 特殊模型设置")

    settings = _get_app_settings()
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**🛡 Guard 审查模型**")
        st.caption("用于 LLM-as-Judge 深度审查 Agent 输出质量（可选）")
        guard_mid = settings.get("guard_model_id", "")
        guard_options = {m["id"]: f"{m['name']} ({m['model']})" for m in models}
        guard_options[""] = "(不使用 LLM Guard)"
        guard_selected = st.selectbox(
            "Guard 模型", list(guard_options.keys()),
            index=list(guard_options.keys()).index(guard_mid) if guard_mid in guard_options else 0,
            format_func=lambda x: guard_options[x],
            key="guard_model_sel",
        )
        if guard_selected != guard_mid:
            _set_app_setting("guard_model_id", guard_selected)
            st.success("已设置")

    with g2:
        st.markdown("**👁 多模态视觉模型**")
        st.caption("上传图片时先由此模型做 OCR/描述，再交给语言模型（可选）")
        vision_mid = settings.get("vision_model_id", "")
        vision_options = {m["id"]: f"{m['name']} ({m['model']})" for m in models}
        vision_options[""] = "(不启用多模态管道)"
        vision_selected = st.selectbox(
            "视觉模型", list(vision_options.keys()),
            index=list(vision_options.keys()).index(vision_mid) if vision_mid in vision_options else 0,
            format_func=lambda x: vision_options[x],
            key="vision_model_sel",
        )
        if vision_selected != vision_mid:
            _set_app_setting("vision_model_id", vision_selected)
            st.success("已设置")


def _get_app_settings() -> dict:
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def _set_app_setting(key: str, value: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
