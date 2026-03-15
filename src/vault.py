"""
vault.py  —  GhostStore SQLite vault database
Session 8: store, retrieve, list, and delete manifest records.

Database location: ~/ghoststore_vault.db  (created automatically)

Schema
------
files
    id          TEXT PRIMARY KEY   — UUID
    filename    TEXT               — original filename
    created     TEXT               — ISO timestamp
    size_bytes  INTEGER            — original file size
    key_hex     TEXT               — hex-encoded AES-256 key
    chunk_count INTEGER            — number of chunks
    storage_dir TEXT               — folder where carriers live
    manifest    TEXT               — JSON manifest (full copy)
    notes       TEXT               — optional user notes
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


# Default vault location — next to the script or in user home
_DEFAULT_DB = Path.home() / 'ghoststore_vault.db'


def _connect(db_path=None):
    path = str(db_path or _DEFAULT_DB)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            created     TEXT NOT NULL,
            size_bytes  INTEGER NOT NULL,
            key_hex     TEXT NOT NULL,
            chunk_count INTEGER NOT NULL,
            storage_dir TEXT NOT NULL,
            manifest    TEXT NOT NULL,
            notes       TEXT DEFAULT ''
        )
    """)
    conn.commit()


# ── Public API ────────────────────────────────────────────────────────────────

def register(manifest: dict, db_path=None) -> str:
    """
    Save a manifest to the vault.
    Returns the record id.
    """
    conn = _connect(db_path)
    try:
        conn.execute("""
            INSERT OR REPLACE INTO files
                (id, filename, created, size_bytes, key_hex, chunk_count, storage_dir, manifest, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            manifest['id'],
            manifest['filename'],
            manifest['created'],
            manifest['size_bytes'],
            manifest['key_hex'],
            len(manifest['chunks']),
            manifest['storage_dir'],
            json.dumps(manifest),
            manifest.get('notes', ''),
        ))
        conn.commit()
        return manifest['id']
    finally:
        conn.close()


def get(record_id: str, db_path=None) -> dict:
    """
    Retrieve a manifest by id.
    Returns the manifest dict or None.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT manifest FROM files WHERE id = ?", (record_id,)
        ).fetchone()
        return json.loads(row['manifest']) if row else None
    finally:
        conn.close()


def list_all(db_path=None) -> list:
    """
    List all records — returns list of summary dicts (no full manifest).
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute("""
            SELECT id, filename, created, size_bytes, chunk_count, storage_dir, notes
            FROM files ORDER BY created DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete(record_id: str, db_path=None) -> bool:
    """
    Delete a record from the vault (does NOT delete carrier files).
    Returns True if deleted, False if not found.
    """
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM files WHERE id = ?", (record_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_notes(record_id: str, notes: str, db_path=None) -> bool:
    """Update the notes field for a record."""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE files SET notes = ? WHERE id = ?", (notes, record_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def rebuild_from_manifest(manifest_path: str, db_path=None) -> str:
    """
    Re-register a manifest from a .json file on disk.
    Useful if the vault database is lost.
    Returns the record id.
    """
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    return register(manifest, db_path)
