"""
test_franchise_intelligence.py - Comprehensive Unit & Integration Tests for
Verified Franchise Tag Intelligence System (Kuro Screensaver Migration v14)

Covers:
1. Structured Franchise Catalog & Verified Tag IDs (Bleach, One Piece, JJK, Demon Slayer, AOT, etc.)
2. Query Strategy Construction (verified_tag_id, character_tag_id, franchise_keyword, alias_keyword)
3. Ambiguity Guard & Keyword Exclusion Filters
4. Database Schema v14, Query Strategy tracking, and Tag Metadata Cache
5. Multi-Strategy Merging & ID Deduplication
6. Graceful Tag Query Error Fallback
7. Administrative Catalog Update & Reset
8. Live / Mock Tag Verification & REST Endpoints
"""

import copy
import http.server
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from database import DatabaseManager, CURRENT_SCHEMA_VERSION
from franchise_registry import FranchiseRegistry, FRANCHISE_REGISTRY
from providers import NormalizedWallpaper, WallhavenProvider, SafebooruProvider, KonachanProvider


class TestFranchiseCatalogVerification(unittest.TestCase):
    """Tests the structured franchise catalog, verified tag IDs, and aliases."""

    def setUp(self):
        self.catalog = FranchiseRegistry.get_catalog()

    def test_catalog_has_all_18_franchises(self):
        self.assertGreaterEqual(len(self.catalog), 18)
        expected_slugs = [
            "bleach", "one-piece", "jujutsu-kaisen", "demon-slayer", "attack-on-titan",
            "solo-leveling", "chainsaw-man", "cyberpunk-edgerunners", "neon-genesis-evangelion",
            "naruto", "dragon-ball", "death-note", "hunter-x-hunter", "frieren",
            "my-hero-academia", "vinland-saga", "black-clover", "fate-series"
        ]
        for slug in expected_slugs:
            self.assertIn(slug, self.catalog, f"Catalog missing essential franchise: {slug}")

    def test_verified_tag_ids_integrity(self):
        # 1. Bleach: Series ID 1405
        bleach = self.catalog["bleach"]
        self.assertEqual(bleach["name"], "Bleach")
        self.assertIn(1405, bleach["wallhaven_tag_ids"])
        self.assertIn(1570, bleach["character_tag_ids"].get("Ichigo Kurosaki", []))

        # 2. One Piece: Series ID 1394
        op = self.catalog["one-piece"]
        self.assertEqual(op["name"], "One Piece")
        self.assertIn(1394, op["wallhaven_tag_ids"])
        self.assertIn(1551, op["character_tag_ids"].get("Roronoa Zoro", []))
        self.assertIn(1550, op["character_tag_ids"].get("Monkey D. Luffy", []))

        # 3. Jujutsu Kaisen: Series ID 108966
        jjk = self.catalog["jujutsu-kaisen"]
        self.assertIn(108966, jjk["wallhaven_tag_ids"])
        self.assertIn(109009, jjk["character_tag_ids"].get("Satoru Gojo", []))

        # 4. Demon Slayer: Series ID 84088
        ds = self.catalog["demon-slayer"]
        self.assertIn(84088, ds["wallhaven_tag_ids"])
        self.assertIn(89202, ds["character_tag_ids"].get("Kyojuro Rengoku", []))
        self.assertIn(145609, ds["character_tag_ids"].get("Akaza", []))

        # 5. Attack on Titan: Series ID 140
        aot = self.catalog["attack-on-titan"]
        self.assertIn(140, aot["wallhaven_tag_ids"])
        self.assertIn(4386, aot["character_tag_ids"].get("Levi Ackerman", []))
        self.assertIn(139326, aot["character_tag_ids"].get("Zeke Yeager", []))

    def test_aliases_and_search_queries_present(self):
        for slug, entry in self.catalog.items():
            self.assertTrue(entry.get("name"), f"Missing display name for {slug}")
            self.assertTrue(entry.get("english_aliases"), f"Missing english aliases for {slug}")
            self.assertTrue(entry.get("search_queries"), f"Missing search queries for {slug}")
            self.assertTrue(entry.get("allowlist_tags"), f"Missing allowlist tags for {slug}")


class TestQueryStrategyBuilders(unittest.TestCase):
    """Tests URL query generation across separate strategies."""

    def test_strategy_a_verified_tag_query(self):
        url = FranchiseRegistry.build_wallhaven_tag_query(
            tag_id=1405,
            negative_keywords=["-cleaning", "-detergent"],
            page=2,
            ratio="landscape",
            min_resolution="1920x1080"
        )
        self.assertIn("q=id%3A1405%20-cleaning%20-detergent", url)
        self.assertIn("categories=010", url)
        self.assertIn("purity=100", url)
        self.assertIn("atleast=1920x1080", url)
        self.assertIn("page=2", url)
        self.assertIn("ratios=16x9,16x10", url)

    def test_strategy_b_keyword_query(self):
        url = FranchiseRegistry.build_wallhaven_keyword_query(
            keyword="Bleach",
            negative_keywords=["-cleaning"],
            page=1,
            ratio="ultrawide"
        )
        self.assertIn("q=%22Bleach%22%20-cleaning", url)
        self.assertIn("ratios=21x9,32x9,16x9", url)

    def test_strategy_c_character_tag_query(self):
        url = FranchiseRegistry.build_wallhaven_tag_query(
            tag_id=1551,
            negative_keywords=["-swimsuit"],
            page=1,
            ratio="portrait"
        )
        self.assertIn("q=id%3A1551%20-swimsuit", url)
        self.assertIn("ratios=9x16,10x16", url)


class TestAmbiguityGuard(unittest.TestCase):
    """Tests rejection of generic tags and ambiguous keywords."""

    def test_one_piece_swimsuit_ambiguity_rejection(self):
        # Ambiguous artwork tagged with 'swimsuit' or 'monokini' must be rejected
        is_valid, char = FranchiseRegistry.validate_tags(
            "one-piece",
            ["one piece", "swimsuit", "beach"]
        )
        self.assertFalse(is_valid, "Should reject One Piece image with swimsuit keyword")

        # Excluded tag ID 243 (swimsuit)
        is_valid_id, _ = FranchiseRegistry.validate_tags(
            "one-piece",
            ["one piece", "straw hat"],
            tag_ids=[243]
        )
        self.assertFalse(is_valid_id, "Should reject One Piece image with excluded tag ID 243")

        # Valid One Piece artwork
        is_valid_legit, char_legit = FranchiseRegistry.validate_tags(
            "one-piece",
            ["one piece", "monkey d. luffy", "straw hat pirates"]
        )
        self.assertTrue(is_valid_legit)
        self.assertEqual(char_legit, "Monkey D. Luffy")

    def test_bleach_cleaning_ambiguity_rejection(self):
        # Cleaning products matching 'bleach'
        is_valid, _ = FranchiseRegistry.validate_tags(
            "bleach",
            ["bleach", "detergent", "laundry"]
        )
        self.assertFalse(is_valid, "Should reject Bleach artwork matching detergent keywords")

        # Legitimate Bleach anime artwork
        is_valid_legit, char = FranchiseRegistry.validate_tags(
            "bleach",
            ["bleach", "kurosaki ichigo", "tybw"]
        )
        self.assertTrue(is_valid_legit)
        self.assertEqual(char, "Ichigo Kurosaki")

    def test_generic_disallowed_tags_rejection(self):
        is_valid, _ = FranchiseRegistry.validate_tags(
            "jujutsu-kaisen",
            ["jujutsu kaisen", "vtuber", "hololive"]
        )
        self.assertFalse(is_valid, "Should reject vtuber / generic crossover artwork")


class TestDatabaseSchemaV14AndTagCache(unittest.TestCase):
    """Tests Migration v14, query_strategy persistence, and verified tag cache."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kuro_test_v14_")
        self.db_path = Path(self.temp_dir) / "kuro_test.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_migration_version_14_applied(self):
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(version) FROM schema_migrations")
            ver = cur.fetchone()[0]
            self.assertGreaterEqual(ver, 14)

            # Check columns in wallpaper_lifecycle
            cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
            cols = [c[1] for c in cur.fetchall()]
            self.assertIn("query_strategy", cols)

            # Check table verified_tag_cache
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='verified_tag_cache'")
            self.assertIsNotNone(cur.fetchone())

            # Check table franchise_catalog
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='franchise_catalog'")
            self.assertIsNotNone(cur.fetchone())

    def test_add_unseen_wallpapers_persists_query_strategy(self):
        items = [
            {
                "id": "wh_strategy_test_1",
                "url": "https://w.wallhaven.cc/full/1.jpg",
                "resolution": "1920x1080",
                "anime": "Bleach",
                "character": "Ichigo Kurosaki",
                "query_strategy": "verified_tag_id"
            },
            {
                "id": "wh_strategy_test_2",
                "url": "https://w.wallhaven.cc/full/2.jpg",
                "resolution": "2560x1440",
                "anime": "One Piece",
                "character": "Roronoa Zoro",
                "query_strategy": "character_tag_id"
            },
            {
                "id": "sb_strategy_test_3",
                "url": "https://safebooru.org/images/3.jpg",
                "resolution": "1920x1080",
                "anime": "Jujutsu Kaisen",
                "character": "Satoru Gojo",
                "query_strategy": "booru_failover"
            }
        ]
        added = self.db.add_unseen_wallpapers(items)
        self.assertEqual(added, 3)

        rec1 = self.db.get_wallpaper_by_id("wh_strategy_test_1")
        self.assertIsNotNone(rec1)
        self.assertEqual(rec1.get("query_strategy"), "verified_tag_id")

        rec2 = self.db.get_wallpaper_by_id("wh_strategy_test_2")
        self.assertEqual(rec2.get("query_strategy"), "character_tag_id")

        rec3 = self.db.get_wallpaper_by_id("sb_strategy_test_3")
        self.assertEqual(rec3.get("query_strategy"), "booru_failover")

    def test_tag_cache_methods(self):
        # Cache a tag
        ok = self.db.cache_verified_tag(
            tag_id=1405,
            tag_name="Bleach",
            category="Series",
            purity="sfw",
            raw_metadata={"id": 1405, "name": "Bleach", "category": "Series"}
        )
        self.assertTrue(ok)

        # Retrieve cached tag
        cached = self.db.get_cached_tag(1405)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["tag_name"], "Bleach")
        self.assertEqual(cached["category"], "Series")
        self.assertEqual(cached["purity"], "sfw")
        self.assertIsInstance(cached["raw_metadata"], dict)

        # Retrieve all cached tags
        all_tags = self.db.get_all_cached_tags()
        self.assertEqual(len(all_tags), 1)
        self.assertEqual(all_tags[0]["tag_id"], 1405)


class TestMultiStrategyExecutionAndDeduplication(unittest.TestCase):
    """Tests WallhavenProvider strategy dispatching, ID deduplication, and fallback."""

    def setUp(self):
        self.provider = WallhavenProvider()

    @patch.object(WallhavenProvider, "_fetch_wallhaven_api")
    def test_strategy_merging_and_deduplication(self, mock_fetch):
        # Simulate Strategy A (tag query id:1405) returning 2 items
        # Simulate Strategy B (keyword "Bleach") returning 2 items (1 overlapping, 1 new)
        def side_effect(url):
            if "id%3A1405" in url:
                return [
                    {
                        "id": "wh_item_1",
                        "path": "https://w.wallhaven.cc/full/1.jpg",
                        "purity": "100",
                        "dimension_x": 1920,
                        "dimension_y": 1080,
                        "resolution": "1920x1080",
                        "tags": [{"name": "bleach", "category": "Series"}]
                    },
                    {
                        "id": "wh_item_2",
                        "path": "https://w.wallhaven.cc/full/2.jpg",
                        "purity": "100",
                        "dimension_x": 1920,
                        "dimension_y": 1080,
                        "resolution": "1920x1080",
                        "tags": [{"name": "ichigo kurosaki", "category": "Characters"}]
                    }
                ]
            else:
                return [
                    # wh_item_2 is duplicate from Strategy A
                    {
                        "id": "wh_item_2",
                        "path": "https://w.wallhaven.cc/full/2.jpg",
                        "purity": "100",
                        "dimension_x": 1920,
                        "dimension_y": 1080,
                        "resolution": "1920x1080",
                        "tags": [{"name": "ichigo kurosaki", "category": "Characters"}]
                    },
                    # wh_item_3 is new from Strategy B
                    {
                        "id": "wh_item_3",
                        "path": "https://w.wallhaven.cc/full/3.jpg",
                        "purity": "100",
                        "dimension_x": 1920,
                        "dimension_y": 1080,
                        "resolution": "1920x1080",
                        "tags": [{"name": "rukia kuchiki", "category": "Characters"}]
                    }
                ]

        mock_fetch.side_effect = side_effect

        results = self.provider.search(
            franchise_slug="bleach",
            limit=24
        )

        # Deduplication must yield exactly 3 items, not 4
        self.assertEqual(len(results), 3)
        ids = [r.id for r in results]
        self.assertEqual(ids, ["wh_item_1", "wh_item_2", "wh_item_3"])

        # Check strategy provenance tracking
        r1 = next(r for r in results if r.id == "wh_item_1")
        self.assertEqual(r1.query_strategy, "verified_tag_id")

        r2 = next(r for r in results if r.id == "wh_item_2")
        self.assertEqual(r2.query_strategy, "verified_tag_id")

    @patch.object(WallhavenProvider, "_fetch_wallhaven_api")
    def test_ambiguous_artwork_filtered_in_search(self, mock_fetch):
        # Return an item with ambiguous tag ("cleaning" for Bleach)
        mock_fetch.return_value = [
            {
                "id": "wh_cleaning_bottle",
                "path": "https://w.wallhaven.cc/full/clean.jpg",
                "purity": "100",
                "dimension_x": 1920,
                "dimension_y": 1080,
                "tags": [{"name": "bleach", "category": "General"}, {"name": "cleaning", "category": "General"}]
            },
            {
                "id": "wh_legit_bleach",
                "path": "https://w.wallhaven.cc/full/legit.jpg",
                "purity": "100",
                "dimension_x": 1920,
                "dimension_y": 1080,
                "tags": [{"name": "bleach", "category": "Series"}, {"name": "ichigo kurosaki", "category": "Characters"}]
            }
        ]

        results = self.provider.search(franchise_slug="bleach", limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "wh_legit_bleach")

    @patch.object(WallhavenProvider, "_fetch_wallhaven_api")
    def test_graceful_fallback_when_tag_query_fails(self, mock_fetch):
        # Strategy A (tag query) raises HTTP Error 500
        # Strategy B (keyword query) succeeds
        def side_effect(url):
            if "id%3A1405" in url:
                raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)
            return [
                {
                    "id": "wh_fallback_1",
                    "path": "https://w.wallhaven.cc/full/fb.jpg",
                    "purity": "100",
                    "dimension_x": 1920,
                    "dimension_y": 1080,
                    "tags": [{"name": "bleach", "category": "Series"}]
                }
            ]

        mock_fetch.side_effect = side_effect

        results = self.provider.search(franchise_slug="bleach", limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "wh_fallback_1")
        self.assertEqual(results[0].query_strategy, "franchise_keyword")


class TestAdministrativeCatalogUpdateAndReset(unittest.TestCase):
    """Tests runtime dynamic inspection, updates, and resetting of franchise catalog."""

    def test_update_catalog_entry_and_reset(self):
        # Check initial One Piece tag
        op_initial = FranchiseRegistry.get_franchise("one-piece")
        self.assertIn(1394, op_initial.get("wallhaven_tag_ids", []))

        # Perform administrative update: add custom tag ID 99999
        updated = FranchiseRegistry.update_franchise_catalog_entry(
            slug="one-piece",
            data={
                "name": "One Piece (Custom)",
                "wallhaven_tag_ids": [1394, 99999],
                "excluded_keywords": ["swimsuit", "bikini", "cosplay"]
            },
            save_file=False
        )
        self.assertIn(99999, updated["wallhaven_tag_ids"])
        self.assertEqual(updated["name"], "One Piece (Custom)")

        # Verify reflected in get_franchise
        op_modified = FranchiseRegistry.get_franchise("one-piece")
        self.assertEqual(op_modified["name"], "One Piece (Custom)")
        self.assertIn(99999, op_modified["wallhaven_tag_ids"])

        # Reset to defaults
        reset_res = FranchiseRegistry.reset_catalog_to_defaults(save_file=False)
        self.assertIn("one-piece", reset_res)
        op_restored = FranchiseRegistry.get_franchise("one-piece")
        self.assertEqual(op_restored["name"], "One Piece")
        self.assertNotIn(99999, op_restored.get("wallhaven_tag_ids", []))


class TestTagVerificationService(unittest.TestCase):
    """Tests the live/mocked Wallhaven tag verification tool."""

    @patch("franchise_registry.urllib.request.urlopen")
    def test_verify_tag_id_online_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "data": {
                "id": 1405,
                "name": "Bleach",
                "category": "Series",
                "purity": "sfw",
                "created_at": "2014-04-14 00:00:00"
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = FranchiseRegistry.verify_tag_id_online(1405)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["id"], 1405)
        self.assertEqual(res["name"], "Bleach")
        self.assertEqual(res["category"], "Series")

    @patch("franchise_registry.urllib.request.urlopen")
    def test_verify_tag_id_online_404(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError("https://wallhaven.cc/api/v1/tag/9999999", 404, "Not Found", {}, None)
        res = FranchiseRegistry.verify_tag_id_online(9999999)
        self.assertFalse(res["is_valid"])
        self.assertIn("HTTP 404", res["error"])


class TestFranchiseCatalogRestAPI(unittest.TestCase):
    """Integration tests for Franchise Tag Intelligence REST endpoints."""

    @classmethod
    def setUpClass(cls):
        import socket
        from server import ThreadedHTTPServer, KuroHandler, HOST, security_manager

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        cls.test_port = s.getsockname()[1]
        s.close()

        cls.server = ThreadedHTTPServer((HOST, cls.test_port), KuroHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)
        cls.base_url = f"http://{HOST}:{cls.test_port}"
        cls.session_token = security_manager.session_token

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_get_franchise_catalog_endpoint(self):
        req = urllib.request.Request(f"{self.base_url}/api/franchises/catalog")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("catalog", data)
            self.assertGreaterEqual(data["total_franchises"], 18)
            catalog = data["catalog"]
            self.assertIn("bleach", catalog)
            self.assertIn(1405, catalog["bleach"]["wallhaven_tag_ids"])

    def test_verify_tag_endpoint(self):
        url = f"{self.base_url}/api/franchises/catalog/verify-tag"
        payload = json.dumps({"tag_id": 1405}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.session_token
            }
        )
        with patch.object(FranchiseRegistry, "verify_tag_id_online") as mock_verify:
            mock_verify.return_value = {
                "id": 1405,
                "name": "Bleach",
                "category": "Series",
                "purity": "sfw",
                "created_at": "2014-04-14 00:00:00",
                "is_valid": True,
                "error": None
            }

            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertEqual(data["status"], "verified")
                self.assertEqual(data["tag"]["id"], 1405)
                self.assertEqual(data["tag"]["name"], "Bleach")

    def test_update_and_reset_catalog_endpoint(self):
        url = f"{self.base_url}/api/franchises/catalog/update"
        payload = json.dumps({
            "slug": "demon-slayer",
            "entry": {
                "name": "Demon Slayer (Kimetsu)",
                "wallhaven_tag_ids": [84088, 77777]
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.session_token
            }
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "updated")
            self.assertIn(77777, data["entry"]["wallhaven_tag_ids"])

        # Reset endpoint
        reset_url = f"{self.base_url}/api/franchises/catalog/reset"
        reset_req = urllib.request.Request(
            reset_url,
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.session_token
            }
        )
        with urllib.request.urlopen(reset_req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            reset_data = json.loads(resp.read().decode())
            self.assertEqual(reset_data["status"], "reset")
            self.assertGreaterEqual(reset_data["total_franchises"], 18)


if __name__ == "__main__":
    unittest.main()
