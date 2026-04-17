"""
Phase 4 – Step 1: SQLite Cache
Stores pipeline results keyed by a hash of the source component JSON.
On a cache hit the entire Phase 3 pipeline is skipped (instant response).

Schema:
  Table: query_cache
    id            INTEGER PRIMARY KEY
    cache_key     TEXT UNIQUE        — SHA256 of normalised component JSON
    component_name TEXT              — for human-readable display
    component_type TEXT
    query_string  TEXT               — Mouser keyword string used
    results_json  TEXT               — JSON-serialised top-5 results
    source_json   TEXT               — original component JSON (for reference)
    created_at    TEXT               — ISO timestamp
    hit_count     INTEGER DEFAULT 0  — number of times this cache entry was used
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Database location ─────────────────────────────────────────────────────────
DB_DIR = Path(os.environ.get("DB_DIR", Path(__file__).parent.parent / "db"))
DB_PATH = DB_DIR / "component_cache.db"


def _get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # access columns by name
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Call once at app startup."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key      TEXT    UNIQUE NOT NULL,
                component_name TEXT,
                component_type TEXT,
                query_string   TEXT,
                results_json   TEXT    NOT NULL,
                source_json    TEXT    NOT NULL,
                created_at     TEXT    NOT NULL,
                hit_count      INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()


def make_cache_key(component_json: dict) -> str:
    """
    Deterministic SHA256 hash of the component JSON.
    Normalised (sorted keys, no whitespace) so cosmetic differences don't cause misses.
    """
    normalised = json.dumps(component_json, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalised.encode()).hexdigest()


def get_cached(component_json: dict) -> Optional[dict]:
    """
    Returns cached pipeline output if available, else None.
    Also increments hit_count on a cache hit.

    Returns:
        {
          "results": [...],       — list of scored part dicts
          "query_string": "...",  — Mouser keyword used
          "cached": True,
          "created_at": "...",
          "hit_count": N,
        }
        or None on cache miss.
    """
    key = make_cache_key(component_json)

    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM query_cache WHERE cache_key = ?", (key,)
        ).fetchone()

        if row is None:
            return None

        # Increment hit counter
        conn.execute(
            "UPDATE query_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
            (key,),
        )
        conn.commit()

    return {
        "results": json.loads(row["results_json"]),
        "query_string": row["query_string"],
        "cached": True,
        "created_at": row["created_at"],
        "hit_count": row["hit_count"] + 1,
    }


def set_cache(
    component_json: dict,
    query_string: str,
    results: list[dict],
) -> None:
    """
    Stores pipeline results in the cache.
    If an entry already exists for this key it is replaced (UPSERT).

    Args:
        component_json: Original structured component JSON.
        query_string:   Mouser keyword string that was used.
        results:        Scored & ranked parts list (top N).
    """
    key = make_cache_key(component_json)
    now = datetime.now(timezone.utc).isoformat()

    # Strip the heavy "raw" field before caching to keep DB small
    clean_results = []
    for r in results:
        r_copy = {k: v for k, v in r.items() if k != "raw"}
        clean_results.append(r_copy)

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO query_cache
                (cache_key, component_name, component_type, query_string,
                 results_json, source_json, created_at, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(cache_key) DO UPDATE SET
                query_string  = excluded.query_string,
                results_json  = excluded.results_json,
                source_json   = excluded.source_json,
                created_at    = excluded.created_at,
                hit_count     = 0
            """,
            (
                key,
                component_json.get("component_name", ""),
                component_json.get("component_type", ""),
                query_string,
                json.dumps(clean_results),
                json.dumps(component_json),
                now,
            ),
        )
        conn.commit()


def list_cached_queries() -> list[dict]:
    """Returns all cached entries (for admin/debug view)."""
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT cache_key, component_name, component_type, query_string, "
            "created_at, hit_count FROM query_cache ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def clear_cache() -> int:
    """Deletes all cache entries. Returns number of rows deleted."""
    with _get_connection() as conn:
        cur = conn.execute("DELETE FROM query_cache")
        conn.commit()
    return cur.rowcount
