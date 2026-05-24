import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os, sys, shutil, subprocess, configparser, traceback
import datetime, threading, re, json, socket

# ── resource path ─────────────────────────────────────────────────────────────
def resource_path(relative):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

# ── constants ─────────────────────────────────────────────────────────────────
INI_REL       = os.path.join("src", "system", "scripts", "SplinterCellConviction.FusionFix.ini")
EXE_REL       = os.path.join("src", "system", "scc_lan_helper.exe")
SRC_DIR       = resource_path("src")
LOG_FILE_NAME = "SCC_Launcher_debug.log"
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".scc_launcher_settings.json")

# ── settings ──────────────────────────────────────────────────────────────────
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                return json.load(f)
        except: pass
    return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except: pass

# ── logging ───────────────────────────────────────────────────────────────────
def get_log_file(game_dir=None):
    if game_dir and os.path.isdir(game_dir):
        return os.path.join(game_dir, LOG_FILE_NAME)
    return os.path.join(os.path.expanduser("~"), LOG_FILE_NAME)

def log(msg, error=False, game_dir=None):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "ERROR" if error else "INFO"
    try:
        with open(get_log_file(game_dir), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{prefix}] {msg}\n")
    except: pass

def log_exc(context, exc, game_dir=None):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb = traceback.format_exc()
    try:
        with open(get_log_file(game_dir), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [ERROR] {context}: {exc}\n{tb}\n")
    except: pass

# ── ini ───────────────────────────────────────────────────────────────────────
_cc = set()
def _convert(path):
    if path in _cc: return
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            c = f.read()
        if "//" not in c: _cc.add(path); return
        nc = re.sub(r"^(\s*)//", r"\1#", c, flags=re.MULTILINE)
        if nc != c:
            with open(path, "w", encoding="utf-8") as f:
                f.write(nc)
        _cc.add(path)
    except: pass

def get_ini(d): return os.path.join(d, INI_REL)
def get_exe(d): return os.path.join(d, EXE_REL)

def read_ip(d):
    p = get_ini(d)
    if not os.path.exists(p): return ""
    _convert(p)
    cfg = configparser.ConfigParser()
    cfg.read(p, encoding="utf-8")
    return cfg.get("LAN", "ServerAddr", fallback="")

def write_ip(d, ip):
    p = get_ini(d)
    _convert(p)
    cfg = configparser.ConfigParser()
    cfg.read(p, encoding="utf-8")
    if not cfg.has_section("LAN"): cfg.add_section("LAN")
    cfg.set("LAN", "ServerAddr", ip)
    with open(p, "w", encoding="utf-8") as f:
        cfg.write(f)

# ── file ops ──────────────────────────────────────────────────────────────────
def copy_src(dest):
    shutil.copytree(SRC_DIR, os.path.join(dest, "src"), dirs_exist_ok=True)

def copy_dlc(src, dest):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dest, item)
        if os.path.isdir(s): shutil.copytree(s, d, dirs_exist_ok=True)
        else: shutil.copy2(s, d)

# ── shortcuts ─────────────────────────────────────────────────────────────────
def make_shortcuts(target, types, name):
    if sys.platform == "win32":
        for t in types:
            try:
                if t == "desktop":
                    dest = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.lnk")
                elif t == "startmenu":
                    dest = os.path.join(os.environ.get("APPDATA",""), "Microsoft","Windows","Start Menu","Programs", f"{name}.lnk")
                else: continue
                ps = f'$ws=New-Object -ComObject WScript.Shell;$s=$ws.CreateShortcut(\'{dest}\');$s.TargetPath=\'{target}\';$s.WorkingDirectory=\'{os.path.dirname(target)}\';$s.Save()'
                subprocess.Popen(["powershell","-Command",ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass
    else:
        entry = f"[Desktop Entry]\nName={name}\nExec=\"{target}\"\nType=Application\nTerminal=false\nCategories=Game;\n"
        for t in types:
            try:
                if t == "desktop": dest = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.desktop")
                elif t == "startmenu": dest = os.path.join(os.path.expanduser("~"), ".local","share","applications", f"{name}.desktop")
                else: continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest,"w") as f: f.write(entry)
                os.chmod(dest, 0o755)
            except: pass

# ── network ───────────────────────────────────────────────────────────────────
def get_ips():
    ips, seen = [], set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None):
            ip = item[4][0]
            if ip not in seen and not ip.startswith("127.") and ":" not in ip:
                seen.add(ip)
                if ip.startswith("25."): lbl = f"Hamachi ({ip})"
                elif ip.startswith("100."): lbl = f"ZeroTier/Tailscale ({ip})"
                elif ip.startswith("10."): lbl = f"VPN/LAN ({ip})"
                elif ip.startswith("192.168."): lbl = f"Local Network ({ip})"
                elif ip.startswith("172."): lbl = f"Private Network ({ip})"
                else: lbl = f"Network ({ip})"
                ips.append((lbl, ip))
    except: pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1); s.connect(("8.8.8.8",80))
        ip = s.getsockname()[0]; s.close()
        if ip and ip not in seen:
            ips.append((f"Primary ({ip})", ip))
    except: pass
    return ips

# ── right-click menu ──────────────────────────────────────────────────────────
def ctx_menu(widget):
    m = tk.Menu(widget, tearoff=0, bg="#0f0f12", fg="#F0EEE8",
                activebackground="#E8722A", activeforeground="#060608",
                font=("Courier New", 9), relief="flat")
    m.add_command(label="Cut",        command=lambda: widget.event_generate("<<Cut>>"))
    m.add_command(label="Copy",       command=lambda: widget.event_generate("<<Copy>>"))
    m.add_command(label="Paste",      command=lambda: widget.event_generate("<<Paste>>"))
    m.add_separator()
    m.add_command(label="Select All", command=lambda: (widget.select_range(0,"end"), widget.icursor("end")))
    widget.bind("<Button-3>", lambda e: m.tk_popup(e.x_root, e.y_root))

# ── theme ─────────────────────────────────────────────────────────────────────
BG      = "#060608"
BG2     = "#0a0a0f"
PANEL   = "#0d0d12"
BORDER  = "#1a1a24"
ORANGE  = "#E8722A"
ORANGE2 = "#a04d18"
ORANGE3 = "#2a1008"
WHITE   = "#F0EEE8"
DIM     = "#3a3a40"
DIM2    = "#14141a"
GREEN   = "#4aff91"
RED     = "#ff4a4a"
BLUE    = "#4a9fff"

FT      = ("Courier New", 9)
FT_SM   = ("Courier New", 8)
FT_XS   = ("Courier New", 7)
FT_LG   = ("Courier New", 11, "bold")
FT_TIT  = ("Courier New", 13, "bold")
FT_HED  = ("Courier New", 9, "bold")

# ══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SCC LAN Launcher")
        self.configure(bg=BG)
        self.minsize(520, 400)

        self.settings = load_settings()
        self.gd = self.settings.get("game_dir", "")
        self.setup_done = self.settings.get("setup_done", False)
        if self.gd and not os.path.isdir(self.gd): self.gd = ""; self.setup_done = False

        log("Launcher started.", game_dir=self.gd or None)
        self._build()
        if self.setup_done and self.gd:
            self._show("main")
        else:
            self._show("s0")

    def _save(self):
        self.settings["game_dir"] = self.gd
        self.settings["setup_done"] = self.setup_done
        save_settings(self.settings)

    # ── widget helpers ────────────────────────────────────────────────────────
    def _lbl(self, p, text, fg=WHITE, font=FT, bg=None, **kw):
        return tk.Label(p, text=text, fg=fg, font=font, bg=bg or BG, **kw)

    def _btn(self, p, text, cmd, fg=ORANGE, bg=ORANGE3, font=FT_HED, **kw):
        b = tk.Button(p, text=text, command=cmd, fg=fg, bg=bg,
                      activeforeground=BG, activebackground=fg,
                      font=font, relief="flat", bd=0, cursor="hand2",
                      padx=12, pady=6, **kw)
        return b

    def _entry(self, p, var, w=24, fg=ORANGE, font=("Courier New",13,"bold")):
        e = tk.Entry(p, textvariable=var, fg=fg, bg=BG2,
                     insertbackground=ORANGE, font=font,
                     relief="flat", bd=0, width=w,
                     highlightthickness=1,
                     highlightbackground=ORANGE2,
                     highlightcolor=ORANGE)
        ctx_menu(e)
        return e

    def _sep(self, p):
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", padx=20, pady=10)

    def _sec(self, p, text):
        tk.Label(p, text=text, fg=DIM, font=FT_XS, bg=BG,
                 anchor="w").pack(fill="x", padx=20, pady=(10,2))

    def _panel(self, p, pady=(2,4)):
        outer = tk.Frame(p, bg=ORANGE2)
        outer.pack(fill="x", padx=20, pady=pady)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="x", padx=1, pady=1)
        return inner

    def _status(self, p):
        v = tk.StringVar()
        lbl = tk.Label(p, textvariable=v, font=FT_XS, bg=BG, fg=DIM, anchor="w")
        lbl.pack(fill="x", padx=20, pady=(2,0))
        return v, lbl

    def _ok(self, v, lbl, msg):
        v.set(f"✔  {msg}"); lbl.config(fg=GREEN)
    def _err(self, v, lbl, msg):
        v.set(f"✘  {msg}"); lbl.config(fg=RED)
    def _warn(self, v, lbl, msg):
        v.set(f"⚠  {msg}"); lbl.config(fg=ORANGE)

    # ── show/hide screens ─────────────────────────────────────────────────────
    def _show(self, name):
        for f in self._screens.values():
            f.pack_forget()
        self._screens[name].pack(fill="both", expand=True)

    # ── BUILD ALL SCREENS ─────────────────────────────────────────────────────
    def _build(self):
        # header
        hdr = tk.Frame(self, bg=BG2)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ORANGE, height=2).pack(fill="x")
        hdr2 = tk.Frame(hdr, bg=BG2)
        hdr2.pack(fill="x", padx=16, pady=6)
        tk.Label(hdr2, text="TOM CLANCY'S", fg=DIM, bg=BG2,
                 font=FT_XS).pack(side="left", padx=(0,6))
        tk.Label(hdr2, text="SPLINTER CELL: CONVICTION",
                 fg=ORANGE, bg=BG2, font=FT_HED).pack(side="left")
        self._hdr_right = tk.Label(hdr2, text="LAN LAUNCHER",
                                   fg=DIM, bg=BG2, font=FT_XS)
        self._hdr_right.pack(side="right")
        tk.Frame(hdr, bg=ORANGE2, height=1).pack(fill="x")

        self._screens = {}
        self._screens["s0"] = self._build_s0()
        self._screens["s1"] = self._build_s1()
        self._screens["s2"] = self._build_s2()
        self._screens["s3"] = self._build_s3()
        self._screens["s4"] = self._build_s4()
        self._screens["s5"] = self._build_s5()
        self._screens["main"] = self._build_main()

    def _progress(self, p, current, total=6):
        row = tk.Frame(p, bg=BG)
        row.pack(pady=(12,4))
        for i in range(total):
            if i < current:
                tk.Label(row, text="◆", fg=ORANGE, bg=BG, font=FT_XS).pack(side="left", padx=3)
            elif i == current:
                tk.Label(row, text="◇", fg=ORANGE, bg=BG, font=FT_XS).pack(side="left", padx=3)
            else:
                tk.Label(row, text="◇", fg=DIM, bg=BG, font=FT_XS).pack(side="left", padx=3)

    # ── S0: WELCOME ───────────────────────────────────────────────────────────
    def _build_s0(self):
        f = tk.Frame(self, bg=BG)
        self._progress(f, 0)

        # Eye canvas
        c = tk.Canvas(f, width=320, height=100, bg=BG, highlightthickness=0)
        c.pack(pady=(4,0))
        c.create_oval(40,30,280,70, outline=ORANGE, width=2)
        c.create_oval(70,35,250,65, outline=ORANGE2, width=1)
        c.create_oval(140,20,180,80, outline=ORANGE, width=2)
        c.create_oval(152,32,168,68, fill=ORANGE, outline="")
        c.create_oval(156,40,164,60, fill=BG, outline="")
        c.create_line(40,50,140,50, fill=ORANGE2, width=1)
        c.create_line(180,50,280,50, fill=ORANGE2, width=1)
        # corner brackets
        for x1,y1,x2,y2,x3,y3 in [(0,20,0,0,20,0),(300,0,320,0,320,20),(0,80,0,100,20,100),(300,100,320,100,320,80)]:
            c.create_line(x1,y1,x2,y2,x3,y3, fill=ORANGE2, width=1)
        c.create_text(160,50, text="[ LAST KNOWN POSITION ]", fill=ORANGE3, font=FT_XS)

        tk.Label(f, text="SCC  LAN  LAUNCHER", fg=ORANGE, bg=BG,
                 font=("Courier New", 20, "bold")).pack(pady=(10,2))
        tk.Label(f, text="FOURTH ECHELON  ·  NETWORK CONFIGURATION SYSTEM",
                 fg=DIM, bg=BG, font=FT_XS).pack()

        self._sep(f)

        tk.Label(f, text="This utility configures your LAN connection\nfor Splinter Cell: Conviction FusionFix.\n\nComplete each step to initialize the system.",
                 fg=DIM, bg=BG, font=FT, justify="center").pack(pady=8)

        self._btn(f, "▶  INITIALIZE SETUP",
                  lambda: [self._hdr_right.config(text="SETUP  1/5"), self._show("s1")],
                  font=FT_LG).pack(pady=(8,20))
        return f

    # ── S1: DIRECTORY ─────────────────────────────────────────────────────────
    def _build_s1(self):
        f = tk.Frame(self, bg=BG)
        self._progress(f, 1)
        tk.Label(f, text="GAME DIRECTORY", fg=ORANGE, bg=BG, font=FT_TIT).pack(anchor="w", padx=20, pady=(8,2))
        tk.Label(f, text="Select the root folder of your game installation.\nDo NOT select the src/ subfolder.",
                 fg=DIM, bg=BG, font=FT_XS, justify="left").pack(anchor="w", padx=20)

        self._sec(f, "CURRENT PATH")
        panel = self._panel(f)
        self._s1_path = tk.StringVar(value=self.gd or "No directory selected")
        tk.Label(panel, textvariable=self._s1_path, fg=WHITE if self.gd else DIM,
                 bg=PANEL, font=FT, wraplength=440, anchor="w",
                 justify="left").pack(fill="x", padx=12, pady=8)

        s1v, s1l = self._status(f)

        def browse():
            d = filedialog.askdirectory(title="Select Game Directory")
            if not d: return
            if os.path.basename(d).lower() == "src":
                self._warn(s1v, s1l, "Please select the main game folder, not src/")
                return
            self.gd = d; self._s1_path.set(d); self._save()
            log(f"Game directory set: {d}", game_dir=d)
            self._ok(s1v, s1l, "Directory set.")

        row = tk.Frame(f, bg=BG)
        row.pack(anchor="w", padx=20, pady=(8,0))
        self._btn(row, "📁  BROWSE", browse).pack(side="left")

        self._sep(f)
        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,16))
        self._btn(nav, "◀  BACK", lambda: self._show("s0"), fg=DIM, bg=DIM2).pack(side="left")

        def nxt():
            if not self.gd:
                self._warn(s1v, s1l, "Please select a game directory first."); return
            self._hdr_right.config(text="SETUP  2/5")
            self._show("s2")

        self._btn(nav, "NEXT  ▶", nxt).pack(side="right")
        return f

    # ── S2: DLC ───────────────────────────────────────────────────────────────
    def _build_s2(self):
        f = tk.Frame(self, bg=BG)
        self._progress(f, 2)
        tk.Label(f, text="OPTIONAL DLC", fg=ORANGE, bg=BG, font=FT_TIT).pack(anchor="w", padx=20, pady=(8,2))
        tk.Label(f, text="Install the Insurgency Pack DLC before copying main files.\nExtract the DLC .zip first, then select the extracted folder.\nYou can skip this and install DLC later.",
                 fg=DIM, bg=BG, font=FT_XS, justify="left").pack(anchor="w", padx=20)

        s2v, s2l = self._status(f)
        dlc_btn = [None]

        def install():
            d = filedialog.askdirectory(title="Select Extracted Insurgency Pack DLC Folder")
            if not d: return
            dlc_btn[0].config(state="disabled", text="Installing...")
            self._warn(s2v, s2l, "Copying DLC files...")
            def _do():
                try:
                    log(f"Installing DLC: {d}", game_dir=self.gd)
                    copy_dlc(d, self.gd)
                    log("DLC installed.", game_dir=self.gd)
                    f.after(0, lambda: (dlc_btn[0].config(state="normal", text="📦  INSTALL INSURGENCY PACK DLC"), self._ok(s2v, s2l, "DLC installed.")))
                except Exception as e:
                    log_exc("DLC failed", e, self.gd)
                    f.after(0, lambda: (dlc_btn[0].config(state="normal", text="📦  INSTALL INSURGENCY PACK DLC"), self._err(s2v, s2l, str(e))))
            threading.Thread(target=_do, daemon=True).start()

        row = tk.Frame(f, bg=BG)
        row.pack(anchor="w", padx=20, pady=(12,0))
        b = self._btn(row, "📦  INSTALL INSURGENCY PACK DLC", install, fg=BLUE, bg=DIM2)
        b.pack(side="left"); dlc_btn[0] = b

        self._sep(f)
        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,16))
        self._btn(nav, "◀  BACK", lambda: self._show("s1"), fg=DIM, bg=DIM2).pack(side="left")
        nxt = lambda: [self._hdr_right.config(text="SETUP  3/5"), self._show("s3")]
        self._btn(nav, "SKIP  ▶", nxt, fg=DIM, bg=DIM2).pack(side="right", padx=(0,8))
        self._btn(nav, "NEXT  ▶", nxt).pack(side="right")
        return f

    # ── S3: INSTALL ───────────────────────────────────────────────────────────
    def _build_s3(self):
        f = tk.Frame(self, bg=BG)
        self._progress(f, 3)
        tk.Label(f, text="INSTALL FILES", fg=ORANGE, bg=BG, font=FT_TIT).pack(anchor="w", padx=20, pady=(8,2))
        tk.Label(f, text="Copy all required files into your game directory.",
                 fg=DIM, bg=BG, font=FT_XS, justify="left").pack(anchor="w", padx=20)

        s3v, s3l = self._status(f)
        installed = [False]
        inst_btn = [None]
        nxt_btn  = [None]

        def install():
            inst_btn[0].config(state="disabled", text="Copying files...")
            self._warn(s3v, s3l, "Copying files, please wait...")
            def _do():
                try:
                    log(f"Installing to: {self.gd}", game_dir=self.gd)
                    copy_src(self.gd)
                    log("Files copied.", game_dir=self.gd)
                    installed[0] = True
                    f.after(0, lambda: (
                        inst_btn[0].config(state="normal", text="▶  INSTALL FILES"),
                        nxt_btn[0].config(state="normal"),
                        self._ok(s3v, s3l, "Files installed successfully.")))
                except Exception as e:
                    log_exc("Install failed", e, self.gd)
                    f.after(0, lambda: (
                        inst_btn[0].config(state="normal", text="▶  INSTALL FILES"),
                        self._err(s3v, s3l, str(e))))
            threading.Thread(target=_do, daemon=True).start()

        row = tk.Frame(f, bg=BG)
        row.pack(anchor="w", padx=20, pady=(12,0))
        ib = self._btn(row, "▶  INSTALL FILES", install, font=FT_LG)
        ib.pack(); inst_btn[0] = ib

        self._sep(f)
        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,16))
        self._btn(nav, "◀  BACK", lambda: self._show("s2"), fg=DIM, bg=DIM2).pack(side="left")

        def nxt():
            if not installed[0]:
                self._warn(s3v, s3l, "Please install files first."); return
            self._hdr_right.config(text="SETUP  4/5"); self._show("s4")
            self._load_ip_s4()

        nb = self._btn(nav, "NEXT  ▶", nxt)
        nb.config(state="disabled"); nb.pack(side="right"); nxt_btn[0] = nb
        return f

    # ── S4: IP ────────────────────────────────────────────────────────────────
    def _build_s4(self):
        f = tk.Frame(self, bg=BG)
        self._progress(f, 4)
        tk.Label(f, text="SERVER ADDRESS", fg=ORANGE, bg=BG, font=FT_TIT).pack(anchor="w", padx=20, pady=(8,2))
        tk.Label(f, text="Set the ServerAddr for LAN play.\nPick a detected interface or enter manually.",
                 fg=DIM, bg=BG, font=FT_XS, justify="left").pack(anchor="w", padx=20)

        self._sec(f, "DETECTED INTERFACES")
        np = self._panel(f)
        nr = tk.Frame(np, bg=PANEL)
        nr.pack(fill="x", padx=8, pady=8)
        self._s4_net = tk.StringVar(value="Scanning...")
        self._s4_map = {}
        self._s4_dd = ttk.Combobox(nr, textvariable=self._s4_net, font=FT, state="readonly", width=36)
        self._s4_dd.pack(side="left", fill="x", expand=True)

        def use_net():
            ip = self._s4_map.get(self._s4_net.get())
            if ip: self._s4_ip.set(ip); self._ok(s4v, s4l, "IP set from interface.")
        self._btn(nr, "USE", use_net).pack(side="left", padx=(8,0))

        self._sec(f, "MANUAL ENTRY")
        ip_panel = self._panel(f)
        ir = tk.Frame(ip_panel, bg=PANEL)
        ir.pack(fill="x", padx=8, pady=8)
        tk.Label(ir, text="ServerAddr :", fg=DIM, bg=PANEL, font=FT).pack(side="left")
        self._s4_ip = tk.StringVar()
        self._entry(ip_panel if False else ir, self._s4_ip).pack(side="left", padx=(8,0), ipady=4, ipadx=4)

        s4v, s4l = self._status(f)

        def save():
            ip = self._s4_ip.get().strip()
            if not ip: self._warn(s4v, s4l, "Enter an IP address."); return
            def _do():
                try:
                    write_ip(self.gd, ip)
                    log(f"Saved ServerAddr = {ip}", game_dir=self.gd)
                    f.after(0, lambda: self._ok(s4v, s4l, f"Saved  ServerAddr = {ip}"))
                except Exception as e:
                    log_exc("Save IP", e, self.gd)
                    f.after(0, lambda: self._err(s4v, s4l, str(e)))
            threading.Thread(target=_do, daemon=True).start()

        row = tk.Frame(f, bg=BG)
        row.pack(anchor="w", padx=20, pady=(8,0))
        self._btn(row, "💾  SAVE IP", save).pack(side="left")

        self._sep(f)
        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,16))
        self._btn(nav, "◀  BACK", lambda: self._show("s3"), fg=DIM, bg=DIM2).pack(side="left")
        self._btn(nav, "NEXT  ▶", lambda: [self._hdr_right.config(text="SETUP  5/5"), self._show("s5")]).pack(side="right")
        return f

    def _load_ip_s4(self):
        def _do():
            try:
                ip = read_ip(self.gd)
                self.after(0, lambda: self._s4_ip.set(ip))
            except: pass
        threading.Thread(target=_do, daemon=True).start()
        self._scan_nets_s4()

    def _scan_nets_s4(self):
        def _do():
            ips = get_ips()
            def _upd():
                self._s4_map = {lbl: ip for lbl, ip in ips}
                if ips:
                    self._s4_dd.config(values=[lbl for lbl,_ in ips])
                    self._s4_net.set(ips[0][0])
                else:
                    self._s4_dd.config(values=["No interfaces detected"])
                    self._s4_net.set("No interfaces detected")
            self.after(0, _upd)
        threading.Thread(target=_do, daemon=True).start()

    # ── S5: SHORTCUTS ─────────────────────────────────────────────────────────
    def _build_s5(self):
        f = tk.Frame(self, bg=BG)
        self._progress(f, 5)
        tk.Label(f, text="CREATE SHORTCUTS", fg=ORANGE, bg=BG, font=FT_TIT).pack(anchor="w", padx=20, pady=(8,2))
        tk.Label(f, text="Optionally create shortcuts. The launcher stays wherever you saved it.",
                 fg=DIM, bg=BG, font=FT_XS).pack(anchor="w", padx=20)

        self._sec(f, "SHORTCUT LOCATION")
        lp = self._panel(f)
        self._s5_desk = tk.BooleanVar(value=True)
        self._s5_start = tk.BooleanVar(value=False)
        for txt, var in [("Desktop", self._s5_desk), ("Start Menu / App Launcher", self._s5_start)]:
            row = tk.Frame(lp, bg=PANEL)
            row.pack(fill="x", padx=12, pady=3)
            tk.Checkbutton(row, text=txt, variable=var, fg=WHITE, bg=PANEL,
                           selectcolor=BG2, activebackground=PANEL,
                           activeforeground=ORANGE, font=FT,
                           relief="flat").pack(side="left")

        self._sec(f, "CREATE SHORTCUT FOR")
        wp = self._panel(f)
        self._s5_launcher = tk.BooleanVar(value=True)
        self._s5_helper   = tk.BooleanVar(value=True)
        for txt, var in [("SCC LAN Launcher  (this app)", self._s5_launcher),
                         ("SCC LAN Helper  (game helper exe)", self._s5_helper)]:
            row = tk.Frame(wp, bg=PANEL)
            row.pack(fill="x", padx=12, pady=3)
            tk.Checkbutton(row, text=txt, variable=var, fg=WHITE, bg=PANEL,
                           selectcolor=BG2, activebackground=PANEL,
                           activeforeground=ORANGE, font=FT,
                           relief="flat").pack(side="left")

        s5v, s5l = self._status(f)

        def finish():
            types = []
            if self._s5_desk.get():  types.append("desktop")
            if self._s5_start.get(): types.append("startmenu")
            launcher = sys.executable if getattr(sys,"frozen",False) else os.path.abspath(__file__)
            helper   = get_exe(self.gd)
            if self._s5_launcher.get() and types:
                threading.Thread(target=make_shortcuts, args=(launcher, types, "SCC LAN Launcher"), daemon=True).start()
            if self._s5_helper.get() and types:
                threading.Thread(target=make_shortcuts, args=(helper, types, "SCC LAN Helper"), daemon=True).start()
            self.setup_done = True; self._save()
            self._hdr_right.config(text="LAN LAUNCHER")
            self._show("main")
            self._load_main()

        self._sep(f)
        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,16))
        self._btn(nav, "◀  BACK", lambda: self._show("s4"), fg=DIM, bg=DIM2).pack(side="left")
        self._btn(nav, "✔  FINISH", finish, fg=GREEN, bg="#0a1f0a", font=FT_LG).pack(side="right")
        return f

    # ── MAIN ──────────────────────────────────────────────────────────────────
    def _build_main(self):
        f = tk.Frame(self, bg=BG)

        # scrollable container
        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0,0), window=inner, anchor="nw")

        def _resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # title row
        tr = tk.Frame(inner, bg=BG)
        tr.pack(fill="x", padx=20, pady=(12,0))
        tk.Label(tr, text="SCC  LAN  LAUNCHER", fg=ORANGE, bg=BG,
                 font=("Courier New", 16, "bold")).pack(side="left")
        tk.Label(tr, text="[ ONLINE ]", fg=GREEN, bg=BG, font=FT_XS).pack(side="right", pady=(6,0))

        # dir display
        self._sec(inner, "GAME DIRECTORY")
        dp = self._panel(inner)
        self._main_dir = tk.StringVar(value=self.gd or "Not set")
        tk.Label(dp, textvariable=self._main_dir, fg=WHITE, bg=PANEL,
                 font=FT, wraplength=440, anchor="w", justify="left").pack(fill="x", padx=12, pady=8)

        self._sep(inner)

        # IP
        self._sec(inner, "SERVER ADDRESS")
        np = self._panel(inner)
        nr = tk.Frame(np, bg=PANEL)
        nr.pack(fill="x", padx=8, pady=(8,4))
        tk.Label(nr, text="INTERFACE :", fg=DIM, bg=PANEL, font=FT_XS).pack(side="left")
        self._main_net = tk.StringVar(value="Scanning...")
        self._main_map = {}
        self._main_dd = ttk.Combobox(nr, textvariable=self._main_net, font=FT, state="readonly", width=30)
        self._main_dd.pack(side="left", padx=(6,6), fill="x", expand=True)

        def use_main_net():
            ip = self._main_map.get(self._main_net.get())
            if ip: self._main_ip.set(ip); self._ok(mipv, mipl, "IP set from interface.")
        self._btn(nr, "USE", use_main_net).pack(side="left")

        ir = tk.Frame(np, bg=PANEL)
        ir.pack(fill="x", padx=8, pady=(0,8))
        tk.Label(ir, text="ServerAddr :", fg=DIM, bg=PANEL, font=FT).pack(side="left")
        self._main_ip = tk.StringVar()
        self._entry(ir, self._main_ip).pack(side="left", padx=(8,8), ipady=4, ipadx=4)

        mipv, mipl = self._status(inner)

        def save_main():
            ip = self._main_ip.get().strip()
            if not ip: self._warn(mipv, mipl, "Enter an IP address."); return
            def _do():
                try:
                    write_ip(self.gd, ip)
                    log(f"Saved ServerAddr = {ip}", game_dir=self.gd)
                    inner.after(0, lambda: self._ok(mipv, mipl, f"Saved  ServerAddr = {ip}"))
                except Exception as e:
                    log_exc("Save IP", e, self.gd)
                    inner.after(0, lambda: self._err(mipv, mipl, str(e)))
            threading.Thread(target=_do, daemon=True).start()

        row = tk.Frame(inner, bg=BG)
        row.pack(anchor="w", padx=20, pady=(6,0))
        self._btn(row, "💾  SAVE", save_main).pack(side="left")

        self._sep(inner)

        # launch
        self._sec(inner, "LAUNCH")
        lv, ll = self._status(inner)

        def launch():
            exe = get_exe(self.gd)
            if not os.path.exists(exe):
                self._err(lv, ll, "EXE not found. Reinstall files first."); return
            try:
                log(f"Launching: {exe}", game_dir=self.gd)
                subprocess.Popen([exe], cwd=os.path.dirname(exe))
                self._ok(lv, ll, "Launched successfully.")
            except Exception as e:
                log_exc("Launch", e, self.gd)
                self._err(lv, ll, str(e))

        self._btn(inner, "⬛  LAUNCH SCC LAN HELPER", launch,
                  fg=GREEN, bg="#0a1f0a", font=FT_LG).pack(fill="x", padx=20)
        lv.set(""); ll.pack(fill="x", padx=20, pady=(2,0))

        self._sep(inner)

        # actions
        self._sec(inner, "ACTIONS")
        av, al = self._status(inner)
        inst_btn = [None]; dlc_btn = [None]

        def reinstall():
            inst_btn[0].config(state="disabled", text="Copying...")
            self._warn(av, al, "Copying files...")
            def _do():
                try:
                    log(f"Reinstalling to: {self.gd}", game_dir=self.gd)
                    copy_src(self.gd)
                    log("Reinstalled.", game_dir=self.gd)
                    inner.after(0, lambda: (inst_btn[0].config(state="normal", text="▶  REINSTALL FILES"), self._ok(av, al, "Files reinstalled.")))
                except Exception as e:
                    log_exc("Reinstall", e, self.gd)
                    inner.after(0, lambda: (inst_btn[0].config(state="normal", text="▶  REINSTALL FILES"), self._err(av, al, str(e))))
            threading.Thread(target=_do, daemon=True).start()

        def install_dlc():
            d = filedialog.askdirectory(title="Select Extracted DLC Folder")
            if not d: return
            dlc_btn[0].config(state="disabled", text="Installing...")
            self._warn(av, al, "Copying DLC...")
            def _do():
                try:
                    log(f"DLC from: {d}", game_dir=self.gd)
                    copy_dlc(d, self.gd)
                    log("DLC installed.", game_dir=self.gd)
                    inner.after(0, lambda: (dlc_btn[0].config(state="normal", text="📦  INSTALL DLC"), self._ok(av, al, "DLC installed.")))
                except Exception as e:
                    log_exc("DLC", e, self.gd)
                    inner.after(0, lambda: (dlc_btn[0].config(state="normal", text="📦  INSTALL DLC"), self._err(av, al, str(e))))
            threading.Thread(target=_do, daemon=True).start()

        ar = tk.Frame(inner, bg=BG)
        ar.pack(fill="x", padx=20, pady=(4,0))
        ib = self._btn(ar, "▶  REINSTALL FILES", reinstall)
        ib.pack(side="left"); inst_btn[0] = ib
        db = self._btn(ar, "📦  INSTALL DLC", install_dlc, fg=BLUE, bg=DIM2)
        db.pack(side="left", padx=(8,0)); dlc_btn[0] = db

        self._sep(inner)

        # settings
        self._sec(inner, "SETTINGS")

        def reconfigure():
            if not messagebox.askyesno("Reconfigure", "Change the game directory?\nThis will restart the setup wizard."): return
            also = messagebox.askyesno("Reset?", "Also clear saved IP and reinstall flag?")
            log("Reconfigure triggered.", game_dir=self.gd)
            self.setup_done = False
            if also: self.gd = ""
            self._save(); self._show("s1")

        def reset_all():
            if not messagebox.askyesno("Reset", "Reset all settings and return to setup?"): return
            also = messagebox.askyesno("Clear dir?", "Also clear the game directory path?")
            log("Full reset triggered.", game_dir=self.gd)
            self.setup_done = False
            if also: self.gd = ""
            self._save(); self._show("s0")

        sr = tk.Frame(inner, bg=BG)
        sr.pack(fill="x", padx=20, pady=(4,0))
        self._btn(sr, "⟳  RECONFIGURE PATH", reconfigure, fg=DIM, bg=DIM2).pack(side="left")
        self._btn(sr, "↺  RESET SETTINGS", reset_all, fg=RED, bg=DIM2).pack(side="left", padx=(8,0))

        self._sep(inner)

        # debug log
        self._sec(inner, "DEBUG LOG")
        self._main_logpath = tk.Label(inner, text="", fg=DIM, bg=BG, font=FT_XS, anchor="w")
        self._main_logpath.pack(fill="x", padx=20, pady=(0,4))

        lgv, lgl = self._status(inner)

        def copy_log():
            lp = get_log_file(self.gd)
            if not os.path.exists(lp): self._warn(lgv, lgl, "No log file yet."); return
            try:
                with open(lp, "r", encoding="utf-8") as lf: cnt = lf.read()
                self.clipboard_clear(); self.clipboard_append(cnt)
                self._ok(lgv, lgl, "Log copied to clipboard.")
            except Exception as e:
                self._err(lgv, lgl, str(e))

        def clear_log():
            lp = get_log_file(self.gd)
            if not os.path.exists(lp): self._warn(lgv, lgl, "No log to clear."); return
            if messagebox.askyesno("Clear Log", "Delete the debug log?"):
                try: os.remove(lp); self._ok(lgv, lgl, "Log cleared.")
                except Exception as e: self._err(lgv, lgl, str(e))

        logr = tk.Frame(inner, bg=BG)
        logr.pack(fill="x", padx=20, pady=(0,20))
        self._btn(logr, "📋  COPY LOG", copy_log).pack(side="left")
        self._btn(logr, "🗑  CLEAR LOG", clear_log, fg=RED, bg=DIM2).pack(side="left", padx=(8,0))

        # store refs for _load_main
        self._main_inner = inner
        self._main_mipv = mipv; self._main_mipl = mipl
        self._main_lv = lv; self._main_ll = ll

        return f

    def _load_main(self):
        self._main_dir.set(self.gd or "Not set")
        self._main_logpath.config(text=f"Log: {get_log_file(self.gd)}")
        def _load_ip():
            try:
                ip = read_ip(self.gd)
                self.after(0, lambda: self._main_ip.set(ip))
            except: pass
        threading.Thread(target=_load_ip, daemon=True).start()
        self._scan_nets_main()

    def _scan_nets_main(self):
        def _do():
            ips = get_ips()
            def _upd():
                self._main_map = {lbl: ip for lbl, ip in ips}
                if ips:
                    self._main_dd.config(values=[lbl for lbl,_ in ips])
                    self._main_net.set(ips[0][0])
                else:
                    self._main_dd.config(values=["No interfaces detected"])
                    self._main_net.set("No interfaces detected")
            self.after(0, _upd)
        threading.Thread(target=_do, daemon=True).start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
