# GhostStore

**Universal Steganographic File Storage**

> Store anything, anywhere, invisibly.

GhostStore hides any file inside ordinary media — photos, videos, audio — using three layers of protection: **Zstandard compression → AES-256-GCM encryption → LSB steganographic embedding**.

The result is data that is invisible, encrypted, and indistinguishable from normal files.

---

## Download
[Download GhostStore for Windows →](https://github.com/JamesPaul777/ghoststore-personal/releases/latest)

## How it works

```
Secret file(s)
  ↓ Compress       (Zstandard)
  ↓ Chunk          (1MB fixed-size chunks)
  ↓ Encrypt        (AES-256-GCM per chunk)
  ↓ Embed          (LSB steganography into carrier)
  ↓ Save carriers  (output folder)
  ↓ Write manifest (manifest.json)
  ↓ Register       (local vault database)
```

To recover your files, you need the `manifest.json` and your encryption key. Without both, the data is unrecoverable by design.

---

## Two modes

### ⭐ Blend & Hide (primary)

Hide your files inside media **you already own** — holiday photos, home videos, audio recordings.

- Zero extra storage cost — the carrier already exists on your device
- Output looks identical to the original media file
- Only you can extract the hidden data with your key

### 📦 Portable Container

GhostStore generates a synthetic carrier automatically.

- Best for sharing hidden data with someone else
- Output is self-contained — carrier + hidden data together
- Note: output is larger than input — this is a sharing tool, not a storage saver

---

## Carrier types

| Carrier        | Method              | Storage ratio |
| -------------- | ------------------- | ------------- |
| PNG image      | LSB (1 bit/channel) | ~8:1          |
| FFV1 MKV video | LSB per frame       | ~2:1          |
| WAV audio      | LSB (1 bit/sample)  | ~4:1          |

Auto-conversion: JPEG → PNG, MP4 → FFV1 MKV, MP3 → WAV before embedding.

---

## Features

- Hide any file type — documents, images, archives, executables
- Multi-file support — hide multiple files in one operation, recovered as a bundle
- Smart carrier recommendation — suggests best carrier type based on payload size
- Encryption key popup — key shown immediately on hide, auto-copied to clipboard
- Key file auto-save — key saved as `.key` file alongside carriers
- Named key store — label and browse your keys inside the app
- Local vault — browsable history of all hidden files
- Manifest recovery — import `manifest.json` to rebuild vault if database is lost
- Carrier inspection — check capacity and metadata before hiding
- Desktop GUI — Windows `.exe`, no installation required
- CLI — command-line interface for scripting and automation
- REST API — integrate GhostStore into your own applications

---

## Installation

### Requirements

- Python 3.10+
- FFmpeg (for video carrier support)

### From source

```bash
git clone https://github.com/JamesPaul777/ghoststore.git
cd ghoststore
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
python src/gui.py
```

### Windows .exe

Download the latest release from the [Releases](https://github.com/JamesPaul777/ghoststore/releases) page. No installation required.

---

## CLI usage

```bash
# Hide a file
python src/cli.py hide secret.pdf --output ./carriers --carrier-type image

# Reveal
python src/cli.py reveal ./carriers/manifest.json --output ./revealed

# Inspect a carrier
python src/cli.py inspect carrier_0000.png
```

---

## Security model

| Layer         | Protection                                         |
| ------------- | -------------------------------------------------- |
| Steganography | Visual detection, file scanning, casual inspection |
| AES-256-GCM   | Brute force, known-plaintext attacks               |
| Chunking      | Single-chunk compromise exposes only that chunk    |

**Key security properties:**

- Key is never stored alongside data — you hold the key
- Per-chunk independent encryption — one chunk compromised does not reveal others
- Loss of key = permanent data loss by design (no backdoor, no recovery)
- Carrier files pass visual inspection — look like ordinary media

---

## Project structure

```
src/
  compress.py          Zstandard compress / decompress
  encrypt.py           AES-256-GCM per-chunk encrypt / decrypt
  embed.py             LSB embed into PNG
  extract.py           LSB extract from PNG
  chunker.py           Fixed-size 1MB chunking
  vault.py             Local SQLite vault database
  key_manager.py       Named key store
  storage.py           Embed chunks into carriers, write manifest
  pipeline.py          Full v2 pipeline
  carrier_generate.py  Synthetic carrier generation
  carrier_convert.py   Auto-convert JPEG/MP4/MP3 to lossless
  carrier_inspect.py   Carrier capacity analysis
  video_carrier.py     FFV1 MKV LSB embed / extract
  audio_carrier.py     WAV LSB embed / extract
  multi_carrier.py     Multi-carrier span utilities
  cli.py               Command-line interface
  api.py               REST API (Flask)
  gui.py               Desktop GUI

tests/
  test_v2.py           42 tests — core pipeline
```

---

## GhostStore Pro & Enterprise

GhostStore Personal is free and open source.

**GhostStore Pro** adds:

- SQLite carrier — store hidden data inside realistic database files at ~1:1 storage ratio
- Named key store with team vault
- REST API
- Cloud storage targets (S3, Google Drive, Azure)

**GhostStore Enterprise** adds:

- Content-defined chunking (CDC) for cross-file deduplication
- Up to 60% storage reduction on AI training datasets
- Zero-knowledge key management
- Full compliance audit log
- On-premise deployment

→ Contact: [github.com/JamesPaul777](https://github.com/JamesPaul777)

---

## Licence

GhostStore Personal is licensed under the [GNU General Public License v3.0](LICENSE).

Commercial use in closed-source products requires a separate commercial licence.
Contact via GitHub for enquiries.

---

_Built by James Paul — March 2026_
