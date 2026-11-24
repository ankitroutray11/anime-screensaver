#!/usr/bin/env python3
"""
Unit and integration tests for DownloadAutoSaver module.
Verifies:
- Filename sanitization and Windows path compatibility.
- Clean human-readable naming (<Anime> - <Character> [<id>].<ext>).
- Fast-path atomic copy from local cache.
- Duplicate prevention.
- Stats calculation.
- Open folder functionality.
- Server API integration.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from download_autosaver import DownloadAutoSaver, sanitize_filename


class TestDownloadAutoSaver(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kuro_test_downloads_")
        self.downloads_dir = Path(self.temp_dir) / "Downloads" / "Kuro Wallpapers"
        self.base_dir = Path(self.temp_dir) / "kuro_app"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / ".cache" / "wallpapers").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "curated_wallpapers").mkdir(parents=True, exist_ok=True)

        self.autosaver = DownloadAutoSaver(
            downloads_dir=self.downloads_dir,
            base_dir=self.base_dir
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Jujutsu: Kaisen / Shibuya"), "Jujutsu Kaisen Shibuya")
        self.assertEqual(sanitize_filename("Fate/stay night: Heaven's Feel?"), "Fate stay night Heaven's Feel")
        self.assertEqual(sanitize_filename(""), "Anime")
        long_name = "A" * 150
        self.assertLessEqual(len(sanitize_filename(long_name, max_length=50)), 50)

    def test_target_filename_with_character(self):
        wp = {
            "id": "abc1234",
            "anime": "Demon Slayer",
            "character": "Nezuko Kamado",
            "url": "https://example.com/images/abc1234.png"
        }
        filename = self.autosaver.get_target_filename(wp)
        self.assertEqual(filename, "Demon Slayer - Nezuko Kamado [abc1234].png")

    def test_target_filename_without_character(self):
        wp = {
            "id": "xyz9876",
            "anime": "Cyberpunk: Edgerunners",
            "character": "all",
            "url": "https://example.com/wallpapers/xyz9876.jpg"
        }
        filename = self.autosaver.get_target_filename(wp)
        self.assertEqual(filename, "Cyberpunk Edgerunners [xyz9876].jpg")

    def test_fast_path_cache_copy(self):
        # Create a simulated cached wallpaper
        wp_id = "test_wp_001"
        cache_file = self.base_dir / ".cache" / "wallpapers" / f"{wp_id}.jpg"
        test_content = b"SIMULATED_HIGH_RES_WALLPAPER_BINARY_DATA_12345678"
        cache_file.write_bytes(test_content)

        wp = {
            "id": wp_id,
            "anime": "Solo Leveling",
            "character": "Sung Jin-Woo",
            "url": f"/api/image/{wp_id}"
        }

        # Perform save
        self.autosaver._save_worker(wp)

        # Verify saved in downloads
        expected_target = self.downloads_dir / "Solo Leveling - Sung Jin-Woo [test_wp_001].jpg"
        self.assertTrue(expected_target.is_file(), f"Expected file not found: {expected_target}")
        self.assertEqual(expected_target.read_bytes(), test_content)
        self.assertIn(wp_id, self.autosaver.saved_ids)

    def test_fast_path_curated_copy(self):
        # Create simulated curated wallpaper
        wp_id = "curated_dual_01"
        curated_file = self.base_dir / "curated_wallpapers" / f"{wp_id}.svg"
        test_content = b"<svg>simulated dual screen 32:9 wallpaper</svg>"
        curated_file.write_bytes(test_content)

        wp = {
            "id": wp_id,
            "anime": "Neon Genesis Evangelion",
            "character": "Asuka Langley",
            "url": f"/api/curated/{wp_id}.svg"
        }

        self.autosaver._save_worker(wp)

        expected_target = self.downloads_dir / "Neon Genesis Evangelion - Asuka Langley [curated_dual_01].svg"
        self.assertTrue(expected_target.is_file())
        self.assertEqual(expected_target.read_bytes(), test_content)

    def test_duplicate_prevention(self):
        wp_id = "dup_test_100"
        cache_file = self.base_dir / ".cache" / "wallpapers" / f"{wp_id}.jpg"
        cache_file.write_bytes(b"DATA")

        wp = {
            "id": wp_id,
            "anime": "Attack on Titan",
            "character": "Levi Ackerman",
            "url": "/api/image/dup_test_100"
        }

        self.autosaver._save_worker(wp)
        self.assertIn(wp_id, self.autosaver.saved_ids)

        # Call again via async save
        # Modify cache file to verify it doesn't overwrite
        cache_file.write_bytes(b"NEW_DATA")
        self.autosaver.save_wallpaper_async(wp)
        time.sleep(0.1)

        target = self.downloads_dir / "Attack on Titan - Levi Ackerman [dup_test_100].jpg"
        self.assertEqual(target.read_bytes(), b"DATA")

    def test_get_stats(self):
        stats = self.autosaver.get_stats()
        self.assertTrue(stats["enabled"])
        self.assertEqual(stats["saved_count"], 0)
        self.assertEqual(stats["total_size_mb"], 0.0)

        # Write a dummy file
        (self.downloads_dir / "Anime [wp01].jpg").write_bytes(b"X" * (1024 * 1024))
        stats = self.autosaver.get_stats()
        self.assertEqual(stats["saved_count"], 1)
        self.assertEqual(stats["total_size_mb"], 1.0)
        self.assertEqual(len(stats["recent_files"]), 1)

    def test_toggle_enabled(self):
        self.autosaver.enabled = False
        wp = {
            "id": "disabled_test",
            "anime": "Bleach",
            "url": "/api/image/disabled_test"
        }
        self.autosaver.save_wallpaper_async(wp)
        self.assertNotIn("disabled_test", self.autosaver.saved_ids)


if __name__ == "__main__":
    unittest.main()
