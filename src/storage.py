"""
storage.py  —  GhostStore local storage manager
Session 8: save carrier files + manifest to a local output folder.

save(chunks, output_dir, manifest) → list[str]  (carrier paths)
load_chunk(carrier_path)           → bytes       (raw embedded bytes)
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

from embed import embed
from extract import extract as img_extract
from audio_carrier import embed_audio, extract_audio
from video_carrier import hide_in_video, reveal_from_video
from carrier_generator import (
    generate_image_carrier,
    generate_audio_carrier,
    generate_video_carrier,
)
from carrier_convert import prepare_carrier
from sqlite_carrier import embed_sqlite, extract_sqlite
from cdc_chunker import chunk_hash as compute_chunk_hash


# Carrier type → generator function
_GENERATORS = {
    'image':  generate_image_carrier,
    'video':  generate_video_carrier,
    'audio':  generate_audio_carrier,
    'sqlite': None,   # SQLite carriers are written directly — no temp file needed
}

# Carrier type → file extension
_EXT = {
    'image':  '.png',
    'video':  '.mkv',
    'audio':  '.wav',
    'sqlite': '.db',
}


def _embed_chunk(chunk: bytes, carrier_type: str, out_path: str,
                sqlite_template: str = 'cache'):
    """Embed a single chunk into a generated carrier and save to out_path."""
    if carrier_type == 'sqlite':
        # SQLite carriers are written directly — no temp file
        embed_sqlite(chunk, out_path, template=sqlite_template)
        return

    gen = _GENERATORS[carrier_type]
    tmp = gen(len(chunk))
    ext = Path(tmp).suffix.lower()

    try:
        if ext == '.png':
            embed(tmp, chunk, out_path)
        elif ext in ('.mkv', '.avi'):
            hide_in_video(chunk, tmp, out_path)
        elif ext == '.wav':
            embed_audio(chunk, tmp, out_path)
        else:
            raise ValueError(f"Unsupported carrier extension: {ext}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _embed_chunk_into_user_carrier(chunk: bytes, carrier_path: str, out_path: str) -> str:
    """
    Embed a single chunk into a user-supplied carrier.
    Returns the actual carrier_type used ('image' | 'video' | 'audio').
    out_path is used as a base — the actual saved file may have a different
    extension depending on what the carrier really is.
    """
    # prepare_carrier returns (path, carrier_type) tuple
    prepared, ctype = prepare_carrier(carrier_path)

    # Use the correct extension for this carrier type
    correct_ext = _EXT[ctype]
    base = str(out_path)
    # Strip any existing extension and replace with correct one
    for old_ext in ('.png', '.mkv', '.wav', '.avi'):
        if base.lower().endswith(old_ext):
            base = base[:-len(old_ext)]
            break
    actual_out = base + correct_ext

    try:
        if ctype == 'image':
            embed(prepared, chunk, actual_out)
        elif ctype == 'video':
            hide_in_video(chunk, prepared, actual_out)
        elif ctype == 'audio':
            embed_audio(chunk, prepared, actual_out)
        else:
            raise ValueError(f"Unsupported carrier type: {ctype}")
    finally:
        # Clean up temp converted file (prepare_carrier writes to temp dir)
        if prepared != carrier_path and os.path.exists(prepared):
            os.remove(prepared)

    return ctype, actual_out


def save(
    chunks: list,                  # list[bytes] — encrypted chunks from chunker.py
    output_dir: str,               # where to save carrier files + manifest
    manifest: dict,                # manifest dict (will be saved as manifest.json)
    carrier_type: str = 'image',   # 'image' | 'video' | 'audio' | 'sqlite'
    user_carriers: list = None,    # list[str] | None — Mode 2 user carrier paths
    sqlite_template: str = 'cache',# 'cache' | 'analytics' | 'browser'
    use_dedup: bool = False,       # True = CDC mode, check dedup registry
    db_path=None,                  # vault DB path for dedup registry
) -> list:
    """
    Embed each chunk into a carrier and save everything to output_dir.
    Also writes manifest.json into output_dir.

    Returns
    -------
    list[str]  — absolute paths of carrier files saved
    """
    os.makedirs(output_dir, exist_ok=True)
    ext          = _EXT.get(carrier_type, '.png')
    carrier_paths = []

    dedup_hits  = 0
    dedup_saved = 0

    for i, chunk in enumerate(chunks):
        if user_carriers and i < len(user_carriers):
            # Mode 2 — carrier type determined by the actual user file
            out_path_base = os.path.join(output_dir, f'carrier_{i:04d}')
            actual_ctype, actual_out = _embed_chunk_into_user_carrier(
                chunk, user_carriers[i], out_path_base)
            carrier_paths.append(os.path.abspath(actual_out))
            print(f'  ✅ Chunk {i+1}/{len(chunks)} → {os.path.basename(actual_out)}  [{actual_ctype}]')
        else:
            carrier_name = f'carrier_{i:04d}{ext}'
            out_path     = os.path.join(output_dir, carrier_name)

            # Dedup check — only in CDC mode
            dedup_hit = False
            if use_dedup:
                from dedup_engine import lookup_chunk, register_chunk
                h = compute_chunk_hash(chunk)
                existing = lookup_chunk(h, db_path)
                if existing and os.path.exists(existing['carrier_path']):
                    # Reuse existing carrier — just point to it
                    carrier_paths.append(existing['carrier_path'])
                    register_chunk(h, existing['carrier_path'],
                                   manifest['id'], len(chunk), i, db_path)
                    dedup_hits  += 1
                    dedup_saved += len(chunk)
                    print(f'  ♻️  Chunk {i+1}/{len(chunks)} → DEDUP HIT  '
                          f'(saved {len(chunk)//1024}KB, reusing existing carrier)')
                    dedup_hit = True
                else:
                    _embed_chunk(chunk, carrier_type, out_path, sqlite_template=sqlite_template)
                    carrier_paths.append(os.path.abspath(out_path))
                    register_chunk(h, os.path.abspath(out_path),
                                   manifest['id'], len(chunk), i, db_path)
                    print(f'  ✅ Chunk {i+1}/{len(chunks)} → {carrier_name}  [new]')

            if not dedup_hit and not use_dedup:
                _embed_chunk(chunk, carrier_type, out_path, sqlite_template=sqlite_template)
                carrier_paths.append(os.path.abspath(out_path))
                print(f'  ✅ Chunk {i+1}/{len(chunks)} → {carrier_name}')

    if dedup_hits:
        print(f'  ♻️  Dedup: {dedup_hits} hit(s), {dedup_saved//1024}KB saved')

    # Update manifest with actual carrier paths and save it
    manifest['chunks'] = [
        {
            'index':        i,
            'carrier':      os.path.basename(p),
            'carrier_path': p,
            'size_bytes':   len(chunks[i]),
        }
        for i, p in enumerate(carrier_paths)
    ]
    manifest['storage_dir'] = os.path.abspath(output_dir)

    manifest_path = os.path.join(output_dir, 'manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'  📋 Manifest saved → manifest.json')

    return carrier_paths


def load_chunks(manifest: dict) -> list:
    """
    Load and extract all chunks from carriers listed in a manifest.

    Returns
    -------
    list[bytes]  — chunks in correct order
    """
    chunks = []
    for entry in sorted(manifest['chunks'], key=lambda x: x['index']):
        path = entry['carrier_path']
        ext  = Path(path).suffix.lower()

        if ext == '.png':
            raw = img_extract(path)
        elif ext in ('.mkv', '.avi'):
            raw = reveal_from_video(path)
        elif ext == '.wav':
            raw = extract_audio(path)
        elif ext == '.db':
            raw = extract_sqlite(path)
        else:
            raise ValueError(f"Unsupported carrier: {path}")

        chunks.append(raw)
        print(f'  ✅ Loaded chunk {entry["index"]+1}/{len(manifest["chunks"])}')

    return chunks
