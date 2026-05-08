"""Export tools — DOCX, PDF, LaTeX, ZIP."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

from config import GENERATED_DIR
PAPER_CSS = """
@page {
    size: A4;
    margin: 2.5cm 2cm 2cm 2cm;
    @bottom-center {
        content: counter(page);
        font-size: 10pt;
        font-family: 'SimSun', serif;
    }
}
body {
    font-family: 'SimSun', 'Microsoft YaHei', 'Noto Sans CJK SC', serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #333;
}
h1 {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 18pt;
    text-align: center;
    margin-bottom: 1.5cm;
    page-break-before: avoid;
}
h2 {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 15pt;
    margin-top: 1.5em;
    margin-bottom: 0.8em;
    border-bottom: 1px solid #aaa;
    padding-bottom: 0.3em;
}
h3 {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 13pt;
    margin-top: 1.2em;
}
p {
    text-indent: 2em;
    margin: 0.5em 0;
    text-align: justify;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 10.5pt;
}
table th {
    background-color: #4472C4;
    color: white;
    padding: 6px 8px;
    border: 1px solid #999;
}
table td {
    padding: 5px 8px;
    border: 1px solid #999;
}
table tr:nth-child(even) {
    background-color: #f2f2f2;
}
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
    page-break-inside: avoid;
}
figure {
    page-break-inside: avoid;
    margin: 1em auto;
    text-align: center;
}
figcaption {
    font-size: 10pt;
    color: #666;
    margin-top: 0.5em;
}
blockquote {
    border-left: 4px solid #4472C4;
    padding-left: 1em;
    margin: 1em 0;
    color: #555;
    background: #f8f9fa;
    page-break-inside: avoid;
}
code {
    font-family: 'Courier New', monospace;
    background: #f4f4f4;
    padding: 1px 4px;
    font-size: 10.5pt;
}
pre {
    background: #f8f9fa;
    padding: 1em;
    border: 1px solid #ddd;
    overflow-x: auto;
    font-size: 10pt;
    page-break-inside: avoid;
}
ul, ol {
    margin: 0.5em 0;
    padding-left: 2em;
}
li {
    margin: 0.3em 0;
}
"""


EXPORTS_DIR = GENERATED_DIR / "exports"


def _ensure_exports() -> None:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Markdown exports ──────────────────────────────────

def tool_export_docx(markdown_path: str, output_name: str = "") -> str:
    """Convert a Markdown file to DOCX. Uses python-docx if available, otherwise pandoc.
    Args: markdown_path (relative to workspace), output_name (optional).
    """
    from skills.builtin.file_ops import _get_workspace_root

    root = _get_workspace_root()
    src = root / markdown_path
    if not src.exists():
        return f"Error: file not found: {markdown_path}"

    _ensure_exports()
    name = output_name or src.stem
    dest = EXPORTS_DIR / f"{name}_{uuid.uuid4().hex[:6]}.docx"

    # Try python-docx first
    try:
        from docx import Document
        doc = Document()
        text = src.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            doc.add_paragraph(line)
        doc.save(str(dest))
        return json.dumps({"path": str(dest), "method": "python-docx"}, ensure_ascii=False)
    except ImportError:
        pass

    # Fallback to pandoc
    try:
        proc = subprocess.run(
            ["pandoc", str(src), "-o", str(dest)],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            return json.dumps({"path": str(dest), "method": "pandoc"}, ensure_ascii=False)
        return f"Error: pandoc failed — {proc.stderr}"
    except FileNotFoundError:
        return "Error: neither python-docx nor pandoc is available. Install one: pip install python-docx"


def tool_export_markdown_pdf(markdown_path: str, output_name: str = "") -> str:
    """Convert a Markdown file to a well-formatted PDF with CJK support.
    Uses weasyprint + markdown for best quality. Includes images and tables.
    Args: markdown_path (relative to workspace).
    """
    from skills.builtin.file_ops import _get_workspace_root

    root = _get_workspace_root()
    src = root / markdown_path
    if not src.exists():
        return f"Error: file not found: {markdown_path}"

    _ensure_exports()
    name = output_name or src.stem
    dest = EXPORTS_DIR / f"{name}_{uuid.uuid4().hex[:6]}.pdf"

    # ── Method 1: weasyprint + markdown (best quality, subprocess with 60s timeout) ──
    try:
        # Use a subprocess to avoid blocking the main process indefinitely
        pdf_script = f'''
import sys, json
from pathlib import Path
src = Path(r"{src.as_posix()}")
dest = Path(r"{dest.as_posix()}")
md_text = src.read_text(encoding="utf-8", errors="replace")
import markdown as _md
from weasyprint import HTML
css = r"""{PAPER_CSS}"""
html_body = _md.markdown(
    md_text,
    extensions=['tables', 'fenced_code', 'toc', 'nl2br', 'sane_lists']
)
html = f"<html><head><meta charset=\"utf-8\"><style>{{css}}</style></head><body>{{html_body}}</body></html>"
HTML(string=html).write_pdf(str(dest))
size = dest.stat().st_size
print(json.dumps({{"path": str(dest), "method": "weasyprint", "size": size}}, ensure_ascii=False))
'''
        proc = subprocess.run(
            [sys.executable, "-c", pdf_script],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0 and dest.exists():
            return proc.stdout.strip()
        # If subprocess failed, fall through to Method 2
    except subprocess.TimeoutExpired:
        # Subprocess timed out — fall through to Method 2
        pass
    except ImportError:
        pass
    except Exception:
        pass

    # ── Method 1b: direct weasyprint (fallback if subprocess approach fails) ──
    try:
        import markdown as _md
        from weasyprint import HTML

        md_text = src.read_text(encoding="utf-8", errors="replace")
        
        # CSS for academic paper style with CJK font stack
        css = """
@page {
    size: A4;
    margin: 2.5cm 2cm 2.5cm 2cm;
    @bottom-center {
        content: counter(page);
        font-family: 'SimSun', 'Microsoft YaHei', serif;
        font-size: 9pt;
    }
}
body {
    font-family: 'SimSun', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #222;
}
h1 {
    font-family: 'SimHei', 'Microsoft YaHei', 'PingFang SC', sans-serif;
    font-size: 18pt;
    text-align: center;
    margin-bottom: 24pt;
    border-bottom: 2px solid #333;
    padding-bottom: 12pt;
}
h2 {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 14pt;
    margin-top: 20pt;
    margin-bottom: 10pt;
    border-bottom: 1px solid #999;
    padding-bottom: 4pt;
}
h3 {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 12pt;
    margin-top: 16pt;
}
h4 {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 11pt;
}
p { text-indent: 2em; margin: 6pt 0; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 16pt 0;
    font-size: 10pt;
}
table th {
    background: #4472C4;
    color: white;
    padding: 6pt 8pt;
    border: 1px solid #4472C4;
}
table td {
    padding: 4pt 8pt;
    border: 1px solid #ccc;
}
img {
    max-width: 100%;
    height: auto;
    margin: 12pt auto;
    display: block;
}
blockquote {
    border-left: 3px solid #4472C4;
    padding: 8pt 16pt;
    margin: 12pt 0;
    background: #f5f7fa;
    font-size: 10pt;
}
code {
    font-family: 'Consolas', monospace;
    font-size: 9pt;
    background: #f0f0f0;
    padding: 1pt 4pt;
}
ul, ol { margin: 8pt 0; }
li { margin: 4pt 0; }
"""
        # Convert markdown to HTML
        html_body = _md.markdown(
            md_text,
            extensions=['tables', 'fenced_code', 'toc', 'nl2br', 'sane_lists']
        )
        html = f"""<html><head><meta charset="utf-8">
<style>{css}</style></head><body>{html_body}</body></html>"""
        
        HTML(string=html).write_pdf(str(dest))
        return json.dumps({"path": str(dest), "method": "weasyprint", "size": dest.stat().st_size}, ensure_ascii=False)
    except ImportError as e:
        pass  # fall through
    except Exception as e:
        pass  # fall through

    # ── Method 2: reportlab with CJK font ──
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.enums import TA_LEFT

        # Register CJK font — search common Windows/macOS paths
        cjk_font_path = None
        candidates = [
            "C:/Windows/Fonts/simsun.ttc",    # 宋体 (Windows)
            "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑 (Windows)
            "C:/Windows/Fonts/simhei.ttf",      # 黑体 (Windows)
        ]
        for fp in candidates:
            if Path(fp).exists():
                cjk_font_path = fp
                break

        if cjk_font_path:
            try:
                pdfmetrics.registerFont(TTFont('CJK', cjk_font_path))
                style = ParagraphStyle('CJKStyle', fontName='CJK', fontSize=11, leading=18)
            except Exception:
                style = getSampleStyleSheet()["Normal"]
        else:
            style = getSampleStyleSheet()["Normal"]

        text = src.read_text(encoding="utf-8", errors="replace")
        doc = SimpleDocTemplate(str(dest), pagesize=A4)
        story = [Paragraph(line.replace("&", "&amp;").replace("<", "&lt;"), style)
                 for line in text.splitlines() if line.strip()]
        doc.build(story)
        return json.dumps({"path": str(dest), "method": "reportlab"}, ensure_ascii=False)
    except ImportError:
        return "Error: neither pandoc nor reportlab is available."


# ── LaTeX ─────────────────────────────────────────────

def tool_export_latex_article(project_id: str, title: str, author: str,
                               abstract: str, sections_json: str) -> str:
    """Save a LaTeX article (main.tex + references.bib) for a paper project.
    Args: project_id, title, author, abstract, sections_json (JSON array of {title, content}).
    """
    from skills.builtin.academic import _project_dir

    proj = _project_dir(project_id)
    if not proj.exists():
        return f"Error: project {project_id} not found"

    try:
        sections = json.loads(sections_json)
    except json.JSONDecodeError as e:
        return f"Error: {e}"

    tex = f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath, amssymb}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\geometry{{a4paper, margin=1in}}

\\title{{{title}}}
\\author{{{author}}}
\\date{{\\today}}

\\begin{{document}}
\\maketitle

\\begin{{abstract}}
{abstract}
\\end{{abstract}}

"""
    for s in sections:
        tex += f"\\section{{{s.get('title', 'Untitled')}}}\n{s.get('content', '')}\n\n"

    tex += "\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"

    (proj / "main.tex").write_text(tex, encoding="utf-8")
    if not (proj / "references.bib").exists():
        (proj / "references.bib").write_text("", encoding="utf-8")

    return f"LaTeX article saved to {proj / 'main.tex'}"


def tool_export_latex_pdf(project_id: str) -> str:
    """Compile a paper project's main.tex to PDF using xelatex or pdflatex.
    Args: project_id."""
    from skills.builtin.academic import _project_dir

    proj = _project_dir(project_id)
    tex_file = proj / "main.tex"
    if not tex_file.exists():
        return f"Error: main.tex not found in project {project_id}"

    for engine in ["xelatex", "pdflatex"]:
        try:
            proc = subprocess.run(
                [engine, "-interaction=nonstopmode", "main.tex"],
                cwd=str(proj), capture_output=True, text=True, timeout=60,
            )
            pdf = proj / "main.pdf"
            if pdf.exists():
                return json.dumps({"path": str(pdf), "engine": engine}, ensure_ascii=False)
        except FileNotFoundError:
            continue

    return "Error: neither xelatex nor pdflatex found. Install TeX Live or MiKTeX."


def tool_export_paper_zip(project_id: str) -> str:
    """Package an entire paper project into a ZIP file.
    Args: project_id."""
    from skills.builtin.academic import _project_dir

    proj = _project_dir(project_id)
    if not proj.exists():
        return f"Error: project {project_id} not found"

    _ensure_exports()
    zip_path = EXPORTS_DIR / f"{project_id}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in proj.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(proj))

    return json.dumps({"path": str(zip_path), "size": zip_path.stat().st_size}, ensure_ascii=False)
