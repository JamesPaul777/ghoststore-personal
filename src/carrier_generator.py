"""
carrier_generate.py  —  GhostStore synthetic carrier generation (Mode 1)
Session 7: Generate & Hide mode — create a carrier when the user has no media file.

All carriers are procedurally generated to look like ordinary media:
  - Image  : soft colour gradient + subtle noise  (looks like a blurry photo)
  - Audio  : near-silence room-tone noise         (sounds like ambient background)
  - Video  : slow gradient pan sequence via FFmpeg FFV1

Each generator accepts the minimum payload size in bytes and returns the
path to a temporary file that is large enough to hold that payload.
Temporary files should be cleaned up by the caller after embedding.
"""

import os
import math
import shutil
import subprocess
import sys
import tempfile

# Suppress console window when running as a frozen .exe on Windows
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
import wave

import numpy as np
from PIL import Image

# Embed uses 1 LSB per channel.
# PNG  : RGB  → 3 bits / pixel  → capacity_bytes = (W × H × 3) // 8
# WAV  : 16-bit mono → 1 bit / sample → capacity_bytes = samples // 8
# Video: same as PNG per frame  → capacity_bytes = frames × (W × H × 3) // 8

_SAFETY = 1.5       # carrier must hold 1.5× the payload to give headroom
_MIN_IMAGE_SIDE = 64
_MIN_WAV_SECONDS = 1
_MIN_VIDEO_FRAMES = 30
_VIDEO_W, _VIDEO_H = 640, 480


# ─────────────────────────────────────────────────────────────────────────────
# Image
# ─────────────────────────────────────────────────────────────────────────────

def generate_image_carrier(min_payload_bytes: int) -> str:
    """
    Return path to a temporary PNG large enough to hide min_payload_bytes.
    The image is a soft pastel gradient with a light noise layer —
    visually similar to a slightly out-of-focus photograph.
    """
    # pixels needed so (pixels × 3 bits) // 8 >= payload × SAFETY
    pixels_needed = math.ceil(min_payload_bytes * _SAFETY * 8 / 3)
    side = max(math.ceil(math.sqrt(pixels_needed)), _MIN_IMAGE_SIDE)

    rng = np.random.default_rng()

    # Gradient base
    x_grad = np.linspace(60, 200, side, dtype=np.float32)
    y_grad = np.linspace(80, 180, side, dtype=np.float32)
    xx, yy = np.meshgrid(x_grad, y_grad)

    # Three channels with independent mild noise (+/- 15 counts)
    noise = rng.integers(-15, 16, (side, side, 3), dtype=np.int16)
    r = np.clip(xx          + noise[:, :, 0], 0, 255).astype(np.uint8)
    g = np.clip(yy * 0.8    + noise[:, :, 1], 0, 255).astype(np.uint8)
    b = np.clip((xx + yy) * 0.4 + noise[:, :, 2] + 40, 0, 255).astype(np.uint8)

    arr = np.stack([r, g, b], axis=2)
    img = Image.fromarray(arr, 'RGB')

    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.close()
    img.save(tmp.name, format='PNG', optimize=False)
    return tmp.name


# ─────────────────────────────────────────────────────────────────────────────
# Audio
# ─────────────────────────────────────────────────────────────────────────────

def generate_audio_carrier(min_payload_bytes: int, sample_rate: int = 44100) -> str:
    """
    Return path to a temporary WAV (16-bit, mono) large enough to hide
    min_payload_bytes.  The audio is very-low-amplitude Gaussian noise —
    perceptually indistinguishable from room silence.
    """
    samples_needed = math.ceil(min_payload_bytes * _SAFETY * 8)
    samples_needed = max(samples_needed, sample_rate * _MIN_WAV_SECONDS)

    rng = np.random.default_rng()
    # Amplitude ≈ 40 counts out of 32768 → effectively inaudible room tone
    noise = rng.integers(-40, 41, samples_needed, dtype=np.int16)

    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.close()

    with wave.open(tmp.name, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(noise.tobytes())

    return tmp.name


# ─────────────────────────────────────────────────────────────────────────────
# Video
# ─────────────────────────────────────────────────────────────────────────────

def generate_video_carrier(
    min_payload_bytes: int,
    ffmpeg_path: str = 'ffmpeg',
    fps: int = 30,
) -> str:
    """
    Return path to a temporary FFV1 MKV large enough to hide min_payload_bytes.
    Frames are a slowly drifting colour gradient — looks like a gentle slow-pan
    of a plain wall or sky.
    Uses FFmpeg so the output is a proper lossless MKV identical in structure
    to a user-converted video carrier.
    """
    bytes_per_frame = (_VIDEO_W * _VIDEO_H * 3) // 8
    frames_needed   = max(
        math.ceil(min_payload_bytes * _SAFETY / bytes_per_frame),
        _MIN_VIDEO_FRAMES,
    )

    tmp_frames = tempfile.mkdtemp(prefix='gs_frames_')
    tmp_out    = tempfile.NamedTemporaryFile(suffix='.mkv', delete=False)
    tmp_out.close()

    rng = np.random.default_rng(42)

    try:
        for i in range(frames_needed):
            drift = i * 1.5   # slow horizontal colour drift
            arr   = np.zeros((_VIDEO_H, _VIDEO_W, 3), dtype=np.uint8)

            r_row = np.clip(np.linspace(drift, drift + 180, _VIDEO_W), 0, 255).astype(np.uint8)
            g_col = np.clip(np.linspace(80, 200, _VIDEO_H), 0, 255).astype(np.uint8)
            b_val = int(np.clip(120 + drift * 0.3, 0, 255))

            arr[:, :, 0] = r_row[np.newaxis, :]
            arr[:, :, 1] = g_col[:, np.newaxis]
            arr[:, :, 2] = b_val

            # Slight per-frame noise so FFV1 doesn't collapse identical frames
            arr = np.clip(
                arr.astype(np.int16) + rng.integers(-5, 6, (_VIDEO_H, _VIDEO_W, 3), dtype=np.int16),
                0, 255,
            ).astype(np.uint8)

            Image.fromarray(arr, 'RGB').save(
                os.path.join(tmp_frames, f'frame_{i:06d}.png')
            )

        cmd = [
            ffmpeg_path, '-y',
            '-framerate', str(fps),
            '-i',         os.path.join(tmp_frames, 'frame_%06d.png'),
            '-c:v',       'ffv1',
            tmp_out.name,
        ]
        result = subprocess.run(cmd, capture_output=True, creationflags=_SUBPROCESS_FLAGS)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed:\n{result.stderr.decode(errors='replace')}"
            )

    finally:
        shutil.rmtree(tmp_frames, ignore_errors=True)

    return tmp_out.name
