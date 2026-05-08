"""Config tab — project root, soul MD presets, custom skills, advanced settings."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import DATA_DIR
from data.database import get_db, db_transaction
from data.model_store import list_models


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

    # Soul agent management is now in the 灵魂Agent tab (ui/souls.py)


