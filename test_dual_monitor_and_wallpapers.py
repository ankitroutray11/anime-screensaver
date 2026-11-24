#!/usr/bin/env python3
"""
Unit and Integration Tests for Dual-Monitor & 32:9 Wallpaper Features
Covers:
1. MonitorDetector topology & multi-screen virtual coordinates.
2. Dual-screen 32:9 aspect ratio query construction across providers.
3. DualScreenManager server synchronization & state endpoints.
4. Coordinated Screen 0 / Screen 1 span mode delivery.
5. Curated 32:9 offline SVG wallpapers & metadata.
6. Launcher multi-monitor configuration & command flags.
"""

import os
import sys
import json
import time
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from monitor_detector import MonitorDetector
from franchise_registry import FranchiseRegistry
from providers import NormalizedWallpaper, WallhavenProvider, SafebooruProvider, KonachanProvider
from server import DualScreenManager


class TestDualMonitorTopology(unittest.TestCase):
    def test_classify_orientation_dual(self):
        # 3840x1080 -> 3.555 -> dual
        self.assertEqual(MonitorDetector.classify_orientation(3840, 1080), "dual")
        # 5120x1440 -> 3.555 -> dual
        self.assertEqual(MonitorDetector.classify_orientation(5120, 1440), "dual")
        # 3440x1440 -> 2.388 -> ultrawide
        self.assertEqual(MonitorDetector.classify_orientation(3440, 1440), "ultrawide")
        # 1920x1080 -> 1.777 -> landscape
        self.assertEqual(MonitorDetector.classify_orientation(1920, 1080), "landscape")
        # 1080x1920 -> 0.562 -> portrait
        self.assertEqual(MonitorDetector.classify_orientation(1080, 1920), "portrait")

    def test_get_dual_monitor_topology(self):
        topo = MonitorDetector.get_dual_monitor_topology()
        self.assertIsInstance(topo, dict)
        self.assertIn("is_dual", topo)
        self.assertIn("monitors", topo)
        self.assertIn("combined_resolution", topo)

        if topo["is_dual"]:
            self.assertGreaterEqual(topo["count"], 2)
            self.assertIsNotNone(topo["left_monitor"])
            self.assertIsNotNone(topo["right_monitor"])
            self.assertTrue(topo["span_supported"])
            # Left monitor x-coord must be <= right monitor x-coord
            self.assertLessEqual(topo["left_monitor"]["left"], topo["right_monitor"]["left"])
            # Combined width should equal or exceed single monitor
            self.assertGreaterEqual(topo["combined_width"], topo["left_monitor"]["width"])


class TestDualScreenProviderQueries(unittest.TestCase):
    def test_wallhaven_tag_query_ratio_dual(self):
        url = FranchiseRegistry.build_wallhaven_tag_query(
            tag_id=123,
            ratio="dual",
            min_resolution="1920x1080"
        )
        self.assertIn("ratios=32x9,32x10,21x9", url)

    def test_wallhaven_keyword_query_ratio_dual(self):
        url = FranchiseRegistry.build_wallhaven_keyword_query(
            keyword="Frieren",
            ratio="32:9",
            min_resolution="1920x1080"
        )
        self.assertIn("ratios=32x9,32x10,21x9", url)

    def test_normalized_wallpaper_32_9_classification(self):
        wp = NormalizedWallpaper(
            id="test_dual_01",
            provider="wallhaven",
            url="http://127.0.0.1/test.jpg",
            thumbnail_url="http://127.0.0.1/thumb.jpg",
            resolution="3840x1080",
            dimension_x=3840,
            dimension_y=1080,
            aspect_ratio="32:9" if (3840 / 1080 >= 2.85) else "landscape",
            file_size=1024,
            anime="Frieren",
            character="Frieren",
            tags=["frieren", "scenery"],
            purity="sfw",
            views=100,
            favorites=50,
            uploader="artist",
            upload_date="2026-01-01",
            source_url="http://127.0.0.1/source"
        )
        self.assertEqual(wp.aspect_ratio, "32:9")
        d = wp.to_candidate_dict()
        self.assertEqual(d["aspect_ratio"], "32:9")
        self.assertEqual(d["resolution"], "3840x1080")


class TestDualScreenManagerSync(unittest.TestCase):
    def setUp(self):
        DualScreenManager.update_state({"mode": "span", "bezel_compensation_px": 0})

    def test_state_management(self):
        st = DualScreenManager.get_state()
        self.assertEqual(st["mode"], "span")

        DualScreenManager.update_state({"mode": "sync", "bezel_compensation_px": 12})
        st2 = DualScreenManager.get_state()
        self.assertEqual(st2["mode"], "sync")
        self.assertEqual(st2["bezel_compensation_px"], 12)

    def test_span_wallpaper_coordination(self):
        sample_wp = {
            "id": "wp_dual_test_123",
            "url": "http://127.0.0.1:54321/api/image/test_dual",
            "resolution": "3840x1080",
            "aspect_ratio": "32:9",
            "anime": "Frieren"
        }
        tid = DualScreenManager.set_active_span_wallpaper(sample_wp)
        self.assertIsInstance(tid, str)
        self.assertTrue(len(tid) > 0)

        active = DualScreenManager.get_active_span_wallpaper()
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], "wp_dual_test_123")
        self.assertEqual(active["resolution"], "3840x1080")

    def test_screen_wallpaper_tracking_no_mirroring(self):
        wp0 = {"id": "wp_s0_16_9", "resolution": "1920x1080", "aspect_ratio": "landscape"}
        wp1 = {"id": "wp_s1_distinct", "resolution": "1920x1080", "aspect_ratio": "landscape"}

        DualScreenManager.set_screen_wallpaper("0", wp0)
        DualScreenManager.set_screen_wallpaper("1", wp1)

        s0 = DualScreenManager.get_screen_wallpaper("0")
        s1 = DualScreenManager.get_screen_wallpaper("1")

        self.assertEqual(s0["id"], "wp_s0_16_9")
        self.assertEqual(s1["id"], "wp_s1_distinct")
        self.assertNotEqual(s0["id"], s1["id"], "Screen 1 must not mirror Screen 0")


class TestCuratedDualScreenWallpapers(unittest.TestCase):
    def test_curated_dual_svgs_exist(self):
        curated_dir = PROJECT_ROOT / "curated_wallpapers"
        self.assertTrue(curated_dir.is_dir())

        dual_svgs = list(curated_dir.glob("curated_dual_*.svg"))
        self.assertGreaterEqual(len(dual_svgs), 3)

        for d_svg in dual_svgs:
            content = d_svg.read_text(encoding="utf-8")
            self.assertIn('viewBox="0 0 3840 1080"', content)
            self.assertIn('width="3840"', content)
            self.assertIn('height="1080"', content)

            meta_file = d_svg.with_suffix(".json")
            self.assertTrue(meta_file.is_file())
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            self.assertEqual(meta.get("resolution"), "3840x1080")
            self.assertEqual(meta.get("aspect_ratio"), "32:9")
            self.assertTrue(meta.get("is_dual_span"))


class TestLauncherDualConfig(unittest.TestCase):
    def test_launcher_status_execution(self):
        import subprocess
        res = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "launcher.py"), "status"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Monitors Detected:", res.stdout)
        if "Dual Monitor Topology:" in res.stdout:
            self.assertIn("3840x1080", res.stdout)
            self.assertIn("32:9", res.stdout)

    def test_launcher_defaults_single_screen(self):
        cfg_file = PROJECT_ROOT / "launcher_config.json"
        if cfg_file.is_file():
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            self.assertEqual(cfg.get("target_monitor"), "primary")
            self.assertEqual(cfg.get("mode"), "fullscreen")


if __name__ == "__main__":
    unittest.main()
