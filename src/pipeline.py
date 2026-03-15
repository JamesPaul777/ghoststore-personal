"""
pipeline_v2.py  —  GhostStore full pipeline v2
Session 8: compress → encrypt → chunk → embed → store → manifest → vault

hide_v2()   — hide one or more files, chunk them, store carriers, register in vault
reveal_v2() — load manifest from vault or file, reassemble chunks, decrypt, decompress
"""

import io
import os
import secrets
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from compress import compress, decompress
from encrypt import encrypt, decrypt
from chunker import split, reassemble, DEFAULT_CHUNK_SIZE
from cdc_chunker import cdc_split, cdc_reassemble, chunk_stats
from storage import save, load_chunks
from vault import register, get

_BUNDLE_NAME = '_ghoststore_bundle.zip'


def hide_v2(
    secret_paths,               # str | Path | list[str | Path]
    output_dir,                 # str | Path — folder to store all carriers + manifest
    key=None,                   # bytes | None — 32-byte AES key, auto-generated if None
    carrier_type='image',       # 'image' | 'video' | 'audio' | 'sqlite'
    user_carriers=None,         # list[str] | None — Mode 2 user carrier paths
    chunk_size=DEFAULT_CHUNK_SIZE,  # bytes per chunk
    notes='',                   # optional label stored in vault
    db_path=None,               # vault DB path (None = default)
    sqlite_template='cache',    # 'cache' | 'analytics' | 'browser'  — Mode C only
    chunking_mode='fixed',      # 'fixed' | 'cdc'  — Enterprise CDC chunking
    use_dedup=False,            # True = check dedup registry (requires CDC)
    cloud_target=None,
    auto_push=False,
    cloud_prefix="ghoststore",
) -> dict:
    """
    Full pipeline: hide one or more files using chunked steganography.

    Returns
    -------
    manifest dict  (also saved to output_dir/manifest.json and vault DB)
    """

    # ── 1. Normalise inputs ─────────────────────────────────────────────
    if isinstance(secret_paths, (str, Path)):
        secret_paths = [Path(secret_paths)]
    else:
        secret_paths = [Path(p) for p in secret_paths]

    if key is None:
        key = secrets.token_bytes(32)

    # ── 2. Bundle multiple files ────────────────────────────────────────
    if len(secret_paths) == 1:
        payload      = secret_paths[0].read_bytes()
        filename     = secret_paths[0].name
        original_size = len(payload)
    else:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED) as zf:
            for p in secret_paths:
                zf.write(p, arcname=p.name)
        payload       = buf.getvalue()
        filename      = _BUNDLE_NAME
        original_size = sum(p.stat().st_size for p in secret_paths)

    print(f'\n🗂  Hiding: {filename}  ({original_size:,} bytes)')

    # ── 3. Compress ─────────────────────────────────────────────────────
    compressed = compress(payload)
    print(f'  🗜  Compressed: {len(compressed):,} bytes')

    # ── 4. Chunk (before encrypt — avoids AES-GCM 2GB limit) ────────────
    if chunking_mode == 'cdc':
        raw_chunks = cdc_split(compressed, avg_chunk=chunk_size)
        stats = chunk_stats(raw_chunks)
        print(f'  ✂️  CDC split into {len(raw_chunks)} chunk(s)  '
              f'avg={stats["avg_bytes"]//1024}KB  '
              f'min={stats["min_bytes"]//1024}KB  '
              f'max={stats["max_bytes"]//1024}KB')
    else:
        raw_chunks = split(compressed, chunk_size)
        print(f'  ✂️  Fixed split into {len(raw_chunks)} chunk(s) × up to {chunk_size//1024} KB')

    # ── 5. Encrypt each chunk individually ──────────────────────────────
    chunks = [encrypt(c, key) for c in raw_chunks]
    print(f'  🔐 Encrypted {len(chunks)} chunk(s)')

    # ── 6. Build manifest skeleton ──────────────────────────────────────
    record_id = str(uuid.uuid4())
    manifest  = {
        'id':          record_id,
        'filename':    filename,
        'created':     datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'size_bytes':  original_size,
        'key_hex':     key.hex(),
        'chunk_count': len(raw_chunks),
        'chunk_size':  chunk_size,
        'carrier_type':   carrier_type,
        'chunking_mode':  chunking_mode,
        'storage_dir': str(output_dir),
        'notes':       notes,
        'chunks':      [],  # filled in by storage.save()
    }

    # ── 7. Embed chunks into carriers + save manifest.json ──────────────
    output_dir = str(output_dir)
    save(chunks, output_dir, manifest,
         carrier_type=carrier_type,
         user_carriers=user_carriers,
         sqlite_template=sqlite_template,
         use_dedup=(use_dedup and chunking_mode == 'cdc'),
         db_path=db_path)

    # ── 8. Register in vault database ───────────────────────────────────
    register(manifest, db_path)
    print(f'  🔐 Registered in vault: {record_id}')
    if auto_push and cloud_target:
        try:
            from cloud_storage import get_provider
            import json as _json
            provider = get_provider(cloud_target)
            updated_manifest = provider.push_manifest(manifest, prefix=cloud_prefix)
            manifest.update(updated_manifest)
            print(f'  ☁️  Auto-pushed {len(manifest["chunks"])} carrier(s) to {cloud_target}.')
        except Exception as exc:
            print(f'  ⚠️  Cloud auto-push failed ({cloud_target}): {exc}')
    print(f'  ✅ Done — {len(chunks)} carrier(s) in: {output_dir}')

    return manifest


def reveal_v2(
    source,         # str — vault record id OR path to manifest.json
    output_path,    # str | Path — output file or directory
    db_path=None,   # vault DB path (None = default)
) -> list:
    """
    Full pipeline: reveal hidden files from a manifest.

    source can be:
      - A vault record UUID  → loads manifest from vault DB
      - A path to manifest.json → loads manifest from file

    Returns
    -------
    list[str]  — paths of revealed file(s)
    """
    import json

    # ── 1. Load manifest ────────────────────────────────────────────────
    if os.path.isfile(str(source)):
        with open(source, 'r') as f:
            manifest = json.load(f)
        print(f'\n📂 Loading manifest from file: {source}')
    else:
        manifest = get(str(source), db_path)
        if not manifest:
            raise ValueError(f"No vault record found for id: {source}")
        print(f'\n📂 Loading manifest from vault: {source}')

    print(f'  File: {manifest["filename"]}  |  {len(manifest["chunks"])} chunk(s)')

    # ── 2. Load + reassemble chunks ─────────────────────────────────────
    raw_chunks     = load_chunks(manifest)
    encrypted_blob = reassemble(raw_chunks)

    # ── 3. Decrypt each chunk → Reassemble → Decompress ────────────────
    key        = bytes.fromhex(manifest['key_hex'])
    dec_chunks = [decrypt(c, key) for c in raw_chunks]
    _reassemble = cdc_reassemble if manifest.get('chunking_mode') == 'cdc' else reassemble
    compressed = _reassemble(dec_chunks)
    plaintext  = decompress(compressed)

    # ── 4. Write output ─────────────────────────────────────────────────
    out = Path(output_path)
    revealed = []

    if manifest['filename'] == _BUNDLE_NAME:
        # Multiple files — extract zip
        dest = out if not out.suffix else out.parent / (out.stem + '_revealed')
        dest.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO(plaintext)
        with zipfile.ZipFile(buf, 'r') as zf:
            zf.extractall(dest)
            revealed = [str(dest / n) for n in zf.namelist()]
        print(f'  ✅ Revealed {len(revealed)} file(s) → {dest}')
    else:
        # Single file
        if out.suffix:
            out.parent.mkdir(parents=True, exist_ok=True)
            out_file = out
        else:
            out.mkdir(parents=True, exist_ok=True)
            out_file = out / manifest['filename']
        out_file.write_bytes(plaintext)
        revealed = [str(out_file)]
        print(f'  ✅ Revealed → {out_file}')

    return revealed
