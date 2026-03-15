from PIL import Image
import numpy as np

def extract(carrier_path: str) -> bytes:
    """Extract hidden payload bytes from a PNG image using LSB steganography."""
    
    img = Image.open(carrier_path).convert("RGB")
    pixels = np.array(img, dtype=np.uint8)
    flat = pixels.flatten()
    
    # Read the first 32 bits (4 bytes) to get the payload length header
    header_bits = flat[:32] & 1
    payload_length = 0
    for bit in header_bits:
        payload_length = (payload_length << 1) | int(bit)
    
    # Now read the next payload_length * 8 bits
    total_bits_needed = 32 + payload_length * 8
    if total_bits_needed > len(flat):
        raise ValueError("Carrier image is too small or does not contain a valid payload.")
    
    payload_bits = flat[32:total_bits_needed] & 1
    
    # Reconstruct bytes from bits
    payload_bytes = bytearray()
    for i in range(0, len(payload_bits), 8):
        byte = 0
        for bit in payload_bits[i:i+8]:
            byte = (byte << 1) | int(bit)
        payload_bytes.append(byte)
    
    print(f"✅ Extracted {payload_length} bytes from {carrier_path}")
    return bytes(payload_bytes)


if __name__ == "__main__":
    result = extract("test_output.png")
    print(f"Extracted message: {result.decode('utf-8')}")