"""Skill registration for Galaxy New.

Import this module to register all built-in tools into the global registry.
Call register_all_skills() once at startup.
"""

from skills.registry import register_skill

from skills.builtin.file_ops import (
    tool_read_file, tool_write_file, tool_write_base64_file,
    tool_list_files, tool_search_text, tool_read_many_files,
    tool_replace_in_file, tool_file_info, tool_make_directory,
    tool_safe_delete,
)
from skills.builtin.shell import tool_terminal, tool_run_script
from skills.builtin.python_exec import (
    tool_python_run, tool_calculator, tool_json_parse,
    tool_text_stats, tool_code_compile, tool_run_tests,
)
from skills.builtin.web import (
    tool_fetch_url, tool_web_search, tool_extract_links_from_url,
    tool_download_file, tool_download_image, tool_current_datetime,
)
from skills.builtin.env_manager import tool_env_check, tool_env_install
from skills.builtin.git_tools import (
    tool_git_diff, tool_git_status, tool_project_tree_summary,
    tool_dependency_scan,
)
from skills.builtin.patch_tools import (
    tool_patch_preview, tool_patch_apply, tool_patch_reject,
)
from skills.builtin.contract_tools import (
    tool_contract_write, tool_contract_read, tool_contract_summary,
)
from skills.builtin.handoff_tools import tool_handoff_write, tool_handoff_read
from skills.builtin.snapshot_tools import tool_workspace_snapshot, tool_conflict_check
from skills.builtin.academic import (
    tool_academic_project_create, tool_academic_section_save,
    tool_academic_markdown_save, tool_academic_outline_generate,
    tool_academic_table_generate, tool_academic_reference_add,
    tool_citation_check, tool_paper_assets_list,
    tool_figure_caption_generate, tool_doc_outline_extract,
)
from skills.builtin.charts import (
    tool_chart_line, tool_chart_bar,
    tool_chart_confusion_matrix, tool_chart_training_curves,
    tool_mermaid_mindmap, tool_mermaid_flowchart,
)
from skills.builtin.export import (
    tool_export_docx, tool_export_markdown_pdf,
    tool_export_latex_article, tool_export_latex_pdf,
    tool_export_paper_zip,
)

# ── Registration ──────────────────────────────────────

def register_all_skills() -> None:
    """Register all built-in tools into the global skill registry."""

    # File Ops
    register_skill("read_file", "读取文件", tool_read_file,
                   "读取工作区文本文件内容")
    register_skill("write_file", "写入文件", tool_write_file,
                   "在工作区写入文本文件")
    register_skill("write_base64_file", "写入二进制文件", tool_write_base64_file,
                   "把 base64 内容写为二进制文件")
    register_skill("list_files", "文件列表", tool_list_files,
                   "列出工作区文件，支持 glob 模式")
    register_skill("search_text", "全文搜索", tool_search_text,
                   "在项目文件里搜索文本或正则")
    register_skill("read_many_files", "批量读取文件", tool_read_many_files,
                   "一次读取多个文本文件")
    register_skill("replace_in_file", "精确替换", tool_replace_in_file,
                   "对单文件做精确文本替换")
    register_skill("file_info", "文件信息", tool_file_info,
                   "查看文件/目录元数据和哈希")
    register_skill("make_directory", "创建目录", tool_make_directory,
                   "创建项目目录")
    register_skill("safe_delete", "安全删除", tool_safe_delete,
                   "移动文件到回收目录(.trash/)，可恢复")

    # Shell
    register_skill("terminal", "终端执行", tool_terminal,
                   "执行 Shell 命令（自动检测 bash/powershell/cmd）")
    register_skill("run_script", "运行脚本", tool_run_script,
                   "运行 .py/.sh/.ps1 脚本，自动检测解释器")

    # Python
    register_skill("python", "Python 执行器", tool_python_run,
                   "执行 Python 代码片段")
    register_skill("calculator", "计算器", tool_calculator,
                   "数学表达式求值")
    register_skill("json", "JSON 解析", tool_json_parse,
                   "解析 JSON 字符串查看结构")
    register_skill("text", "文本分析", tool_text_stats,
                   "统计文本字数、行数、阅读时间")
    register_skill("code_compile", "编译检查", tool_code_compile,
                   "对 Python 文件运行 py_compile 检查语法")
    register_skill("run_tests", "运行测试", tool_run_tests,
                   "运行 pytest 等测试命令")

    # Web
    register_skill("current_datetime", "当前日期时间", tool_current_datetime,
                   "获取当前日期/时间/星期/时区")
    register_skill("fetch_url", "网页/API 获取", tool_fetch_url,
                   "获取 URL 文本内容")
    register_skill("web_search", "联网搜索", tool_web_search,
                   "用 DuckDuckGo/Bing 搜索并抓取网页摘要")
    register_skill("extract_links_from_url", "网页链接提取", tool_extract_links_from_url,
                   "读取网页 HTML 提取图片/文档/链接")
    register_skill("download_file", "下载网络文件", tool_download_file,
                   "从 URL 下载文件到 generated/downloads/")
    register_skill("download_image", "下载网络图片", tool_download_image,
                   "下载图片到 generated/images/")

    # Env
    register_skill("env_check", "环境检查", tool_env_check,
                   "列出当前 Python 环境、已安装包、conda 环境")
    register_skill("env_install", "安装依赖包", tool_env_install,
                   "用 pip install 安装缺失的 Python 包")

    # Git / Project
    register_skill("git_diff", "Git 状态/Diff", tool_git_diff,
                   "查看 git status 和 diff")
    register_skill("git_status", "Git 简要状态", tool_git_status,
                   "显示 git status 摘要")
    register_skill("project_tree_summary", "项目结构摘要", tool_project_tree_summary,
                   "生成项目目录树摘要，避免盲目探索")
    register_skill("dependency_scan", "依赖扫描", tool_dependency_scan,
                   "扫描 requirements.txt/pyproject.toml/package.json")

    # Patch
    register_skill("patch_preview", "Patch 预览", tool_patch_preview,
                   "预览 unified diff 会改哪些文件")
    register_skill("patch_apply", "Patch 应用", tool_patch_apply,
                   "应用 unified diff 到工作区")
    register_skill("patch_reject", "Patch 拒绝", tool_patch_reject,
                   "拒绝 patch 并保存到 generated/patches/")

    # Contract
    register_skill("contract_write", "写任务契约", tool_contract_write,
                   "PM 写并发任务契约")
    register_skill("contract_read", "读任务契约", tool_contract_read,
                   "Agent 读当前 run 的契约")
    register_skill("contract_summary", "契约摘要", tool_contract_summary,
                   "快速读取契约中的 Agent 分工摘要")

    # Handoff
    register_skill("handoff_write", "写阶段交接", tool_handoff_write,
                   "写阶段交接文件")
    register_skill("handoff_read", "读阶段交接", tool_handoff_read,
                   "读上一阶段交接文件")

    # Snapshot
    register_skill("workspace_snapshot", "工作区快照", tool_workspace_snapshot,
                   "保存当前工作区文件状态的快照")
    register_skill("conflict_check", "冲突检查", tool_conflict_check,
                   "检查两个 Agent 是否修改同一文件")

    # Mermaid
    register_skill("mermaid_mindmap", "思维导图", tool_mermaid_mindmap,
                   "生成 Mermaid mindmap 代码块")
    register_skill("mermaid_flowchart", "流程图", tool_mermaid_flowchart,
                   "生成 Mermaid flowchart 代码块")

    # Academic
    register_skill("academic_project_create", "创建论文项目", tool_academic_project_create,
                   "创建论文项目目录和元数据")
    register_skill("academic_markdown_save", "保存论文 Markdown", tool_academic_markdown_save,
                   "保存完整论文 Markdown")
    register_skill("academic_section_save", "保存论文章节", tool_academic_section_save,
                   "保存单章节目录到 paper project")
    register_skill("academic_reference_add", "添加 BibTeX 参考文献", tool_academic_reference_add,
                   "解析并保存 BibTeX 引用")
    register_skill("academic_outline_generate", "生成论文大纲", tool_academic_outline_generate,
                   "生成中英文论文大纲模板")
    register_skill("academic_table_generate", "生成三线表 Markdown", tool_academic_table_generate,
                   "用 JSON 生成学术三线表")
    register_skill("citation_check", "引用检查", tool_citation_check,
                   "检查论文引用缺少哪些必填字段")
    register_skill("paper_assets_list", "论文资产列表", tool_paper_assets_list,
                   "列出论文项目所有文件")
    register_skill("figure_caption_generate", "图注生成", tool_figure_caption_generate,
                   "根据图表路径和上下文生成 caption 草稿")
    register_skill("doc_outline_extract", "文档大纲提取", tool_doc_outline_extract,
                   "从 Markdown 提取标题大纲")

    # Charts
    register_skill("chart_line", "生成折线图", tool_chart_line,
                   "用 matplotlib 生成 PNG 折线图")
    register_skill("chart_bar", "生成柱状图", tool_chart_bar,
                   "用 matplotlib 生成 PNG 柱状图")
    register_skill("chart_confusion_matrix", "生成混淆矩阵", tool_chart_confusion_matrix,
                   "用 matplotlib 生成 PNG 混淆矩阵")
    register_skill("chart_training_curves", "生成训练曲线", tool_chart_training_curves,
                   "用训练历史 JSON 生成 PNG 曲线图")

    # Export
    register_skill("export_docx", "Markdown 导出 DOCX", tool_export_docx,
                   "将 Markdown 导出为 DOCX")
    register_skill("export_markdown_pdf", "Markdown 导出 PDF", tool_export_markdown_pdf,
                   "将 Markdown 导出为 PDF")
    register_skill("export_latex_article", "保存 LaTeX Article", tool_export_latex_article,
                   "保存 main.tex 和 references.bib")
    register_skill("export_latex_pdf", "LaTeX 编译 PDF", tool_export_latex_pdf,
                   "用 xelatex/pdflatex 编译 PDF")
    register_skill("export_paper_zip", "打包论文项目", tool_export_paper_zip,
                   "把论文项目目录打包为 zip")
