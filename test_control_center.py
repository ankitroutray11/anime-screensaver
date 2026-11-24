"""
Tests for Advanced Anime Ambient Control Center (Preferences & System Calibration).
Covers:
- Database Migration v12 (control_center_settings table).
- Full 6-section configuration schema (General, Wallpaper, Visual, Display, Performance, Privacy).
- Individual section reset without affecting other sections.
- Configuration export and import parity.
- Factory reset preserving saved favorites.
- REST API v1 endpoints with CSRF token authentication and parameter validation.
"""

import unittest
import json
import urllib.request
import urllib.error
import threading
import tempfile
import shutil
import time
from pathlib import Path

import database
import server

class TestControlCenterDatabase(unittest.TestCase):
    """Verifies SQLite WAL persistence, migration v12, section isolation, and defaults."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_ctrl_test_"))
        self.db_path = self.test_dir / "test_ctrl.db"
        self.db = database.DatabaseManager(self.db_path)

    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_01_migration_v12_applied(self):
        """Verifies schema version >= 12 and control_center_settings table exists."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(version) FROM schema_migrations")
            max_ver = cur.fetchone()[0]
            self.assertGreaterEqual(max_ver, 12)

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='control_center_settings'")
            self.assertIsNotNone(cur.fetchone())

    def test_02_all_six_sections_present_with_defaults(self):
        """Verifies all 6 required sections exist with valid default values."""
        settings = self.db.get_control_center_settings()
        expected_sections = ["general", "wallpaper", "visual", "display", "performance", "privacy"]
        for sec in expected_sections:
            self.assertIn(sec, settings)
            self.assertIsInstance(settings[sec], dict)
            self.assertGreater(len(settings[sec]), 0)

        # Spot-check critical defaults
        gen = settings["general"]
        self.assertEqual(gen["display_mode"], "ambient")
        self.assertEqual(gen["slideshow_interval"], 30)

        vis = settings["visual"]
        self.assertEqual(vis["visual_theme"], "kuro-dark")
        self.assertTrue(vis["visual_dynamic_accent"])
        self.assertEqual(vis["visual_hud_opacity"], 100)

        perf = settings["performance"]
        self.assertEqual(perf["perf_prefetch_queue_size"], 6)
        self.assertEqual(perf["perf_cache_limit_mb"], 2048)

    def test_03_save_and_retrieve_section_settings(self):
        """Verifies saving updates for a single section persists and returns correctly."""
        new_visual = {
            "visual_theme": "cyberpunk-neon",
            "visual_dynamic_accent": False,
            "visual_accent_color": "#06b6d4",
            "visual_hud_opacity": 85
        }
        ok = self.db.save_control_center_settings("visual", new_visual)
        self.assertTrue(ok)

        # Retrieve visual section
        vis = self.db.get_control_center_settings("visual")
        self.assertEqual(vis["visual_theme"], "cyberpunk-neon")
        self.assertFalse(vis["visual_dynamic_accent"])
        self.assertEqual(vis["visual_accent_color"], "#06b6d4")
        self.assertEqual(vis["visual_hud_opacity"], 85)

        # Verify other sections were NOT modified or erased
        gen = self.db.get_control_center_settings("general")
        self.assertEqual(gen["display_mode"], "ambient")

    def test_04_reset_individual_section(self):
        """Verifies resetting one section restores defaults without affecting others."""
        # Modify visual and general
        self.db.save_control_center_settings("visual", {"visual_theme": "sakura-blossom"})
        self.db.save_control_center_settings("general", {"display_mode": "cinematic"})

        # Reset visual section only
        reset_vis = self.db.reset_control_center_section("visual")
        self.assertEqual(reset_vis["visual_theme"], "kuro-dark")

        # Confirm in database
        vis = self.db.get_control_center_settings("visual")
        self.assertEqual(vis["visual_theme"], "kuro-dark")

        # General should remain cinematic
        gen = self.db.get_control_center_settings("general")
        self.assertEqual(gen["display_mode"], "cinematic")

    def test_05_export_and_import_configuration(self):
        """Verifies export produces comprehensive JSON structure and import restores it."""
        self.db.save_control_center_settings("visual", {"visual_theme": "midnight-minimal"})
        export_data = self.db.export_full_configuration()

        self.assertIn("control_center", export_data)
        self.assertIn("scheduler", export_data)
        self.assertIn("quality", export_data)
        self.assertEqual(export_data["control_center"]["visual"]["visual_theme"], "midnight-minimal")

        # Reset and import
        self.db.reset_control_center_section("visual")
        self.assertEqual(self.db.get_control_center_settings("visual")["visual_theme"], "kuro-dark")

        ok = self.db.import_full_configuration(export_data)
        self.assertTrue(ok)
        self.assertEqual(self.db.get_control_center_settings("visual")["visual_theme"], "midnight-minimal")

    def test_06_factory_reset_preserves_favorites(self):
        """Verifies factory reset clears preferences but preserves user favorites."""
        # Save a favorite
        self.db.add_favorite({
            "id": "fav_test_01",
            "url": "http://127.0.0.1/test.jpg",
            "anime": "Test Anime",
            "resolution": "1920x1080"
        })
        self.assertTrue(self.db.is_favorite("fav_test_01"))

        # Modify settings
        self.db.save_control_center_settings("visual", {"visual_theme": "tokyo-noir"})

        # Factory reset
        self.db.factory_reset_configuration()

        # Settings should be default
        vis = self.db.get_control_center_settings("visual")
        self.assertEqual(vis["visual_theme"], "kuro-dark")

        # Favorite must STILL exist
        self.assertTrue(self.db.is_favorite("fav_test_01"))


class TestControlCenterAPI(unittest.TestCase):
    """Verifies Control Center REST API endpoints, security CSRF tokens, and validation."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="kuro_ctrl_api_"))
        cls.db_path = cls.test_dir / "api_ctrl.db"
        cls.db = database.DatabaseManager(cls.db_path)

        cls.orig_db = server.db_manager
        server.db_manager = cls.db
        cls.port = 58942
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server = server.ThreadedHTTPServer(("127.0.0.1", cls.port), server.KuroHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        cls.token = server.security_manager.session_token

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass
        server.db_manager = cls.orig_db
        try:
            shutil.rmtree(cls.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_01_api_get_settings_all_and_section(self):
        """Tests GET /api/settings and GET /api/settings?section=visual."""
        req = urllib.request.Request(f"{self.base_url}/api/settings")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "ok")
            self.assertIn("general", data["settings"])
            self.assertIn("visual", data["settings"])

        req_sec = urllib.request.Request(f"{self.base_url}/api/settings?section=visual")
        with urllib.request.urlopen(req_sec) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "ok")
            self.assertIn("visual_theme", data["settings"])

    def test_02_api_post_settings_authenticated(self):
        """Tests POST /api/settings with valid CSRF session token."""
        payload = json.dumps({
            "section": "visual",
            "settings": {
                "visual_theme": "cyberpunk-neon",
                "visual_hud_opacity": 90
            }
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": "http://127.0.0.1"
            }
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "saved")
            self.assertEqual(data["settings"]["visual_theme"], "cyberpunk-neon")

    def test_03_api_post_settings_unauthenticated_fails(self):
        """Tests POST /api/settings without token rejects with HTTP 401."""
        payload = json.dumps({"section": "visual", "settings": {}}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=payload,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 401)

    def test_04_api_post_settings_validation_rejects_invalid_values(self):
        """Tests validation rejects out-of-range interval and cache limits."""
        # 1. Invalid slideshow interval (< 5)
        payload = json.dumps({
            "section": "general",
            "settings": {"slideshow_interval": 2}
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": "http://127.0.0.1"
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

        # 2. Invalid cache limit (> 20000MB)
        payload2 = json.dumps({
            "section": "performance",
            "settings": {"perf_cache_limit_mb": 99999}
        }).encode()

        req2 = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=payload2,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": "http://127.0.0.1"
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx2:
            urllib.request.urlopen(req2)
        self.assertEqual(ctx2.exception.code, 400)

    def test_05_api_export_and_reset_endpoints(self):
        """Tests GET /api/settings/export and POST /api/settings/reset."""
        # Export
        req_exp = urllib.request.Request(f"{self.base_url}/api/settings/export")
        with urllib.request.urlopen(req_exp) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "ok")
            self.assertIn("control_center", data["export"])

        # Reset Section
        reset_payload = json.dumps({"section": "visual"}).encode()
        req_reset = urllib.request.Request(
            f"{self.base_url}/api/settings/reset",
            data=reset_payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": "http://127.0.0.1"
            }
        )
        with urllib.request.urlopen(req_reset) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "reset")
            self.assertEqual(data["settings"]["visual_theme"], "kuro-dark")


if __name__ == "__main__":
    unittest.main()
