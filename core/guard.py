"""Guard system — quality gate for agent outputs.

Checks:
  1. Structured JSON validity
  2. Real git diff vs claimed files_changed
  3. py_compile on changed Python files
  4. Forbidden path detection
  5. Test record completeness
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from core.enums import GuardDecision
from core.schemas import AgentStageResult, GuardResult


def enhanced_guard_check(
    result: AgentStageResult,
    workspace_root: Path,
    run_id: str = "",
    forbidden_paths: list[str] | None = None,
) -> GuardResult:
    """Run enhanced guard checks on an agent's stage result.
    Returns a GuardResult with decision, score, and evidence.
    """
    score = 100
    blocking: list[str] = []
    warnings: list[str] = []
    evidence_parts: list[str] = []

    # ── 1. Structured JSON validity ──
    valid_json = getattr(result, "parsed_json_ok", True)
    if not valid_json:
        score -= 15
        warnings.append("Agent output was not valid structured JSON")
    evidence_parts.append(f"valid_json={valid_json}")

    # ── 2. Status checks ──
    if result.status.value == "failed":
        score = min(score, 40)
        blocking.append("Agent reported failed status")
    if result.status.value == "blocked":
        score = min(score, 50)
        blocking.append("Agent reported blocked status")
    evidence_parts.append(f"status={result.status.value}")

    # ── 3. Summary checks ──
    if not result.summary.strip():
        score -= 10
        warnings.append("Missing summary")
    if not result.handoff_summary.strip():
        score -= 10
        warnings.append("Missing handoff_summary")

    # ── 4. Real git diff check ──
    if result.files_changed:
        real_changes = _get_real_changed_files(workspace_root)
        evidence_parts.append(f"real_git_changes={len(real_changes)}")

        # Check claimed vs real
        claimed = set(str(f).replace("\\", "/") for f in result.files_changed)
        real = set(str(f).replace("\\", "/") for f in real_changes)

        missing_from_claim = real - claimed
        claimed_not_real = claimed - real

        if claimed_not_real:
            score -= 20
            warnings.append(
                f"Agent claims changed files not in git diff: {', '.join(sorted(claimed_not_real)[:5])}"
            )

        if missing_from_claim:
            score -= 10
            warnings.append(
                f"Git diff shows changes not in agent's files_changed: {', '.join(sorted(missing_from_claim)[:5])}"
            )

        if not claimed_not_real and not missing_from_claim:
            evidence_parts.append("git_diff_matches=True")

        # ── 5. py_compile on changed Python files ──
        py_files = [f for f in real_changes if f.endswith(".py")]
        if py_files:
            compile_results = _compile_changed_files(workspace_root, py_files)
            failures = [r for r in compile_results if not r["ok"]]
            if failures:
                score -= 30
                blocking.append(
                    f"py_compile failed on: {', '.join(r['file'] for r in failures[:5])}"
                )
                for f in failures[:3]:
                    evidence_parts.append(f"compile_fail:{f['file']}:{f.get('error','')}")
            else:
                evidence_parts.append(f"py_compile_passed={len(py_files)}")

    # ── 6. Forbidden path check ──
    forbidden = set(forbidden_paths or [])
    if forbidden and result.files_changed:
        # Only match by exact filename, not substring, to prevent false positives
        # like "fp=app" matching "path/to/mapping.py"
        _forbidden_names = {fp.lstrip("/").rstrip("/") for fp in forbidden}
        violations = [
            f for f in result.files_changed
            if Path(str(f)).name in _forbidden_names
        ]
        if violations:
            score = min(score, 30)
            blocking.append(f"Agent modified forbidden paths: {', '.join(violations[:5])}")
            evidence_parts.append(f"forbidden_violations={len(violations)}")

    # ── 7. Test record check ──
    passed_tests = [t for t in result.tests if t.result.value == "passed"]
    missing_tests = bool(result.files_changed) and not result.tests

    # Not test check keywords (English, Chinese, Japanese, etc.)
    _no_test_keywords = ["no test", "not test", "documentation", "无需测试", "不用测试",
                         "不需要测试", "非代码", "not code", "test not", "不要测试"]
    no_test_needed = any(
        kw in (risk.lower() if isinstance(risk, str) else "")
        for risk in result.risks
        for kw in _no_test_keywords
    ) or any(
        kw in result.handoff_summary.lower()
        for kw in _no_test_keywords
    )

    # ── 8. Test record scoring ──
    if not result.tests:
        score -= 15
        warnings.append("No test record")
    elif missing_tests:
        score -= 20
        warnings.append("Files changed but no test records")

    for test in result.tests:
        if test.result.value == "failed":
            score -= 30
            blocking.append(f"Test failed: {test.command}")
        elif test.result.value == "not_run":
            score -= 10
            warnings.append(f"Test not run: {test.command or 'unspecified'}")

    evidence_parts.append(f"tests_total={len(result.tests)}")
    evidence_parts.append(f"tests_passed={len(passed_tests)}")

    # ── 9. Risk penalty ──
    if result.risks:
        penalty = min(20, len(result.risks) * 5)
        score -= penalty
        warnings.extend(result.risks)

    # ── 10. Path escape check ──
    suspicious = [
        p for p in result.files_changed
        if ".." in str(p).replace("\\", "/").split("/")
    ]
    if suspicious:
        blocking.append("Changed path appears to escape workspace")
        score = min(score, 40)

    # ── Decision ──
    score = max(0, min(100, score))
    changed_without_passed = bool(result.files_changed) and not passed_tests and not no_test_needed

    if blocking:
        decision = GuardDecision.BLOCK if score < 60 else GuardDecision.RETRY
    elif missing_tests or changed_without_passed:
        decision = GuardDecision.RETRY
    elif score >= 80:
        decision = GuardDecision.PASS
    elif score >= 60:
        decision = GuardDecision.RETRY
    else:
        decision = GuardDecision.BLOCK

    evidence = "; ".join(evidence_parts)
    retry_instruction = ""
    if decision == GuardDecision.RETRY:
        if missing_tests or changed_without_passed:
            retry_instruction = (
                "Add tests for changed files, or explain why tests aren't needed."
            )
        else:
            retry_instruction = "Fix the guard warnings and ensure valid structured JSON output."

    return GuardResult(
        decision=decision,
        score=score,
        pass_=decision == GuardDecision.PASS,
        blocking_issues=blocking,
        warnings=warnings,
        retry_instruction=retry_instruction,
        evidence=evidence,
    )


# ── Helpers ───────────────────────────────────────────

def _get_real_changed_files(root: Path) -> list[str]:
    """Get files changed in working tree via git diff + untracked files.

    Combines git diff --name-only (tracked changes) AND
    git ls-files --others --exclude-standard (untracked/new files).
    Without untracked detection, agents creating new files completely
    bypass the guard's file change verification.
    """
    result = []
    try:
        # Tracked changes
        proc = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(root),
            text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=10,
        )
        if proc.returncode == 0:
            result.extend(line.strip() for line in proc.stdout.splitlines() if line.strip())
        # Untracked files (new files not yet git-added)
        proc2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(root),
            text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=10,
        )
        if proc2.returncode == 0:
            result.extend(line.strip() for line in proc2.stdout.splitlines() if line.strip())
    except Exception:
        pass
    return result


def _compile_changed_files(root: Path, files: list[str]) -> list[dict[str, Any]]:
    """Syntax-check Python files without executing them.

    Uses ast.parse() instead of py_compile.compile() to avoid executing
    module-level code (import side effects, malicious __main__ guards, etc.).
    """
    import ast
    results = []
    for f in files:
        full = root / f
        if not full.exists():
            results.append({"file": f, "ok": False, "error": "file not found"})
            continue
        try:
            source = full.read_text(encoding="utf-8", errors="replace")
            ast.parse(source, filename=str(full))
            results.append({"file": f, "ok": True})
        except SyntaxError as e:
            results.append({"file": f, "ok": False, "error": f"SyntaxError: {e.msg} (line {e.lineno}, col {e.offset})"})
        except Exception as e:
            results.append({"file": f, "ok": False, "error": str(e)})
    return results
