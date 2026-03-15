"""
test_v2.py  —  GhostStore v2 module tests
Session 10: chunker, vault, storage (mocked), pipeline end-to-end,
            sqlite_carrier, key_manager

Run from project root with venv active:
    python -m pytest tests/test_v2.py -v
"""

import io
import json
import os
import secrets
import sqlite3
import sys
import tempfile
import uuid
import zipfile

import pytest

# Make src/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from chunker        import split, reassemble, DEFAULT_CHUNK_SIZE
from compress       import compress, decompress
from encrypt        import encrypt, decrypt
from vault          import register, get, list_all, delete, update_notes, rebuild_from_manifest
from key_manager    import save_key, list_keys, get_key_hex, delete_key, rename_key
from sqlite_carrier import embed_sqlite, extract_sqlite, capacity_sqlite, list_templates


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Fresh temporary vault DB for each test."""
    return str(tmp_path / 'test_vault.db')


@pytest.fixture
def sample_key():
    return secrets.token_bytes(32)


@pytest.fixture
def sample_manifest(tmp_path):
    """A realistic manifest dict for vault tests."""
    return {
        'id':           str(uuid.uuid4()),
        'filename':     'test_document.pdf',
        'created':      '2026-03-13T10:00:00Z',
        'size_bytes':   1_048_576,
        'key_hex':      secrets.token_bytes(32).hex(),
        'chunk_count':  2,
        'chunk_size':   DEFAULT_CHUNK_SIZE,
        'carrier_type': 'image',
        'storage_dir':  str(tmp_path),
        'notes':        'Test record',
        'chunks': [
            {'index': 0, 'carrier': 'carrier_0000.png',
             'carrier_path': str(tmp_path / 'carrier_0000.png'), 'size_bytes': 524288},
            {'index': 1, 'carrier': 'carrier_0001.png',
             'carrier_path': str(tmp_path / 'carrier_0001.png'), 'size_bytes': 524288},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# chunker.py
# ─────────────────────────────────────────────────────────────────────────────

class TestChunker:

    def test_split_single_chunk(self):
        data = b'A' * 100
        chunks = split(data, chunk_size=1024)
        assert len(chunks) == 1
        assert chunks[0] == data

    def test_split_multiple_chunks(self):
        data = b'B' * (3 * 1024 + 1)
        chunks = split(data, chunk_size=1024)
        assert len(chunks) == 4
        assert sum(len(c) for c in chunks) == len(data)

    def test_split_exact_boundary(self):
        data = b'C' * (4 * 1024)
        chunks = split(data, chunk_size=1024)
        assert len(chunks) == 4
        assert all(len(c) == 1024 for c in chunks)

    def test_reassemble_round_trip(self):
        data = secrets.token_bytes(5_000)
        chunks = split(data, chunk_size=1024)
        assert reassemble(chunks) == data

    def test_single_byte(self):
        data = b'\xff'
        assert reassemble(split(data, chunk_size=1024)) == data

    def test_empty_data(self):
        # chunker correctly rejects empty data — nothing to hide
        with pytest.raises(ValueError):
            split(b'', chunk_size=1024)

    def test_default_chunk_size(self):
        assert DEFAULT_CHUNK_SIZE == 1024 * 1024  # 1MB


# ─────────────────────────────────────────────────────────────────────────────
# compress + encrypt pipeline integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestCompressEncrypt:

    def test_compress_expand_round_trip(self):
        data = b'Hello GhostStore! ' * 1000
        assert decompress(compress(data)) == data

    def test_encrypt_decrypt_round_trip(self, sample_key):
        data = secrets.token_bytes(2048)
        assert decrypt(encrypt(data, sample_key), sample_key) == data

    def test_wrong_key_fails(self, sample_key):
        data = b'secret'
        blob = encrypt(data, sample_key)
        wrong_key = secrets.token_bytes(32)
        with pytest.raises(Exception):
            decrypt(blob, wrong_key)

    def test_full_compress_chunk_encrypt(self, sample_key):
        """Full compress → chunk → encrypt → decrypt → reassemble → decompress."""
        original = b'GhostStore test payload ' * 500
        compressed = compress(original)
        chunks = split(compressed, chunk_size=1024)
        encrypted = [encrypt(c, sample_key) for c in chunks]
        decrypted = [decrypt(e, sample_key) for e in encrypted]
        result = decompress(reassemble(decrypted))
        assert result == original


# ─────────────────────────────────────────────────────────────────────────────
# vault.py
# ─────────────────────────────────────────────────────────────────────────────

class TestVault:

    def test_register_and_get(self, tmp_db, sample_manifest):
        register(sample_manifest, tmp_db)
        retrieved = get(sample_manifest['id'], tmp_db)
        assert retrieved['id']       == sample_manifest['id']
        assert retrieved['filename'] == sample_manifest['filename']
        assert retrieved['key_hex']  == sample_manifest['key_hex']

    def test_list_all(self, tmp_db, sample_manifest):
        register(sample_manifest, tmp_db)
        records = list_all(tmp_db)
        assert len(records) == 1
        assert records[0]['id'] == sample_manifest['id']

    def test_delete(self, tmp_db, sample_manifest):
        register(sample_manifest, tmp_db)
        assert delete(sample_manifest['id'], tmp_db) is True
        assert get(sample_manifest['id'], tmp_db) is None

    def test_delete_nonexistent(self, tmp_db):
        assert delete(str(uuid.uuid4()), tmp_db) is False

    def test_update_notes(self, tmp_db, sample_manifest):
        register(sample_manifest, tmp_db)
        update_notes(sample_manifest['id'], 'Updated note', tmp_db)
        records = list_all(tmp_db)
        assert records[0]['notes'] == 'Updated note'

    def test_rebuild_from_manifest(self, tmp_db, sample_manifest, tmp_path):
        manifest_path = str(tmp_path / 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(sample_manifest, f)
        rebuild_from_manifest(manifest_path, tmp_db)
        assert get(sample_manifest['id'], tmp_db) is not None

    def test_get_nonexistent(self, tmp_db):
        assert get(str(uuid.uuid4()), tmp_db) is None

    def test_multiple_records_ordered(self, tmp_db):
        for i in range(3):
            m = {
                'id': str(uuid.uuid4()), 'filename': f'file{i}.pdf',
                'created': f'2026-03-1{i+1}T10:00:00Z', 'size_bytes': 1000,
                'key_hex': secrets.token_bytes(32).hex(), 'chunk_count': 1,
                'chunk_size': DEFAULT_CHUNK_SIZE, 'carrier_type': 'image',
                'storage_dir': '/tmp', 'notes': '', 'chunks': [],
            }
            register(m, tmp_db)
        records = list_all(tmp_db)
        assert len(records) == 3
        # Most recent first
        assert records[0]['created'] > records[1]['created']


# ─────────────────────────────────────────────────────────────────────────────
# key_manager.py
# ─────────────────────────────────────────────────────────────────────────────

class TestKeyManager:

    def test_save_and_retrieve(self, tmp_db, sample_key):
        key_hex = sample_key.hex()
        kid = save_key('My test key', key_hex, db_path=tmp_db)
        assert get_key_hex(kid, tmp_db) == key_hex

    def test_list_keys(self, tmp_db, sample_key):
        save_key('Key A', sample_key.hex(), db_path=tmp_db)
        save_key('Key B', secrets.token_bytes(32).hex(), db_path=tmp_db)
        keys = list_keys(tmp_db)
        assert len(keys) == 2
        # Most recent first
        assert keys[0]['name'] == 'Key B'

    def test_rename_key(self, tmp_db, sample_key):
        kid = save_key('Original name', sample_key.hex(), db_path=tmp_db)
        rename_key(kid, 'New name', tmp_db)
        keys = list_keys(tmp_db)
        assert keys[0]['name'] == 'New name'

    def test_delete_key(self, tmp_db, sample_key):
        kid = save_key('To delete', sample_key.hex(), db_path=tmp_db)
        assert delete_key(kid, tmp_db) is True
        assert get_key_hex(kid, tmp_db) is None

    def test_invalid_key_hex(self, tmp_db):
        with pytest.raises(ValueError):
            save_key('Bad key', 'tooshort', db_path=tmp_db)

    def test_key_preview_hides_full_key(self, tmp_db, sample_key):
        save_key('Preview test', sample_key.hex(), db_path=tmp_db)
        keys = list_keys(tmp_db)
        # Preview must NOT expose the full key
        assert keys[0]['key_preview'] != sample_key.hex()
        assert '........' in keys[0]['key_preview']

    def test_linked_record_id(self, tmp_db, sample_key):
        record_id = str(uuid.uuid4())
        kid = save_key('Linked key', sample_key.hex(),
                       record_id=record_id, db_path=tmp_db)
        keys = list_keys(tmp_db)
        assert keys[0]['record_id'] == record_id


# ─────────────────────────────────────────────────────────────────────────────
# sqlite_carrier.py
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLiteCarrier:

    @pytest.mark.parametrize("template", ["cache", "analytics", "browser"])
    def test_round_trip(self, tmp_path, template):
        data = secrets.token_bytes(50_000)
        db_path = str(tmp_path / f'carrier_{template}.db')
        embed_sqlite(data, db_path, template=template)
        assert extract_sqlite(db_path) == data

    def test_small_payload(self, tmp_path):
        data = b'tiny'
        db_path = str(tmp_path / 'tiny.db')
        embed_sqlite(data, db_path)
        assert extract_sqlite(db_path) == data

    def test_large_payload(self, tmp_path):
        """Multi-row payload — exceeds 512KB row chunk size."""
        data = secrets.token_bytes(600_000)
        db_path = str(tmp_path / 'large.db')
        embed_sqlite(data, db_path)
        assert extract_sqlite(db_path) == data

    def test_invalid_template(self, tmp_path):
        with pytest.raises(ValueError):
            embed_sqlite(b'data', str(tmp_path / 'bad.db'), template='invalid')

    def test_not_a_ghoststore_db(self, tmp_path):
        """Plain SQLite file with no GhostStore magic should raise."""
        db_path = str(tmp_path / 'plain.db')
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE stuff (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO stuff VALUES (1, 'hello')")
        conn.commit()
        conn.close()
        with pytest.raises(ValueError):
            extract_sqlite(db_path)

    def test_capacity(self, tmp_path):
        data = secrets.token_bytes(10_000)
        db_path = str(tmp_path / 'cap.db')
        embed_sqlite(data, db_path)
        cap = capacity_sqlite(db_path)
        assert cap > len(data)   # includes magic header overhead

    def test_list_templates(self):
        templates = list_templates()
        assert set(templates.keys()) == {'cache', 'analytics', 'browser'}

    def test_output_is_valid_sqlite(self, tmp_path):
        """Carrier must be openable as a normal SQLite file."""
        data = secrets.token_bytes(1000)
        db_path = str(tmp_path / 'valid.db')
        embed_sqlite(data, db_path)
        conn = sqlite3.connect(db_path)
        # Should be able to query it like a normal db
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert len(tables) > 0

    def test_encrypted_payload_round_trip(self, tmp_path, sample_key):
        """Simulate what the real pipeline does — encrypt then embed."""
        plaintext  = b'Sensitive document content ' * 200
        compressed = compress(plaintext)
        encrypted  = encrypt(compressed, sample_key)

        db_path = str(tmp_path / 'encrypted_carrier.db')
        embed_sqlite(encrypted, db_path)

        recovered_enc = extract_sqlite(db_path)
        recovered     = decompress(decrypt(recovered_enc, sample_key))
        assert recovered == plaintext


# ─────────────────────────────────────────────────────────────────────────────
# pipeline end-to-end (image carrier — no FFmpeg required)
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineEndToEnd:

    def test_hide_and_reveal_single_file_image(self, tmp_path, tmp_db):
        """Full hide_v2 → reveal_v2 round trip using image carrier."""
        from pipeline import hide_v2, reveal_v2

        # Create a secret file
        secret = tmp_path / 'secret.txt'
        secret.write_bytes(b'Top secret content ' * 100)

        output_dir = tmp_path / 'output'

        manifest = hide_v2(
            secret_paths=[str(secret)],
            output_dir=str(output_dir),
            carrier_type='image',
            db_path=tmp_db,
        )

        assert manifest['filename'] == 'secret.txt'
        assert manifest['chunk_count'] >= 1
        assert len(manifest['key_hex']) == 64
        assert (output_dir / 'manifest.json').exists()

        # Reveal
        reveal_dir = tmp_path / 'revealed'
        paths = reveal_v2(str(output_dir / 'manifest.json'), str(reveal_dir), db_path=tmp_db)

        assert len(paths) == 1
        assert (reveal_dir / 'secret.txt').read_bytes() == secret.read_bytes()

    def test_hide_and_reveal_sqlite_carrier(self, tmp_path, tmp_db):
        """Full hide_v2 → reveal_v2 round trip using SQLite carrier."""
        from pipeline import hide_v2, reveal_v2

        secret = tmp_path / 'data.bin'
        secret.write_bytes(secrets.token_bytes(10_000))

        output_dir = tmp_path / 'sqlite_output'

        manifest = hide_v2(
            secret_paths=[str(secret)],
            output_dir=str(output_dir),
            carrier_type='sqlite',
            sqlite_template='analytics',
            db_path=tmp_db,
        )

        assert manifest['carrier_type'] == 'sqlite'

        reveal_dir = tmp_path / 'sqlite_revealed'
        paths = reveal_v2(str(output_dir / 'manifest.json'), str(reveal_dir), db_path=tmp_db)

        assert (reveal_dir / 'data.bin').read_bytes() == secret.read_bytes()

    def test_hide_multiple_files(self, tmp_path, tmp_db):
        """Multiple files are bundled into a zip and recovered correctly."""
        from pipeline import hide_v2, reveal_v2

        files = []
        for i in range(3):
            f = tmp_path / f'file{i}.txt'
            f.write_bytes(f'Content of file {i} '.encode() * 50)
            files.append(str(f))

        output_dir = tmp_path / 'multi_output'
        manifest = hide_v2(
            secret_paths=files,
            output_dir=str(output_dir),
            carrier_type='image',
            db_path=tmp_db,
        )

        reveal_dir = tmp_path / 'multi_revealed'
        paths = reveal_v2(str(output_dir / 'manifest.json'), str(reveal_dir), db_path=tmp_db)

        assert len(paths) == 3
        for i, f in enumerate(files):
            fname = os.path.basename(f)
            assert (reveal_dir / fname).read_bytes() == open(f, 'rb').read()

    def test_vault_registration(self, tmp_path, tmp_db):
        """hide_v2 registers the record in the vault DB."""
        from pipeline import hide_v2

        secret = tmp_path / 'doc.txt'
        secret.write_bytes(b'Vault test')

        manifest = hide_v2(
            secret_paths=[str(secret)],
            output_dir=str(tmp_path / 'out'),
            carrier_type='image',
            db_path=tmp_db,
        )

        records = list_all(tmp_db)
        assert any(r['id'] == manifest['id'] for r in records)

    def test_reveal_from_vault_id(self, tmp_path, tmp_db):
        """reveal_v2 can load from vault UUID instead of manifest path."""
        from pipeline import hide_v2, reveal_v2

        secret = tmp_path / 'vault_test.txt'
        secret.write_bytes(b'Reveal from vault ID test')

        manifest = hide_v2(
            secret_paths=[str(secret)],
            output_dir=str(tmp_path / 'out'),
            carrier_type='image',
            db_path=tmp_db,
        )

        reveal_dir = tmp_path / 'revealed'
        paths = reveal_v2(manifest['id'], str(reveal_dir), db_path=tmp_db)
        assert len(paths) == 1
        assert open(paths[0], 'rb').read() == b'Reveal from vault ID test'
