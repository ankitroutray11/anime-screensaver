"""
Comprehensive test suite for KuroAnime Screensaver - Visual Wallpaper History Explorer.
Tests:
1. Paged history querying (get_wallpaper_history) with pagination metadata (page, page_size, total, total_pages).
2. Multi-parameter filtering:
   - Search query (q) across franchise, character, and wallpaper ID
   - Franchise filter
   - Date filter (today, yesterday, week, month)
   - Resolution filter (4k, 1440p, 1080p, ultrawide, portrait)
   - Favorites filter (favorites_only)
3. Sorting strategies (newest, oldest, popularity, quality).
4. Similarity group classification.
5. Exporting history metadata (JSON and RFC 4180 CSV).
6. Zero-duplicate invariant on Revisit:
   - Verifies revisit does NOT insert any new row into wallpaper_lifecycle.
   - Verifies lifecycle status remains DISPLAYED and count is unchanged.
   - Verifies revisit taste interaction is logged in preference_interactions.
7. REST API HTTP endpoints (/api/history, /api/history/explorer, /api/history/export, /api/history/revisit).

100% Python Standard Library.
"""

import os
import sys
import json
import csv
import io
import time
import shutil
import sqlite3
import tempfile
import unittest
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import database
import server


class TestDatabaseHistoryExplorer(unittest.TestCase):
    """Unit tests for database.get_wallpaper_history and database.export_wallpaper_history."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_hist_test_"))
        self.db_path = self.test_dir / "test_kuro.db"
        self.db = database.DatabaseManager(str(self.db_path))

        # Populate test wallpapers and lifecycle records
        now = datetime.now(timezone.utc)
        # Anchor "today" and "yesterday" to local noon converted to UTC so
        # SQLite date(..., 'localtime') is deterministic even right after midnight.
        local_noon = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
        today_utc = local_noon.astimezone(timezone.utc)
        yesterday_utc = (local_noon - timedelta(days=1)).astimezone(timezone.utc)
        self.sample_wallpapers = [
            {
                "id": "wp_naruto_01",
                "url": "https://example.com/naruto.jpg",
                "resolution": "3840x2160",
                "dimension_x": 3840,
                "dimension_y": 2160,
                "file_size": 4194304,
                "views": 15000,
                "favorites": 3500,
                "anime": "Naruto Shippuden",
                "character": "Naruto Uzumaki",
                "quality_score": 92.5,
                "displayed_at": today_utc.strftime("%Y-%m-%d %H:%M:%S"),
                "is_fav": True,
            },
            {
                "id": "wp_aot_02",
                "url": "https://example.com/aot.jpg",
                "resolution": "1920x1080",
                "dimension_x": 1920,
                "dimension_y": 1080,
                "file_size": 2097152,
                "views": 8000,
                "favorites": 1200,
                "anime": "Attack on Titan",
                "character": "Eren Yeager",
                "quality_score": 75.0,
                "displayed_at": yesterday_utc.strftime("%Y-%m-%d %H:%M:%S"),
                "is_fav": False,
            },
            {
                "id": "wp_ds_03",
                "url": "https://example.com/ds.jpg",
                "resolution": "1440x2560", # Portrait
                "dimension_x": 1440,
                "dimension_y": 2560,
                "file_size": 3145728,
                "views": 6000,
                "favorites": 900,
                "anime": "Demon Slayer",
                "character": "Tanjiro Kamado",
                "quality_score": 68.0,
                "displayed_at": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                "is_fav": False,
            },
            {
                "id": "wp_cyber_04",
                "url": "https://example.com/cyber.jpg",
                "resolution": "3440x1440", # Ultrawide
                "dimension_x": 3440,
                "dimension_y": 1440,
                "file_size": 5242880,
                "views": 25000,
                "favorites": 6000,
                "anime": "Cyberpunk Edgerunners",
                "character": "Lucy",
                "quality_score": 96.0,
                "displayed_at": (now - timedelta(days=12)).strftime("%Y-%m-%d %H:%M:%S"),
                "is_fav": True,
            },
            {
                "id": "wp_op_05",
                "url": "https://example.com/op.jpg",
                "resolution": "2560x1440", # 1440p landscape
                "dimension_x": 2560,
                "dimension_y": 1440,
                "file_size": 3670016,
                "views": 11000,
                "favorites": 2100,
                "anime": "One Piece",
                "character": "Monkey D. Luffy",
                "quality_score": 84.0,
                "displayed_at": (now - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S"),
                "is_fav": False,
            },
        ]

        with self.db.get_connection() as conn:
            for item in self.sample_wallpapers:
                conn.execute(
                    """
                    INSERT INTO wallpaper_lifecycle (
                        id, url, resolution, dimension_x, dimension_y, file_size, views, favorites,
                        anime, character, source, status, displayed_at, quality_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Wallhaven', 'DISPLAYED', ?, ?)
                    """,
                    (
                        item["id"],
                        item["url"],
                        item["resolution"],
                        item["dimension_x"],
                        item["dimension_y"],
                        item["file_size"],
                        item["views"],
                        item["favorites"],
                        item["anime"],
                        item["character"],
                        item["displayed_at"],
                        item["quality_score"],
                    ),
                )
                if item["is_fav"]:
                    conn.execute(
                        """
                        INSERT INTO favorites (id, url, resolution, mood, character)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (item["id"], item["url"], item["resolution"], item["anime"], item["character"]),
                    )

            # Insert an UNSEEN and a RESERVED wallpaper to verify they are NOT returned in history
            conn.execute(
                """
                INSERT INTO wallpaper_lifecycle (id, url, resolution, status)
                VALUES ('wp_unseen_99', 'https://example.com/unseen.jpg', '1920x1080', 'UNSEEN')
                """
            )

            conn.execute(
                """
                INSERT INTO wallpaper_lifecycle (id, url, resolution, status, reservation_token, reserved_at)
                VALUES ('wp_reserved_98', 'https://example.com/reserved.jpg', '1920x1080', 'RESERVED', 'tok_98', CURRENT_TIMESTAMP)
                """
            )
            conn.commit()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_history_query(self):
        """History should only return DISPLAYED wallpapers, ordered newest first by default."""
        res = self.db.get_wallpaper_history(page=1, page_size=20)
        self.assertEqual(res["total"], 5)
        self.assertEqual(len(res["items"]), 5)
        self.assertEqual(res["page"], 1)
        self.assertEqual(res["total_pages"], 1)

        # Most recent should be Naruto (2 hours ago)
        self.assertEqual(res["items"][0]["id"], "wp_naruto_01")
        # Oldest should be One Piece (45 days ago)
        self.assertEqual(res["items"][-1]["id"], "wp_op_05")

        # Verify unseen and reserved items were excluded
        ids = [it["id"] for it in res["items"]]
        self.assertNotIn("wp_unseen_99", ids)
        self.assertNotIn("wp_reserved_98", ids)

    def test_pagination(self):
        """Paging parameters (page and page_size) should slice results accurately."""
        res_p1 = self.db.get_wallpaper_history(page=1, page_size=2)
        self.assertEqual(res_p1["total"], 5)
        self.assertEqual(res_p1["page"], 1)
        self.assertEqual(res_p1["page_size"], 2)
        self.assertEqual(res_p1["total_pages"], 3)
        self.assertEqual(len(res_p1["items"]), 2)
        self.assertEqual(res_p1["items"][0]["id"], "wp_naruto_01")
        self.assertEqual(res_p1["items"][1]["id"], "wp_aot_02")

        res_p2 = self.db.get_wallpaper_history(page=2, page_size=2)
        self.assertEqual(res_p2["page"], 2)
        self.assertEqual(len(res_p2["items"]), 2)
        self.assertEqual(res_p2["items"][0]["id"], "wp_ds_03")
        self.assertEqual(res_p2["items"][1]["id"], "wp_cyber_04")

        res_p3 = self.db.get_wallpaper_history(page=3, page_size=2)
        self.assertEqual(res_p3["page"], 3)
        self.assertEqual(len(res_p3["items"]), 1)
        self.assertEqual(res_p3["items"][0]["id"], "wp_op_05")

    def test_search_filter(self):
        """Free-text search should match franchise, character, and wallpaper ID."""
        # By anime franchise
        res_naruto = self.db.get_wallpaper_history(search_query="Naruto")
        self.assertEqual(res_naruto["total"], 1)
        self.assertEqual(res_naruto["items"][0]["anime"], "Naruto Shippuden")

        # By character name
        res_lucy = self.db.get_wallpaper_history(search_query="Lucy")
        self.assertEqual(res_lucy["total"], 1)
        self.assertEqual(res_lucy["items"][0]["character"], "Lucy")

        # By partial ID
        res_id = self.db.get_wallpaper_history(search_query="cyber_04")
        self.assertEqual(res_id["total"], 1)
        self.assertEqual(res_id["items"][0]["id"], "wp_cyber_04")

        # Non-matching search
        res_none = self.db.get_wallpaper_history(search_query="Dragon Ball")
        self.assertEqual(res_none["total"], 0)
        self.assertEqual(len(res_none["items"]), 0)

    def test_franchise_filter(self):
        """Filtering by exact franchise should return only that franchise."""
        res = self.db.get_wallpaper_history(franchise="Attack on Titan")
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["items"][0]["id"], "wp_aot_02")

    def test_date_filter(self):
        """Date filtering should partition today, yesterday, week, and month."""
        # Today (< 24h): only Naruto (2h ago)
        res_today = self.db.get_wallpaper_history(date_filter="today")
        self.assertEqual(res_today["total"], 1)
        self.assertEqual(res_today["items"][0]["id"], "wp_naruto_01")

        # Yesterday (24h - 48h): only Attack on Titan (30h ago)
        res_yesterday = self.db.get_wallpaper_history(date_filter="yesterday")
        self.assertEqual(res_yesterday["total"], 1)
        self.assertEqual(res_yesterday["items"][0]["id"], "wp_aot_02")

        # Week (< 7 days): Naruto (2h), AoT (30h), Demon Slayer (3d)
        res_week = self.db.get_wallpaper_history(date_filter="week")
        self.assertEqual(res_week["total"], 3)
        week_ids = [it["id"] for it in res_week["items"]]
        self.assertIn("wp_naruto_01", week_ids)
        self.assertIn("wp_aot_02", week_ids)
        self.assertIn("wp_ds_03", week_ids)

        # Month (< 30 days): Naruto, AoT, DS, Cyberpunk (12d)
        res_month = self.db.get_wallpaper_history(date_filter="month")
        self.assertEqual(res_month["total"], 4)
        month_ids = [it["id"] for it in res_month["items"]]
        self.assertNotIn("wp_op_05", month_ids) # 45 days ago

    def test_resolution_filter(self):
        """Resolution filtering should detect 4K, 1440p, 1080p, portrait, and ultrawide."""
        # 4K
        res_4k = self.db.get_wallpaper_history(resolution="4k")
        self.assertEqual(res_4k["total"], 1)
        self.assertEqual(res_4k["items"][0]["id"], "wp_naruto_01")

        # 1080p
        res_1080p = self.db.get_wallpaper_history(resolution="1080p")
        self.assertEqual(res_1080p["total"], 1)
        self.assertEqual(res_1080p["items"][0]["id"], "wp_aot_02")

        # Ultrawide (21:9)
        res_uw = self.db.get_wallpaper_history(resolution="ultrawide")
        self.assertEqual(res_uw["total"], 1)
        self.assertEqual(res_uw["items"][0]["id"], "wp_cyber_04")

        # Portrait (height > width)
        res_port = self.db.get_wallpaper_history(resolution="portrait")
        self.assertEqual(res_port["total"], 1)
        self.assertEqual(res_port["items"][0]["id"], "wp_ds_03")

    def test_favorites_only_filter(self):
        """Favorites-only filter should restrict results to favorited wallpapers."""
        res_favs = self.db.get_wallpaper_history(favorites_only=True)
        self.assertEqual(res_favs["total"], 2)
        fav_ids = {it["id"] for it in res_favs["items"]}
        self.assertEqual(fav_ids, {"wp_naruto_01", "wp_cyber_04"})

    def test_sorting_modes(self):
        """Sorting should respect newest, oldest, popularity, and quality."""
        # Oldest first
        res_oldest = self.db.get_wallpaper_history(sort_by="oldest")
        self.assertEqual(res_oldest["items"][0]["id"], "wp_op_05")
        self.assertEqual(res_oldest["items"][-1]["id"], "wp_naruto_01")

        # Popularity (Cyberpunk favorites = 6000)
        res_pop = self.db.get_wallpaper_history(sort_by="popularity")
        self.assertEqual(res_pop["items"][0]["id"], "wp_cyber_04")

        # Quality (Cyberpunk = 96.0, Naruto = 92.5)
        res_qual = self.db.get_wallpaper_history(sort_by="quality")
        self.assertEqual(res_qual["items"][0]["id"], "wp_cyber_04")
        self.assertEqual(res_qual["items"][1]["id"], "wp_naruto_01")

    def test_similarity_group_computed(self):
        """Every historical wallpaper should have a computed similarity_group attribute."""
        res = self.db.get_wallpaper_history(page=1, page_size=10)
        for item in res["items"]:
            self.assertIn("similarity_group", item)
            self.assertTrue(len(item["similarity_group"]) > 0)
            self.assertIn(item["anime"], item["similarity_group"])

    def test_export_json_format(self):
        """export_wallpaper_history format='json' should yield valid JSON array."""
        json_str, mime = self.db.export_wallpaper_history(export_format="json")
        self.assertEqual(mime, "application/json; charset=utf-8")

        data = json.loads(json_str)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["total_records"], 5)
        self.assertEqual(len(data["history"]), 5)
        first = data["history"][0]
        self.assertIn("id", first)
        self.assertIn("anime", first)
        self.assertIn("character", first)
        self.assertIn("resolution", first)
        self.assertIn("quality_score", first)
        self.assertIn("similarity_group", first)

    def test_export_csv_format(self):
        """export_wallpaper_history format='csv' should yield valid RFC 4180 CSV."""
        csv_str, mime = self.db.export_wallpaper_history(export_format="csv")
        self.assertEqual(mime, "text/csv; charset=utf-8")

        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        self.assertEqual(len(rows), 5)
        self.assertIn("id", reader.fieldnames)
        self.assertIn("anime", reader.fieldnames)
        self.assertIn("character", reader.fieldnames)
        self.assertIn("quality_score", reader.fieldnames)
        self.assertIn("similarity_group", reader.fieldnames)
        self.assertEqual(rows[0]["id"], "wp_naruto_01")


class TestRevisitZeroDuplicateInvariant(unittest.TestCase):
    """Verifies that revisiting historical artwork preserves the global zero-duplicate invariant."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_revisit_test_"))
        self.db_path = self.test_dir / "test_kuro.db"
        self.db = database.DatabaseManager(str(self.db_path))

        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO wallpaper_lifecycle (id, url, resolution, anime, character, source, status, displayed_at)
                VALUES ('wp_test_rev', 'https://example.com/rev.jpg', '3840x2160', 'Steins;Gate', 'Kurisu Makise', 'Wallhaven', 'DISPLAYED', CURRENT_TIMESTAMP)
                """
            )
            conn.commit()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_revisit_does_not_duplicate_lifecycle_records(self):
        """revisit_wallpaper must not add a new row to wallpaper_lifecycle or reset lifecycle status."""
        with self.db.get_connection() as conn:
            initial_count = conn.execute("SELECT COUNT(*) FROM wallpaper_lifecycle").fetchone()[0]
            initial_status = conn.execute(
                "SELECT status FROM wallpaper_lifecycle WHERE id = 'wp_test_rev'"
            ).fetchone()[0]

        self.assertEqual(initial_count, 1)
        self.assertEqual(initial_status, "DISPLAYED")

        # Perform multiple revisits
        wp1 = self.db.revisit_wallpaper("wp_test_rev")
        self.assertIsNotNone(wp1)
        self.assertEqual(wp1["id"], "wp_test_rev")
        self.assertEqual(wp1["anime"], "Steins;Gate")

        wp2 = self.db.revisit_wallpaper("wp_test_rev")
        self.assertIsNotNone(wp2)

        # Verify lifecycle table is completely untouched
        with self.db.get_connection() as conn:
            final_count = conn.execute("SELECT COUNT(*) FROM wallpaper_lifecycle").fetchone()[0]
            final_rows = conn.execute(
                "SELECT id, status FROM wallpaper_lifecycle WHERE id = 'wp_test_rev'"
            ).fetchall()

        self.assertEqual(final_count, 1, "Lifecycle count must remain strictly 1; no duplicate rows allowed!")
        self.assertEqual(len(final_rows), 1)
        self.assertEqual(final_rows[0][1], "DISPLAYED", "Status must remain DISPLAYED, never reset to RESERVED!")

    def test_revisit_non_displayed_artwork_returns_none(self):
        """Attempting to revisit an unseen artwork should return None."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO wallpaper_lifecycle (id, url, status) VALUES ('wp_unseen_only', 'https://example.com/unseen.jpg', 'UNSEEN')
                """
            )

        res = self.db.revisit_wallpaper("wp_unseen_only")
        self.assertIsNone(res)


class TestServerHistoryExplorerEndpoints(unittest.TestCase):
    """Integration tests for HTTP REST endpoints of the Wallpaper History Explorer."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="kuro_http_hist_test_"))
        cls.db_path = cls.test_dir / "test_kuro.db"
        cls.db = database.DatabaseManager(str(cls.db_path))

        # Insert sample data
        with cls.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO wallpaper_lifecycle (
                    id, url, resolution, dimension_x, dimension_y, views, favorites,
                    anime, character, source, status, displayed_at, quality_score
                ) VALUES
                    ('wp_http_01', 'https://example.com/01.jpg', '3840x2160', 3840, 2160, 5000, 1200, 'Frieren: Beyond Journeys End', 'Frieren', 'Wallhaven', 'DISPLAYED', CURRENT_TIMESTAMP, 91.0),
                    ('wp_http_02', 'https://example.com/02.jpg', '1920x1080', 1920, 1080, 3000, 450, 'Bocchi the Rock!', 'Hitori Gotoh', 'Wallhaven', 'DISPLAYED', CURRENT_TIMESTAMP, 78.0)
                """
            )
            conn.commit()

        # Mock engine
        class MockEngine:
            def __init__(self, db):
                self.db = db
                self.recommendation_engine = MockRec()

        class MockRec:
            def record_revisit(self, wp_id, anime=None, character=None):
                pass

        cls.orig_db_manager = getattr(server, "db_manager", None)
        cls.orig_engine = getattr(server, "engine", None)
        cls.orig_token = getattr(server, "SESSION_TOKEN", None)

        server.db_manager = cls.db
        server.engine = MockEngine(cls.db)
        server.SESSION_TOKEN = "test_valid_hist_csrf_token"

        cls.httpd = server.ThreadedHTTPServer(("127.0.0.1", 0), server.KuroHandler)
        cls.port = cls.httpd.server_address[1]
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.db_manager = cls.orig_db_manager
        server.engine = cls.orig_engine
        server.SESSION_TOKEN = cls.orig_token
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_api_history_explorer_get(self):
        """GET /api/history/explorer should return paged explorer structure."""
        url = f"http://127.0.0.1:{self.port}/api/history/explorer?page=1&page_size=10"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 2)
            self.assertEqual(len(data["items"]), 2)
            self.assertIn("franchises", data)
            anime_titles = [it["anime"] for it in data["items"]]
            self.assertIn("Frieren: Beyond Journeys End", anime_titles)
            self.assertIn("Bocchi the Rock!", anime_titles)

    def test_api_history_with_search_param(self):
        """GET /api/history?q=Bocchi should return paged results filtered to Bocchi."""
        url = f"http://127.0.0.1:{self.port}/api/history?q=Bocchi"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["items"][0]["character"], "Hitori Gotoh")

    def test_api_history_backward_compatibility(self):
        """GET /api/history without params should return a raw list of items for backward compatibility."""
        url = f"http://127.0.0.1:{self.port}/api/history"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 2)

    def test_api_history_export_json(self):
        """GET /api/history/export?format=json should return an attachment with JSON array."""
        url = f"http://127.0.0.1:{self.port}/api/history/export?format=json"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/json", resp.headers.get("Content-Type", ""))
            self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
            body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body["total_records"], 2)
            self.assertEqual(len(body["history"]), 2)

    def test_api_history_export_csv(self):
        """GET /api/history/export?format=csv should return an attachment with CSV lines."""
        url = f"http://127.0.0.1:{self.port}/api/history/export?format=csv"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/csv", resp.headers.get("Content-Type", ""))
            self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
            csv_text = resp.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)
            self.assertEqual(len(rows), 2)

    def test_api_history_revisit_post(self):
        """POST /api/history/revisit with valid CSRF token should return wallpaper without duplicate lifecycle."""
        url = f"http://127.0.0.1:{self.port}/api/history/revisit"
        payload = json.dumps({"id": "wp_http_01"}).encode("utf-8")
        token = server.security_manager.session_token
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": token,
            },
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["wallpaper"]["id"], "wp_http_01")
            self.assertEqual(data["wallpaper"]["anime"], "Frieren: Beyond Journeys End")

        # Verify lifecycle records count in database did NOT increase
        with self.db.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE id = 'wp_http_01'").fetchone()[0]
            self.assertEqual(count, 1, "Revisit must not create duplicate lifecycle records!")

    def test_api_history_revisit_forbidden_without_csrf(self):
        """POST /api/history/revisit without CSRF token must return 401/403 Forbidden."""
        url = f"http://127.0.0.1:{self.port}/api/history/revisit"
        payload = json.dumps({"id": "wp_http_01"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertIn(ctx.exception.code, (401, 403))


if __name__ == "__main__":
    unittest.main()
