# FIX_ROUND2.md — 第2轮修复摘要

**日期:** 2026-05-08  
**范围:** 18个中等严重度问题  
**状态:** ✅ 全部修复完成，smoke test 通过

---

## 修复清单

### Data 层 (6项)

| 编号 | 文件 | 问题 | 修复 |
|------|------|------|------|
| **B1** | `data/database.py` | `db_transaction()` 无线程归属检查 | 添加 `_thread_id` 快照，事务提交前检查线程一致性，跨线程抛出 `RuntimeError` |
| **B7** | `data/model_store.py` | keyring 失败静默回退到文件 | `_set_key()` 和 `_get_key()` 在 keyring 失败时打印 `logging.warning` |
| **B8** | `data/model_store.py` | `_get_key()` 使用 `GALAXY_DEFAULT_API_KEY` 全局兜底 | 删除全局 env 兜底，改为返回空字符串。per-model 兜底由 `get_model_api_key()` 处理 |
| **B14** | `data/model_store.py` | `.keys/` 目录权限未设置 | `_save_key_file()` 创建 `.keys/` 后调用 `os.chmod(path, 0o700)` 限制为 owner-only |
| **B15/B16** | `data/run_store.py` | `save_run_state()` 接受任意字符串无校验 | 改为接受 `dict | None` 参数，内部 `json.dumps(default=str)`；添加 500KB 长度限制；`load_run_state()` 解析失败时记录 warning |
| **B20** | `data/session_store.py` | `save_session()` 无校验 | `json.dumps` 添加 `default=str`；添加 2MB 长度限制 |

### Core 层 (10项)

| 编号 | 文件 | 问题 | 修复 |
|------|------|------|------|
| **A2** | `core/agent_factory.py` | `_uses_manual_tool_protocol` 用子串匹配 | 改为精确匹配：`name in MANUAL_TOOL_MODELS` |
| **A9** | `core/agent_factory.py` | `_build_system_prompt` 每个 skill 单独打开 DB 连接 | 循环外打开一次，循环内复用；添加 sid 长度校验 |
| **O6** | `core/orchestrator.py` | `_run_streaming` 用 `type(msg).__name__` 字符串比较 | 改为 `isinstance(msg, ToolCallRequestEvent)` + try/except import 保护 |
| **O10** | `core/orchestrator.py` | `build_tool_specs` 无 hasattr 检查 | 添加 `hasattr(registry, "build_tool_specs")` 检查 |
| **O17** | `core/orchestrator.py` | f-string 注入 `display_name` 破坏 JSON | 使用 `json.dumps()` 转义后注入 |
| **G2** | `core/guard.py` | `git diff` 不检测未跟踪文件 | 同时运行 `git ls-files --others --exclude-standard` 捕获新创建但未 track 的文件 |
| **G5** | `core/guard.py` | 禁止路径检测用 `in` 操作符误匹配 | 改为 `Path(f).name` 精确文件名匹配 |
| **P3** | `core/permission.py` + `config.py` | 危险命令检测可被空格/长参数/别名绕过 | 添加 `" ".join(lowered.split())` 空白归一化；扩展 `DANGEROUS_SHELL_PATTERNS` 覆盖 `--recursive --force`、`format C:`、PowerShell 别名 `ri -r -fo`、Base64 编码命令等 13 个模式 |
| **H3** | `core/handoff.py` | status 枚举值输出对象而非字符串 | 使用 `status_raw.value if hasattr(status_raw, "value") else str(status_raw)` 规范化 |
| **H5** | `core/handoff.py` | 失败 agent 输出未被标记 | 对 failed/blocked/needs_retry 状态的 agent 在标题中添加 `⚠ FAILED/BLOCKED/NEEDS RETRY` 标记 |

### Presets 层 (2项)

| 编号 | 文件 | 问题 | 修复 |
|------|------|------|------|
| **B31** | `presets/skills.py` | 技能内容引用不存在的工具名 `chart_tools`/`figure_tools` | 改为实际注册的工具名：`chart_line`, `chart_bar`, `export_markdown_pdf`, `mermaid_mindmap` |
| **B31** | `presets/skills.py` | `skill_claude_code` 中"运行最小验证"未指定具体工具 | 改为明确的 `code_compile` 检查语法, `run_tests` 执行 pytest |

### Structured Output (1项)

| 编号 | 文件 | 问题 | 修复 |
|------|------|------|------|
| **SO1** | `core/structured_output.py` | fence 大括号正则 `.*?` 可能跨越多个 ``` 块 | 改为 `[^`]*?` 排除反引号，防止跨 fence 匹配 |

---

## 验证

- ✅ `python -c "from data.database import init_db; init_db(); from skills import register_all_skills; register_all_skills()"` → SMOKE OK
- ✅ 所有 12 个修改文件的模块导入测试通过
- ✅ 所有 25 个断言检查通过

## 修改的文件（已 git add）

```
data/database.py        — B1 (thread check)
data/model_store.py     — B7 (keyring warning), B8 (remove global env), B14 (keys dir perms)
data/run_store.py       — B15 (dict param + length limit), B16 (parse error logging)
data/session_store.py   — B20 (default=str + length limit)
core/agent_factory.py   — A2 (exact match), A9 (DB connection reuse)
core/orchestrator.py    — O6 (isinstance), O10 (hasattr), O17 (json escape)
core/guard.py           — G2 (untracked files), G5 (exact filename match)
core/permission.py      — P3 (whitespace normalization)
core/handoff.py         — H3 (status enum), H5 (mark failed agents)
core/structured_output.py — SO1 (fence regex)
config.py               — P3 (expanded dangerous shell patterns)
presets/skills.py       — B31 (tool name consistency)
```
