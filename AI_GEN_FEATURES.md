# AI 生成功能开发摘要

## 日期
2026-05-08

## 修改文件
- `ui/skills.py` — 新增共享 AI 调用辅助函数 + AI 生成工具代码
- `ui/config_ui.py` — 新增 AI 生成灵魂 MD + AI 生成自定义技能
- `ui/teams.py` — 新增 AI 自动匹配团队

## 需求1: AI 生成工具代码 (ui/skills.py tab2)

在"新建工具"表单上方添加了 `🤖 AI 生成工具` expander：
- 用户输入工具描述（自然语言）
- 选择模型（从已有模型列表选，默认使用默认模型）
- 点击"🤖 生成代码"调 LLM 生成完整 Python `def run(params):` 函数
- 生成结果显示代码、名称、描述，点击"📋 填入新建表单"自动填充到下方表单
- 无模型时给出提示
- 新增函数 `_ai_generate_tool(user_desc, model_id)`

## 需求2: AI 生成灵魂 MD (ui/config_ui.py 灵魂 MD 预设区域)

在"新增灵魂 MD"表单上方添加了 `🤖 AI 生成灵魂 MD` expander：
- 用户输入灵魂描述（如"一个严格追求代码质量的资深架构师..."）
- 选择模型
- LLM 生成名称、概述、完整 Markdown 内容
- 点击"📋 填入新建表单"自动填充
- 新增函数 `_ai_generate_soul(user_desc, model_id)`

## 需求3: AI 生成自定义技能 (ui/config_ui.py 自定义技能管理区域)

在"新建自定义技能"表单上方添加了 `🤖 AI 生成技能` expander：
- 用户描述需求的技能
- LLM 生成技能名称、概述、内容（含适用场景、工作流程、约束条件、输出格式）
- 点击"📋 填入新建表单"自动填充
- 新增函数 `_ai_generate_skill(user_desc, model_id)`

## 需求4: 快速操作自动匹配团队 (ui/teams.py 快速操作区域)

保留了原有的"快速执行"功能（直接跳转 chat），同时新增 `🤖 AI 匹配团队` expander：
- 用户输入任务描述
- LLM 从所有已注册团队中推荐最匹配的 1-3 个
- 显示团队名称 + 推荐理由
- 点击"✅ 选择"自动跳转到该团队编辑页
- 如果现有团队都不合适，显示建议使用"AI 创建团队"功能
- 新增函数 `_ai_match_team(user_desc, teams)`

## 共享辅助函数 (ui/skills.py)

- `_ai_call_json(prompt, system)` — 调默认模型 API，返回解析后的 JSON dict
- `_ai_call_to_text(prompt, system, model_id)` — 调指定模型 API，返回纯文本（供灵魂 MD 和技能生成用）

## 设计约束

- 所有 AI 按钮执行前检查模型是否配置
- `_ai_call_to_text` 支持指定 model_id 参数用于模型选择
- 不修改现有功能（原有表单和流程保持不变）
- 所有生成结果需用户手动确认后再填入表单（非自动覆盖）

## 验证

- 三个文件均通过 `py_compile.compile(..., doraise=True)` 验证
- `git add` 暂存，未 commit
