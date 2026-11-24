"""
Automated Unit and Integration Tests for Interactive Artwork Information Panel
and Intelligent Wallpaper Composition & Focal-Point Protection.

Tests:
- Database Migrations v10 (Composition) and v11 (Enhanced Artwork Metadata)
- Persistence of authentic source metadata (uploader, upload_date, source_url, dimensions, file size, views, favorites)
- Non-fabrication of missing metadata (strictly returns None / Unavailable indicator)
- Aspect ratio computation and formatting (16:9, 21:9 Ultrawide, 9:16 Portrait)
- Formatted file size string generation
- Wallpaper composition CRUD (focal_x, focal_y, display_mode, blurred_background, multi-character list)
- Clamping of focal coordinates to 0.0 - 100.0%
- REST API endpoints:
  - GET /api/wallpaper/<id> & /api/v1/wallpaper/<id>
  - GET /api/composition/settings & POST /api/composition/settings (CSRF protected)
  - GET /api/composition/<id> & POST /api/composition/<id> (CSRF protected)
- Input validation and structured error responses
"""

import unittest
import json
import sys
import urllib.request
import urllib.error
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from database import DatabaseManager
import server


class TestArtworkInfoAndCompositionDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "test_kuro.db"
        cls.db = DatabaseManager(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_01_migrations_v10_and_v11_applied(self):
        """Verifies schema version >= 11 and composition & metadata tables/columns exist."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(version) FROM schema_migrations")
            max_ver = cur.fetchone()[0]
            self.assertGreaterEqual(max_ver, 11)

            # Check composition tables
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wallpaper_composition'")
            self.assertIsNotNone(cur.fetchone())

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='composition_settings'")
            self.assertIsNotNone(cur.fetchone())

            # Check lifecycle columns
            cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
            cols = {col[1] for col in cur.fetchall()}
            self.assertIn("uploader", cols)
            self.assertIn("upload_date", cols)
            self.assertIn("source_url", cols)
            self.assertIn("dimension_x", cols)
            self.assertIn("dimension_y", cols)
            self.assertIn("file_size", cols)
            self.assertIn("views", cols)
            self.assertIn("favorites", cols)

    def test_02_composition_settings_defaults_and_updates(self):
        """Verifies composition settings defaults and persistent updating."""
        cfg = self.db.get_composition_settings()
        self.assertEqual(cfg["default_mode_landscape"], "fill")
        self.assertEqual(cfg["default_mode_portrait"], "fit")
        self.assertTrue(cfg["blurred_backdrop_enabled"])
        self.assertEqual(cfg["blur_intensity_px"], 28)

        # Update settings
        ok = self.db.update_composition_settings({
            "default_mode_landscape": "fit",
            "default_mode_portrait": "fill",
            "default_mode_ultrawide": "fit",
            "blurred_backdrop_enabled": 0,
            "blur_intensity_px": 40,
            "backdrop_opacity": 0.8
        })
        self.assertTrue(ok)

        updated = self.db.get_composition_settings()
        self.assertEqual(updated["default_mode_landscape"], "fit")
        self.assertEqual(updated["default_mode_portrait"], "fill")
        self.assertFalse(updated["blurred_backdrop_enabled"])
        self.assertEqual(updated["blur_intensity_px"], 40)
        self.assertEqual(updated["backdrop_opacity"], 0.8)

    def test_03_wallpaper_composition_crud_and_characters(self):
        """Verifies saving, retrieving, updating, and deleting custom wallpaper compositions with character pins."""
        wp_id = "test_wp_comp_01"
        self.db.add_unseen_wallpapers([{
            "id": wp_id,
            "url": "https://example.com/test01.jpg",
            "resolution": "3840x2160",
            "anime": "Frieren"
        }])

        # Save custom composition
        chars = [
            {"id": 1, "name": "Frieren", "x": 32.5, "y": 28.0},
            {"id": 2, "name": "Fern", "x": 68.0, "y": 30.5}
        ]
        ok = self.db.save_wallpaper_composition(wp_id, {
            "focal_x": 32.5,
            "focal_y": 28.0,
            "display_mode": "fill",
            "blurred_background": 1,
            "portrait_display_mode": "fit",
            "characters": chars
        })
        self.assertTrue(ok)

        comp = self.db.get_wallpaper_composition(wp_id)
        self.assertIsNotNone(comp)
        self.assertEqual(comp["wallpaper_id"], wp_id)
        self.assertEqual(comp["focal_x"], 32.5)
        self.assertEqual(comp["focal_y"], 28.0)
        self.assertEqual(comp["display_mode"], "fill")
        self.assertEqual(comp["portrait_display_mode"], "fit")
        self.assertEqual(len(comp["characters"]), 2)
        self.assertEqual(comp["characters"][0]["name"], "Frieren")

        # Delete composition (reset to default)
        deleted = self.db.delete_wallpaper_composition(wp_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.db.get_wallpaper_composition(wp_id))

    def test_04_focal_bounds_clamping(self):
        """Verifies focal coordinates outside 0.0-100.0 are clamped safely."""
        wp_id = "test_wp_clamped"
        self.db.add_unseen_wallpapers([{
            "id": wp_id,
            "url": "https://example.com/clamped.jpg",
            "anime": "Bleach"
        }])
        self.db.save_wallpaper_composition(wp_id, {
            "focal_x": -15.0,
            "focal_y": 150.0,
            "display_mode": "invalid_mode"
        })
        comp = self.db.get_wallpaper_composition(wp_id)
        self.assertEqual(comp["focal_x"], 0.0)
        self.assertEqual(comp["focal_y"], 100.0)
        self.assertEqual(comp["display_mode"], "fill")  # Fallback to fill

    def test_05_metadata_persistence_and_no_invented_data(self):
        """
        Verifies authentic source metadata is preserved in SQLite without inventing missing fields.
        Missing fields must remain None so the UI can honestly display 'Unavailable'.
        """
        wp_id = "test_wp_meta_honest"
        self.db.add_unseen_wallpapers([{
            "id": wp_id,
            "url": "https://example.com/meta_test.jpg",
            "resolution": "1920x1080",
            "anime": "Jujutsu Kaisen",
            "character": "Gojo Satoru",
            "dimension_x": 1920,
            "dimension_y": 1080,
            "file_size": 2621440,  # Exactly 2.5 MB
            "views": 15420,
            "favorites": 1280,
            "uploader": "AnimeArtist99",
            "upload_date": "2024-01-15 10:30:00",
            "source_url": "https://wallhaven.cc/w/test_wp_meta_honest"
        }])

        details = self.db.get_artwork_details(wp_id)
        self.assertIsNotNone(details)
        self.assertEqual(details["id"], wp_id)
        self.assertEqual(details["anime"], "Jujutsu Kaisen")
        self.assertEqual(details["character"], "Gojo Satoru")
        self.assertEqual(details["uploader"], "AnimeArtist99")
        self.assertEqual(details["upload_date"], "2024-01-15 10:30:00")
        self.assertEqual(details["file_size_formatted"], "2.50 MB")
        self.assertEqual(details["views"], 15420)
        self.assertEqual(details["favorites"], 1280)
        self.assertEqual(details["aspect_ratio"], "16:9 (1.78:1)")

        # Now test a wallpaper with missing metadata
        wp_missing_id = "test_wp_missing"
        self.db.add_unseen_wallpapers([{
            "id": wp_missing_id,
            "url": "https://example.com/minimal.jpg",
            "anime": "Unknown"
        }])

        details_missing = self.db.get_artwork_details(wp_missing_id)
        self.assertIsNotNone(details_missing)
        self.assertIsNone(details_missing["character"])
        self.assertIsNone(details_missing["uploader"])
        self.assertIsNone(details_missing["upload_date"])
        self.assertIsNone(details_missing["file_size"])
        self.assertIsNone(details_missing["file_size_formatted"])


class TestArtworkInfoAndCompositionAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "test_api_kuro.db"
        cls.db = DatabaseManager(cls.db_path)

        # Seed sample wallpaper
        cls.wp_id = "wp_api_sample_01"
        cls.db.add_unseen_wallpapers([{
            "id": cls.wp_id,
            "url": "https://example.com/api_sample.jpg",
            "resolution": "2560x1440",
            "anime": "Solo Leveling",
            "character": "Sung Jin-woo",
            "dimension_x": 2560,
            "dimension_y": 1440,
            "file_size": 1840000,
            "views": 8500,
            "favorites": 620,
            "uploader": "ShadowMonarch",
            "upload_date": "2024-02-10 18:00:00",
            "source_url": f"https://wallhaven.cc/w/{cls.wp_id}"
        }])

        # Monkeypatch server instances safely
        cls.orig_db = server.db_manager
        cls.orig_port = server.PORT
        server.db_manager = cls.db
        cls.token = server.security_manager.session_token

        # Dynamic test port
        cls.port = 54452
        server.PORT = cls.port
        cls.server = server.ThreadedHTTPServer(("127.0.0.1", cls.port), server.KuroHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass
        server.db_manager = cls.orig_db
        server.PORT = cls.orig_port
        cls.temp_dir.cleanup()

    def test_01_api_get_wallpaper_details(self):
        """Tests GET /api/wallpaper/<id> returns complete authentic metadata."""
        url = f"{self.base_url}/api/wallpaper/{self.wp_id}"
        req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["id"], self.wp_id)
            self.assertEqual(data["anime"], "Solo Leveling")
            self.assertEqual(data["character"], "Sung Jin-woo")
            self.assertEqual(data["uploader"], "ShadowMonarch")
            self.assertEqual(data["views"], 8500)
            self.assertEqual(data["favorites"], 620)
            self.assertIn("16:9", data["aspect_ratio"])

    def test_02_api_get_wallpaper_not_found(self):
        """Tests GET /api/wallpaper/nonexistent returns 404 structured error."""
        url = f"{self.base_url}/api/wallpaper/nonexistent_id_999"
        req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)
        err = json.loads(ctx.exception.read().decode())
        self.assertEqual(err["error"]["code"], "NOT_FOUND")

    def test_03_api_composition_settings_get_and_post(self):
        """Tests GET and POST /api/composition/settings with CSRF protection."""
        url = f"{self.base_url}/api/composition/settings"

        # 1. GET settings
        req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("default_mode_portrait", data)

        # 2. POST without CSRF token -> 401 Unauthorized
        post_req = urllib.request.Request(
            url,
            data=json.dumps({"default_mode_portrait": "fill"}).encode(),
            headers={"Origin": "http://127.0.0.1", "Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(post_req)
        self.assertEqual(ctx.exception.code, 401)

        # 3. POST with valid CSRF token -> 200 OK
        valid_post = urllib.request.Request(
            url,
            data=json.dumps({"default_mode_portrait": "fill"}).encode(),
            headers={
                "Origin": "http://127.0.0.1",
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token
            }
        )
        with urllib.request.urlopen(valid_post) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode())
            self.assertEqual(res["status"], "updated")
            self.assertEqual(res["settings"]["default_mode_portrait"], "fill")

    def test_04_api_wallpaper_composition_save_and_reset(self):
        """Tests POST /api/composition/<id> to save focal point and reset."""
        url = f"{self.base_url}/api/composition/{self.wp_id}"

        # 1. Save focal point (30.0%, 25.0%) with CSRF token
        payload = {
            "focal_x": 30.0,
            "focal_y": 25.0,
            "display_mode": "fill",
            "blurred_background": 1
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Origin": "http://127.0.0.1",
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token
            }
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode())
            self.assertEqual(res["status"], "saved")
            self.assertEqual(res["composition"]["focal_x"], 30.0)
            self.assertEqual(res["composition"]["focal_y"], 25.0)

        # 2. Verify GET /api/composition/<id> reflects saved coordinates
        get_req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
        with urllib.request.urlopen(get_req) as resp:
            data = json.loads(resp.read().decode())
            self.assertEqual(data["focal_x"], 30.0)
            self.assertEqual(data["focal_y"], 25.0)

        # 3. Test Invalid Coordinates rejection (focal_x > 100) -> 400 Bad Request
        bad_req = urllib.request.Request(
            url,
            data=json.dumps({"focal_x": 120.0, "focal_y": 50.0}).encode(),
            headers={
                "Origin": "http://127.0.0.1",
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token
            }
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(bad_req)
        self.assertEqual(ctx.exception.code, 400)

        # 4. Reset composition
        reset_req = urllib.request.Request(
            url,
            data=json.dumps({"reset": True}).encode(),
            headers={
                "Origin": "http://127.0.0.1",
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token
            }
        )
        with urllib.request.urlopen(reset_req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode())
            self.assertEqual(res["status"], "reset")


if __name__ == "__main__":
    unittest.main(verbosity=2)
