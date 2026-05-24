import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os, sys, shutil, subprocess, configparser, traceback, datetime, socket
import threading, time, re, json
import struct

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
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

# ── logging ───────────────────────────────────────────────────────────────────
def get_log_file(game_dir=None):
    if game_dir and os.path.isdir(game_dir):
        return os.path.join(game_dir, LOG_FILE_NAME)
    return os.path.join(os.path.expanduser("~"), LOG_FILE_NAME)

def log(message, error=False, game_dir=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "ERROR" if error else "INFO"
    line = f"[{timestamp}] [{prefix}] {message}\n"
    try:
        with open(get_log_file(game_dir), "a", encoding="utf-8") as f:
            f.write(line)
    except:
        pass

def log_exception(context, exc, game_dir=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb = traceback.format_exc()
    try:
        with open(get_log_file(game_dir), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [ERROR] {context}: {exc}\n{tb}\n")
    except:
        pass

# ── network ───────────────────────────────────────────────────────────────────
def get_local_ips():
    """Return list of (interface_name, ip) for all active non-loopback interfaces."""
    ips = []
    try:
        import socket
        # Get all IPs by connecting to external address (doesn't actually send data)
        hostname = socket.gethostname()
        all_ips = socket.getaddrinfo(hostname, None)
        seen = set()
        for item in all_ips:
            ip = item[4][0]
            if ip not in seen and not ip.startswith("127.") and ":" not in ip:
                seen.add(ip)
                # Try to guess interface type
                if ip.startswith("25."):
                    label = f"Hamachi  ({ip})"
                elif ip.startswith("100."):
                    label = f"ZeroTier/Tailscale  ({ip})"
                elif ip.startswith("10."):
                    label = f"VPN/LAN  ({ip})"
                elif ip.startswith("192.168."):
                    label = f"Local Network  ({ip})"
                elif ip.startswith("172."):
                    label = f"Private Network  ({ip})"
                else:
                    label = f"Network  ({ip})"
                ips.append((label, ip))
    except:
        pass
    # Also try socket approach
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not any(i[1] == ip for i in ips):
            ips.append((f"Primary Network  ({ip})", ip))
    except:
        pass
    return ips

# ── ini helpers ───────────────────────────────────────────────────────────────
def _convert_comments(ini_path):
    with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    converted = re.sub(r"^(\s*)//", r"\1#", content, flags=re.MULTILINE)
    if converted != content:
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(converted)

def get_ini_path(game_dir):
    return os.path.join(game_dir, INI_REL)

def get_exe_path(game_dir):
    return os.path.join(game_dir, EXE_REL)

def read_server_addr(game_dir):
    ini_path = get_ini_path(game_dir)
    if not os.path.exists(ini_path):
        return ""
    _convert_comments(ini_path)
    cfg = configparser.ConfigParser()
    cfg.read(ini_path, encoding="utf-8")
    return cfg.get("LAN", "ServerAddr", fallback="")

def write_server_addr(game_dir, ip):
    ini_path = get_ini_path(game_dir)
    _convert_comments(ini_path)
    cfg = configparser.ConfigParser()
    cfg.read(ini_path, encoding="utf-8")
    if not cfg.has_section("LAN"):
        cfg.add_section("LAN")
    cfg.set("LAN", "ServerAddr", ip)
    with open(ini_path, "w", encoding="utf-8") as f:
        cfg.write(f)

# ── file ops ──────────────────────────────────────────────────────────────────
def copy_src_to_dir(dest):
    d = os.path.join(dest, "src")
    shutil.copytree(SRC_DIR, d, dirs_exist_ok=True)

def copy_dlc_to_dir(dlc_folder, game_dir):
    for item in os.listdir(dlc_folder):
        s = os.path.join(dlc_folder, item)
        d = os.path.join(game_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

def is_wine():
    """Detect if we are running inside Wine on Linux."""
    # Wine sets WINELOADERNOEXEC or exposes a wine registry path
    if os.environ.get("WINELOADERNOEXEC"):
        return True
    # Check for Wine-specific file
    if os.path.exists("/proc/version"):
        try:
            with open("/proc/version") as f:
                return True  # /proc exists = real Linux kernel under Wine
        except:
            pass
    # Check for Z: drive mapping (Wine maps / to Z:)
    if sys.platform == "win32" and os.path.exists("Z:\\"):
        return True
    return False

def wine_to_unix(path):
    """Convert a Wine path like Z:/home/user/... to /home/user/..."""
    p = path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        return p[2:] or "/"
    return p

def unix_to_wine(path):
    """Convert a Unix path to Wine Z:/path."""
    return "Z:" + path

def self_install(game_dir):
    """
    Copy this launcher exe into src/system/ of the game directory.
    Handles Windows native, Wine on Linux, and plain Linux.
    Returns (dest_exe, needs_relaunch_via_script).
    """
    if getattr(sys, 'frozen', False):
        src_exe = sys.executable
    else:
        src_exe = os.path.abspath(__file__)

    dest_dir = os.path.join(game_dir, "src", "system")
    os.makedirs(dest_dir, exist_ok=True)
    dest_exe = os.path.join(dest_dir, os.path.basename(src_exe))

    # Already running from destination — nothing to do
    if os.path.abspath(src_exe).lower() == os.path.abspath(dest_exe).lower():
        return dest_exe, False

    running_under_wine = is_wine()
    log(f"self_install: src_exe={src_exe}, dest_exe={dest_exe}, wine={running_under_wine}, platform={sys.platform}, frozen={getattr(sys,'frozen',False)}", game_dir=game_dir)

    if running_under_wine and getattr(sys, 'frozen', False):
        # Running as .exe under Wine on Linux
        # Convert paths to real Linux paths for the shell script
        src_unix  = wine_to_unix(src_exe)
        dest_unix = wine_to_unix(dest_exe)
        dest_wine = unix_to_wine(dest_unix)
        pid = os.getpid()

        sh_path = os.path.join(os.path.expanduser("~"), "_scc_install.sh")
        sh_unix = wine_to_unix(sh_path)
        if not sh_unix.startswith("/"):
            sh_unix = os.path.join("/tmp", "_scc_install.sh")

        log(f"self_install wine: src_unix={src_unix}, dest_unix={dest_unix}, dest_wine={dest_wine}, sh_unix={sh_unix}, pid={pid}", game_dir=game_dir)

        sh = f"""#!/bin/bash
# Wait for Wine process to exit
while kill -0 {pid} 2>/dev/null; do
    sleep 0.5
done
sleep 1
cp -f "{src_unix}" "{dest_unix}"
chmod +x "{dest_unix}"
# Relaunch via Wine using the wine path
WINEPREFIX="$(dirname $(dirname $(dirname $(dirname "{dest_unix}"))))" wine "{dest_wine}" &
rm -- "$0"
"""
        with open(sh_unix, "w") as sf:
            sf.write(sh)
        os.chmod(sh_unix, 0o755)
        subprocess.Popen(["/bin/bash", sh_unix],
                         start_new_session=True,
                         close_fds=True)
        return dest_exe, True

    elif sys.platform == "win32" and getattr(sys, 'frozen', False):
        # Native Windows — use batch script
        bat_path = os.path.join(os.path.expanduser("~"), "_scc_install.bat")
        bat = f"""@echo off
:wait
timeout /t 1 /nobreak >nul
tasklist /fi "PID eq {os.getpid()}" | find "{os.getpid()}" >nul 2>&1
if not errorlevel 1 goto wait
copy /y "{src_exe}" "{dest_exe}"
start "" "{dest_exe}"
del "%~f0"
"""
        with open(bat_path, "w") as bf:
            bf.write(bat)
        subprocess.Popen(["cmd", "/c", bat_path],
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         close_fds=True)
        return dest_exe, True

    else:
        # Plain Linux .py script or non-frozen — direct copy is fine
        shutil.copy2(src_exe, dest_exe)
        try:
            os.chmod(dest_exe, 0o755)
        except:
            pass
        return dest_exe, False

def create_shortcut_windows(target, name, shortcut_types):
    """Create Windows shortcuts using PowerShell."""
    results = []
    for stype in shortcut_types:
        try:
            if stype == "desktop":
                dest = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.lnk")
            elif stype == "startmenu":
                dest = os.path.join(os.environ.get("APPDATA",""), "Microsoft","Windows","Start Menu","Programs", f"{name}.lnk")
            else:
                continue
            ps = f'''$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{dest}')
$s.TargetPath = '{target}'
$s.WorkingDirectory = '{os.path.dirname(target)}'
$s.Save()'''
            subprocess.run(["powershell", "-Command", ps], capture_output=True)
            results.append(stype)
        except:
            pass
    return results

def create_shortcut_linux(target, name, shortcut_types):
    """Create Linux .desktop shortcuts."""
    results = []
    desktop_entry = f"""[Desktop Entry]
Name={name}
Exec="{target}"
Type=Application
Terminal=false
Categories=Game;
"""
    for stype in shortcut_types:
        try:
            if stype == "desktop":
                dest = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.desktop")
            elif stype == "startmenu":
                dest = os.path.join(os.path.expanduser("~"), ".local", "share", "applications", f"{name}.desktop")
            else:
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w") as f:
                f.write(desktop_entry)
            os.chmod(dest, 0o755)
            results.append(stype)
        except:
            pass
    return results

def create_shortcuts(target, shortcut_types):
    name = "SCC LAN Launcher"
    if sys.platform == "win32":
        return create_shortcut_windows(target, name, shortcut_types)
    else:
        return create_shortcut_linux(target, name, shortcut_types)

def relaunch(new_exe, game_dir):
    """Relaunch from new_exe location and exit current instance."""
    try:
        if sys.platform == "win32":
            subprocess.Popen([new_exe], cwd=os.path.dirname(new_exe))
        else:
            subprocess.Popen([new_exe], cwd=os.path.dirname(new_exe))
        sys.exit(0)
    except Exception as e:
        log_exception("Relaunch failed", e, game_dir)

# ── theme ─────────────────────────────────────────────────────────────────────
BG        = "#080808"
BG2       = "#0f0f0f"
PANEL     = "#111111"
ORANGE    = "#E8722A"
ORANGE2   = "#a04d18"
ORANGE3   = "#3a1a08"
WHITE     = "#F0EEE8"
DIM       = "#444440"
DIM2      = "#222220"
GREEN_HUD = "#4aff91"
RED_HUD   = "#ff4a4a"

FONT_TITLE  = ("Courier New", 22, "bold")
FONT_HEAD   = ("Courier New", 11, "bold")
FONT_BODY   = ("Courier New", 9)
FONT_SMALL  = ("Courier New", 7)
FONT_MONO   = ("Courier New", 11, "bold")
FONT_BTN    = ("Courier New", 9, "bold")
FONT_BTN_LG = ("Courier New", 11, "bold")

# ── animated canvas elements ──────────────────────────────────────────────────
class HUDCanvas(tk.Canvas):
    """Canvas with corner brackets and optional scanlines."""
    def __init__(self, parent, width=480, height=60, color=ORANGE, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=BG, highlightthickness=0, **kwargs)
        self._w = width
        self._h = height
        self._color = color
        self._draw_brackets()

    def _draw_brackets(self):
        self.delete("brackets")
        c = self._color
        w, h = self._w, self._h
        sz = 12
        t = 1
        corners = [
            [(0,sz,0,0,sz,0)],
            [(w-sz,0,w,0,w,sz)],
            [(0,h-sz,0,h,sz,h)],
            [(w-sz,h,w,h,w,h-sz)],
        ]
        for pts in corners:
            self.create_line(*pts[0], fill=c, width=t, tags="brackets")

class FlickerLabel(tk.Label):
    """Label that flickers on appearance like a CRT boot."""
    def __init__(self, parent, text="", flicker_done_cb=None, **kwargs):
        super().__init__(parent, text="", **kwargs)
        self._full = text
        self._cb = flicker_done_cb
        self._after_id = None

    def start(self, delay=80):
        self._flicker(0, delay)

    def _flicker(self, step, delay):
        if step < 4:
            vis = step % 2 == 0
            self.config(text=self._full if vis else "")
            self._after_id = self.after(delay, self._flicker, step+1, delay)
        else:
            self.config(text=self._full)
            if self._cb:
                self._cb()

class TypewriterLabel(tk.Label):
    """Types out text character by character."""
    def __init__(self, parent, text="", speed=40, done_cb=None, **kwargs):
        super().__init__(parent, text="", **kwargs)
        self._full = text
        self._speed = speed
        self._cb = done_cb
        self._idx = 0

    def start(self, delay=0):
        self.after(delay, self._tick)

    def _tick(self):
        if self._idx <= len(self._full):
            self.config(text=self._full[:self._idx] + ("_" if self._idx < len(self._full) else ""))
            self._idx += 1
            self.after(self._speed, self._tick)
        else:
            self.config(text=self._full)
            if self._cb:
                self._cb()

# ── context menu for entry ────────────────────────────────────────────────────
def add_context_menu(entry_widget):
    menu = tk.Menu(entry_widget, tearoff=0,
                   bg=PANEL, fg=WHITE, activebackground=ORANGE,
                   activeforeground=BG, font=FONT_BODY,
                   relief="flat", bd=0)
    menu.add_command(label="Cut",        command=lambda: entry_widget.event_generate("<<Cut>>"))
    menu.add_command(label="Copy",       command=lambda: entry_widget.event_generate("<<Copy>>"))
    menu.add_command(label="Paste",      command=lambda: entry_widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Select All", command=lambda: (entry_widget.select_range(0, "end"), entry_widget.icursor("end")))

    def show(event):
        menu.tk_popup(event.x_root, event.y_root)
    entry_widget.bind("<Button-3>", show)

# ── main app ──────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SCC LAN Launcher")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.settings = load_settings()
        self.game_dir = self.settings.get("game_dir", "")
        self.setup_done = self.settings.get("setup_done", False)

        # Validate saved dir still exists
        if self.game_dir and not os.path.isdir(self.game_dir):
            self.game_dir = ""
            self.setup_done = False

        log("Launcher started.", game_dir=self.game_dir or None)

        self._current_frame = None
        self._step = 0

        if self.setup_done and self.game_dir:
            self._show_main()
        else:
            self._show_step(0)

    def _gd(self):
        return self.game_dir if self.game_dir and os.path.isdir(self.game_dir) else None

    def _save(self):
        self.settings["game_dir"] = self.game_dir
        self.settings["setup_done"] = self.setup_done
        save_settings(self.settings)

    # ── frame transitions ─────────────────────────────────────────────────────
    def _transition(self, build_fn):
        if self._current_frame:
            self._slide_out(self._current_frame, build_fn)
        else:
            frame = build_fn()
            frame.pack(fill="both", expand=True)
            self._current_frame = frame
            self.update_idletasks()
            self.geometry("")

    def _slide_out(self, old_frame, build_fn):
        old_frame.pack_forget()
        new_frame = build_fn()
        new_frame.pack(fill="both", expand=True)
        self._current_frame = new_frame
        self.update_idletasks()
        self.geometry("")

    # ── helpers ───────────────────────────────────────────────────────────────
    def _make_frame(self):
        f = tk.Frame(self, bg=BG)
        return f

    def _divider(self, parent):
        tk.Frame(parent, bg=ORANGE2, height=1).pack(fill="x", padx=20, pady=8)

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, font=FONT_SMALL,
                 fg=DIM, bg=BG).pack(anchor="w", padx=20, pady=(8,2))

    def _hud_panel(self, parent, pady=(4,4)):
        outer = tk.Frame(parent, bg=ORANGE2, pady=1)
        outer.pack(fill="x", padx=20, pady=pady)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="x", padx=1, pady=1)
        return inner

    def _btn(self, parent, text, cmd, bg=ORANGE3, fg=ORANGE, large=False, width=None):
        kw = {"width": width} if width else {}
        b = tk.Button(parent, text=text, command=cmd,
                      font=FONT_BTN_LG if large else FONT_BTN,
                      bg=bg, fg=fg,
                      activebackground=fg, activeforeground=BG,
                      relief="flat", bd=0, cursor="hand2",
                      padx=14, pady=10 if large else 7, **kw)
        return b

    def _status_label(self, parent):
        lbl = tk.Label(parent, text="", font=FONT_SMALL, fg=ORANGE, bg=BG)
        lbl.pack(anchor="w", padx=20, pady=(2,0))
        return lbl

    def _ok(self, lbl, msg):
        lbl.config(text=f"✔  {msg}", fg=GREEN_HUD)

    def _err(self, lbl, msg):
        lbl.config(text=f"✘  {msg}", fg=RED_HUD)

    def _warn(self, lbl, msg):
        lbl.config(text=f"⚠  {msg}", fg=ORANGE)

    # ── SETUP HEADER ──────────────────────────────────────────────────────────
    def _setup_header(self, parent, step_num, total=6):
        # Top bar
        bar = tk.Frame(parent, bg=BG2)
        bar.pack(fill="x")

        tk.Label(bar, text="TOM CLANCY'S", font=FONT_SMALL,
                 fg=DIM, bg=BG2).pack(side="left", padx=(20,4), pady=8)
        tk.Label(bar, text="SPLINTER CELL: CONVICTION", font=("Courier New", 8, "bold"),
                 fg=ORANGE, bg=BG2).pack(side="left", pady=8)

        step_txt = f"SETUP  {step_num}/{total}"
        tk.Label(bar, text=step_txt, font=FONT_SMALL,
                 fg=DIM, bg=BG2).pack(side="right", padx=20, pady=8)

        tk.Frame(parent, bg=ORANGE, height=2).pack(fill="x")

        # Progress dots
        dot_row = tk.Frame(parent, bg=BG)
        dot_row.pack(pady=(10,0))
        for i in range(total):
            color = ORANGE if i < step_num else DIM2
            tk.Label(dot_row, text="◆" if i < step_num else "◇",
                     font=("Courier New", 8), fg=color, bg=BG).pack(side="left", padx=3)

    def _main_header(self, parent):
        bar = tk.Frame(parent, bg=BG2)
        bar.pack(fill="x")
        tk.Label(bar, text="TOM CLANCY'S", font=FONT_SMALL,
                 fg=DIM, bg=BG2).pack(side="left", padx=(20,4), pady=8)
        tk.Label(bar, text="SPLINTER CELL: CONVICTION", font=("Courier New", 8, "bold"),
                 fg=ORANGE, bg=BG2).pack(side="left", pady=8)
        tk.Label(bar, text="LAN LAUNCHER", font=FONT_SMALL,
                 fg=DIM, bg=BG2).pack(side="right", padx=20, pady=8)
        tk.Frame(parent, bg=ORANGE, height=2).pack(fill="x")

    # ══════════════════════════════════════════════════════════════════════════
    # SETUP STEPS
    # ══════════════════════════════════════════════════════════════════════════

    def _show_step(self, step):
        self._step = step
        steps = [
            self._build_step0_welcome,
            self._build_step1_directory,
            self._build_step2_dlc,
            self._build_step3_install,
            self._build_step4_ip,
            self._build_step5_shortcuts,
        ]
        self._transition(steps[step])

    # ── Step 0: Welcome ───────────────────────────────────────────────────────
    def _build_step0_welcome(self):
        f = self._make_frame()
        self._setup_header(f, 0, 6)

        # Eye / silhouette art
        art = tk.Canvas(f, width=480, height=120, bg=BG, highlightthickness=0)
        art.pack(pady=(20,0))

        # Draw stylized eye
        cx, cy = 240, 60
        art.create_oval(cx-80, cy-30, cx+80, cy+30, outline=ORANGE, width=2)
        art.create_oval(cx-20, cy-20, cx+20, cy+20, fill=ORANGE, outline="")
        art.create_oval(cx-8, cy-8, cx+8, cy+8, fill=BG, outline="")
        # corner brackets
        for x1,y1,x2,y2,x3,y3 in [
            (0,20,0,0,20,0),(460,0,480,0,480,20),
            (0,100,0,120,20,120),(460,120,480,120,480,100)]:
            art.create_line(x1,y1,x2,y2,x3,y3, fill=ORANGE2, width=1)

        # Ghost text
        ghost = tk.Label(f, text="[ LAST KNOWN POSITION ]",
                         font=("Courier New", 8), fg=ORANGE2, bg=BG)
        ghost.pack()

        # Title flicker
        title = FlickerLabel(f, text="SCC  LAN  LAUNCHER",
                             font=FONT_TITLE, fg=ORANGE, bg=BG)
        title.pack(pady=(16, 4))

        # Typewriter subtitle
        sub = TypewriterLabel(f,
            text="FOURTH ECHELON  ·  NETWORK CONFIGURATION SYSTEM",
            font=FONT_SMALL, fg=DIM, bg=BG, speed=35)
        sub.pack()

        self._divider(f)

        desc = tk.Label(f,
            text="This utility will configure your LAN connection\nfor Splinter Cell: Conviction FusionFix.\n\nComplete each step to initialize the system.",
            font=FONT_BODY, fg=WHITE, bg=BG, justify="center")
        desc.pack(pady=12)

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(pady=(8, 20))
        self._btn(btn_row, "▶  INITIALIZE SETUP", lambda: self._show_step(1),
                  large=True).pack()

        def _start_anim():
            title.start()
            sub.start(delay=600)
        f.after(100, _start_anim)
        return f

    # ── Step 1: Directory ─────────────────────────────────────────────────────
    def _build_step1_directory(self):
        f = self._make_frame()
        self._setup_header(f, 1, 6)

        tk.Label(f, text="GAME DIRECTORY", font=FONT_HEAD,
                 fg=ORANGE, bg=BG).pack(anchor="w", padx=20, pady=(20,4))
        tk.Label(f,
            text="Select the root folder of your Splinter Cell: Conviction installation.\nDo NOT select the src/ subfolder — select the main game folder.",
            font=FONT_BODY, fg=DIM, bg=BG, justify="left").pack(anchor="w", padx=20, pady=(0,12))

        panel = self._hud_panel(f)
        path_var = tk.StringVar(value=self.game_dir or "No directory selected")
        path_lbl = tk.Label(panel, textvariable=path_var, font=FONT_BODY,
                            fg=WHITE, bg=PANEL, anchor="w", wraplength=400, justify="left")
        path_lbl.pack(fill="x", padx=12, pady=10)

        status = self._status_label(f)

        def browse():
            d = filedialog.askdirectory(title="Select Game Directory")
            if d:
                # Warn if they selected src/
                if os.path.basename(d).lower() == "src":
                    self._warn(status, "Please select the main game folder, not src/")
                    return
                self.game_dir = d
                path_var.set(d)
                self._ok(status, "Directory set.")
                log(f"Game directory set: {d}", game_dir=d)

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", padx=20, pady=(8,0))
        self._btn(btn_row, "📁  BROWSE", browse).pack(side="left")

        self._divider(f)

        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,20))
        self._btn(nav, "◀  BACK", lambda: self._show_step(0),
                  bg=DIM2, fg=DIM).pack(side="left")

        def next_step():
            if not self.game_dir or not os.path.isdir(self.game_dir):
                self._warn(status, "Please select a valid game directory first.")
                return
            self._save()
            self._show_step(2)

        self._btn(nav, "NEXT  ▶", next_step, large=False).pack(side="right")
        return f

    # ── Step 2: DLC ───────────────────────────────────────────────────────────
    def _build_step2_dlc(self):
        f = self._make_frame()
        self._setup_header(f, 2, 6)

        tk.Label(f, text="OPTIONAL DLC", font=FONT_HEAD,
                 fg=ORANGE, bg=BG).pack(anchor="w", padx=20, pady=(20,4))
        tk.Label(f,
            text="Install the Insurgency Pack DLC before copying main files.\nExtract the DLC .zip first, then select the extracted folder.\nYou can also skip this and install DLC later from the main screen.",
            font=FONT_BODY, fg=DIM, bg=BG, justify="left").pack(anchor="w", padx=20, pady=(0,12))

        status = self._status_label(f)

        def install_dlc():
            dlc = filedialog.askdirectory(title="Select Extracted Insurgency Pack DLC Folder")
            if not dlc:
                return
            try:
                log(f"Installing DLC from: {dlc}", game_dir=self.game_dir)
                copy_dlc_to_dir(dlc, self.game_dir)
                log("DLC installed successfully.", game_dir=self.game_dir)
                self._ok(status, "Insurgency Pack DLC installed.")
            except Exception as e:
                log_exception("DLC install failed", e, self.game_dir)
                self._err(status, f"DLC install failed. Check debug log.")

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", padx=20, pady=(8,0))
        self._btn(btn_row, "📦  INSTALL INSURGENCY PACK DLC",
                  install_dlc, bg="#1a222a", fg="#6fa8cf").pack(side="left")

        self._divider(f)

        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,20))
        self._btn(nav, "◀  BACK", lambda: self._show_step(1), bg=DIM2, fg=DIM).pack(side="left")
        self._btn(nav, "SKIP  ▶", lambda: self._show_step(3), bg=DIM2, fg=DIM).pack(side="right", padx=(0,8))
        self._btn(nav, "NEXT  ▶", lambda: self._show_step(3)).pack(side="right")
        return f

    # ── Step 3: Install files ─────────────────────────────────────────────────
    def _build_step3_install(self):
        f = self._make_frame()
        self._setup_header(f, 3, 6)

        tk.Label(f, text="INSTALL FILES", font=FONT_HEAD,
                 fg=ORANGE, bg=BG).pack(anchor="w", padx=20, pady=(20,4))
        tk.Label(f,
            text=f"Files will be copied to:\n{self.game_dir}",
            font=FONT_BODY, fg=DIM, bg=BG, justify="left",
            wraplength=440).pack(anchor="w", padx=20, pady=(0,12))

        status = self._status_label(f)
        installed = [False]

        def install():
            try:
                log(f"Installing files to: {self.game_dir}", game_dir=self.game_dir)
                copy_src_to_dir(self.game_dir)
                log("Files copied successfully.", game_dir=self.game_dir)
                self._ok(status, "Files installed successfully.")
                installed[0] = True
            except Exception as e:
                log_exception("Install failed", e, self.game_dir)
                self._err(status, "Install failed. Check debug log.")

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", padx=20, pady=(8,0))
        self._btn(btn_row, "▶  INSTALL FILES", install, large=True).pack()

        self._divider(f)

        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,20))
        self._btn(nav, "◀  BACK", lambda: self._show_step(2), bg=DIM2, fg=DIM).pack(side="left")

        def next_step():
            if not installed[0] and not os.path.exists(get_exe_path(self.game_dir)):
                self._warn(status, "Please install files before continuing.")
                return
            self._show_step(4)

        self._btn(nav, "NEXT  ▶", next_step).pack(side="right")
        return f

    # ── Step 4: IP ────────────────────────────────────────────────────────────
    def _build_step4_ip(self):
        f = self._make_frame()
        self._setup_header(f, 4, 6)

        tk.Label(f, text="SERVER ADDRESS", font=FONT_HEAD,
                 fg=ORANGE, bg=BG).pack(anchor="w", padx=20, pady=(20,4))
        tk.Label(f,
            text="Set the ServerAddr for LAN play. Select a detected network\ninterface (VPN/LAN) or enter an IP manually.",
            font=FONT_BODY, fg=DIM, bg=BG, justify="left").pack(anchor="w", padx=20, pady=(0,12))

        # Network detection
        self._section_label(f, "DETECTED INTERFACES")
        net_panel = self._hud_panel(f)

        net_var = tk.StringVar(value="Scanning...")
        net_map = {}

        def populate_nets():
            ips = get_local_ips()
            if ips:
                options = [label for label,ip in ips]
                net_map.update({label:ip for label,ip in ips})
                net_dropdown.config(values=options)
                net_var.set(options[0])
            else:
                net_dropdown.config(values=["No interfaces detected"])
                net_var.set("No interfaces detected")

        net_row = tk.Frame(net_panel, bg=PANEL)
        net_row.pack(fill="x", padx=8, pady=8)

        net_dropdown = ttk.Combobox(net_row, textvariable=net_var,
                                    font=FONT_BODY, state="readonly", width=40)
        net_dropdown.pack(side="left", fill="x", expand=True)

        def use_detected():
            sel = net_var.get()
            if sel in net_map:
                ip_var.set(net_map[sel])
                self._ok(ip_status, f"IP set from interface.")

        self._btn(net_row, "USE", use_detected, small=True if False else False
                  ).pack(side="left", padx=(8,0))

        # Manual IP
        self._section_label(f, "MANUAL ENTRY")
        ip_panel = self._hud_panel(f)

        ip_row = tk.Frame(ip_panel, bg=PANEL)
        ip_row.pack(fill="x", padx=8, pady=8)

        tk.Label(ip_row, text="ServerAddr :", font=FONT_BODY,
                 fg=DIM, bg=PANEL).pack(side="left")

        current_ip = read_server_addr(self.game_dir) if self.game_dir else ""
        ip_var = tk.StringVar(value=current_ip or "")
        ip_entry = tk.Entry(ip_row, textvariable=ip_var,
                            font=FONT_MONO, bg=BG2, fg=ORANGE,
                            insertbackground=ORANGE, relief="flat",
                            width=20, bd=0,
                            highlightthickness=1,
                            highlightbackground=ORANGE2,
                            highlightcolor=ORANGE)
        ip_entry.pack(side="left", padx=(8,0), ipady=5, ipadx=4)
        add_context_menu(ip_entry)

        ip_status = self._status_label(f)

        def save_ip():
            ip = ip_var.get().strip()
            if not ip:
                self._warn(ip_status, "Enter an IP address.")
                return
            try:
                write_server_addr(self.game_dir, ip)
                log(f"Saving ServerAddr = {ip}", game_dir=self.game_dir)
                self._ok(ip_status, f"Saved  ServerAddr = {ip}")
            except Exception as e:
                log_exception("Save IP failed", e, self.game_dir)
                self._err(ip_status, "Save failed. Check debug log.")

        save_row = tk.Frame(f, bg=BG)
        save_row.pack(anchor="w", padx=20, pady=(6,0))
        self._btn(save_row, "💾  SAVE IP", save_ip).pack(side="left")

        self._divider(f)

        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,20))
        self._btn(nav, "◀  BACK", lambda: self._show_step(3), bg=DIM2, fg=DIM).pack(side="left")
        self._btn(nav, "NEXT  ▶", lambda: self._show_step(5)).pack(side="right")

        f.after(100, populate_nets)
        return f

    # ── Step 5: Shortcuts ─────────────────────────────────────────────────────
    def _build_step5_shortcuts(self):
        f = self._make_frame()
        self._setup_header(f, 5, 6)

        tk.Label(f, text="CREATE SHORTCUTS", font=FONT_HEAD,
                 fg=ORANGE, bg=BG).pack(anchor="w", padx=20, pady=(20,4))
        tk.Label(f,
            text="Select where to create shortcuts for the launcher.\nAt least one is recommended so you can launch from the game directory.",
            font=FONT_BODY, fg=DIM, bg=BG, justify="left").pack(anchor="w", padx=20, pady=(0,12))

        desktop_var   = tk.BooleanVar(value=True)
        startmenu_var = tk.BooleanVar(value=False)

        panel = self._hud_panel(f)
        for text, var in [("Desktop shortcut", desktop_var),
                          ("Start Menu / App launcher shortcut", startmenu_var)]:
            row = tk.Frame(panel, bg=PANEL)
            row.pack(fill="x", padx=12, pady=4)
            tk.Checkbutton(row, text=text, variable=var,
                           font=FONT_BODY, fg=WHITE, bg=PANEL,
                           selectcolor=BG2, activebackground=PANEL,
                           activeforeground=ORANGE,
                           relief="flat").pack(side="left")

        status = self._status_label(f)

        self._divider(f)

        nav = tk.Frame(f, bg=BG)
        nav.pack(fill="x", padx=20, pady=(0,20))
        self._btn(nav, "◀  BACK", lambda: self._show_step(4), bg=DIM2, fg=DIM).pack(side="left")

        def _do_finish(shortcut_types, finish_btn, _stop_spin=None):
            # Run on background thread to avoid freezing UI
            new_exe = None
            via_script = False
            try:
                new_exe, via_script = self_install(self.game_dir)
                log(f"Launcher self-installed to: {new_exe} (via_script={via_script})", game_dir=self.game_dir)
            except Exception as e:
                log_exception("Self-install failed", e, self.game_dir)

            if shortcut_types and new_exe:
                try:
                    create_shortcuts(new_exe, shortcut_types)
                    log(f"Shortcuts created: {shortcut_types}", game_dir=self.game_dir)
                except Exception as e:
                    log_exception("Shortcut creation failed", e, self.game_dir)

            self.setup_done = True
            self._save()

            # Schedule UI update back on main thread
            def _on_done():
                if _stop_spin: _stop_spin()
                finish_btn.config(state="normal", text="✔  FINISH  &  LAUNCH")
                if via_script:
                    # Batch script is already running waiting for us to exit
                    self._ok(status, "Copying launcher... closing to complete install.")
                    messagebox.showinfo("Setup Complete",
                        "Setup is complete!\n\nThe launcher will now close and automatically "
                        "reopen from your game directory.")
                elif new_exe:
                    self._ok(status, "Setup complete!")
                    f.after(800, self._show_main)
                else:
                    self._ok(status, "Setup complete!")
                    f.after(800, self._show_main)
            f.after(0, _on_done)

        # Spinner animation
        spinner_chars = ["◆  ", " ◆ ", "  ◆"]
        spinner_idx = [0]
        spinner_id = [None]

        def _spin():
            if spinner_id[0] is not None:
                c = spinner_chars[spinner_idx[0] % len(spinner_chars)]
                status.config(text=f"{c} Copying launcher to game directory, please wait...")
                spinner_idx[0] += 1
                spinner_id[0] = f.after(300, _spin)

        def _stop_spin():
            if spinner_id[0] is not None:
                f.after_cancel(spinner_id[0])
                spinner_id[0] = None

        def finish():
            shortcut_types = []
            if desktop_var.get():   shortcut_types.append("desktop")
            if startmenu_var.get(): shortcut_types.append("startmenu")

            finish_btn.config(state="disabled", text="Please wait...")
            spinner_id[0] = "start"
            _spin()

            t = threading.Thread(target=_do_finish, args=(shortcut_types, finish_btn, _stop_spin), daemon=True)
            t.start()

        finish_btn = self._btn(nav, "✔  FINISH  &  LAUNCH", finish, large=True)
        finish_btn.pack(side="right")
        return f

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN SCREEN
    # ══════════════════════════════════════════════════════════════════════════

    def _show_main(self):
        self._transition(self._build_main)

    def _build_main(self):
        f = self._make_frame()
        self._main_header(f)

        # ── Title strip ───────────────────────────────────────────────────────
        title_row = tk.Frame(f, bg=BG)
        title_row.pack(fill="x", padx=20, pady=(16,0))
        tk.Label(title_row, text="SCC  LAN  LAUNCHER",
                 font=("Courier New", 18, "bold"), fg=ORANGE, bg=BG).pack(side="left")
        tk.Label(title_row, text="[ ONLINE ]",
                 font=FONT_SMALL, fg=GREEN_HUD, bg=BG).pack(side="right", pady=(8,0))

        # Game dir display
        dir_panel = self._hud_panel(f, pady=(8,4))
        dir_row = tk.Frame(dir_panel, bg=PANEL)
        dir_row.pack(fill="x", padx=12, pady=6)
        tk.Label(dir_row, text="DIR :", font=FONT_SMALL, fg=DIM, bg=PANEL).pack(side="left")
        tk.Label(dir_row, text=self.game_dir, font=FONT_BODY,
                 fg=WHITE, bg=PANEL, wraplength=360, anchor="w").pack(side="left", padx=(6,0))

        self._divider(f)

        # ── IP Section ────────────────────────────────────────────────────────
        self._section_label(f, "SERVER ADDRESS")

        ip_panel = self._hud_panel(f, pady=(2,4))
        ip_top = tk.Frame(ip_panel, bg=PANEL)
        ip_top.pack(fill="x", padx=8, pady=(8,4))

        # Network dropdown
        tk.Label(ip_top, text="INTERFACE :", font=FONT_SMALL, fg=DIM, bg=PANEL).pack(side="left")
        net_var = tk.StringVar(value="Scanning...")
        net_map = {}
        net_dd = ttk.Combobox(ip_top, textvariable=net_var, font=FONT_BODY,
                               state="readonly", width=34)
        net_dd.pack(side="left", padx=(6,6))

        ip_bot = tk.Frame(ip_panel, bg=PANEL)
        ip_bot.pack(fill="x", padx=8, pady=(0,8))

        tk.Label(ip_bot, text="ServerAddr :", font=FONT_BODY, fg=DIM, bg=PANEL).pack(side="left")
        current_ip = read_server_addr(self.game_dir) if self._gd() else ""
        ip_var = tk.StringVar(value=current_ip)
        ip_entry = tk.Entry(ip_bot, textvariable=ip_var,
                            font=FONT_MONO, bg=BG2, fg=ORANGE,
                            insertbackground=ORANGE, relief="flat", width=20, bd=0,
                            highlightthickness=1,
                            highlightbackground=ORANGE2, highlightcolor=ORANGE)
        ip_entry.pack(side="left", padx=(8,8), ipady=5, ipadx=4)
        add_context_menu(ip_entry)

        ip_status = self._status_label(f)

        def use_net():
            sel = net_var.get()
            if sel in net_map:
                ip_var.set(net_map[sel])
                self._ok(ip_status, "IP set from interface.")

        def populate_nets():
            ips = get_local_ips()
            if ips:
                options = [lbl for lbl,ip in ips]
                net_map.update({lbl:ip for lbl,ip in ips})
                net_dd.config(values=options)
                net_var.set(options[0])
            else:
                net_dd.config(values=["No interfaces detected"])
                net_var.set("No interfaces detected")

        use_net_btn = self._btn(ip_top, "USE", use_net)
        use_net_btn.pack(side="left")

        def save_ip():
            ip = ip_var.get().strip()
            if not ip:
                self._warn(ip_status, "Enter an IP address.")
                return
            try:
                write_server_addr(self.game_dir, ip)
                log(f"Saving ServerAddr = {ip}", game_dir=self.game_dir)
                self._ok(ip_status, f"Saved  ServerAddr = {ip}")
            except Exception as e:
                log_exception("Save IP failed", e, self.game_dir)
                self._err(ip_status, "Save failed.")

        self._btn(ip_bot, "💾  SAVE", save_ip).pack(side="left")

        self._divider(f)

        # ── Action buttons ────────────────────────────────────────────────────
        self._section_label(f, "ACTIONS")

        launch_status = self._status_label(f)
        install_status = self._status_label(f)
        dlc_status = self._status_label(f)

        def launch():
            exe = get_exe_path(self.game_dir)
            if not os.path.exists(exe):
                self._err(launch_status, "EXE not found. Reinstall files first.")
                return
            try:
                log(f"Launching: {exe}", game_dir=self.game_dir)
                subprocess.Popen([exe], cwd=os.path.dirname(exe))
                self._ok(launch_status, "Launched successfully.")
            except Exception as e:
                log_exception("Launch failed", e, self.game_dir)
                self._err(launch_status, "Launch failed. Check debug log.")

        def reinstall():
            try:
                log(f"Reinstalling files to: {self.game_dir}", game_dir=self.game_dir)
                copy_src_to_dir(self.game_dir)
                log("Files reinstalled.", game_dir=self.game_dir)
                self._ok(install_status, "Files reinstalled.")
            except Exception as e:
                log_exception("Reinstall failed", e, self.game_dir)
                self._err(install_status, "Reinstall failed.")

        def install_dlc():
            dlc = filedialog.askdirectory(title="Select Extracted Insurgency Pack DLC Folder")
            if not dlc:
                return
            try:
                log(f"Installing DLC from: {dlc}", game_dir=self.game_dir)
                copy_dlc_to_dir(dlc, self.game_dir)
                log("DLC installed.", game_dir=self.game_dir)
                self._ok(dlc_status, "Insurgency Pack DLC installed.")
            except Exception as e:
                log_exception("DLC install failed", e, self.game_dir)
                self._err(dlc_status, "DLC install failed.")

        # Launch row
        row1 = tk.Frame(f, bg=BG)
        row1.pack(fill="x", padx=20, pady=(4,2))
        self._btn(row1, "⬛  LAUNCH SCC LAN HELPER", launch,
                  bg="#1a2a1a", fg=GREEN_HUD, large=True).pack(fill="x")

        # Install + DLC row
        row2 = tk.Frame(f, bg=BG)
        row2.pack(fill="x", padx=20, pady=(4,2))
        self._btn(row2, "▶  REINSTALL FILES", reinstall).pack(side="left", fill="x", expand=True)
        tk.Frame(row2, bg=BG, width=8).pack(side="left")
        self._btn(row2, "📦  INSTALL DLC", install_dlc,
                  bg="#1a222a", fg="#6fa8cf").pack(side="left", fill="x", expand=True)

        self._divider(f)

        # ── Settings row ──────────────────────────────────────────────────────
        self._section_label(f, "SETTINGS")

        def reconfigure():
            confirm = messagebox.askyesno("Reconfigure",
                "Change the game directory?\nThis will restart the setup wizard.")
            if not confirm:
                return
            also_reset = messagebox.askyesno("Reset Installation?",
                "Also clear saved IP and mark files as not installed?\n(Files already copied will remain on disk.)")
            log("User triggered reconfigure.", game_dir=self.game_dir)
            self.setup_done = False
            if also_reset:
                self.game_dir = ""
            self._save()
            self._show_step(0 if also_reset else 1)

        def reset_all():
            confirm = messagebox.askyesno("Reset Settings",
                "This will clear your saved IP and game directory.\nYou will be returned to the setup wizard.\n\nContinue?")
            if not confirm:
                return
            also_dir = messagebox.askyesno("Reset Game Directory?",
                "Also clear the game directory path?\n(Files already copied will NOT be deleted.)")
            log("User triggered full reset.", game_dir=self.game_dir)
            self.setup_done = False
            if also_dir:
                self.game_dir = ""
            self._save()
            self._show_step(0)

        set_row = tk.Frame(f, bg=BG)
        set_row.pack(fill="x", padx=20, pady=(4,2))
        self._btn(set_row, "⟳  RECONFIGURE PATH", reconfigure,
                  bg=DIM2, fg=DIM).pack(side="left")
        tk.Frame(set_row, bg=BG, width=8).pack(side="left")
        self._btn(set_row, "↺  RESET SETTINGS", reset_all,
                  bg=RED_HUD+"22", fg=RED_HUD).pack(side="left")

        self._divider(f)

        # ── Debug log ─────────────────────────────────────────────────────────
        self._section_label(f, "DEBUG LOG")
        log_path = get_log_file(self.game_dir)
        tk.Label(f, text=f"Log: {log_path}", font=FONT_SMALL,
                 fg=DIM, bg=BG, wraplength=460).pack(anchor="w", padx=20, pady=(0,4))

        log_status = self._status_label(f)

        def copy_log():
            if not os.path.exists(log_path):
                self._warn(log_status, "No log file found yet.")
                return
            try:
                with open(log_path, "r", encoding="utf-8") as lf:
                    contents = lf.read()
                self.clipboard_clear()
                self.clipboard_append(contents)
                self._ok(log_status, "Log copied to clipboard.")
            except Exception as e:
                self._err(log_status, "Could not read log.")

        def clear_log():
            if not os.path.exists(log_path):
                self._warn(log_status, "No log file to clear.")
                return
            if messagebox.askyesno("Clear Log", "Delete the debug log?\n\nThis cannot be undone."):
                try:
                    os.remove(log_path)
                    self._ok(log_status, "Log cleared.")
                except Exception as e:
                    self._err(log_status, "Could not clear log.")

        log_row = tk.Frame(f, bg=BG)
        log_row.pack(fill="x", padx=20, pady=(0,20))
        self._btn(log_row, "📋  COPY LOG", copy_log).pack(side="left")
        tk.Frame(log_row, bg=BG, width=8).pack(side="left")
        self._btn(log_row, "🗑  CLEAR LOG", clear_log,
                  bg=RED_HUD+"22", fg=RED_HUD).pack(side="left")

        f.after(100, populate_nets)
        return f

# ── entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
