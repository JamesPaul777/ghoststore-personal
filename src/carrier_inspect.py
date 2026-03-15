import os
import sys
import sqlite3
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import numpy as np
import subprocess


def inspect_png(path: str) -> dict:
    """Analyse a PNG carrier's embedding capacity."""
    img = Image.open(path).convert("RGB")
    pixels = np.array(img)
    total_bits = pixels.size
    total_bytes = total_bits // 8
    usable_bytes = total_bytes - 4  # minus 4-byte header

    width, height = img.size

    print(f"\n🖼️  PNG Carrier Analysis: {os.path.basename(path)}")
    print(f"   Resolution:      {width} x {height} pixels")
    print(f"   Total pixels:    {width * height:,}")
    print(f"   Raw capacity:    {total_bytes:,} bytes ({total_bytes/1024:.1f} KB)")
    print(f"   Usable capacity: {usable_bytes:,} bytes ({usable_bytes/1024:.1f} KB)")
    print(f"   Recommended max payload (after compress+encrypt overhead): "
          f"{int(usable_bytes * 0.95):,} bytes")

    return {
        "type": "png",
        "width": width,
        "height": height,
        "usable_bytes": usable_bytes
    }


def inspect_video(path: str) -> dict:
    """Analyse a video carrier's embedding capacity."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-count_frames",
        "-of", "csv=p=0",
        path
    ], capture_output=True, text=True)

    parts = result.stdout.strip().split(",")
    codec = parts[0]
    width = int(parts[1])
    height = int(parts[2])
    frame_rate = parts[3]
    nb_frames = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None

    bytes_per_frame = (width * height * 3) // 8 - 4  # minus 4-byte header per frame

    print(f"\n📹 Video Carrier Analysis: {os.path.basename(path)}")
    print(f"   Codec:           {codec}")
    print(f"   Resolution:      {width} x {height}")
    print(f"   Frame rate:      {frame_rate} fps")

    if nb_frames:
        total_bytes = bytes_per_frame * nb_frames
        total_mb = total_bytes / (1024 ** 2)
        total_gb = total_bytes / (1024 ** 3)
        print(f"   Frame count:     {nb_frames:,}")
        print(f"   Per frame:       {bytes_per_frame:,} bytes ({bytes_per_frame/1024:.1f} KB)")
        print(f"   Total capacity:  {total_bytes:,} bytes ({total_mb:.1f} MB / {total_gb:.2f} GB)")
        print(f"   Recommended max: {int(total_bytes * 0.95):,} bytes "
              f"({total_gb * 0.95:.2f} GB)")
    else:
        print(f"   Per frame:       {bytes_per_frame:,} bytes ({bytes_per_frame/1024:.1f} KB)")
        print(f"   Frame count:     counting frames (this may take a moment)...")
        result2 = subprocess.run([
            "ffprobe", "-v", "error", "-count_frames",
            "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames",
            "-of", "csv=p=0", path
        ], capture_output=True, text=True)
        nb_frames = int(result2.stdout.strip()) if result2.stdout.strip().isdigit() else 0
        if nb_frames:
            total_bytes = bytes_per_frame * nb_frames
            total_gb = total_bytes / (1024 ** 3)
            print(f"   Frame count:     {nb_frames:,}")
            print(f"   Total capacity:  {total_bytes:,} bytes ({total_gb:.2f} GB)")

    return {
        "type": "video",
        "codec": codec,
        "width": width,
        "height": height,
        "nb_frames": nb_frames,
        "bytes_per_frame": bytes_per_frame
    }


def inspect_sqlite(path: str) -> dict:
    """Analyse a SQLite carrier — detects template, row count, and payload size."""
    from sqlite_carrier import _TEMPLATES, _MAGIC

    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in
                  conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        # Detect which template was used
        matched_name = None
        matched_tmpl = None
        for tmpl_name, tmpl in _TEMPLATES.items():
            if tmpl['table'] in tables:
                matched_name = tmpl_name
                matched_tmpl = tmpl
                break

        if matched_tmpl is None:
            print(f"\n🗄  SQLite file: {os.path.basename(path)}")
            print(f"   ⚠️  Not a GhostStore SQLite carrier — no recognised table found.")
            print(f"   Tables found: {', '.join(tables) or 'none'}")
            return {"type": "sqlite", "ghoststore": False}

        rows = conn.execute(
            f"SELECT {matched_tmpl['blob_col']} FROM {matched_tmpl['table']}"
        ).fetchall()

        total_blob_bytes = sum(len(r[0]) for r in rows)
        row_count = len(rows)

        # Check for GhostStore magic in first row
        is_ghoststore = False
        payload_bytes = 0
        if rows:
            first_blob = rows[0][0]
            if first_blob[:len(_MAGIC)] == _MAGIC:
                is_ghoststore = True
                payload_bytes = int.from_bytes(first_blob[len(_MAGIC):len(_MAGIC)+8], 'big')

        file_size = os.path.getsize(path)

        print(f"\n🗄  SQLite Carrier Analysis: {os.path.basename(path)}")
        print(f"   Template:        {matched_name}  ({matched_tmpl['description']})")
        print(f"   Table:           {matched_tmpl['table']}")
        print(f"   Rows:            {row_count:,}")
        print(f"   File size:       {file_size:,} bytes ({file_size/1024:.1f} KB)")
        print(f"   Total BLOB data: {total_blob_bytes:,} bytes ({total_blob_bytes/1024:.1f} KB)")
        if is_ghoststore:
            print(f"   Hidden payload:  {payload_bytes:,} bytes ({payload_bytes/1024:.1f} KB)  ✅ GhostStore carrier")
        else:
            print(f"   ⚠️  No GhostStore magic found — may not be a valid carrier")

    finally:
        conn.close()

    return {
        "type":          "sqlite",
        "ghoststore":    is_ghoststore,
        "template":      matched_name,
        "row_count":     row_count,
        "payload_bytes": payload_bytes,
        "file_size":     file_size,
    }


def inspect(path: str) -> dict:
    """Auto-detect carrier type and inspect it."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        return inspect_png(path)
    elif ext in (".mkv", ".avi", ".mov"):
        return inspect_video(path)
    elif ext == ".db":
        return inspect_sqlite(path)
    else:
        print(f"❌ Unsupported carrier type: {ext}")
        return {}


if __name__ == "__main__":
    inspect("carriers/demo_carrier.png")
