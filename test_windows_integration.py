#!/usr/bin/env python3
"""
Automated verification suite for Windows Integration & Launcher:
- Server process lifecycle & single-instance prevention
- Health polling & diagnostic error reporting
- Browser detection across Windows Registry and fallback paths
- Target monitor detection & coordinate positioning
- Graceful shutdown (/api/shutdown) and PID cleanup
- Windows Startup shortcut management
- Configuration persistence (launcher_config.json)
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
import threading
import urllib.request
from pathlib import Path

import launcher
from monitor_detector import MonitorDetector
from security import SecurityManager

class TestWindowsIntegration(unittest.TestCase):
    def test_01_detect_browsers(self):
        """Tests browser detection via Windows Registry and system disk paths."""
        browsers = launcher.detect_supported_browsers()
        self.assertIsInstance(browsers, list)
        # On standard Windows systems, at least one browser (e.g. Edge, Chrome, or Brave) is present
        if sys.platform == "win32":
            self.assertGreater(len(browsers), 0)
            print(f"[Test] Detected {len(browsers)} browser(s): {[b['name'] for b in browsers]}")
            exe_path, is_chrom = launcher.get_browser_executable()
            self.assertIsNotNone(exe_path)
            self.assertTrue(os.path.isfile(exe_path))

    def test_02_monitor_detection_and_positioning(self):
        """Tests multi-monitor topology resolution and coordinate calculation."""
        monitors = MonitorDetector.get_connected_monitors()
        self.assertIsInstance(monitors, list)
        self.assertGreater(len(monitors), 0)
        first_mon = monitors[0]
        self.assertIn("width", first_mon)
        self.assertIn("height", first_mon)
        self.assertIn("left", first_mon)
        self.assertIn("top", first_mon)
        self.assertIn("primary", first_mon)
        print(f"[Test] Primary monitor: {first_mon['name']} ({first_mon['width']}x{first_mon['height']})")

    def test_03_config_persistence(self):
        """Tests reading, updating, and saving launcher_config.json."""
        orig_cfg = launcher.load_config()
        self.assertIn("mode", orig_cfg)

        test_cfg = dict(orig_cfg)
        test_cfg["mode"] = "windowed"
        test_cfg["target_monitor"] = "secondary"

        self.assertTrue(launcher.save_config(test_cfg))
        reloaded = launcher.load_config()
        self.assertEqual(reloaded["mode"], "windowed")
        self.assertEqual(reloaded["target_monitor"], "secondary")

        # Restore original
        launcher.save_config(orig_cfg)

    def test_04_server_start_single_instance_and_shutdown(self):
        """Tests starting server, verifying single-instance lock, health polling, and clean shutdown."""
        # Ensure any leftover processes are cleaned
        launcher.stop_screensaver()
        time.sleep(0.5)

        # 1. Start backend server
        success, port, msg = launcher.start_backend(silent=True, max_wait=10.0)
        self.assertTrue(success, f"Backend failed to start: {msg}")
        self.assertTrue(launcher.is_server_healthy(port))
        self.assertTrue(launcher.PID_FILE.is_file())

        # 2. Prevent multiple instances: second start call should detect running instance
        success2, port2, msg2 = launcher.start_backend(silent=True, max_wait=5.0)
        self.assertTrue(success2)
        self.assertEqual(port, port2)
        self.assertIn("already running", msg2.lower())

        # 3. Test /api/v1/launcher/config endpoint
        sec = SecurityManager()
        cfg_url = f"http://127.0.0.1:{port}/api/v1/launcher/config"
        req = urllib.request.Request(cfg_url, headers={"Origin": f"http://127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            self.assertIn("mode", data)

        # 4. Stop screensaver gracefully
        stop_ok, stop_msg = launcher.stop_screensaver()
        self.assertTrue(stop_ok)
        time.sleep(1.0)

        # 5. Verify PID file removed and server stopped
        self.assertFalse(launcher.is_server_healthy(port))
        self.assertFalse(launcher.PID_FILE.is_file())

    def test_05_windows_startup_integration(self):
        """Tests enabling, checking status, and disabling Windows Startup shortcut."""
        # Status
        ok, msg = launcher.manage_windows_startup("status")
        self.assertTrue(ok)

        # Enable
        ok_en, msg_en = launcher.manage_windows_startup("enable")
        self.assertTrue(ok_en)
        self.assertIn("Successfully registered", msg_en)

        # Verify enabled
        ok_chk, msg_chk = launcher.manage_windows_startup("status")
        self.assertIn("ENABLED", msg_chk)

        # Disable
        ok_dis, msg_dis = launcher.manage_windows_startup("disable")
        self.assertTrue(ok_dis)

        # Verify disabled
        ok_chk2, msg_chk2 = launcher.manage_windows_startup("status")
        self.assertIn("DISABLED", msg_chk2)

if __name__ == "__main__":
    unittest.main()
