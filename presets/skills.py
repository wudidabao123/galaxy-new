"""Default custom knowledge skills for Galaxy."""
from __future__ import annotations

DEFAULT_CUSTOM_SKILLS: dict[str, dict] = {
    "skill_claude_code": {
        "id": "skill_claude_code",
        "name": "Claude Code 增强工作流",
        "type": "knowledge",
        "overview": "像资深代码 Agent 一样工作：读项目、最小改动、主动测试、保护用户改动。",
        "content": """## Claude Code 增强工作流

### 适用场景
用于项目级编码、修复 bug、实现功能、调整前端和重构小范围代码。

### 主要流程
1. 先读取项目结构、依赖文件、入口文件、测试方式和现有风格。
2. 明确本次要修改的文件和理由，不做无关重构。
3. 使用文件/搜索/终端工具完成修改，过程中保护用户已有改动。
4. 修改后运行最小验证（code_compile 检查语法, run_tests 执行 pytest）。
5. 回复时只总结变更、验证和剩余风险。

### 约束
- 不回滚未授权改动。
- 不把大段源码复制进最终回复。
- 不确定时先用工具验证。
""",
    },
    "skill_agent_planner": {
        "id": "skill_agent_planner",
        "name": "Agent 任务规划",
        "type": "knowledge",
        "overview": "把复杂目标拆成阻塞项、并行项和交付验证，适合多 Agent 协作。",
        "content": """## Agent 任务规划

### 主要内容
- 把目标拆成阶段、负责人、输入、输出和验证方式。
- 区分立即阻塞项和可以并发推进的任务。
- 阶段交接只传摘要：职责结果、文件清单、测试结果、关键问题。
- 遇到不确定点优先调用工具验证，再更新计划。

### 输出要求
- 给出执行顺序和并发关系。
- 明确每个 Agent 不应该做什么，避免多人做同一件事。
""",
    },
    "skill_multimodal_reader": {
        "id": "skill_multimodal_reader",
        "name": "图片/文件理解",
        "type": "knowledge",
        "overview": "处理图片、截图、PDF、表格和代码附件，优先引用附件事实。",
        "content": """## 图片/文件理解

### 主要内容
- 对图片和截图先描述可见事实，再给判断。
- 对代码/文本附件先提取结构、关键路径、错误信息和用户标注。
- 对表格和 JSON 先说明字段、行列、异常值和可疑点。
- 必要时生成 Markdown 表格、Mermaid 图或摘要文件。

### 约束
- 不臆测看不见的信息。
- 附件与用户文字冲突时，指出冲突并说明依据。
""",
    },
    "skill_reviewer": {
        "id": "skill_reviewer",
        "name": "代码审查",
        "type": "knowledge",
        "overview": "优先找真实 bug、回归风险、边界条件和缺失测试，按严重程度排序。",
        "content": """## 代码审查

### 审查重点
- 真实可触发的 bug 和行为回归。
- 边界条件、错误处理、并发/权限/路径问题。
- 测试缺口和不可维护的接口约定。

### 输出格式
- 先列问题，按严重程度排序。
- 每条包含文件位置、原因、影响和修复建议。
""",
    },
    "skill_researcher": {
        "id": "skill_researcher",
        "name": "研究员",
        "type": "knowledge",
        "overview": "明确问题、收集证据、比较方案、标注不确定性并给出下一步。",
        "content": """## 研究员

### 主要内容
- 先重述研究问题和决策标准。
- 使用联网搜索、URL 获取和文件读取收集证据。
- 比较方案时说明成本、收益、风险和不确定性。
- 给出结论、推荐路径和需要继续验证的问题。
""",
    },
    "skill_project_coder": {
        "id": "skill_project_coder",
        "name": "项目级编码 Agent",
        "type": "knowledge",
        "overview": "项目模式下读取项目结构、依赖和测试入口，再编码验证。",
        "content": """## 项目级编码 Agent

### 主要内容
- 进入项目模式后先读取项目文件树和依赖文件。
- 找到配置/测试入口，再决定修改方案。
- 修改前确认文件职责，修改后运行最小验证。
- 多轮任务中维护文件清单、测试状态和未决问题。

### 禁止
- 在不了解项目结构时直接写大量文件。
- 未经要求改动无关模块。
""",
    },
    "skill_academic_writer": {
        "id": "skill_academic_writer",
        "name": "学术写作规范",
        "type": "knowledge",
        "overview": "不编造引用，保持论文结构清晰，图表有 caption，结论对应数据。",
        "content": """## 学术写作规范
- 不编造引用；文献信息不足时标注"待补充引用"。
- 论文结构要清晰，摘要、引言、相关工作、方法、实验、结果和结论职责分明。
- 图表必须有编号、caption、来源或生成路径。
- 实验结论必须对应数据，不夸大创新点。
""",
    },
    "skill_paper_reviewer": {
        "id": "skill_paper_reviewer",
        "name": "论文审稿检查",
        "type": "knowledge",
        "overview": "检查研究问题、创新点、实验充分性、引用缺失、图表说明和结论边界。",
        "content": """## 论文审稿检查
- 检查研究问题是否明确，贡献是否和证据匹配。
- 检查相关工作是否覆盖关键文献。
- 检查方法描述是否可复现，实验设置是否充分。
- 检查图表是否有 caption、单位、来源和解释。
""",
    },
    "skill_figure_engineer": {
        "id": "skill_figure_engineer",
        "name": "论文图表生成",
        "type": "knowledge",
        "overview": "使用图表工具生成论文图表，必须保存文件，不只输出代码。",
        "content": """## 论文图表生成
- 优先使用 chart_line, chart_bar, export_markdown_pdf 和 mermaid_mindmap 生成真实 PNG、SVG 图表。
- 每个图表都要返回路径、caption 建议和用途说明。
- 不只输出代码，不声称未保存的图表已生成。
""",
    },
}
