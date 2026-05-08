# Galaxy New — R2 安全加固修改摘要

**日期**: 2026-05-08  
**原则**: 只加固不改功能，所有修改通过 smoke test

---

## 1. ✅ 请求级错误重试 — `skills/builtin/web.py`

为 `tool_web_search` 和 `tool_fetch_url` 添加指数退避重试机制：

- 新增 `_retry_with_backoff(fn, max_retries=3, base_delay=1.0)` 通用重试辅助函数
- `tool_fetch_url`: 整个 fetch 操作包裹在 3 次重试中（间隔 1s/2s/4s）
- `tool_web_search`: DuckDuckGo 和 Bing 搜索各独立重试 3 次；页面抓取重试 2 次（间隔 0.5s/1s）
- 重试失败后抛出最后一次异常，由外层 try/except 捕获返回错误信息

---

## 2. ✅ 路径穿越防护 — `skills/builtin/file_ops.py`

在 `_safe_workspace_path()` 中添加两层防护：

1. **拒绝 `..` 路径**: 将路径中反斜杠统一为正斜杠，检查是否包含 `..`，如果包含则抛出 `ValueError("Path traversal blocked: '..' not allowed in path")`
2. **resolve 后检查**: 保持原有的 `Path.resolve()` 后 `root in candidate.parents` 检查

覆盖所有使用 `_safe_workspace_path` 的工具：`read_file`, `write_file`, `write_base64_file`, `list_files`, `search_text`, `read_many_files`, `replace_in_file`, `file_info`, `make_directory`, `safe_delete`

---

## 3. ✅ 工具调用日志 — `core/orchestrator.py`

在 `_run_agent_to_text()` 中添加工具调用日志记录：

- 在收集 agent 输出的同时，检测以 `[TOOL]` 开头的流式输出块
- 将检测到的工具调用标记写入 `tool_logs` 表（`run_id`, `agent_name`, `tool_name`, `args_preview`, `timestamp`）
- 新增 `import datetime` 已在模块顶部存在
- 日志写入为 best-effort，失败不中断编排流程

---

## 4. ✅ 危险命令检测增强 — `config.py`

扩展 `DANGEROUS_SHELL_PATTERNS` 列表，新增以下检测模式：

| 模式 | 说明 |
|------|------|
| `regedit` | 注册表编辑器 |
| `Invoke-WebRequest.*-OutFile` | PowerShell 加密下载 |
| `IWR.*-OutFile` | PowerShell 下载别名 |
| `sc stop`, `sc delete` | Windows 服务控制 |
| `net stop` | Windows 服务停止 |
| `schtasks` | 计划任务操作 |
| `-(enc\|e)(odedcommand)?` | Base64 编码命令（统一 -EncodedCommand, -enc, -e 三种形式） |

原有的 `reg\s+(delete\|add)` 和 Base64 检测模式也做了微调优化。

---

## 5. ✅ Export 工具超时保护 — `skills/builtin/export.py`

`tool_export_markdown_pdf` 的 weasyprint 导出改为 subprocess 方式：

- **Method 1**（新）: 将 weasyprint 渲染放在独立子进程中执行，设置 60 秒超时
  - 超时后自动 `except subprocess.TimeoutExpired`，降级到 Method 1b
  - 成功时直接返回 JSON 结果
- **Method 1b**（保留）: 直接 import weasyprint 的原有逻辑，作为 subprocess 方案的 fallback
- **Method 2**（保留）: reportlab 回退逻辑不变

---

## 6. ✅ init_db 表完整性 — `data/database.py`

检查确认 `init_db()` 已包含：
- `custom_tools` 表 ✅ (第 159 行)
- `custom_skills` 表 ✅ (第 119 行)

无需修改。

---

## 验证结果

```bash
$ python -c "import sys;sys.path.insert(0,'.');from data.database import init_db;init_db();from skills import register_all_skills;register_all_skills();print('SMOKE OK')"
SMOKE OK
```

## 修改的文件

| 文件 | 变更行数 | 说明 |
|------|---------|------|
| `skills/builtin/web.py` | +45/-12 | 指数退避重试 |
| `skills/builtin/file_ops.py` | +4 | 路径穿越防护 |
| `core/orchestrator.py` | +24 | 工具调用日志 |
| `config.py` | +13/-2 | 危险命令检测扩展 |
| `skills/builtin/export.py` | +38/-1 | weasyprint subprocess 超时保护 |

**总计**: 5 个文件，+119 行，-17 行。已 `git add` 暂存，未 commit。
