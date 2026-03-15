import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import tempfile
import uuid
from flask import Flask, request, jsonify, send_file
from encrypt import generate_key, encrypt, decrypt
from compress import compress, decompress
from embed import embed
from extract import extract
from audio_carrier import embed_audio, extract_audio
from carrier_convert import prepare_carrier
from carrier_inspect import inspect_png
from audio_carrier import get_audio_capacity

app = Flask(__name__)

# Temp storage for session files
TEMP_DIR = tempfile.mkdtemp()


def allowed_carrier(filename: str) -> bool:
    allowed = {'.png', '.jpg', '.jpeg', '.wav', '.webp', '.bmp'}
    return os.path.splitext(filename)[1].lower() in allowed


def allowed_secret(filename: str) -> bool:
    blocked = {'.exe', '.bat', '.sh', '.cmd'}
    return os.path.splitext(filename)[1].lower() not in blocked


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "name": "GhostStore API",
        "version": "1.0.0",
        "description": "Universal Steganographic File Storage System",
        "endpoints": {
            "POST /hide": "Hide a file inside a carrier",
            "POST /reveal": "Reveal a hidden file from a carrier",
            "POST /inspect": "Analyse a carrier's capacity",
            "GET  /health": "Health check"
        }
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "GhostStore API"})


@app.route('/hide', methods=['POST'])
def hide_endpoint():
    """
    Hide a secret file inside a carrier.

    Multipart form data:
        secret   — the file to hide
        carrier  — the carrier file (PNG, JPEG, WAV)
        key      — (optional) hex AES-256 key. Omit to generate a new one.

    Returns: the output carrier file with hidden data + the key used
    """
    if 'secret' not in request.files or 'carrier' not in request.files:
        return jsonify({"error": "Both 'secret' and 'carrier' files are required"}), 400

    secret_file = request.files['secret']
    carrier_file = request.files['carrier']

    if not allowed_carrier(carrier_file.filename):
        return jsonify({"error": f"Unsupported carrier format"}), 400
    if not allowed_secret(secret_file.filename):
        return jsonify({"error": "Secret file type not allowed"}), 400

    # Get or generate key
    key_hex = request.form.get('key', None)
    if key_hex:
        try:
            key = bytes.fromhex(key_hex)
            if len(key) != 32:
                return jsonify({"error": "Key must be 32 bytes (64 hex characters)"}), 400
        except ValueError:
            return jsonify({"error": "Invalid key format"}), 400
    else:
        key = generate_key()

    # Save uploaded files to temp directory
    session_id = str(uuid.uuid4())
    secret_path = os.path.join(TEMP_DIR, f"{session_id}_secret{os.path.splitext(secret_file.filename)[1]}")
    carrier_path = os.path.join(TEMP_DIR, f"{session_id}_carrier{os.path.splitext(carrier_file.filename)[1]}")
    output_path = os.path.join(TEMP_DIR, f"{session_id}_output.png")

    secret_file.save(secret_path)
    carrier_file.save(carrier_path)

    try:
        # Read and process secret
        with open(secret_path, 'rb') as f:
            raw = f.read()

        compressed = compress(raw)
        encrypted = encrypt(compressed, key)

        # Auto-convert carrier and embed
        ext = os.path.splitext(carrier_path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.webp', '.bmp']:
            lossless_carrier = prepare_carrier(carrier_path)
            output_path = os.path.join(TEMP_DIR, f"{session_id}_output.png")
        elif ext == '.wav':
            lossless_carrier = carrier_path
            output_path = os.path.join(TEMP_DIR, f"{session_id}_output.wav")
        else:
            lossless_carrier = carrier_path

        if output_path.endswith('.wav'):
            embed_audio(lossless_carrier, encrypted, output_path)
        else:
            embed(lossless_carrier, encrypted, output_path)

        response = send_file(
            output_path,
            as_attachment=True,
            download_name=f"ghoststore_output{os.path.splitext(output_path)[1]}"
        )
        response.headers['X-GhostStore-Key'] = key.hex()
        response.headers['X-GhostStore-Secret-Size'] = str(len(raw))
        response.headers['X-GhostStore-Session'] = session_id
        return response

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500
    finally:
        for f in [secret_path, carrier_path]:
            if os.path.exists(f):
                os.remove(f)


@app.route('/reveal', methods=['POST'])
def reveal_endpoint():
    """
    Reveal a hidden file from a carrier.

    Multipart form data:
        carrier      — the carrier file containing hidden data
        key          — hex AES-256 key used during hide
        output_name  — (optional) filename for the recovered file

    Returns: the recovered secret file
    """
    if 'carrier' not in request.files:
        return jsonify({"error": "'carrier' file is required"}), 400
    if 'key' not in request.form:
        return jsonify({"error": "'key' is required"}), 400

    carrier_file = request.files['carrier']
    key_hex = request.form['key']
    output_name = request.form.get('output_name', 'recovered_file')

    try:
        key = bytes.fromhex(key_hex)
        if len(key) != 32:
            return jsonify({"error": "Key must be 32 bytes (64 hex chars)"}), 400
    except ValueError:
        return jsonify({"error": "Invalid key format"}), 400

    session_id = str(uuid.uuid4())
    carrier_ext = os.path.splitext(carrier_file.filename)[1].lower()
    carrier_path = os.path.join(TEMP_DIR, f"{session_id}_carrier{carrier_ext}")
    output_path = os.path.join(TEMP_DIR, f"{session_id}_{output_name}")

    carrier_file.save(carrier_path)

    try:
        if carrier_ext == '.wav':
            encrypted = extract_audio(carrier_path)
        else:
            encrypted = extract(carrier_path)

        compressed = decrypt(encrypted, key)
        raw = decompress(compressed)

        with open(output_path, 'wb') as f:
            f.write(raw)

        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_name
        )

    except Exception as e:
        return jsonify({"error": f"Reveal failed: {str(e)}"}), 400
    finally:
        if os.path.exists(carrier_path):
            os.remove(carrier_path)


@app.route('/inspect', methods=['POST'])
def inspect_endpoint():
    """
    Inspect a carrier file's embedding capacity.

    Multipart form data:
        carrier — the carrier file to inspect

    Returns: JSON with capacity information
    """
    if 'carrier' not in request.files:
        return jsonify({"error": "'carrier' file is required"}), 400

    carrier_file = request.files['carrier']
    session_id = str(uuid.uuid4())
    carrier_ext = os.path.splitext(carrier_file.filename)[1].lower()
    carrier_path = os.path.join(TEMP_DIR, f"{session_id}_carrier{carrier_ext}")
    carrier_file.save(carrier_path)

    try:
        if carrier_ext == '.wav':
            info = get_audio_capacity(carrier_path)
        else:
            info = inspect_png(carrier_path)
        return jsonify(info)
    finally:
        if os.path.exists(carrier_path):
            os.remove(carrier_path)


if __name__ == '__main__':
    print("\n👻 GhostStore API starting...")
    print("   http://localhost:5000")
    print("   Endpoints: / | /health | /hide | /reveal | /inspect\n")
    app.run(debug=True, port=5000)
