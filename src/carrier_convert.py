"""
carrier_convert.py — GhostStore
Converts user-supplied media files into a GhostStore-compatible FFV1 MKV carrier.

BUG FIX (Session 9):
  - Converted MKV is now written to a system temp directory, not next to the source.
  - This fixes failure when the source is on a read-only / external drive (e.g. A:, DVD).
  - Also fixes paths with spaces on Windows (subprocess list args, no shell=True).

Supported input formats: MP4, MOV, AVI, WMV, MKV, PNG, JPG, WEBP, BMP, WAV, MP3, FLAC
"""

import os
import subprocess
import tempfile
from pathlib import Path

# Extensions that need video conversion → FFV1 MKV
_VIDEO_EXTS  = {'.mp4', '.mov', '.avi', '.wmv', '.mkv', '.m4v'}
# Extensions that are already lossless images — embed directly via Pillow
_IMAGE_EXTS  = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
# Audio extensions — convert to WAV via FFmpeg
_AUDIO_EXTS  = {'.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a'}


def prepare_carrier(carrier_path: str, ffmpeg_path: str = 'ffmpeg') -> tuple[str, str]:
    """
    Inspect carrier_path and return (usable_path, carrier_type).

    carrier_type is one of: 'image' | 'video' | 'audio'

    For video/audio inputs that need transcoding, a converted temp file is
    created in the system temp directory (not next to the source — avoids
    read-only drive issues). The caller is responsible for cleanup if needed;
    GhostStore leaves temp files in place so Windows doesn't reclaim them
    before embedding finishes.

    Raises:
        FileNotFoundError  — source does not exist
        ValueError         — unrecognised extension
        RuntimeError       — FFmpeg conversion failed (includes FFmpeg stderr)
    """
    src = Path(carrier_path)
    if not src.exists():
        raise FileNotFoundError(f'Carrier not found: {carrier_path}')

    ext = src.suffix.lower()

    # ── Image — no conversion needed ─────────────────────────────────────────
    if ext in _IMAGE_EXTS:
        return str(src), 'image'

    # ── Video — transcode to FFV1 MKV in temp dir ────────────────────────────
    if ext in _VIDEO_EXTS:
        # Use system temp dir, not source location (fixes read-only drive bug)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='_gs_carrier.mkv',
                                             prefix='ghoststore_',
                                             dir=tempfile.gettempdir())
        os.close(tmp_fd)  # FFmpeg will open it itself

        cmd = [
            ffmpeg_path,
            '-i', str(src),      # subprocess list → spaces handled correctly
            '-c:v', 'ffv1',
            '-level', '3',
            '-an',               # strip audio — not needed for steganography
            '-y',                # overwrite temp file
            tmp_path,
            '-loglevel', 'error',
        ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors='replace').strip()
            os.unlink(tmp_path)
            raise RuntimeError(
                f'FFmpeg video conversion failed.\n'
                f'Source: {src}\n'
                f'FFmpeg error: {stderr or "(no output — check ffmpeg is in PATH)"}'
            )

        return tmp_path, 'video'

    # ── Audio — transcode to WAV in temp dir ─────────────────────────────────
    if ext in _AUDIO_EXTS:
        if ext == '.wav':
            return str(src), 'audio'   # WAV is already fine

        tmp_fd, tmp_path = tempfile.mkstemp(suffix='_gs_carrier.wav',
                                             prefix='ghoststore_',
                                             dir=tempfile.gettempdir())
        os.close(tmp_fd)

        cmd = [
            ffmpeg_path,
            '-i', str(src),
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-y',
            tmp_path,
            '-loglevel', 'error',
        ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors='replace').strip()
            os.unlink(tmp_path)
            raise RuntimeError(
                f'FFmpeg audio conversion failed.\n'
                f'Source: {src}\n'
                f'FFmpeg error: {stderr or "(no output — check ffmpeg is in PATH)"}'
            )

        return tmp_path, 'audio'

    raise ValueError(
        f'Unsupported carrier format: {ext}\n'
        f'Supported: images ({", ".join(_IMAGE_EXTS)}), '
        f'video ({", ".join(_VIDEO_EXTS)}), '
        f'audio ({", ".join(_AUDIO_EXTS)})'
    )
