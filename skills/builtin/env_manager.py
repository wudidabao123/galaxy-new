"""Environment management tools — pip/conda detection, package installation."""

from __future__ import annotations

import subprocess
import sys


def _clip_output(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


def tool_env_check() -> str:
    """List current Python environment: version, executable path, installed packages,
    and available conda environments. Use before installing anything."""
    import json as _json

    info = {
        "python_version": sys.version,
        "executable": sys.executable,
        "platform": sys.platform,
    }

    # Installed packages
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            pkgs = _json.loads(proc.stdout)
            info["installed_packages"] = [
                f"{p['name']}=={p['version']}" for p in pkgs[:200]
            ]
            info["package_count"] = len(pkgs)
        else:
            info["installed_packages"] = ["(pip list failed)"]
    except Exception as e:
        info["installed_packages"] = [f"Error: {e}"]

    # Conda environments (if available)
    try:
        proc = subprocess.run(
            ["conda", "env", "list"],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0:
            info["conda_envs"] = proc.stdout.strip()
    except Exception:
        info["conda_envs"] = "(conda not available)"

    return _json.dumps(info, ensure_ascii=False, indent=2)


def tool_env_install(package: str) -> str:
    """Install a pip package into the current Python environment.
    Use this when you detect a missing dependency. Only one package per call.
    Args: package — package name, optionally with version (e.g. 'requests' or 'requests==2.28').
    """
    # Safety check
    name = package.strip()
    if not name:
        return "Error: no package specified"
    if any(c in name for c in [";", "&&", "||", "|", "`", "$"]):
        return "Error: package name contains unsafe characters"

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", name],
            capture_output=True, text=True, timeout=120,
        )
        output = []
        output.append(f"exit_code={proc.returncode}")
        if proc.stdout:
            output.append("[stdout]\n" + proc.stdout)
        if proc.stderr:
            output.append("[stderr]\n" + proc.stderr)
        return _clip_output("\n".join(output))
    except subprocess.TimeoutExpired:
        return "Error: pip install timed out after 120s"
    except Exception as e:
        return f"Error: {e}"
