import os
import sys
import math
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image
import numpy as np
from encrypt import encrypt, decrypt, generate_key
from compress import compress, decompress
from embed import embed
from extract import extract


def split_bytes(data: bytes, chunk_size: int) -> list:
    """Split bytes into chunks of chunk_size."""
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]


def get_carrier_capacity(carrier_path: str) -> int:
    """Return the usable byte capacity of a PNG carrier."""
    img = Image.open(carrier_path).convert("RGB")
    pixels = np.array(img)
    return (pixels.size // 8) - 4  # minus 4-byte header


def hide_multi(secret_file: str, carrier_dir: str, output_dir: str, key: bytes) -> dict:
    """
    Hide a file across multiple PNG carriers.

    carrier_dir  → folder containing carrier PNG images
    output_dir   → folder where output PNGs will be saved
    Returns a manifest describing how to reconstruct the file.
    """
    print(f"\n🚀 GhostStore MULTI-CARRIER HIDE")
    print(f"   Secret file: {secret_file}")
    print("─" * 50)

    # Read and process the secret file
    with open(secret_file, "rb") as f:
        raw = f.read()
    print(f"📄 Read {len(raw):,} bytes")

    compressed = compress(raw)
    encrypted = encrypt(compressed, key)
    print(f"   Final payload: {len(encrypted):,} bytes")

    # Load available carriers
    carriers = sorted([
        os.path.join(carrier_dir, f)
        for f in os.listdir(carrier_dir)
        if f.lower().endswith(".png")
    ])

    if not carriers:
        raise ValueError(f"No PNG carriers found in {carrier_dir}")

    # Calculate capacity of each carrier
    capacities = [get_carrier_capacity(c) for c in carriers]
    total_capacity = sum(capacities)

    print(f"\n📦 Carriers available: {len(carriers)}")
    print(f"   Total capacity:    {total_capacity:,} bytes ({total_capacity/1024:.1f} KB)")
    print(f"   Payload size:      {len(encrypted):,} bytes ({len(encrypted)/1024:.1f} KB)")

    if len(encrypted) > total_capacity:
        raise ValueError(
            f"Payload too large: {len(encrypted):,} bytes needed, "
            f"only {total_capacity:,} bytes available across {len(carriers)} carriers."
        )

    # Split payload across carriers
    os.makedirs(output_dir, exist_ok=True)
    manifest = {
        "secret_file": os.path.basename(secret_file),
        "total_bytes": len(raw),
        "payload_bytes": len(encrypted),
        "carriers_used": [],
        "key_hint": key.hex()[:8] + "..."  # first 4 bytes as hint only
    }

    remaining = encrypted
    carriers_used = 0

    for i, (carrier_path, capacity) in enumerate(zip(carriers, capacities)):
        if not remaining:
            break

        chunk = remaining[:capacity]
        remaining = remaining[capacity:]

        carrier_name = os.path.basename(carrier_path)
        output_name = f"part_{i+1:03d}_{carrier_name}"
        output_path = os.path.join(output_dir, output_name)

        embed(carrier_path, chunk, output_path)
        manifest["carriers_used"].append({
            "part": i + 1,
            "filename": output_name,
            "bytes_embedded": len(chunk)
        })
        carriers_used += 1
        print(f"   Part {i+1}: {len(chunk):,} bytes → {output_name}")

    print(f"\n✅ DONE — {len(encrypted):,} bytes split across {carriers_used} carriers")
    print(f"   Output folder: {output_dir}")
    return manifest


def reveal_multi(output_dir: str, key: bytes, recovered_file: str) -> None:
    """
    Reconstruct a file from multiple PNG carriers.

    output_dir     → folder containing the output PNGs (in order)
    key            → AES-256 decryption key
    recovered_file → where to save the recovered file
    """
    print(f"\n🔍 GhostStore MULTI-CARRIER REVEAL")
    print("─" * 50)

    # Find all part files in order
    parts = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.lower().startswith("part_") and f.lower().endswith(".png")
    ])

    if not parts:
        raise ValueError(f"No part files found in {output_dir}")

    print(f"   Found {len(parts)} carrier parts")

    # Extract and reassemble
    encrypted = b""
    for part_path in parts:
        chunk = extract(part_path)
        encrypted += chunk
        print(f"   Extracted {len(chunk):,} bytes from {os.path.basename(part_path)}")

    print(f"\n   Total extracted: {len(encrypted):,} bytes")

    # Decrypt and decompress
    compressed = decrypt(encrypted, key)
    print(f"🔓 Decrypted successfully")

    raw = decompress(compressed)
    print(f"📦 Decompressed → {len(raw):,} bytes")

    with open(recovered_file, "wb") as f:
        f.write(raw)

    print(f"\n✅ DONE — file recovered to {recovered_file}")


if __name__ == "__main__":
    import shutil

    print("🧪 Multi-carrier split test")
    print("=" * 50)

    # Create a test secret file larger than one small carrier
    secret_content = b"GhostStore Multi-Carrier Test Data - " * 2000  # ~72KB
    with open("multi_secret.txt", "wb") as f:
        f.write(secret_content)
    print(f"📄 Created test secret: {len(secret_content):,} bytes")

    # Create multiple small carriers (200x200 each = ~46KB each)
    test_carriers = "test_carriers"
    test_output = "test_multi_output"
    os.makedirs(test_carriers, exist_ok=True)

    for i in range(6):
        carrier = Image.fromarray(
            np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8), "RGB"
        )
        carrier.save(os.path.join(test_carriers, f"carrier_{i+1:03d}.png"))
    print(f"🖼️  Created 6 test carriers (200x200 each)")

    # Run multi-carrier hide
    key = generate_key()
    manifest = hide_multi("multi_secret.txt", test_carriers, test_output, key)

    # Run multi-carrier reveal
    reveal_multi(test_output, key, "multi_recovered.txt")

    # Verify
    with open("multi_secret.txt", "rb") as f:
        original = f.read()
    with open("multi_recovered.txt", "rb") as f:
        recovered = f.read()

    if original == recovered:
        print("\n🎉 PERFECT MATCH — file reconstructed perfectly from multiple carriers")
    else:
        print("\n❌ MISMATCH")

    # Cleanup
    shutil.rmtree(test_carriers)
    shutil.rmtree(test_output)
    os.remove("multi_secret.txt")
    os.remove("multi_recovered.txt")

