# 审计报告：data/ 模块 + presets/ 模块 + skills/ 模块

> 审计日期：2026-05-08
> 审计范围：`data/database.py`, `data/model_store.py`, `data/run_store.py`, `data/session_store.py`, `data/team_store.py`, `presets/models.py`, `presets/skills.py`, `presets/teams.py`, `presets/souls.py`, `skills/registry.py`, `skills/__init__.py`

---

## 一、data/database.py

### B1: `get_db()` 缺少线程安全保证 — 严重程度：高
- **问题**：`_local.conn` 使用了 `threading.local()`，每个线程拥有独立连接。但是 `db_transaction()` 上下文管理器没有线程归属检查——如果在一个线程获取连接、在另一个线程 yield，会导致事务跨越线程，行为不可预测。
- **影响**：多线程环境下可能导致死锁或静默数据损坏。当前用 `check_same_thread=False` 掩盖了这个问题而非解决它。
- **建议**：在 `db_transaction()` 入口检查当前线程是否与 `_local.conn` 所属线程一致；或者使用连接池（如 `sqlite3` 的 URI 模式 + 写锁）管理 SQLite 的串行写入限制。

### B2: `get_db()` 每个线程独立 WAL 连接 — 严重程度：中
- **问题**：每个线程调用 `get_db()` 都会执行 `PRAGMA journal_mode=WAL` 和 `PRAGMA foreign_keys=ON`。这些是连接级 PRAGMA，但每次创建新连接都要重设。如果一个线程的 `_local.conn` 被设为 `None`（没有途径），新连接会拿到正确的 PRAGMA；但如果未来有代码 `del _local.conn` 或类似操作，会创建一个不带 PRAGMA 的连接。
- **影响**：当前代码路径没有删除 `_local.conn` 的途径，暂时安全。但 `None` 值被正确重新创建——问题不严重，属防御性不足。
- **建议**：封装一个 `_create_connection()` 工厂函数，集中设置所有 PRAGMA。

### B3: WAL 模式无检查点策略 — 严重程度：低
- **问题**：SQLite WAL 文件会随写入无限增长，没有 WAL checkpoint 调用。长时间运行后 WAL 文件可能占用大量磁盘空间。
- **影响**：频繁写入场景（大量 tool_logs/stage_logs）下磁盘可能耗尽。
- **建议**：在 `init_db()` 或定期任务中添加 `PRAGMA wal_checkpoint(TRUNCATE)` 调用。

### B4: `db_transaction()` 只处理 Exception，不处理 KeyboardInterrupt/SystemExit — 严重程度：低
- **问题**：`except Exception:` 不会捕获 `KeyboardInterrupt` 或 `SystemExit`。如果程序在这些信号下中断，事务不会 rollback，连接可能处于异常状态。
- **影响**：程序被迫终止时数据库可能残留未提交事务（但 WAL 模式会处理）。
- **建议**：改为 `except BaseException:` 或至少加 `finally` 清理。实际上 WAL 模式会处理残留事务，这个问题影响有限。

### B5: `stage_logs` 表缺少索引 — 严重程度：中
- **问题**：`stage_logs` 表没有 `created_at` 索引，`get_stage_logs()` 按 `id ASC` 排序（依赖自增主键），但如果需要按时间范围查询会很慢。
- **影响**：当前只有按 `run_id` 查询的场景，影响有限。但如果未来加时间范围过滤将产生性能问题。
- **建议**：如无时间查询需求则忽略；如有，加 `CREATE INDEX IF NOT EXISTS idx_stage_logs_created ON stage_logs(created_at)`。

---

## 二、data/model_store.py

### B6: API Key 明文存储（base85 不是加密） — 严重程度：高
- **问题**：`_save_key_file()` 使用 `base64.b85encode` 作为"简单混淆"。这是编码而非加密——任何人拿到 `.keys/` 目录下的文件都能直接解码。函数注释称 "not real encryption" 但没有警告用户。
- **影响**：攻击者获得文件系统读取权限即可获取所有 API Key。在生产环境中这是严重的安全隐患。
- **建议**：
  1. 至少使用操作系统提供的加密 API（如 Windows DPAPI `cryptography` 库的 `fernet`）。
  2. 优先使用 keyring 后端；文件 fallback 应该引发警告。
  3. 考虑加密码保护，存储时要求用户设置主密码。

### B7: Keyring 失败静默回退到文件 — 严重程度：中
- **问题**：`_set_key()` 在 keyring 写入失败时 `pass` 后静默回退到文件存储。用户不知道 keyring 失败了，也不知道 key 存到了文件中。`_get_key()` 同样如此。
- **影响**：用户以为 key 安全存在系统凭据管理器，但实际上可能存在不安全的文件中。
- **建议**：至少在首次 keyring 失败时打印 warning 日志，告知用户回退路径。

### B8: 环境变量 `GALAXY_DEFAULT_API_KEY` 作为全局兜底 — 严重程度：中
- **问题**：`_get_key()` 对**所有** key_ref 都尝试 `GALAXY_DEFAULT_API_KEY` 作为最后兜底。这意味着如果用户配置了多个模型但只设置了一个环境变量，所有模型都会拿到相同的 API Key。而 `get_model_api_key()` 的 per-model env 变量兜底逻辑更合理。
- **影响**：多模型共用同一个 key 可能导致：
  - 用 DeepSeek key 调用 OpenAI API（失败）
  - 用 OpenAI key 调用 DeepSeek API（泄露 key 到错误服务）
- **建议**：删除 `_get_key()` 中的全局环境变量兜底，或将其标记为 `deprecated`，只保留 `get_model_api_key()` 中的 per-model 兜底。

### B9: `get_model_api_key()` 和 `_get_key()` 存在两层环境变量逻辑 — 严重程度：低
- **问题**：`_get_key()` 在第3步尝试 `GALAXY_DEFAULT_API_KEY`，而 `get_model_api_key()` 在第4步又尝试 `GALAXY_API_KEY_{model_id}` + `GALAXY_DEFAULT_API_KEY`。两层兜底逻辑重复且容易让人困惑。
- **影响**：代码可读性差，优先级不透明。
- **建议**：统一到一个函数中：keyring → file → per-model env → global env。

### B10: `record_model_usage()` 中的 token 估算过于粗糙 — 严重程度：低
- **问题**：`input_chars // 3` 和 `output_chars // 3` 是非常粗糙的 token 估算。对于中文文本（每个字符可能对应2个token）和代码（每个字符接近1 token），偏差可达 3-6 倍。
- **影响**：统计数据不准确，但不影响功能。
- **建议**：考虑使用 `tiktoken` 库进行更准确的 token 计数；或至少根据文本语言特征（检测中文字符比例）使用不同因子。

### B11: `save_model()` 的 `api_key` 参数传入空字符串时仍创建 key_ref — 严重程度：低
- **问题**：`save_model()` 总是生成 `key_ref = f"model:{mid}"` 并调用 `_set_key(key_ref, api_key)`。如果 `api_key` 为空，`_set_key()` 中 `if not api_key: return` 会跳过存储，但 key_ref 已写入数据库。
- **影响**：数据库有 key_ref 记录但实际没有 key，查询时返回空字符串。功能正确但有多余的数据库写入。
- **建议**：如果 `api_key` 为空，不写入 `key_ref` 字段（留空或设为特殊值）。

### B12: `delete_model()` 不会删除 `model_usage` 记录 — 严重程度：低
- **问题**：删除模型后，`model_usage` 表中的关联记录不会被清理。
- **影响**：残留的孤立统计数据，不影响功能但占用空间。
- **建议**：`delete_model()` 中追加 `DELETE FROM model_usage WHERE model_id = ?`。

### B13: `set_default_model()` 对不存在的 model_id 静默成功 — 严重程度：低
- **问题**：如果 `model_id` 不存在，`set_default_model()` 先执行 `UPDATE models SET is_default = 0` 清空所有默认标记，然后第二个 UPDATE 影响0行。结果是没有模型标记为默认。
- **影响**：所有模型都不是默认，`get_default_model()` 会 fallback 到按名字排序的第一个。功能不会崩溃但逻辑不符合预期。
- **建议**：先检查 model_id 是否存在，不存在时抛异常或返回 False。

### B14: `.keys/` 目录权限未设置 — 严重程度：中
- **问题**：`_save_key_file()` 创建 `.keys/` 目录时没有显式设置权限。在 Windows 上默认继承父目录权限，在 Linux/Mac 上默认 755。
- **影响**：多用户系统上其他用户可能读取 `.keys/` 目录内容。虽然 base85 不是真正的加密，但至少应该限制文件系统权限。
- **建议**：创建目录后设置 `0o700` 权限（仅 owner 可访问）。

---

## 三、data/run_store.py

### B15: `save_run_state()` 的 `state_json` 参数接受任意字符串 — 严重程度：中
- **问题**：函数签字为 `state_json: str = "{}"`，直接写入数据库。调用者可能传入非 JSON 字符串，后续 `load_run_state()` 的 `json.loads()` 会抛异常并返回空 dict——静默丢失数据。
- **影响**：如果调用方误传非 JSON 字符串，状态数据永久丢失（因为 `load_run_state()` catch 了异常返回 `{}`），而数据库中的原始数据仍然是非 JSON 垃圾。
- **建议**：
  1. 修改签名为 `state: dict`，在函数内部 `json.dumps`。
  2. 或者至少在校验阶段做 `json.loads(state_json)` 验证。

### B16: `load_run_state()` 静默吞掉 state_json 解析失败 — 严重程度：低
- **问题**：`json.loads()` 失败时返回 `d["state"] = {}`，不记录任何日志。与 B15 配合形成"静默数据丢失"链。
- **影响**：调试困难，用户不知道状态数据已经丢失。
- **建议**：至少加 `logging.warning` 或 `print` 警告。

### B17: `list_run_states()` 不返回 state 内容 — 严重程度：低
- **问题**：SELECT 只取了 `run_id, task, team_id, mode, created_at, updated_at`，没有 `state_json`。调用者无法从列表判断运行状态。
- **影响**：列表视图缺少关键信息，需要额外调用 `load_run_state()`。
- **建议**：考虑增加一个 `include_state` 参数（默认 False 以节省传输）。

### B18: `append_stage_log()` 和 `append_tool_log()` 无输入校验 — 严重程度：低
- **问题**：`structured` 和 `guard` 参数使用 `default=str` 进行 JSON 序列化，意味着任何不可序列化对象都会被转为字符串而非抛出错误。`tool_name`、`args_preview` 等字段无长度检查。
- **影响**：超大日志可能导致数据库膨胀或插入失败。
- **建议**：对文本字段添加合理的长度检查；对 `structured`/`guard` 使用 `json.dumps` 时不泄露内部实现细节。

### B19: `get_tool_logs()` 返回顺序为 `id DESC` — 严重程度：低
- **问题**：工具日志按 `id DESC` 返回（最新在前），而 `get_stage_logs()` 按 `id ASC` 返回（最早在前）。不一致的排序约定容易导致调用方出错。
- **影响**：调用方需要记住不同函数的不同排序方向。
- **建议**：统一返回顺序或添加 `order` 参数。

---

## 四、data/session_store.py

### B20: `save_session()` 的 `history` 类型标注是 `list[dict]` 但无校验 — 严重程度：中
- **问题**：注释标注 `history: list[dict]`，但实际接受任意类型，直接 `json.dumps(history, ensure_ascii=False)`。如果 `history` 包含不可序列化对象（如 `datetime` 对象），`json.dumps` 会抛出 `TypeError`，事务 rollback。
- **影响**：如果 UI 传入不规范的历史消息，保存会静默失败，用户丢失聊天记录。
- **建议**：使用 `default=str` 兜底，或在校验层做类型检查。

### B21: `delete_session()` 永远返回 True — 严重程度：低
- **问题**：即使 `sid` 不存在，DELETE 执行成功（影响 0 行），函数仍返回 `True`。调用者无法区分"删除了"和"本来就不存在"。
- **影响**：UI 可能显示"已删除"成功提示，但实际上什么都没删除。通常可以接受，但不够严谨。
- **建议**：检查 `conn.execute(...).rowcount`，返回是否实际删除了行。

### B22: `list_sessions()` 不返回 `history_json` — 严重程度：低
- **问题**：只返回元数据字段，不包含聊天历史。与 B17 相同模式。
- **影响**：列表视图缺少内容预览，需要额外请求 `get_session()`。
- **建议**：考虑增加 `include_history` 参数（默认 False）。

---

## 五、data/team_store.py

### B23: `save_team()` 接受任意 dict 但无 schema 校验 — 严重程度：中
- **问题**：`save_team()` 接受 `team: dict[str, Any]`，不做任何字段校验。可以传入任意键值对，但只有 `name, category, chat_style, max_turns, roles, parallel_stages` 被保存。其他字段静默丢弃。
- **影响**：调用方可能传入无效字段而不知道被丢弃。`roles` 或 `parallel_stages` 中可能有循环引用导致 `json.dumps` 失败。
- **建议**：
  1. 使用 Pydantic model 或 TypedDict 做参数校验。
  2. 对 `json.dumps` 使用 `default=str` 兜底。

### B24: `save_team()` 团队 ID 生成只有 6 位 — 严重程度：低
- **问题**：`tid = team.get("id") or str(uuid.uuid4())[:6]` —— 只取 UUID 前6位，碰撞概率约为 1/16^6 ≈ 1/16M。虽然不大，但远不如完整 UUID 安全。
- **影响**：理论上存在 ID 碰撞可能。
- **建议**：使用完整 UUID 或 `uuid.uuid4().hex[:12]`。

### B25: `delete_team()` 不清理关联数据 — 严重程度：高
- **问题**：删除团队后，`chat_sessions` 表中 `team_id` 引用该团队的行不会被清理，`run_states` 表中的关联运行也不会清理。这导致：
  1. 会话列表引用已删除的团队，UI 可能显示异常。
  2. 孤儿数据积累。
- **影响**：数据完整性问题。外键约束未启用（虽然 `PRAGMA foreign_keys=ON`，但表定义中未见 `FOREIGN KEY` 约束）。
- **建议**：
  1. 在 `delete_team()` 中追加清理 `chat_sessions` 和 `run_states` 的关联行。
  2. 或者在表定义中添加 `FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE`。

### B26: `max_turns` 无上限校验 — 严重程度：低
- **问题**：`team.get("max_turns", 10)` 可以传入极大值（如 `999999`），导致无限对话循环。
- **影响**：可能耗尽 token 配额或导致超时。
- **建议**：添加合理上限，如 `max(max_turns, 50)` 或可配置。

---

## 六、presets/models.py

### B27: `Ollama Local` 预设默认端口 11434 但语法正确 — 严重程度：低
- **问题**：`"base_url": "http://localhost:11434/v1"` —— 标准 Ollama 端口是 11434，这是正确的。但 URL 包含 `/v1` 路径，如果用户用的是原生 Ollama API（路径为 `/api`），会出问题。
- **影响**：仅影响使用默认 Ollama 预设且 API 路径不匹配的用户。
- **建议**：在 description 中注明端口和 API 路径，或提供多个 Ollama 预设。

### B28: DeepSeek 模型 `context_length` 可能过低 — 严重程度：低
- **问题**：`DeepSeek V3`、`R1`、`V4 Pro` 都使用 `context_length: 64000`。实际 DeepSeek V3 支持 128K，DeepSeek R1 支持 128K。
- **影响**：限制用户可用上下文长度，大文档可能被截断。
- **建议**：更新为实际支持的上下文长度。

### B29: `Moonshot` 使用 `moonshot-v1-8k` 但 context_length 仅为 8000 — 严重程度：低
- **问题**：Moonshot 以超长上下文闻名，默认 8K 模型严重限制能力。
- **影响**：用户可能不知道有其他更长上下文的 Moonshot 模型可用。
- **建议**：改为 `moonshot-v1-128k` 或至少加注释说明。

### B30: 预设模型配置未包含 `capabilities` 字段 — 严重程度：低
- **问题**：`PRESET_MODELS` 中没有任何模型包含 `capabilities` 字段（如 `{"vision": true, "tools": true}`），而数据库 schema 和 `save_model()` 都支持此字段。
- **影响**：导入预设时所有模型 capability 为 `{}`，可能影响功能路由。
- **建议**：为支持视觉、工具调用的模型添加 `capabilities` 字段。

---

## 七、presets/skills.py

### B31: 技能内容中引用不存在的工具 — 严重程度：中
- **问题**：
  - `skill_figure_engineer` 中提到 "优先使用 chart_tools 和 figure_tools 生成真实 PNG、SVG"，但注册表中没有名为 `chart_tools` 或 `figure_tools` 的工具 ID（实际注册的是 `chart_line`、`chart_bar` 等）。
  - `skill_project_coder` 中提到 "运行最小验证"，但未说明具体用什么工具。
- **影响**：Agent 按照技能指导尝试调用不存在的工具，产生错误。
- **建议**：更新技能内容中的工具名称与实际注册表一致。

### B32: 技能 ID 无冲突检测 — 严重程度：低
- **问题**：`DEFAULT_CUSTOM_SKILLS` 中的 key 和 value 中的 `id` 字段可能不一致。如果手动编辑导致不匹配，会导致混淆。
- **影响**：当前代码中所有 key 和 id 一致，暂无问题。但缺乏编译时检查。
- **建议**：添加断言或测试校验 key == d["id"]。

### B33: 所有技能都是 `type: "knowledge"` — 严重程度：低
- **问题**：schema 定义了 `type` 字段，但所有刻技能都设为 `"knowledge"`。如果系统未来支持 `"tool"` 或 `"behavior"` 类型，当前设计无法区分。
- **影响**：不影响当前功能，但如果 `type` 用于路由则全部分类错误。
- **建议**：扩展 `type` 枚举或重命名为更具体的分类。

---

## 八、presets/teams.py

### B34: 预设团队使用 `mode` 字段但数据库使用 `chat_style` — 严重程度：高
- **问题**：预设团队所有条目使用 `"mode": "round_robin"`，但数据库 schema 的列名是 `chat_style`，`team_store.save_team()` 从 `team.get("chat_style", "round")` 读取。**导入预设团队时 `mode` 字段会被静默丢失**，所有团队 fallback 到 `chat_style="round"`。
- **影响**：这是数据模型不一致——预设和存储层使用不同的字段名。可能导致用户看到的所有预设团队都是 `round` 模式而非预期的 `round_robin`。
- **建议**：
  1. 在导入/同步预设时做字段名映射（`mode` → `chat_style`）。
  2. 或者统一预置定义，使用 `chat_style` 字段。

### B35: `PARALLEL_PROJECT_SQUAD_V2` 包含 `skills` 列表 — 严重程度：高
- **问题**：`PARALLEL_PROJECT_SQUAD_V2["roles"]` 每个角色带有 `skills` 字段（如 `["contract_write", "contract_read", ...]`），但 `team_store.save_team()` 只保存 `roles` 数组的 JSON。如果 `roles` 数组中的元素包含额外字段（如 `skills`、`model_id`），它们会被保存但**不会被 `_row_to_team()` 正确还原**，因为 `_row_to_team()` 只做 JSON 反序列化，不处理嵌套字段的 schema。
- **影响**：`PARALLEL_PROJECT_SQUAD_V2` 是一个高级团队模板，但如果通过 `save_team` API 存储，`skills` 和 `model_id` 字段会混在 `roles_json` 中，但 `_row_to_team()` 能正确处理 JSON 解析——实际上这个问题的影响取决于 `roles` 的消费方是否期望这些额外字段。如果消费者不知道这些字段存在，它们会被忽略。
- **实际影响**：如果 `PARALLEL_PROJECT_SQUAD_V2` 是通过专门的导入路径（而非 `save_team`），则影响极小。但如果不统一，维护两份角色 schema 是技术债务。
- **建议**：为 `roles` 定义清晰的 schema，确保预设和运行时的字段一致。

### B36: 超大字典定义 — 严重程度：低
- **问题**：`PRESET_TEAMS` 是一个巨大的嵌套字典（~400行），纯 Python 数据。没有懒加载，每次 import 都全部解析。
- **影响**：启动时内存占用和解析开销，但现代 Python 开销可忽略。
- **建议**：如果未来预设变得更大，考虑改为 JSON 文件 + 懒加载。

### B37: `CATEGORIES` 与 `PRESET_TEAMS` 的 key 一致性无保证 — 严重程度：低
- **问题**：`PRESET_TEAMS` 的 key（如 "编程与技术"）依赖与 `CATEGORIES` 匹配。如果添加新分类但在 `PRESET_TEAMS` 中没有对应条目，UI 可能显示空列表。
- **影响**：不影响崩溃，但 UX 可能不佳。
- **建议**：添加测试校验 `CATEGORIES.keys() == PRESET_TEAMS.keys()`。

---

## 九、presets/souls.py

### B38: 灵魂预设结构简单，无明显 bug — 严重程度：无
- **问题**：`DEFAULT_SOUL_PRESETS` 结构简洁，所有字段与数据库 schema (`soul_presets`) 匹配。无发现问题。
- **建议**：无。

### B39: `soul_codex_context` 命名混淆 — 严重程度：低
- **问题**：名为 "Codex 上下文压缩协议"，但提到的是 OpenAI Codex 的上下文压缩概念，与项目中用的模型无关。新用户可能困惑。
- **影响**：仅影响文档可读性。
- **建议**：重命名为更通用的名字，如 "上下文压缩协议"。

---

## 十、skills/registry.py

### B40: `FunctionTool` 使用 `skill.fn.__doc__` 作为 description — 严重程度：中
- **问题**：`build_tools()` 中 `description=skill.fn.__doc__ or ""`。如果函数的 docstring 包含多行，只有第一行有意义（FunctionTool 的描述通常是简短字符串）。而且如果函数被装饰器包装（如 `@tool`），`__doc__` 可能被修改或丢失。
- **影响**：某些工具的 description 可能是多行且包含格式标记，导致 LLM 混淆。
- **建议**：使用 `skill.desc`（注册时传入的描述）替代 `skill.fn.__doc__`，或者在构造 `SkillInfo` 时优先使用显式描述。

### B41: `build_tools()` 静默跳过未知 skill_id — 严重程度：中
- **问题**：注释说 "silently skips unknowns"。如果用户配置中写错了工具名（typo），系统不会报错，Agent 会缺少关键工具而用户不知道原因。
- **影响**：调试困难——用户配置了工具但没生效，无任何提示。
- **建议**：至少记录 warning 日志，或使用 `strict` 参数控制是否抛出异常。

### B42: `build_tool_specs()` 截断到 8000 字符 — 严重程度：低
- **问题**：`return (...)[:8000]` —— 如果工具很多，描述会被硬截断，可能切断在 tool spec 中间导致格式错误。
- **影响**：仅在工具极多时（>80个描述）出现，但当前只有 ~45 个工具，暂时安全。
- **建议**：至少截断在换行符 `\n` 处，确保最后一条是完整的。

### B43: `SkillRegistry` 的 `_skills` 是 `OrderedDict` 但无排序逻辑 — 严重程度：低
- **问题**：使用 `OrderedDict` 但没有显式排序，依赖注册顺序。Python 3.7+ 普通 `dict` 也保持插入顺序。
- **影响**：无实际影响，`OrderedDict` 在 Python 3.7+ 是多余的（除非需要 `move_to_end` 等操作）。
- **建议**：改用普通 `dict` 或添加 `reversed()` 等需要 OrderedDict 特性的操作。

### B44: 全局单例 `_registry` 无线程安全 — 严重程度：低
- **问题**：`get_registry()` 使用 `global _registry` + `if _registry is None` 模式。如果两个线程同时首次调用 `get_registry()`，可能创建两个实例（虽然概率极低）。
- **影响**：概率极低，且 tools 注册通常在启动时单线程完成。
- **建议**：使用 `threading.Lock` 或模块级初始化（在文件末尾直接 `_registry = SkillRegistry()`）。

---

## 十一、skills/__init__.py

### B45: `tool_mermaid_mindmap` 作为内联函数但缺乏注册上下文 — 严重程度：低
- **问题**：`tool_mermaid_mindmap` 定义在 `__init__.py` 中，与其他从 `skills.builtin.*` 导入的函数风格不一致。这个函数极其简单（纯字符串拼接），但作为模块入口的顶级定义可能干扰代码组织。
- **影响**：无功能影响，属于代码组织问题。
- **建议**：移到 `skills/builtin/charts.py` 与其他图表工具放在一起。

### B46: `tool_mermaid_mindmap` 无输入校验 — 严重程度：低
- **问题**：`nodes` 参数直接 `splitlines()` 处理后拼接到 Mermaid 语法中。如果 `nodes` 包含 Mermaid 特殊字符（如 `(`、`)`、`[`、`]`），可能破坏 Mermaid 语法。
- **影响**：生成的 Mermaid 块可能渲染失败。
- **建议**：对特殊字符做转义或至少加文档说明。

### B47: `register_all_skills()` 是一个巨大的函数 — 严重程度：低
- **问题**：51 个 `register_skill()` 调用在一个函数中，无任何分组或循环。
- **影响**：添加新工具时需要手动添加注册行，容易遗漏。
- **建议**：使用注册表模式（如装饰器）自动注册，或至少按类别拆分注册逻辑。

### B48: `register_all_skills()` 导入所有子模块 — 严重程度：低
- **问题**：函数开头导入了所有 builtin 子模块（`file_ops`、`shell`、`python_exec` 等），即使调用者可能不需要全部工具。延迟导入（lazy import）可能更好。
- **影响**：启动时间略微增加，但如果某些模块有重量级依赖（如 `matplotlib` 在 charts 中），会导致所有用户都需要安装这些依赖。
- **建议**：将注册改为按需加载，或者确保所有依赖都是可选的（当前 charts 工具依赖 matplotlib）。

---

## 汇总

| 严重程度 | 数量 | 编号 |
|---------|------|------|
| 🔴 高 | 5 | B1, B6, B25, B34, B35 |
| 🟡 中 | 10 | B2, B5, B7, B8, B14, B15, B20, B23, B31, B40, B41 |
| 🟢 低 | 28 | 其余 |

### 必须立即修复（高严重性）：
1. **B34** — 预设团队的 `mode` 字段与数据库 `chat_style` 字段不匹配，导致 round_robin 模式丢失
2. **B35** — `PARALLEL_PROJECT_SQUAD_V2` 的 `skills`/`model_id` 字段在角色 schema 中未被标准化处理
3. **B25** — 删除团队不清理关联的 sessions 和 runs
4. **B6** — API Key 使用 base85 编码而非加密存储
5. **B1** — 多线程场景下 SQLite 连接安全问题（如果项目是多线程的话）

### 建议优先修复（中严重性）：
- **B7/B8/B14** — API Key 安全相关（keyring 静默回退、环境变量混用、文件权限）
- **B15/B20/B23** — 数据写入无校验导致静默数据丢失
- **B31/B40/B41** — 工具注册与实际调用的不一致性

---

*审计完毕。共发现 48 个问题。*
