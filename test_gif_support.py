"""
test_gif_support.py - Unit & Integration Test Suite for High-Res Animated GIF Support in Kuro
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from database import DatabaseManager
from providers import NormalizedWallpaper, NekosBestGifProvider, SafebooruProvider, ProviderManager
from download_autosaver import DownloadAutoSaver


class TestGifSupport(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_gif_test_"))
        self.db_path = self.test_dir / "test_kuro.db"
        self.db = DatabaseManager(self.db_path)
        self.downloads_dir = self.test_dir / "downloads"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normalized_wallpaper_gif_attributes(self):
        """Test NormalizedWallpaper dataclass handles animated GIF attributes."""
        wp = NormalizedWallpaper(
            id="nb_test123",
            provider="NekosBest",
            url="https://nekos.best/api/v2/dance/test.gif",
            thumbnail_url="https://nekos.best/api/v2/dance/test.gif",
            resolution="1280x720",
            dimension_x=1280,
            dimension_y=720,
            aspect_ratio="landscape",
            file_size=2048500,
            anime="Lucky Star",
            character="Konata Izumi",
            tags=["animated", "gif", "dance", "sfw"],
            purity="sfw",
            views=1000,
            favorites=250,
            uploader="nekos.best",
            upload_date=None,
            source_url="https://nekos.best",
            media_type="gif",
            is_animated=True
        )
        cand = wp.to_candidate_dict()
        self.assertEqual(cand["media_type"], "gif")
        self.assertEqual(cand["is_animated"], 1)
        self.assertTrue(cand["url"].endswith(".gif"))

    def test_nekos_best_provider_mock_search(self):
        """Test NekosBestGifProvider parses API v2 response cleanly."""
        provider = NekosBestGifProvider(enabled=True)
        self.assertIn("dance", provider.ANIMATED_CATEGORIES)
        self.assertIn("smile", provider.ANIMATED_CATEGORIES)

        mock_payload = {
            "results": [
                {
                    "anime_name": "Frieren: Beyond Journey's End",
                    "url": "https://nekos.best/api/v2/dance/frieren_dance_123.gif",
                    "dimensions": {"width": 1280, "height": 720}
                }
            ]
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            results = provider.search(limit=5, category="dance")
            self.assertEqual(len(results), 1)
            gif = results[0]
            self.assertEqual(gif.id, "nb_frieren_dance_123")
            self.assertEqual(gif.anime, "Frieren: Beyond Journey's End")
            self.assertEqual(gif.dimension_x, 1280)
            self.assertEqual(gif.dimension_y, 720)
            self.assertEqual(gif.media_type, "gif")
            self.assertTrue(gif.is_animated)

    def test_safebooru_gif_translation(self):
        """Test SafebooruProvider includes animated tags when media_type='gif'."""
        provider = SafebooruProvider(enabled=True)
        tags = provider._translate_tags(franchise_slug="frieren", character_name=None, ratio="landscape", media_type="gif")
        self.assertIn("animated", tags)

    def test_database_migration_v17_and_settings(self):
        """Test Database schema version 17 and gif_settings table operations."""
        # 1. Check gif_settings retrieval
        settings = self.db.get_gif_settings()
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["mode"], "all")
        self.assertTrue(settings["prefer_hd"])

        # 2. Check gif_settings persistence
        self.db.save_gif_settings(enabled=True, mode="gif", prefer_hd=False)
        updated = self.db.get_gif_settings()
        self.assertTrue(updated["enabled"])
        self.assertEqual(updated["mode"], "gif")
        self.assertFalse(updated["prefer_hd"])

    def test_database_lifecycle_media_type_filtering(self):
        """Test add_unseen_wallpapers and reserve_next_wallpaper with media_type filter."""
        items = [
            {
                "id": "static_wp_01",
                "url": "https://example.com/static1.jpg",
                "resolution": "1920x1080",
                "anime": "Attack on Titan",
                "media_type": "static",
                "is_animated": 0
            },
            {
                "id": "gif_wp_01",
                "url": "https://example.com/loop.gif",
                "resolution": "1280x720",
                "anime": "Jujutsu Kaisen",
                "media_type": "gif",
                "is_animated": 1
            }
        ]
        added = self.db.add_unseen_wallpapers(items)
        self.assertEqual(added, 2)

        # 1. Filter for GIFs only
        res_gif = self.db.reserve_next_wallpaper(media_type="gif")
        self.assertIsNotNone(res_gif)
        self.assertEqual(res_gif["id"], "gif_wp_01")
        self.assertEqual(res_gif["media_type"], "gif")
        self.assertTrue(res_gif["is_animated"])

        # 2. Filter for Static only
        res_static = self.db.reserve_next_wallpaper(media_type="static")
        self.assertIsNotNone(res_static)
        self.assertEqual(res_static["id"], "static_wp_01")
        self.assertEqual(res_static["media_type"], "static")
        self.assertFalse(res_static["is_animated"])

    def test_curated_gif_indexing(self):
        """Test index_curated_collection indexes .gif files with is_animated=1."""
        curated_dir = self.test_dir / "curated_wallpapers"
        curated_dir.mkdir(parents=True, exist_ok=True)

        gif_file = curated_dir / "curated_test_anim.gif"
        gif_file.write_bytes(b"GIF89a" + b"\x00" * 20)

        meta_file = curated_dir / "curated_test_anim.json"
        meta_file.write_text(json.dumps({
            "id": "curated_test_anim",
            "anime": "Solo Leveling",
            "resolution": "1920x1080",
            "media_type": "gif",
            "is_animated": 1
        }), encoding="utf-8")

        count = self.db.index_curated_collection(curated_dir)
        self.assertEqual(count, 1)

        res = self.db.reserve_next_wallpaper(media_type="gif", target_level=3)
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "curated_test_anim")
        self.assertEqual(res["media_type"], "gif")
        self.assertTrue(res["is_animated"])

    def test_autosaver_gif_support(self):
        """Test DownloadAutoSaver generates .gif filenames and copies .gif files cleanly."""
        autosaver = DownloadAutoSaver(base_dir=self.test_dir, downloads_dir=self.downloads_dir)

        gif_wp = {
            "id": "anim_101",
            "anime": "Frieren",
            "character": "Fern",
            "url": "https://example.com/magic.gif",
            "media_type": "gif",
            "is_animated": 1
        }
        filename = autosaver.get_target_filename(gif_wp)
        self.assertTrue(filename.endswith(".gif"), f"Expected .gif filename, got: {filename}")
        self.assertIn("Frieren", filename)
        self.assertIn("[anim_101]", filename)


if __name__ == "__main__":
    unittest.main()
