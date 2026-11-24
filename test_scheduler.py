"""
Automated Unit and Integration Tests for Intelligent Slideshow Scheduling System.
Tests:
- Fixed interval calculation
- Random interval generation within range
- Quality / Rating weighted duration bonuses (high score, low score, favorite)
- Time-of-day interval slots (Day, Evening, Night)
- Franchise rotation tracking and advancing
- Manual-only mode (infinite duration / disabled timer)
- Display mode overrides (Cinematic, Dashboard)
- Bound clamping (5s - 600s)
- Database schema migration v8 & CRUD persistence
- Server REST API endpoints (/api/scheduler/settings GET & POST with CSRF token)
"""

import unittest
import json
import urllib.request
import urllib.error
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from database import DatabaseManager
from scheduler import SlideshowScheduler
import server

class TestSlideshowScheduler(unittest.TestCase):
    def setUp(self):
        self.scheduler = SlideshowScheduler({
            "strategy": "fixed",
            "fixed_seconds": 30,
            "random_min": 15,
            "random_max": 60,
            "day_seconds": 25,
            "evening_seconds": 35,
            "night_seconds": 60,
            "cinematic_seconds": 45,
            "dashboard_seconds": 20,
            "quality_bonus_enabled": True,
            "pause_on_hidden": True,
            "franchise_rotation_interval": 3
        })

    def test_fixed_strategy(self):
        self.scheduler.update_settings({"strategy": "fixed", "fixed_seconds": 30})
        duration = self.scheduler.calculate_slide_duration(wallpaper={})
        self.assertEqual(duration, 30.0)

    def test_random_strategy(self):
        self.scheduler.update_settings({"strategy": "random", "random_min": 15, "random_max": 45})
        for _ in range(20):
            duration = self.scheduler.calculate_slide_duration(wallpaper={})
            self.assertGreaterEqual(duration, 15.0)
            self.assertLessEqual(duration, 45.0)

    def test_quality_weighted_strategy(self):
        self.scheduler.update_settings({"strategy": "quality_weighted", "fixed_seconds": 30})
        
        # High quality score: 95
        high_wp = {"quality_score": 95, "is_favorite": False}
        high_dur = self.scheduler.calculate_slide_duration(wallpaper=high_wp)
        self.assertGreater(high_dur, 30.0)

        # Baseline score: 70
        base_wp = {"quality_score": 70, "is_favorite": False}
        base_dur = self.scheduler.calculate_slide_duration(wallpaper=base_wp)
        self.assertEqual(base_dur, 30.0)

        # Low quality score: 20
        low_wp = {"quality_score": 20, "is_favorite": False}
        low_dur = self.scheduler.calculate_slide_duration(wallpaper=low_wp)
        self.assertLess(low_dur, 30.0)
        self.assertGreaterEqual(low_dur, 5.0)

        # Favorite bonus (+10s)
        fav_wp = {"quality_score": 70, "is_favorite": True}
        fav_dur = self.scheduler.calculate_slide_duration(wallpaper=fav_wp)
        self.assertEqual(fav_dur, 40.0)

    def test_time_of_day_strategy(self):
        self.scheduler.update_settings({
            "strategy": "time_of_day",
            "day_seconds": 25,
            "evening_seconds": 35,
            "night_seconds": 60,
            "quality_bonus_enabled": False
        })
        # 11:00 AM -> Day
        day_dur = self.scheduler.calculate_slide_duration(wallpaper={}, current_hour=11)
        self.assertEqual(day_dur, 25.0)

        # 19:00 -> Evening
        eve_dur = self.scheduler.calculate_slide_duration(wallpaper={}, current_hour=19)
        self.assertEqual(eve_dur, 35.0)

        # 02:00 -> Night
        night_dur = self.scheduler.calculate_slide_duration(wallpaper={}, current_hour=2)
        self.assertEqual(night_dur, 60.0)

    def test_franchise_rotation_advancement(self):
        self.scheduler.update_settings({"franchise_rotation_interval": 3})
        franchises = ["jujutsu-kaisen", "demon-slayer", "attack-on-titan"]
        
        # Slide 1: no rotation
        r1 = self.scheduler.advance_franchise_slide(franchises)
        self.assertIsNone(r1)

        # Slide 2: no rotation
        r2 = self.scheduler.advance_franchise_slide(franchises)
        self.assertIsNone(r2)

        # Slide 3: rotates to demon-slayer
        r3 = self.scheduler.advance_franchise_slide(franchises)
        self.assertEqual(r3, "demon-slayer")

        # Slide 4: no rotation
        r4 = self.scheduler.advance_franchise_slide(franchises)
        self.assertIsNone(r4)

    def test_manual_mode(self):
        self.scheduler.update_settings({"strategy": "manual"})
        duration = self.scheduler.calculate_slide_duration(wallpaper={})
        self.assertEqual(duration, float("inf"))

    def test_display_mode_overrides(self):
        self.scheduler.update_settings({
            "strategy": "fixed",
            "fixed_seconds": 25,
            "cinematic_seconds": 45,
            "dashboard_seconds": 15,
            "quality_bonus_enabled": False
        })
        # Ambient mode uses base
        ambient_dur = self.scheduler.calculate_slide_duration(wallpaper={}, display_mode="ambient")
        self.assertEqual(ambient_dur, 25.0)

        # Cinematic mode scales up to cinematic_seconds
        cinematic_dur = self.scheduler.calculate_slide_duration(wallpaper={}, display_mode="cinematic")
        self.assertEqual(cinematic_dur, 45.0)

        # Dashboard mode scales down to dashboard_seconds
        dashboard_dur = self.scheduler.calculate_slide_duration(wallpaper={}, display_mode="dashboard")
        self.assertEqual(dashboard_dur, 15.0)

    def test_duration_bounds_clamping(self):
        # Even with extreme settings, clamp between 5.0 and 600.0
        self.scheduler.update_settings({"strategy": "fixed", "fixed_seconds": 2, "quality_bonus_enabled": False})
        min_dur = self.scheduler.calculate_slide_duration(wallpaper={})
        self.assertEqual(min_dur, 5.0)

        self.scheduler.update_settings({"strategy": "fixed", "fixed_seconds": 1000, "quality_bonus_enabled": False})
        max_dur = self.scheduler.calculate_slide_duration(wallpaper={})
        self.assertEqual(max_dur, 600.0)


class TestSchedulerDatabaseAndAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "test_kuro.db"
        cls.db_manager = DatabaseManager(cls.db_path)
        cls.scheduler = SlideshowScheduler(cls.db_manager.get_scheduler_settings())

        # Save server state
        cls.orig_db = server.db_manager
        cls.orig_engine = server.engine
        cls.orig_port = server.PORT

        server.db_manager = cls.db_manager
        server.engine.db_manager = cls.db_manager
        server.engine.scheduler = cls.scheduler

        # Pick dynamic test port
        cls.port = 54440
        server.PORT = cls.port
        cls.server = server.ThreadedHTTPServer(("127.0.0.1", cls.port), server.KuroHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        server.db_manager = cls.orig_db
        server.engine = cls.orig_engine
        server.PORT = cls.orig_port
        cls.temp_dir.cleanup()

    def setUp(self):
        # Reset DB settings to default before each test
        self.db_manager.update_scheduler_settings({
            "strategy": "fixed",
            "fixed_seconds": 30,
            "random_min": 15,
            "random_max": 60,
            "day_seconds": 25,
            "evening_seconds": 35,
            "night_seconds": 60,
            "cinematic_seconds": 45,
            "dashboard_seconds": 20,
            "quality_bonus_enabled": True,
            "pause_on_hidden": True,
            "franchise_rotation_interval": 5
        })

    def test_database_crud(self):
        settings = self.db_manager.get_scheduler_settings()
        self.assertIn("strategy", settings)
        self.assertIn("fixed_seconds", settings)
        self.assertIn("day_seconds", settings)
        self.assertEqual(settings["strategy"], "fixed")

        # Update settings in DB
        ok = self.db_manager.update_scheduler_settings({
            "strategy": "time_of_day",
            "day_seconds": 22,
            "evening_seconds": 38,
            "night_seconds": 75,
            "franchise_rotation_interval": 7
        })
        self.assertTrue(ok)

        updated = self.db_manager.get_scheduler_settings()
        self.assertEqual(updated["strategy"], "time_of_day")
        self.assertEqual(updated["day_seconds"], 22)
        self.assertEqual(updated["evening_seconds"], 38)
        self.assertEqual(updated["night_seconds"], 75)
        self.assertEqual(updated["franchise_rotation_interval"], 7)

    def test_api_scheduler_get_and_post(self):
        # 1. GET /api/scheduler/settings
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/scheduler/settings")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("strategy", data)
            self.assertIn("fixed_seconds", data)

        # 2. POST without CSRF token fails (401 Unauthorized)
        payload = json.dumps({"strategy": "random", "random_min": 18, "random_max": 50}).encode("utf-8")
        req_bad = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/scheduler/settings",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_bad)
        self.assertEqual(ctx.exception.code, 401)

        # 3. POST with valid CSRF token succeeds
        token = server.security_manager.session_token
        req_good = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/scheduler/settings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": token
            }
        )
        with urllib.request.urlopen(req_good) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res_data["status"], "updated")
            self.assertEqual(res_data["settings"]["strategy"], "random")
            self.assertEqual(res_data["settings"]["random_min"], 18)
            self.assertEqual(res_data["settings"]["random_max"], 50)


if __name__ == "__main__":
    unittest.main()
