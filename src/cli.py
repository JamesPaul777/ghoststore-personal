import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import argparse
from pipeline import hide, reveal
from encrypt import generate_key
from video_carrier import hide_in_video, reveal_from_video
from audio_carrier import embed_audio, extract_audio
from compress import compress, decompress
from encrypt import encrypt, decrypt
from carrier_inspect import inspect
from carrier_convert import prepare_carrier


VIDEO_EXTENSIONS = ['.mkv', '.avi', '.mov', '.mp4', '.m4v', '.wmv']
AUDIO_EXTENSIONS = ['.wav']


def main():
    parser = argparse.ArgumentParser(
        prog="ghoststore",
        description="👻 GhostStore — Universal Steganographic File Storage"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- HIDE command ---
    hide_parser = subparsers.add_parser("hide", help="Hide a file inside any photo, video or audio")
    hide_parser.add_argument("secret", help="Path to the secret file to hide")
    hide_parser.add_argument("carrier", help="Carrier file (JPEG, PNG, MP4, MOV, MKV, WAV...)")
    hide_parser.add_argument("output", help="Path to save the output file")
    hide_parser.add_argument("--key", help="Hex key (32 bytes). Omit to generate a new one.")
    hide_parser.add_argument("--no-convert", action="store_true",
                             help="Skip carrier conversion")

    # --- REVEAL command ---
    reveal_parser = subparsers.add_parser("reveal", help="Reveal a hidden file from a carrier")
    reveal_parser.add_argument("carrier", help="Carrier file containing hidden data")
    reveal_parser.add_argument("output", help="Path to save the recovered file")
    reveal_parser.add_argument("--key", required=True, help="Hex key used during hide")

    # --- INSPECT command ---
    inspect_parser = subparsers.add_parser("inspect", help="Analyse a carrier's capacity")
    inspect_parser.add_argument("carrier", help="Path to PNG, video, or WAV to inspect")

    args = parser.parse_args()

    if args.command == "hide":
        key = bytes.fromhex(args.key) if args.key else generate_key()

        # Auto-convert carrier to lossless format if needed
        carrier_path = args.carrier
        if not getattr(args, 'no_convert', False):
            ext_check = os.path.splitext(args.carrier)[1].lower()
            if ext_check not in AUDIO_EXTENSIONS:  # don't convert WAV
                carrier_path = prepare_carrier(args.carrier)

        ext = os.path.splitext(carrier_path)[1].lower()

        if ext in AUDIO_EXTENSIONS:
            # Audio pipeline
            print(f"\n📄 Reading {args.secret}...")
            with open(args.secret, "rb") as f:
                raw = f.read()
            print(f"   Read {len(raw):,} bytes")
            compressed = compress(raw)
            encrypted = encrypt(compressed, key)
            embed_audio(carrier_path, encrypted, args.output)

        elif ext in VIDEO_EXTENSIONS:
            # Video pipeline
            print(f"\n📄 Reading {args.secret}...")
            with open(args.secret, "rb") as f:
                raw = f.read()
            print(f"   Read {len(raw):,} bytes")
            compressed = compress(raw)
            encrypted = encrypt(compressed, key)
            hide_in_video(encrypted, carrier_path, args.output)

        else:
            # PNG pipeline
            hide(args.secret, carrier_path, args.output, key)

        print(f"\n🔑 Your key: {key.hex()}")
        print("⚠️  Save this key — you cannot recover your file without it.")

    elif args.command == "reveal":
        key = bytes.fromhex(args.key)
        ext = os.path.splitext(args.carrier)[1].lower()

        if ext in AUDIO_EXTENSIONS:
            # Audio pipeline
            encrypted = extract_audio(args.carrier)
            compressed = decrypt(encrypted, key)
            raw = decompress(compressed)
            with open(args.output, "wb") as f:
                f.write(raw)
            print(f"\n✅ DONE — file recovered to {args.output}")
            print(f"   Recovered {len(raw):,} bytes")

        elif ext in VIDEO_EXTENSIONS:
            # Video pipeline
            encrypted = reveal_from_video(args.carrier)
            compressed = decrypt(encrypted, key)
            raw = decompress(compressed)
            with open(args.output, "wb") as f:
                f.write(raw)
            print(f"\n✅ DONE — file recovered to {args.output}")
            print(f"   Recovered {len(raw):,} bytes")

        else:
            # PNG pipeline
            reveal(args.carrier, args.output, key)

    elif args.command == "inspect":
        ext = os.path.splitext(args.carrier)[1].lower()
        if ext in AUDIO_EXTENSIONS:
            from audio_carrier import get_audio_capacity
            get_audio_capacity(args.carrier)
        else:
            inspect(args.carrier)


if __name__ == "__main__":
    main()
