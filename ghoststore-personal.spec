# ghoststore-personal.spec — PyInstaller build spec
# GhostStore Personal — open source build
#
# Build command (run from project root with venv active):
#   pyinstaller ghoststore-personal.spec
#
# Output: dist\ghoststore.exe

import sys
from pathlib import Path

block_cipher = None

HIDDEN = [
    'compress',
    'encrypt',
    'embed',
    'extract',
    'chunker',
    'vault',
    'key_manager',
    'storage',
    'pipeline',
    'carrier_generate',
    'carrier_convert',
    'carrier_inspect',
    'video_carrier',
    'audio_carrier',
    'multi_carrier',
    # third-party
    'zstandard',
    'cryptography',
    'cryptography.hazmat.primitives.ciphers.aead',
    'PIL',
    'PIL.Image',
    'numpy',
    'numpy.core._multiarray_umath',
    'sqlite3',
]

a = Analysis(
    ['src\\gui.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'pandas', 'IPython',
        'tkinter.test', 'unittest', 'email', 'html',
        'http', 'xmlrpc', 'pydoc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ghoststore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
