"""
KURO // ANIME — Windows Multi-Monitor & Display Detection Engine
Enumerates physical displays, virtual desktops, resolutions, orientations,
and aspect ratios using pure Python standard library (ctypes user32).
"""

import sys
from typing import List, Dict, Any, Optional

# Supported target resolutions
SUPPORTED_RESOLUTIONS = {
    "1920x1080": {"name": "Full HD 1080p", "ratio": "16:9", "orientation": "landscape"},
    "2560x1440": {"name": "QHD 1440p", "ratio": "16:9", "orientation": "landscape"},
    "3840x2160": {"name": "4K UHD 2160p", "ratio": "16:9", "orientation": "landscape"},
    "3440x1440": {"name": "Ultrawide QHD", "ratio": "21:9", "orientation": "ultrawide"},
    "2560x1080": {"name": "Ultrawide FHD", "ratio": "21:9", "orientation": "ultrawide"},
    "5120x1440": {"name": "Super Ultrawide", "ratio": "32:9", "orientation": "ultrawide"},
    "1080x1920": {"name": "Portrait Full HD", "ratio": "9:16", "orientation": "portrait"},
    "1440x2560": {"name": "Portrait QHD", "ratio": "9:16", "orientation": "portrait"},
    "2160x3840": {"name": "Portrait 4K", "ratio": "9:16", "orientation": "portrait"},
}


class MonitorDetector:
    @staticmethod
    def classify_orientation(width: int, height: int) -> str:
        """Determines orientation: portrait, ultrawide, or landscape."""
        if height <= 0 or width <= 0:
            return "landscape"
        aspect = width / height
        if height > width:
            return "portrait"
        elif aspect >= 2.05:
            return "ultrawide"
        else:
            return "landscape"

    @staticmethod
    def get_ratio_name(width: int, height: int) -> str:
        """Returns standard ratio string (e.g. 16:9, 21:9, 9:16)."""
        if height <= 0 or width <= 0:
            return "16:9"
        aspect = width / height
        if height > width:
            return "9:16"
        elif aspect >= 2.9:
            return "32:9"
        elif aspect >= 2.05:
            return "21:9"
        elif abs(aspect - 16 / 10) < 0.08:
            return "16:10"
        elif abs(aspect - 16 / 9) < 0.08:
            return "16:9"
        elif abs(aspect - 4 / 3) < 0.08:
            return "4:3"
        return f"{round(aspect, 2)}:1"

    @classmethod
    def get_resolution_profile(cls, width: int, height: int) -> Dict[str, str]:
        """Resolves known resolution profile details."""
        key = f"{width}x{height}"
        if key in SUPPORTED_RESOLUTIONS:
            return SUPPORTED_RESOLUTIONS[key]

        orient = cls.classify_orientation(width, height)
        ratio = cls.get_ratio_name(width, height)
        return {
            "name": f"{width}×{height}",
            "ratio": ratio,
            "orientation": orient
        }

    @classmethod
    def get_connected_monitors(cls) -> List[Dict[str, Any]]:
        """
        Enumerates all connected physical displays on Windows via user32.EnumDisplayMonitors.
        Falls back to a standard default if running on a non-Windows platform or headless.
        """
        monitors: List[Dict[str, Any]] = []

        if sys.platform != "win32":
            # Portable fallback for testing/non-Windows environments
            monitors.append({
                "id": "DISPLAY1",
                "device": "\\\\.\\DISPLAY1",
                "name": "Display 1: Full HD 1080p (16:9) [Primary]",
                "width": 1920,
                "height": 1080,
                "left": 0,
                "top": 0,
                "primary": True,
                "orientation": "landscape",
                "ratio": "16:9",
                "profile": "Full HD 1080p"
            })
            return monitors

        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            class MONITORINFOEXW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32),
                ]

            def _enum_callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                info = MONITORINFOEXW()
                info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
                    w = info.rcMonitor.right - info.rcMonitor.left
                    h = info.rcMonitor.bottom - info.rcMonitor.top
                    dev_name = info.szDevice
                    mon_id = dev_name.replace("\\\\.\\", "").strip()
                    is_primary = bool(info.dwFlags & 1)

                    profile = cls.get_resolution_profile(w, h)
                    role = "Primary" if is_primary else "Secondary"
                    idx = len(monitors) + 1

                    monitors.append({
                        "id": mon_id,
                        "device": dev_name,
                        "name": f"Monitor {idx}: {profile['name']} ({profile['ratio']}) [{role}]",
                        "width": w,
                        "height": h,
                        "left": info.rcMonitor.left,
                        "top": info.rcMonitor.top,
                        "primary": is_primary,
                        "orientation": profile["orientation"],
                        "ratio": profile["ratio"],
                        "profile": profile["name"],
                    })
                return 1

            MONITORENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_int,
                wintypes.HMONITOR,
                wintypes.HDC,
                ctypes.POINTER(RECT),
                wintypes.LPARAM,
            )
            ctypes.windll.user32.EnumDisplayMonitors(
                None, None, MONITORENUMPROC(_enum_callback), 0
            )

        except Exception as e:
            print(f"[KuroMonitor] Error enumerating monitors: {e}")

        if not monitors:
            monitors.append({
                "id": "DISPLAY1",
                "device": "\\\\.\\DISPLAY1",
                "name": "Monitor 1: Full HD 1080p (16:9) [Default]",
                "width": 1920,
                "height": 1080,
                "left": 0,
                "top": 0,
                "primary": True,
                "orientation": "landscape",
                "ratio": "16:9",
                "profile": "Full HD 1080p"
            })

        return monitors

    @classmethod
    def get_monitor_by_id(cls, monitor_id: str) -> Optional[Dict[str, Any]]:
        """Finds a monitor by device ID (e.g. DISPLAY1, DISPLAY2)."""
        clean_id = monitor_id.replace("\\\\.\\", "").strip().upper()
        for m in cls.get_connected_monitors():
            if m["id"].upper() == clean_id:
                return m
        return None

if __name__ == "__main__":
    import json
    monitors = MonitorDetector.get_connected_monitors()
    print(f"Connected Monitors Detected: {len(monitors)}")
    print(json.dumps(monitors, indent=2))
