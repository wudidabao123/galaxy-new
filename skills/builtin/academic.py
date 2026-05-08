"""Academic writing tools — paper projects, sections, citations, figures, exports."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from config import GENERATED_DIR


ACADEMIC_DIR = GENERATED_DIR / "academic"


def _ensure_academic() -> None:
    ACADEMIC_DIR.mkdir(parents=True, exist_ok=True)


def _project_dir(project_id: str) -> Path:
    return ACADEMIC_DIR / project_id


# ── Project Management ────────────────────────────────

def tool_academic_project_create(title: str, lang: str = "zh") -> str:
    """Create a new academic paper project directory. Returns project_id.
    Args: title (paper title), lang ('zh' or 'en')."""
    _ensure_academic()
    pid = uuid.uuid4().hex[:12]
    proj_dir = _project_dir(pid)
    sections_dir = proj_dir / "sections"
    exports_dir = proj_dir / "exports"
    for d in [proj_dir, sections_dir, exports_dir]:
        d.mkdir(parents=True, exist_ok=True)

    project = {
        "project_id": pid,
        "title": title,
        "lang": lang,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sections": [],
        "references": [],
        "exports": [],
    }
    (proj_dir / "paper_project.json").write_text(
        json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return json.dumps({"project_id": pid, "path": str(proj_dir)}, ensure_ascii=False, indent=2)


def tool_academic_section_save(project_id: str, section_name: str, content: str) -> str:
    """Save a paper section to the project's sections/ directory.
    Args: project_id, section_name (e.g. '引言', 'introduction'), content (Markdown)."""
    proj = _project_dir(project_id)
    if not proj.exists():
        return f"Error: project {project_id} not found"
    sections_dir = proj / "sections"
    sections_dir.mkdir(exist_ok=True)
    safe = section_name.replace("/", "_").replace("\\", "_")
    path = sections_dir / f"{safe}.md"
    path.write_text(content, encoding="utf-8")
    return f"Section saved: {path} ({len(content)} chars)"


def tool_academic_markdown_save(project_id: str, content: str) -> str:
    """Save the full paper as a single Markdown file in the project directory.
    Args: project_id, content (full paper Markdown)."""
    proj = _project_dir(project_id)
    if not proj.exists():
        return f"Error: project {project_id} not found"
    path = proj / "paper.md"
    path.write_text(content, encoding="utf-8")
    return f"Paper saved: {path} ({len(content)} chars)"


def tool_academic_outline_generate(title: str, sections_json: str, lang: str = "zh") -> str:
    """Generate a paper outline template from a title and section list.
    Args: title, sections_json (JSON array of section titles), lang ('zh'/'en').
    """
    try:
        sections = json.loads(sections_json)
    except json.JSONDecodeError:
        return "Error: sections_json must be a valid JSON array of strings"

    if lang == "en":
        lines = [f"# {title}", "", "## Abstract", "", "## 1. Introduction", ""]
        for i, s in enumerate(sections, 2):
            lines.append(f"## {i}. {s}")
            lines.append("")
        lines.extend(["## References", ""])
    else:
        lines = [f"# {title}", "", "## 摘要", "", "## 1. 引言", ""]
        for i, s in enumerate(sections, 2):
            lines.append(f"## {i}. {s}")
            lines.append("")
        lines.extend(["## 参考文献", ""])
    return "\n".join(lines)


def tool_academic_table_generate(headers_json: str, rows_json: str, caption: str = "") -> str:
    """Generate a three-line (academic style) Markdown table.
    Args: headers_json (JSON array of column names), rows_json (JSON array of row arrays), caption."""
    try:
        headers = json.loads(headers_json)
        rows = json.loads(rows_json)
    except json.JSONDecodeError as e:
        return f"Error: {e}"

    lines = []
    if caption:
        lines.append(f"**Table:** {caption}")
    lines.append("| " + " | ".join(str(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


# ── References ────────────────────────────────────────

def tool_academic_reference_add(project_id: str, bibtex: str) -> str:
    """Add a BibTeX reference to the paper project. Parses and validates.
    Args: project_id, bibtex (full BibTeX entry)."""
    proj = _project_dir(project_id)
    if not proj.exists():
        return f"Error: project {project_id} not found"

    # Extract citation key
    import re as _re
    match = _re.search(r"@\w+\{([^,]+)", bibtex)
    cite_key = match.group(1).strip() if match else "unknown"

    ref_path = proj / "references.bib"
    existing = ref_path.read_text(encoding="utf-8", errors="replace") if ref_path.exists() else ""

    if cite_key in existing:
        return f"Reference '{cite_key}' already exists. Not duplicated."

    ref_path.write_text((existing + "\n" + bibtex.strip() + "\n").strip() + "\n", encoding="utf-8")
    return f"Reference added: '{cite_key}'\nPath: {ref_path}"


def tool_citation_check(project_id: str) -> str:
    """Check all citations in a paper project for missing required fields.
    Reports issues like missing author, year, title, journal.
    Args: project_id."""
    import re as _re

    proj = _project_dir(project_id)
    if not proj.exists():
        return f"Error: project {project_id} not found"

    ref_path = proj / "references.bib"
    if not ref_path.exists():
        return "No references.bib found in project."

    text = ref_path.read_text(encoding="utf-8", errors="replace")
    entries = _re.split(r"\n(?=@)", text)

    results = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        match = _re.search(r"@(\w+)\{([^,]+)", entry)
        if not match:
            results.append({"type": "unknown", "key": "?", "issues": ["Cannot parse entry"]})
            continue
        etype = match.group(1)
        key = match.group(2)

        issues = []
        if "author" not in entry.lower() and "editor" not in entry.lower():
            issues.append("Missing author/editor")
        if "year" not in entry.lower() and "date" not in entry.lower():
            issues.append("Missing year/date")
        if "title" not in entry.lower():
            issues.append("Missing title")
        if etype == "article" and "journal" not in entry.lower():
            issues.append("Missing journal (article type)")

        results.append({
            "type": etype, "key": key,
            "status": "ok" if not issues else "issues",
            "issues": issues,
        })

    return json.dumps(results, ensure_ascii=False, indent=2)


# ── Paper Assets ──────────────────────────────────────

def tool_paper_assets_list(project_id: str) -> str:
    """List all files in a paper project: sections, figures, references, exports.
    Args: project_id."""
    proj = _project_dir(project_id)
    if not proj.exists():
        return f"Error: project {project_id} not found"

    files = []
    for p in sorted(proj.rglob("*")):
        if p.is_file():
            rel = p.relative_to(proj)
            files.append({
                "path": str(rel).replace("\\", "/"),
                "size": p.stat().st_size,
                "type": p.suffix or "(no ext)",
            })

    return json.dumps({
        "project_id": project_id,
        "file_count": len(files),
        "files": files,
    }, ensure_ascii=False, indent=2)


def tool_figure_caption_generate(figure_path: str, context: str = "") -> str:
    """Generate a draft figure caption suggestion based on context.
    Does not modify files. Use to get caption ideas.
    Args: figure_path (relative path in project), context (what the figure shows).
    """
    fname = Path(figure_path).stem.replace("_", " ").replace("-", " ")
    templates = {
        "chart": f"Figure X: {context or fname}. Data source: [待补充].",
        "architecture": f"Figure X: System architecture of {context or fname}.",
        "flowchart": f"Figure X: Flowchart of the {context or fname} process.",
        "comparison": f"Figure X: Comparison of {context or fname} across different methods.",
    }
    # Simple heuristic
    if any(kw in figure_path.lower() for kw in ["chart", "plot", "curve", "bar", "line"]):
        return templates["chart"]
    elif any(kw in figure_path.lower() for kw in ["arch", "system", "component"]):
        return templates["architecture"]
    elif any(kw in figure_path.lower() for kw in ["flow", "method", "process"]):
        return templates["flowchart"]
    else:
        return f"Figure X: {context or fname}. [Caption needs manual review.]"


def tool_doc_outline_extract(file_path: str) -> str:
    """Extract the heading structure (outline) from a Markdown file.
    Args: file_path (relative path in workspace)."""
    from skills.builtin.file_ops import _get_workspace_root

    root = _get_workspace_root()
    full = root / file_path
    if not full.exists():
        return f"Error: file not found: {file_path}"

    text = full.read_text(encoding="utf-8", errors="replace")
    import re as _re
    headings = []
    for line in text.splitlines():
        m = _re.match(r"^(#{1,6})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            headings.append(f"{'  ' * (level - 1)}- {m.group(2)}")

    if not headings:
        return "No headings found in file."
    return f"# Outline: {file_path}\n\n" + "\n".join(headings)
