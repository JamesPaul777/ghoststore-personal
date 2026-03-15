"""
key_manager.py  —  GhostStore named key store
Session 9: save, retrieve, list, rename, and delete named encryption keys.

Keys are stored in the same SQLite vault DB as file records, in a
separate 'keys' table. Each key is optionally linked to its vault
record by record_id.

Schema
------
keys
    id          TEXT PRIMARY KEY   — UUID
    name        TEXT NOT NULL      — user-supplied friendly name
    key_hex     TEXT NOT NULL      — 64-char hex AES-256 key
    created     TEXT NOT NULL      — ISO timestamp
    record_id   TEXT               — linked vault file record (nullable)
    notes       TEXT DEFAULT ''
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path.home() / 'ghoststore_vault.db'


def _connect(db_path=None):
    path = str(db_path or _DEFAULT_DB)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            key_hex     TEXT NOT NULL,
            created     TEXT NOT NULL,
            record_id   TEXT DEFAULT NULL,
            notes       TEXT DEFAULT ''
        )
    """)
    conn.commit()


# ── Public API ────────────────────────────────────────────────────────────────

def save_key(name: str, key_hex: str, record_id: str = None,
             notes: str = '', db_path=None) -> str:
    """
    Save a named key. Returns the key id.
    name      — friendly label e.g. "Tax docs 2025"
    key_hex   — 64-char hex string (32 bytes AES-256)
    record_id — optional UUID of the linked vault file record
    """
    if len(key_hex) != 64:
        raise ValueError(f'key_hex must be 64 hex chars (got {len(key_hex)})')

    key_id = str(uuid.uuid4())
    conn   = _connect(db_path)
    try:
        conn.execute("""
            INSERT INTO keys (id, name, key_hex, created, record_id, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            key_id,
            name.strip() or 'Unnamed key',
            key_hex,
            datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            record_id,
            notes,
        ))
        conn.commit()
        return key_id
    finally:
        conn.close()


def list_keys(db_path=None) -> list:
    """List all saved keys — most recent first. key_hex is NOT returned."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("""
            SELECT id, name, created, record_id, notes,
                   substr(key_hex, 1, 8) || '........' AS key_preview
            FROM keys ORDER BY created DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_key_hex(key_id: str, db_path=None) -> str:
    """Return the full raw hex key for a given key id. Returns None if not found."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            'SELECT key_hex FROM keys WHERE id = ?', (key_id,)
        ).fetchone()
        return row['key_hex'] if row else None
    finally:
        conn.close()


def find_by_record(record_id: str, db_path=None) -> dict:
    """Find the key linked to a vault record. Returns dict or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            'SELECT * FROM keys WHERE record_id = ?', (record_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def rename_key(key_id: str, new_name: str, db_path=None) -> bool:
    """Rename a key. Returns True if updated."""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            'UPDATE keys SET name = ? WHERE id = ?', (new_name.strip(), key_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_key(key_id: str, db_path=None) -> bool:
    """Delete a key record. Returns True if deleted."""
    conn = _connect(db_path)
    try:
        cur = conn.execute('DELETE FROM keys WHERE id = ?', (key_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
