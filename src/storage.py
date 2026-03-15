"""
storage.py  —  GhostStore Personal storage manager
save(chunks, output_dir, manifest) → list[str]  (carrier paths)
load_chunks(manifest)              → list[bytes]
"""

import json
import os
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


_GENERATORS = {
    'image': generate_image_carrier,
    'video': generate_video_carrier,
    'audio': generate_audio_carrier,
}

_EXT = {
    'image': '.png',
    'video': '.mkv',
    'audio': '.wav',
}


def _embed_chunk(chunk: bytes, carrier_type: str, out_path: str):
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


def _embed_chunk_into_user_carrier(chunk: bytes, carrier_path: str, out_path: str):
    prepared, ctype = prepare_carrier(carrier_path)
    correct_ext = _EXT[ctype]
    base = str(out_path)
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
        if prepared != carrier_path and os.path.exists(prepared):
            os.remove(prepared)
    return ctype, actual_out


def save(
    chunks: list,
    output_dir: str,
    manifest: dict,
    carrier_type: str = 'image',
    user_carriers: list = None,
    db_path=None,
) -> list:
    os.makedirs(output_dir, exist_ok=True)
    ext = _EXT.get(carrier_type, '.png')
    carrier_paths = []

    for i, chunk in enumerate(chunks):
        if user_carriers and i < len(user_carriers):
            out_path_base = os.path.join(output_dir, f'carrier_{i:04d}')
            actual_ctype, actual_out = _embed_chunk_into_user_carrier(
                chunk, user_carriers[i], out_path_base)
            carrier_paths.append(os.path.abspath(actual_out))
            print(f'  ✅ Chunk {i+1}/{len(chunks)} → {os.path.basename(actual_out)}  [{actual_ctype}]')
        else:
            carrier_name = f'carrier_{i:04d}{ext}'
            out_path = os.path.join(output_dir, carrier_name)
            _embed_chunk(chunk, carrier_type, out_path)
            carrier_paths.append(os.path.abspath(out_path))
            print(f'  ✅ Chunk {i+1}/{len(chunks)} → {carrier_name}')

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
        else:
            raise ValueError(f"Unsupported carrier: {path}")
        chunks.append(raw)
        print(f'  ✅ Loaded chunk {entry["index"]+1}/{len(manifest["chunks"])}')
    return chunks
