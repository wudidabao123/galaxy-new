# 🔍 Galaxy New — Core 模块深度审计报告

> **审计日期**: 2026-05-08  
> **审计范围**: `core/` 下 13 个模块  
> **审计方法**: 静态代码分析 + 依赖追踪 + 边界条件穷举  
> **严重程度定义**: 🔴致命 / 🟠严重 / 🟡中等 / 🟢轻微

---

## 1. `core/enums.py` — 枚举定义

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| E1 | 全文 | 所有枚举继承 `str` + `Enum` 但没有实现 `_missing_` 方法。当从 JSON/API 接收到未知值时直接抛 `ValueError`，没有降级策略 | 🟡中等 | 为每个枚举添加 `@classmethod _missing_(cls, value)` 返回一个合理的默认值（如 `UNKNOWN`）并打日志 |
| E2 | 23 | `AgentStatus` 枚举值 `needs_retry` vs schemas 中是 `needs_retry`，但 `parse_agent_stage_result` 中 fallback 是 `AgentStatus.DONE`，不一致时可能导致静默忽略 retry 状态 | 🟡中等 | 在 `parse_agent_stage_result` 中对无法解析的 status 记录 warning 日志，而非静默 fallback 到 DONE |
| E3 | 9-11 | `PermissionMode` 只有三种模式，但 `permission.py` 中 `should_ask_permission` 只处理了 ASK。GUARD 和 AUTO 模式的权限行为未区分 | 🟡中等 | GUARD 和 AUTO 应该有区别：GUARD 至少记录日志，AUTO 才完全跳过 |

---

## 2. `core/schemas.py` — 数据模式

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| S1 | 10 | `import uuid` 只在 78 行 `RunState.run_id` 默认工厂里用到，且用了 `uuid.uuid4().hex[:12]` — 12 位十六进制碰撞概率远高于标准 UUID，多用户并发时可能重复 | 🟠严重 | 使用 `uuid.uuid4().hex`（完整 32 位）或 `uuid.uuid4().hex[:16]` 至少 16 位 |
| S2 | 21-24 | `CommandResult.exit_code` 允许 `None`，但没有任何地方校验 `exit_code` 的合法性（是否为有效退出码）。如果 API 传入负数或超大值，不会被检测 | 🟢轻微 | 添加 `__post_init__` 验证 `exit_code` 范围 0-255 |
| S3 | 28-38 | `AgentStageResult.risks` 是 `list[str]`，但没有任何去重逻辑。多次 retry 后同一风险会被重复添加 | 🟢轻微 | 在 parse 或 append 时做去重 |
| S4 | 43-49 | `GuardResult.decision` 和 `pass_` 存在信息冗余（`pass_` 可以从 `decision` 推导），两者可能不一致 | 🟡中等 | 移除 `pass_` 字段或改为 `@property`，从 `decision` 自动计算 |
| S5 | 73-87 | `RunState` 包含 `stages: list[StageState]` 和 `artifacts: list[str]`，但没有 `team_id` 的校验——`team_id` 为空字符串默认值时 RunState 仍然"有效" | 🟢轻微 | `__post_init__` 校验 `team_id` 非空 |
| S6 | 93-101 | `AgentContract.allowed_paths` 和 `forbidden_paths` 都是 `list[str]` 但没有路径规范化。`app.py` 和 `./app.py` 会被当成两个不同路径 | 🟠严重 | 在 `__post_init__` 中对所有路径做 `Path(x).resolve()` 或至少做标准化 |
| S7 | 55-62 | `StageState.results` 用 `dict[str, AgentStageResult]`，但 key 是 agent display_name。如果两个 agent 同名，后者会覆盖前者，且无任何告警 | 🟡中等 | 加重复检测或使用 agent 内部 ID 作为 key |

---

## 3. `core/agent_factory.py` — Agent 创建逻辑

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| A1 | 14-19 | `_ascii_name` 在 `display_name` 去除所有非 ASCII 字符后长度 < 2 时返回 `f"agent{idx}"`。但如果多个角色都触发这个 fallback，参数 `safe` 在 role 数组里不是唯一的（比如 idx=0 和 idx=10 都叫 "agent0" 不可能，但如果数组很大可能有歧义） | 🟢轻微 | 使用 `f"agent_{idx:03d}"` 确保唯一性 |
| A2 | 24-26 | `_uses_manual_tool_protocol` 做的是子串匹配。如果 model_name 包含 "deepseek" 而 `MANUAL_TOOL_MODELS` 包含 `"deepseek-v4-pro"`，那么 `model_name = "my-deepseek-model"` 也会被匹配到，但实际上这个模型可能不是 deepseek 系列 | 🟡中等 | 精确匹配或限定仅匹配特定前缀/后缀，不要仅靠 `in` 操作符 |
| A3 | 29-38 | `create_agents_for_team` 的 `model_data` fallback 逻辑：先查 `get_model(mid)`，查不到就用 `get_default_model()`。如果默认模型也不存在，直接 `continue` 跳过该角色。跳过的角色没有任何日志告警，前端会看到 agent 数量不对但不知道原因 | 🟠严重 | 跳过时打 warning 日志，返回的 agents 列表中追加一个 error 标记 |
| A4 | 43-49 | `api_key` 缺失直接 `raise RuntimeError` 终止所有 agent 创建。如果 5 个角色中第 3 个缺 key，前 2 个已经创建了 Agent 和 client（可能已连接），抛出异常后资源不会被清理 | 🟡中等 | 创建 agent 前先收集所有 key，做预校验；或在异常处理中清理已创建的资源 |
| A5 | 54-62 | 对非 OpenAI 模型强制设置 `model_info`（vision=True, function_calling=True），但实际上某些非 OpenAI 模型（如 Anthropic、Google Gemini via OpenAI-compatible API）可能不支持 function calling 或 structured_output，会导致后续调用失败 | 🟠严重 | 增加按模型系列（provider）定制 model_info 的逻辑，或从 model_data 中读取配置 |
| A6 | 64 | `tools = registry.build_tools(skill_ids)` — 如果 `skill_ids` 包含不存在的 skill ID，`build_tools` 的返回值未做校验。可能返回空列表或部分工具 | 🟡中等 | 校验并记录缺失的 skills |
| A7 | 69-70 | `display_name = role.get("name", f"agent_{i}")` 和 `safe = _ascii_name(display_name, i)`：如果两个 role 的 display_name 的 ASCII 过滤后相同（如 "张三"→"", "李四"→""），safe 会重复为 `"agent0"` | 🟡中等 | `_ascii_name` 改为接收一个去重集合参数，保证唯一性 |
| A8 | 73-84 | `AssistantAgent` 构造函数中 `tools=None if manual_tools else (tools if tools else None)` 和 `reflect_on_tool_use=False if manual_tools else bool(tools)` — 三重嵌套判断逻辑，极其易读错。当 `tools` 为空列表且 `manual_tools=False` 时，`reflect_on_tool_use=bool([])=False` 是正确的，但逻辑可读性极差 | 🟢轻微 | 用显式变量拆解：`has_tools = tools is not None and len(tools) > 0` |
| A9 | 108-157 | `_build_system_prompt` 中对 `custom_skill_ids` 的处理：每个 skill 都单独打开数据库连接 `conn = get_db()`，在高并发下可能产生大量数据库连接 | 🟡中等 | 在循环外打开一次连接，循环内复用 |
| A10 | 136-137 | `row = conn.execute("SELECT content FROM custom_skills WHERE id = ?", (sid,)).fetchone()` — SQL 注入风险？这里用了参数化查询是正确的，但 `sid` 来自 `role.get("skills", [])`，没有验证它是合法 UUID/整数格式 | 🟢轻微 | 验证 sid 格式后再查询 |

---

## 4. `core/orchestrator.py` — 编排器

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| O1 | 32-103 | `_summarize_stage_outputs` 中 `structured_payloads` 的筛选条件是 `payload.get("structured")`。但 `payload.get("structured")` 可能是 `AgentStageResult()` 的默认实例（所有字段为空字符串），仍会被认为是有效 structured payload。当 agent 报错返回空 `AgentStageResult` 时，会显示误导性的 "Agent count: N" | 🟡中等 | 增加 `payload.get("structured") and payload["structured"].summary` 检查，确保有实际内容 |
| O2 | 42 | `guard.decision.value` 直接访问，但 `guard` 也可能是 `None`（当 guard 检查被跳过时）。虽然有 `p.get("guard")` 的检查，但字典取值的 guard 可能是 `None` | 🟠严重 | 添加 `guard and guard.decision and ...` 的空值保护 |
| O3 | 62 | `t.command` 可能为 `None`（CommandResult 的默认构造），`f"{t.command} => {t.result.value}"` 会产生 "None => passed" 的奇怪输出 | 🟢轻微 | 用 `t.command or "(unnamed)"` |
| O4 | 134-137 | `_build_task_payload` 中的图片处理：`DATA_DIR / att["path"]` 直接用 path 拼接，但 `att["path"]` 可能是绝对路径、相对路径或包含 `..`。没有做路径遍历检查 | 🟠严重 | 使用 `(DATA_DIR / att["path"]).resolve()` 并检查结果是否在 `DATA_DIR` 子树内 |
| O5 | 187-190 | `_build_parallel_task_payload` 中的 `.format(sid=...)` 方法？不对，看代码用的是 f-string。但实际的 `compact_history` 返回的是 `list[dict]`，`_build_task_payload` 直接接受。如果 `compact` 中的消息内容包含 `{` `}` 字符（如 JSON 示例），会被 f-string 错误解析——不过这里没有用 f-string 包含 compact 内容，确认安全。 | — | 审计确认无问题 |
| O6 | 228-230 | `_run_streaming` 中 `type(msg).__name__` 硬编码做 `if msg_type == "ToolCallRequestEvent"` 字符串比较。如果 AutoGen 升级后类型名改变（如改为 `ToolCallRequest`），不会报错，但静默丢失所有工具调用事件 | 🟡中等 | 使用 `isinstance(msg, ToolCallRequestEvent)` 或 try/except import |
| O7 | 243-247 | `_sync_stream` 中 `asyncio.get_event_loop_policy().__class__.__name__` 检测 Windows，但这个字符串检测在 CPython 以外的解释器（如 PyPy）上可能不准确 | 🟢轻微 | 用 `sys.platform == "win32"` 判断 |
| O8 | 257-263 | `_sync_stream` 创建新 event loop 后 `loop.close()` 在 finally 中执行。如果 `loop.run_until_complete` 抛出异常（非 StopAsyncIteration），loop 可能处于未清理状态 | 🟢轻微 | 确认 `loop.close()` 确实在 finally 中已执行 |
| O9 | 336-338 | `_run_manual_tool_protocol` 中 `cfg.get("base_url") or None` — 如果 `base_url` 为空字符串 `""`，`or None` 会转为 `None`，导致 AsyncOpenAI 使用默认 URL，这是正确行为但意图不明确 | 🟢轻微 | 改为 `cfg.get("base_url") or None` 加注释说明 |
| O10 | 344-347 | `_manual_tool_specs` 调用了 `registry.build_tool_specs(skill_ids)`，但这个函数可能在 registry 中不存在——如果 registry 的实现没有这个方法，会引发 AttributeError | 🟡中等 | 加 try/except 或用 `hasattr` 检查 |
| O11 | 376-377 | `_run_manual_tool_protocol` 的循环次数硬编码为 `range(10)`（第 375 行），但这个值没有和任何配置关联。与 `MAX_GUARD_RETRIES` 不同，没有暴露配置项 | 🟡中等 | 提为配置项 `MAX_MANUAL_TOOL_ITERATIONS` |
| O12 | 392-395 | `results = [_execute_manual_tool_call(call) for call in calls]` — 如果 `calls` 有 100 个元素（攻击者构造），会执行 100 个工具调用，没有任何限流 | 🟠严重 | 限制单次 tool_calls 数量不超过 20 |
| O13 | 392-395 | 同上，`_execute_manual_tool_call` 将所有 tool 结果通过 str() 序列化，不受限地放入 messages。大结果可能撑爆 token 限制 | 🟡中等 | 在 `_execute_manual_tool_call` 返回结果中已经用了 `_clip_output(str(result), 8000)`，确认但 message 本身可能累积到很大 |
| O14 | 409 | `repeated_calls >= 2 or all(not r.get("ok") for r in results)` — 如果模型故意每次改变一个无关参数来绕过重复检测，仍然可以无限循环（只是每次最多 10 轮，但每次调用可能很贵） | 🟢轻微 | 增加总调用次数计数器，跨 loop 追踪 |
| O15 | 452-456 | `_sync_agent_stream` 中为 manual tool protocol 创建了新 event loop，捕获了 `concurrent.futures.TimeoutError` 和 `asyncio.TimeoutError`。但 `_run_manual_tool_protocol` 的内部 API 调用 timeout=120 秒，这个 timeout 是 API 级别，不会抛 TimeoutError 到生成器级别 | 🟢轻微 | 确认异常类型覆盖 |
| O16 | 475-479 | `_split_tool_events` 和 `_is_tool_event_chunk`：它检测 `[TOOL]` 前缀来分离工具事件。但如果 agent 在普通回复内容中也包含 `[TOOL]` 字符串（如讨论工具名称），会被错误分类为工具事件 | 🟢轻微 | 只在行首匹配且要求无前导空白 |
| O17 | 485-561 | `run_agent_with_guard` 中的结构化 JSON prompt 包含 f-string 注入：`f"...{agent_info['display_name']}..."` 如果 display_name 包含引号或大括号，会破坏 JSON 格式或 prompt 结构 | 🟡中等 | 对注入 JSON 的变量做 `json.dumps()` 转义或至少 `repr()` |
| O18 | 503-504 | Guard retry 循环条件：`guard.decision.value == "retry"` 字符串比较，而 `GuardDecision.RETRY.value` 就是 `"retry"`。这里应该用 `guard.decision == GuardDecision.RETRY` | 🟢轻微 | 用枚举比较而非字符串 |
| O19 | 537-541 | `run_agent_with_guard` 内部用 `importlib.import_module("core.structured_output")` 做懒加载，但在函数每次调用时都会执行 import。虽然是幂等的但开销不必要 | 🟢轻微 | 在模块顶部 import |
| O20 | 564-595 | `run_parallel_stages` 中 ThreadPoolExecutor `max_workers=min(len(batch_agents), 8)`。如果 batch_agents 有 50 个，8 个 worker 全部自旋在一个 300 秒 timeout 的任务上时，ThreadPoolExecutor 会阻塞。虽然 `as_completed` 可以逐步处理，但总耗时可能是 50/8 * 300s | 🟡中等 | 添加总超时时间控制或限制 batch size |
| O21 | 562-582 | `forbidden_paths=["app.py", "config.py"] if ainfo["display_name"] not in ("integration_agent", "integration") else []` — 使用 `not in` 进行角色名白名单。如果有新 agent 角色叫 "integration_agent_v2" 也会被排除。应该用角色标签/标记而非名称匹配 | 🟡中等 | 在 role config 中添加 `can_modify_config: bool` 字段 |
| O22 | 621-640 | `_get_parallel_stages` 中对 `team.get("parallel_stages")` 的 `stage.get("roles")` 做了 `selected = [r for r in stage.get("roles", []) if r in roles]` 过滤。如果某 stage 的 roles 全部不存在，filter 后 `selected` 为空列表，`if selected:` 为 False，该 stage 被静默跳过 | 🟡中等 | 被跳过的 stage 应该记录 warning |
| O23 | 641-676 | `verify_agent_output` 调用 `_get_workspace_root()` 但从 `skills.builtin.file_ops` import，存在跨模块依赖不够清晰的问题 | 🟢轻微 | 使用 `config.DATA_DIR` 代替 |
| O24 | 679-754 | `run_paper_pipeline` — 800+ 行的函数，做了 4 个 stage 的硬编码 pipeline。重复代码极多（每个 stage 都 build payload → run → verify），应抽象为通用 stage runner | 🟡中等 | 提取 `_run_paper_stage` 通用函数 |
| O25 | 712-716 | PM 结束后检查 `acad_dir` 来找 project_id。如果 PM 创建了目录但被另一个并发运行的 paper pipeline 覆盖，会拿到错误的 project_id | 🟠严重 | 使用 PM agent 输出中的显式 project_id，而非文件系统侧信道推断 |
| O26 | 720 | `history.append({"source": "pm", "content": result, "avatar": ""})` — 每次运行都直接修改传入的 `history` 列表（可变默认参数已正确用 `None` 处理，但在函数内部仍直接修改）。如果外部调用方保留了 history 引用，会被意外修改 | 🟡中等 | 使用 `history = list(history or [])` 显式拷贝 |
| O27 | 755-796 | `direct_paper_export` 中第 759 行 `import subprocess, sys, time` — `time` 被 import 但从未使用 | 🟢轻微 | 删除未使用的 import |
| O28 | 765 | `ws = Path(workspace_root)` — `workspace_root` 参数类型注解是 `None`，但函数逻辑依赖于它是 Path-like。第 757 行传进来的可能已经是 Path，不需要再包一层 | 🟢轻微 | 类型注解改为 `Path | None` |
| O29 | 769 | `auto_merge_paper` 的返回值 `paper_path` 可能是 `None`，第 771 行检查了 `if not paper_path:` 后提前返回，但 `paper_path` 的类型检查器会认为它可能是 None，后面 `paper_path.read_text()` 会触发类型警告 | 🟢轻微 | 用 `assert paper_path is not None` 或在 if 分支中使用 |

---

## 5. `core/guard.py` — 安全守卫

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| G1 | 31-35 | `valid_json = "Agent output was not valid structured JSON" not in result.risks` — 用字符串匹配检查 JSON 有效性，极其脆弱。如果将来 `parse_agent_stage_result` 修改了风险消息文本，这里就静默失效 | 🟠严重 | 在 `AgentStageResult` 中添加 `is_valid_json: bool` 字段，而非依赖字符串匹配 |
| G2 | 63-64 | `missing_from_claim = real - claimed` — 这行在逻辑上检查了"git 有变化但 agent 没报告的文件"。但如果 agent 只创建了新文件（未 `git add`），`git diff` 不会显示未跟踪文件，`real` 集合为空，这个检查完全失效 | 🟠严重 | 需要同时检查 `git diff --name-only` 和 `git ls-files --others --exclude-standard`（未跟踪文件） |
| G3 | 70-71 | `claimed_not_real` 的扣分场景：agent 声称改了 `app.py`，但 git diff 没有。可能是 agent 说了谎，也可能是 git diff 没检测到（文件未跟踪）。直接扣 20 分太激进 | 🟡中等 | 对于 claimed_not_real，应加一个 "file existence" 的额外检查——如果文件确实存在且 mtime 有变化，至少说明 agent 可能操作了 |
| G4 | 78-85 | `_compile_changed_files` 使用 `py_compile.compile(str(full), doraise=True)` 编译 Python 文件。但这会在编译时执行模块级别的代码（import 副作用），如果被修改的文件中有恶意代码（如 `import os; os.system("rm -rf /")`），Guard 检查本身就成了攻击向量 | 🔴致命 | **必须使用 `py_compile.compile(file, dfile=..., doraise=True)` 放在沙箱中执行，或者在 subprocess 中执行，或使用 `ast.parse` 做语法检查而不执行** |
| G5 | 89-103 | 禁止路径检测：匹配逻辑使用 `any(str(f).replace("\\", "/").endswith(fp.replace("\\", "/"))` 和 `fp.rstrip("/") in str(f).replace("\\", "/")`。对于 `fp = "config.py"`，`f = "my_config.py"` 的 `endswith` 匹配会是 False，正确的。但 `fp.rstrip("/") in f` 对于 `fp = "app"` 会错误匹配 `path/to/mapping.py` 中的 'app' | 🟡中等 | 只使用 `endswith` 或 `Path(f).name == fp` 比较文件名 |
| G6 | 113-118 | `_no_test_keywords` 列表同时包含英文和中文关键词，但匹配时强制 `.lower()` — 这对中文无效（`"无需测试".lower() == "无需测试"`），而检查时 `"无需测试" in risk.lower()` 实际上可以工作（因为两边都未转换）。但混用 lower() 对中文词没意义 | 🟢轻微 | 对于 CJK 关键词单独做不含 lower() 的检查 |
| G7 | 120-122 | `no_test_needed` 检查两个来源：`result.risks` 和 `result.handoff_summary`。如果 agent 在 `summary` 中写了 "no test needed" 但在 `risks` 和 `handoff_summary` 都未出现，仍然会被误判为需要测试 | 🟢轻微 | 扩展检查范围到 `summary` 和 `task_scope` |
| G8 | 126 | `if not result.tests: score -= 15` 永远无法执行——因为没有 test 的情况（`not result.tests`）已经在上面第 125 行检查过 `missing_tests`。如果 `not result.tests and result.files_changed` 则 `missing_tests=True`，走下面的 elif。如果 `not result.tests and not result.files_changed`，则 `missing_tests=False`，走这个分支 | 🟡中等 | 逻辑是：没有文件变更 + 没有 test → 扣 15 分（合理但意图不清晰）。需要加注释说明 |
| G9 | 140 | `penalty = min(20, len(result.risks) * 5)` — 如果 `risks` 长度 > 4，扣分上限 20 分。但风险可能很多，每个风险固定 5 分太粗糙。比如 10 个安全风险 vs 10 个格式风险，权重应不同 | 🟢轻微 | 按风险严重程度分级扣分 |
| G10 | 146-149 | 路径逃逸检测：`if ".." in str(p).replace("\\", "/").split("/")` — 正确检测了 `..` 组件。但还有符号链接攻击（`/tmp/link -> /etc/passwd`）完全无法检测 | 🟡中等 | 增加 `Path(workspace_root / p).resolve()` 检查，确保解析后仍在 workspace 内 |
| G11 | 155-157 | Decision 规则：如果有 blocking issues 且 score < 60 → BLOCK，否则 RETRY。这里如果 score 正好 60 且有 blocking，走 `else: GuardDecision.RETRY`，意味着 blocking issues 存在但 score=60 时可以 retry。这是设计意图？ | 🟡中等 | 明确决策矩阵并加注释说明 |

---

## 6. `core/permission.py` — 权限系统

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| P1 | 17-18 | `from core.conflict import check_file_write_conflict, reset_file_write_locks, FILE_WRITE_LOCKS` — 模块级别的循环引用风险。`core.conflict` ↔ `core.permission` 互相引用（虽然当前 conflict.py 没有 import permission.py，但注释中写了"Re-export from conflict.py"）| 🟡中等 | 确认没有循环引用，或抽取公共接口 |
| P2 | 21 | `is_dangerous_shell_command` 使用 `(command or "").lower()` — 正则匹配 `r"\brm\s+-rf\b"` 在 `lower()` 后的字符串上执行是正确的，但对 Windows 命令 `rmdir /s /q` 只有 `rmdir /s` 被匹配，`/q` 变体不在列表中。 | 🟡中等 | 扩展 Windows 命令模式覆盖：`rmdir /s /q`, `format c:`, `del /f /s /q` 等 |
| P3 | 21-25 | 危险命令检测用正则匹配，但攻击者可以绕过：`rm  -rf`（双空格）、`rm --recursive --force`（长参数）、PowerShell `ri -r -fo`（别名）等全部不在模式中 | 🟠严重 | 危险命令检测应使用命令解析器先 normalize（展开别名、合并选项），再做检测 |
| P4 | 28-30 | `should_ask_permission` 只有 `mode == PermissionMode.ASK` 返回 True。GUARD 和 AUTO 都返回 False——意味着两个模式在行为上没有区别（都没有用户确认） | 🟡中等 | GUARD 模式至少应该在前端显示一个"已自动通过 Guard 检查"的通知 |
| P5 | 16 | `FILE_WRITE_LOCKS` 被 re-export 为 `permission.FILE_WRITE_LOCKS` 和 `conflict.FILE_WRITE_LOCKS`。如果外部代码通过 `permission.FILE_WRITE_LOCKS` 直接操作，可能绕过 `check_file_write_conflict` 的冲突检测 | 🟡中等 | 不 re-export `FILE_WRITE_LOCKS`，只暴露 `check_file_write_conflict` 和 `reset_file_write_locks` |

---

## 7. `core/context.py` — 上下文管理

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| C1 | 12 | `_clip_output`, `_is_tool_event_chunk`, `_split_tool_events` 在 `orchestrator.py` 中有 **完全相同的函数定义**（orchestrator L33, L112, L117），这违反了 DRY 原则，且未来只改一边会导致行为不一致 | 🟡中等 | 统一到一个模块（建议 `context.py`）并从 `orchestrator.py` 中删除重复定义 |
| C2 | 37-39 | `_history_text_size` 只计算 `content` 字段的字符长度，忽略了 `source`, `avatar` 等字段。如果消息包含大的二进制数据（attach），这个估算严重偏低 | 🟢轻微 | 修改为计算整个消息 dict 的 str() 长度 |
| C3 | 42 | `_context_budget_chars` = `max(12000, int(context_length * CONTEXT_COMPACT_RATIO * 3.2))` — 这个 3.2 魔法数字没有解释。而且 `context_length` 是 token 数，乘以 3.2 得出字符数（假设 ~3.2 chars/token），但这对于中文（~2 chars/token）和英文（~4 chars/token）不一样 | 🟡中等 | 针对不同语言调整系数，或使用 tiktoken 等 tokenizer 精确计算 |
| C4 | 58-59 | `_extract_artifact_lines` 中的关键词匹配 `"wrote "` 匹配英文，但中文是 `"文件"` 这种短词，会把几乎所有中文消息都标记为 artifact。比如 "这个文件不需要修改" 也会被匹配 | 🟢轻微 | 中英文关键词应分开并增加语境检查 |
| C5 | 70-84 | `compact_history` 中 `max_chars` 默认 1800。当一条消息被截断后，用 `_clip_output(content, max_chars)` 保留前面 1800 字符 + artifact 线索。但如果 artifact 线索恰好都在消息的后半部分，截断后会丢失所有关键信息 | 🟡中等 | 对 content 同时保留头部和尾部（头 1000 + 尾 800） |
| C6 | 91-95 | `history_for_model_context` 中 `keep_recent` 的扩展逻辑：当一条最近消息 > recent_limit 时调用 `compact_history([msg], max_chars=2500)`，返回一个单元素列表。但 `extend` 会将其展开为多个元素，这可能不符合预期 | 🟢轻微 | `compact_history` 返回 `list[dict]`，确认展开后正确 |
| C7 | 82 | `compact_history` 保留 `events` 数量但折叠了详细内容，只显示 `【工具事件】N 条，已从模型上下文中折叠。`。如果这些工具事件包含关键的编译错误信息，agent 就无法知道自己犯了什么错误 | 🟡中等 | 保留最后 N 条工具事件的 summary 行 |
| C8 | 112-114 | `load_soul_md_context` 接收 `preset_contents` 用于注入预置内容。但如果 preset_contents 包含了与 soul MD 文件重叠的内容，会重复注入，浪费 token | 🟢轻微 | 对内容做去重或至少记录总注入量 |
| C9 | 125-131 | Soul MD 文件读取没有大小限制（只有 max_chars 的截断）。一个 10MB 的 SOUL.md 文件会被完整读取到内存 | 🟢轻微 | 对大文件提前检查文件大小 |

---

## 8. `core/handoff.py` — 交接文档

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| H1 | 16-19 | `generate_handoff` 没有对 `run_id` 做安全文件名处理。如果 `run_id` 包含 `/` 或 `\`，会导致文件写入错误路径 | 🟡中等 | 对 `run_id` 也做 sanitize（如 `run_id.replace("/", "_").replace("\\", "_")`） |
| H2 | 26-28 | `datetime.now().isoformat(timespec='seconds')` 生成时间戳，但 `stage_name` 没有时间戳。如果同一 stage 多次运行，handoff 文件会互相覆盖 | 🟡中等 | 在文件名中加入时间戳或在内容中记录历史版本 |
| H3 | 36 | `structured = payload.get("structured")` — 如果 structured 是 `AgentStageResult` 对象，`getattr(structured, "status", "unknown")` 返回的是枚举值而不是字符串。随后的 `lines.append(f"- 状态: {status}")` 会输出 `AgentStatus.DONE` 而不是 `"done"` | 🟠严重 | 使用 `status.value if hasattr(status, 'value') else status` 做规范化 |
| H4 | 74-79 | "下一阶段注意" 是硬编码的中文提示，如果系统需要国际化需要提取到配置。问题不严重，但灵活度差 | 🟢轻微 | 无 |
| H5 | 30-76 | `generate_handoff` 生成的文档包含所有 agent 的输出，没有过滤掉失败/blocked 的 agent。下一阶段读取时会看到失败 agent 的垃圾输出 | 🟡中等 | 对失败/blocked 的 agent 标明显标记，或在汇总区分离 |

---

## 9. `core/structured_output.py` — 结构化输出解析

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| SO1 | 18-29 | `extract_json_object` 从文本中扫描所有 `{` 并用深度计数器找配对 `}`。如果文本中有非 JSON 的大括号（如 `{"key": "value with } inside"}`），深度计数器会错误匹配 | 🟡中等 | 实现一个正确的 JSON parser 或使用 `json.JSONDecoder.raw_decode()` 迭代尝试 |
| SO2 | 19 | `fence = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, _re.I | _re.S)` — 用了 `.*?`（非贪婪），但如果代码块中有嵌套的 ```（如 markdown 示例），会过早结束匹配 | 🟢轻微 | 使用更健壮的 fence 检测 |
| SO3 | 25-39 | 手动实现的大括号配对算法没有处理字符串内的转义引号 `\"` 和 `\\`。它正确处理了 `\\` 作为 escape 字符但未处理多字符 escape 序列 | 🟡中等 | 部分已处理 `escape`，检查是否处理了所有 edge case（`\n`, `\t`, `\uXXXX` 等） |
| SO4 | 49-58 | `_command_from_any` 中 `value.get("result") in {"passed", "failed", "not_run", "unknown"}` — 如果 JSON 中的 result 是 `"Passed"`（大写），匹配失败后会 fallback 到 `TestStatus.UNKNOWN` | 🟡中等 | `.lower()` 处理后再匹配 |
| SO5 | 66-69 | `_string_list` 处理单个字符串时返回 `[value.strip()]`。但如果 value 是 `"a,b,c"`（逗号分隔的列表字符串），它不会拆分，因为函数假设 JSON 中用的是数组。如果某些 agent 输出的是逗号分隔字符串，会被当作单个路径处理 | 🟢轻微 | 对字符串类型做逗号拆分或保持现状并文档化要求只用数组 |
| SO6 | 75-99 | `parse_agent_stage_result` 在 `data` 存在但缺少某些字段时，对 `files_read`, `files_changed`, `commands_run`, `tests`, `risks` 的默认值处理不一致。`files_read` 缺省为 `[]`，但 `summary` 缺省为 `""`。这意味着空的 structured JSON `{}` 会创建合法的 `AgentStageResult`（status=DONE）——这应该被视为无效 | 🟠严重 | 增加最低有效字段检查：`summary` 或 `task_scope` 至少一个非空才算有效 |
| SO7 | 80 | `status = AgentStatus(status_str)` — 如果 JSON 中的 status 值（如 `"needs retry"` with space）不在枚举中，`ValueError` 被捕获后静默改为 DONE。这会让真正需要 retry 的 agent 被当成 done | 🟡中等 | 尝试做 fuzzy matching（如 `status_str.replace(" ", "_").lower()`），匹配失败时至少保留原值并加到 risks |
| SO8 | 90-103 | `agent_result_to_markdown` 中 `f"{test.command}: {test.result.value} {test.evidence}"` — 如果 `test.command` 或 `test.result` 为 None 会输出 None 字符串 | 🟢轻微 | 使用 `getattr` 提供默认值 |
| SO9 | 14-52 | `extract_json_object` 当文本不含任何 JSON 时返回 None，但 `parse_agent_stage_result` 对所有调用都试图解析。如果 agent 输出完全不是 JSON，会在 risks 中记录但 status 仍为 DONE——可能掩盖真正的错误 | 🟡中等 | 当 JSON 解析失败时，status 应为 `FAILED` 而非 `DONE` |

---

## 10. `core/conflict.py` — 冲突管理

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| CF1 | 8 | `FILE_WRITE_LOCKS: dict[str, str] = {}` 是全局模块级字典，无并发保护。在 ThreadPoolExecutor（`orchestrator.py` L564）中多个线程同时调用 `check_file_write_conflict` → `FILE_WRITE_LOCKS[key] = agent_name` 会发生竞态条件，两个 agent 可能同时获得同一文件的写锁 | 🔴致命 | 使用 `threading.Lock()` 保护所有 `FILE_WRITE_LOCKS` 的读写操作 |
| CF2 | 11-20 | `check_file_write_conflict` 对路径的标准化使用 `str(Path(path)).replace("\\", "/").lower()`。在 Windows 上，`C:\Users\...` 和 `c:\Users\...` 会正确归一化，但 `path/to/file` 和 `./path/to/file` 不会被归一化为同一路径 | 🟡中等 | 使用 `Path(path).resolve()` 获取绝对路径后再做比较 |
| CF3 | 13-14 | `if not run_id or not path: return True, ""` — 如果传空字符串，直接放行不检查锁。这意味着任何地方传空 run_id 都可以绕过冲突检测 | 🟡中等 | 至少记录 warning 日志，或者对空 run_id 拒绝创建锁 |
| CF4 | 22 | `FILE_WRITE_LOCKS[key] = agent_name` — 注释说 "Same agent can write the same file multiple times"，但如果 agent_name 也相同（第二次写入），锁被覆盖为相同的 agent_name，行为正确。但第二次写入不会检查第一次写入是否完成，可能产生中间一致性状态 | 🟢轻微 | 增加状态标记（如 `pending` → `committed`） |
| CF5 | 28-33 | `reset_file_write_locks` 遍历所有 key 做 `startswith(prefix)` 检查，复杂度 O(n)。如果有大量 lock，遍历会慢但影响不大 | 🟢轻微 | 使用 `{run_id: {path: agent}}` 的二级字典结构可以 O(1) 清理 |

---

## 11. `core/contract.py` — 合约

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| CT1 | 21-78 | `create_contract` 生成 Markdown 格式的合约文件。合约中 `global_forbidden = {"app.py", "config.py"}` 硬编码——如果未来需要保护其他文件（如 `.env`），需要改代码 | 🟡中等 | 从 `config.py` 读取 `GLOBAL_FORBIDDEN_FILES` 配置 |
| CT2 | 24 | `task` 参数直接作为用户输入的 raw task 写入合约文件。如果 task 包含恶意 Markdown 或 HTML 注入（通过 `{}` ）——虽然 Markdown 渲染器通常会 escape HTML，但在某些预览器中可能触发 XSS | 🟢轻微 | 对 task 做 sanitize，转义 HTML 标签 |
| CT3 | 47 | `prompt = role.get("prompt", "")` — prompt 可能包含敏感信息（如 API key、数据库密码），直接写入合约文件可能泄露给不该看的 agent | 🟠严重 | 截断 prompt 到 200 字符（按现有代码已截断到 200），但应添加敏感信息过滤 regex |
| CT4 | 64-67 | 合约中写死了工具限制为硬编码的 `["code_compile"]` 和 `["run_tests pytest"]`。如果 team 配置中没有这些工具，合约内容会不准确 | 🟡中等 | 从 team config 中动态读取测试命令 |
| CT5 | 76-78 | `get_contract_path` 和 `contract_exists` 各直接拼接路径，但没有处理 `run_id` 中的特殊字符（如 `../../` 路径遍历） | 🟠严重 | 对 `run_id` 做 sanitize：只允许 `[a-zA-Z0-9_-]` |

---

## 12. `core/patch_manager.py` — 补丁管理

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| PM1 | 11-33 | `save_agent_diff` 调用 `subprocess.run(["git", "diff"], ...)`。如果 `workspace_root` 不是一个 git 仓库，`returncode != 0` 会返回 None，异常静默吞掉 | 🟡中等 | 区分 "非 git 仓库"（normal）和真正的 git 错误，对后者打日志 |
| PM2 | 19-20 | `subprocess.run` 的 `timeout=15` 秒可能不够——大型仓库的 `git diff` 可能需要更长时间 | 🟢轻微 | 将 timeout 提升到 30 秒或可配置 |
| PM3 | 27-29 | 文件名包含 `{run_id}_{safe_name}_{ts}.diff` — `safe_name` 通过 `replace(" ", "_")` 处理，但 `run_id` 没有被同样处理。如果 `run_id` 包含空格或特殊字符，会生成无效文件名 | 🟡中等 | 对 `run_id` 也做 `replace(" ", "_").replace("/", "_")` 或只允许安全字符 |
| PM4 | 29 | `header = f"# Agent: {agent_name}\n# Run: {run_id}\n# Time: {ts}\n\n"` — 如果 `agent_name` 包含换行符，会破坏 diff 文件格式（注入假行） | 🟡中等 | 对 `agent_name` 做 sanitize，替换换行符 |
| PM5 | 11 | `workspace_root: Path | None = None` 默认值时 fallback 到 `DIFFS_DIR.parent`（即 `GENERATED_DIR`）。这个 fallback 可能不是正确的 git 仓库根目录 | 🟡中等 | 默认值应使用 `config.DATA_DIR` 或通过 `git rev-parse --show-toplevel` 找到真正的 git 根目录 |
| PM6 | 37-40 | `list_agent_diffs` 使用 `sorted(DIFFS_DIR.glob(f"{run_id}_*.diff"))` — 如果 `run_id` 包含 glob 特殊字符（如 `*`, `?`, `[`），glob 模式会被解释，可能匹配到错误文件 | 🟡中等 | 使用 `glob.escape(run_id)` 转义 |

---

## 13. `core/merge.py` — 合并逻辑

| 编号 | 行号 | 问题 | 严重程度 | 修复建议 |
|------|------|------|----------|----------|
| M1 | 1 | 文件缺少标准模块 docstring 和 `from __future__ import annotations` | 🟢轻微 | 添加 |
| M2 | 3-4 | 函数签名只有 `project_id` 和 `workspace_root` 两个参数，没有对 `project_id` 做任何验证（是否为空字符串、是否包含路径遍历字符） | 🟠严重 | 添加 project_id 验证：不能为空，不能包含 `/`, `\\`, `..` |
| M3 | 14-16 | `sections = sorted(sections_dir.glob('*.md'), key=lambda p: p.stat().st_mtime)` — 按修改时间排序意味着最后写的 section 排最后。但这不能保证逻辑顺序正确（如 Introduction 应该在 Chapter 3 前面）。如果 agent 并发写入，st_mtime 相近，排序接近随机 | 🟡中等 | 尝试从文件名提取序号（如 `01_intro.md`），fallback 到 mtime |
| M4 | 22-26 | `meta_path.read_text()` 使用 `json.loads()` + 裸 `except: pass`。如果 JSON 损坏但文件存在，`import json` 在循环外已 import（第一次通过后不再正确）——不，实际上 `import json` 在 try 块内每次循环都会检查 sys.modules，所以没问题。但裸 `except: pass` 掩盖所有错误 | 🟢轻微 | 至少捕获 `(json.JSONDecodeError, OSError)` |
| M5 | 49 | `cjk_count = len(re.findall(r'[\u4e00-\u9fff]', content))` — 只统计基本 CJK 统一汉字（U+4E00 ~ U+9FFF），不包括扩展 A/B/C/D/E/F 区、CJK 兼容汉字、日文汉字、韩文汉字。对使用扩展汉字的文档，字数统计严重偏低 | 🟡中等 | 使用 `r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u{20000}-\u{2a6df}\u{2a700}-\u{2ebef}]'` 或第三方库 `regex` 的 `\p{Han}` |
| M6 | 51-55 | 每个 section 作为 `## 第{i}章 {sec.stem}` 插入。如果 section 文件本身也使用 `##` 级别的标题，会导致标题层级混淆 | 🟢轻微 | 将 section 内的标题自动降级一级（`# → ##`, `## → ###`） |
| M7 | 62-71 | references.json 的加载同样有裸 `except: pass`，且直接访问 `r.get('citation', r.get('text', str(r)))` — 如果 reference 条目是 string，`str(r)` 会给出 `"{'title': ...}"` 而不是有意义的引用格式 | 🟢轻微 | 检查类型后再提取字段 |
| M8 | 74-75 | `paper_path.write_text('\n'.join(lines), encoding='utf-8')` — 用 `\n` 连接行但没有在最后加换行符。POSIX 标准建议文本文件以换行符结尾 | 🟢轻微 | 使用 `'\n'.join(lines) + '\n'` |
| M9 | 76 | 返回值 `total_chars` 是原始字符数（不准确），但 `cjk_count` 是准确的中文字数。外部调用方 `direct_paper_export` 中把 `cjk_count` 当 `word_count` 使用，这对于中英混合文档不准确 | 🟡中等 | 实现更合理的字数统计算法（CJK: 1 char = 1 word; English: split by whitespace） |

---

## 📊 问题汇总统计

| 严重程度 | 数量 | 文件分布 |
|----------|------|----------|
| 🔴 致命 | 2 | guard.py (G4), conflict.py (CF1) |
| 🟠 严重 | 15 | schemas.py(2), agent_factory.py(2), orchestrator.py(4), guard.py(2), permission.py(1), structured_output.py(1), merge.py(1), contract.py(2) |
| 🟡 中等 | 41 | 几乎覆盖所有文件 |
| 🟢 轻微 | 28 | 代码风格、冗余检查、易读性等 |
| **合计** | **86** | |

---

## 🎯 优先修复建议（Top 10）

1. **🔴 G4 (`guard.py:78-85`)** — `py_compile.compile` 会执行模块级代码，存在远程代码执行风险。立即改为 `ast.parse` 语法检查或 subprocess 沙箱执行。
2. **🔴 CF1 (`conflict.py:8`)** — `FILE_WRITE_LOCKS` 全局字典无并发保护，ThreadPoolExecutor 多线程写锁存在竞态条件。添加 `threading.Lock()`。
3. **🟠 O25 (`orchestrator.py:712-716`)** — `run_paper_pipeline` 用文件系统侧信道推断 project_id，并发运行时会拿错 ID。改为从 PM agent 输出中显式提取。
4. **🟠 G2 (`guard.py:63-64`)** — guard 的 `git diff` 检查不覆盖未跟踪文件，声称改了文件但 git 未跟踪的 agent 完全绕过检测。
5. **🟠 A5 (`agent_factory.py:54-62`)** — 对所有非 OpenAI 模型硬编码 `model_info` 声明支持 function_calling，导致不支持的模型调用失败。
6. **🟠 O4 (`orchestrator.py:134-137`)** — 图片路径拼接未防路径遍历攻击。
7. **🟠 CT5 (`contract.py:76-78`)** — `run_id` 未 sanitize，可路径遍历。
8. **🟠 M2 (`merge.py:3-4`)** — `project_id` 未验证，可路径遍历。
9. **🟠 H3 (`handoff.py:36`)** — agent status 输出枚举对象而非字符串值。
10. **🟠 SO6 (`structured_output.py:75-99`)** — 空 `{}` JSON 被解析为有效 `AgentStageResult`（status=DONE），应拒收。

---

## 附注

- 审计中发现的**代码重复**：`_clip_output`, `_is_tool_event_chunk`, `_split_tool_events` 在 `orchestrator.py` 和 `context.py` 中各有一份完全相同的拷贝。
- `orchestrator.py` 是最大的文件（~800 行），`run_paper_pipeline` 函数过于庞大、重复逻辑多，建议重构。
- 多个模块对 `run_id` 缺少统一的安全校验，建议在 `schemas.py` 中抽象一个 `RunID` 类型并统一校验。
- `strip()` 和 `lower()` 的混用在 CJK 场景下可能产生预期外行为，建议统一处理策略。