"""Custom tool management — register user-defined Python functions as Agent tools.

Custom tools are stored in the DB and can be compiled into callable functions
with proper type hints so AutoGen's FunctionTool can generate valid schemas.

Architecture:
  User code (def run(...):) → compile → wrap with type hints → FunctionTool → registry
"""

import json, sys, os, traceback, inspect
from pathlib import Path
from typing import Callable, Any

from data.database import get_db, db_transaction


def list_custom_tools() -> list[dict]:
    """List all custom tools from DB."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM custom_tools ORDER BY name").fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["parameters"] = json.loads(d.get("parameters_json", "[]"))
        except Exception:
            d["parameters"] = []
        results.append(d)
    return results


def save_custom_tool(tool_id: str, name: str, description: str,
                     code: str, parameters: list = None) -> str:
    """Save or update a custom tool. Returns tool_id."""
    import uuid
    from datetime import datetime
    tid = tool_id or f"utool_{uuid.uuid4().hex[:8]}"
    params_json = json.dumps(parameters or [], ensure_ascii=False)
    now = datetime.now().isoformat(timespec="seconds")

    with db_transaction() as conn:
        existing = conn.execute("SELECT 1 FROM custom_tools WHERE id = ?", (tid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE custom_tools SET name=?, description=?, code=?, "
                "parameters_json=?, updated_at=? WHERE id=?",
                (name.strip(), description.strip(), code, params_json, now, tid),
            )
        else:
            conn.execute(
                "INSERT INTO custom_tools (id, name, description, code, "
                "parameters_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (tid, name.strip(), description.strip(), code, params_json, now, now),
            )
    return tid


def delete_custom_tool(tool_id: str) -> bool:
    """Delete a custom tool."""
    with db_transaction() as conn:
        conn.execute("DELETE FROM custom_tools WHERE id = ?", (tool_id,))
    return True


def _compile_user_code(code: str) -> Callable | None:
    """Compile user code and extract the 'run' function.

    The user MUST define a function like:
        def run(query: str, count: int = 5) -> str:
            ...
    
    Type hints are REQUIRED — AutoGen uses them to generate the function schema.
    If the user wrote `def run(params):` (single dict param), we wrap it.
    """
    local_ns: dict[str, Any] = {}
    safe_builtins = {
        'print': print, 'len': len, 'str': str, 'int': int, 'float': float,
        'bool': bool, 'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
        'range': range, 'enumerate': enumerate, 'zip': zip, 'map': map,
        'filter': filter, 'sorted': sorted, 'reversed': reversed, 'min': min,
        'max': max, 'sum': sum, 'abs': abs, 'round': round, 'isinstance': isinstance,
        'json': json, 'Path': Path, 'True': True, 'False': False, 'None': None,
        'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
    }
    safe_imports = {
        'json': json, 'os': os, 'sys': sys, 're': __import__('re'),
        'datetime': __import__('datetime'), 'math': __import__('math'),
        'random': __import__('random'), 'hashlib': __import__('hashlib'),
        'base64': __import__('base64'), 'csv': __import__('csv'),
        'itertools': __import__('itertools'), 'collections': __import__('collections'),
        'functools': __import__('functools'), 'urllib': __import__('urllib'),
        'urllib.request': __import__('urllib.request'),
    }
    local_ns.update(safe_imports)
    local_ns['__builtins__'] = safe_builtins

    try:
        exec(code, local_ns)
    except Exception:
        traceback.print_exc()
        return None

    fn = local_ns.get('run')
    if not callable(fn):
        return None
    return fn


def build_custom_tool_function(code: str) -> Callable | None:
    """Build a callable from user code, ensuring it has valid type hints
    so AutoGen's FunctionTool can generate a proper schema.

    Supports two user code styles:
    1. Modern (recommended): def run(query: str, count: int = 5) -> str: ...
    2. Legacy: def run(params): ...  → auto-wrapped with type hints
    """
    fn = _compile_user_code(code)
    if fn is None:
        return None

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())

    # Check for legacy style: single 'params' parameter with no type hint
    is_legacy = (
        len(params) == 1
        and params[0].name == 'params'
        and params[0].annotation is inspect.Parameter.empty
    )

    if is_legacy:
        # Wrap legacy dict-based function into a **kwargs bridge for AutoGen
        # AutoGen will pass all params as keyword args; we collect them into a dict
        def _legacy_bridge(**kwargs) -> str:
            result = fn(kwargs)
            return str(result) if not isinstance(result, str) else result

        return _legacy_bridge

    # Modern style: check that all params have type hints
    missing = [p.name for p in params if p.annotation is inspect.Parameter.empty]
    if missing:
        # Warn but don't block — AutoGen will use "any" type
        pass

    return fn


def test_custom_tool(code: str, test_params: dict = None) -> dict:
    """Test-run a custom tool and return result."""
    fn = build_custom_tool_function(code)
    if fn is None:
        return {"ok": False, "result": "Function compilation failed"}
    try:
        if test_params:
            result = fn(**test_params)
        else:
            result = fn()
        return {"ok": True, "result": str(result)[:5000]}
    except Exception as e:
        return {"ok": False, "result": f"Execution error: {e}\n{traceback.format_exc()[:2000]}"}


def register_custom_tool_to_registry(tool_id: str) -> bool:
    """Compile a custom tool from DB and register it in the global skill registry.
    Returns True on success."""
    tools = list_custom_tools()
    ct = None
    for t in tools:
        if t["id"] == tool_id:
            ct = t
            break
    if not ct:
        return False

    fn = build_custom_tool_function(ct["code"])
    if fn is None:
        return False

    from autogen_core.tools import FunctionTool
    from skills.registry import get_registry

    # Build FunctionTool with proper schema
    desc = ct.get("description", "") or ct.get("name", "")
    ft = FunctionTool(fn, name=ct["id"], description=desc)

    # Register into global registry so agents can use it
    get_registry().register(
        ct["id"], ct["name"], fn, desc
    )
    return True


def unregister_custom_tool(tool_id: str) -> None:
    """Remove a custom tool from the global registry."""
    from skills.registry import get_registry
    reg = get_registry()
    if tool_id in reg.list_all():
        del reg._skills[tool_id]


def get_custom_tools_for_agent(skill_ids: list[str]) -> list:
    """Build FunctionTool objects for custom tools matching given skill IDs."""
    from autogen_core.tools import FunctionTool

    tools = []
    all_custom = list_custom_tools()
    for ct in all_custom:
        if ct["id"] not in skill_ids:
            continue
        fn = build_custom_tool_function(ct["code"])
        if fn is None:
            continue
        tools.append(FunctionTool(
            fn, name=ct["id"],
            description=ct.get("description", ct.get("name", ""))
        ))
    return tools
