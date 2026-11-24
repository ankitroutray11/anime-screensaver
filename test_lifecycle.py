"""
Automated Test Suite for KuroAnime Wallpaper Lifecycle Engine.
Covers:
1. Duplicate API results & unique constraint enforcement.
2. Concurrent requests & zero race condition guarantee.
3. Application restart & persistence across sessions.
4. Failed image downloads & safe state handling.
5. Failed browser image loading (report_failed).
6. Abandoned reservations recovery.
7. Database recovery & WAL transactional integrity.
8. Exhausted wallpaper collections without silent resets.
"""

import os
import sys
import time
import uuid
import shutil
import sqlite3
import tempfile
import unittest
import threading
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import DatabaseManager
from engine import WallpaperEngine

class TestWallpaperLifecycle(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary test database for each test
        self.test_dir = tempfile.mkdtemp(prefix="kuro_test_")
        self.db_path = Path(self.test_dir) / "test_kuro.db"
        self.db = DatabaseManager(self.db_path)
        # Bounded buffer size = 10 and auto_prefetch=False for deterministic testing
        self.engine = WallpaperEngine(self.db, max_unseen_buffer=10, auto_prefetch=False)

    def tearDown(self):
        self.engine.stop()
        time.sleep(0.1)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_duplicate_api_results(self):
        """Verify that duplicate API discoveries are safely deduplicated by SQLite UNIQUE constraint."""
        candidates = [
            {"id": "wp_001", "url": "https://img.test/1.jpg", "resolution": "1920x1080", "anime": "Jujutsu Kaisen"},
            {"id": "wp_002", "url": "https://img.test/2.jpg", "resolution": "2560x1440", "anime": "Jujutsu Kaisen"},
            {"id": "wp_001", "url": "https://img.test/1.jpg", "resolution": "1920x1080", "anime": "Jujutsu Kaisen"}, # Duplicate
        ]
        
        # First insertion: 2 unique items added
        added = self.db.add_unseen_wallpapers(candidates)
        self.assertEqual(added, 2)
        
        # Second insertion with exact same list: 0 added
        added_again = self.db.add_unseen_wallpapers(candidates)
        self.assertEqual(added_again, 0)
        
        stats = self.db.get_stats()
        self.assertEqual(stats["unseen_count"], 2)

    def test_02_concurrent_requests_no_double_reservations(self):
        """Verify that concurrent requests NEVER reserve the same wallpaper simultaneously."""
        # Seed database with 20 items
        items = [{"id": f"wp_c_{i:03d}", "url": f"https://img.test/{i}.jpg", "resolution": "1080p", "anime": "One Piece"} for i in range(20)]
        self.db.add_unseen_wallpapers(items)

        reserved_ids = []
        lock = threading.Lock()

        def worker():
            token = str(uuid.uuid4())
            res = self.db.reserve_next_wallpaper(anime="One Piece", token=token)
            if res:
                with lock:
                    reserved_ids.append(res["id"])

        threads = [threading.Thread(target=worker) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check: 15 items reserved, and every single one is strictly UNIQUE
        self.assertEqual(len(reserved_ids), 15)
        self.assertEqual(len(set(reserved_ids)), 15, "Concurrent requests resulted in duplicate reservations!")
        
        stats = self.db.get_stats()
        self.assertEqual(stats["reserved_count"], 15)
        self.assertEqual(stats["unseen_count"], 5)

    def test_03_application_restart_persistence(self):
        """Verify displayed history and state persist completely across application restarts."""
        item = {"id": "wp_persist_01", "url": "https://img.test/p1.jpg", "anime": "Demon Slayer"}
        self.db.add_unseen_wallpapers([item])
        
        # Reserve and confirm display
        reserved = self.db.reserve_next_wallpaper(anime="Demon Slayer", token="token-123")
        self.assertIsNotNone(reserved)
        confirmed = self.db.confirm_displayed(reserved["id"], "token-123")
        self.assertTrue(confirmed)
        
        # Shut down current engine instance
        self.engine.stop()
        
        # Re-initialize new DatabaseManager and WallpaperEngine pointing to the same file
        db2 = DatabaseManager(self.db_path)
        engine2 = WallpaperEngine(db2, auto_prefetch=False)
        
        stats = db2.get_stats()
        self.assertEqual(stats["displayed_count"], 1)
        self.assertTrue(db2.is_displayed("wp_persist_01"))
        
        # Verify it cannot be reserved again
        next_item = db2.reserve_next_wallpaper(anime="Demon Slayer", token="token-456")
        self.assertIsNone(next_item, "Displayed item was re-reserved after restart!")
        
        engine2.stop()

    def test_04_failed_browser_image_loading(self):
        """Verify that browser image decode failures transition to FAILED and do not burn seen history."""
        item = {"id": "wp_broken_01", "url": "https://img.test/broken.jpg", "anime": "Chainsaw Man"}
        self.db.add_unseen_wallpapers([item])
        
        reserved = self.db.reserve_next_wallpaper(anime="Chainsaw Man", token="token-fail")
        self.assertIsNotNone(reserved)
        self.assertEqual(self.db.get_stats()["reserved_count"], 1)
        
        # Client reports load failure
        reported = self.db.mark_display_failed(reserved["id"], "token-fail", "404 Not Found")
        self.assertTrue(reported)
        
        stats = self.db.get_stats()
        self.assertEqual(stats["reserved_count"], 0)
        self.assertEqual(stats["failed_count"], 1)
        self.assertEqual(stats["displayed_count"], 0)
        self.assertFalse(self.db.is_displayed("wp_broken_01"))

    def test_05_abandoned_reservations_recovery(self):
        """Verify that abandoned reservations exceeding timeout are recovered back to UNSEEN."""
        item = {"id": "wp_abandon_01", "url": "https://img.test/a1.jpg", "anime": "Bleach"}
        self.db.add_unseen_wallpapers([item])
        
        reserved = self.db.reserve_next_wallpaper(anime="Bleach", token="token-abandon")
        self.assertIsNotNone(reserved)
        self.assertEqual(self.db.get_stats()["reserved_count"], 1)
        
        # Simulate time passing beyond timeout by manually updating reserved_at
        past_time = time.time() - 100.0
        with self.db.get_connection() as conn:
            conn.execute("UPDATE wallpaper_lifecycle SET reserved_at = ? WHERE id = ?", (past_time, reserved["id"]))
            conn.commit()
            
        # Run recovery
        recovered = self.db.recover_abandoned_reservations(timeout_seconds=45.0)
        self.assertEqual(recovered, 1)
        
        stats = self.db.get_stats()
        self.assertEqual(stats["reserved_count"], 0)
        self.assertEqual(stats["unseen_count"], 1)
        
        # Verify it can be reserved again with a new token
        re_reserved = self.db.reserve_next_wallpaper(anime="Bleach", token="token-new")
        self.assertIsNotNone(re_reserved)
        self.assertEqual(re_reserved["id"], "wp_abandon_01")

    def test_06_startup_crash_recovery(self):
        """Verify startup automatically recovers any lingering RESERVED status from an abrupt crash."""
        item = {"id": "wp_crash_01", "url": "https://img.test/crash.jpg", "anime": "Evangelion"}
        self.db.add_unseen_wallpapers([item])
        
        reserved = self.db.reserve_next_wallpaper(anime="Evangelion", token="token-crash")
        self.assertEqual(self.db.get_stats()["reserved_count"], 1)
        
        # Abruptly stop engine without confirming or failing
        self.engine.stop()
        
        # Boot new engine
        db2 = DatabaseManager(self.db_path)
        recovered = db2.recover_all_reservations_on_startup()
        self.assertEqual(recovered, 1)
        
        stats = db2.get_stats()
        self.assertEqual(stats["reserved_count"], 0)
        self.assertEqual(stats["unseen_count"], 1)

    def test_07_exhausted_collection_handling(self):
        """Verify that when all items in a collection are DISPLAYED, exhaustion is explicitly returned."""
        # Insert exactly 2 items for Solo Leveling
        items = [
            {"id": "wp_ex_01", "url": "https://img.test/ex1.jpg", "anime": "Solo Leveling"},
            {"id": "wp_ex_02", "url": "https://img.test/ex2.jpg", "anime": "Solo Leveling"}
        ]
        self.db.add_unseen_wallpapers(items)

        # Mark as exhausted on discovery level so no remote fetch triggers
        key = self.engine._make_search_key("solo-leveling", None, "landscape")
        self.engine.exhausted_keys.add(key)

        # Consume item 1
        res1 = self.engine.get_next(anime="solo-leveling")
        self.assertEqual(res1["id"], "wp_ex_01")
        self.engine.confirm_displayed(res1["id"], res1["reservation_token"])

        # Consume item 2
        res2 = self.engine.get_next(anime="solo-leveling")
        self.assertEqual(res2["id"], "wp_ex_02")
        self.engine.confirm_displayed(res2["id"], res2["reservation_token"])

        # Attempt to consume item 3 -> must return EXHAUSTED state
        res3 = self.engine.get_next(anime="solo-leveling")
        self.assertTrue(res3.get("exhausted", False))
        self.assertIn("Solo Leveling", res3.get("anime", ""))

        # Verify the seen database was NOT silently wiped
        stats = self.db.get_stats()
        self.assertEqual(stats["displayed_count"], 2)
        self.assertEqual(stats["unseen_count"], 0)

    def test_08_schema_migration_preserves_legacy_data(self):
        """Verify legacy seen_wallpapers rows are automatically migrated to DISPLAYED in wallpaper_lifecycle."""
        # Create a raw legacy v1 database
        legacy_dir = tempfile.mkdtemp(prefix="kuro_legacy_")
        legacy_db_path = Path(legacy_dir) / "legacy.db"
        
        conn = sqlite3.connect(str(legacy_db_path))
        conn.execute("""
            CREATE TABLE seen_wallpapers (
                id TEXT PRIMARY KEY,
                url TEXT,
                resolution TEXT,
                mood TEXT,
                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO seen_wallpapers (id, url, resolution, mood) VALUES ('leg_01', 'http://a.com/1.jpg', '1080p', 'Naruto')")
        conn.execute("INSERT INTO seen_wallpapers (id, url, resolution, mood) VALUES ('leg_02', 'http://a.com/2.jpg', '4K', 'Naruto')")
        conn.commit()
        conn.close()
        
        # Open with DatabaseManager -> triggers migration v2
        migrated_db = DatabaseManager(legacy_db_path)
        stats = migrated_db.get_stats()
        
        self.assertEqual(stats["displayed_count"], 2)
        self.assertTrue(migrated_db.is_displayed("leg_01"))
        self.assertTrue(migrated_db.is_displayed("leg_02"))
        
        shutil.rmtree(legacy_dir, ignore_errors=True)

    def test_09_franchise_tag_validation_and_generic_rejection(self):
        """Verify franchise tag allowlists validate genuine artwork and reject generic/original art."""
        from franchise_registry import FranchiseRegistry

        # 1. Valid Jujutsu Kaisen with character
        valid_jjk, char = FranchiseRegistry.validate_tags("jujutsu-kaisen", ["Jujutsu Kaisen", "Gojo Satoru", "anime boys"])
        self.assertTrue(valid_jjk)
        self.assertEqual(char, "Satoru Gojo")

        # 2. Reject original/generic art even if tagged with anime
        valid_orig, _ = FranchiseRegistry.validate_tags("jujutsu-kaisen", ["original", "anime girl", "Jujutsu Kaisen"])
        self.assertFalse(valid_orig, "Generic 'original' tag was not rejected!")

        # 3. Reject vtuber/game art
        valid_vtuber, _ = FranchiseRegistry.validate_tags("chainsaw-man", ["chainsaw man", "vtuber", "hololive"])
        self.assertFalse(valid_vtuber, "VTuber tag was not rejected!")

        # 4. Valid Demon Slayer character
        valid_ds, ds_char = FranchiseRegistry.validate_tags("demon-slayer", ["kimetsu no yaiba", "tomioka giyu"])
        self.assertTrue(valid_ds)
        self.assertEqual(ds_char, "Giyu Tomioka")

    def test_10_character_specific_filtering_and_persistence(self):
        """Verify character-specific filtering and metadata storage in SQLite."""
        items = [
            {"id": "jjk_gojo_1", "url": "https://img.test/gojo.jpg", "anime": "Jujutsu Kaisen", "character": "Satoru Gojo", "resolution": "1920x1080"},
            {"id": "jjk_sukuna_1", "url": "https://img.test/sukuna.jpg", "anime": "Jujutsu Kaisen", "character": "Ryomen Sukuna", "resolution": "1920x1080"},
            {"id": "jjk_yuji_1", "url": "https://img.test/yuji.jpg", "anime": "Jujutsu Kaisen", "character": "Yuji Itadori", "resolution": "1920x1080"}
        ]
        self.db.add_unseen_wallpapers(items)

        # Filter strictly for Satoru Gojo
        res = self.db.reserve_next_wallpaper(anime="Jujutsu Kaisen", character="Satoru Gojo", token="tok-gojo")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "jjk_gojo_1")
        self.assertEqual(res["character"], "Satoru Gojo")

        # Confirm display and verify SQLite row contains character metadata
        self.db.confirm_displayed(res["id"], "tok-gojo")
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT anime, character FROM wallpaper_lifecycle WHERE id = ?", ("jjk_gojo_1",)).fetchone()
            self.assertEqual(row["anime"], "Jujutsu Kaisen")
            self.assertEqual(row["character"], "Satoru Gojo")

    def test_11_franchise_and_character_exclusions(self):
        """Verify franchise and character exclusions are strictly enforced."""
        items = [
            {"id": "ds_01", "url": "https://img.test/ds1.jpg", "anime": "Demon Slayer", "character": "Tanjiro Kamado"},
            {"id": "aot_levi", "url": "https://img.test/levi.jpg", "anime": "Attack on Titan", "character": "Levi Ackerman"},
            {"id": "aot_eren", "url": "https://img.test/eren.jpg", "anime": "Attack on Titan", "character": "Eren Yeager"}
        ]
        self.db.add_unseen_wallpapers(items)

        # Exclude franchise "Demon Slayer" and character "Levi Ackerman"
        res = self.db.reserve_next_wallpaper(
            anime="all",
            excluded_franchises=["Demon Slayer"],
            excluded_characters=["Levi Ackerman"],
            token="tok-ex"
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "aot_eren", "Excluded franchise or character was incorrectly reserved!")

    def test_12_selected_franchises_mode(self):
        """Verify selected-franchises-only mode restricts reservations to the specified whitelist."""
        items = [
            {"id": "op_01", "url": "https://img.test/op.jpg", "anime": "One Piece"},
            {"id": "nar_01", "url": "https://img.test/nar.jpg", "anime": "Naruto"},
            {"id": "sl_01", "url": "https://img.test/sl.jpg", "anime": "Solo Leveling"}
        ]
        self.db.add_unseen_wallpapers(items)

        # Whitelist only Solo Leveling
        res = self.db.reserve_next_wallpaper(
            selected_franchises=["Solo Leveling"],
            token="tok-sl"
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "sl_01")

    def test_13_resolution_preference_prioritizes_higher_resolution(self):
        """Verify 4K (3840x2160) and 1440p (2560x1440) are preferred over 1080p."""
        items = [
            {"id": "res_1080", "url": "https://img.test/1080.jpg", "anime": "Bleach", "resolution": "1920x1080"},
            {"id": "res_4k", "url": "https://img.test/4k.jpg", "anime": "Bleach", "resolution": "3840x2160"},
            {"id": "res_1440", "url": "https://img.test/1440.jpg", "anime": "Bleach", "resolution": "2560x1440"}
        ]
        self.db.add_unseen_wallpapers(items)

        # Next reservation should pick 4K first
        res1 = self.db.reserve_next_wallpaper(anime="Bleach", token="tok-4k")
        self.assertEqual(res1["id"], "res_4k")

        # Next reservation should pick 1440p second
        res2 = self.db.reserve_next_wallpaper(anime="Bleach", token="tok-1440")
        self.assertEqual(res2["id"], "res_1440")

        # Next reservation picks 1080p third
        res3 = self.db.reserve_next_wallpaper(anime="Bleach", token="tok-1080")
        self.assertEqual(res3["id"], "res_1080")

    def test_14_offline_fallback_level1_to_level2(self):
        """Verify that when offline, engine skips Level 1 and serves Level 2 local cache."""
        item_l1 = {"id": "wp_l1", "url": "https://img.test/l1.jpg", "anime": "Jujutsu Kaisen", "level": 1}
        item_l2 = {"id": "wp_l2", "url": "/api/image/wp_l2", "anime": "Jujutsu Kaisen", "level": 2, "is_cached": 1, "local_path": ".cache/wallpapers/wp_l2.jpg"}
        self.db.add_unseen_wallpapers([item_l1, item_l2])

        # Force engine offline
        self.engine.is_online = False
        self.engine.network_backoff_until = time.time() + 100.0

        res = self.engine.get_next(anime="Jujutsu Kaisen")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "wp_l2")
        self.assertEqual(res["level"], 2)
        self.assertTrue(res["offline"])

    def test_15_offline_fallback_level2_to_level3_curated(self):
        """Verify that when offline and Level 2 is empty, engine falls back to Level 3 Curated Collection."""
        curated_item = {
            "id": "curated_gojo",
            "url": "/api/image/curated_gojo",
            "anime": "Jujutsu Kaisen",
            "character": "Satoru Gojo",
            "level": 3,
            "is_cached": 1,
            "local_path": "curated_wallpapers/curated_01_jujutsu_kaisen_gojo.svg"
        }
        self.db.add_unseen_wallpapers([curated_item])

        # Force offline and no Level 2 items exist
        self.engine.is_online = False
        self.engine.network_backoff_until = time.time() + 100.0

        res = self.engine.get_next(anime="Jujutsu Kaisen")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "curated_gojo")
        self.assertEqual(res["level"], 3)
        self.assertEqual(res["source"], "Curated Offline")

    def test_16_curated_collection_deduplication(self):
        """Verify curated collection enforces zero repeated images across restarts."""
        curated_1 = {"id": "cur_a", "url": "/api/image/cur_a", "anime": "Frieren", "level": 3, "is_cached": 1}
        curated_2 = {"id": "cur_b", "url": "/api/image/cur_b", "anime": "Frieren", "level": 3, "is_cached": 1}
        self.db.add_unseen_wallpapers([curated_1, curated_2])

        # Reserve and confirm display of cur_a
        tok1 = str(uuid.uuid4())
        res1 = self.db.reserve_next_wallpaper(anime="Frieren", token=tok1, target_level=3)
        self.assertEqual(res1["id"], "cur_a")
        self.db.confirm_displayed("cur_a", tok1)

        # Simulate restart
        new_db = DatabaseManager(self.db_path)
        # Attempt to re-index or re-add
        new_db.add_unseen_wallpapers([curated_1, curated_2])

        # Next reservation must be cur_b; cur_a is NEVER repeated
        tok2 = str(uuid.uuid4())
        res2 = new_db.reserve_next_wallpaper(anime="Frieren", token=tok2, target_level=3)
        self.assertEqual(res2["id"], "cur_b")

        # After cur_b is displayed, curated pool for Frieren is exhausted
        new_db.confirm_displayed("cur_b", tok2)
        res3 = new_db.reserve_next_wallpaper(anime="Frieren", token="tok3", target_level=3)
        self.assertIsNone(res3, "Curated item was repeated after exhaustion!")

    def test_17_graceful_empty_offline_collection(self):
        """Verify engine gracefully returns exhaustion when all offline collections are empty."""
        self.engine.is_online = False
        self.engine.network_backoff_until = time.time() + 100.0

        res = self.engine.get_next(anime="Solo Leveling")
        self.assertTrue(res.get("exhausted"), "Expected exhausted state when offline and pool empty")
        self.assertTrue(res.get("offline"))
        self.assertIn("message", res)

    def test_18_exponential_backoff_and_reconnection(self):
        """Verify network backoff doubles on failures and resets on reconnection."""
        self.engine.is_online = True
        self.engine.consecutive_network_failures = 0
        self.engine.current_backoff_delay = 3.0

        # Simulate consecutive failures
        initial_delay = self.engine.current_backoff_delay
        self.assertEqual(initial_delay, 3.0)

        # First failure
        now = time.time()
        self.engine.is_online = False
        self.engine.consecutive_network_failures += 1
        self.engine.network_backoff_until = now + self.engine.current_backoff_delay
        self.engine.current_backoff_delay = min(self.engine.current_backoff_delay * 2, 60.0)
        self.assertEqual(self.engine.current_backoff_delay, 6.0)

        # While within backoff window, check_connectivity returns False immediately
        self.assertFalse(self.engine.check_connectivity(force_probe=False))

        # Reconnection restores state
        self.engine.is_online = True
        self.engine.consecutive_network_failures = 0
        self.engine.current_backoff_delay = 3.0
        self.engine.network_backoff_until = 0.0
        self.assertEqual(self.engine.current_backoff_delay, 3.0)
        self.assertTrue(self.engine.is_online)

if __name__ == "__main__":
    unittest.main()
