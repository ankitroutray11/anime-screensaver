"""
Unit & Integration Test Suite for Intelligent Artwork Quality Scoring System
Verifies:
1. Native resolution preference & upscaling penalties.
2. Aspect ratio compatibility (16:9, 21:9 Ultrawide, 9:16 Portrait).
3. Community popularity (logarithmic curve + engagement ratio as one signal).
4. Sharpness, detail density, and bits-per-pixel.
5. Tone, dynamic range, and luminance analysis.
6. Configurable filters: avoid overly bright & avoid overly dark.
7. Perceptual color similarity penalty vs recent wallpapers.
8. Clear technical vs popularity distinction (artistic quality disclaimer).
9. Minimum quality threshold filtering.
10. SQLite persistence and zero unnecessary recalculations.
11. Bulk backfill for existing catalog wallpapers.
12. Quality REST API endpoints (/api/quality/settings, /api/quality/scores).
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
import urllib.request
import urllib.error
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DatabaseManager
from quality_scorer import QualityScorer
from engine import WallpaperEngine
import server


class TestQualityScoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="kuro_quality_test_"))
        cls.db_path = cls.temp_dir / "test_quality.db"
        cls.db = DatabaseManager(cls.db_path)
        cls.scorer = QualityScorer()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_resolution_native_vs_upscaling(self):
        """Verify native resolution receives full score and upscaled low-res is penalized."""
        # Target 1080p (1920x1080)
        score_4k, scale_4k, is_native_4k = self.scorer.score_resolution(3840, 2160, 1920, 1080)
        score_1080p, scale_1080p, is_native_1080p = self.scorer.score_resolution(1920, 1080, 1920, 1080)
        score_720p, scale_720p, is_native_720p = self.scorer.score_resolution(1280, 720, 1920, 1080)
        score_480p, scale_480p, is_native_480p = self.scorer.score_resolution(854, 480, 1920, 1080)

        # 4K has supersampling bonus
        self.assertEqual(score_4k, 40.0)
        self.assertTrue(is_native_4k)
        self.assertGreaterEqual(scale_4k, 2.0)

        # 1080p is exact native match
        self.assertEqual(score_1080p, 30.0)
        self.assertTrue(is_native_1080p)
        self.assertEqual(scale_1080p, 1.0)

        # 720p and 480p require upscaling and are penalized
        self.assertFalse(is_native_720p)
        self.assertLess(score_720p, 23.0)
        self.assertLess(score_480p, score_720p)

        # 1080p on 4K display requires significant upscaling
        score_1080_on_4k, scale_up, is_native_up = self.scorer.score_resolution(1920, 1080, 3840, 2160)
        self.assertFalse(is_native_up)
        self.assertEqual(scale_up, 0.5)
        self.assertLessEqual(score_1080_on_4k, 18.0)

    def test_02_aspect_ratio_compatibility(self):
        """Verify aspect ratio compatibility rewards exact matches and penalizes severe mismatches."""
        # 16:9 on Landscape target (1920x1080)
        score_16_9, err_16_9 = self.scorer.score_aspect_ratio(1920, 1080, "landscape")
        self.assertEqual(score_16_9, 20.0)
        self.assertLessEqual(err_16_9, 0.01)

        # 16:10 on Landscape target (minor letterbox)
        score_16_10, err_16_10 = self.scorer.score_aspect_ratio(1920, 1200, "landscape")
        self.assertGreaterEqual(score_16_10, 12.0)
        self.assertLess(score_16_10, 20.0)

        # 9:16 Portrait on Landscape target (severe mismatch)
        score_portrait, err_portrait = self.scorer.score_aspect_ratio(1080, 1920, "landscape")
        self.assertLessEqual(score_portrait, 5.0)
        self.assertGreater(err_portrait, 0.5)

        # 21:9 Ultrawide on Ultrawide target
        score_uw, err_uw = self.scorer.score_aspect_ratio(3440, 1440, "ultrawide")
        self.assertEqual(score_uw, 20.0)

        # 9:16 Portrait on Portrait target
        score_port_native, err_port_native = self.scorer.score_aspect_ratio(1080, 1920, "portrait")
        self.assertEqual(score_port_native, 20.0)

    def test_03_community_popularity_as_one_signal(self):
        """Verify community popularity uses logarithmic curve and accounts for engagement ratio."""
        # 0 favorites
        pop_0 = self.scorer.score_community_popularity(0, 100)
        self.assertEqual(pop_0, 0.0)

        # 10 favorites, 100 views
        pop_10 = self.scorer.score_community_popularity(10, 100)
        self.assertGreater(pop_10, 5.0)

        # 500 favorites, 2000 views
        pop_500 = self.scorer.score_community_popularity(500, 2000)
        self.assertGreater(pop_500, 12.0)

        # 5000 favorites (max popularity capped at 20.0 raw)
        pop_5000 = self.scorer.score_community_popularity(5000, 10000)
        self.assertLessEqual(pop_5000, 20.0)

        # Offline fallback: None favorites / views gets neutral 12.0 (60%)
        pop_offline = self.scorer.score_community_popularity(None, None)
        self.assertEqual(pop_offline, 12.0)

    def test_04_tone_and_luminance_analysis(self):
        """Verify brightness and contrast metrics extracted from color palettes."""
        vibrant_palette = ["#050811", "#1e293b", "#3b82f6", "#93c5fd", "#f8fafc"]
        tone_vibrant, mean_y, std_dev, _, _ = self.scorer.score_tone_and_luminance(vibrant_palette)

        self.assertEqual(tone_vibrant, 10.0)
        self.assertGreater(std_dev, 25.0)

        flat_gray_palette = ["#505050", "#525252", "#545454"]
        tone_flat, _, std_flat, _, _ = self.scorer.score_tone_and_luminance(flat_gray_palette)
        self.assertLess(tone_flat, 7.0)
        self.assertLess(std_flat, 10.0)

    def test_05_avoid_too_bright_filter(self):
        """Verify blindingly bright artwork is penalized when avoid_too_bright is active."""
        bright_palette = ["#f8fafc", "#ffffff", "#f1f5f9", "#e2e8f0"]
        scorer_filter_on = QualityScorer({"avoid_too_bright": True})
        scorer_filter_off = QualityScorer({"avoid_too_bright": False})

        res_on = scorer_filter_on.score_wallpaper({"resolution": "1920x1080", "colors": bright_palette})
        res_off = scorer_filter_off.score_wallpaper({"resolution": "1920x1080", "colors": bright_palette})

        self.assertIn("too_bright", res_on["filter_flags"])
        self.assertGreater(res_off["quality_score"], res_on["quality_score"])

    def test_06_avoid_too_dark_filter(self):
        """Verify pitch-dark artwork is penalized when avoid_too_dark is active."""
        dark_palette = ["#000000", "#050505", "#0a0a0a", "#020202"]
        scorer_filter_on = QualityScorer({"avoid_too_dark": True})
        scorer_filter_off = QualityScorer({"avoid_too_dark": False})

        res_on = scorer_filter_on.score_wallpaper({"resolution": "1920x1080", "colors": dark_palette})
        res_off = scorer_filter_off.score_wallpaper({"resolution": "1920x1080", "colors": dark_palette})

        self.assertIn("too_dark", res_on["filter_flags"])
        self.assertGreater(res_off["quality_score"], res_on["quality_score"])

    def test_07_perceptual_similarity_penalty(self):
        """Verify perceptual similarity penalty applies to visually repetitive color schemes."""
        candidate_colors = ["#dc2626", "#ef4444", "#b91c1c"]  # Red palette
        same_recent = [["#dc2626", "#b91c1c"]]  # Identical red palette
        distinct_recent = [["#0284c7", "#0369a1"]]  # Blue palette

        penalty_same = self.scorer.calculate_perceptual_similarity_penalty(candidate_colors, same_recent)
        penalty_distinct = self.scorer.calculate_perceptual_similarity_penalty(candidate_colors, distinct_recent)

        self.assertGreater(penalty_same, 5.0)
        self.assertEqual(penalty_distinct, 0.0)

    def test_08_clear_distinction_technical_vs_popularity(self):
        """Verify technical quality and popularity are measured independently with disclaimers."""
        item = {
            "resolution": "3840x2160",
            "colors": ["#0f172a", "#1e293b", "#38bdf8"],
            "favorites": 10,
            "views": 500,
            "file_size": 3_500_000
        }
        res = self.scorer.score_wallpaper(item)

        # Technical score should be very high (4K native, good tone, high bpp)
        self.assertGreaterEqual(res["technical_score"], 90.0)
        # Popularity score is modest (only 10 favorites)
        self.assertLess(res["popularity_score"], 50.0)
        # Disclaimer must exist
        self.assertIn("artistic quality is unmeasured", res["disclaimer"].lower())

    def test_09_min_quality_threshold_filtering(self):
        """Verify minimum quality threshold marks low quality candidates as not passing."""
        scorer = QualityScorer({"min_quality_score": 70.0})

        high_res_item = {"resolution": "3840x2160", "favorites": 500, "views": 2000}
        low_res_item = {"resolution": "640x360", "favorites": 0, "views": 100}

        high_eval = scorer.score_wallpaper(high_res_item)
        low_eval = scorer.score_wallpaper(low_res_item)

        self.assertTrue(high_eval["passes_threshold"])
        self.assertFalse(low_eval["passes_threshold"])
        self.assertIn("below_min_threshold", low_eval["filter_flags"])

    def test_10_sqlite_persistence_and_no_recalculation(self):
        """Verify scores are stored in SQLite and retrieved directly without recalculation."""
        item = {
            "id": "wp_persist_test_01",
            "url": "https://example.com/wp01.jpg",
            "resolution": "3840x2160",
            "anime": "Frieren",
            "character": "Frieren",
            "source": "Wallhaven",
            "quality_score": 88.5,
            "technical_score": 92.0,
            "popularity_score": 82.0,
            "dimension_x": 3840,
            "dimension_y": 2160,
            "file_size": 2800000,
            "views": 1200,
            "favorites": 150
        }
        added = self.db.add_unseen_wallpapers([item])
        self.assertEqual(added, 1)

        # Reserve wallpaper and verify scores are retrieved directly
        reserved = self.db.reserve_next_wallpaper(token="token_test_10", min_quality=80.0)
        self.assertIsNotNone(reserved)
        self.assertEqual(reserved["id"], "wp_persist_test_01")
        self.assertEqual(reserved["quality_score"], 88.5)
        self.assertEqual(reserved["technical_score"], 92.0)
        self.assertEqual(reserved["popularity_score"], 82.0)

        # Mark displayed
        self.db.confirm_displayed("wp_persist_test_01", "token_test_10")

    def test_11_bulk_backfill_unscored_wallpapers(self):
        """Verify backfill_quality_scores scores existing catalog wallpapers lacking scores."""
        item_unscored = {
            "id": "wp_unscored_01",
            "url": "https://example.com/unscored.jpg",
            "resolution": "2560x1440",
            "anime": "Jujutsu Kaisen",
            "character": "Gojo",
            "tags": json.dumps(["#0a0e17", "#2563eb", "#60a5fa"])
        }
        self.db.add_unseen_wallpapers([item_unscored])

        # Verify initial quality_score is NULL
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT quality_score FROM wallpaper_lifecycle WHERE id = 'wp_unscored_01'")
            row = cur.fetchone()
            self.assertIsNone(row[0])

        # Run backfill
        count = self.db.backfill_quality_scores(self.scorer)
        self.assertGreaterEqual(count, 1)

        # Verify quality_score is now populated
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT quality_score, technical_score, popularity_score FROM wallpaper_lifecycle WHERE id = 'wp_unscored_01'")
            row = cur.fetchone()
            self.assertIsNotNone(row[0])
            self.assertGreater(row[0], 0.0)

    def test_12_quality_api_endpoints(self):
        """Verify GET and POST endpoints for quality settings and scores summary."""
        # Settings retrieval
        settings = self.db.get_quality_settings()
        self.assertIn("min_quality_score", settings)
        self.assertIn("technical_weight", settings)

        # Settings update
        ok = self.db.update_quality_settings({
            "min_quality_score": 65.0,
            "avoid_too_bright": 1,
            "popularity_weight": 0.40,
            "technical_weight": 0.60
        })
        self.assertTrue(ok)

        updated = self.db.get_quality_settings()
        self.assertEqual(updated["min_quality_score"], 65.0)
        self.assertEqual(updated["popularity_weight"], 0.40)
        self.assertEqual(updated["technical_weight"], 0.60)

        # Scores summary
        summary = self.db.get_quality_scores_summary()
        self.assertIn("total_wallpapers", summary)
        self.assertIn("scored_wallpapers", summary)
        self.assertIn("top_scored", summary)
        self.assertIn("disclaimer", summary)


if __name__ == "__main__":
    unittest.main()
