
import json
from data.database import get_db, db_transaction

def migrate_iter7():
    """Create custom_tools table if not exists."""
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_tools (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                code TEXT DEFAULT '',
                parameters_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Also ensure model_usage has balance fields
        try:
            conn.execute("ALTER TABLE model_usage ADD COLUMN last_cost_est REAL DEFAULT 0")
        except:
            pass
    return True
