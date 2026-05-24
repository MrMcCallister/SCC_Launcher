import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import shutil
import subprocess
import configparser
import traceback
import datetime

# ── helpers ───────────────────────────────────────────────────────────────────

def resource_path(relative):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

INI_REL      = os.path.join("system", "scripts", "SplinterCellConviction.FusionFix.ini")
EXE_REL      = os.path.join("system", "scc_lan_helper.exe")
SRC_DIR      = resource_path("src")
LOG_FILE_NAME = "SCC_Launcher_debug.log"

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".scc_launcher_settings.txt")

# ── logging ───────────────────────────────────────────────────────────────────

def get_log_file(game_dir=None):
    """Log lives in the game directory if set, otherwise falls back to home."""
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
    except Exception:
        pass

def log_exception(context, exc, game_dir=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb = traceback.format_exc()
    try:
        with open(get_log_file(game_dir), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [ERROR] {context}: {exc}\n")
            f.write(tb)
            f.write("\n")
    except Exception:
        pass

# ── settings ──────────────────────────────────────────────────────────────────

def load_saved_dir():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            d = f.read().strip()
        if os.path.isdir(d):
            return d
    return ""

def save_dir(path):
    with open(SETTINGS_FILE, "w") as f:
        f.write(path)

# ── game helpers ──────────────────────────────────────────────────────────────

def get_ini_path(game_dir):
    return os.path.join(game_dir, INI_REL)

def get_exe_path(game_dir):
    return os.path.join(game_dir, EXE_REL)

def read_server_addr(game_dir):
    ini_path = get_ini_path(game_dir)
    if not os.path.exists(ini_path):
        return ""
    cfg = configparser.ConfigParser()
    cfg.read(ini_path)
    return cfg.get("LAN", "ServerAddr", fallback="")

def write_server_addr(game_dir, ip):
    ini_path = get_ini_path(game_dir)
    cfg = configparser.ConfigParser()
    cfg.read(ini_path)
    if not cfg.has_section("LAN"):
        cfg.add_section("LAN")
    cfg.set("LAN", "ServerAddr", ip)
    with open(ini_path, "w") as f:
        cfg.write(f)

def copy_src_to_dir(dest):
    for item in os.listdir(SRC_DIR):
        s = os.path.join(SRC_DIR, item)
        d = os.path.join(dest, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

def copy_dlc_to_dir(dlc_folder, game_dir):
    for item in os.listdir(dlc_folder):
        s = os.path.join(dlc_folder, item)
        d = os.path.join(game_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

# ── GUI ───────────────────────────────────────────────────────────────────────

BG       = "#0d0d0f"
CARD     = "#13131a"
ACCENT   = "#c8a96e"
ACCENT2  = "#7b5e3a"
FG       = "#e8e0d0"
FG_DIM   = "#5a5650"
GREEN    = "#6fcf6f"
GREEN_BG = "#1a2a1a"
RED      = "#cf6f6f"
RED_BG   = "#2a1a1a"
BLUE     = "#6fa8cf"
BLUE_BG  = "#1a222a"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SCC LAN Launcher")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.game_dir = tk.StringVar(value=load_saved_dir())
        log("Launcher started.", game_dir=self.game_dir.get())
        self._build_ui()
        self._refresh_state()

    def _gd(self):
        """Return current game dir or None."""
        d = self.game_dir.get().strip()
        return d if d and os.path.isdir(d) else None

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        PAD = 18

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=PAD, pady=(PAD, 4))
        tk.Label(header, text="SCC  LAN  LAUNCHER",
                 font=("Courier New", 15, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(header, text="FusionFix Edition",
                 font=("Courier New", 8),
                 fg=FG_DIM, bg=BG).pack(side="left", padx=(8,0), pady=(4,0))

        tk.Frame(self, bg=ACCENT2, height=1).pack(fill="x", padx=PAD, pady=(0, PAD))

        # ── Game Directory ────────────────────────────────────────────────────
        sec1 = self._section("GAME DIRECTORY")

        path_frame = tk.Frame(sec1, bg=CARD, highlightthickness=1,
                              highlightbackground=ACCENT2)
        path_frame.pack(fill="x", pady=(4, 8))
        tk.Label(path_frame, text="Path:", font=("Courier New", 8),
                 fg=FG_DIM, bg=CARD).pack(side="left", padx=(8,4), pady=6)
        self.dir_label = tk.Label(path_frame, textvariable=self.game_dir,
                                  font=("Courier New", 9), fg=FG, bg=CARD,
                                  anchor="w", wraplength=320, justify="left")
        self.dir_label.pack(side="left", fill="x", expand=True, padx=(0,8), pady=6)

        btn_row = tk.Frame(sec1, bg=BG)
        btn_row.pack(fill="x")
        self._btn(btn_row, "📁  Set Game Directory",
                  self._browse_dir, ACCENT2, ACCENT, small=True).pack(side="left")
        self._btn(btn_row, "⟳  Reconfigure Path",
                  self._reconfigure, RED_BG, RED, small=True).pack(side="left", padx=(8,0))

        self.install_btn = self._btn(sec1,
            "▶  Install / Copy Files to Directory", self._install, ACCENT2, ACCENT)
        self.install_btn.pack(fill="x", pady=(10, 0))

        self.install_status = tk.Label(sec1, text="", font=("Courier New", 8),
                                       fg=ACCENT, bg=BG)
        self.install_status.pack(anchor="w", pady=(3, 0))

        tk.Frame(self, bg=ACCENT2, height=1).pack(fill="x", padx=PAD, pady=(4, PAD))

        # ── DLC ───────────────────────────────────────────────────────────────
        sec_dlc = self._section("OPTIONAL DLC")
        tk.Label(sec_dlc,
                 text="Extract the DLC .zip first, then click the button below to install it.",
                 font=("Courier New", 8), fg=FG_DIM, bg=BG,
                 wraplength=460, justify="left").pack(anchor="w", pady=(0, 6))
        self.dlc_btn = self._btn(sec_dlc,
            "📦  Install Insurgency Pack DLC", self._install_dlc, BLUE_BG, BLUE)
        self.dlc_btn.pack(fill="x")
        self.dlc_status = tk.Label(sec_dlc, text="", font=("Courier New", 8),
                                   fg=BLUE, bg=BG)
        self.dlc_status.pack(anchor="w", pady=(3, 0))

        tk.Frame(self, bg=ACCENT2, height=1).pack(fill="x", padx=PAD, pady=(4, PAD))

        # ── Server Address ────────────────────────────────────────────────────
        sec2 = self._section("SERVER ADDRESS  (ServerAddr)")
        ip_row = tk.Frame(sec2, bg=BG)
        ip_row.pack(fill="x", pady=(4, 0))
        tk.Label(ip_row, text="IP :", font=("Courier New", 10),
                 fg=FG_DIM, bg=BG).pack(side="left")
        self.ip_var = tk.StringVar()
        self.ip_entry = tk.Entry(ip_row, textvariable=self.ip_var,
                                 font=("Courier New", 12, "bold"),
                                 bg=CARD, fg=ACCENT, insertbackground=ACCENT,
                                 relief="flat", bd=0, width=22,
                                 highlightthickness=1,
                                 highlightbackground=ACCENT2,
                                 highlightcolor=ACCENT)
        self.ip_entry.pack(side="left", padx=(8,0), ipady=6, ipadx=6)
        self.save_ip_btn = self._btn(ip_row, "Save IP",
                                     self._save_ip, ACCENT2, ACCENT, small=True)
        self.save_ip_btn.pack(side="left", padx=(8, 0))
        self.ip_status = tk.Label(sec2, text="", font=("Courier New", 8),
                                  fg=ACCENT, bg=BG)
        self.ip_status.pack(anchor="w", pady=(3, 0))

        tk.Frame(self, bg=ACCENT2, height=1).pack(fill="x", padx=PAD, pady=(4, PAD))

        # ── Launch ────────────────────────────────────────────────────────────
        sec3 = self._section("LAUNCH")
        self.launch_btn = self._btn(sec3,
            "⬛  Launch SCC LAN Helper", self._launch, GREEN_BG, GREEN)
        self.launch_btn.pack(fill="x", pady=(4, 0))
        self.launch_status = tk.Label(sec3, text="", font=("Courier New", 8),
                                      fg=GREEN, bg=BG)
        self.launch_status.pack(anchor="w", pady=(3, 0))

        tk.Frame(self, bg=ACCENT2, height=1).pack(fill="x", padx=PAD, pady=(4, PAD))

        # ── Debug Log ─────────────────────────────────────────────────────────
        sec4 = self._section("DEBUG LOG")

        self.log_path_label = tk.Label(sec4, text="",
                 font=("Courier New", 7), fg=FG_DIM, bg=BG,
                 wraplength=460, justify="left")
        self.log_path_label.pack(anchor="w", pady=(0, 6))

        log_btn_row = tk.Frame(sec4, bg=BG)
        log_btn_row.pack(fill="x")
        self._btn(log_btn_row, "📋  Copy Log to Clipboard",
                  self._copy_log, ACCENT2, ACCENT, small=True).pack(side="left")
        self._btn(log_btn_row, "🗑  Clear Log",
                  self._clear_log, RED_BG, RED, small=True).pack(side="left", padx=(8,0))

        self.log_status = tk.Label(sec4, text="", font=("Courier New", 8),
                                   fg=ACCENT, bg=BG)
        self.log_status.pack(anchor="w", pady=(3, 0))

        # footer
        tk.Frame(self, bg=ACCENT2, height=1).pack(fill="x", padx=PAD, pady=(PAD, 0))
        tk.Label(self, text="Splinter Cell: Conviction  ·  LAN FusionFix",
                 font=("Courier New", 7), fg=FG_DIM, bg=BG).pack(pady=(4, PAD))

        self.minsize(500, 0)

    def _section(self, title):
        PAD = 18
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=PAD, pady=(0, PAD))
        tk.Label(f, text=title, font=("Courier New", 7, "bold"),
                 fg=FG_DIM, bg=BG).pack(anchor="w", pady=(0, 2))
        return f

    def _btn(self, parent, text, cmd, bg, fg, small=False):
        font = ("Courier New", 8, "bold") if small else ("Courier New", 10, "bold")
        return tk.Button(parent, text=text, command=cmd,
                         font=font, bg=bg, fg=fg,
                         activebackground=fg, activeforeground=bg,
                         relief="flat", bd=0, cursor="hand2",
                         padx=10, pady=5 if small else 10)

    # ── state ─────────────────────────────────────────────────────────────────

    def _refresh_state(self):
        d = self.game_dir.get().strip()
        ok = bool(d) and os.path.isdir(d)
        files_present = ok and os.path.exists(get_exe_path(d))

        self.install_btn.config(state="normal" if ok else "disabled")
        self.dlc_btn.config(state="normal" if files_present else "disabled")
        self.launch_btn.config(state="normal" if files_present else "disabled")
        self.save_ip_btn.config(state="normal" if files_present else "disabled")
        self.ip_entry.config(state="normal" if files_present else "disabled")

        if not d:
            self.dir_label.config(fg=RED)
            self.game_dir.set("No directory set — click 'Set Game Directory'")
        elif not os.path.isdir(d):
            self.dir_label.config(fg=RED)
        else:
            self.dir_label.config(fg=FG)

        if files_present:
            self.ip_var.set(read_server_addr(d))
        else:
            self.ip_var.set("")

        if ok and not files_present:
            self.install_status.config(
                text="⚠  Files not found in directory. Click Install to copy them.",
                fg=ACCENT)
        elif not ok:
            self.install_status.config(text="", fg=ACCENT)

        # update log path label
        log_path = get_log_file(d if ok else None)
        self.log_path_label.config(text=f"Log location:  {log_path}")

    # ── actions ───────────────────────────────────────────────────────────────

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Select Game Directory")
        if d:
            log(f"Game directory set to: {d}", game_dir=d)
            self.game_dir.set(d)
            save_dir(d)
            for lbl, fg in [(self.install_status, ACCENT),
                            (self.ip_status, ACCENT),
                            (self.launch_status, GREEN),
                            (self.dlc_status, BLUE),
                            (self.log_status, ACCENT)]:
                lbl.config(text="", fg=fg)
            self._refresh_state()

    def _reconfigure(self):
        if not messagebox.askyesno("Reconfigure Path",
                "This will clear the current game directory setting.\n\nContinue?"):
            return
        log("User reconfigured game directory.", game_dir=self._gd())
        self.game_dir.set("")
        save_dir("")
        for lbl, fg in [(self.install_status, ACCENT),
                        (self.ip_status, ACCENT),
                        (self.launch_status, GREEN),
                        (self.dlc_status, BLUE),
                        (self.log_status, ACCENT)]:
            lbl.config(text="", fg=fg)
        self._refresh_state()
        self._browse_dir()

    def _install(self):
        d = self._gd()
        if not d:
            return
        try:
            log(f"Installing files to: {d}", game_dir=d)
            copy_src_to_dir(d)
            log("Files copied successfully.", game_dir=d)
            self.install_status.config(text="✔  Files copied successfully.", fg=GREEN)
            self._refresh_state()
        except Exception as e:
            log_exception("Install failed", e, game_dir=d)
            messagebox.showerror("Install Error", str(e))
            self.install_status.config(text="✘  Copy failed. Check debug log.", fg=RED)

    def _install_dlc(self):
        d = self._gd()
        if not d:
            return
        dlc_folder = filedialog.askdirectory(
            title="Select Extracted Insurgency Pack DLC Folder")
        if not dlc_folder:
            return
        try:
            log(f"Installing DLC from: {dlc_folder}", game_dir=d)
            copy_dlc_to_dir(dlc_folder, d)
            log("DLC installed successfully.", game_dir=d)
            self.dlc_status.config(
                text="✔  Insurgency Pack DLC installed successfully.", fg=GREEN)
        except Exception as e:
            log_exception("DLC install failed", e, game_dir=d)
            messagebox.showerror("DLC Install Error", str(e))
            self.dlc_status.config(text="✘  DLC install failed. Check debug log.", fg=RED)

    def _launch(self):
        d = self._gd()
        exe = get_exe_path(d)
        if not os.path.exists(exe):
            log(f"Launch failed — exe not found: {exe}", error=True, game_dir=d)
            messagebox.showerror("Not Found",
                f"Cannot find:\n{exe}\n\nTry reinstalling the files.")
            return
        try:
            log(f"Launching: {exe}", game_dir=d)
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
            self.launch_status.config(text="✔  Launched successfully.", fg=GREEN)
        except Exception as e:
            log_exception("Launch failed", e, game_dir=d)
            messagebox.showerror("Launch Error", str(e))
            self.launch_status.config(text="✘  Launch failed. Check debug log.", fg=RED)

    def _save_ip(self):
        d = self._gd()
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showwarning("Empty IP", "Please enter a valid IP address.")
            return
        try:
            log(f"Saving ServerAddr = {ip}", game_dir=d)
            write_server_addr(d, ip)
            self.ip_status.config(text=f"✔  Saved  ServerAddr = {ip}", fg=GREEN)
        except Exception as e:
            log_exception("Save IP failed", e, game_dir=d)
            messagebox.showerror("Save Error", str(e))
            self.ip_status.config(text="✘  Save failed. Check debug log.", fg=RED)

    def _copy_log(self):
        log_file = get_log_file(self._gd())
        if not os.path.exists(log_file):
            self.log_status.config(text="⚠  No log file found yet.", fg=ACCENT)
            return
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                contents = f.read()
            self.clipboard_clear()
            self.clipboard_append(contents)
            self.log_status.config(text="✔  Log copied to clipboard.", fg=GREEN)
            log("User copied log to clipboard.", game_dir=self._gd())
        except Exception as e:
            log_exception("Copy log failed", e, game_dir=self._gd())
            self.log_status.config(text="✘  Could not read log.", fg=RED)

    def _clear_log(self):
        log_file = get_log_file(self._gd())
        if not os.path.exists(log_file):
            self.log_status.config(text="⚠  No log file to clear.", fg=ACCENT)
            return
        if not messagebox.askyesno("Clear Log",
                "This will permanently delete the debug log.\n\nContinue?"):
            return
        try:
            os.remove(log_file)
            self.log_status.config(text="✔  Log cleared.", fg=GREEN)
        except Exception as e:
            log_exception("Clear log failed", e, game_dir=self._gd())
            self.log_status.config(text="✘  Could not clear log.", fg=RED)

if __name__ == "__main__":
    app = App()
    app.mainloop()
