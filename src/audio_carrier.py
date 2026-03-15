import os
import sys
import struct
import wave
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))


def get_audio_capacity(wav_path: str) -> dict:
    """Analyse a WAV file's embedding capacity."""
    with wave.open(wav_path, 'rb') as wav:
        channels = wav.getnchannels()
        sampwidth = wav.getsampwidth()
        framerate = wav.getframerate()
        nframes = wav.getnframes()
        duration = nframes / framerate

    # Each sample holds 1 bit in its LSB
    total_samples = nframes * channels
    usable_bytes = (total_samples // 8) - 4  # minus 4-byte header

    print(f"\n🎵 Audio Carrier Analysis: {os.path.basename(wav_path)}")
    print(f"   Channels:        {channels} ({'stereo' if channels == 2 else 'mono'})")
    print(f"   Sample rate:     {framerate:,} Hz")
    print(f"   Bit depth:       {sampwidth * 8} bit")
    print(f"   Duration:        {duration:.1f} seconds")
    print(f"   Total samples:   {total_samples:,}")
    print(f"   Usable capacity: {usable_bytes:,} bytes ({usable_bytes/1024:.1f} KB)")

    return {
        "channels": channels,
        "sampwidth": sampwidth,
        "framerate": framerate,
        "nframes": nframes,
        "usable_bytes": usable_bytes
    }


def embed_audio(carrier_path: str, payload_bytes: bytes, output_path: str) -> None:
    """Hide payload bytes inside a WAV audio file using LSB steganography."""

    with wave.open(carrier_path, 'rb') as wav:
        params = wav.getparams()
        frames = wav.readframes(wav.getnframes())

    # Convert frames to numpy array of samples
    sampwidth = params.sampwidth
    if sampwidth == 2:
        samples = np.frombuffer(frames, dtype=np.int16).copy()
    elif sampwidth == 1:
        samples = np.frombuffer(frames, dtype=np.uint8).copy()
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes. Use 16-bit or 8-bit WAV.")

    # Prepend 4-byte header with payload length
    header = len(payload_bytes).to_bytes(4, byteorder='big')
    data = header + payload_bytes

    # Convert to bits
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)

    if len(bits) > len(samples):
        raise ValueError(
            f"Payload too large: need {len(bits)} bits, "
            f"carrier only has {len(samples)} samples."
        )

    # Embed each bit into LSB of each sample
    for i, bit in enumerate(bits):
        if sampwidth == 2:
            samples[i] = (samples[i] & ~1) | bit
        else:
            samples[i] = (samples[i] & ~1) | bit

    # Write output WAV
    with wave.open(output_path, 'wb') as out_wav:
        out_wav.setparams(params)
        out_wav.writeframes(samples.tobytes())

    size_kb = os.path.getsize(output_path) / 1024
    print(f"✅ Embedded {len(payload_bytes):,} bytes into {output_path} ({size_kb:.1f} KB)")


def extract_audio(carrier_path: str) -> bytes:
    """Extract hidden payload bytes from a WAV audio file."""

    with wave.open(carrier_path, 'rb') as wav:
        sampwidth = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if sampwidth == 2:
        samples = np.frombuffer(frames, dtype=np.int16)
    elif sampwidth == 1:
        samples = np.frombuffer(frames, dtype=np.uint8)
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth} bytes.")

    # Read first 32 bits to get payload length
    header_bits = samples[:32] & 1
    payload_length = 0
    for bit in header_bits:
        payload_length = (payload_length << 1) | int(bit)

    # Read payload bits
    total_bits = 32 + payload_length * 8
    if total_bits > len(samples):
        raise ValueError("Audio carrier too small or does not contain a valid payload.")

    payload_bits = samples[32:total_bits] & 1

    # Reconstruct bytes
    payload = bytearray()
    for i in range(0, len(payload_bits), 8):
        byte = 0
        for bit in payload_bits[i:i + 8]:
            byte = (byte << 1) | int(bit)
        payload.append(byte)

    print(f"✅ Extracted {payload_length:,} bytes from {carrier_path}")
    return bytes(payload)


def create_wav_carrier(output_path: str, duration_seconds: int = 10,
                        framerate: int = 44100, channels: int = 2) -> None:
    """Create a blank WAV carrier file for testing."""
    nframes = duration_seconds * framerate
    samples = np.random.randint(-32768, 32767,
                                 nframes * channels, dtype=np.int16)
    with wave.open(output_path, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(framerate)
        wav.writeframes(samples.tobytes())
    size_kb = os.path.getsize(output_path) / 1024
    print(f"🎵 Created WAV carrier: {output_path} "
          f"({duration_seconds}s, {framerate}Hz, {channels}ch, {size_kb:.1f} KB)")


if __name__ == "__main__":
    print("🧪 Audio carrier test")
    print("=" * 50)

    # Create a test WAV carrier (10 seconds stereo)
    create_wav_carrier("test_audio_carrier.wav", duration_seconds=10)

    # Analyse capacity
    info = get_audio_capacity("test_audio_carrier.wav")

    # Embed a payload
    payload = b"GhostStore Audio Carrier Test" * 200
    print(f"\n📦 Embedding {len(payload):,} bytes...")
    embed_audio("test_audio_carrier.wav", payload, "test_audio_output.wav")

    # Extract
    recovered = extract_audio("test_audio_output.wav")

    # Verify
    if recovered == payload:
        print("🎉 PERFECT MATCH — payload survived WAV audio embed + extract")
    else:
        print("❌ MISMATCH")

    # Cleanup
    os.remove("test_audio_carrier.wav")
    os.remove("test_audio_output.wav")
