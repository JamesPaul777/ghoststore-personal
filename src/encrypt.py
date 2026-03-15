import os
import struct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def generate_key() -> bytes:
    """Generate a cryptographically secure 256-bit key."""
    return os.urandom(32)

def encrypt(data: bytes, key: bytes) -> bytes:
    """
    Encrypt bytes using AES-256-GCM.
    Returns: nonce (12 bytes) + ciphertext + auth tag (16 bytes)
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    print(f"🔐 Encrypted {len(data)} bytes → {len(nonce + ciphertext)} bytes "
          f"(+28 bytes overhead for nonce + auth tag)")
    return nonce + ciphertext

def decrypt(data: bytes, key: bytes) -> bytes:
    """
    Decrypt AES-256-GCM bytes.
    Expects: nonce (12 bytes) + ciphertext + auth tag
    """
    aesgcm = AESGCM(key)
    nonce = data[:12]
    ciphertext = data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)


if __name__ == "__main__":
    key = generate_key()
    original = b"Hello GhostStore" * 100
    encrypted = encrypt(original, key)
    decrypted = decrypt(encrypted, key)
    assert decrypted == original
    print("✅ encrypt.py smoke test passed.")
    print(f"🔑 Sample key (hex): {key.hex()}")
