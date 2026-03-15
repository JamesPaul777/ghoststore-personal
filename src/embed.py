from PIL import Image
import numpy as np

def embed(carrier_path: str, payload_bytes: bytes, output_path: str) -> None:
    """Hide payload_bytes inside a PNG image using LSB steganography."""
    
    img = Image.open(carrier_path).convert("RGB")
    pixels = np.array(img, dtype=np.uint8)
    
    # Prepend a 4-byte header storing the payload length
    payload_length = len(payload_bytes)
    header = payload_length.to_bytes(4, byteorder="big")
    data = header + payload_bytes
    
    # Convert data to a flat list of bits
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    
    # Check the image has enough pixels to carry the payload
    max_bits = pixels.size  # each pixel channel holds 1 bit
    if len(bits) > max_bits:
        raise ValueError(
            f"Payload too large: need {len(bits)} bits, "
            f"carrier only holds {max_bits} bits."
        )
    
    # Embed each bit into the LSB of each channel value
    flat = pixels.flatten()
    for i, bit in enumerate(bits):
        flat[i] = (flat[i] & 0xFE) | bit  # clear LSB then set it
    
    # Reshape back and save as PNG (lossless)
    result = flat.reshape(pixels.shape)
    Image.fromarray(result, "RGB").save(output_path, format="PNG")
    print(f"✅ Embedded {payload_length} bytes into {output_path}")


if __name__ == "__main__":
    # Quick smoke test
    img = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8), "RGB")
    img.save("test_carrier.png")
    embed("test_carrier.png", b"Hello GhostStore", "test_output.png")
    print("embed.py smoke test passed.")