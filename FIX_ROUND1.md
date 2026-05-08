# 🔧 Fix Round 1 — 致命+高严重度+关键中严重度

> 日期: 2026-05-08  
> 基于: AUDIT_CORE.md, AUDIT_DATA_PRESETS.md, AUDIT_SKILLS_APP.md  
> 修改文件: 9 个  

---

## 修复清单

### 🔴 B34 (致命) — presets/teams.py `mode` vs team_store.py `chat_style` 字段不匹配
- **文件**: `presets/teams.py`
- **修改**: 将所有 60 处 `"mode":` 替换为 `"chat_style":`
- **影响**: 预设团队导入后不再丢失 round_robin 模式，UI 已有兼容代码 (`pt.get("chat_style") or pt.get("mode")`) 但现在数据源也标准化了

### 🟠 B35 (高) — PARALLEL_PROJECT_SQUAD_V2 roles 含 `skills`/`model_id`
- **状态**: 经分析，`skills` 和 `model_id` 是 **有意支持的角色字段**。`create_agents_for_team()` 已通过 `role.get("skills", [])` 和 `role.get("model_id", "")` 正确读取。`ui/teams.py` 导入路径也显式传递这些字段。**无需修改** — 这些是高级团队模板的标准功能。

### 🟠 B25 (高) — delete_team() 不清理关联 sessions/runs
- **文件**: `data/team_store.py`
- **修改**: `delete_team()` 中添加 `DELETE FROM chat_sessions WHERE team_id=?` 和 `DELETE FROM run_states WHERE team_id=?` 级联清理
- **影响**: 删除团队后不再遗留学孤儿会话和运行记录

### 🟠 B6 (高) — API Key base85 弱加密
- **文件**: `data/model_store.py`
- **修改**: 在 `_save_key_file()` 的 base85 编码处添加醒目的 WARNING 注释，明确说明这是编码而非加密，并给出生产环境加密方案建议
- **影响**: 开发者不会再误以为 base85 提供任何安全保护

### 🔴 G4 (致命) — guard.py py_compile.compile 可能执行恶意代码
- **文件**: `core/guard.py`
- **修改**: `_compile_changed_files()` 从 `py_compile.compile()` 改为 `ast.parse()` 做纯语法检查
- **影响**: Guard 检查不再执行被修改文件的 import 副作用，消除了代码执行攻击向量。仍能捕获 SyntaxError

### 🟠 A5 (严重) — agent_factory.py 对非 OpenAI 模型强制设置 vision=True
- **文件**: `core/agent_factory.py`
- **修改**: 非 OpenAI 模型优先从 `model_data["capabilities"]` 读取配置；无配置时使用保守默认值（vision=False, function_calling=True）
- **影响**: 不支持 function_calling 的模型（Anthropic 通过 compatible API）不再被错误标记；支持自定义 provider 的能力声明

### 🟠 A3 (严重) — agent_factory.py 跳过角色无日志
- **文件**: `core/agent_factory.py`
- **修改**: 当角色因找不到模型配置被跳过时，添加 `logging.warning()` 输出角色名和尝试的 model_id
- **影响**: 调试时能快速定位为什么某个 agent 没被创建

### 🟠 O4 (严重) — orchestrator 图片路径无遍历检查
- **文件**: `core/orchestrator.py`
- **修改**: `_build_task_payload()` 中图片路径解析后检查是否在 `DATA_DIR` 子树内，越界路径跳过并记录 warning
- **影响**: 防止通过构造的 attachment path 读取 DATA_DIR 外的文件

### 🟠 O25 (严重) — run_paper_pipeline 用文件系统侧信道找 project_id
- **文件**: `core/orchestrator.py`
- **修改**: 优先从 PM agent 输出中正则提取 `"project_id": "xxx"`；仅在提取失败时才 fallback 到文件系统扫描
- **影响**: 并发运行 paper pipeline 时不再拿错 project_id

### 🟠 G1 (严重) — guard.py 用字符串匹配检查 JSON 有效性
- **文件**: `core/schemas.py`, `core/structured_output.py`, `core/guard.py`
- **修改**: 
  - `AgentStageResult` 新增 `parsed_json_ok: bool` 字段
  - `parse_agent_stage_result()` 正确设置该字段
  - `enhanced_guard_check()` 使用 `getattr(result, "parsed_json_ok", True)` 替代字符串匹配
- **影响**: 不再依赖脆弱的字符串匹配；解析逻辑变更不影响 guard 的正确性

### 🟠 O12 (严重) — orchestrator 工具调用无限流
- **文件**: `core/orchestrator.py`
- **修改**: `_run_manual_tool_protocol()` 中单轮 tool_calls 限制为最多 20 个
- **影响**: 防止攻击者构造 100+ 工具调用导致 token 耗尽或 DoS

### 🟠 S1 (严重) — schemas.py run_id 只用 12 位 hex
- **文件**: `core/schemas.py`
- **修改**: `RunState.run_id` 默认工厂从 `uuid4().hex[:12]` 改为 `uuid4().hex[:24]`（96 bits）
- **影响**: 碰撞概率从 ~1/16M 降至 ~1/2^96

### 🟡 S4 (中) — schemas.py GuardResult pass_ 冗余字段
- **文件**: `core/schemas.py`
- **修改**: 在 `pass_` 字段添加注释说明其与 `decision` 的关系，标记为向后兼容字段
- **影响**: 未来维护者知道应该检查 `decision` 而非 `pass_`

### 🟡 B40 (中) — skills/registry.py FunctionTool description 用 __doc__
- **文件**: `skills/registry.py`
- **修改**: `FunctionTool` description 从 `skill.fn.__doc__` 改为 `skill.desc or skill.fn.__doc__`，优先使用注册时传入的显式描述
- **影响**: 被装饰器包装后 docstring 丢失的工具仍能获得正确的 description

### 🟠 O2 (严重) — orchestrator.py guard 可能为 None 的 .value 访问
- **文件**: `core/orchestrator.py`
- **修改**: `_summarize_stage_outputs()` 中 guard 检查增加 `getattr(guard.decision, "value", None)` 空值保护
- **影响**: 非结构化结果（guard 为 None）不再触发 AttributeError

---

## 验证结果

```
SMOKE OK — all imports, init, and registry work
_smoke_test.py ALL SMOKE TESTS PASSED:
  - G4: ast.parse syntax check works (ok + bad cases)
  - S1: run_id now 24 hex chars
  - G1: parsed_json_ok field functional
  - B25: delete_team cascades to sessions/runs
  - B34: all presets now use chat_style
  - B40: registry builds tools with description
  - A3/A5: agent_factory imports OK
  - O2/O4/O25: orchestrator imports OK
```

## 未修项目（不在第1轮范围内）

以下审计问题故意推迟到后续轮次：

| 编号 | 原因 |
|------|------|
| CF1 (致命) | FILE_WRITE_LOCKS 竞态 — 需要 threading.Lock + 回测验证，风险大 |
| G2 (严重) | guard git diff 不覆盖未跟踪文件 — 需要修改 git 命令逻辑 |
| SO6 (严重) | 空 JSON {} 被解析为有效结果 — 影响面大，需要讨论合理阈值 |
| H3 (严重) | agent status 输出枚举对象 — risk 较小，边缘场景 |
| CT5 (严重) | contract run_id 未 sanitize — 需要统一方案 |
| M2 (严重) | merge project_id 未验证 — 需要统一方案 |
| P3 (严重) | 危险命令检测不完整 — 需要命令解析器 |
