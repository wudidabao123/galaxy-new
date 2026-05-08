"""Galaxy New — Global configuration constants and runtime directories."""

from __future__ import annotations

import os
from pathlib import Path

# ── Project root ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.resolve()
# Workspace — where agents create files (separate from project code)
_DATA_DIR_ENV = os.environ.get("GALAXY_DATA_DIR", "").strip()
if _DATA_DIR_ENV:
    _WORKSPACE_PATH = Path(_DATA_DIR_ENV).expanduser()
elif os.environ.get("GALAXY_PORTABLE", "").strip() == "1":
    _WORKSPACE_PATH = PROJECT_ROOT / "workspace"
else:
    _WORKSPACE_PATH = PROJECT_ROOT.parent / "Galaxy_workspace"
DATA_DIR = _WORKSPACE_PATH

# ── Directories ───────────────────────────────────────
UPLOADS_DIR = DATA_DIR / "uploads"
GENERATED_DIR = DATA_DIR / "generated"
RUNS_DIR = DATA_DIR / "runs"
CONTRACTS_DIR = GENERATED_DIR / "contracts"
HANDOFFS_DIR = GENERATED_DIR / "handoffs"
DIFFS_DIR = GENERATED_DIR / "diffs"
PATCHES_DIR = GENERATED_DIR / "patches"
AVATARS_DIR = DATA_DIR / "avatars"
TEMPLATES_DIR = DATA_DIR / "templates"

# ── Database ──────────────────────────────────────────
# DB stays in project root (it's project metadata, not agent workspace)
DB_PATH = PROJECT_ROOT / "galaxy.db"
RUNTIME_DIRS = [
    UPLOADS_DIR, GENERATED_DIR, RUNS_DIR,
    CONTRACTS_DIR, HANDOFFS_DIR, DIFFS_DIR, PATCHES_DIR,
    AVATARS_DIR,
    # DB dir stays in project root
    PROJECT_ROOT,
]


def ensure_runtime_dirs() -> None:
    """Create runtime directories used by the app."""
    for path in RUNTIME_DIRS:
        path.mkdir(parents=True, exist_ok=True)

# ── Agent limits ──────────────────────────────────────
MAX_AGENT_TURNS = 200
MAX_GUARD_RETRIES = 2
DEFAULT_CONTEXT_LENGTH = 128000
CONTEXT_COMPACT_RATIO = 0.55

# ── Chat attachment types ─────────────────────────────
CHAT_ATTACHMENT_TYPES = [
    "png", "jpg", "jpeg", "webp", "gif", "bmp",
    "txt", "md", "json", "csv", "tsv", "py", "js", "ts", "tsx",
    "html", "css", "xml", "yaml", "yml", "toml", "ini", "log",
    "pdf", "docx", "xlsx", "pptx", "zip",
]

# ── Known OpenAI models ───────────────────────────────
KNOWN_OPENAI = {
    "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "o4-mini", "o3-mini",
    "o3", "o1", "o1-mini", "o1-pro", "chatgpt-4o-latest",
}

# ── Manual tool protocol models ──────────────────────
MANUAL_TOOL_MODELS = {"deepseek-v4-pro", "deepseek-reasoner"}

# ── Dangerous shell patterns (always blocked) ────────
DANGEROUS_SHELL_PATTERNS: list[tuple[str, str]] = [
    # Unix/Linux/macOS
    (r"\brm\s+-(?:rf|fr|r\s*-f|f\s*-r)\b", "rm -rf"),
    (r"\brm\s+--recursive\s+--force\b", "rm --recursive --force"),
    (r"\bmkfs\b", "mkfs"),
    (r"\bshutdown\s+", "shutdown"),
    # Windows cmd
    (r"\bdel\b.*\s/[sfq]+", "del /s /f /q"),
    (r"\brmdir\b.*\s/[sq]+", "rmdir /s /q"),
    (r"\bformat\s+[a-zA-Z]:", "format drive"),
    (r"\bdiskpart\b", "diskpart"),
    (r"\breg\s+(delete|add)", "reg delete/add"),
    (r"\bregedit\b", "regedit (registry editor)"),
    # PowerShell
    (r"\bremove-item\b.*-(?:recurse|r)", "Remove-Item -Recurse"),
    (r"\bri\s+-r\s+-fo\b", "ri -r -fo (PowerShell alias)"),
    (r"\bdel\s+-r\s+-fo\b", "del -r -fo (PowerShell alias)"),
    # PowerShell encrypted download (Invoke-WebRequest -OutFile / IWR -OutFile)
    (r"invoke-webrequest.*-outfile", "Invoke-WebRequest -OutFile (download)"),
    (r"\biwr\b.*-outfile", "IWR -OutFile (PowerShell download alias)"),
    # Service operations
    (r"\bsc\s+(stop|delete)\b", "sc stop/delete (service control)"),
    (r"\bnet\s+stop\b", "net stop (service stop)"),
    # Scheduled tasks
    (r"\bschtasks\b", "schtasks (scheduled task manipulation)"),
    # Base64-encoded PowerShell (common bypass) — covers -EncodedCommand, -enc, -e
    (r"-(?:enc|e)(?:odedcommand)?\s+[A-Za-z0-9+/=]{20,}", "Base64-encoded PowerShell"),
]

# ── Agent colors / avatars ────────────────────────────
AGENT_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#F7DC6F", "#6C5CE7", "#00B894", "#E17055",
    "#A29BFE", "#FD79A8", "#00CEC9", "#FDCB6E", "#74B9FF",
    "#E056A0", "#55E6C1", "#F8A5C2", "#63CDDA", "#CF6A87",
]

AGENT_AVATARS = ["🤖","🔍","💡","✍🏻",
                 "🎯","📝","🧠","⚡","🔥","🌟"]

USER_AVATAR = "👤"

AVATAR_EMOJIS = [
    "🤖","🔍","💡","✍🏻","🎯","📝","🧠","⚡","🔥","🌟",
    "😊","🤔","👨‍💻","👩‍💻","🦸","🧙","👑","🎭","🎪","🎨",
    "🔬","🚀","💎","🌈","🦊","🐱","🐶","🦄","🌺","🍀",
    "⭐","🌙","☀️","🌊","🏔️","🎵","📚","🔧","💰","🛡️",
    "⚔️","🏆","🎓","💼","🎤","📡","🔮","🧿","🌍","🦾",
    "👁️","💭","🗣️","🐉","🌪️","🧩","🎲","🧭","⏳","🔑",
    "💊","🧲","🕯️","📯","🦅","🐺","🦉","🦋","🌋","💠",
    "🌀","👤","🎋","🪧","👺","🫂","🧶","🪄","🎮","🦸",
]
