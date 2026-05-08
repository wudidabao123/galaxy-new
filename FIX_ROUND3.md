# 🔧 Galaxy New — Round 3 Fix Report

> **日期**: 2026-05-08  
> **范围**: 低严重度问题修复 + 最终打磨  
> **修改文件**: 8 个文件

---

## 已修复问题

### B3 — database.py WAL 无检查点策略
- **文件**: `data/database.py`
- **修复**: `init_db()` 末尾添加 `PRAGMA wal_checkpoint(TRUNCATE)` 调用
- **影响**: 防止长时间运行后 WAL 文件无限增长

### B10 — model_store.py token估算过于粗糙
- **文件**: `data/model_store.py` — `record_model_usage()`
- **修复**: 替换粗糙的 `chars // 3` 估算为 CJK 感知算法
  - 中文 (U+4E00-9FFF) 和日文 (U+3040-30FF) 字符按 ~0.6 tokens/char 计算
  - ASCII/拉丁字符按 ~0.3 tokens/char 计算
  - 混合文本按比例混合双因子
- **验证**: 中文 "你好世界这是一个测试" (10 chars): 旧=3 tokens, 新=6 tokens (更准确)

### B12 — model_store.py delete_model 不清理 model_usage
- **文件**: `data/model_store.py` — `delete_model()`
- **修复**: 添加 `DELETE FROM model_usage WHERE model_id = ?` 清理孤立记录

### B13 — model_store.py set_default_model 对不存在的id静默成功
- **文件**: `data/model_store.py` — `set_default_model()`
- **修复**: 调用前先 `get_model(model_id)` 验证存在，不存在抛 `ValueError`

### B29 — presets/models.py Moonshot只有8K模型
- **文件**: `presets/models.py`
- **修复**: `moonshot-v1-8k` → `moonshot-v1-128k`, context_length: 8000 → 128000

### B30 — presets/models.py 预设缺少capabilities字段
- **文件**: `presets/models.py`
- **修复**: 所有 13 个预设模型均添加 `capabilities` 字段，标注 vision/function_calling/streaming/structured_output 等能力
- **验证**: `all('capabilities' in m for m in PRESET_MODELS)` = True

### B45/B46 — skills/__init__.py mermaid_mindmap 移到 charts.py + 转义
- **文件**: `skills/builtin/charts.py`, `skills/__init__.py`
- **修复**:
  1. `tool_mermaid_mindmap()` 从 `skills/__init__.py` 移到 `skills/builtin/charts.py`
  2. 添加双引号转义防止 Mermaid 语法破坏
  3. 新增 `tool_mermaid_flowchart()` 工具
  4. `skills/__init__.py` 从 charts 导入并注册

### C1 — context.py 和 orchestrator.py 重复函数
- **文件**: `core/orchestrator.py`
- **修复**: 删除 orchestrator 中重复的 `_clip_output()`, `_is_tool_event_chunk()`, `_split_tool_events()`，改为从 `core.context` 导入
- 同时删除未使用的 `_uses_manual_tool_protocol()` (orchestrator直接用 `agent_info["manual_tools"]`)

### O23 — orchestrator.py verify_agent_output 用 config.DATA_DIR
- **文件**: `core/orchestrator.py`
- **修复**: `verify_agent_output()` 中 `from skills.builtin.file_ops import _get_workspace_root` 替换为 `from config import DATA_DIR`
- 同样修复 `run_paper_pipeline()` 和 `direct_paper_export()` 中的两处调用

### O3 — orchestrator.py CommandResult command可能为None
- **文件**: `core/orchestrator.py`
- **修复**: `f"{t.command} => ..."` → `f"{t.command or '(unnamed)'} => ..."` (行82)

### A1 — agent_factory.py _ascii_name fallback唯一性
- **文件**: `core/agent_factory.py`
- **修复**: 
  1. `_ascii_name()` 接受可选 `used_names: set` 参数
  2. fallback 格式从 `f"agent{idx}"` 改为 `f"agent_{idx:03d}"` (保证 0-padding)
  3. 自动检测冲突并追加 `_2`, `_3` 后缀确保唯一性
  4. `create_agents_for_team()` 传递 `used_names` set

### 额外: custom_tools 表加入 init_db
- **文件**: `data/database.py`
- **修复**: `init_db()` 中添加 `CREATE TABLE IF NOT EXISTS custom_tools` (之前只在 `_migrate_iter7.py` 中创建)
- `custom_skills` 表已存在 — 无需额外操作

---

## 验证结果

### 核心功能测试 (全部通过)
```
✅ model_store imports
✅ context imports (no duplicate functions)
✅ preset models (capabilities + Moonshot 128K)
✅ CJK-aware token estimation
✅ database tables (custom_tools, custom_skills, models, teams)
✅ agent _ascii_name uniqueness
✅ set_default_model ValueError validation
✅ delete_model cleans model_usage
✅ mermaid tools in charts.py
✅ orchestrator no duplicate functions
✅ verify_agent_output uses config.DATA_DIR
✅ CommandResult None-safe
```

### E2E 功能测试
```
✅ web_search              — 返回搜索结果
✅ academic_project_create — 创建项目并返回 project_id
✅ academic_section_save   — 保存章节文件
✅ academic_markdown_save  — 函数正常工作(参数名测试脚本修正)
✅ export_markdown_pdf     — 工具注册正确
✅ export_docx             — 工具注册正确
✅ agent_factory           — 中文名唯一性保证
```

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `data/database.py` | B3: WAL checkpoint + custom_tools 表 |
| `data/model_store.py` | B10: CJK token估算 + B12: 清理model_usage + B13: set_default 验证 |
| `presets/models.py` | B29: Moonshot 128K + B30: capabilities 字段 |
| `skills/builtin/charts.py` | B45/B46: mermaid 函数迁移 + 转义 |
| `skills/__init__.py` | B45/B46: 移除内联 mermaid, 从 charts 导入 |
| `core/orchestrator.py` | C1: 去重函数 + O23: DATA_DIR + O3: None-safe + O27: 清理未用import |
| `core/agent_factory.py` | A1: _ascii_name 唯一性 + A2: 精确模型匹配 |

---

## 未修复 (超出本轮范围)

- 临时脚本清理: 项目根目录未找到 `_iter*.py`, `_gen_report*.py`, `_report.py`, `_check_*.py` 等临时文件（可能已在前两轮清理）
- E2E 完整端到端测试需要 Streamlit UI 运行环境 + API Keys + 完整模型配置
