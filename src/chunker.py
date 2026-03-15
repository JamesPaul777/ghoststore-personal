"""
chunker.py  —  GhostStore payload chunker
Session 8: split encrypted bytes into fixed-size chunks for multi-carrier storage.

split(data, chunk_size) → list[bytes]
reassemble(chunks)      → bytes
"""

import math


DEFAULT_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB


def split(data: bytes, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list:
    """
    Split data into fixed-size chunks.
    Last chunk may be smaller than chunk_size.

    Returns
    -------
    list[bytes]
    """
    if not data:
        raise ValueError("Cannot chunk empty data.")
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1.")

    total   = len(data)
    n       = math.ceil(total / chunk_size)
    chunks  = [data[i * chunk_size : (i + 1) * chunk_size] for i in range(n)]
    return chunks


def reassemble(chunks: list) -> bytes:
    """
    Reassemble chunks back into the original data.

    Parameters
    ----------
    chunks : list[bytes]  — in correct order

    Returns
    -------
    bytes
    """
    if not chunks:
        raise ValueError("No chunks to reassemble.")
    return b''.join(chunks)
