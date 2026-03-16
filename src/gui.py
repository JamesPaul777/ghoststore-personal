"""
gui.py  —  GhostStore Personal Desktop GUI
Hide, Reveal, Inspect, Vault, Keys tabs.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pipeline import hide_v2, reveal_v2
from vault import list_all, delete, rebuild_from_manifest
from key_manager import save_key, list_keys, get_key_hex, delete_key, rename_key
from carrier_inspect import inspect

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = '#1a1a2e'
PANEL     = '#16213e'
ACCENT    = '#0f3460'
HIGHLIGHT = '#e94560'
FG        = '#eaeaea'
FG_DIM    = '#8888aa'
FONT      = ('Segoe UI', 10)
FONT_B    = ('Segoe UI', 10, 'bold')
FONT_BIG  = ('Segoe UI', 13, 'bold')
MONO      = ('Consolas', 9)
PAD       = 10

CARRIER_EXT = {'image': '.png', 'video': '.mkv', 'audio': '.wav'}
ALL_MEDIA   = [
    ('Media files', '*.png *.jpg *.jpeg *.webp *.bmp *.mp4 *.mov *.avi *.mkv *.wmv *.wav'),
    ('Any file', '*.*'),
]

# ── Helper widgets ────────────────────────────────────────────────────────────

def _fmt_size(n):
    if n < 1024:          return f'{n} B'
    elif n < 1024**2:     return f'{n/1024:.1f} KB'
    elif n < 1024**3:     return f'{n/1024**2:.1f} MB'
    else:                 return f'{n/1024**3:.2f} GB'

def _btn(parent, text, command, danger=False):
    colour = HIGHLIGHT if danger else '#3a7bd5'
    return tk.Button(parent, text=text, command=command,
                     bg=colour, fg='white', activebackground=colour,
                     relief='flat', font=FONT_B, padx=12, pady=5, cursor='hand2')

def _entry(parent, textvariable=None, width=50, readonly=False):
    return tk.Entry(parent, textvariable=textvariable, width=width,
                    bg=ACCENT, fg=FG, insertbackground=FG,
                    relief='flat', font=MONO,
                    state='readonly' if readonly else 'normal')

def _section(parent, title):
    outer = tk.Frame(parent, bg=BG, pady=4)
    outer.pack(fill='x', padx=PAD)
    tk.Label(outer, text=f'  {title}  ', bg=BG, fg=FG_DIM, font=FONT).pack(anchor='w')
    inner = tk.Frame(outer, bg=PANEL, padx=PAD, pady=PAD)
    inner.pack(fill='x')
    return inner

def _row(parent, **kw):
    f = tk.Frame(parent, bg=PANEL, **kw)
    f.pack(fill='x', pady=2)
    return f


# ── Main app ──────────────────────────────────────────────────────────────────

class GhostStoreApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('GhostStore')
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(640, 520)

        self._secret_paths  = []
        self._hide_mode     = tk.StringVar(value='blend')
        self._carrier_type  = tk.StringVar(value='image')
        self._carrier_path  = tk.StringVar()
        self._hide_output   = tk.StringVar()
        self._hide_label    = tk.StringVar()
        self._last_key      = tk.StringVar()

        self._reveal_manifest = tk.StringVar()
        self._reveal_outdir   = tk.StringVar()
        self._inspect_path    = tk.StringVar()

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True)

        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=ACCENT, foreground=FG,
                        font=FONT_B, padding=[16, 6])
        style.map('TNotebook.Tab',
                  background=[('selected', HIGHLIGHT)],
                  foreground=[('selected', 'white')])

        self._tab_hide    = tk.Frame(nb, bg=BG)
        self._tab_reveal  = tk.Frame(nb, bg=BG)
        self._tab_inspect = tk.Frame(nb, bg=BG)
        self._tab_vault   = tk.Frame(nb, bg=BG)
        self._tab_keys    = tk.Frame(nb, bg=BG)

        nb.add(self._tab_hide,    text='  HIDE  ')
        nb.add(self._tab_reveal,  text=' REVEAL ')
        nb.add(self._tab_inspect, text=' INSPECT')
        nb.add(self._tab_vault,   text='  VAULT ')
        nb.add(self._tab_keys,    text='  KEYS  ')

        self._build_hide_tab()
        self._build_reveal_tab()
        self._build_inspect_tab()
        self._build_vault_tab()
        self._build_keys_tab()

    # ── HIDE tab ──────────────────────────────────────────────────────────────

    def _build_hide_tab(self):
        outer = self._tab_hide
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        parent = tk.Frame(canvas, bg=BG)
        cw = canvas.create_window((0, 0), window=parent, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))
        parent.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

        tk.Label(parent, text='GhostStore — Hide Your Files', bg=BG,
                 fg=HIGHLIGHT, font=FONT_BIG).pack(pady=(14, 4))

        # Mode
        sec = _section(parent, 'Mode')
        tk.Radiobutton(sec, text='⭐  Blend & Hide  —  hide inside YOUR existing media  (zero extra storage cost)',
                       variable=self._hide_mode, value='blend', command=self._on_mode_change,
                       bg=PANEL, fg='#44cc88', selectcolor=ACCENT, activebackground=PANEL,
                       font=FONT_B).pack(anchor='w')
        tk.Radiobutton(sec, text='📦  Portable Container  —  GhostStore generates a carrier  (output will be larger than input)',
                       variable=self._hide_mode, value='generate', command=self._on_mode_change,
                       bg=PANEL, fg=FG_DIM, selectcolor=ACCENT, activebackground=PANEL,
                       font=FONT).pack(anchor='w')
        self._savings_lbl = tk.Label(sec, text='', bg=PANEL, fg='#44cc88', font=FONT)
        self._savings_lbl.pack(anchor='w', pady=(4, 0))

        # Secret files
        sec2 = _section(parent, 'Secret Files  (select one or more)')
        self._secret_listbox = tk.Listbox(sec2, bg=ACCENT, fg=FG, font=MONO,
                                          height=4, selectmode='extended', relief='flat')
        self._secret_listbox.pack(fill='x', pady=(4, 0))
        br = _row(sec2)
        _btn(br, 'Add Files…', self._browse_secrets).pack(side='left', padx=(0, 6))
        _btn(br, 'Clear', self._clear_secrets, danger=True).pack(side='left')
        self._secret_count_lbl = tk.Label(br, text='', bg=PANEL, fg=FG_DIM, font=FONT)
        self._secret_count_lbl.pack(side='left', padx=12)

        # Carrier
        self._carrier_sec = _section(parent, 'Carrier  (your existing media becomes the hiding spot)')
        self._ctype_frame = tk.Frame(self._carrier_sec, bg=PANEL)
        self._ctype_frame.pack(fill='x')
        tk.Label(self._ctype_frame, text='Generate carrier type:', bg=PANEL,
                 fg=FG, font=FONT).pack(side='left', padx=(0, 12))
        for val, label in [('image', '🖼 Image (PNG)'),
                            ('video', '🎬 Video (MKV)'),
                            ('audio', '🔊 Audio (WAV)')]:
            tk.Radiobutton(self._ctype_frame, text=label,
                           variable=self._carrier_type, value=val,
                           command=self._on_carrier_type_change,
                           bg=PANEL, fg=FG, selectcolor=ACCENT,
                           activebackground=PANEL, font=FONT).pack(side='left', padx=8)

        self._recommend_lbl = tk.Label(self._carrier_sec, text='', bg=PANEL,
                                       fg='#44cc88', font=FONT)
        self._recommend_lbl.pack(anchor='w', pady=(4, 0))
        self._carrier_size_lbl = tk.Label(self._carrier_sec, text='', bg=PANEL,
                                          fg=FG_DIM, font=FONT)
        self._carrier_size_lbl.pack(anchor='w')

        self._cfile_frame = tk.Frame(self._carrier_sec, bg=PANEL)
        tk.Label(self._cfile_frame, text='Carrier file:', bg=PANEL,
                 fg=FG, font=FONT).pack(side='left', padx=(0, 8))
        _entry(self._cfile_frame, textvariable=self._carrier_path,
               width=44).pack(side='left')
        _btn(self._cfile_frame, 'Browse…', self._browse_carrier).pack(side='left', padx=(6, 0))

        self._on_mode_change()

        # Output
        sec3 = _section(parent, 'Output')
        f3 = _row(sec3)
        tk.Label(f3, text='Save to folder:', bg=PANEL, fg=FG, font=FONT).pack(side='left', padx=(0, 8))
        _entry(f3, textvariable=self._hide_output, width=40).pack(side='left')
        _btn(f3, 'Browse…', self._browse_hide_output).pack(side='left', padx=(6, 0))

        f3b = _row(sec3)
        tk.Label(f3b, text='Name (for Vault):', bg=PANEL, fg=FG, font=FONT).pack(side='left', padx=(0, 8))
        _entry(f3b, textvariable=self._hide_label, width=40).pack(side='left')
        tk.Label(f3b, text='  e.g. "Tax docs 2025"', bg=PANEL, fg=FG_DIM, font=FONT).pack(side='left')

        # Action
        tk.Frame(parent, bg=BG).pack(pady=4)
        _btn(parent, '   HIDE FILES   ', self._run_hide).pack()

        self._hide_status = tk.Label(parent, text='', bg=BG, fg=FG_DIM,
                                     font=FONT, wraplength=580)
        self._hide_status.pack()

        key_sec = _section(parent, 'Encryption Key  (save this — you cannot recover your files without it)')
        key_row = _row(key_sec)
        self._key_display = _entry(key_row, textvariable=self._last_key,
                                   width=56, readonly=True)
        self._key_display.pack(side='left')
        _btn(key_row, '📋 Copy', self._copy_key).pack(side='left', padx=(8, 0))

    # ── REVEAL tab ────────────────────────────────────────────────────────────

    def _build_reveal_tab(self):
        parent = self._tab_reveal
        tk.Label(parent, text='GhostStore — Reveal', bg=BG,
                 fg=HIGHLIGHT, font=FONT_BIG).pack(pady=(14, 4))
        tk.Label(parent,
                 text='Select the manifest.json from your carrier folder. '
                      'The key is stored inside it — no need to enter it manually.',
                 bg=BG, fg=FG_DIM, font=FONT, wraplength=580).pack(pady=(0, 6))

        sec = _section(parent, 'Manifest File  (manifest.json inside your carrier folder)')
        f = _row(sec)
        tk.Label(f, text='manifest.json:', bg=PANEL, fg=FG, font=FONT).pack(side='left', padx=(0, 8))
        _entry(f, textvariable=self._reveal_manifest, width=44).pack(side='left')
        _btn(f, 'Browse…', self._browse_reveal_manifest).pack(side='left', padx=(6, 0))

        sec2 = _section(parent, 'Output Folder  (where to save revealed files)')
        f2 = _row(sec2)
        tk.Label(f2, text='Save to:', bg=PANEL, fg=FG, font=FONT).pack(side='left', padx=(0, 8))
        _entry(f2, textvariable=self._reveal_outdir, width=44).pack(side='left')
        _btn(f2, 'Browse…', self._browse_reveal_outdir).pack(side='left', padx=(6, 0))

        tk.Frame(parent, bg=BG).pack(pady=4)
        _btn(parent, '  REVEAL FILES  ', self._run_reveal).pack()

        self._reveal_status = tk.Label(parent, text='', bg=BG, fg=FG_DIM,
                                       font=FONT, wraplength=580)
        self._reveal_status.pack()

        res_sec = _section(parent, 'Revealed Files')
        self._reveal_listbox = tk.Listbox(res_sec, bg=ACCENT, fg=FG, font=MONO,
                                          height=6, relief='flat')
        self._reveal_listbox.pack(fill='x')
        _btn(res_sec, '📂 Open Folder', self._open_reveal_folder).pack(anchor='w', pady=(6, 0))

    # ── INSPECT tab ───────────────────────────────────────────────────────────

    def _build_inspect_tab(self):
        parent = self._tab_inspect
        tk.Label(parent, text='GhostStore — Inspect Carrier', bg=BG,
                 fg=HIGHLIGHT, font=FONT_BIG).pack(pady=(14, 4))

        sec = _section(parent, 'Carrier File')
        f = _row(sec)
        tk.Label(f, text='File:', bg=PANEL, fg=FG, font=FONT).pack(side='left', padx=(0, 8))
        _entry(f, textvariable=self._inspect_path, width=48).pack(side='left')
        _btn(f, 'Browse…', self._browse_inspect).pack(side='left', padx=(6, 0))

        tk.Frame(parent, bg=BG).pack(pady=4)
        _btn(parent, '  INSPECT  ', self._run_inspect).pack()

        self._inspect_result = tk.Text(parent, bg=PANEL, fg=FG, font=MONO,
                                       height=12, relief='flat', state='disabled')
        self._inspect_result.pack(fill='both', expand=True, padx=PAD, pady=(0, PAD))

    # ── VAULT tab ─────────────────────────────────────────────────────────────

    def _build_vault_tab(self):
        parent = self._tab_vault
        tk.Label(parent, text='GhostStore — Vault', bg=BG,
                 fg=HIGHLIGHT, font=FONT_BIG).pack(pady=(14, 4))

        toolbar = tk.Frame(parent, bg=BG)
        toolbar.pack(fill='x', padx=PAD, pady=(0, 6))
        _btn(toolbar, '🔄 Refresh',      self._vault_refresh).pack(side='left', padx=(0, 6))
        _btn(toolbar, '📂 Import .json', self._vault_import).pack(side='left', padx=(0, 6))
        _btn(toolbar, '🗑 Delete',       self._vault_delete, danger=True).pack(side='left')

        header = tk.Frame(parent, bg=ACCENT)
        header.pack(fill='x', padx=PAD)
        for col, w in [('Name / Label', 28), ('Created', 18), ('Size', 10),
                        ('Chunks', 7), ('Original Filename', 20)]:
            tk.Label(header, text=col, bg=ACCENT, fg=FG, font=FONT_B,
                     width=w, anchor='w').pack(side='left', padx=2)

        self._vault_listbox = tk.Listbox(parent, bg=PANEL, fg=FG, font=MONO,
                                         selectmode='single', relief='flat', height=12,
                                         activestyle='none', selectbackground=HIGHLIGHT)
        self._vault_listbox.pack(fill='both', expand=True, padx=PAD, pady=(0, 4))

        action = tk.Frame(parent, bg=BG)
        action.pack(fill='x', padx=PAD, pady=6)
        _btn(action, '🔓 Reveal Selected', self._vault_reveal).pack(side='left', padx=(0, 8))
        tk.Label(action, text='Output folder:', bg=BG, fg=FG, font=FONT).pack(side='left')
        self._vault_outdir = tk.StringVar()
        _entry(action, textvariable=self._vault_outdir, width=34).pack(side='left', padx=6)
        _btn(action, 'Browse…', self._vault_browse_outdir).pack(side='left')

        self._vault_status = tk.Label(parent, text='', bg=BG, fg=FG_DIM,
                                      font=FONT, wraplength=580)
        self._vault_status.pack()
        self._vault_records = []
        self._vault_refresh()

    # ── KEYS tab ──────────────────────────────────────────────────────────────

    def _build_keys_tab(self):
        parent = self._tab_keys
        tk.Label(parent, text='GhostStore — Key Manager', bg=BG,
                 fg=HIGHLIGHT, font=FONT_BIG).pack(pady=(14, 4))
        tk.Label(parent,
                 text='Your encryption keys are saved here automatically after every hide. '
                      'Copy a key to use it for manual reveal.',
                 bg=BG, fg=FG_DIM, font=FONT, wraplength=580).pack(pady=(0, 6))

        toolbar = tk.Frame(parent, bg=BG)
        toolbar.pack(fill='x', padx=PAD, pady=(0, 6))
        _btn(toolbar, '🔄 Refresh',  self._keys_refresh).pack(side='left', padx=(0, 6))
        _btn(toolbar, '📋 Copy Key', self._keys_copy).pack(side='left', padx=(0, 6))
        _btn(toolbar, '✏️  Rename',   self._keys_rename).pack(side='left', padx=(0, 6))
        _btn(toolbar, '🗑 Delete',   self._keys_delete, danger=True).pack(side='left')

        header = tk.Frame(parent, bg=ACCENT)
        header.pack(fill='x', padx=PAD)
        for col, w in [('Name', 26), ('Created', 18), ('Key Preview', 18), ('Linked File', 20)]:
            tk.Label(header, text=col, bg=ACCENT, fg=FG, font=FONT_B,
                     width=w, anchor='w').pack(side='left', padx=2)

        self._keys_listbox = tk.Listbox(parent, bg=PANEL, fg=FG, font=MONO,
                                        selectmode='single', relief='flat', height=14,
                                        activestyle='none', selectbackground=HIGHLIGHT)
        self._keys_listbox.pack(fill='both', expand=True, padx=PAD, pady=(0, 4))

        self._keys_status = tk.Label(parent, text='', bg=BG, fg=FG_DIM,
                                     font=FONT, wraplength=580)
        self._keys_status.pack()
        self._keys_records = []
        self._keys_refresh()

    # ── Mode toggle ───────────────────────────────────────────────────────────

    def _on_mode_change(self, *_):
        if self._hide_mode.get() == 'generate':
            self._cfile_frame.pack_forget()
            self._ctype_frame.pack(fill='x')
        else:
            self._ctype_frame.pack_forget()
            self._cfile_frame.pack(fill='x')
        self._update_savings_calculator()

    def _on_carrier_type_change(self):
        total = sum(os.path.getsize(p) for p in self._secret_paths if os.path.exists(p))
        if total > 0:
            self._update_carrier_size_estimate(total)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_savings_calculator(self):
        if self._hide_mode.get() != 'blend':
            self._savings_lbl.config(text='')
            return
        total = sum(os.path.getsize(p) for p in self._secret_paths if os.path.exists(p))
        carrier_raw = self._carrier_path.get().strip()
        carrier = carrier_raw.split('  (')[0].strip() if '  (' in carrier_raw else carrier_raw
        if total == 0:
            self._savings_lbl.config(
                text='⭐ Blend & Hide: add your secret files to see your storage saving.',
                fg='#44cc88')
        elif carrier and os.path.exists(carrier):
            cs = os.path.getsize(carrier)
            self._savings_lbl.config(
                text=f'✅ You save {_fmt_size(total)} — hidden inside your existing '
                     f'{_fmt_size(cs)} carrier. Zero extra storage cost.',
                fg='#44cc88')
        else:
            self._savings_lbl.config(
                text=f'✅ Once you select your carrier, {_fmt_size(total)} will be '
                     f'hidden at zero extra storage cost.',
                fg='#44cc88')

    def _update_carrier_size_estimate(self, payload_bytes):
        ctype = self._carrier_type.get()
        if ctype == 'image':
            est = payload_bytes * 10
            note = f'⚠️  Estimated carrier size: ~{_fmt_size(est)} (PNG)'
            colour = '#ffaa00' if est > 5*1024*1024 else FG_DIM
        elif ctype == 'audio':
            samples = payload_bytes * 8
            est = samples * 2
            note = f'📁 Estimated carrier size: ~{_fmt_size(est)} WAV'
            colour = FG_DIM
        else:
            est = max(payload_bytes * 2, 1024*1024)
            note = f'📁 Estimated carrier size: ~{_fmt_size(est)} MKV'
            colour = FG_DIM
        self._carrier_size_lbl.config(text=note, fg=colour)

    def _update_recommendation(self):
        if not self._secret_paths:
            self._recommend_lbl.config(text='')
            return
        total = sum(os.path.getsize(p) for p in self._secret_paths if os.path.exists(p))
        total_kb = total / 1024
        total_mb = total_kb / 1024
        if total < 100*1024:
            rec, tip = 'image', f'💡 {total_kb:.0f} KB — Image carrier recommended'
        elif total < 1024*1024:
            rec, tip = 'audio', f'💡 {total_kb:.0f} KB — Audio carrier recommended'
        else:
            rec, tip = 'video', f'💡 {total_mb:.1f} MB — Video carrier recommended'
        self._carrier_type.set(rec)
        self._recommend_lbl.config(text=tip)
        self._update_carrier_size_estimate(total)
        self._update_savings_calculator()

    def _check_capacity(self, carrier_path, payload_bytes):
        ext = os.path.splitext(carrier_path)[1].lower()
        if ext in {'.mp4', '.mov', '.avi', '.wmv', '.mkv', '.m4v'}:
            return True, -1  # skip — capacity only known after FFV1 conversion
        try:
            info = inspect(carrier_path)
            cap = info.get('capacity_bytes', 0)
            return cap >= payload_bytes, cap
        except Exception:
            return True, 0

    # ── Browse helpers ────────────────────────────────────────────────────────

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
            self._secret_listbox.insert('end', f'{os.path.basename(p)}  ({_fmt_size(size)})')
        n = len(self._secret_paths)
        self._secret_count_lbl.config(
            text=f'{n} file{"s" if n!=1 else ""} — {_fmt_size(total)} total' if n else '')
        self._update_recommendation()

    def _browse_carrier(self):
        p = filedialog.askopenfilename(title='Select carrier file', filetypes=ALL_MEDIA)
        if p:
            self._carrier_path.set(f'{p}  ({_fmt_size(os.path.getsize(p))})')
            self._update_savings_calculator()

    def _browse_hide_output(self):
        d = filedialog.askdirectory(title='Select output folder')
        if d:
            self._hide_output.set(d)

    def _browse_reveal_manifest(self):
        p = filedialog.askopenfilename(
            title='Select manifest.json',
            filetypes=[('JSON manifest', '*.json'), ('Any file', '*.*')])
        if p:
            self._reveal_manifest.set(p)

    def _browse_reveal_outdir(self):
        d = filedialog.askdirectory(title='Select output folder')
        if d:
            self._reveal_outdir.set(d)

    def _browse_inspect(self):
        p = filedialog.askopenfilename(title='Select carrier file', filetypes=ALL_MEDIA)
        if p:
            self._inspect_path.set(p)

    # ── HIDE action ───────────────────────────────────────────────────────────

    def _run_hide(self):
        if not self._secret_paths:
            messagebox.showwarning('GhostStore', 'Please select at least one secret file.')
            return
        output = self._hide_output.get().strip()
        if not output:
            messagebox.showwarning('GhostStore', 'Please choose an output folder.')
            return
        mode = self._hide_mode.get()
        if mode == 'blend':
            raw = self._carrier_path.get().strip()
            carrier = raw.split('  (')[0].strip() if '  (' in raw else raw
            if not carrier:
                messagebox.showwarning('GhostStore', 'Please select a carrier file.')
                return
            total_secret = sum(os.path.getsize(p) for p in self._secret_paths)
            ok, cap = self._check_capacity(carrier, total_secret)
            if not ok:
                if not messagebox.askyesno('Capacity Warning',
                    f'Carrier may be too small.\nSecret: {total_secret:,} bytes\n'
                    f'Capacity: {cap:,} bytes\nContinue anyway?'):
                    return
        else:
            carrier = None

        self._hide_status.config(text='⏳ Working…', fg=FG_DIM)
        self.update_idletasks()

        def worker():
            try:
                if mode == 'blend' and carrier:
                    ext = os.path.splitext(carrier)[1].lower()
                    if ext in {'.mp4','.mov','.avi','.wmv','.mkv','.m4v'}:
                        ctype = 'video'
                    elif ext in {'.wav','.mp3','.flac','.aac','.ogg','.m4a'}:
                        ctype = 'audio'
                    else:
                        ctype = 'image'
                else:
                    ctype = self._carrier_type.get()

                manifest = hide_v2(
                    secret_paths=self._secret_paths,
                    output_dir=output,
                    carrier_type=ctype,
                    user_carriers=[carrier] if mode == 'blend' and carrier else None,
                    notes=self._hide_label.get().strip(),
                )
                self.after(0, self._on_hide_success, manifest['key_hex'])
                self.after(0, self._vault_refresh)
            except Exception as exc:
                self.after(0, self._on_hide_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_hide_success(self, key_hex):
        label = self._hide_label.get().strip()
        self._last_key.set(key_hex)
        self._hide_label.set('')
        output = self._hide_output.get()
        self._hide_status.config(text=f'✅ Done! Output: {output}', fg='#44cc88')
        try:
            with open(output + '.key', 'w') as f:
                f.write(key_hex)
        except Exception:
            pass
        try:
            key_name = label if label else (
                os.path.basename(self._secret_paths[0]) if self._secret_paths else 'Unnamed key')
            save_key(key_name, key_hex)
            self.after(0, self._keys_refresh)
        except Exception:
            pass
        self.clipboard_clear()
        self.clipboard_append(key_hex)
        messagebox.showinfo('🔑 Encryption Key — Save This!',
            f'Your encryption key:\n\n{key_hex}\n\n'
            f'✅ Key also saved in the KEYS tab.\n\n'
            f'KEEP THIS SAFE — without it your files cannot be recovered.')

    def _on_hide_error(self, msg):
        self._hide_status.config(text=f'❌ Error: {msg}', fg=HIGHLIGHT)
        messagebox.showerror('GhostStore — Hide failed', msg)

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

    def _on_reveal_success(self, paths):
        self._reveal_listbox.delete(0, 'end')
        for p in paths:
            self._reveal_listbox.insert('end', p)
        n = len(paths)
        self._reveal_status.config(text=f'✅ Revealed {n} file{"s" if n!=1 else ""}!',
                                   fg='#44cc88')

    def _on_reveal_error(self, msg):
        self._reveal_status.config(text=f'❌ Error: {msg}', fg=HIGHLIGHT)
        messagebox.showerror('GhostStore — Reveal failed', msg)

    def _open_reveal_folder(self):
        d = self._reveal_outdir.get().strip()
        if d and os.path.isdir(d):
            os.startfile(d)

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
                self.after(0, self._set_inspect_text,
                           '\n'.join(f'{k}: {v}' for k, v in info.items()))
            except Exception as exc:
                self.after(0, self._set_inspect_text, f'Error: {exc}')

        threading.Thread(target=worker, daemon=True).start()

    def _set_inspect_text(self, text):
        self._inspect_result.config(state='normal')
        self._inspect_result.delete('1.0', 'end')
        self._inspect_result.insert('1.0', text)
        self._inspect_result.config(state='disabled')

    # ── VAULT actions ─────────────────────────────────────────────────────────

    def _vault_refresh(self):
        self._vault_listbox.delete(0, 'end')
        try:
            self._vault_records = list_all()
        except Exception as e:
            self._vault_status.config(text=f'❌ {e}', fg=HIGHLIGHT)
            return
        missing = 0
        for r in self._vault_records:
            size = _fmt_size(r['size_bytes'])
            display_name = r['notes'] if r['notes'] else r['filename']
            path_ok = os.path.isdir(r['storage_dir'])
            if not path_ok:
                missing += 1
            icon = '✅' if path_ok else '⚠️'
            line = f"{icon} {display_name:<28} {r['created'][:16]:<18} {size:<12} {r['chunk_count']:<8} {r['filename']}"
            self._vault_listbox.insert('end', line)
            if not path_ok:
                self._vault_listbox.itemconfig('end', fg=HIGHLIGHT)
        n = len(self._vault_records)
        if missing:
            self._vault_status.config(
                text=f'{n} record(s) in vault  •  ⚠️ {missing} carrier folder(s) not found.',
                fg='#e09030')
        else:
            self._vault_status.config(
                text=f'{n} record(s) in vault  •  all carrier folders found ✅', fg=FG_DIM)

    def _vault_import(self):
        path = filedialog.askopenfilename(
            title='Import manifest.json',
            filetypes=[('JSON manifest', '*.json'), ('Any file', '*.*')])
        if not path:
            return
        try:
            rebuild_from_manifest(path)
            self._vault_refresh()
            self._vault_status.config(text='✅ Manifest imported.', fg='#44cc88')
        except Exception as e:
            messagebox.showerror('Import failed', str(e))

    def _vault_delete(self):
        sel = self._vault_listbox.curselection()
        if not sel:
            messagebox.showwarning('GhostStore', 'Select a record to delete.')
            return
        record = self._vault_records[sel[0]]
        if not messagebox.askyesno('Delete record',
            f'Remove "{record["filename"]}" from vault?\nCarrier files will NOT be deleted.'):
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
                self.after(0, lambda: self._vault_status.config(
                    text=f'✅ Revealed {len(paths)} file(s)!', fg='#44cc88'))
                self.after(0, lambda: os.startfile(outdir))
            except Exception as e:
                self.after(0, lambda: self._vault_status.config(
                    text=f'❌ {e}', fg=HIGHLIGHT))

        threading.Thread(target=worker, daemon=True).start()

    # ── KEYS actions ──────────────────────────────────────────────────────────

    def _keys_refresh(self):
        self._keys_listbox.delete(0, 'end')
        try:
            self._keys_records = list_keys()
        except Exception as e:
            self._keys_status.config(text=f'❌ {e}', fg=HIGHLIGHT)
            return
        for r in self._keys_records:
            linked = r['notes'] if r['notes'] else (r['record_id'][:8]+'…' if r['record_id'] else '—')
            self._keys_listbox.insert('end',
                f"{r['name']:<28} {r['created'][:16]:<18} {r['key_preview']:<18} {linked}")
        n = len(self._keys_records)
        self._keys_status.config(text=f'{n} key{"s" if n!=1 else ""} stored', fg=FG_DIM)

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
                messagebox.showerror('GhostStore', 'Key not found.')
                return
            self.clipboard_clear()
            self.clipboard_append(key_hex)
            self._keys_status.config(text=f'✅ Key "{rec["name"]}" copied.', fg='#44cc88')
        except Exception as e:
            messagebox.showerror('Copy failed', str(e))

    def _keys_rename(self):
        rec = self._keys_selected()
        if not rec:
            return
        import tkinter.simpledialog as sd
        new_name = sd.askstring('Rename Key', f'New name for:\n"{rec["name"]}"',
                                initialvalue=rec['name'], parent=self)
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = GhostStoreApp()
    app.mainloop()
