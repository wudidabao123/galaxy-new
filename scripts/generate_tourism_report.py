"""
Qianshan Tourism Development Research Report Generator
=======================================================
Uses Galaxy's parallel project squad to collaboratively produce
a comprehensive PDF report on Qianshan (潜山) tourism development.

5-STAGE PIPELINE:
  Stage 1: RESEARCH - 3 agents search web in parallel (tourism data, culture, policies)
  Stage 2: ANALYSIS - 2 agents analyze findings (SWOT, market trends)
  Stage 3: CONTENT  - 3 agents write chapters in parallel (overview, resources, strategy)
  Stage 4: CHARTS   - 2 agents generate charts and find images
  Stage 5: ASSEMBLY - 1 agent assembles final markdown + exports PDF

Usage:
  E:/gitpro/AutoGen/.venv/Scripts/python.exe scripts/generate_tourism_report.py

Prerequisites:
  - DeepSeek API key configured in Galaxy Models tab (stored in keyring)
  - Internet access for web search
  - Python packages: streamlit, autogen, keyring, matplotlib, pillow
"""

from __future__ import annotations
import sys, os, json, uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DATA_DIR, GENERATED_DIR, RUNS_DIR
from data.database import init_db
from data.model_store import list_models, get_default_model, get_model_api_key
from data.team_store import get_team, save_team, list_teams
from skills import register_all_skills
from core.agent_factory import create_agents_for_team
from core.orchestrator import run_parallel_stages
from core.context import compact_history

_TZ = timezone(timedelta(hours=8))

# ── Stage definitions ────────────────────────────────────

PARALLEL_PROJECT_SQUAD = {
    "id": "tourism_report_squad",
    "name": "Tourism Report Squad",
    "category": "Parallel Work",
    "chat_style": "parallel",
    "max_turns": 5,
    "desc": "5-stage pipeline for Qianshan tourism report",
    "roles": [
        {   # RESEARCHER
            "name": "researcher",
            "model_id": "",  # filled at runtime
            "prompt": """你是一位资深旅游行业研究员。你的任务:
1. 用 web_search 搜索"潜山 旅游 发展 2025 2026"
2. 搜索"天柱山 游客 数据 收入"
3. 搜索"潜山 文化旅游 非遗 民宿"
4. 搜索"安徽 旅游 政策 乡村振兴"
5. 把所有搜索到的数据、事实、数字整理成结构化笔记。
6. 每一条信息标注来源。
最终输出 JSON: {"status":"done","summary":"...","files_read":[],"files_changed":[],"handoff_summary":"提炼的20条关键数据和事实"}
""",
            "skills": ["web_search", "fetch_url", "current_datetime", "read_file", "write_file"],
        },
        {   # DATA ANALYST
            "name": "analyst",
            "model_id": "",
            "prompt": """你是旅游数据分析师。基于研究员提供的搜索数据:
1. 提取关键指标: 游客量、旅游收入、增长率
2. 分析潜山旅游资源分类 (自然景观、文化遗产、休闲度假)
3. 做SWOT分析 (优势/劣势/机会/威胁)
4. 用 chart_bar 生成关键数据对比柱状图
5. 用 mermaid_mindmap 生成旅游资源分布思维导图
输出结构化JSON + 图表。
""",
            "skills": ["web_search", "chart_bar", "chart_line", "mermaid_mindmap",
                       "read_file", "write_file", "calculator", "current_datetime"],
        },
        {   # CONTENT WRITER - Chapter 1 & 2
            "name": "writer_intro",
            "model_id": "",
            "prompt": """你是旅游报告主编。请撰写报告的前两章:
## 第一章: 潜山旅游发展概况
- 地理区位和交通优势
- 核心旅游资源 (天柱山 5A、山谷流泉、三祖寺等)
- 近年旅游发展成就和数据

## 第二章: 旅游资源深度分析
- 自然景观资源 (地质奇观、生态资源)
- 文化遗产资源 (禅宗文化、戏曲文化、非遗)
- 休闲度假资源 (民宿、康养、户外运动)

每章不少于800字，数据引用研究员提供的具体数字。
将内容保存为 generated/tourism_ch1_2.md
""",
            "skills": ["write_file", "read_file", "read_many_files", "web_search", "current_datetime"],
        },
        {   # CONTENT WRITER - Chapter 3 & 4
            "name": "writer_strategy",
            "model_id": "",
            "prompt": """你是旅游规划专家。请撰写报告的后两章:
## 第三章: 市场分析与竞争定位
- 客源市场分析 (省内/长三角/全国)
- 竞争对比 (与黄山、九华山、庐山对比)
- 目标客群画像

## 第四章: 发展战略与实施路径
- "十四五"旅游发展战略定位
- 产品创新 (夜游经济、研学旅游、康养度假)
- 营销推广策略 (新媒体、节庆活动)
- 基础设施和服务提升
- 可持续发展与生态保护

每章不少于800字，引用分析师提供的SWOT和市场数据。
将内容保存为 generated/tourism_ch3_4.md
""",
            "skills": ["write_file", "read_file", "web_search", "mermaid_mindmap", "current_datetime"],
        },
        {   # DESIGNER
            "name": "designer",
            "model_id": "",
            "prompt": """你是报告设计师。请:
1. 用 chart_line 生成"潜山近5年游客量增长趋势"折线图
2. 用 chart_bar 生成"潜山旅游资源分类占比"柱状图
3. 用 mermaid_mindmap 生成"潜山旅游发展全景"思维导图
4. 用 web_search 找到潜山天柱山的代表性图片描述 (用于配图)
5. 设计报告封面文案和排版建议
将图表描述和路径整理为 generated/tourism_design.md
""",
            "skills": ["chart_line", "chart_bar", "mermaid_mindmap",
                       "write_file", "web_search", "current_datetime"],
        },
        {   # ASSEMBLER
            "name": "assembler",
            "model_id": "",
            "prompt": """你是报告总编。请将前面所有章节和图表组装成完整的调研报告:
1. 读取 generated/tourism_ch1_2.md
2. 读取 generated/tourism_ch3_4.md
3. 读取 generated/tourism_design.md
4. 组装为完整 Markdown 报告，包含:
   - 封面 (标题、副标题、日期、编制单位)
   - 目录
   - 第一章到第四章正文
   - 图表插入位置 (用markdown图片语法引用图表路径)
   - 结论与建议
   - 参考文献
5. 保存完整报告到 generated/qianshan_tourism_report.md
6. 用 export_markdown_pdf 导出PDF
输出最终文件路径。
""",
            "skills": ["read_file", "read_many_files", "write_file",
                       "export_markdown_pdf", "file_info", "current_datetime", "chart_line", "chart_bar", "mermaid_mindmap", "web_search", "fetch_url"],
        },
    ],
    "parallel_stages": [
        {"name": "Stage 1: Research", "roles": ["researcher"]},
        {"name": "Stage 2: Analysis", "roles": ["analyst"]},
        {"name": "Stage 3: Content", "roles": ["writer_intro", "writer_strategy"]},
        {"name": "Stage 4: Design", "roles": ["designer"]},
        {"name": "Stage 5: Assembly", "roles": ["assembler"]},
    ],
}

# ── Main ─────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Qianshan Tourism Report Generator")
    print("  5-Stage Parallel Pipeline")
    print("=" * 60)

    # 1. Initialize infrastructure
    print("\n[1/5] Initializing Galaxy infrastructure...")
    init_db()
    register_all_skills()
    print("  DB + Skills ready.")

    # 2. Find model with API key
    print("\n[2/5] Finding configured model...")
    models = list_models()
    if not models:
        print("ERROR: No models configured. Please add a model in Galaxy UI first.")
        print("  Open Galaxy → Models tab → Add model with API Key")
        sys.exit(1)

    # Find first model with a working API key
    model_id = None
    model_cfg = None
    api_key = None
    for m in models:
        mid = m["id"]
        key = get_model_api_key(mid)
        if key:
            model_id = mid
            model_cfg = m
            api_key = key
            break

    if not api_key:
        default = get_default_model()
        if default:
            key = get_model_api_key(default["id"])
            if key:
                model_id = default["id"]
                model_cfg = default
                api_key = key

    if not api_key:
        print("ERROR: No model has an API key. Please configure one in Galaxy UI.")
        print("  Models tab → select model → enter API Key → save")
        sys.exit(1)

    print(f"  Using model: {model_cfg['name']} ({model_cfg.get('model', '?')})")

    # 3. Prepare team
    print("\n[3/5] Preparing parallel project squad...")
    squad = dict(PARALLEL_PROJECT_SQUAD)
    for role in squad["roles"]:
        role["model_id"] = model_id

    # Save team to DB (so team_store works)
    existing = list_teams()
    existing_ids = {t["id"] for t in existing}
    if squad["id"] not in existing_ids:
        save_team(squad["id"], squad["name"], squad["roles"],
                  category=squad["category"], chat_style="parallel",
                  max_turns=squad["max_turns"], desc=squad.get("desc", ""),
                  parallel_stages=squad["parallel_stages"])
        print("  Team saved to DB.")
    else:
        print("  Team already exists in DB.")

    # 4. Run pipeline
    print("\n[4/5] Running 5-stage parallel pipeline...")
    print("  This may take several minutes. Each stage runs autonomously.\n")

    initial_history = [{
        "source": "User",
        "content": """请为安徽省潜山市制作一份全面的旅游发展调研报告，包含:
1. 潜山旅游发展概况 (地理位置、旅游资源、近年成就)
2. 旅游资源深度分析 (自然景观、文化遗产、休闲度假)
3. 市场分析与竞争定位 (客源市场、竞争对比、目标客群)
4. 发展战略与实施路径 (产品创新、营销推广、基础设施、可持续发展)
5. 数据图表 (游客量趋势、资源分类、思维导图)
6. 最终输出为图文并茂的Markdown报告和PDF

请先用web_search工具收集潜山旅游相关信息、数据和政策，再进行深度分析和写作。
注意: 2026年5月8日。""",
        "avatar": "",
    }]

    print("  Starting pipeline...\n")
    try:
        stage_results = run_parallel_stages(
            squad,
            initial_history,
            "User",
            max_turns=5,
            workspace_root=PROJECT_ROOT,
            run_id=f"tourism_{uuid.uuid4().hex[:8]}",
        )
    except Exception as e:
        print(f"\nERROR during pipeline execution: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 5. Results
    print("\n[5/5] Pipeline complete!\n")
    print("=" * 60)
    print("  STAGE RESULTS")
    print("=" * 60)

    for stage_data in stage_results:
        stage_name = stage_data["stage_name"]
        print(f"\n--- {stage_name} ---")
        for agent_name, payload in stage_data["results"].items():
            content = str(payload.get("content", "")).strip()
            guard = payload.get("guard")
            status = "PASS" if guard and getattr(guard, "decision", None) and getattr(guard.decision, "value", None) == "pass" else "CHECK"
            print(f"  [{status}] {agent_name}: {len(content)} chars")

    # Check for generated files
    print("\n" + "=" * 60)
    print("  GENERATED FILES")
    print("=" * 60)

    report_md = GENERATED_DIR / "qianshan_tourism_report.md"
    report_pdf = GENERATED_DIR / "qianshan_tourism_report.pdf"

    for f in sorted(GENERATED_DIR.glob("**/*"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        if f.is_file():
            size = f.stat().st_size
            print(f"  {f.relative_to(PROJECT_ROOT)} ({size:,} bytes)")

    if report_md.exists():
        print(f"\n  ✅ Markdown report: {report_md}")
    else:
        print(f"\n  ⚠ Markdown report not found, checking alternatives...")
        for f in GENERATED_DIR.glob("**/*tourism*"):
            print(f"  Found: {f.relative_to(PROJECT_ROOT)}")

    if report_pdf.exists():
        print(f"  ✅ PDF report: {report_pdf}")
    else:
        print(f"  ⚠ PDF not generated. Check if export_markdown_pdf was run.")

    print("\nDone! Open the generated files to view the report.")


if __name__ == "__main__":
    main()
