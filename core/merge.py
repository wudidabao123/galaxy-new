
def auto_merge_paper(project_id, workspace_root=None):
    """Automatically merge all section markdown files into paper.md.
    This is the fallback if integration agent fails to call academic_markdown_save."""
    from pathlib import Path
    import re
    
    if workspace_root is None:
        from skills.builtin.file_ops import _get_workspace_root
        workspace_root = _get_workspace_root()
    
    sections_dir = Path(workspace_root) / 'generated' / 'academic' / project_id / 'sections'
    if not sections_dir.exists():
        return None, "Sections directory not found"
    
    sections = sorted(sections_dir.glob('*.md'), key=lambda p: p.stat().st_mtime)
    if not sections:
        return None, "No section files found"
    
    # Read metadata for title
    meta_path = Path(workspace_root) / 'generated' / 'academic' / project_id / 'project.json'
    title = "研究报告"
    if meta_path.exists():
        try:
            import json
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            title = meta.get('title', title)
        except:
            pass
    
    # Build merged paper
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("> 本文由 Galaxy 多智能体系统自动生成")
    lines.append("")
    
    # TOC
    lines.append("## 目录")
    lines.append("")
    for i, sec in enumerate(sections, 1):
        sec_name = sec.stem
        lines.append(f"{i}. {sec_name}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    total_cjk = 0
    total_chars = 0
    
    for i, sec in enumerate(sections, 1):
        content = sec.read_text(encoding='utf-8', errors='replace')
        cjk_count = len(re.findall(r'[\u4e00-\u9fff]', content))
        
        lines.append(f"## 第{i}章 {sec.stem}")
        lines.append("")
        lines.append(content.strip())
        lines.append("")
        
        total_cjk += cjk_count
        total_chars += len(content)
    
    # References section
    refs_path = Path(workspace_root) / 'generated' / 'academic' / project_id / 'references.json'
    if refs_path.exists():
        try:
            refs = json.loads(refs_path.read_text(encoding='utf-8'))
            if refs:
                lines.append("## 参考文献")
                lines.append("")
                for r in refs:
                    lines.append(f"- {r.get('citation', r.get('text', str(r)))}")
                lines.append("")
        except:
            pass
    
    # Save
    paper_path = Path(workspace_root) / 'generated' / 'academic' / project_id / 'paper.md'
    paper_path.write_text('\n'.join(lines), encoding='utf-8')
    
    return paper_path, f"Merged {len(sections)} sections, {total_cjk} CJK chars, {total_chars} total chars"
