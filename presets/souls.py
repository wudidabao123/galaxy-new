"""Default soul MD presets."""
from __future__ import annotations

DEFAULT_SOUL_PRESETS: dict[str, dict] = {
    "soul_claude_code": {
        "id": "soul_claude_code",
        "name": "CLAUDE.md 同款项目规则",
        "overview": "让 Agent 像 Claude Code 一样先读项目、保护用户改动、最小修改并主动验证。",
        "content": """# CLAUDE.md / Galaxy Project Rules

## 工作原则
- 先理解项目结构、依赖、入口、测试方式，再修改文件。
- 永远不要回滚用户已有改动；遇到不属于本任务的改动，保持原样。
- 优先做最小可验证修改，避免顺手重构。
- 写代码前说明将修改的文件和原因；写完后运行最小验证。

## 工具使用
- 搜索用全文搜索/文件列表，读关键文件后再动手。
- 修改文件后用 Git diff 或文件读取确认结果。
- 能跑测试就跑测试；不能跑时说明原因和剩余风险。

## 输出格式
- 简洁说明改了什么、验证了什么、还有什么风险。
- 生成产物时给出相对路径。
""",
    },
    "soul_codex_context": {
        "id": "soul_codex_context",
        "name": "Codex 上下文压缩协议",
        "overview": "长任务中保留目标、约束、文件清单、测试结果和未决问题。",
        "content": """# Context Compaction Protocol

## 何时压缩
- 历史很长、工具输出很多、出现大段源码/CSS/日志时。

## 压缩保留
- 用户目标和最新指令。
- 已修改/创建的文件清单。
- 每个 Agent 的职责结果。
- 测试命令、结果、失败原因。
- 关键约束、接口约定、未决问题。

## 压缩丢弃
- 完整工具日志。
- 大段重复源码。
- 已解决的中间推理和废弃方案。
""",
    },
    "soul_parallel_handoff": {
        "id": "soul_parallel_handoff",
        "name": "多 Agent 阶段交接",
        "overview": "并发团队每阶段只交接摘要：职责结果、文件清单、测试结果、关键问题。",
        "content": """# Parallel Handoff Rules

## 阶段输出
每个阶段输出以下四块：
1. 职责结果：本角色完成/判断了什么。
2. 文件清单：创建、修改、读取的重要文件路径。
3. 测试结果：运行了什么命令，结果如何。
4. 关键问题：阻塞、风险、接口不一致、需要下一阶段关注的点。

## 禁止
- 不把完整 CSS/JS/HTML/日志复制给下一阶段。
- 不越权完成别的 Agent 的职责。
- 不改变 PM 指定的文件命名和接口约定。
""",
    },
}
