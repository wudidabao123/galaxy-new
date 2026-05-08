"""Model store — CRUD for model configurations.

API keys are stored in the system keyring (Windows Credential Manager),
not in the database. The DB only stores a key_ref string.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from data.database import db_transaction, get_db

_KEYRING_SERVICE = "galaxy-new"
_KEYRING_AVAILABLE = False
try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    pass

# ── Env fallback ──────────────────────────────────────
# Load .env file for GALAXY_DEFAULT_API_KEY as last-resort fallback
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os as _os


def _set_key(key_ref: str, api_key: str) -> None:
    if not api_key:
        return
    if _KEYRING_AVAILABLE:
        try:
            keyring.set_password(_KEYRING_SERVICE, key_ref, api_key)
        except Exception:
            import logging
            logging.warning(
                "Keyring write failed for key_ref=%s - falling back to file storage. "
                "API key will be stored with simple encoding (not encryption).",
                key_ref,
            )
    # Also save to a file-based fallback for when keyring is unavailable
    _save_key_file(key_ref, api_key)


def _get_key(key_ref: str) -> str:
    if not key_ref:
        return ""
    # 1) Try keyring first
    if _KEYRING_AVAILABLE:
        try:
            val = keyring.get_password(_KEYRING_SERVICE, key_ref)
            if val:
                return val
        except Exception:
            import logging
            logging.warning(
                "Keyring read failed for key_ref=%s - falling back to file/env storage.",
                key_ref,
            )
    # 2) Try file-based fallback
    val = _load_key_file(key_ref)
    if val:
        return val
    # 3) Global env fallback is handled by get_model_api_key() per-model,
    #    NOT here - using one global key for all models is a security risk.
    return ""


def _delete_key(key_ref: str) -> None:
    if _KEYRING_AVAILABLE:
        try:
            keyring.delete_password(_KEYRING_SERVICE, key_ref)
        except Exception:
            pass
    _delete_key_file(key_ref)


# ── File-based key fallback ───────────────────────────

def _key_file_path(key_ref: str) -> str:
    from config import PROJECT_ROOT
    import hashlib
    safe = hashlib.sha256(key_ref.encode()).hexdigest()[:16]
    return str(PROJECT_ROOT / ".keys" / f"{safe}.key")


def _save_key_file(key_ref: str, api_key: str) -> None:
    try:
        from pathlib import Path
        import base64
        path = Path(_key_file_path(key_ref))
        path.parent.mkdir(parents=True, exist_ok=True)
        # Restrict .keys/ directory to owner-only access
        try:
            import stat
            _os.chmod(path.parent, stat.S_IRWXU)  # 0o700
        except Exception:
            pass
        # WARNING: base85 is ENCODING, not encryption.
        # Anyone with filesystem read access can decode the key instantly.
        # For production, integrate OS-level encryption (Windows DPAPI, macOS Keychain, Linux libsecret)
        # or use the 'cryptography' library's Fernet with a user-supplied master password.
        encoded = base64.b85encode(api_key.encode("utf-8")).decode("ascii")
        path.write_text(encoded, encoding="ascii")
    except Exception:
        pass


def _load_key_file(key_ref: str) -> str:
    try:
        from pathlib import Path
        import base64
        path = Path(_key_file_path(key_ref))
        if not path.exists():
            return ""
        encoded = path.read_text(encoding="ascii")
        return base64.b85decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def _delete_key_file(key_ref: str) -> None:
    try:
        from pathlib import Path
        path = Path(_key_file_path(key_ref))
        if path.exists():
            path.unlink()
    except Exception:
        pass


# ── Public API ────────────────────────────────────────

def list_models() -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM models ORDER BY is_default DESC, name ASC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_model(model_id: str) -> dict[str, Any] | None:
    if not model_id:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM models WHERE id = ?", (model_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_default_model() -> dict[str, Any] | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM models WHERE is_default = 1 LIMIT 1"
    ).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM models ORDER BY name ASC LIMIT 1").fetchone()
    return _row_to_dict(row) if row else None


def save_model(
    model_id: str | None,
    name: str,
    model_name: str,
    base_url: str,
    api_key: str,
    context_length: int = 128000,
    capabilities: dict | None = None,
    is_default: bool = False,
) -> str:
    """Save or update a model. Returns the model_id."""
    mid = model_id or str(uuid.uuid4())[:8]
    key_ref = f"model:{mid}"
    now = datetime.now().isoformat(timespec="seconds")

    with db_transaction() as conn:
        if is_default:
            conn.execute("UPDATE models SET is_default = 0")
        caps_json = json.dumps(capabilities or {}, ensure_ascii=False)

        existing = conn.execute("SELECT 1 FROM models WHERE id = ?", (mid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE models SET name=?, model_name=?, base_url=?, key_ref=?, "
                "context_length=?, capabilities=?, is_default=?, updated_at=? WHERE id=?",
                (name, model_name, base_url, key_ref, context_length, caps_json,
                 1 if is_default else 0, now, mid),
            )
        else:
            conn.execute(
                "INSERT INTO models (id, name, model_name, base_url, key_ref, "
                "context_length, capabilities, is_default, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mid, name, model_name, base_url, key_ref, context_length, caps_json,
                 1 if is_default else 0, now, now),
            )

    # Store the key in keyring
    _set_key(key_ref, api_key)

    return mid


def delete_model(model_id: str) -> bool:
    model = get_model(model_id)
    if not model:
        return False
    _delete_key(model.get("key_ref", ""))
    with db_transaction() as conn:
        conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
        # B12: also clean up orphaned usage records
        conn.execute("DELETE FROM model_usage WHERE model_id = ?", (model_id,))
    return True


def get_model_api_key(model_id: str) -> str:
    """Retrieve the API key for a model from keyring, file, or env.
    
    Fallback order:
    1. System keyring (key_ref)
    2. File cache (.keys/)
    3. Per-model env var: GALAXY_API_KEY_<MODEL_ID>
    4. Global env var: GALAXY_DEFAULT_API_KEY
    """
    model = _get_model_raw(model_id)
    key_ref = model.get("key_ref", "") if model else ""
    key = _get_key(key_ref)
    # Per-model env fallback
    if not key:
        key = _os.environ.get(f"GALAXY_API_KEY_{model_id}", "") or ""
    return key


def set_default_model(model_id: str) -> None:
    # B13: validate model exists before clearing all defaults
    existing = get_model(model_id)
    if not existing:
        raise ValueError(f"Model '{model_id}' does not exist")
    with db_transaction() as conn:
        conn.execute("UPDATE models SET is_default = 0")
        conn.execute(
            "UPDATE models SET is_default = 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), model_id),
        )


# ── Model usage stats ─────────────────────────────────

def record_model_usage(model_id: str, model_cfg: dict, task: Any, output: str) -> None:
    """Record a model usage event."""
    if not model_id:
        return
    now = datetime.now().isoformat(timespec="seconds")
    name = model_cfg.get("name", "") or model_cfg.get("model", "")
    model_name = model_cfg.get("model", "")

    # Token estimation with CJK-aware weighting
    # CJK characters typically ~1.5-2 tokens each in most tokenizers,
    # while ASCII/Latin average ~0.25-0.35 tokens per character.
    # We use a heuristic: detect proportion of CJK chars and blend factors.
    def _est_tokens(text: str) -> int:
        if not text:
            return 1
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff')
        total = len(text)
        cjk_ratio = cjk / total if total > 0 else 0
        # Blend: CJK ~0.6 tokens/char, non-CJK ~0.3 tokens/char
        factor = cjk_ratio * 0.6 + (1 - cjk_ratio) * 0.3
        return max(1, int(total * factor))

    input_est = _est_tokens(str(task))
    output_est = _est_tokens(str(output))

    with db_transaction() as conn:
        existing = conn.execute(
            "SELECT calls, total_tokens_est FROM model_usage WHERE model_id = ?",
            (model_id,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE model_usage SET name=?, model_name=?, calls=calls+1, "
                "input_tokens_est=input_tokens_est+?, output_tokens_est=output_tokens_est+?, "
                "total_tokens_est=total_tokens_est+?, last_used=? WHERE model_id=?",
                (name, model_name, input_est, output_est,
                 input_est + output_est, now, model_id),
            )
        else:
            conn.execute(
                "INSERT INTO model_usage (model_id, name, model_name, calls, "
                "input_tokens_est, output_tokens_est, total_tokens_est, last_used) "
                "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
                (model_id, name, model_name, input_est, output_est,
                 input_est + output_est, now),
            )


def get_model_usage() -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM model_usage ORDER BY last_used DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ── Helpers ───────────────────────────────────────────

def _get_model_raw(model_id: str) -> dict[str, Any] | None:
    """Get raw model data WITHOUT embedding api_key."""
    if not model_id:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    return dict(row) if row else None


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a sqlite3.Row to a dict with normalized field names.
    
    DB column 'model_name' is aliased to 'model' for backward compat.
    Callers should use .get("model", "") for the API model id string
    and .get("name", "") for the user-facing display name.
    """
    if not row:
        return {}
    d = dict(row)
    # Normalize: DB has 'model_name' column; expose as 'model' for compat
    if "model_name" in d:
        d["model"] = d.pop("model_name")
    elif "model" not in d:
        d["model"] = ""
    # Never embed api_key
    d.pop("api_key", None)
    try:
        d["capabilities"] = json.loads(d.get("capabilities", "{}"))
    except (json.JSONDecodeError, TypeError):
        d["capabilities"] = {}
    return d
