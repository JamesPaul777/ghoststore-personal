import os
import sys
import subprocess
import tempfile
import struct
from PIL import Image
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from embed import embed
from extract import extract


def get_video_capacity(video_path: str) -> dict:
    """Analyse a video file and report its embedding capacity."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_frames,r_frame_rate,codec_name",
        "-of", "csv=p=0",
        video_path
    ], capture_output=True, text=True)

    parts = result.stdout.strip().split(",")
    codec = parts[0]
    width = int(parts[1])
    height = int(parts[2])
    frame_rate = parts[3]
    nb_frames = int(parts[4]) if parts[4].isdigit() else "unknown"

    # Each frame: width * height * 3 channels * 1 bit per channel = capacity in bits
    bits_per_frame = width * height * 3
    bytes_per_frame = bits_per_frame // 8

    if isinstance(nb_frames, int):
        total_bytes = bytes_per_frame * nb_frames
        total_gb = total_bytes / (1024 ** 3)
    else:
        total_bytes = "unknown"
        total_gb = "unknown"

    print(f"\n📹 Video Analysis: {os.path.basename(video_path)}")
    print(f"   Codec:      {codec}")
    print(f"   Resolution: {width}x{height}")
    print(f"   Frames:     {nb_frames}")
    print(f"   Frame rate: {frame_rate} fps")
    print(f"   Capacity per frame: {bytes_per_frame:,} bytes ({bytes_per_frame/1024:.1f} KB)")
    if isinstance(total_bytes, int):
        print(f"   Total capacity: {total_bytes:,} bytes ({total_gb:.2f} GB)")

    return {
        "codec": codec, "width": width, "height": height,
        "nb_frames": nb_frames, "bytes_per_frame": bytes_per_frame,
        "total_bytes": total_bytes
    }


def extract_frames(video_path: str, output_dir: str) -> list:
    """Extract all frames from a video as PNG files."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n🎬 Extracting frames from {os.path.basename(video_path)}...")
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vsync", "0",
        os.path.join(output_dir, "frame_%06d.png"),
        "-y", "-loglevel", "error"
    ], check=True)
    frames = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".png")
    ])
    print(f"   Extracted {len(frames)} frames")
    return frames


def reassemble_video(frames_dir: str, output_path: str, frame_rate: str = "30") -> None:
    """Reassemble frames into a lossless FFV1 video."""
    print(f"\n🎞️  Reassembling frames into lossless video...")
    subprocess.run([
        "ffmpeg",
        "-framerate", frame_rate,
        "-i", os.path.join(frames_dir, "frame_%06d.png"),
        "-c:v", "ffv1",        # FFV1 lossless codec — preserves every pixel exactly
        "-level", "3",
        "-y", output_path,
        "-loglevel", "error"
    ], check=True)
    size_mb = os.path.getsize(output_path) / (1024 ** 2)
    print(f"   ✅ Saved lossless video: {output_path} ({size_mb:.1f} MB)")


def hide_in_video(payload_bytes: bytes, carrier_video: str, output_video: str) -> None:
    """
    Hide payload bytes across the frames of a lossless video.
    Splits payload across as many frames as needed.
    """
    print(f"\n🚀 GhostStore VIDEO HIDE")
    print(f"   Payload size: {len(payload_bytes):,} bytes")

    with tempfile.TemporaryDirectory() as tmp:
        frames_dir = os.path.join(tmp, "frames")
        modified_dir = os.path.join(tmp, "modified")
        os.makedirs(modified_dir, exist_ok=True)

        # Extract all frames
        frames = extract_frames(carrier_video, frames_dir)

        # Calculate how many frames we need
        test_img = np.array(Image.open(frames[0]))
        bytes_per_frame = (test_img.size) // 8 - 4  # minus 4-byte header

        # Prepend total payload length as 8-byte header in frame 0
        header = len(payload_bytes).to_bytes(8, byteorder="big")
        full_data = header + payload_bytes

        # Split data into chunks, one chunk per frame
        chunks = []
        for i in range(0, len(full_data), bytes_per_frame):
            chunks.append(full_data[i:i + bytes_per_frame])

        if len(chunks) > len(frames):
            raise ValueError(
                f"Payload too large: needs {len(chunks)} frames, "
                f"video only has {len(frames)} frames."
            )

        print(f"   Using {len(chunks)} of {len(frames)} frames")

        # Embed each chunk into its frame
        for i, frame_path in enumerate(frames):
            out_path = os.path.join(modified_dir, f"frame_{i+1:06d}.png")
            if i < len(chunks):
                embed(frame_path, chunks[i], out_path)
            else:
                # Copy unmodified frames
                import shutil
                shutil.copy(frame_path, out_path)

        # Reassemble into lossless video
        reassemble_video(modified_dir, output_video)

    print(f"\n✅ DONE — payload hidden inside {output_video}")


def reveal_from_video(carrier_video: str) -> bytes:
    """Extract hidden payload bytes from a lossless video."""
    print(f"\n🔍 GhostStore VIDEO REVEAL")

    with tempfile.TemporaryDirectory() as tmp:
        frames_dir = os.path.join(tmp, "frames")
        frames = extract_frames(carrier_video, frames_dir)

        # Read 8-byte header from frame 0 to get total payload length
        first_chunk = extract(frames[0])
        total_length = int.from_bytes(first_chunk[:8], byteorder="big")
        data = first_chunk[8:]

        print(f"   Total payload: {total_length:,} bytes")

        # Read subsequent frames until we have all the data
        for frame_path in frames[1:]:
            if len(data) >= total_length:
                break
            data += extract(frame_path)

        payload = data[:total_length]
        print(f"   ✅ Extracted {len(payload):,} bytes from video")
        return payload


if __name__ == "__main__":
    from PIL import Image
    import numpy as np

    print("🎬 Creating a test video (3 seconds, 30fps = 90 frames)...")

    with tempfile.TemporaryDirectory() as tmp:
        # Generate 90 random frames
        frames_dir = os.path.join(tmp, "frames")
        os.makedirs(frames_dir)
        for i in range(90):
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            Image.fromarray(frame, "RGB").save(
                os.path.join(frames_dir, f"frame_{i+1:06d}.png")
            )

        # Assemble into lossless video
        test_video = "test_carrier.mkv"
        reassemble_video(frames_dir, test_video)

    # Analyse capacity
    info = get_video_capacity(test_video)

    # Hide a payload
    payload = b"GhostStore Video Test - Phase 3" * 500
    hide_in_video(payload, test_video, "test_output.mkv")

    # Reveal it
    recovered = reveal_from_video("test_output.mkv")

    # Verify
    if recovered == payload:
        print("\n🎉 PERFECT MATCH — payload survived video embed + extract")
    else:
        print("\n❌ MISMATCH")

    # Cleanup
    os.remove("test_carrier.mkv")
    os.remove("test_output.mkv")

