import webview
import os, sys, shutil, subprocess, configparser, traceback, datetime, socket
import threading, re, json, base64

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

def log(message, error=False, game_dir=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "ERROR" if error else "INFO"
    try:
        with open(get_log_file(game_dir), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{prefix}] {message}\n")
    except: pass

def log_exception(context, exc, game_dir=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb = traceback.format_exc()
    try:
        with open(get_log_file(game_dir), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [ERROR] {context}: {exc}\n{tb}\n")
    except: pass

# ── network ───────────────────────────────────────────────────────────────────
def get_local_ips():
    ips = []
    seen = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None):
            ip = item[4][0]
            if ip not in seen and not ip.startswith("127.") and ":" not in ip:
                seen.add(ip)
                if ip.startswith("25."): label = f"Hamachi ({ip})"
                elif ip.startswith("100."): label = f"ZeroTier/Tailscale ({ip})"
                elif ip.startswith("10."): label = f"VPN/LAN ({ip})"
                elif ip.startswith("192.168."): label = f"Local Network ({ip})"
                elif ip.startswith("172."): label = f"Private Network ({ip})"
                else: label = f"Network ({ip})"
                ips.append({"label": label, "ip": ip})
    except: pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip not in seen:
            ips.append({"label": f"Primary Network ({ip})", "ip": ip})
    except: pass
    return ips

# ── ini helpers ───────────────────────────────────────────────────────────────
_converted_cache = set()

def _convert_comments(ini_path):
    if ini_path in _converted_cache:
        return
    try:
        with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "//" not in content:
            _converted_cache.add(ini_path)
            return
        converted = re.sub(r"^(\s*)//", r"\1#", content, flags=re.MULTILINE)
        if converted != content:
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write(converted)
        _converted_cache.add(ini_path)
    except: pass

def get_ini_path(game_dir): return os.path.join(game_dir, INI_REL)
def get_exe_path(game_dir): return os.path.join(game_dir, EXE_REL)

def read_server_addr(game_dir):
    ini_path = get_ini_path(game_dir)
    if not os.path.exists(ini_path): return ""
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
        if os.path.isdir(s): shutil.copytree(s, d, dirs_exist_ok=True)
        else: shutil.copy2(s, d)

# ── shortcuts ─────────────────────────────────────────────────────────────────
def create_shortcuts(target, shortcut_types, name="SCC LAN Launcher"):
    if sys.platform == "win32":
        for stype in shortcut_types:
            try:
                if stype == "desktop":
                    dest = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.lnk")
                elif stype == "startmenu":
                    dest = os.path.join(os.environ.get("APPDATA",""), "Microsoft","Windows","Start Menu","Programs", f"{name}.lnk")
                else: continue
                ps = f'''$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{dest}')
$s.TargetPath = '{target}'
$s.WorkingDirectory = '{os.path.dirname(target)}'
$s.Save()'''
                subprocess.Popen(["powershell", "-Command", ps],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass
    else:
        entry = f"[Desktop Entry]\nName={name}\nExec=\"{target}\"\nType=Application\nTerminal=false\nCategories=Game;\n"
        for stype in shortcut_types:
            try:
                if stype == "desktop":
                    dest = os.path.join(os.path.expanduser("~"), "Desktop", f"{name}.desktop")
                elif stype == "startmenu":
                    dest = os.path.join(os.path.expanduser("~"), ".local", "share", "applications", f"{name}.desktop")
                else: continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "w") as f: f.write(entry)
                os.chmod(dest, 0o755)
            except: pass

# ── API exposed to JS ─────────────────────────────────────────────────────────
class Api:
    def __init__(self):
        self.settings = load_settings()
        self.game_dir = self.settings.get("game_dir", "")
        self.setup_done = self.settings.get("setup_done", False)
        if self.game_dir and not os.path.isdir(self.game_dir):
            self.game_dir = ""
            self.setup_done = False
        log("Launcher started.", game_dir=self.game_dir or None)

    def get_state(self):
        return {
            "game_dir": self.game_dir,
            "setup_done": self.setup_done,
            "files_present": os.path.exists(get_exe_path(self.game_dir)) if self.game_dir else False
        }

    def browse_directory(self):
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            d = result[0]
            if os.path.basename(d).lower() == "src":
                return {"ok": False, "error": "Please select the main game folder, not src/"}
            self.game_dir = d
            self.settings["game_dir"] = d
            save_settings(self.settings)
            log(f"Game directory set: {d}", game_dir=d)
            return {"ok": True, "path": d}
        return {"ok": False, "error": "No directory selected"}

    def browse_dlc_directory(self):
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            return {"ok": True, "path": result[0]}
        return {"ok": False, "error": "No directory selected"}

    def install_files(self):
        if not self.game_dir:
            return {"ok": False, "error": "No game directory set"}
        try:
            log(f"Installing files to: {self.game_dir}", game_dir=self.game_dir)
            copy_src_to_dir(self.game_dir)
            log("Files copied successfully.", game_dir=self.game_dir)
            return {"ok": True}
        except Exception as e:
            log_exception("Install failed", e, self.game_dir)
            return {"ok": False, "error": str(e)}

    def install_dlc(self, dlc_path):
        if not self.game_dir:
            return {"ok": False, "error": "No game directory set"}
        try:
            log(f"Installing DLC from: {dlc_path}", game_dir=self.game_dir)
            copy_dlc_to_dir(dlc_path, self.game_dir)
            log("DLC installed successfully.", game_dir=self.game_dir)
            return {"ok": True}
        except Exception as e:
            log_exception("DLC install failed", e, self.game_dir)
            return {"ok": False, "error": str(e)}

    def get_server_addr(self):
        if not self.game_dir: return {"ok": True, "ip": ""}
        try:
            ip = read_server_addr(self.game_dir)
            return {"ok": True, "ip": ip}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_server_addr(self, ip):
        if not self.game_dir:
            return {"ok": False, "error": "No game directory set"}
        try:
            write_server_addr(self.game_dir, ip)
            log(f"Saving ServerAddr = {ip}", game_dir=self.game_dir)
            return {"ok": True}
        except Exception as e:
            log_exception("Save IP failed", e, self.game_dir)
            return {"ok": False, "error": str(e)}

    def get_local_ips(self):
        try:
            return {"ok": True, "ips": get_local_ips()}
        except Exception as e:
            return {"ok": False, "ips": []}

    def launch_helper(self):
        if not self.game_dir:
            return {"ok": False, "error": "No game directory set"}
        exe = get_exe_path(self.game_dir)
        if not os.path.exists(exe):
            return {"ok": False, "error": f"Cannot find: {exe}"}
        try:
            log(f"Launching: {exe}", game_dir=self.game_dir)
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
            return {"ok": True}
        except Exception as e:
            log_exception("Launch failed", e, self.game_dir)
            return {"ok": False, "error": str(e)}

    def finish_setup(self, launcher_shortcut, helper_shortcut, desktop, startmenu):
        shortcut_types = []
        if desktop: shortcut_types.append("desktop")
        if startmenu: shortcut_types.append("startmenu")
        if getattr(sys, "frozen", False):
            launcher_exe = sys.executable
        else:
            launcher_exe = os.path.abspath(__file__)
        helper_exe = get_exe_path(self.game_dir)
        if launcher_shortcut and shortcut_types:
            try:
                create_shortcuts(launcher_exe, shortcut_types, "SCC LAN Launcher")
                log(f"Launcher shortcuts: {shortcut_types}", game_dir=self.game_dir)
            except Exception as e:
                log_exception("Launcher shortcut failed", e, self.game_dir)
        if helper_shortcut and shortcut_types:
            try:
                create_shortcuts(helper_exe, shortcut_types, "SCC LAN Helper")
                log(f"Helper shortcuts: {shortcut_types}", game_dir=self.game_dir)
            except Exception as e:
                log_exception("Helper shortcut failed", e, self.game_dir)
        self.setup_done = True
        self.settings["setup_done"] = True
        save_settings(self.settings)
        return {"ok": True}

    def reset_settings(self, clear_dir):
        log("User triggered reset.", game_dir=self.game_dir)
        self.setup_done = False
        if clear_dir:
            self.game_dir = ""
            self.settings["game_dir"] = ""
        self.settings["setup_done"] = False
        save_settings(self.settings)
        return {"ok": True}

    def get_log(self):
        log_path = get_log_file(self.game_dir or None)
        try:
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    return {"ok": True, "path": log_path, "content": f.read()}
        except: pass
        return {"ok": True, "path": log_path, "content": ""}

    def clear_log(self):
        log_path = get_log_file(self.game_dir or None)
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

# ── HTML UI ───────────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>SCC LAN Launcher</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Share+Tech+Mono&display=swap');

  :root {
    --bg: #060608;
    --bg2: #0a0a0f;
    --panel: #0d0d12;
    --border: #1a1a24;
    --orange: #E8722A;
    --orange2: #a04d18;
    --orange3: #3a1a08;
    --orange-glow: rgba(232,114,42,0.15);
    --white: #F0EEE8;
    --dim: #3a3a40;
    --dim2: #1a1a20;
    --green: #4aff91;
    --green-glow: rgba(74,255,145,0.15);
    --red: #ff4a4a;
    --blue: #4a9fff;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--white);
    font-family: 'Share Tech Mono', 'Courier New', monospace;
    overflow: hidden;
    height: 100vh;
    display: flex;
    flex-direction: column;
    user-select: none;
  }

  /* ── scanlines overlay ── */
  body::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0,0,0,0.08) 2px,
      rgba(0,0,0,0.08) 4px
    );
    pointer-events: none;
    z-index: 9999;
  }

  /* ── noise overlay ── */
  body::after {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    opacity: 0.025;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 9998;
  }

  /* ── header ── */
  .header {
    background: var(--bg2);
    border-bottom: 2px solid var(--orange);
    padding: 10px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    position: relative;
  }
  .header::after {
    content: '';
    position: absolute;
    bottom: -6px; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, transparent, var(--orange-glow), transparent);
  }
  .header-left { display: flex; align-items: baseline; gap: 8px; }
  .header-tom { font-size: 10px; color: var(--dim); letter-spacing: 3px; }
  .header-title { font-family: 'Bebas Neue', sans-serif; font-size: 16px; color: var(--orange); letter-spacing: 4px; }
  .header-right { font-size: 10px; color: var(--dim); letter-spacing: 2px; }

  /* ── main content ── */
  #app {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0;
    scrollbar-width: thin;
    scrollbar-color: var(--orange2) var(--bg2);
  }
  #app::-webkit-scrollbar { width: 4px; }
  #app::-webkit-scrollbar-track { background: var(--bg2); }
  #app::-webkit-scrollbar-thumb { background: var(--orange2); }

  /* ── screens ── */
  .screen { display: none; padding: 20px; animation: fadeIn 0.3s ease; }
  .screen.active { display: block; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

  /* ── progress dots ── */
  .progress { display: flex; gap: 8px; justify-content: center; margin: 16px 0 24px; }
  .dot { width: 8px; height: 8px; border: 1px solid var(--dim); transform: rotate(45deg); transition: all 0.3s; }
  .dot.done { background: var(--orange); border-color: var(--orange); box-shadow: 0 0 8px var(--orange); }
  .dot.active { border-color: var(--orange); box-shadow: 0 0 4px var(--orange); }

  /* ── welcome screen ── */
  .eye-container { text-align: center; margin: 10px 0 20px; position: relative; }
  .eye-svg { width: 100%; max-width: 340px; }
  .welcome-title {
    font-family: 'Bebas Neue', sans-serif;
    font-size: clamp(32px, 6vw, 52px);
    color: var(--orange);
    letter-spacing: 8px;
    text-align: center;
    text-shadow: 0 0 30px rgba(232,114,42,0.5), 0 0 60px rgba(232,114,42,0.2);
    margin: 0 0 6px;
  }
  .welcome-sub {
    font-size: 10px;
    color: var(--dim);
    letter-spacing: 4px;
    text-align: center;
    margin-bottom: 20px;
  }
  .ghost-text {
    font-size: 9px;
    color: var(--orange2);
    letter-spacing: 4px;
    text-align: center;
    margin-bottom: 4px;
    opacity: 0.6;
  }
  .welcome-desc {
    text-align: center;
    font-size: 11px;
    color: var(--dim);
    line-height: 1.8;
    margin: 16px 0 24px;
    letter-spacing: 1px;
  }

  /* ── section label ── */
  .section-label {
    font-size: 9px;
    color: var(--dim);
    letter-spacing: 4px;
    margin: 16px 0 6px;
    padding-left: 2px;
  }

  /* ── hud panel ── */
  .hud-panel {
    background: var(--panel);
    border: 1px solid var(--border);
    position: relative;
    padding: 12px 16px;
    margin-bottom: 8px;
  }
  .hud-panel::before, .hud-panel::after,
  .hud-panel .corner-br, .hud-panel .corner-tl {
    content: '';
    position: absolute;
    width: 10px; height: 10px;
    border-color: var(--orange2);
    border-style: solid;
  }
  .hud-panel::before { top: -1px; left: -1px; border-width: 2px 0 0 2px; }
  .hud-panel::after  { top: -1px; right: -1px; border-width: 2px 2px 0 0; }
  .hud-panel .corner-bl { position: absolute; bottom: -1px; left: -1px; width: 10px; height: 10px; border: solid var(--orange2); border-width: 0 0 2px 2px; }
  .hud-panel .corner-br { position: absolute; bottom: -1px; right: -1px; width: 10px; height: 10px; border: solid var(--orange2); border-width: 0 2px 2px 0; }

  /* ── path display ── */
  .path-display {
    font-size: 10px;
    color: var(--white);
    word-break: break-all;
    line-height: 1.6;
    min-height: 20px;
  }
  .path-display.empty { color: var(--dim); font-style: italic; }

  /* ── inputs ── */
  .input-row { display: flex; align-items: center; gap: 10px; }
  .input-label { font-size: 10px; color: var(--dim); letter-spacing: 2px; white-space: nowrap; }
  input[type="text"] {
    flex: 1;
    background: var(--bg2);
    border: 1px solid var(--orange2);
    color: var(--orange);
    font-family: 'Bebas Neue', sans-serif;
    font-size: 18px;
    letter-spacing: 2px;
    padding: 6px 10px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  input[type="text"]:focus {
    border-color: var(--orange);
    box-shadow: 0 0 12px var(--orange-glow);
  }
  select {
    flex: 1;
    background: var(--bg2);
    border: 1px solid var(--orange2);
    color: var(--white);
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    padding: 6px 10px;
    outline: none;
    cursor: pointer;
  }
  select:focus { border-color: var(--orange); }

  /* ── checkboxes ── */
  .check-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; cursor: pointer; }
  .check-row input[type="checkbox"] { display: none; }
  .check-box {
    width: 14px; height: 14px;
    border: 1px solid var(--dim);
    transform: rotate(45deg);
    flex-shrink: 0;
    transition: all 0.2s;
    position: relative;
  }
  .check-row input:checked + .check-box {
    background: var(--orange);
    border-color: var(--orange);
    box-shadow: 0 0 8px var(--orange-glow);
  }
  .check-label { font-size: 11px; color: var(--white); letter-spacing: 1px; }

  /* ── buttons ── */
  .btn {
    background: var(--orange3);
    border: 1px solid var(--orange2);
    color: var(--orange);
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    letter-spacing: 2px;
    padding: 8px 18px;
    cursor: pointer;
    transition: all 0.15s;
    position: relative;
    overflow: hidden;
    white-space: nowrap;
  }
  .btn::before {
    content: '';
    position: absolute;
    top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(232,114,42,0.1), transparent);
    transition: left 0.4s;
  }
  .btn:hover::before { left: 100%; }
  .btn:hover {
    background: var(--orange2);
    border-color: var(--orange);
    color: var(--white);
    box-shadow: 0 0 16px var(--orange-glow);
  }
  .btn:active { transform: scale(0.97); }
  .btn:disabled { opacity: 0.3; cursor: not-allowed; }
  .btn:disabled:hover { background: var(--orange3); border-color: var(--orange2); color: var(--orange); box-shadow: none; }

  .btn-large {
    font-size: 13px;
    padding: 12px 24px;
    letter-spacing: 3px;
    width: 100%;
  }
  .btn-green {
    background: var(--green-glow);
    border-color: var(--green);
    color: var(--green);
  }
  .btn-green:hover { background: rgba(74,255,145,0.2); box-shadow: 0 0 16px var(--green-glow); }
  .btn-red {
    background: rgba(255,74,74,0.08);
    border-color: rgba(255,74,74,0.4);
    color: var(--red);
  }
  .btn-red:hover { background: rgba(255,74,74,0.15); box-shadow: 0 0 12px rgba(255,74,74,0.2); }
  .btn-blue {
    background: rgba(74,159,255,0.08);
    border-color: rgba(74,159,255,0.4);
    color: var(--blue);
  }
  .btn-blue:hover { background: rgba(74,159,255,0.15); }
  .btn-dim {
    background: transparent;
    border-color: var(--dim2);
    color: var(--dim);
  }
  .btn-dim:hover { border-color: var(--dim); color: var(--white); box-shadow: none; background: var(--dim2); }

  /* ── nav row ── */
  .nav-row { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; gap: 8px; }
  .nav-row .right { display: flex; gap: 8px; }

  /* ── status ── */
  .status {
    font-size: 10px;
    letter-spacing: 1px;
    margin-top: 8px;
    min-height: 16px;
    transition: all 0.3s;
  }
  .status.ok { color: var(--green); }
  .status.err { color: var(--red); }
  .status.warn { color: var(--orange); }

  /* ── divider ── */
  .divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 20px 0;
    position: relative;
  }
  .divider::after {
    content: '◆';
    position: absolute;
    left: 50%;
    top: -7px;
    transform: translateX(-50%);
    font-size: 8px;
    color: var(--orange2);
    background: var(--bg);
    padding: 0 6px;
  }

  /* ── screen title ── */
  .screen-title {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 22px;
    color: var(--orange);
    letter-spacing: 6px;
    margin-bottom: 4px;
  }
  .screen-desc {
    font-size: 10px;
    color: var(--dim);
    letter-spacing: 1px;
    line-height: 1.7;
    margin-bottom: 16px;
  }

  /* ── main screen layout ── */
  .main-grid { display: flex; flex-direction: column; gap: 4px; }
  .main-section { padding: 4px 0; }

  /* ── log viewer ── */
  .log-content {
    background: var(--bg2);
    border: 1px solid var(--border);
    padding: 10px;
    font-size: 9px;
    color: var(--dim);
    max-height: 120px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.6;
    scrollbar-width: thin;
    scrollbar-color: var(--orange2) var(--bg2);
  }

  /* ── loading spinner ── */
  .spinner {
    display: inline-block;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    0%  { content: '◆'; }
    25% { content: '◇'; }
    50% { content: '◆'; }
    75% { content: '◇'; }
  }

  /* ── pulse animation for online indicator ── */
  .pulse {
    display: inline-block;
    width: 6px; height: 6px;
    background: var(--green);
    border-radius: 50%;
    box-shadow: 0 0 6px var(--green);
    animation: pulse 2s ease-in-out infinite;
    margin-right: 6px;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--green); }
    50% { opacity: 0.4; box-shadow: 0 0 2px var(--green); }
  }

  /* ── boot animation ── */
  .boot-screen {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: var(--bg);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    z-index: 9000;
    transition: opacity 0.5s;
  }
  .boot-screen.fade-out { opacity: 0; pointer-events: none; }
  .boot-line {
    font-size: 10px; color: var(--orange2);
    letter-spacing: 2px; margin: 3px 0;
    opacity: 0;
    animation: bootLine 0.1s forwards;
  }
  @keyframes bootLine { to { opacity: 1; } }

  /* ── flicker animation ── */
  @keyframes flicker {
    0%, 100% { opacity: 1; }
    92% { opacity: 1; }
    93% { opacity: 0.4; }
    94% { opacity: 1; }
    96% { opacity: 0.6; }
    97% { opacity: 1; }
  }
  .flicker { animation: flicker 4s infinite; }

  /* ── eye animation ── */
  @keyframes eyePulse {
    0%, 100% { transform: scale(1); opacity: 0.8; }
    50% { transform: scale(1.05); opacity: 1; }
  }
  .eye-pulse { animation: eyePulse 3s ease-in-out infinite; }

  /* ── btn row ── */
  .btn-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }

  /* ── warning box ── */
  .warn-box {
    background: rgba(232,114,42,0.05);
    border: 1px solid var(--orange2);
    padding: 8px 12px;
    font-size: 10px;
    color: var(--orange);
    letter-spacing: 1px;
    margin-bottom: 12px;
  }
</style>
</head>
<body>

<!-- Boot screen -->
<div class="boot-screen" id="bootScreen">
  <div style="text-align:center">
    <svg width="80" height="50" viewBox="0 0 160 100">
      <ellipse cx="80" cy="50" rx="70" ry="28" fill="none" stroke="#E8722A" stroke-width="1.5" opacity="0.6"/>
      <circle cx="80" cy="50" r="16" fill="#E8722A" opacity="0.9" class="eye-pulse"/>
      <circle cx="80" cy="50" r="6" fill="#060608"/>
    </svg>
    <div id="bootLines" style="margin-top:16px"></div>
  </div>
</div>

<!-- Header -->
<div class="header">
  <div class="header-left">
    <span class="header-tom">TOM CLANCY'S</span>
    <span class="header-title">SPLINTER CELL: CONVICTION</span>
  </div>
  <div class="header-right" id="headerRight">LAN LAUNCHER</div>
</div>

<!-- App -->
<div id="app">

  <!-- ── SCREEN 0: WELCOME ── -->
  <div class="screen active" id="screen-0">
    <div class="progress" id="progress-0">
      <div class="dot active"></div>
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>

    <div class="eye-container">
      <svg class="eye-svg flicker" viewBox="0 0 400 160" xmlns="http://www.w3.org/2000/svg">
        <!-- bracket corners -->
        <polyline points="0,30 0,0 30,0" fill="none" stroke="#a04d18" stroke-width="1"/>
        <polyline points="370,0 400,0 400,30" fill="none" stroke="#a04d18" stroke-width="1"/>
        <polyline points="0,130 0,160 30,160" fill="none" stroke="#a04d18" stroke-width="1"/>
        <polyline points="370,160 400,160 400,130" fill="none" stroke="#a04d18" stroke-width="1"/>
        <!-- eye outer -->
        <ellipse cx="200" cy="80" rx="120" ry="48" fill="none" stroke="#E8722A" stroke-width="1.5" opacity="0.7"/>
        <!-- eye inner glow -->
        <ellipse cx="200" cy="80" rx="100" ry="38" fill="none" stroke="#E8722A" stroke-width="0.5" opacity="0.3"/>
        <!-- iris -->
        <circle cx="200" cy="80" r="28" fill="none" stroke="#E8722A" stroke-width="1.5" opacity="0.9"/>
        <circle cx="200" cy="80" r="28" fill="rgba(232,114,42,0.08)"/>
        <!-- pupil -->
        <circle cx="200" cy="80" r="10" fill="#E8722A" opacity="0.95" class="eye-pulse"/>
        <circle cx="200" cy="80" r="4" fill="#060608"/>
        <!-- scan lines on eye -->
        <line x1="80" y1="80" x2="172" y2="80" stroke="#a04d18" stroke-width="0.5" opacity="0.5"/>
        <line x1="228" y1="80" x2="320" y2="80" stroke="#a04d18" stroke-width="0.5" opacity="0.5"/>
        <!-- target reticle -->
        <circle cx="200" cy="80" r="44" fill="none" stroke="#3a1a08" stroke-width="1" stroke-dasharray="4,8"/>
      </svg>
    </div>

    <div class="ghost-text">[ LAST KNOWN POSITION ]</div>
    <div class="welcome-title flicker" id="welcomeTitle">SCC LAN LAUNCHER</div>
    <div class="welcome-sub" id="welcomeSub">FOURTH ECHELON  ·  NETWORK CONFIGURATION SYSTEM</div>

    <hr class="divider">

    <div class="welcome-desc">
      This utility configures your LAN connection<br>
      for Splinter Cell: Conviction FusionFix.<br><br>
      Complete each step to initialize the system.
    </div>

    <button class="btn btn-large" onclick="goToStep(1)">▶  INITIALIZE SETUP</button>
  </div>

  <!-- ── SCREEN 1: DIRECTORY ── -->
  <div class="screen" id="screen-1">
    <div class="progress" id="progress-1"></div>
    <div class="screen-title">GAME DIRECTORY</div>
    <div class="screen-desc">
      Select the root folder of your Splinter Cell: Conviction installation.<br>
      Do NOT select the src/ subfolder — select the main game folder.
    </div>

    <div class="section-label">CURRENT PATH</div>
    <div class="hud-panel">
      <div class="corner-bl"></div><div class="corner-br"></div>
      <div class="path-display empty" id="dirDisplay">No directory selected</div>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="browseDir()">📁  BROWSE</button>
    </div>
    <div class="status" id="dirStatus"></div>

    <hr class="divider">
    <div class="nav-row">
      <button class="btn btn-dim" onclick="goToStep(0)">◀  BACK</button>
      <button class="btn" onclick="nextFromDir()">NEXT  ▶</button>
    </div>
  </div>

  <!-- ── SCREEN 2: DLC ── -->
  <div class="screen" id="screen-2">
    <div class="progress" id="progress-2"></div>
    <div class="screen-title">OPTIONAL DLC</div>
    <div class="screen-desc">
      Install the Insurgency Pack DLC before copying main files.<br>
      Extract the DLC .zip first, then select the extracted folder.<br>
      You can skip this and install DLC later from the main screen.
    </div>
    <div class="btn-row">
      <button class="btn btn-blue" id="dlcBtn2" onclick="installDLC2()">📦  INSTALL INSURGENCY PACK DLC</button>
    </div>
    <div class="status" id="dlcStatus2"></div>

    <hr class="divider">
    <div class="nav-row">
      <button class="btn btn-dim" onclick="goToStep(1)">◀  BACK</button>
      <div class="right">
        <button class="btn btn-dim" onclick="goToStep(3)">SKIP  ▶</button>
        <button class="btn" onclick="goToStep(3)">NEXT  ▶</button>
      </div>
    </div>
  </div>

  <!-- ── SCREEN 3: INSTALL ── -->
  <div class="screen" id="screen-3">
    <div class="progress" id="progress-3"></div>
    <div class="screen-title">INSTALL FILES</div>
    <div class="screen-desc" id="installDesc">Files will be copied to your game directory.</div>

    <div class="btn-row">
      <button class="btn btn-large" id="installBtn" onclick="installFiles()">▶  INSTALL FILES</button>
    </div>
    <div class="status" id="installStatus"></div>

    <hr class="divider">
    <div class="nav-row">
      <button class="btn btn-dim" onclick="goToStep(2)">◀  BACK</button>
      <button class="btn" id="installNextBtn" onclick="nextFromInstall()" disabled>NEXT  ▶</button>
    </div>
  </div>

  <!-- ── SCREEN 4: IP ── -->
  <div class="screen" id="screen-4">
    <div class="progress" id="progress-4"></div>
    <div class="screen-title">SERVER ADDRESS</div>
    <div class="screen-desc">
      Set the ServerAddr for LAN play. Select a detected network interface or enter manually.
    </div>

    <div class="section-label">DETECTED INTERFACES</div>
    <div class="hud-panel">
      <div class="corner-bl"></div><div class="corner-br"></div>
      <div class="input-row">
        <select id="netSelect4"><option>Scanning...</option></select>
        <button class="btn" onclick="useDetectedIP(4)">USE</button>
      </div>
    </div>

    <div class="section-label">MANUAL ENTRY</div>
    <div class="hud-panel">
      <div class="corner-bl"></div><div class="corner-br"></div>
      <div class="input-row">
        <span class="input-label">ServerAddr :</span>
        <input type="text" id="ipInput4" placeholder="0.0.0.0">
      </div>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="saveIP(4)">💾  SAVE IP</button>
    </div>
    <div class="status" id="ipStatus4"></div>

    <hr class="divider">
    <div class="nav-row">
      <button class="btn btn-dim" onclick="goToStep(3)">◀  BACK</button>
      <button class="btn" onclick="goToStep(5)">NEXT  ▶</button>
    </div>
  </div>

  <!-- ── SCREEN 5: SHORTCUTS ── -->
  <div class="screen" id="screen-5">
    <div class="progress" id="progress-5"></div>
    <div class="screen-title">CREATE SHORTCUTS</div>
    <div class="screen-desc">
      Optionally create shortcuts for quick access.<br>
      The launcher stays wherever you saved it.
    </div>

    <div class="section-label">SHORTCUT LOCATION</div>
    <div class="hud-panel">
      <div class="corner-bl"></div><div class="corner-br"></div>
      <label class="check-row">
        <input type="checkbox" id="desktopCheck" checked>
        <div class="check-box"></div>
        <span class="check-label">Desktop</span>
      </label>
      <label class="check-row">
        <input type="checkbox" id="startmenuCheck">
        <div class="check-box"></div>
        <span class="check-label">Start Menu / App Launcher</span>
      </label>
    </div>

    <div class="section-label">CREATE SHORTCUT FOR</div>
    <div class="hud-panel">
      <div class="corner-bl"></div><div class="corner-br"></div>
      <label class="check-row">
        <input type="checkbox" id="launcherShortcut" checked>
        <div class="check-box"></div>
        <span class="check-label">SCC LAN Launcher  (this app)</span>
      </label>
      <label class="check-row">
        <input type="checkbox" id="helperShortcut" checked>
        <div class="check-box"></div>
        <span class="check-label">SCC LAN Helper  (game helper exe)</span>
      </label>
    </div>
    <div class="status" id="shortcutStatus"></div>

    <hr class="divider">
    <div class="nav-row">
      <button class="btn btn-dim" onclick="goToStep(4)">◀  BACK</button>
      <button class="btn btn-green btn-large" style="width:auto;padding:12px 32px" onclick="finishSetup()">✔  FINISH</button>
    </div>
  </div>

  <!-- ── SCREEN 6: MAIN ── -->
  <div class="screen" id="screen-6">
    <div class="main-grid">

      <!-- Status bar -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-family:'Bebas Neue',sans-serif;font-size:20px;color:var(--orange);letter-spacing:5px">SCC LAN LAUNCHER</div>
        <div style="font-size:9px;color:var(--green);display:flex;align-items:center"><span class="pulse"></span>SYSTEM ONLINE</div>
      </div>

      <div class="hud-panel" style="margin-bottom:12px">
        <div class="corner-bl"></div><div class="corner-br"></div>
        <div style="font-size:9px;color:var(--dim);letter-spacing:2px;margin-bottom:4px">GAME DIRECTORY</div>
        <div class="path-display" id="mainDirDisplay"></div>
      </div>

      <hr class="divider">

      <!-- IP Section -->
      <div class="section-label">SERVER ADDRESS</div>
      <div class="hud-panel">
        <div class="corner-bl"></div><div class="corner-br"></div>
        <div style="margin-bottom:10px">
          <div style="font-size:9px;color:var(--dim);letter-spacing:2px;margin-bottom:6px">DETECTED INTERFACES</div>
          <div class="input-row">
            <select id="netSelectMain"><option>Scanning...</option></select>
            <button class="btn" onclick="useDetectedIP('main')">USE</button>
          </div>
        </div>
        <div>
          <div style="font-size:9px;color:var(--dim);letter-spacing:2px;margin-bottom:6px">SERVER ADDR</div>
          <div class="input-row">
            <input type="text" id="ipInputMain" placeholder="0.0.0.0" style="font-size:22px">
            <button class="btn" onclick="saveIP('main')">💾  SAVE</button>
          </div>
        </div>
      </div>
      <div class="status" id="ipStatusMain"></div>

      <hr class="divider">

      <!-- Launch -->
      <div class="section-label">LAUNCH</div>
      <button class="btn btn-green btn-large" onclick="launchHelper()">⬛  LAUNCH SCC LAN HELPER</button>
      <div class="status" id="launchStatus"></div>

      <hr class="divider">

      <!-- Actions -->
      <div class="section-label">ACTIONS</div>
      <div class="btn-row">
        <button class="btn" id="reinstallBtn" onclick="reinstallFiles()">▶  REINSTALL FILES</button>
        <button class="btn btn-blue" id="dlcBtnMain" onclick="installDLCMain()">📦  INSTALL DLC</button>
      </div>
      <div class="status" id="actionStatus"></div>

      <hr class="divider">

      <!-- Settings -->
      <div class="section-label">SETTINGS</div>
      <div class="btn-row">
        <button class="btn btn-dim" onclick="reconfigure()">⟳  RECONFIGURE PATH</button>
        <button class="btn btn-red" onclick="resetSettings()">↺  RESET SETTINGS</button>
      </div>

      <hr class="divider">

      <!-- Debug Log -->
      <div class="section-label">DEBUG LOG</div>
      <div class="log-content" id="logContent">Loading...</div>
      <div class="status" id="logStatus"></div>
      <div class="btn-row" style="margin-top:8px">
        <button class="btn" onclick="copyLog()">📋  COPY LOG</button>
        <button class="btn btn-red" onclick="clearLog()">🗑  CLEAR LOG</button>
      </div>

    </div>
  </div>

</div><!-- end #app -->

<script>
// ── state ──────────────────────────────────────────────────────────────────
let state = {};
let netMap = {};
let netMapMain = {};

// ── boot sequence ─────────────────────────────────────────────────────────
const bootLines = [
  "FOURTH ECHELON NETWORK SYSTEM v4.6",
  "INITIALIZING SECURE CHANNEL...",
  "LOADING CONVICTION PROTOCOL...",
  "LAN SUBSYSTEM ONLINE",
  "READY."
];

async function boot() {
  const container = document.getElementById('bootLines');
  for (let i = 0; i < bootLines.length; i++) {
    await delay(180);
    const d = document.createElement('div');
    d.className = 'boot-line';
    d.style.animationDelay = '0s';
    d.textContent = bootLines[i];
    container.appendChild(d);
  }
  await delay(400);
  document.getElementById('bootScreen').classList.add('fade-out');
  await delay(500);
  document.getElementById('bootScreen').remove();

  // Load state and show correct screen
  state = await pywebview.api.get_state();
  if (state.setup_done && state.game_dir) {
    showMain();
  } else {
    updateDirDisplay();
  }
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── progress dots ──────────────────────────────────────────────────────────
function renderProgress(screenId, current) {
  const el = document.getElementById('progress-' + screenId);
  if (!el) return;
  let html = '';
  for (let i = 0; i < 6; i++) {
    if (i < current) html += '<div class="dot done"></div>';
    else if (i === current) html += '<div class="dot active"></div>';
    else html += '<div class="dot"></div>';
  }
  el.innerHTML = html;
}

// ── screen navigation ──────────────────────────────────────────────────────
function goToStep(n) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-' + n).classList.add('active');
  renderProgress(n, n);
  document.getElementById('headerRight').textContent = n < 6 ? `SETUP  ${n}/5` : 'LAN LAUNCHER';
  document.getElementById('app').scrollTop = 0;

  if (n === 4) loadIPScreen();
  if (n === 6) showMain();
}

function showMain() {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-6').classList.add('active');
  document.getElementById('headerRight').textContent = 'LAN LAUNCHER';
  document.getElementById('app').scrollTop = 0;
  document.getElementById('mainDirDisplay').textContent = state.game_dir || 'Not set';
  loadIPMain();
  loadLog();
  scanNetsMain();
}

// ── directory ──────────────────────────────────────────────────────────────
function updateDirDisplay() {
  const el = document.getElementById('dirDisplay');
  if (state.game_dir) {
    el.textContent = state.game_dir;
    el.classList.remove('empty');
  } else {
    el.textContent = 'No directory selected';
    el.classList.add('empty');
  }
}

async function browseDir() {
  setStatus('dirStatus', 'warn', 'Opening folder browser...');
  const res = await pywebview.api.browse_directory();
  if (res.ok) {
    state.game_dir = res.path;
    updateDirDisplay();
    setStatus('dirStatus', 'ok', 'Directory set: ' + res.path);
    document.getElementById('installDesc').textContent = 'Files will be copied to: ' + res.path;
  } else {
    setStatus('dirStatus', 'err', res.error || 'Cancelled');
  }
}

function nextFromDir() {
  if (!state.game_dir) {
    setStatus('dirStatus', 'warn', 'Please select a game directory first.');
    return;
  }
  goToStep(2);
}

// ── DLC ────────────────────────────────────────────────────────────────────
async function installDLC2() {
  setStatus('dlcStatus2', 'warn', 'Opening folder browser...');
  setBtnLoading('dlcBtn2', true, 'Installing...');
  const folderRes = await pywebview.api.browse_dlc_directory();
  if (!folderRes.ok) {
    setStatus('dlcStatus2', 'warn', 'Cancelled.');
    setBtnLoading('dlcBtn2', false, '📦  INSTALL INSURGENCY PACK DLC');
    return;
  }
  setStatus('dlcStatus2', 'warn', 'Copying DLC files...');
  const res = await pywebview.api.install_dlc(folderRes.path);
  setBtnLoading('dlcBtn2', false, '📦  INSTALL INSURGENCY PACK DLC');
  if (res.ok) setStatus('dlcStatus2', 'ok', 'Insurgency Pack DLC installed successfully.');
  else setStatus('dlcStatus2', 'err', 'DLC install failed: ' + res.error);
}

// ── install files ──────────────────────────────────────────────────────────
async function installFiles() {
  setBtnLoading('installBtn', true, 'Copying files...');
  setStatus('installStatus', 'warn', 'Copying files to game directory...');
  const res = await pywebview.api.install_files();
  setBtnLoading('installBtn', false, '▶  INSTALL FILES');
  if (res.ok) {
    setStatus('installStatus', 'ok', 'Files installed successfully.');
    document.getElementById('installNextBtn').disabled = false;
  } else {
    setStatus('installStatus', 'err', 'Install failed: ' + res.error);
  }
}

function nextFromInstall() {
  goToStep(4);
}

// ── IP ─────────────────────────────────────────────────────────────────────
let ipNetMap4 = {};
let ipNetMapMain = {};

async function loadIPScreen() {
  const res = await pywebview.api.get_server_addr();
  if (res.ok) document.getElementById('ipInput4').value = res.ip || '';
  scanNets4();
}

async function scanNets4() {
  const res = await pywebview.api.get_local_ips();
  const sel = document.getElementById('netSelect4');
  ipNetMap4 = {};
  if (res.ok && res.ips.length > 0) {
    sel.innerHTML = res.ips.map(i => `<option value="${i.ip}">${i.label}</option>`).join('');
    res.ips.forEach(i => ipNetMap4[i.ip] = i.ip);
  } else {
    sel.innerHTML = '<option>No interfaces detected</option>';
  }
}

async function loadIPMain() {
  const res = await pywebview.api.get_server_addr();
  if (res.ok) document.getElementById('ipInputMain').value = res.ip || '';
}

async function scanNetsMain() {
  const res = await pywebview.api.get_local_ips();
  const sel = document.getElementById('netSelectMain');
  ipNetMapMain = {};
  if (res.ok && res.ips.length > 0) {
    sel.innerHTML = res.ips.map(i => `<option value="${i.ip}">${i.label}</option>`).join('');
  } else {
    sel.innerHTML = '<option>No interfaces detected</option>';
  }
}

function useDetectedIP(screen) {
  if (screen === 4) {
    const sel = document.getElementById('netSelect4');
    document.getElementById('ipInput4').value = sel.value;
    setStatus('ipStatus4', 'ok', 'IP set from interface.');
  } else {
    const sel = document.getElementById('netSelectMain');
    document.getElementById('ipInputMain').value = sel.value;
    setStatus('ipStatusMain', 'ok', 'IP set from interface.');
  }
}

async function saveIP(screen) {
  const inputId = screen === 4 ? 'ipInput4' : 'ipInputMain';
  const statusId = screen === 4 ? 'ipStatus4' : 'ipStatusMain';
  const ip = document.getElementById(inputId).value.trim();
  if (!ip) { setStatus(statusId, 'warn', 'Enter an IP address.'); return; }
  setStatus(statusId, 'warn', 'Saving...');
  const res = await pywebview.api.save_server_addr(ip);
  if (res.ok) setStatus(statusId, 'ok', `Saved  ServerAddr = ${ip}`);
  else setStatus(statusId, 'err', 'Save failed: ' + res.error);
}

// ── shortcuts + finish ─────────────────────────────────────────────────────
async function finishSetup() {
  const launcher = document.getElementById('launcherShortcut').checked;
  const helper = document.getElementById('helperShortcut').checked;
  const desktop = document.getElementById('desktopCheck').checked;
  const startmenu = document.getElementById('startmenuCheck').checked;
  setStatus('shortcutStatus', 'warn', 'Creating shortcuts...');
  const res = await pywebview.api.finish_setup(launcher, helper, desktop, startmenu);
  if (res.ok) {
    state.setup_done = true;
    setStatus('shortcutStatus', 'ok', 'Setup complete!');
    await delay(600);
    showMain();
  } else {
    setStatus('shortcutStatus', 'err', 'Error: ' + res.error);
  }
}

// ── main screen actions ────────────────────────────────────────────────────
async function launchHelper() {
  setStatus('launchStatus', 'warn', 'Launching...');
  const res = await pywebview.api.launch_helper();
  if (res.ok) setStatus('launchStatus', 'ok', 'Launched successfully.');
  else setStatus('launchStatus', 'err', 'Launch failed: ' + res.error);
}

async function reinstallFiles() {
  setBtnLoading('reinstallBtn', true, 'Copying...');
  setStatus('actionStatus', 'warn', 'Copying files...');
  const res = await pywebview.api.install_files();
  setBtnLoading('reinstallBtn', false, '▶  REINSTALL FILES');
  if (res.ok) setStatus('actionStatus', 'ok', 'Files reinstalled.');
  else setStatus('actionStatus', 'err', 'Reinstall failed: ' + res.error);
}

async function installDLCMain() {
  setBtnLoading('dlcBtnMain', true, 'Installing...');
  const folderRes = await pywebview.api.browse_dlc_directory();
  if (!folderRes.ok) { setBtnLoading('dlcBtnMain', false, '📦  INSTALL DLC'); return; }
  setStatus('actionStatus', 'warn', 'Copying DLC files...');
  const res = await pywebview.api.install_dlc(folderRes.path);
  setBtnLoading('dlcBtnMain', false, '📦  INSTALL DLC');
  if (res.ok) setStatus('actionStatus', 'ok', 'DLC installed.');
  else setStatus('actionStatus', 'err', 'DLC failed: ' + res.error);
}

function reconfigure() {
  if (confirm('Change the game directory? This will restart the setup wizard.')) {
    const also = confirm('Also clear the saved IP and reinstall flag?');
    pywebview.api.reset_settings(also).then(() => {
      state.setup_done = false;
      if (also) state.game_dir = '';
      updateDirDisplay();
      goToStep(also ? 0 : 1);
    });
  }
}

function resetSettings() {
  if (confirm('Reset all settings? You will be returned to setup.')) {
    const also = confirm('Also clear the game directory path?');
    pywebview.api.reset_settings(also).then(() => {
      state.setup_done = false;
      if (also) state.game_dir = '';
      updateDirDisplay();
      goToStep(0);
    });
  }
}

// ── log ────────────────────────────────────────────────────────────────────
async function loadLog() {
  const res = await pywebview.api.get_log();
  const el = document.getElementById('logContent');
  if (res.content) {
    el.textContent = res.content;
    el.scrollTop = el.scrollHeight;
  } else {
    el.textContent = 'No log entries yet.';
  }
}

async function copyLog() {
  const res = await pywebview.api.get_log();
  if (res.content) {
    try {
      await navigator.clipboard.writeText(res.content);
      setStatus('logStatus', 'ok', 'Log copied to clipboard.');
    } catch(e) {
      // Fallback for Wine
      const ta = document.createElement('textarea');
      ta.value = res.content;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setStatus('logStatus', 'ok', 'Log copied to clipboard.');
    }
  } else {
    setStatus('logStatus', 'warn', 'No log to copy.');
  }
}

async function clearLog() {
  if (confirm('Delete the debug log? This cannot be undone.')) {
    const res = await pywebview.api.clear_log();
    if (res.ok) { setStatus('logStatus', 'ok', 'Log cleared.'); loadLog(); }
    else setStatus('logStatus', 'err', 'Could not clear log.');
  }
}

// ── helpers ────────────────────────────────────────────────────────────────
function setStatus(id, type, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'status ' + type;
  el.textContent = (type === 'ok' ? '✔  ' : type === 'err' ? '✘  ' : '⚠  ') + msg;
}

function clearStatus(id) {
  const el = document.getElementById(id);
  if (el) { el.className = 'status'; el.textContent = ''; }
}

function setBtnLoading(id, loading, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.disabled = loading;
  el.textContent = text;
}

// ── start ──────────────────────────────────────────────────────────────────
window.addEventListener('pywebviewready', boot);
</script>
</body>
</html>
"""

# ── entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        "SCC LAN Launcher",
        html=HTML,
        js_api=api,
        width=640,
        height=780,
        min_size=(520, 600),
        background_color="#060608",
        text_select=False
    )
    webview.start(debug=False)
