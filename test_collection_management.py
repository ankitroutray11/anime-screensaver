#!/usr/bin/env python3
"""
Comprehensive automated tests for Personal Anime Wallpaper Collection Management System:
- Favorites management (high-res saving, chunked progress tracking, duplicate prevention, removal, file cleanup, interrupted recovery)
- Custom collections (creation, rename, deletion, adding/removing items, franchise & resolution filters, character search)
- Wallpaper blacklist (permanent exclusion from reserve_next_wallpaper and prefetch, restoration)
- Aggregate library statistics & storage metrics (favorites & cache breakdown, utilization, purge)
- API endpoints & versioning parity (/api/v1/ and /api/)
"""

import os
import sys
import json
import time
import shutil
import socket
import tempfile
import unittest
import threading
import urllib.request
import urllib.parse
from pathlib import Path

from database import DatabaseManager
from cache_manager import CacheManager
from favorites_downloader import FavoritesDownloader
from server import KuroHandler, ThreadedHTTPServer, HOST, security_manager

class TestCollectionManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="kuro_col_test_"))
        cls.db_path = cls.test_dir / "test_collection.db"
        cls.fav_dir = cls.test_dir / "favorites"
        cls.cache_dir = cls.test_dir / ".cache" / "wallpapers"
        cls.fav_dir.mkdir(parents=True, exist_ok=True)
        cls.cache_dir.mkdir(parents=True, exist_ok=True)

        cls.db = DatabaseManager(cls.db_path)
        cls.fav_downloader = FavoritesDownloader(cls.db, cls.fav_dir)

        # Seed sample wallpapers
        cls.sample_items = [
            {
                "id": "col_wp_01",
                "url": "https://w.wallhaven.cc/full/col_wp_01.jpg",
                "resolution": "3840x2160",
                "anime": "Jujutsu Kaisen",
                "character": "Gojo Satoru",
                "source": "Wallhaven"
            },
            {
                "id": "col_wp_02",
                "url": "https://w.wallhaven.cc/full/col_wp_02.png",
                "resolution": "2560x1440",
                "anime": "Demon Slayer",
                "character": "Tanjiro Kamado",
                "source": "Wallhaven"
            },
            {
                "id": "col_wp_03",
                "url": "https://w.wallhaven.cc/full/col_wp_03.jpg",
                "resolution": "1920x1080",
                "anime": "Attack on Titan",
                "character": "Levi Ackerman",
                "source": "Wallhaven"
            },
            {
                "id": "col_wp_04",
                "url": "https://w.wallhaven.cc/full/col_wp_04.jpg",
                "resolution": "3840x2160",
                "anime": "Jujutsu Kaisen",
                "character": "Sukuna",
                "source": "Wallhaven"
            }
        ]
        cls.db.add_unseen_wallpapers(cls.sample_items)

        # Start a local test HTTP server on an ephemeral port
        s = socket.socket()
        s.bind((HOST, 0))
        cls.port = s.getsockname()[1]
        s.close()

        # Point global instances in server module for integration testing
        import server
        cls._orig_server_db = server.db_manager
        cls._orig_server_fav = server.favorites_downloader
        cls._orig_server_base = server.BASE_DIR
        cls._orig_server_db_path = server.DB_PATH
        cls._orig_server_port = server.PORT

        server.PORT = cls.port
        server.DB_PATH = cls.db_path
        server.FAVORITES_DIR = cls.fav_dir
        server.BASE_DIR = cls.test_dir
        server.db_manager = cls.db
        server.favorites_downloader = cls.fav_downloader

        cls.httpd = ThreadedHTTPServer((HOST, cls.port), KuroHandler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        except Exception:
            pass
        import server
        server.db_manager = cls._orig_server_db
        server.favorites_downloader = cls._orig_server_fav
        server.BASE_DIR = cls._orig_server_base
        server.DB_PATH = cls._orig_server_db_path
        server.PORT = cls._orig_server_port
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def _api_get(self, path: str):
        url = f"http://{HOST}:{self.port}{path}"
        req = urllib.request.Request(url, headers={"Origin": f"http://{HOST}:{self.port}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _api_post(self, path: str, payload: dict, token: str = None):
        url = f"http://{HOST}:{self.port}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://{HOST}:{self.port}"
        }
        if token:
            headers["X-Kuro-Token"] = token
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # =========================================================================
    # 1. FAVORITES MANAGEMENT TESTS
    # =========================================================================
    def test_01_add_favorite_and_duplicate_handling(self):
        """Tests adding favorites, metadata preservation, and duplicate download prevention."""
        item = {
            "id": "col_fav_01",
            "url": "https://w.wallhaven.cc/full/col_fav_01.jpg",
            "resolution": "3840x2160",
            "anime": "Chainsaw Man",
            "character": "Makima",
            "source": "Wallhaven"
        }
        self.assertTrue(self.db.add_favorite(item))
        self.assertTrue(self.db.is_favorite("col_fav_01"))

        fav = self.db.get_favorite_by_id("col_fav_01")
        self.assertIsNotNone(fav)
        self.assertEqual(fav["anime"], "Chainsaw Man")
        self.assertEqual(fav["character"], "Makima")
        self.assertEqual(fav["download_status"], "pending")

        # Simulate completed file download
        fake_file = self.fav_dir / "col_fav_01.jpg"
        fake_file.write_bytes(b"\xFF\xD8\xFF\xE0" + b"X" * 1024)
        self.db.update_favorite_download("col_fav_01", "completed", 100, "favorites/col_fav_01.jpg", len(fake_file.read_bytes()))

        # Re-adding favorite should NOT overwrite completed status
        self.db.add_favorite(item)
        fav_updated = self.db.get_favorite_by_id("col_fav_01")
        self.assertEqual(fav_updated["download_status"], "completed")
        self.assertEqual(fav_updated["download_progress"], 100)

    def test_02_remove_favorite_with_disk_file_cleanup(self):
        """Tests favorite removal and physical image deletion."""
        # Create dummy favorite with file
        item_id = "col_fav_del_01"
        fake_file = self.fav_dir / f"{item_id}.jpg"
        fake_file.write_bytes(b"image_content_here")

        self.db.add_favorite({
            "id": item_id,
            "url": f"https://w.wallhaven.cc/full/{item_id}.jpg",
            "resolution": "1920x1080",
            "anime": "Bleach",
            "character": "Ichigo Kurosaki",
            "file_path": f"favorites/{item_id}.jpg",
            "file_size": len(fake_file.read_bytes()),
            "download_status": "completed"
        })
        self.assertTrue(fake_file.exists())

        # Remove favorite via db & downloader
        rel_path = self.db.remove_favorite(item_id)
        self.assertEqual(rel_path, f"favorites/{item_id}.jpg")
        self.fav_downloader.delete_favorite_file(item_id, rel_path)

        self.assertFalse(self.db.is_favorite(item_id))
        self.assertFalse(fake_file.exists())

    def test_03_favorites_filtering_and_search(self):
        """Tests filtering favorites by franchise, resolution, character, and text search."""
        self.db.add_favorite({
            "id": "col_fav_filter_1",
            "url": "https://w.wallhaven.cc/full/1.jpg",
            "resolution": "3840x2160",
            "anime": "Naruto",
            "character": "Kakashi Hatake",
            "source": "Wallhaven"
        })
        self.db.add_favorite({
            "id": "col_fav_filter_2",
            "url": "https://w.wallhaven.cc/full/2.jpg",
            "resolution": "2560x1440",
            "anime": "Naruto",
            "character": "Itachi Uchiha",
            "source": "Wallhaven"
        })
        self.db.add_favorite({
            "id": "col_fav_filter_3",
            "url": "https://w.wallhaven.cc/full/3.jpg",
            "resolution": "3840x2160",
            "anime": "Solo Leveling",
            "character": "Sung Jin-woo",
            "source": "Wallhaven"
        })

        # Franchise filter
        naruto_favs = self.db.get_favorites(franchise="Naruto")
        self.assertEqual(len(naruto_favs), 2)

        # Resolution filter
        res_4k = self.db.get_favorites(resolution="3840x2160")
        self.assertTrue(any(f["id"] == "col_fav_filter_3" for f in res_4k))

        # Character filter
        kakashi = self.db.get_favorites(character="Kakashi Hatake")
        self.assertEqual(len(kakashi), 1)
        self.assertEqual(kakashi[0]["id"], "col_fav_filter_1")

        # Text search
        search_itachi = self.db.get_favorites(search="Itachi")
        self.assertEqual(len(search_itachi), 1)
        self.assertEqual(search_itachi[0]["character"], "Itachi Uchiha")

    def test_04_interrupted_download_cleanup(self):
        """Tests that orphaned .tmp files and dangling downloading states are resolved."""
        # Create orphaned temp file
        orphan_tmp = self.fav_dir / "col_interrupted.jpg.tmp.deadbeef"
        orphan_tmp.write_bytes(b"partial_download_bytes")

        # Set downloading status in DB
        self.db.add_favorite({
            "id": "col_interrupted",
            "url": "https://w.wallhaven.cc/full/col_interrupted.jpg",
            "download_status": "downloading",
            "file_path": "favorites/col_interrupted.jpg"
        })

        cleaned = self.fav_downloader.cleanup_interrupted()
        self.assertGreaterEqual(cleaned, 1)
        self.assertFalse(orphan_tmp.exists())

        rec = self.db.get_favorite_by_id("col_interrupted")
        self.assertEqual(rec["download_status"], "failed")

    # =========================================================================
    # 2. CUSTOM COLLECTIONS TESTS
    # =========================================================================
    def test_05_create_rename_delete_collections(self):
        """Tests collection lifecycle: create, rename, list, and delete."""
        col = self.db.create_collection("Cyberpunk Vibes", "High-tech low-life aesthetics")
        col_id = col["id"]
        self.assertTrue(col_id.startswith("col_"))
        self.assertEqual(col["name"], "Cyberpunk Vibes")

        # Verify in list
        cols = self.db.get_collections()
        self.assertTrue(any(c["id"] == col_id for c in cols))

        # Rename
        renamed = self.db.rename_collection(col_id, "Neon Night City", "Updated cyberpunk collection")
        self.assertTrue(renamed)
        cols_after_rename = self.db.get_collections()
        target = next(c for c in cols_after_rename if c["id"] == col_id)
        self.assertEqual(target["name"], "Neon Night City")
        self.assertEqual(target["description"], "Updated cyberpunk collection")

        # Delete
        deleted = self.db.delete_collection(col_id)
        self.assertTrue(deleted)
        cols_after_del = self.db.get_collections()
        self.assertFalse(any(c["id"] == col_id for c in cols_after_del))

    def test_06_collection_items_and_filtering(self):
        """Tests adding/removing wallpapers to collections and filtering by franchise/resolution."""
        col = self.db.create_collection("Epic Shonen", "Legendary battles")
        col_id = col["id"]

        self.assertTrue(self.db.add_to_collection(col_id, "col_wp_01"))  # JKK Gojo 4K
        self.assertTrue(self.db.add_to_collection(col_id, "col_wp_02"))  # Demon Slayer Tanjiro 1440p
        self.assertTrue(self.db.add_to_collection(col_id, "col_wp_04"))  # JKK Sukuna 4K

        # Count verification
        items = self.db.get_collection_wallpapers(col_id)
        self.assertEqual(len(items), 3)

        # Filter by franchise
        jjk_items = self.db.get_collection_wallpapers(col_id, franchise="Jujutsu Kaisen")
        self.assertEqual(len(jjk_items), 2)

        # Filter by resolution
        res_4k = self.db.get_collection_wallpapers(col_id, resolution="3840x2160")
        self.assertEqual(len(res_4k), 2)

        # Search by character
        sukuna = self.db.get_collection_wallpapers(col_id, search="Sukuna")
        self.assertEqual(len(sukuna), 1)
        self.assertEqual(sukuna[0]["id"], "col_wp_04")

        # Remove item
        removed = self.db.remove_from_collection(col_id, "col_wp_02")
        self.assertTrue(removed)
        items_after_remove = self.db.get_collection_wallpapers(col_id)
        self.assertEqual(len(items_after_remove), 2)
        self.assertFalse(any(i["id"] == "col_wp_02" for i in items_after_remove))

    # =========================================================================
    # 3. WALLPAPER BLACKLIST TESTS
    # =========================================================================
    def test_07_blacklist_permanently_excludes_from_reservation(self):
        """Tests that blacklisted wallpaper is NEVER reserved or served to user."""
        wp_to_blacklist = "col_wp_03" # Levi Ackerman
        self.assertFalse(self.db.is_blacklisted(wp_to_blacklist))

        # Add to blacklist
        self.assertTrue(self.db.add_to_blacklist(wp_to_blacklist, reason="Disliked art style"))
        self.assertTrue(self.db.is_blacklisted(wp_to_blacklist))

        b_list = self.db.get_blacklist()
        self.assertTrue(any(b["id"] == wp_to_blacklist for b in b_list))

        # Attempt to reserve with anime="Attack on Titan"
        candidate = self.db.reserve_next_wallpaper(anime="Attack on Titan", token="tok_test_bl")
        # Should be None since col_wp_03 is the only AoT entry and it is blacklisted!
        self.assertIsNone(candidate)

        # Restore from blacklist
        self.assertTrue(self.db.restore_from_blacklist(wp_to_blacklist))
        self.assertFalse(self.db.is_blacklisted(wp_to_blacklist))

        # Now reservation should succeed!
        restored_candidate = self.db.reserve_next_wallpaper(anime="Attack on Titan", token="tok_test_bl2")
        self.assertIsNotNone(restored_candidate)
        self.assertEqual(restored_candidate["id"], wp_to_blacklist)

    # =========================================================================
    # 4. LIBRARY STATISTICS & STORAGE TESTS
    # =========================================================================
    def test_08_library_stats_and_storage_calculations(self):
        """Tests aggregate library statistics, distinct franchise exploration, and storage."""
        # Confirm one wallpaper displayed
        self.db.confirm_displayed("col_wp_03", "tok_test_bl2")

        stats = self.db.get_library_stats(self.test_dir)
        self.assertIn("total_displayed", stats)
        self.assertIn("total_favorites", stats)
        self.assertIn("total_collections", stats)
        self.assertIn("total_blacklisted", stats)
        self.assertIn("franchises_explored", stats)
        self.assertIn("storage", stats)
        self.assertIn("cache_utilization", stats)

        self.assertGreaterEqual(stats["total_displayed"], 1)
        self.assertGreaterEqual(stats["franchises_explored"], 1)
        self.assertGreaterEqual(stats["total_favorites"], 1)

    # =========================================================================
    # 5. SERVER API ENDPOINTS & VERSIONING PARITY
    # =========================================================================
    def test_09_api_endpoints_and_security(self):
        """Tests API routes for favorites, collections, blacklist, stats, and cache purge."""
        token = security_manager.session_token

        # Unauthenticated state-changing POST should be 401
        url = f"http://{HOST}:{self.port}/api/collections"
        req = urllib.request.Request(
            url,
            data=json.dumps({"name": "Unauthorized Col"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": f"http://{HOST}:{self.port}"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 401)

        # Create collection via /api/v1/collections
        res_col = self._api_post("/api/v1/collections", {"name": "Masterpieces V1", "description": "Top quality"}, token=token)
        col_id = res_col["id"]
        self.assertEqual(res_col["name"], "Masterpieces V1")

        # Add item to collection via /api/collections/add-item
        add_item_res = self._api_post("/api/collections/add-item", {"collection_id": col_id, "wallpaper_id": "col_wp_01"}, token=token)
        self.assertTrue(add_item_res["success"])

        # Fetch collection items via GET /api/v1/collections/<id>/items
        items_res = self._api_get(f"/api/v1/collections/{col_id}/items")
        self.assertEqual(len(items_res), 1)
        self.assertEqual(items_res[0]["id"], "col_wp_01")

        # Add to blacklist via /api/v1/blacklist
        bl_res = self._api_post("/api/v1/blacklist", {"wallpaper_id": "col_wp_04", "reason": "Testing API"}, token=token)
        self.assertEqual(bl_res["status"], "blacklisted")

        # Verify in GET /api/blacklist
        bl_list = self._api_get("/api/blacklist")
        self.assertTrue(any(b["id"] == "col_wp_04" for b in bl_list))

        # Restore via POST /api/blacklist/restore
        rest_res = self._api_post("/api/blacklist/restore", {"wallpaper_id": "col_wp_04"}, token=token)
        self.assertEqual(rest_res["status"], "restored")

        # GET /api/v1/library/stats
        stats_v1 = self._api_get("/api/v1/library/stats")
        stats_legacy = self._api_get("/api/library/stats")
        self.assertEqual(stats_v1["total_displayed"], stats_legacy["total_displayed"])
        self.assertEqual(stats_v1["total_favorites"], stats_legacy["total_favorites"])

        # Cache purge via POST /api/v1/cache/purge
        purge_res = self._api_post("/api/v1/cache/purge", {}, token=token)
        self.assertEqual(purge_res["status"], "purged")

if __name__ == "__main__":
    unittest.main()
