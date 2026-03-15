"""
gui.py  —  GhostStore Desktop GUI
Session 7: Mode 1/2 toggle, multi-file selection, carrier type picker,
           key copy button, capacity warning, folder output on reveal.

Layout
------
  Tab 1 — HIDE
    ┌─ Mode ─────────────────────────────────────────────────────────┐
    │  ( ) Generate & Hide    ( ) Blend & Hide                       │
    └────────────────────────────────────────────────────────────────┘
    ┌─ Secret Files ─────────────────────────────────────────────────┐
    │  [file1.pdf, file2.docx ...]           [Browse]  [Clear]       │
    └────────────────────────────────────────────────────────────────┘
    ┌─ Carrier ──────────────────────────────────────────────────────┐
    │  Mode 1: ( ) Image  ( ) Video  ( ) Audio                       │
    │  Mode 2: [carrier_path...]                        [Browse]     │
    └────────────────────────────────────────────────────────────────┘
    ┌─ Output ───────────────────────────────────────────────────────┐
    │  [output_path...]                                 [Browse]     │
    └────────────────────────────────────────────────────────────────┘
                                           [   HIDE   ]

    ┌─ Result ───────────────────────────────────────────────────────┐
    │  Key: 3a4f...                             [Copy Key]           │
    └────────────────────────────────────────────────────────────────┘

  Tab 2 — REVEAL
    ┌─ Carrier File ─────────────────────────────────────────────────┐
    │  [carrier_path...]                                [Browse]     │
    └────────────────────────────────────────────────────────────────┘
    ┌─ Output Folder ────────────────────────────────────────────────┐
    │  [output_dir...]                                  [Browse]     │
    └────────────────────────────────────────────────────────────────┘
    ┌─ Encryption Key ───────────────────────────────────────────────┐
    │  [hex key...]                                                  │
    └────────────────────────────────────────────────────────────────┘
                                           [  REVEAL  ]

    ┌─ Result ───────────────────────────────────────────────────────┐
    │  Revealed: file1.pdf, file2.docx                               │
    └────────────────────────────────────────────────────────────────┘

  Tab 3 — INSPECT (unchanged from Session 6)
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pipeline import hide_v2, reveal_v2
from vault import list_all, delete, rebuild_from_manifest
from key_manager import save_key, list_keys, get_key_hex, delete_key, rename_key
from carrier_inspect import inspect


# ─────────────────────────────────────────────────────────────────────────────
# Palette & sizing constants
# ─────────────────────────────────────────────────────────────────────────────
BG       = '#1a1a2e'
PANEL    = '#16213e'
ACCENT   = '#0f3460'
HIGHLIGHT= '#e94560'
FG       = '#eaeaea'
FG_DIM   = '#8888aa'
FONT     = ('Segoe UI', 10)
FONT_B   = ('Segoe UI', 10, 'bold')
FONT_BIG = ('Segoe UI', 13, 'bold')
MONO     = ('Consolas', 9)
PAD      = 10
IPAD     = 6

# Carrier type → default output extension
CARRIER_EXT = {'image': '.png', 'video': '.mkv', 'audio': '.wav'}

# Carrier type → file dialog filter
CARRIER_FILTER = {
    'image': [('PNG image', '*.png'), ('Any file', '*.*')],
    'video': [('MKV video', '*.mkv'), ('Any file', '*.*')],
    'audio': [('WAV audio', '*.wav'), ('Any file', '*.*')],
}

ALL_MEDIA = [
    ('Media files', '*.png *.jpg *.jpeg *.webp *.bmp *.mp4 *.mov *.avi *.mkv *.wmv *.wav *.db'),
    ('Any file',    '*.*'),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helper widgets
# ─────────────────────────────────────────────────────────────────────────────

def _label(parent, text, big=False, dim=False, **kw):
    colour = FG_DIM if dim else FG
    font   = FONT_BIG if big else FONT
    return tk.Label(parent, text=text, bg=PANEL, fg=colour, font=font, **kw)


def _entry(parent, textvariable=None, width=50, readonly=False):
    state = 'readonly' if readonly else 'normal'
    e = tk.Entry(
        parent, textvariable=textvariable, width=width,
        bg=ACCENT, fg=FG, insertbackground=FG,
        relief='flat', font=MONO, state=state,
    )
    return e


def _btn(parent, text, command, danger=False):
    colour = HIGHLIGHT if danger else '#3a7bd5'
    return tk.Button(
        parent, text=text, command=command,
        bg=colour, fg='white', activebackground=colour,
        relief='flat', font=FONT_B, padx=12, pady=5, cursor='hand2',
    )


def _section(parent, title):
    """Labelled panel frame."""
    outer = tk.Frame(parent, bg=BG, pady=4)
    outer.pack(fill='x', padx=PAD)
    lbl = tk.Label(outer, text=f'  {title}  ', bg=BG, fg=FG_DIM, font=FONT)
    lbl.pack(anchor='w')
    inner = tk.Frame(outer, bg=PANEL, padx=PAD, pady=PAD)
    inner.pack(fill='x')
    return inner


def _row(parent, **kw):
    f = tk.Frame(parent, bg=PANEL, **kw)
    f.pack(fill='x', pady=2)
    return f


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_size(n):
    """Human-readable file size."""
    if n < 1024:
        return f'{n} B'
    elif n < 1024 ** 2:
        return f'{n / 1024:.1f} KB'
    elif n < 1024 ** 3:
        return f'{n / 1024**2:.1f} MB'
    else:
        return f'{n / 1024**3:.2f} GB'


class GhostStoreApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('GhostStore')
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(640, 520)

        # ── state ────────────────────────────────────────────────────────────
        self._secret_paths   = []           # list of chosen secret file paths
        self._hide_mode      = tk.StringVar(value='blend')  # 'generate' | 'blend'
        self._carrier_type   = tk.StringVar(value='image')     # 'image' | 'video' | 'audio'
        self._carrier_path   = tk.StringVar()
        self._hide_output    = tk.StringVar()
        self._hide_label       = tk.StringVar()  # friendly vault name
        self._sqlite_template  = tk.StringVar(value='cache')
        self._chunking_mode    = tk.StringVar(value='fixed')
        self._use_dedup        = tk.BooleanVar(value=False)
        self._auto_push_var          = tk.BooleanVar(value=False)
        self._hide_cloud_provider_var = tk.StringVar(value='s3')
        self._cloud_entries           = {}
        self._last_key       = tk.StringVar()

        self._reveal_manifest = tk.StringVar()
        self._reveal_outdir   = tk.StringVar()

        self._inspect_path   = tk.StringVar()

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=0, pady=0)

        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            'TNotebook',        background=BG, borderwidth=0)
        style.configure(
            'TNotebook.Tab',    background=ACCENT, foreground=FG,
                                font=FONT_B, padding=[16, 6])
        style.map(
            'TNotebook.Tab',
            background=[('selected', HIGHLIGHT)],
            foreground=[('selected', 'white')],
        )

        self._tab_hide    = tk.Frame(nb, bg=BG)
        self._tab_reveal  = tk.Frame(nb, bg=BG)
        self._tab_inspect = tk.Frame(nb, bg=BG)
        self._tab_vault   = tk.Frame(nb, bg=BG)
        self._tab_keys    = tk.Frame(nb, bg=BG)
        self._tab_settings = tk.Frame(nb, bg=BG)
        self._tab_enterprise = tk.Frame(nb, bg=BG)

        nb.add(self._tab_hide,    text='  HIDE  ')
        nb.add(self._tab_reveal,  text=' REVEAL ')
        nb.add(self._tab_inspect, text=' INSPECT')
        nb.add(self._tab_vault,   text='  VAULT ')
        nb.add(self._tab_keys,    text='  KEYS  ')
        nb.add(self._tab_settings, text=' SETTINGS')
        nb.add(self._tab_enterprise, text=' ENTERPRISE')

        self._build_hide_tab()
        self._build_reveal_tab()
        self._build_inspect_tab()
        self._build_vault_tab()
        self._build_keys_tab()
        self._build_settings_tab()
        self._build_enterprise_tab()

    # ── HIDE tab ──────────────────────────────────────────────────────────────

    def _build_hide_tab(self):
        outer = self._tab_hide

        # Scrollable canvas wrapper
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        parent = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=parent, anchor='nw')

        def _on_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', _on_resize)

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox('all'))
        parent.bind('<Configure>', _on_frame_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _on_mousewheel)

        # Title
        tk.Label(parent, text='GhostStore — Hide Your Files', bg=BG, fg=HIGHLIGHT,
                 font=FONT_BIG).pack(pady=(14, 4))

        # ── Mode selector ─────────────────────────────────────────────────
        sec = _section(parent, 'Mode')

        # Hero — Blend & Hide
        hero_row = _row(sec)
        tk.Radiobutton(
            hero_row,
            text='⭐  Blend & Hide  —  hide inside YOUR existing media  (zero extra storage cost)',
            variable=self._hide_mode, value='blend',
            command=self._on_mode_change,
            bg=PANEL, fg='#44cc88', selectcolor=ACCENT, activebackground=PANEL,
            font=FONT_B, indicatoron=True,
        ).pack(side='left')

        # Secondary — Portable Container
        sec_row = _row(sec)
        tk.Radiobutton(
            sec_row,
            text='📦  Portable Container  —  GhostStore generates a carrier  (output will be larger than input)',
            variable=self._hide_mode, value='generate',
            command=self._on_mode_change,
            bg=PANEL, fg=FG_DIM, selectcolor=ACCENT, activebackground=PANEL,
            font=FONT, indicatoron=True,
        ).pack(side='left')

        # Savings calculator label
        self._savings_lbl = tk.Label(
            sec, text='', bg=PANEL, fg='#44cc88', font=FONT)
        self._savings_lbl.pack(anchor='w', pady=(4, 0))

        # ── Secret files ──────────────────────────────────────────────────
        sec2 = _section(parent, 'Secret Files  (select one or more)')
        f2   = _row(sec2)

        self._secret_listbox = tk.Listbox(
            sec2, bg=ACCENT, fg=FG, font=MONO, height=4,
            selectmode='extended', relief='flat',
        )
        self._secret_listbox.pack(fill='x', pady=(4, 0))

        btn_row = _row(sec2)
        _btn(btn_row, 'Add Files…',  self._browse_secrets).pack(side='left', padx=(0, 6))
        _btn(btn_row, 'Clear',       self._clear_secrets,  danger=True).pack(side='left')
        self._secret_count_lbl = tk.Label(
            btn_row, text='', bg=PANEL, fg=FG_DIM, font=FONT)
        self._secret_count_lbl.pack(side='left', padx=12)

        # ── Carrier ───────────────────────────────────────────────────────
        self._carrier_sec = _section(parent, 'Carrier  (your existing media becomes the hiding spot)')

        # Mode 1 — carrier type radio buttons
        self._ctype_frame = tk.Frame(self._carrier_sec, bg=PANEL)
        self._ctype_frame.pack(fill='x')
        tk.Label(self._ctype_frame, text='Generate carrier type:', bg=PANEL, fg=FG,
                 font=FONT).pack(side='left', padx=(0, 12))
        for val, label in [('image',  '🖼 Image (PNG)'),
                            ('video',  '🎬 Video (MKV)'),
                            ('audio',  '🔊 Audio (WAV)'),
                            ('sqlite', '🗄 SQLite DB')]:
            tk.Radiobutton(
                self._ctype_frame, text=label,
                variable=self._carrier_type, value=val,
                command=self._on_carrier_type_change,
                bg=PANEL, fg=FG, selectcolor=ACCENT, activebackground=PANEL,
                font=FONT,
            ).pack(side='left', padx=8)

        # SQLite template picker — only visible when SQLite carrier selected
        self._sqlite_frame = tk.Frame(self._carrier_sec, bg=PANEL)
        tk.Label(self._sqlite_frame, text='DB template:', bg=PANEL, fg=FG,
                 font=FONT).pack(side='left', padx=(0, 12))
        for val, label in [('cache',     '📦 App Cache'),
                            ('analytics', '📊 Analytics'),
                            ('browser',   '🌐 Browser Cache')]:
            tk.Radiobutton(
                self._sqlite_frame, text=label,
                variable=self._sqlite_template, value=val,
                bg=PANEL, fg=FG_DIM, selectcolor=ACCENT, activebackground=PANEL,
                font=FONT,
            ).pack(side='left', padx=6)

        # Recommendation label — auto-suggests best carrier type
        self._recommend_lbl = tk.Label(
            self._carrier_sec, text='', bg=PANEL, fg='#44cc88', font=FONT)
        self._recommend_lbl.pack(anchor='w', pady=(4, 0))

        # Carrier size estimate label
        self._carrier_size_lbl = tk.Label(
            self._carrier_sec, text='', bg=PANEL, fg=FG_DIM, font=FONT)
        self._carrier_size_lbl.pack(anchor='w')

        # Mode 2 — carrier file picker
        self._cfile_frame = tk.Frame(self._carrier_sec, bg=PANEL)
        tk.Label(self._cfile_frame, text='Carrier file:', bg=PANEL, fg=FG,
                 font=FONT).pack(side='left', padx=(0, 8))
        _entry(self._cfile_frame, textvariable=self._carrier_path,
               width=44).pack(side='left')
        _btn(self._cfile_frame, 'Browse…',
             self._browse_carrier).pack(side='left', padx=(6, 0))

        self._on_mode_change()  # set initial visibility

        # ── Output path ───────────────────────────────────────────────────
        sec3 = _section(parent, 'Output')
        f3   = _row(sec3)
        tk.Label(f3, text='Save to folder:', bg=PANEL, fg=FG, font=FONT).pack(
            side='left', padx=(0, 8))
        _entry(f3, textvariable=self._hide_output, width=40).pack(side='left')
        _btn(f3, 'Browse…', self._browse_hide_output).pack(side='left', padx=(6, 0))

        f3b = _row(sec3)
        tk.Label(f3b, text='Name (for Vault):', bg=PANEL, fg=FG, font=FONT).pack(
            side='left', padx=(0, 8))
        _entry(f3b, textvariable=self._hide_label, width=40).pack(side='left')
        tk.Label(f3b,
            text='  e.g. "Tax docs 2025" — shown in Vault instead of filename',
            bg=PANEL, fg=FG_DIM, font=FONT).pack(side='left')

        # ── Chunking mode ──────────────────────────────────────────────────
        sec_chunk = _section(parent, 'Chunking Mode')
        chunk_row = _row(sec_chunk)
        tk.Radiobutton(
            chunk_row, text='Fixed size  (Personal / Pro — fast, predictable)',
            variable=self._chunking_mode, value='fixed',
            bg=PANEL, fg=FG, selectcolor=ACCENT, activebackground=PANEL, font=FONT,
        ).pack(side='left', padx=(0, 24))
        tk.Radiobutton(
            chunk_row, text='⚡ CDC  (Enterprise — enables deduplication)',
            variable=self._chunking_mode, value='cdc',
            bg=PANEL, fg='#44cc88', selectcolor=ACCENT, activebackground=PANEL, font=FONT_B,
        ).pack(side='left')

        dedup_row = _row(sec_chunk)
        tk.Checkbutton(
            dedup_row,
            text='♻️  Enable deduplication  (CDC mode only — reuses carriers for identical chunks)',
            variable=self._use_dedup,
            bg=PANEL, fg=FG_DIM, selectcolor=ACCENT, activebackground=PANEL, font=FONT,
        ).pack(side='left')

        # ── Cloud Push ────────────────────────────────────────────────────
        sec_cloud = _section(parent, 'Cloud Push')
        cloud_row = _row(sec_cloud)
        tk.Checkbutton(
            cloud_row,
            text='☁  Auto-push carriers to cloud after hide',
            variable=self._auto_push_var,
            command=self._on_auto_push_toggle,
            bg=PANEL, fg=FG, selectcolor=ACCENT, activebackground=PANEL, font=FONT,
        ).pack(side='left')

        cloud_row2 = _row(sec_cloud)
        tk.Label(cloud_row2, text='Provider:', bg=PANEL, fg=FG, font=FONT).pack(side='left', padx=(0, 8))
        self._hide_provider_cb = ttk.Combobox(
            cloud_row2,
            textvariable=self._hide_cloud_provider_var,
            values=['s3', 'gcs', 'azure'],
            state='disabled',
            width=12,
        )
        self._hide_provider_cb.pack(side='left')

        # ── Action button ─────────────────────────────────────────────────
        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.pack(pady=10)
        _btn(btn_frame, '   HIDE FILES   ', self._run_hide).pack()

        # ── Progress / status ─────────────────────────────────────────────
        self._hide_status = tk.Label(
            parent, text='', bg=BG, fg=FG_DIM, font=FONT, wraplength=580)
        self._hide_status.pack()

        # ── Result / key ──────────────────────────────────────────────────
        self._key_sec = _section(parent, 'Encryption Key  (save this — you cannot recover your files without it)')
        key_row = _row(self._key_sec)
        self._key_display = _entry(key_row, textvariable=self._last_key,
                                   width=56, readonly=True)
        self._key_display.pack(side='left')
        _btn(key_row, '📋 Copy', self._copy_key).pack(side='left', padx=(8, 0))

    # ── REVEAL tab ────────────────────────────────────────────────────────────

    def _build_reveal_tab(self):
        parent = self._tab_reveal

        tk.Label(parent, text='GhostStore — Reveal', bg=BG, fg=HIGHLIGHT,
                 font=FONT_BIG).pack(pady=(14, 4))

        tk.Label(parent,
            text='Select the manifest.json from your carrier folder. '
                 'The key is stored inside it — no need to enter it manually.',
            bg=BG, fg=FG_DIM, font=FONT, wraplength=580).pack(pady=(0, 6))

        # Manifest file picker
        sec = _section(parent, 'Manifest File  (manifest.json inside your carrier folder)')
        f   = _row(sec)
        tk.Label(f, text='manifest.json:', bg=PANEL, fg=FG, font=FONT).pack(
            side='left', padx=(0, 8))
        _entry(f, textvariable=self._reveal_manifest, width=44).pack(side='left')
        _btn(f, 'Browse…', self._browse_reveal_manifest).pack(
            side='left', padx=(6, 0))

        # Output folder
        sec2 = _section(parent, 'Output Folder  (where to save revealed files)')
        f2   = _row(sec2)
        tk.Label(f2, text='Save to:', bg=PANEL, fg=FG, font=FONT).pack(
            side='left', padx=(0, 8))
        _entry(f2, textvariable=self._reveal_outdir, width=44).pack(side='left')
        _btn(f2, 'Browse…', self._browse_reveal_outdir).pack(
            side='left', padx=(6, 0))

        # Cloud pull
        pull_frame = tk.Frame(parent, bg=BG)
        pull_frame.pack(fill='x', padx=PAD, pady=(0, 4))
        _btn(pull_frame, '☁ Pull from Cloud', self._pull_carriers_from_cloud).pack(side='left')
        tk.Label(pull_frame, text='  Download cloud carriers before revealing',
                 bg=BG, fg=FG_DIM, font=FONT).pack(side='left')

        # Action
        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.pack(pady=10)
        _btn(btn_frame, '  REVEAL FILES  ', self._run_reveal).pack()

        # Status
        self._reveal_status = tk.Label(
            parent, text='', bg=BG, fg=FG_DIM, font=FONT, wraplength=580)
        self._reveal_status.pack()

        # Result list
        self._reveal_result_sec = _section(parent, 'Revealed Files')
        self._reveal_listbox = tk.Listbox(
            self._reveal_result_sec, bg=ACCENT, fg=FG, font=MONO,
            height=6, relief='flat',
        )
        self._reveal_listbox.pack(fill='x')
        _btn(self._reveal_result_sec, '📂 Open Folder',
             self._open_reveal_folder).pack(anchor='w', pady=(6, 0))

    # ── INSPECT tab ───────────────────────────────────────────────────────────

    def _build_inspect_tab(self):
        parent = self._tab_inspect

        tk.Label(parent, text='GhostStore — Inspect Carrier', bg=BG,
                 fg=HIGHLIGHT, font=FONT_BIG).pack(pady=(14, 4))

        sec = _section(parent, 'Carrier File')
        f   = _row(sec)
        tk.Label(f, text='File:', bg=PANEL, fg=FG, font=FONT).pack(
            side='left', padx=(0, 8))
        _entry(f, textvariable=self._inspect_path, width=48).pack(side='left')
        _btn(f, 'Browse…', self._browse_inspect).pack(side='left', padx=(6, 0))

        btn_frame = tk.Frame(parent, bg=BG)
        btn_frame.pack(pady=10)
        _btn(btn_frame, '  INSPECT  ', self._run_inspect).pack()

        self._inspect_result = tk.Text(
            parent, bg=PANEL, fg=FG, font=MONO,
            height=12, relief='flat', state='disabled',
        )
        self._inspect_result.pack(fill='both', expand=True,
                                  padx=PAD, pady=(0, PAD))

    # ── Mode toggle ───────────────────────────────────────────────────────────

    def _on_mode_change(self, *_):
        mode = self._hide_mode.get()
        if mode == 'generate':
            self._cfile_frame.pack_forget()
            self._ctype_frame.pack(fill='x')
        else:
            self._ctype_frame.pack_forget()
            self._cfile_frame.pack(fill='x')

    # ── Browsing helpers ──────────────────────────────────────────────────────

    def _update_savings_calculator(self):
        """Show savings message for Mode 2 — zero extra storage cost."""
        if self._hide_mode.get() != 'blend':
            return
        total = sum(os.path.getsize(p) for p in self._secret_paths if os.path.exists(p))
        carrier_raw = self._carrier_path.get().strip()
        carrier = carrier_raw.split('  (')[0].strip() if '  (' in carrier_raw else carrier_raw

        if total == 0:
            self._savings_lbl.config(
                text='⭐ Blend & Hide: add your secret files to see your storage saving.',
                fg='#44cc88')
            return

        if carrier and os.path.exists(carrier):
            carrier_size = os.path.getsize(carrier)
            self._savings_lbl.config(
                text=f'✅ You save {_fmt_size(total)} — {_fmt_size(total)} of secret data '
                     f'hidden inside your existing {_fmt_size(carrier_size)} carrier. '
                     f'Zero extra storage cost.',
                fg='#44cc88')
        else:
            self._savings_lbl.config(
                text=f'✅ Once you select your carrier, {_fmt_size(total)} of secret data '
                     f'will be hidden at zero extra storage cost.',
                fg='#44cc88')

    def _on_auto_push_toggle(self):
        state = 'readonly' if self._auto_push_var.get() else 'disabled'
        self._hide_provider_cb.configure(state=state)

    def _on_carrier_type_change(self):
        if self._carrier_type.get() == 'sqlite':
            self._sqlite_frame.pack(fill='x', pady=(6, 0))
        else:
            self._sqlite_frame.pack_forget()

        """Recalculate size estimate when user manually picks a carrier type."""
        total = sum(os.path.getsize(p) for p in self._secret_paths if os.path.exists(p))
        if total > 0:
            self._update_carrier_size_estimate(total)

    def _update_carrier_size_estimate(self, payload_bytes):
        """Show estimated output carrier file size."""
        ctype = self._carrier_type.get()
        if ctype == 'image':
            est = payload_bytes * 10
            note = f'⚠️  Estimated carrier size: ~{_fmt_size(est)} (PNG)'
            colour = '#ffaa00' if est > 5 * 1024 * 1024 else FG_DIM
        elif ctype == 'audio':
            # 1 bit per sample, 16-bit mono 44100 Hz
            samples = payload_bytes * 8
            seconds = samples / 44100
            est = samples * 2  # 16-bit = 2 bytes/sample
            note = f'📁 Estimated carrier size: ~{_fmt_size(est)} WAV ({seconds:.0f}s)'
            colour = FG_DIM
        else:  # video
            est = max(payload_bytes * 2, 1024 * 1024)
            note = f'📁 Estimated carrier size: ~{_fmt_size(est)} MKV'
            colour = FG_DIM
        self._carrier_size_lbl.config(text=note, fg=colour)

    def _browse_secrets(self):
        paths = filedialog.askopenfilenames(title='Select secret file(s)')
        if paths:
            for p in paths:
                if p not in self._secret_paths:
                    self._secret_paths.append(p)
            self._refresh_secret_list()

    def _clear_secrets(self):
        self._secret_paths.clear()
        self._refresh_secret_list()

    def _refresh_secret_list(self):
        self._secret_listbox.delete(0, 'end')
        total = 0
        for p in self._secret_paths:
            size = os.path.getsize(p) if os.path.exists(p) else 0
            total += size
            size_str = _fmt_size(size)
            self._secret_listbox.insert('end', f'{os.path.basename(p)}  ({size_str})')
        n = len(self._secret_paths)
        total_str = _fmt_size(total)
        self._secret_count_lbl.config(
            text=f'{n} file{"s" if n != 1 else ""} — {total_str} total' if n else '')
        self._update_recommendation()

    def _update_recommendation(self):
        """Auto-suggest best carrier type based on total payload size."""
        if not self._secret_paths:
            self._recommend_lbl.config(text='')
            return

        total = sum(os.path.getsize(p) for p in self._secret_paths if os.path.exists(p))
        total_kb = total / 1024
        total_mb = total_kb / 1024

        if total < 100 * 1024:          # < 100 KB → Image fine
            rec = 'image'
            tip = f'💡 {total_kb:.0f} KB — Image carrier recommended'
        elif total < 1 * 1024 * 1024:   # 100 KB – 1 MB → Audio
            rec = 'audio'
            tip = f'💡 {total_kb:.0f} KB — Audio carrier recommended'
        else:                            # > 1 MB → Video
            rec = 'video'
            tip = f'💡 {total_mb:.1f} MB — Video carrier recommended (image would be {total_mb * 10:.0f}+ MB)'

        self._carrier_type.set(rec)
        self._recommend_lbl.config(text=tip)
        self._update_carrier_size_estimate(total)
        self._update_savings_calculator()

    def _browse_carrier(self):
        p = filedialog.askopenfilename(title='Select carrier file',
                                       filetypes=ALL_MEDIA)
        if p:
            size_str = _fmt_size(os.path.getsize(p))
            self._carrier_path.set(f'{p}  ({size_str})')
            self._update_savings_calculator()

    def _browse_hide_output(self):
        d = filedialog.askdirectory(title='Select output folder for carriers')
        if d:
            self._hide_output.set(d)

    def _browse_reveal_manifest(self):
        p = filedialog.askopenfilename(
            title='Select manifest.json',
            filetypes=[('GhostStore manifest', 'manifest.json'),
                       ('JSON files', '*.json'),
                       ('Any file', '*.*')])
        if p:
            self._reveal_manifest.set(p)

    def _browse_reveal_outdir(self):
        d = filedialog.askdirectory(title='Select output folder')
        if d:
            self._reveal_outdir.set(d)

    def _browse_inspect(self):
        p = filedialog.askopenfilename(title='Select carrier file',
                                       filetypes=ALL_MEDIA)
        if p:
            self._inspect_path.set(p)

    # ── Capacity check ────────────────────────────────────────────────────────

    def _check_capacity(self, carrier_path, payload_bytes):
        """
        Returns (ok: bool, capacity_bytes: int).
        Only meaningful for Mode 2 (user-supplied carrier).
        """
        try:
            info = inspect(carrier_path)
            cap  = info.get('capacity_bytes', 0)
            return cap >= payload_bytes, cap
        except Exception:
            return True, 0   # can't determine — let embed() raise if needed

    # ── HIDE action ───────────────────────────────────────────────────────────

    def _run_hide(self):
        if not self._secret_paths:
            messagebox.showwarning('GhostStore', 'Please select at least one secret file.')
            return

        output = self._hide_output.get().strip()
        if not output:
            messagebox.showwarning('GhostStore', 'Please choose an output file path.')
            return

        mode = self._hide_mode.get()

        if mode == 'blend':
            # Strip display size annotation e.g. "file.mp4  (7.50 GB)"
            raw = self._carrier_path.get().strip()
            carrier = raw.split('  (')[0].strip() if '  (' in raw else raw
            if not carrier:
                messagebox.showwarning('GhostStore',
                                       'Please select a carrier file (Blend & Hide mode).')
                return

            # Capacity warning
            total_secret = sum(os.path.getsize(p) for p in self._secret_paths)
            ok, cap = self._check_capacity(carrier, total_secret)
            if not ok:
                answer = messagebox.askyesno(
                    'Capacity Warning',
                    f'The carrier may be too small.\n\n'
                    f'Secret data: {total_secret:,} bytes\n'
                    f'Carrier capacity: {cap:,} bytes\n\n'
                    f'Continue anyway?',
                )
                if not answer:
                    return
        else:
            carrier = None

        self._hide_status.config(text='⏳ Working…', fg=FG_DIM)
        self.update_idletasks()

        def worker():
            try:
                if mode == 'blend' and carrier:
                    # Mode 2: detect carrier type from actual file extension
                    ext = os.path.splitext(carrier)[1].lower()
                    _VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.wmv', '.mkv', '.m4v'}
                    _AUDIO_EXTS = {'.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a'}
                    if ext in _VIDEO_EXTS:
                        ctype = 'video'
                    elif ext in _AUDIO_EXTS:
                        ctype = 'audio'
                    else:
                        ctype = 'image'
                else:
                    # Mode 1: use the radio button selection
                    ctype = self._carrier_type.get()

                # Use hide_v2 — chunks, stores carriers, registers in vault
                manifest = hide_v2(
                    secret_paths=self._secret_paths,
                    output_dir=output,
                    carrier_type=ctype,
                    user_carriers=[carrier] if mode == 'blend' and carrier else None,
                    notes=self._hide_label.get().strip(),
                    sqlite_template=self._sqlite_template.get(),
                    chunking_mode=self._chunking_mode.get(),
                    use_dedup=self._use_dedup.get(),
                )
                self.after(0, self._on_hide_success, manifest['key_hex'])
                self.after(0, self._vault_refresh)
            except Exception as exc:
                self.after(0, self._on_hide_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_hide_success(self, key_hex):
        label = self._hide_label.get().strip()
        self._last_key.set(key_hex)
        self._hide_label.set('')   # clear for next operation
        output = self._hide_output.get()
        self._hide_status.config(
            text=f'✅ Done! Output: {output}', fg='#44cc88')

        # Auto-save key file next to output
        try:
            key_file = output + '.key'
            with open(key_file, 'w') as f:
                f.write(key_hex)
        except Exception:
            key_file = None

        # Auto-save key to key manager using vault label as name
        try:
            key_name = label if label else (
                os.path.basename(self._secret_paths[0]) if self._secret_paths else 'Unnamed key')
            save_key(key_name, key_hex)
            self.after(0, self._keys_refresh)
        except Exception:
            pass  # key manager save failure is non-fatal

        # Show key popup
        msg = f'Your encryption key:\n\n{key_hex}\n\n'
        msg += f'✅ Key saved to:\n{key_file}\n\n' if key_file else ''
        msg += '✅ Key also saved in the KEYS tab.\n\n'
        msg += 'KEEP THIS SAFE — without it your files cannot be recovered.'

        self.clipboard_clear()
        self.clipboard_append(key_hex)

        messagebox.showinfo('🔑 Encryption Key — Save This!', msg)

    def _on_hide_error(self, msg):
        self._hide_status.config(text=f'❌ Error: {msg}', fg=HIGHLIGHT)
        messagebox.showerror('GhostStore — Hide failed', msg)

    # ── Copy key ──────────────────────────────────────────────────────────────

    def _copy_key(self):
        key = self._last_key.get()
        if not key:
            messagebox.showinfo('GhostStore', 'No key yet. Run HIDE first.')
            return
        self.clipboard_clear()
        self.clipboard_append(key)
        messagebox.showinfo('GhostStore', 'Key copied to clipboard.\n\nStore it somewhere safe!')

    # ── REVEAL action ─────────────────────────────────────────────────────────

    def _run_reveal(self):
        manifest = self._reveal_manifest.get().strip()
        outdir   = self._reveal_outdir.get().strip()

        if not manifest:
            messagebox.showwarning('GhostStore', 'Please select a manifest.json file.')
            return
        if not os.path.isfile(manifest):
            messagebox.showwarning('GhostStore', 'manifest.json not found at that path.')
            return
        if not outdir:
            messagebox.showwarning('GhostStore', 'Please choose an output folder.')
            return

        self._reveal_status.config(text='⏳ Working…', fg=FG_DIM)
        self._reveal_listbox.delete(0, 'end')
        self.update_idletasks()

        def worker():
            try:
                paths = reveal_v2(manifest, outdir)
                self.after(0, self._on_reveal_success, paths)
            except Exception as exc:
                self.after(0, self._on_reveal_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _pull_carriers_from_cloud(self):
        manifest_path = self._reveal_manifest.get().strip()
        if not manifest_path:
            messagebox.showwarning('GhostStore', 'Browse to a manifest.json first.')
            return

        win = tk.Toplevel(self)
        win.title('Pull from Cloud')
        win.resizable(False, False)
        win.configure(bg=BG)
        tk.Label(win, text='Cloud provider:', bg=BG, fg=FG, font=FONT).grid(
            row=0, column=0, padx=10, pady=10, sticky='w')
        pvar = tk.StringVar(value='s3')
        ttk.Combobox(win, textvariable=pvar, values=['s3', 'gcs', 'azure'],
                     state='readonly', width=12).grid(row=0, column=1, padx=6)

        def _do_pull():
            win.destroy()
            provider_name = pvar.get()
            self._reveal_status.config(text=f'☁ Pulling from {provider_name}…', fg=FG_DIM)
            self.update_idletasks()

            def worker():
                try:
                    import json as _json
                    import tempfile
                    from cloud_storage import get_provider
                    with open(manifest_path, 'r') as f:
                        manifest = _json.load(f)
                    provider = get_provider(provider_name)
                    dest_dir = tempfile.mkdtemp(prefix='gs_cloud_')
                    updated = provider.pull_manifest(
                        manifest,
                        dest_dir=dest_dir,
                        progress_cb=lambda done, total: self.after(
                            0, lambda d=done, t=total: self._reveal_status.config(
                                text=f'☁ Downloading {d}/{t}…', fg=FG_DIM)),
                    )
                    tmp = tempfile.NamedTemporaryFile(
                        suffix='.json', dir=dest_dir, delete=False, mode='w')
                    _json.dump(updated, tmp)
                    tmp.close()
                    self.after(0, lambda: self._reveal_manifest.set(tmp.name))
                    _audit('pull', detail=f'{len(manifest["chunks"])} carrier(s) from {provider_name}', status='ok')
                    self.after(0, lambda: self._reveal_status.config(
                        text=f'✅ Pulled {len(manifest["chunks"])} carrier(s). Ready to reveal.',
                        fg='#44cc88'))
                except Exception as exc:
                    _audit('pull', detail=provider_name, status='error', error=str(exc))
                    self.after(0, lambda: self._reveal_status.config(
                        text=f'❌ Pull failed: {exc}', fg=HIGHLIGHT))

            threading.Thread(target=worker, daemon=True).start()

        _btn(win, 'Pull', _do_pull).grid(row=1, column=0, columnspan=2, pady=10)

    def _on_reveal_success(self, paths):
        self._reveal_listbox.delete(0, 'end')
        for p in paths:
            self._reveal_listbox.insert('end', p)
        n = len(paths)
        self._reveal_status.config(
            text=f'✅ Revealed {n} file{"s" if n != 1 else ""}!', fg='#44cc88')

    def _on_reveal_error(self, msg):
        self._reveal_status.config(text=f'❌ Error: {msg}', fg=HIGHLIGHT)
        messagebox.showerror('GhostStore — Reveal failed', msg)

    def _open_reveal_folder(self):
        d = self._reveal_outdir.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)     # Windows; cross-platform: subprocess.run(['xdg-open', d])

    # ── INSPECT action ────────────────────────────────────────────────────────

    def _run_inspect(self):
        path = self._inspect_path.get().strip()
        if not path:
            messagebox.showwarning('GhostStore', 'Please select a carrier file.')
            return

        self._set_inspect_text('⏳ Inspecting…')
        self.update_idletasks()

        def worker():
            try:
                info = inspect(path)
                lines = [f'{k}: {v}' for k, v in info.items()]
                self.after(0, self._set_inspect_text, '\n'.join(lines))
            except Exception as exc:
                self.after(0, self._set_inspect_text, f'Error: {exc}')

        threading.Thread(target=worker, daemon=True).start()

    def _set_inspect_text(self, text):
        self._inspect_result.config(state='normal')
        self._inspect_result.delete('1.0', 'end')
        self._inspect_result.insert('1.0', text)
        self._inspect_result.config(state='disabled')


    # ── VAULT tab ─────────────────────────────────────────────────────────────

    def _build_vault_tab(self):
        parent = self._tab_vault

        tk.Label(parent, text='GhostStore — Vault', bg=BG, fg=HIGHLIGHT,
                 font=FONT_BIG).pack(pady=(14, 4))

        # Toolbar
        toolbar = tk.Frame(parent, bg=BG)
        toolbar.pack(fill='x', padx=PAD, pady=(0, 6))
        _btn(toolbar, '🔄 Refresh',      self._vault_refresh).pack(side='left', padx=(0, 6))
        _btn(toolbar, '📂 Import .json', self._vault_import).pack(side='left', padx=(0, 6))
        _btn(toolbar, '🗑 Delete',       self._vault_delete, danger=True).pack(side='left')
        _btn(toolbar, '♻️  Dedup Stats',  self._vault_dedup_stats).pack(side='left', padx=(12, 0))
        _btn(toolbar, '☁ Push to Cloud', self._vault_push_selected).pack(side='left', padx=(6, 0))

        # Table headers
        header = tk.Frame(parent, bg=ACCENT)
        header.pack(fill='x', padx=PAD)
        for col, w in [('Name / Label', 28), ('Created', 18), ('Size', 10), ('Chunks', 7), ('Original Filename', 20)]:
            tk.Label(header, text=col, bg=ACCENT, fg=FG, font=FONT_B,
                     width=w, anchor='w').pack(side='left', padx=2)

        # Listbox
        self._vault_listbox = tk.Listbox(
            parent, bg=PANEL, fg=FG, font=MONO,
            selectmode='single', relief='flat', height=12,
            activestyle='none', selectbackground=HIGHLIGHT,
        )
        self._vault_listbox.pack(fill='both', expand=True, padx=PAD, pady=(0, 4))
        self._vault_listbox.bind('<<ListboxSelect>>', self._on_vault_select)

        # Action row
        action = tk.Frame(parent, bg=BG)
        action.pack(fill='x', padx=PAD, pady=6)
        _btn(action, '🔓 Reveal Selected', self._vault_reveal).pack(side='left', padx=(0, 8))
        tk.Label(action, text='Output folder:', bg=BG, fg=FG, font=FONT).pack(side='left')
        self._vault_outdir = tk.StringVar()
        _entry(action, textvariable=self._vault_outdir, width=34).pack(side='left', padx=6)
        _btn(action, 'Browse…', self._vault_browse_outdir).pack(side='left')

        # Status
        self._vault_status = tk.Label(parent, text='', bg=BG, fg=FG_DIM,
                                       font=FONT, wraplength=580)
        self._vault_status.pack()

        # Internal record list
        self._vault_records = []

        self._vault_refresh()

    def _vault_refresh(self):
        self._vault_listbox.delete(0, 'end')
        try:
            self._vault_records = list_all()
        except Exception as e:
            self._vault_status.config(text=f'❌ {e}', fg=HIGHLIGHT)
            return

        missing = 0
        for r in self._vault_records:
            size         = _fmt_size(r['size_bytes'])
            display_name = r['notes'] if r['notes'] else r['filename']
            path_ok      = os.path.isdir(r['storage_dir'])
            status_icon  = '✅' if path_ok else '⚠️'
            if not path_ok:
                missing += 1
            line = f"{status_icon} {display_name:<28} {r['created'][:16]:<18} {size:<12} {r['chunk_count']:<8} {r['filename']}"
            self._vault_listbox.insert('end', line)
            if not path_ok:
                # Tint missing records red
                self._vault_listbox.itemconfig('end', fg=HIGHLIGHT)

        n = len(self._vault_records)
        if missing:
            self._vault_status.config(
                text=f'{n} record{"s" if n != 1 else ""} in vault  •  '
                     f'⚠️ {missing} carrier folder{"s" if missing != 1 else ""} not found — '
                     f'move carriers back or re-hide to restore.',
                fg='#e09030')
        else:
            self._vault_status.config(
                text=f'{n} record{"s" if n != 1 else ""} in vault  •  all carrier folders found ✅',
                fg=FG_DIM)

    def _on_vault_select(self, event=None):
        pass  # reserved for detail panel in future

    def _vault_import(self):
        path = filedialog.askopenfilename(
            title='Import manifest.json',
            filetypes=[('JSON manifest', '*.json'), ('Any file', '*.*')]
        )
        if not path:
            return
        try:
            rebuild_from_manifest(path)
            self._vault_refresh()
            self._vault_status.config(text='✅ Manifest imported into vault.', fg='#44cc88')
        except Exception as e:
            messagebox.showerror('Import failed', str(e))

    def _vault_delete(self):
        sel = self._vault_listbox.curselection()
        if not sel:
            messagebox.showwarning('GhostStore', 'Select a record to delete.')
            return
        record = self._vault_records[sel[0]]
        if not messagebox.askyesno('Delete record',
            f'Remove "{record["filename"]}" from vault?\n\n'
            f'Carrier files will NOT be deleted.'):
            return
        try:
            delete(record['id'])
            self._vault_refresh()
        except Exception as e:
            messagebox.showerror('Delete failed', str(e))

    def _vault_browse_outdir(self):
        d = filedialog.askdirectory(title='Select output folder')
        if d:
            self._vault_outdir.set(d)

    def _vault_reveal(self):
        sel = self._vault_listbox.curselection()
        if not sel:
            messagebox.showwarning('GhostStore', 'Select a record to reveal.')
            return
        outdir = self._vault_outdir.get().strip()
        if not outdir:
            messagebox.showwarning('GhostStore', 'Choose an output folder first.')
            return

        record = self._vault_records[sel[0]]
        self._vault_status.config(text='⏳ Revealing…', fg=FG_DIM)
        self.update_idletasks()

        def worker():
            try:
                paths = reveal_v2(record['id'], outdir)
                self.after(0, self._vault_reveal_done, paths)
            except Exception as e:
                self.after(0, lambda: self._vault_status.config(
                    text=f'❌ {e}', fg=HIGHLIGHT))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _vault_reveal_done(self, paths):
        n = len(paths)
        self._vault_status.config(
            text=f'✅ Revealed {n} file{"s" if n != 1 else ""}!', fg='#44cc88')
        os.startfile(self._vault_outdir.get())



    # ── KEYS tab ──────────────────────────────────────────────────────────────

    def _build_keys_tab(self):
        parent = self._tab_keys

        tk.Label(parent, text='GhostStore — Key Manager', bg=BG, fg=HIGHLIGHT,
                 font=FONT_BIG).pack(pady=(14, 4))
        tk.Label(parent,
            text='Your encryption keys are saved here automatically after every hide. '
                 'Copy a key to use it for manual reveal.',
            bg=BG, fg=FG_DIM, font=FONT, wraplength=580).pack(pady=(0, 6))

        # Toolbar
        toolbar = tk.Frame(parent, bg=BG)
        toolbar.pack(fill='x', padx=PAD, pady=(0, 6))
        _btn(toolbar, '🔄 Refresh',   self._keys_refresh).pack(side='left', padx=(0, 6))
        _btn(toolbar, '📋 Copy Key',  self._keys_copy).pack(side='left', padx=(0, 6))
        _btn(toolbar, '✏️  Rename',    self._keys_rename).pack(side='left', padx=(0, 6))
        _btn(toolbar, '🗑 Delete',    self._keys_delete, danger=True).pack(side='left')

        # Column headers
        header = tk.Frame(parent, bg=ACCENT)
        header.pack(fill='x', padx=PAD)
        for col, w in [('Name', 26), ('Created', 18), ('Key Preview', 18), ('Linked File', 20)]:
            tk.Label(header, text=col, bg=ACCENT, fg=FG, font=FONT_B,
                     width=w, anchor='w').pack(side='left', padx=2)

        # Listbox
        self._keys_listbox = tk.Listbox(
            parent, bg=PANEL, fg=FG, font=MONO,
            selectmode='single', relief='flat', height=14,
            activestyle='none', selectbackground=HIGHLIGHT,
        )
        self._keys_listbox.pack(fill='both', expand=True, padx=PAD, pady=(0, 4))

        # Status bar
        self._keys_status = tk.Label(
            parent, text='', bg=BG, fg=FG_DIM, font=FONT, wraplength=580)
        self._keys_status.pack()

        self._keys_records = []
        self._keys_refresh()

    def _keys_refresh(self):
        self._keys_listbox.delete(0, 'end')
        try:
            self._keys_records = list_keys()
        except Exception as e:
            self._keys_status.config(text=f'❌ {e}', fg=HIGHLIGHT)
            return
        for r in self._keys_records:
            linked = r['notes'] if r['notes'] else (r['record_id'][:8] + '…' if r['record_id'] else '—')
            line = f"{r['name']:<28} {r['created'][:16]:<18} {r['key_preview']:<18} {linked}"
            self._keys_listbox.insert('end', line)
        n = len(self._keys_records)
        self._keys_status.config(
            text=f'{n} key{"s" if n != 1 else ""} stored', fg=FG_DIM)

    def _keys_selected(self):
        sel = self._keys_listbox.curselection()
        if not sel:
            messagebox.showwarning('GhostStore', 'Select a key first.')
            return None
        return self._keys_records[sel[0]]

    def _keys_copy(self):
        rec = self._keys_selected()
        if not rec:
            return
        try:
            key_hex = get_key_hex(rec['id'])
            if not key_hex:
                messagebox.showerror('GhostStore', 'Key not found in database.')
                return
            self.clipboard_clear()
            self.clipboard_append(key_hex)
            self._keys_status.config(
                text=f'✅ Key "{rec["name"]}" copied to clipboard.', fg='#44cc88')
        except Exception as e:
            messagebox.showerror('Copy failed', str(e))

    def _keys_rename(self):
        rec = self._keys_selected()
        if not rec:
            return
        # Simple rename dialog using askstring
        import tkinter.simpledialog as sd
        new_name = sd.askstring(
            'Rename Key',
            f'Enter new name for key:\n"{rec["name"]}"',
            initialvalue=rec['name'],
            parent=self,
        )
        if new_name and new_name.strip():
            try:
                rename_key(rec['id'], new_name.strip())
                self._keys_refresh()
                self._keys_status.config(text=f'✅ Renamed to "{new_name.strip()}".', fg='#44cc88')
            except Exception as e:
                messagebox.showerror('Rename failed', str(e))

    def _keys_delete(self):
        rec = self._keys_selected()
        if not rec:
            return
        if not messagebox.askyesno('Delete Key',
            f'Permanently delete key:\n"{rec["name"]}"?\n\n'
            f'Files hidden with this key cannot be recovered without it.'):
            return
        try:
            delete_key(rec['id'])
            self._keys_refresh()
            self._keys_status.config(text='🗑 Key deleted.', fg=FG_DIM)
        except Exception as e:
            messagebox.showerror('Delete failed', str(e))

    def _build_settings_tab(self):
        parent = self._tab_settings
        tk.Label(parent, text='GhostStore — Settings', bg=BG, fg=HIGHLIGHT,
                 font=FONT_BIG).pack(pady=(14, 4))

        lf_outer = tk.Frame(parent, bg=BG, pady=4)
        lf_outer_inner = tk.Frame(lf_outer, bg=PANEL, padx=PAD, pady=PAD)
        tk.Label(lf_outer, text='  ☁  Cloud Storage  ', bg=BG, fg=FG_DIM, font=FONT).pack(anchor='w')
        lf_outer.pack(fill='x', padx=PAD)
        lf_outer_inner.pack(fill='x')

        tk.Label(lf_outer_inner, text='Provider:', bg=PANEL, fg=FG, font=FONT).grid(
            row=0, column=0, sticky='w', pady=4)
        self._settings_provider_var = tk.StringVar(value='s3')
        provider_cb = ttk.Combobox(
            lf_outer_inner,
            textvariable=self._settings_provider_var,
            values=['s3', 'gcs', 'azure'],
            state='readonly', width=12,
        )
        provider_cb.grid(row=0, column=1, sticky='w', padx=6)
        provider_cb.bind('<<ComboboxSelected>>', lambda _: self._refresh_cloud_fields(lf_outer_inner))

        self._cloud_fields_frame = tk.Frame(lf_outer_inner, bg=PANEL)
        self._cloud_fields_frame.grid(row=1, column=0, columnspan=3, sticky='ew', pady=6)

        btn_row = tk.Frame(lf_outer_inner, bg=PANEL)
        btn_row.grid(row=2, column=0, columnspan=3, sticky='w', pady=(6, 0))
        _btn(btn_row, 'Save to keychain', self._save_cloud_credentials).pack(side='left')
        _btn(btn_row, 'Clear credentials', self._clear_cloud_credentials).pack(side='left', padx=(8, 0))

        self._settings_status = tk.Label(parent, text='', bg=BG, fg=FG_DIM, font=FONT)
        self._settings_status.pack(pady=(8, 0))

        self._refresh_cloud_fields(lf_outer_inner)

    def _refresh_cloud_fields(self, parent_frame):
        for widget in self._cloud_fields_frame.winfo_children():
            widget.destroy()
        self._cloud_entries = {}
        provider = self._settings_provider_var.get()
        FIELD_DEFS = {
            's3':    [('Access Key ID',      'ghoststore_s3',    'access_key',          False),
                      ('Secret Access Key',  'ghoststore_s3',    'secret_key',          True),
                      ('Region',             'ghoststore_s3',    'region',              False),
                      ('Bucket Name',        'ghoststore_s3',    'bucket',              False)],
            'gcs':   [('Credentials JSON',   'ghoststore_gcs',   'credentials_json',    False),
                      ('Bucket Name',        'ghoststore_gcs',   'bucket',              False)],
            'azure': [('Connection String',  'ghoststore_azure', 'connection_string',   True),
                      ('Container Name',     'ghoststore_azure', 'container',           False)],
        }
        for i, (label, service, key, secret) in enumerate(FIELD_DEFS.get(provider, [])):
            tk.Label(self._cloud_fields_frame, text=label + ':', bg=PANEL, fg=FG,
                     font=FONT).grid(row=i, column=0, sticky='w', pady=2)
            entry = tk.Entry(self._cloud_fields_frame, width=44, show='*' if secret else '',
                             bg=ACCENT, fg=FG, insertbackground=FG, relief='flat', font=MONO)
            try:
                from cloud_storage import get_credential
                existing = get_credential(service, key)
                if existing:
                    entry.insert(0, existing)
            except Exception:
                pass
            entry.grid(row=i, column=1, sticky='ew', padx=6, pady=2)
            self._cloud_entries[(service, key)] = entry

    def _save_cloud_credentials(self):
        try:
            from cloud_storage import set_credential
            for (service, key), entry in self._cloud_entries.items():
                val = entry.get().strip()
                if val:
                    set_credential(service, key, val)
            self._settings_status.config(text='✅ Credentials saved to Windows keychain.', fg='#44cc88')
        except Exception as exc:
            self._settings_status.config(text=f'❌ {exc}', fg=HIGHLIGHT)

    def _clear_cloud_credentials(self):
        try:
            from cloud_storage import delete_credential
            for (service, key) in list(self._cloud_entries.keys()):
                delete_credential(service, key)
            self._refresh_cloud_fields(self._cloud_fields_frame)
            self._settings_status.config(text='✅ Credentials cleared.', fg=FG_DIM)
        except Exception as exc:
            self._settings_status.config(text=f'❌ {exc}', fg=HIGHLIGHT)

    def _vault_push_selected(self):
        sel = self._vault_listbox.curselection()
        if not sel:
            messagebox.showwarning('GhostStore', 'Select a vault record to push.')
            return

        win = tk.Toplevel(self)
        win.title('Push to Cloud')
        win.resizable(False, False)
        win.configure(bg=BG)
        tk.Label(win, text='Cloud provider:', bg=BG, fg=FG, font=FONT).grid(
            row=0, column=0, padx=10, pady=10, sticky='w')
        pvar = tk.StringVar(value='s3')
        ttk.Combobox(win, textvariable=pvar, values=['s3', 'gcs', 'azure'],
                     state='readonly', width=12).grid(row=0, column=1, padx=6)

        def _do_push():
            win.destroy()
            record = self._vault_records[sel[0]]
            provider_name = pvar.get()
            self._vault_status.config(text=f'☁ Pushing to {provider_name}…', fg=FG_DIM)
            self.update_idletasks()

            def worker():
                try:
                    import json as _json
                    from cloud_storage import get_provider
                    from vault import conn as vault_conn
                    manifest = _json.loads(record['manifest']) if isinstance(record.get('manifest'), str) else record
                    provider = get_provider(provider_name)
                    updated = provider.push_manifest(
                        manifest,
                        prefix='ghoststore',
                        progress_cb=lambda done, total: self.after(
                            0, lambda d=done, t=total: self._vault_status.config(
                                text=f'☁ Uploading {d}/{t}…', fg=FG_DIM)),
                    )
                    vault_conn.execute(
                        'UPDATE files SET manifest = ? WHERE id = ?',
                        (_json.dumps(updated), record['id']),
                    )
                    vault_conn.commit()
                    self.after(0, lambda: self._vault_status.config(
                        text=f'✅ Pushed {len(manifest["chunks"])} carrier(s) to {provider_name}.',
                        fg='#44cc88'))
                except Exception as exc:
                    self.after(0, lambda: self._vault_status.config(
                        text=f'❌ Push failed: {exc}', fg=HIGHLIGHT))

            threading.Thread(target=worker, daemon=True).start()

        _btn(win, 'Push', _do_push).grid(row=1, column=0, columnspan=2, pady=10)

    def _vault_dedup_stats(self):
        try:
            from dedup_engine import dedup_stats
            stats = dedup_stats()
            if stats['total_chunks'] == 0:
                messagebox.showinfo('Dedup Stats',
                    'No CDC chunks registered yet.\n\n'
                    'Hide files using CDC chunking mode to build the dedup registry.')
                return
            msg = (
                f"Deduplication Registry\n"
                f"{'─'*36}\n"
                f"Total chunks:      {stats['total_chunks']:,}\n"
                f"Unique chunks:     {stats['unique_chunks']:,}\n"
                f"Duplicate chunks:  {stats['duplicate_chunks']:,}\n"
                f"\n"
                f"Total data:        {_fmt_size(stats['total_bytes'])}\n"
                f"Actually stored:   {_fmt_size(stats['unique_bytes'])}\n"
                f"Saved:             {_fmt_size(stats['bytes_saved'])}  "
                f"({stats['space_saving_pct']}%)\n"
                f"\n"
                f"Dedup ratio:       {stats['dedup_ratio']*100:.1f}%"
            )
            messagebox.showinfo('♻️  Dedup Stats', msg)
        except Exception as e:
            messagebox.showerror('Dedup Stats', str(e))

    # ── ENTERPRISE tab ────────────────────────────────────────────────────────

    def _build_enterprise_tab(self):
        parent = self._tab_enterprise

        tk.Label(parent, text='GhostStore — Enterprise', bg=BG, fg=HIGHLIGHT,
                 font=FONT_BIG).pack(pady=(14, 4))
        tk.Label(parent,
            text='Deduplication dashboard and full audit log.',
            bg=BG, fg=FG_DIM, font=FONT).pack(pady=(0, 8))

        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=BG)
        cw = canvas.create_window((0, 0), window=inner, anchor='nw')

        def _resize(e): canvas.itemconfig(cw, width=e.width)
        def _scroll(e): canvas.configure(scrollregion=canvas.bbox('all'))
        canvas.bind('<Configure>', _resize)
        inner.bind('<Configure>', _scroll)
        canvas.bind_all('<MouseWheel>',
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

        # ── Dedup dashboard ───────────────────────────────────────────────────
        dash_outer = tk.Frame(inner, bg=BG, pady=4)
        dash_outer.pack(fill='x', padx=PAD)
        tk.Label(dash_outer, text='  ♻  Deduplication Dashboard  ',
                 bg=BG, fg=FG_DIM, font=FONT).pack(anchor='w')
        dash = tk.Frame(dash_outer, bg=PANEL, padx=PAD, pady=PAD)
        dash.pack(fill='x')

        self._ent_stats_frame = tk.Frame(dash, bg=PANEL)
        self._ent_stats_frame.pack(fill='x', pady=(0, 10))

        charts_row = tk.Frame(dash, bg=PANEL)
        charts_row.pack(fill='x')

        self._bar_canvas = tk.Canvas(
            charts_row, bg=PANEL, highlightthickness=0, width=340, height=200)
        self._bar_canvas.pack(side='left', padx=(0, 16))

        self._pie_canvas = tk.Canvas(
            charts_row, bg=PANEL, highlightthickness=0, width=260, height=200)
        self._pie_canvas.pack(side='left')

        btn_row = tk.Frame(dash, bg=PANEL)
        btn_row.pack(fill='x', pady=(10, 0))
        _btn(btn_row, '🔄 Refresh Stats', self._ent_refresh_dedup).pack(side='left')

        # ── Audit log ─────────────────────────────────────────────────────────
        log_outer = tk.Frame(inner, bg=BG, pady=4)
        log_outer.pack(fill='x', padx=PAD, pady=(10, 0))
        tk.Label(log_outer, text='  📋  Audit Log  ',
                 bg=BG, fg=FG_DIM, font=FONT).pack(anchor='w')
        log_frame = tk.Frame(log_outer, bg=PANEL, padx=PAD, pady=PAD)
        log_frame.pack(fill='x')

        filter_row = tk.Frame(log_frame, bg=PANEL)
        filter_row.pack(fill='x', pady=(0, 6))
        tk.Label(filter_row, text='Filter:', bg=PANEL, fg=FG,
                 font=FONT).pack(side='left', padx=(0, 6))
        ops = ['all', 'hide', 'reveal', 'push', 'pull',
               'inspect', 'key_save', 'key_delete', 'key_rename', 'key_copy']
        self._audit_filter_var = tk.StringVar(value='all')
        ttk.Combobox(filter_row, textvariable=self._audit_filter_var,
                     values=ops, state='readonly', width=14).pack(side='left')
        _btn(filter_row, '🔄 Refresh',
             self._ent_refresh_audit).pack(side='left', padx=(10, 0))
        _btn(filter_row, '🗑 Clear Log',
             self._ent_clear_audit, danger=True).pack(side='left', padx=(6, 0))

        header = tk.Frame(log_frame, bg=ACCENT)
        header.pack(fill='x')
        for col, w in [('Timestamp', 20), ('Operation', 12),
                        ('Status', 7), ('Detail', 34), ('Error', 18)]:
            tk.Label(header, text=col, bg=ACCENT, fg=FG, font=FONT_B,
                     width=w, anchor='w').pack(side='left', padx=2)

        self._audit_listbox = tk.Listbox(
            log_frame, bg=PANEL, fg=FG, font=MONO,
            selectmode='single', relief='flat', height=14,
            activestyle='none', selectbackground=HIGHLIGHT,
        )
        self._audit_listbox.pack(fill='both', expand=True, pady=(0, 4))

        self._ent_status = tk.Label(
            inner, text='', bg=BG, fg=FG_DIM, font=FONT)
        self._ent_status.pack(pady=4)

        self._ent_refresh_dedup()
        self._ent_refresh_audit()

    def _ent_refresh_dedup(self):
        try:
            from dedup_engine import dedup_stats
            s = dedup_stats()
            self._draw_dedup_stats(s)
            self._draw_bar_chart(s)
            self._draw_pie_chart(s)
            self._ent_status.config(
                text=f'Last refreshed — {s["total_chunks"]} chunk(s) in registry.',
                fg=FG_DIM)
        except Exception as exc:
            self._ent_status.config(text=f'❌ {exc}', fg=HIGHLIGHT)

    def _draw_dedup_stats(self, s):
        for w in self._ent_stats_frame.winfo_children():
            w.destroy()

        def _stat(label, value, colour=FG):
            f = tk.Frame(self._ent_stats_frame, bg=PANEL, padx=16, pady=6)
            f.pack(side='left')
            tk.Label(f, text=value, bg=PANEL, fg=colour,
                     font=('Segoe UI', 14, 'bold')).pack()
            tk.Label(f, text=label, bg=PANEL, fg=FG_DIM, font=FONT).pack()

        _stat('Total chunks',   str(s.get('total_chunks', 0)))
        _stat('Unique chunks',  str(s.get('unique_chunks', 0)))
        _stat('Duplicate hits', str(s.get('duplicate_chunks', 0)), '#44cc88')
        _stat('Total data',     _fmt_size(s.get('total_bytes', 0)))
        _stat('Stored',         _fmt_size(s.get('unique_bytes', 0)))
        _stat('Saved',
              f'{_fmt_size(s.get("bytes_saved", 0))} ({s.get("space_saving_pct", 0)}%)',
              '#44cc88')

    def _draw_bar_chart(self, s):
        c = self._bar_canvas
        c.delete('all')
        W, H = 340, 200
        pad_l, pad_r, pad_t, pad_b = 54, 16, 20, 40
        total  = s.get('total_bytes',  1) or 1
        stored = s.get('unique_bytes', 0)
        saved  = s.get('bytes_saved',  0)
        chart_h = H - pad_t - pad_b
        chart_w = W - pad_l - pad_r
        bar_w   = chart_w // 4
        bars = [('Total', total, '#4a7fd4'),
                ('Stored', stored, '#3ab5a0'),
                ('Saved',  saved,  '#44cc88')]
        max_val = max(v for _, v, _ in bars) or 1
        c.create_text(W // 2, 10, text='Storage Breakdown (bytes)',
                      fill=FG_DIM, font=FONT, anchor='n')
        for i, (label, val, colour) in enumerate(bars):
            x = pad_l + i * (bar_w + 14)
            bar_h = int((val / max_val) * chart_h)
            y0 = pad_t + chart_h - bar_h
            y1 = pad_t + chart_h
            c.create_rectangle(x, y0, x + bar_w, y1, fill=colour, outline='')
            c.create_text(x + bar_w // 2, y0 - 4,
                          text=_fmt_size(val), fill=FG,
                          font=('Segoe UI', 8), anchor='s')
            c.create_text(x + bar_w // 2, y1 + 6,
                          text=label, fill=FG_DIM,
                          font=('Segoe UI', 8), anchor='n')
        c.create_line(pad_l - 2, pad_t, pad_l - 2, pad_t + chart_h,
                      fill=FG_DIM, width=1)

    def _draw_pie_chart(self, s):
        import math
        c = self._pie_canvas
        c.delete('all')
        W, H = 260, 200
        unique = s.get('unique_chunks',    0)
        dupes  = s.get('duplicate_chunks', 0)
        total  = unique + dupes
        cx, cy, r = W // 2, 90, 68
        c.create_text(W // 2, 10, text='Chunks: Unique vs Duplicate',
                      fill=FG_DIM, font=FONT, anchor='n')
        if total == 0:
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=ACCENT, outline='')
            c.create_text(cx, cy, text='No data', fill=FG_DIM, font=FONT)
            return
        slices = [('Unique',    unique, '#4a7fd4'),
                  ('Duplicate', dupes,  '#44cc88')]
        start = -90.0
        for label, count, colour in slices:
            if count == 0:
                continue
            extent = (count / total) * 360.0
            c.create_arc(cx - r, cy - r, cx + r, cy + r,
                         start=start, extent=extent,
                         fill=colour, outline=PANEL, width=2)
            mid_angle = math.radians(start + extent / 2)
            lx = cx + (r + 20) * math.cos(mid_angle)
            ly = cy + (r + 20) * math.sin(mid_angle)
            c.create_text(lx, ly, text=f'{label}\n{count}',
                          fill=FG, font=('Segoe UI', 8), anchor='center')
            start += extent
        for i, (label, _, colour) in enumerate(slices):
            lx = 16 + i * 120
            c.create_rectangle(lx, H - 24, lx + 12, H - 12,
                                fill=colour, outline='')
            c.create_text(lx + 16, H - 18, text=label,
                          fill=FG_DIM, font=('Segoe UI', 8), anchor='w')

    def _ent_refresh_audit(self):
        self._audit_listbox.delete(0, 'end')
        try:
            from audit_log import get_log
            op_filter = self._audit_filter_var.get()
            op = None if op_filter == 'all' else op_filter
            entries = get_log(limit=200, operation=op)
            for e in entries:
                ts     = e['timestamp'][:19].replace('T', ' ')
                op_str = e['operation'][:10].ljust(11)
                st     = ('✅' if e['status'] == 'ok' else '❌').ljust(3)
                detail = (e['detail'] or '')[:34]
                err    = (e['error']  or '')[:18]
                line   = f'{ts}  {op_str}  {st}  {detail:<34}  {err}'
                self._audit_listbox.insert('end', line)
                if e['status'] == 'error':
                    self._audit_listbox.itemconfig('end', fg=HIGHLIGHT)
            n = len(entries)
            self._ent_status.config(
                text=f'{n} log entr{"y" if n == 1 else "ies"} shown.', fg=FG_DIM)
        except Exception as exc:
            self._ent_status.config(text=f'❌ {exc}', fg=HIGHLIGHT)

    def _ent_clear_audit(self):
        if not messagebox.askyesno('Clear Audit Log',
                                   'Permanently delete all audit log entries?'):
            return
        try:
            from audit_log import clear_log
            n = clear_log()
            self._ent_refresh_audit()
            self._ent_status.config(text=f'🗑 Cleared {n} log entries.', fg=FG_DIM)
        except Exception as exc:
            self._ent_status.config(text=f'❌ {exc}', fg=HIGHLIGHT)

# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = GhostStoreApp()
    app.mainloop()
