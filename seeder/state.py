"""Local SQLite log of everything the seeder has created.

Makes the seeder resumable: if a run crashes, rerunning skips finished records.
Also stores metadata (price, category, return-prone flag) that later steps reuse.
"""
import json, sqlite3

DB_PATH = "seeder_state.db"


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS created (
                   entity     TEXT NOT NULL,
                   key        TEXT NOT NULL,
                   shopify_id TEXT NOT NULL,
                   meta       TEXT,
                   PRIMARY KEY (entity, key))""")
    return c


def get(entity, key):
    with _conn() as c:
        row = c.execute("SELECT shopify_id FROM created WHERE entity=? AND key=?",
                        (entity, key)).fetchone()
    return row[0] if row else None


def record(entity, key, shopify_id, meta=None):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO created VALUES (?,?,?,?)",
                  (entity, key, shopify_id, json.dumps(meta or {})))


def all_of(entity):
    with _conn() as c:
        rows = c.execute("SELECT key, shopify_id, meta FROM created WHERE entity=?",
                         (entity,)).fetchall()
    return [{"key": k, "id": i, **json.loads(m)} for k, i, m in rows]

    