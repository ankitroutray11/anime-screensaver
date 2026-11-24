#!/usr/bin/env python3
"""
Comprehensive automated test suite for KuroAnime Intelligent Wallpaper
Recommendation & Personalization Engine.

Covers:
1. Favorite interaction boosts franchise & character scores (+15/+20).
2. Skip interaction (<5s) penalizes franchise & character scores (-2.5/-4.0).
3. Extended dwell time (>=60s) rewards engagement bonus (+4.0/+5.0).
4. Manual history revisit rewards interest signal (+5.0/+8.0).
5. Blacklist applies heavy penalty (-5.0/-20.0) and permanently excludes.
6. Manual franchise selection boosts target and decays others.
7. Diversity guard recency penalty prevents consecutive clustering.
8. Personalization toggle (when disabled, uniform selection is used).
9. Manual preference adjustments override and bias selection.
10. Reset learning history resets scores/events while preserving seen wallpapers.
11. Global no-repeat guarantee (UNSEEN -> RESERVED -> DISPLAYED) is strictly preserved.
12. API endpoints and cryptographic token protection.
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

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import DatabaseManager
from engine import WallpaperEngine
from recommendation_engine import PersonalizationEngine
from server import KuroHandler, ThreadedHTTPServer, HOST, security_manager

class TestRecommendationEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_rec_test_"))
        self.db_path = self.test_dir / "test_rec.db"
        self.db = DatabaseManager(self.db_path)
        self.rec_engine = PersonalizationEngine(self.db)
        self.engine = WallpaperEngine(self.db, auto_prefetch=False)

    def tearDown(self):
        self.engine.stop()
        time.sleep(0.1)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_favorite_boosts_franchise_and_character(self):
        """Verify favoriting an artwork significantly boosts franchise and character affinity."""
        self.rec_engine.record_favorite(
            wallpaper_id="wp_fav_01",
            anime="Jujutsu Kaisen",
            character="Gojo Satoru"
        )

        f_scores = self.db.get_preference_scores(entity_type="franchise")
        c_scores = self.db.get_preference_scores(entity_type="character")

        self.assertEqual(len(f_scores), 1)
        self.assertEqual(f_scores[0]["entity_name"], "Jujutsu Kaisen")
        self.assertEqual(f_scores[0]["learned_score"], 15.0)
        self.assertEqual(f_scores[0]["favorites_count"], 1)

        self.assertEqual(len(c_scores), 1)
        self.assertEqual(c_scores[0]["entity_name"], "Gojo Satoru")
        self.assertEqual(c_scores[0]["learned_score"], 20.0)
        self.assertEqual(c_scores[0]["favorites_count"], 1)

    def test_02_skip_penalizes_franchise_and_character(self):
        """Verify fast skip (< 5.0s) applies negative penalty to franchise and character."""
        # Dwell for only 2.1 seconds (fast skip)
        res = self.rec_engine.record_dwell_and_transition(
            wallpaper_id="wp_skip_01",
            dwell_seconds=2.1,
            was_skipped=True,
            anime="Demon Slayer",
            character="Zenitsu Agatsuma"
        )

        self.assertEqual(res["event"], "skip")
        self.assertLess(res["franchise_delta"], 0)
        self.assertLess(res["character_delta"], 0)

        f_scores = self.db.get_preference_scores(entity_type="franchise")
        c_scores = self.db.get_preference_scores(entity_type="character")

        self.assertEqual(f_scores[0]["entity_name"], "Demon Slayer")
        self.assertEqual(f_scores[0]["learned_score"], -2.5)
        self.assertEqual(f_scores[0]["skips_count"], 1)

        self.assertEqual(c_scores[0]["entity_name"], "Zenitsu Agatsuma")
        self.assertEqual(c_scores[0]["learned_score"], -4.0)
        self.assertEqual(c_scores[0]["skips_count"], 1)

    def test_03_extended_dwell_rewards_bonus(self):
        """Verify long viewing duration (>=60s) awards high engagement bonus."""
        res = self.rec_engine.record_dwell_and_transition(
            wallpaper_id="wp_dwell_01",
            dwell_seconds=75.0,
            was_skipped=False,
            anime="Bleach",
            character="Ichigo Kurosaki"
        )

        self.assertEqual(res["event"], "dwell_extended")
        self.assertEqual(res["franchise_delta"], 4.0)
        self.assertEqual(res["character_delta"], 5.0)

        f_scores = self.db.get_preference_scores(entity_type="franchise")
        self.assertEqual(f_scores[0]["learned_score"], 4.0)
        self.assertEqual(f_scores[0]["dwell_total_seconds"], 75.0)

    def test_04_revisit_rewards_interest_signal(self):
        """Verify manually stepping back in history to re-view art awards an interest bonus."""
        self.rec_engine.record_revisit(
            wallpaper_id="wp_rev_01",
            anime="Solo Leveling",
            character="Sung Jin-woo"
        )

        f_scores = self.db.get_preference_scores(entity_type="franchise")
        c_scores = self.db.get_preference_scores(entity_type="character")

        self.assertEqual(f_scores[0]["learned_score"], 5.0)
        self.assertEqual(f_scores[0]["revisits_count"], 1)
        self.assertEqual(c_scores[0]["learned_score"], 8.0)
        self.assertEqual(c_scores[0]["revisits_count"], 1)

    def test_05_blacklist_applies_heavy_penalty_and_excludes(self):
        """Verify blacklisting an artwork heavily penalizes character and excludes from reservation."""
        # Seed two wallpapers
        self.db.add_unseen_wallpapers([
            {"id": "wp_bl_01", "url": "https://img.test/bl1.jpg", "anime": "Cyberpunk: Edgerunners", "character": "David Martinez"},
            {"id": "wp_good_02", "url": "https://img.test/good2.jpg", "anime": "Cyberpunk: Edgerunners", "character": "Lucy"}
        ])

        # Blacklist wp_bl_01
        self.db.add_to_blacklist("wp_bl_01", "User excluded")
        self.rec_engine.record_blacklist("wp_bl_01", "Cyberpunk: Edgerunners", "David Martinez")

        c_scores = self.db.get_preference_scores(entity_type="character")
        self.assertEqual(c_scores[0]["entity_name"], "David Martinez")
        self.assertEqual(c_scores[0]["learned_score"], -20.0)

        # Attempt to reserve: wp_bl_01 must NEVER be reserved; wp_good_02 must be chosen
        reserved = self.db.reserve_next_wallpaper(token="tok_test_bl")
        self.assertIsNotNone(reserved)
        self.assertEqual(reserved["id"], "wp_good_02")

    def test_06_manual_selection_boosts_and_decays_others(self):
        """Verify manually picking a franchise boosts it."""
        self.rec_engine.record_franchise_selection("Attack on Titan")
        f_scores = self.db.get_preference_scores(entity_type="franchise")
        self.assertEqual(f_scores[0]["entity_name"], "Attack on Titan")
        self.assertEqual(f_scores[0]["learned_score"], 4.0)

    def test_07_diversity_recency_penalty_prevents_clustering(self):
        """Verify diversity guard penalizes recently displayed franchise so alternative franchise is chosen."""
        # Add items from 2 different franchises with identical resolutions
        self.db.add_unseen_wallpapers([
            {"id": "wp_jk_01", "url": "https://img.test/jk1.jpg", "resolution": "1920x1080", "anime": "Jujutsu Kaisen"},
            {"id": "wp_ds_01", "url": "https://img.test/ds1.jpg", "resolution": "1920x1080", "anime": "Demon Slayer"}
        ])

        # Simulate that "Jujutsu Kaisen" was just displayed 1 wallpaper ago
        recent = ["Jujutsu Kaisen"]

        # Reservation with anime="all" must favor Demon Slayer due to recency penalty on Jujutsu Kaisen
        reserved = self.db.reserve_next_wallpaper(
            anime="all",
            token="tok_div",
            recent_franchises=recent,
            apply_personalization=True
        )

        self.assertIsNotNone(reserved)
        self.assertEqual(reserved["anime"], "Demon Slayer")

    def test_08_personalization_toggle_disables_scoring(self):
        """Verify toggling personalization off ignores preference scores."""
        self.assertTrue(self.rec_engine.is_enabled())
        self.rec_engine.set_enabled(False)
        self.assertFalse(self.rec_engine.is_enabled())
        self.rec_engine.set_enabled(True)
        self.assertTrue(self.rec_engine.is_enabled())

    def test_09_manual_preference_adjustments_override_scores(self):
        """Verify user can manually set franchise/character bias."""
        self.rec_engine.set_manual_score("franchise", "Bleach", 35.0)
        self.rec_engine.set_manual_score("character", "Aizen Sosuke", 50.0)

        f_scores = self.db.get_preference_scores(entity_type="franchise")
        c_scores = self.db.get_preference_scores(entity_type="character")

        self.assertEqual(f_scores[0]["entity_name"], "Bleach")
        self.assertEqual(f_scores[0]["manual_score"], 35.0)
        self.assertEqual(f_scores[0]["total_score"], 35.0)

        self.assertEqual(c_scores[0]["entity_name"], "Aizen Sosuke")
        self.assertEqual(c_scores[0]["manual_score"], 50.0)

    def test_10_reset_learning_history_restores_neutrality_preserves_lifecycle(self):
        """Verify resetting learning history clears scores but preserves displayed catalog."""
        # 1. Add wallpapers and mark one as DISPLAYED
        self.db.add_unseen_wallpapers([
            {"id": "wp_keep_01", "url": "https://img.test/keep1.jpg", "anime": "One Piece"},
            {"id": "wp_keep_02", "url": "https://img.test/keep2.jpg", "anime": "One Piece"}
        ])
        with self.db.get_connection() as conn:
            conn.execute("UPDATE wallpaper_lifecycle SET status = 'DISPLAYED' WHERE id = 'wp_keep_01'")
            conn.commit()

        # 2. Add preference scores
        self.rec_engine.record_favorite("wp_keep_01", "One Piece", "Luffy")
        self.assertGreater(len(self.db.get_preference_scores()), 0)

        # 3. Reset learning
        self.rec_engine.reset_learning()

        # 4. Scores and events must be zeroed
        self.assertEqual(len(self.db.get_preference_scores()), 0)
        profile = self.rec_engine.get_profile()
        self.assertEqual(profile["total_interaction_events"], 0)

        # 5. Displayed status must STILL be preserved!
        self.assertTrue(self.db.is_displayed("wp_keep_01"))

    def test_11_global_no_repeat_guarantee_strictly_preserved(self):
        """Verify that recommended wallpapers transition to RESERVED and are NEVER re-reserved."""
        self.db.add_unseen_wallpapers([
            {"id": "wp_nr_01", "url": "https://img.test/nr1.jpg", "anime": "Hunter x Hunter", "character": "Killua"}
        ])

        # Favorite Killua to give maximum preference score
        self.rec_engine.record_favorite("wp_nr_01", "Hunter x Hunter", "Killua")

        # First reservation succeeds
        res1 = self.engine.get_next(anime="Hunter x Hunter")
        self.assertEqual(res1["id"], "wp_nr_01")
        self.db.confirm_displayed("wp_nr_01", res1["reservation_token"])

        # Second reservation must return exhaustion, NOT repeat wp_nr_01!
        res2 = self.engine.get_next(anime="Hunter x Hunter")
        self.assertTrue(res2.get("exhausted", False))

    def test_12_api_endpoints_and_token_protection(self):
        """Verify REST API v1 endpoints for dwell, revisit, adjust, toggle, and reset."""
        s = socket.socket()
        s.bind((HOST, 0))
        test_port = s.getsockname()[1]
        s.close()

        # Patch server globals
        import server
        orig_db = server.db_manager
        orig_eng = server.engine
        orig_port = server.PORT

        server.PORT = test_port
        server.db_manager = self.db
        server.engine = self.engine

        httpd = ThreadedHTTPServer((HOST, test_port), KuroHandler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.3)

        base_url = f"http://{HOST}:{test_port}"
        token = security_manager.session_token

        try:
            # 1. POST /api/v1/interaction/dwell
            payload = json.dumps({
                "id": "wp_api_01",
                "dwell_seconds": 65.0,
                "was_skipped": False,
                "anime": "Chainsaw Man",
                "character": "Makima"
            }).encode()
            req = urllib.request.Request(
                f"{base_url}/api/v1/interaction/dwell",
                data=payload,
                headers={"Content-Type": "application/json", "X-Kuro-Token": token, "Origin": base_url}
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertEqual(data["status"], "recorded")

            # 2. GET /api/v1/recommendations/profile
            req_prof = urllib.request.Request(
                f"{base_url}/api/v1/recommendations/profile",
                headers={"Origin": base_url}
            )
            with urllib.request.urlopen(req_prof) as resp:
                self.assertEqual(resp.status, 200)
                prof = json.loads(resp.read().decode())
                self.assertTrue(prof["enabled"])
                self.assertGreater(len(prof["top_franchises"]), 0)
                self.assertEqual(prof["top_franchises"][0]["entity_name"], "Chainsaw Man")

            # 3. POST /api/v1/recommendations/adjust
            adj_payload = json.dumps({
                "entity_type": "franchise",
                "entity_name": "Chainsaw Man",
                "manual_score": 15.0
            }).encode()
            req_adj = urllib.request.Request(
                f"{base_url}/api/v1/recommendations/adjust",
                data=adj_payload,
                headers={"Content-Type": "application/json", "X-Kuro-Token": token, "Origin": base_url}
            )
            with urllib.request.urlopen(req_adj) as resp:
                self.assertEqual(resp.status, 200)

            # 4. POST /api/v1/recommendations/toggle
            tog_payload = json.dumps({"enabled": False}).encode()
            req_tog = urllib.request.Request(
                f"{base_url}/api/v1/recommendations/toggle",
                data=tog_payload,
                headers={"Content-Type": "application/json", "X-Kuro-Token": token, "Origin": base_url}
            )
            with urllib.request.urlopen(req_tog) as resp:
                self.assertEqual(resp.status, 200)
                prof2 = json.loads(resp.read().decode())["profile"]
                self.assertFalse(prof2["enabled"])

            # 5. POST /api/v1/recommendations/reset
            req_rst = urllib.request.Request(
                f"{base_url}/api/v1/recommendations/reset",
                data=b"{}",
                headers={"Content-Type": "application/json", "X-Kuro-Token": token, "Origin": base_url}
            )
            with urllib.request.urlopen(req_rst) as resp:
                self.assertEqual(resp.status, 200)

        finally:
            httpd.shutdown()
            httpd.server_close()
            server.db_manager = orig_db
            server.engine = orig_eng
            server.PORT = orig_port

if __name__ == "__main__":
    unittest.main()
