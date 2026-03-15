import zstandard as zstd

def compress(data: bytes) -> bytes:
    """Compress bytes using Zstandard."""
    compressor = zstd.ZstdCompressor(level=10)
    compressed = compressor.compress(data)
    if len(data) > 0:
        print(f"🗜️  Compressed {len(data)} bytes → {len(compressed)} bytes "
              f"({100 - round(len(compressed)/len(data)*100)}% reduction)")
    else:
        print("🗜️  Compressed 0 bytes (empty input)")
    return compressed

def decompress(data: bytes) -> bytes:
    """Decompress Zstandard bytes."""
    decompressor = zstd.ZstdDecompressor()
    return decompressor.decompress(data)


if __name__ == "__main__":
    original = b"Hello GhostStore" * 100
    compressed = compress(original)
    restored = decompress(compressed)
    assert restored == original
    print("✅ compress.py smoke test passed.")

