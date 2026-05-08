"""Python execution tools — run Python code, compile, run tests."""

from __future__ import annotations

import contextlib
import io
import math
import subprocess
import sys
from pathlib import Path


def _clip_output(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


# ── Python Exec ───────────────────────────────────────

def tool_python_run(code: str) -> str:
    """Execute Python code and return the output. Use to test algorithms, do calculations, or process data.
    The code must be a complete, safe Python snippet. Prints are captured."""
    import builtins as _bltin
    safe_builtins = {
        k: getattr(_bltin, k) for k in [
            'abs','all','any','ascii','bin','bool','bytearray','bytes','callable','chr',
            'complex','dict','divmod','enumerate','filter','float','format','frozenset',
            'getattr','hasattr','hash','hex','int','isinstance','issubclass','iter',
            'len','list','map','max','min','next','object','oct','ord','pow','print',
            'range','repr','reversed','round','set','slice','sorted','str','sum',
            'tuple','type','zip','Exception','ValueError','TypeError','KeyError',
            'IndexError','StopIteration','True','False','None','Ellipsis','NotImplemented',
        ]
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            exec(code, {"__builtins__": safe_builtins}, {})
        result = buf.getvalue()
        return result if result.strip() else "(code ran, no output)"
    except Exception as e:
        return f"Error: {e}\n{buf.getvalue()}"


def tool_calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the result.
    Supports: +, -, *, /, **, sqrt, sin, cos, tan, log, abs, round, pi, e, pow."""
    try:
        allowed = {
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
            "tan": math.tan, "log": math.log, "abs": abs, "round": round,
            "pi": math.pi, "e": math.e, "pow": pow,
        }
        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def tool_json_parse(json_str: str) -> str:
    """Parse a JSON string and return a formatted summary (keys, types, length)."""
    import json as _json
    try:
        data = _json.loads(json_str)
        if isinstance(data, list):
            return f"JSON array, {len(data)} items. Keys: {list(data[0].keys()) if data and isinstance(data[0], dict) else 'N/A'}"
        elif isinstance(data, dict):
            return f"JSON object, keys: {list(data.keys())}"
        else:
            return f"JSON value: {type(data).__name__} = {str(data)[:200]}"
    except _json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"


def tool_text_stats(text: str) -> str:
    """Analyze text: count characters, words, lines, and estimate reading time."""
    chars = len(text)
    words = len(text.split())
    lines = text.count("\n") + 1
    minutes = max(1, words // 200)
    return f"Chars: {chars} | Words: {words} | Lines: {lines} | Reading: ~{minutes} min"


# ── Code Compile ──────────────────────────────────────

def tool_code_compile(path: str) -> str:
    """Run python -m py_compile on a Python file to check for syntax errors.
    Use this to verify your changes before declaring them done."""
    from skills.builtin.file_ops import _get_workspace_root
    import py_compile as _py_compile

    workspace = _get_workspace_root()
    full_path = workspace / path
    if not full_path.exists():
        return f"Error: file not found: {path}"
    if full_path.suffix.lower() != ".py":
        return f"Error: not a Python file: {path}"

    try:
        _py_compile.compile(str(full_path), doraise=True)
        return f"py_compile passed: {path}"
    except _py_compile.PyCompileError as e:
        return f"Error: py_compile failed for {path}: {e}"
    except Exception as e:
        return f"Error: {e}"


# ── Run Tests ─────────────────────────────────────────

def tool_run_tests(command: str = "pytest", timeout_seconds: int = 120) -> str:
    """Run the project's test command in the active workspace and return output."""
    from skills.builtin.shell import tool_terminal
    return tool_terminal(command, timeout_seconds=timeout_seconds)
