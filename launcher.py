#!/usr/bin/env python3
"""
KURO // ANIME — Windows Integration & Launcher Module
Provides:
- Backend server process lifecycle management and single-instance enforcement.
- Health endpoint polling and startup error diagnostics with log reporting.
- Browser detection (Chrome, Edge, Brave, Vivaldi, Firefox) with custom path override.
- Monitor positioning (--window-position=X,Y) and Kiosk/Windowed mode selection.
- High-DPI display scaling support.
- Graceful server shutdown and browser termination (zero orphaned processes).
- Optional Windows Startup folder registration/unregistration.
- Clean JSON configuration persistence (launcher_config.json).
"""

import os
import sys
import json
import time
import signal
import socket
import winreg
import logging
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from monitor_detector import MonitorDetector

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "launcher_config.json"
PID_FILE = BASE_DIR / ".kuro.pid"
PORT_FILE = BASE_DIR / ".kuro.port"
BROWSER_PID_FILE = BASE_DIR / ".kuro_browser.pid"
LOG_FILE = BASE_DIR / "kuro_server.log"
DEFAULT_PORT = 54321

DEFAULT_CONFIG: Dict[str, Any] = {
    "mode": "kiosk",               # "kiosk" | "windowed" | "fullscreen"
    "browser_path": "auto",        # "auto" or absolute executable path
    "target_monitor": "auto",      # "auto" | "primary" | "secondary" | "DISPLAY1" | "DISPLAY2"
    "window_width": 1920,
    "window_height": 1080,
    "high_dpi_scaling": True,
    "user_data_profile": True,
    "autostart_on_boot": False
}


def load_config() -> Dict[str, Any]:
    """Loads launcher preferences with fallback to defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.is_file():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> bool:
    """Persists launcher preferences to launcher_config.json."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"[KuroLauncher] Error saving configuration: {e}")
        return False


def get_active_port() -> int:
    """Retrieves port number recorded by server, or default."""
    if PORT_FILE.is_file():
        try:
            p = int(PORT_FILE.read_text(encoding="utf-8").strip())
            if 1024 <= p <= 65535:
                return p
        except Exception:
            pass
    return DEFAULT_PORT


def is_server_healthy(port: int, timeout: float = 1.0) -> bool:
    """Queries /api/health to verify server responsiveness."""
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        req = urllib.request.Request(url, headers={"Origin": f"http://127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") in ("healthy", "degraded")
    except Exception:
        pass
    return False


def is_pid_running(pid: int) -> bool:
    """Checks whether a process with the given PID is actively running."""
    if pid <= 0:
        return False
    try:
        # On Windows, PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def find_python_executable(prefer_silent: bool = False) -> str:
    """Locates pythonw.exe or python.exe."""
    cur_dir = Path(sys.executable).parent
    if prefer_silent:
        w_cand = cur_dir / "pythonw.exe"
        if w_cand.is_file():
            return str(w_cand)

    # Check sys.executable
    if os.path.isfile(sys.executable):
        return sys.executable

    return "python"


def detect_supported_browsers() -> List[Dict[str, str]]:
    """
    Scans Windows Registry (HKCU & HKLM App Paths) and standard filesystem paths
    to detect Chrome, Edge, Brave, Vivaldi, and Firefox installations.
    """
    browsers: List[Dict[str, str]] = []
    seen_paths = set()

    # 1. Windows Registry App Paths
    reg_targets = [
        ("chrome.exe", "Google Chrome", True),
        ("msedge.exe", "Microsoft Edge", True),
        ("brave.exe", "Brave Browser", True),
        ("vivaldi.exe", "Vivaldi", True),
        ("firefox.exe", "Mozilla Firefox", False),
    ]

    for key_root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for exe_name, label, is_chromium in reg_targets:
            sub_key = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_name}"
            try:
                with winreg.OpenKey(key_root, sub_key) as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.isfile(val) and val.lower() not in seen_paths:
                        seen_paths.add(val.lower())
                        browsers.append({
                            "name": label,
                            "path": val,
                            "is_chromium": is_chromium
                        })
            except OSError:
                pass

    # 2. Standard disk path checks
    disk_candidates = [
        (os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"), "Google Chrome", True),
        (os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"), "Google Chrome", True),
        (os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"), "Google Chrome", True),
        (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"), "Microsoft Edge", True),
        (os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"), "Microsoft Edge", True),
        (os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"), "Microsoft Edge", True),
        (os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"), "Brave Browser", True),
        (os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"), "Brave Browser", True),
        (os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"), "Mozilla Firefox", False),
    ]

    for cand_path, label, is_chromium in disk_candidates:
        if cand_path and os.path.isfile(cand_path) and cand_path.lower() not in seen_paths:
            seen_paths.add(cand_path.lower())
            browsers.append({
                "name": label,
                "path": cand_path,
                "is_chromium": is_chromium
            })

    return browsers


def get_browser_executable(custom_path: Optional[str] = None) -> Tuple[Optional[str], bool]:
    """
    Returns (executable_path, is_chromium).
    Prefers user-configured path, otherwise auto-detects Chromium in priority:
    Chrome -> Edge -> Brave -> Vivaldi -> Firefox -> System Default Fallback.
    """
    if custom_path and custom_path.lower() != "auto":
        cand = Path(custom_path)
        if cand.is_file():
            is_chrom = not ("firefox" in cand.name.lower())
            return str(cand), is_chrom

    detected = detect_supported_browsers()
    if detected:
        # Prefer chromium browsers for reliable --kiosk and --window-position support
        chromium_ones = [b for b in detected if b["is_chromium"]]
        if chromium_ones:
            return chromium_ones[0]["path"], True
        return detected[0]["path"], detected[0]["is_chromium"]

    return None, False


def start_backend(silent: bool = False, max_wait: float = 12.0) -> Tuple[bool, int, str]:
    """
    Ensures backend server is running.
    If not running, launches server.py and waits until /api/health responds.
    Returns (success, port, message).
    """
    port = get_active_port()

    # 1. Check if server is already responding
    if is_server_healthy(port):
        return True, port, f"Server already running on port {port}."

    # 2. Check if a lingering dead PID exists
    if PID_FILE.is_file():
        try:
            old_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if is_pid_running(old_pid):
                # Process is alive but maybe still booting, wait a moment
                time.sleep(1.0)
                if is_server_healthy(port):
                    return True, port, f"Server running on PID {old_pid} (port {port})."
            else:
                PID_FILE.unlink(missing_ok=True)
        except Exception:
            PID_FILE.unlink(missing_ok=True)

    # 3. Launch server in background
    py_exe = find_python_executable(prefer_silent=silent)
    server_script = str(BASE_DIR / "server.py")

    # Windows process creation flags: detach without visible console if silent
    creationflags = 0
    if sys.platform == "win32":
        # 0x08000000 = CREATE_NO_WINDOW
        # 0x00000008 = DETACHED_PROCESS
        # 0x00000200 = CREATE_NEW_PROCESS_GROUP
        flags = 0x00000008 | 0x00000200 # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        if silent:
            flags |= 0x08000000 # CREATE_NO_WINDOW
        creationflags = flags

    try:
        proc = subprocess.Popen(
            [py_exe, server_script, "--no-browser"],
            cwd=str(BASE_DIR),
            creationflags=creationflags,
            close_fds=True
        )
    except Exception as e:
        return False, port, f"Failed to spawn Python backend: {e}"

    # 4. Poll health endpoint until online
    start_t = time.time()
    booted_port = port

    while time.time() - start_t < max_wait:
        # Check active port file (server might bind to 54322+ on conflict)
        booted_port = get_active_port()
        if is_server_healthy(booted_port, timeout=0.6):
            return True, booted_port, f"Server successfully started on port {booted_port} (PID: {proc.pid})."
        time.sleep(0.3)

    # If timed out, read tail of server log for diagnostic error
    diag_msg = "Server did not respond within timeout."
    if LOG_FILE.is_file():
        try:
            lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            tail = [l for l in lines[-10:] if "ERROR" in l or "CRITICAL" in l or "Traceback" in l]
            if tail:
                diag_msg += "\nDiagnostics: " + "\n".join(tail)
        except Exception:
            pass

    return False, booted_port, diag_msg


def launch_browser(port: int, config: Dict[str, Any], override_mode: Optional[str] = None, override_monitor: Optional[str] = None) -> bool:
    """
    Launches browser pointed to screensaver with target monitor position,
    kiosk/fullscreen/windowed mode, and isolated profile.
    """
    mode = override_mode or config.get("mode", "kiosk")
    target_mon_id = override_monitor or config.get("target_monitor", "auto")
    browser_exe, is_chromium = get_browser_executable(config.get("browser_path"))

    target_url = f"http://127.0.0.1:{port}"

    # Resolve target monitor coordinates
    monitors = MonitorDetector.get_connected_monitors()
    target_mon = None

    if target_mon_id.lower() == "secondary":
        secondaries = [m for m in monitors if not m["primary"]]
        if secondaries:
            target_mon = secondaries[0]
    elif target_mon_id.lower() not in ("auto", "primary"):
        clean_id = target_mon_id.replace("\\\\.\\", "").strip().upper()
        for m in monitors:
            if m["id"].upper() == clean_id:
                target_mon = m
                break

    if not target_mon:
        # Default to primary or first available
        primaries = [m for m in monitors if m["primary"]]
        target_mon = primaries[0] if primaries else monitors[0]

    mon_left = target_mon["left"]
    mon_top = target_mon["top"]
    mon_width = target_mon["width"]
    mon_height = target_mon["height"]

    # If a supported Chromium browser was found
    if browser_exe and is_chromium:
        profile_dir = BASE_DIR / ".browser_profile"
        profile_dir.mkdir(exist_ok=True)

        args = [
            browser_exe,
            f"--app={target_url}",
            f"--window-position={mon_left},{mon_top}",
            f"--window-size={mon_width},{mon_height}",
            f"--user-data-dir={str(profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-translate",
            "--disable-infobars",
            "--disable-pinch",
            "--overscroll-history-navigation=0",
        ]

        # Display scaling & DPI
        if config.get("high_dpi_scaling", True):
            args.extend(["--high-dpi-support=1", "--force-device-scale-factor=1"])

        if mode == "kiosk":
            args.append("--kiosk")
        elif mode == "fullscreen":
            args.append("--start-fullscreen")
        elif mode == "windowed":
            win_w = config.get("window_width", 1280)
            win_h = config.get("window_height", 720)
            args = [
                browser_exe,
                f"--app={target_url}",
                f"--window-position={mon_left + 80},{mon_top + 60}",
                f"--window-size={win_w},{win_h}",
                f"--user-data-dir={str(profile_dir)}",
                "--no-first-run",
                "--no-default-browser-check"
            ]

        try:
            b_proc = subprocess.Popen(args, close_fds=True)
            BROWSER_PID_FILE.write_text(str(b_proc.pid), encoding="utf-8")
            print(f"[KuroLauncher] Browser launched in {mode.upper()} mode on {target_mon['name']} (PID: {b_proc.pid}).")
            return True
        except Exception as e:
            print(f"[KuroLauncher] Failed to start browser {browser_exe}: {e}")

    # Fallback to standard system browser
    print("[KuroLauncher] Using Windows system default browser fallback...")
    try:
        import webbrowser
        webbrowser.open(target_url)
        return True
    except Exception as e:
        print(f"[KuroLauncher] Fallback browser launch failed: {e}")
        return False


def stop_screensaver() -> Tuple[bool, str]:
    """
    Cleanly shuts down screensaver:
    1. Sends /api/shutdown to server so SQLite WAL is cleanly committed and checkpointed.
    2. Terminates browser process from .kuro_browser.pid.
    3. Confirms server process termination from .kuro.pid.
    4. Purges temporary PID files.
    """
    port = get_active_port()
    closed_browser = False
    closed_server = False

    # 1. Close browser process
    if BROWSER_PID_FILE.is_file():
        try:
            b_pid = int(BROWSER_PID_FILE.read_text(encoding="utf-8").strip())
            if is_pid_running(b_pid):
                subprocess.run(["taskkill", "/PID", str(b_pid), "/F", "/T"], capture_output=True)
                closed_browser = True
        except Exception:
            pass
        finally:
            BROWSER_PID_FILE.unlink(missing_ok=True)

    # 2. Graceful server shutdown request via HTTP
    if is_server_healthy(port):
        try:
            # Load session token from security module
            from security import SecurityManager
            sec = SecurityManager()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/shutdown",
                data=json.dumps({"session_token": sec.session_token}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{port}",
                    "X-Kuro-Token": sec.session_token
                }
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    closed_server = True
        except Exception:
            pass

    # 3. Wait for process exit, or force kill lingering PID
    if PID_FILE.is_file():
        try:
            s_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            time.sleep(0.5)
            if is_pid_running(s_pid):
                subprocess.run(["taskkill", "/PID", str(s_pid), "/F"], capture_output=True)
                closed_server = True
        except Exception:
            pass
        finally:
            PID_FILE.unlink(missing_ok=True)
            PORT_FILE.unlink(missing_ok=True)

    return True, "KuroAnime Screensaver stopped cleanly."


def manage_windows_startup(action: str) -> Tuple[bool, str]:
    """
    Manages autostart via Windows Startup Folder:
    %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\KuroAnime Screensaver.lnk
    """
    startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    if not startup_dir.is_dir():
        return False, "Windows Startup directory not found."

    shortcut_path = startup_dir / "KuroAnime Screensaver.lnk"
    vbs_path = BASE_DIR / "start_silent.vbs"

    if action == "status":
        enabled = shortcut_path.is_file()
        return True, f"Windows Startup: {'ENABLED' if enabled else 'DISABLED'}"

    elif action in ("enable", "install"):
        # Create shortcut via PowerShell WScript.Shell
        ps_cmd = f"""
        $wsh = New-Object -ComObject WScript.Shell;
        $s = $wsh.CreateShortcut('{str(shortcut_path)}');
        $s.TargetPath = 'wscript.exe';
        $s.Arguments = '"{str(vbs_path)}"';
        $s.WorkingDirectory = '{str(BASE_DIR)}';
        $s.Description = 'KURO // ANIME Screensaver Silent Launcher';
        $s.Save();
        """
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        if shortcut_path.is_file():
            cfg = load_config()
            cfg["autostart_on_boot"] = True
            save_config(cfg)
            return True, f"Successfully registered KuroAnime to Windows Startup: {shortcut_path.name}"
        else:
            return False, f"Could not create startup shortcut: {res.stderr}"

    elif action in ("disable", "remove", "uninstall"):
        if shortcut_path.is_file():
            shortcut_path.unlink(missing_ok=True)
        cfg = load_config()
        cfg["autostart_on_boot"] = False
        save_config(cfg)
        return True, "Removed KuroAnime from Windows Startup."

    return False, f"Unknown startup action: {action}"


def pin_to_start() -> Tuple[bool, str]:
    """
    Creates shortcuts in Start Menu and Desktop with high-DPI icon, and pins to Windows Start.
    """
    programs_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    desktop_dir = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if not programs_dir.is_dir():
        return False, "Windows Start Menu Programs directory not found."

    shortcut_name = "Kuro Anime Screensaver.lnk"
    start_shortcut = programs_dir / shortcut_name
    desktop_shortcut = desktop_dir / shortcut_name
    vbs_path = BASE_DIR / "start_silent.vbs"
    icon_path = BASE_DIR / "kuro.ico"

    ps_code = f"""
    $WshShell = New-Object -ComObject WScript.Shell

    $s1 = $WshShell.CreateShortcut('{str(start_shortcut)}')
    $s1.TargetPath = 'wscript.exe'
    $s1.Arguments = '"{str(vbs_path)}"'
    $s1.WorkingDirectory = '{str(BASE_DIR)}'
    if (Test-Path '{str(icon_path)}') {{
        $s1.IconLocation = '{str(icon_path)},0'
    }}
    $s1.Description = 'KURO // ANIME - Cinematic Ambient Screensaver'
    $s1.Save()

    if (Test-Path '{str(desktop_dir)}') {{
        $s2 = $WshShell.CreateShortcut('{str(desktop_shortcut)}')
        $s2.TargetPath = 'wscript.exe'
        $s2.Arguments = '"{str(vbs_path)}"'
        $s2.WorkingDirectory = '{str(BASE_DIR)}'
        if (Test-Path '{str(icon_path)}') {{
            $s2.IconLocation = '{str(icon_path)},0'
        }}
        $s2.Description = 'KURO // ANIME - Cinematic Ambient Screensaver'
        $s2.Save()
    }}

    $shell = New-Object -ComObject Shell.Application
    $folder = $shell.Namespace('{str(programs_dir)}')
    $item = $folder.ParseName('{shortcut_name}')
    if ($item) {{
        foreach ($verb in $item.Verbs()) {{
            $clean = $verb.Name -replace '&', ''
            if ($clean -match 'Pin to Start|pintostart') {{
                $verb.DoIt()
                break
            }}
        }}
    }}
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, text=True)
    if start_shortcut.is_file():
        return True, f"Kuro Anime Screensaver pinned to Windows Start & Desktop ({shortcut_name})"
    return False, "Could not create Start Menu shortcut."


def show_error_dialog(title: str, message: str):
    """Displays a native Windows error popup if running in silent mode or detached."""
    try:
        import ctypes
        # MB_OK | MB_ICONEXCLAMATION = 0x00000030
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x00000030)
    except Exception:
        print(f"[{title}] {message}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="KURO // ANIME Windows Integration & Launcher")
    parser.add_argument("command", choices=["start", "stop", "status", "startup", "pin"], nargs="?", default="start", help="Action to perform")
    parser.add_argument("--silent", action="store_true", help="Run without opening a console window")
    parser.add_argument("--windowed", action="store_true", help="Launch frontend in windowed mode instead of kiosk")
    parser.add_argument("--monitor", type=str, default=None, help="Target monitor device or ID (e.g. DISPLAY1, DISPLAY2, secondary)")
    parser.add_argument("--browser", type=str, default=None, help="Path to browser executable")
    parser.add_argument("startup_action", choices=["enable", "disable", "status"], nargs="?", default="status", help="Startup subcommand")

    args = parser.parse_args()
    config = load_config()

    if args.browser:
        config["browser_path"] = args.browser

    # Command: PIN
    if args.command == "pin":
        success, msg = pin_to_start()
        print(f"[KuroLauncher] {msg}")
        return 0 if success else 1

    # Command: STOP
    if args.command == "stop":
        success, msg = stop_screensaver()
        print(f"[KuroLauncher] {msg}")
        return 0

    # Command: STARTUP
    if args.command == "startup":
        action = args.startup_action
        success, msg = manage_windows_startup(action)
        print(f"[KuroLauncher] {msg}")
        return 0 if success else 1

    # Command: STATUS
    if args.command == "status":
        port = get_active_port()
        healthy = is_server_healthy(port)
        monitors = MonitorDetector.get_connected_monitors()
        print(f"Server Status: {'HEALTHY (127.0.0.1:' + str(port) + ')' if healthy else 'STOPPED'}")
        print(f"Monitors Detected: {len(monitors)}")
        for m in monitors:
            print(f"  - {m['name']} ({m['width']}x{m['height']} at {m['left']},{m['top']})")
        _, start_msg = manage_windows_startup("status")
        print(f"Startup: {start_msg}")
        return 0

    # Command: START
    if args.command == "start":
        mode_override = "windowed" if args.windowed else None

        # 1. Start server
        success, port, msg = start_backend(silent=args.silent)
        if not success:
            err_text = f"Screensaver backend failed to start!\n\n{msg}\n\nPlease check kuro_server.log for details."
            if args.silent:
                show_error_dialog("KuroAnime Screensaver Error", err_text)
            else:
                print(f"[KuroLauncher ERROR] {err_text}", file=sys.stderr)
            return 1

        print(f"[KuroLauncher] {msg}")

        # 2. Launch browser
        b_success = launch_browser(
            port=port,
            config=config,
            override_mode=mode_override,
            override_monitor=args.monitor
        )
        if not b_success:
            err_text = "Failed to launch web browser in kiosk mode.\nPlease ensure Google Chrome, Microsoft Edge, or Brave is installed."
            if args.silent:
                show_error_dialog("KuroAnime Browser Launch Warning", err_text)
            else:
                print(f"[KuroLauncher WARNING] {err_text}", file=sys.stderr)
            return 1

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
