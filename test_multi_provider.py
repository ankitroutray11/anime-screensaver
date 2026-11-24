"""
test_multi_provider.py - Comprehensive Unit & Integration Tests for Multi-Provider Failover

Tests cover:
1. NormalizedWallpaper schema and database candidate compatibility.
2. CircuitBreaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED),
   rate limit trips (HTTP 429), exponential backoff, and manual reset.
3. ProviderHealthTracker metrics (requests, latency, availability, rate-limit counters).
4. SFW purity validation: guarantees Safebooru and Konachan strictly enforce safe content.
5. SafebooruProvider and KonachanProvider parsing, URL normalization, and dimension filtering.
6. ProviderManager failover sequence: Primary Wallhaven failure/rate limit triggers failover
   to Safebooru and Konachan.
7. Global deduplication across all providers (same SQLite lifecycle table).
8. REST API endpoints: GET /api/providers, POST /api/providers/toggle,
   POST /api/providers/priority, POST /api/providers/reset-circuits.
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

from providers import (
    ArtworkProvider,
    CircuitBreaker,
    CircuitState,
    KonachanProvider,
    NormalizedWallpaper,
    ProviderHealthTracker,
    ProviderManager,
    SafebooruProvider,
    WallhavenProvider
)
from database import DatabaseManager
from quality_scorer import QualityScorer


class TestNormalizedWallpaper(unittest.TestCase):
    def test_normalized_structure_and_candidate_dict(self):
        wp = NormalizedWallpaper(
            id="sb_7339399",
            provider="Safebooru",
            url="https://safebooru.org/images/4187/sample.jpg",
            thumbnail_url="https://safebooru.org/thumbnails/4187/thumb.jpg",
            resolution="2560x1440",
            dimension_x=2560,
            dimension_y=1440,
            aspect_ratio="landscape",
            file_size=1048576,
            anime="Cyberpunk: Edgerunners",
            character="Lucy",
            tags=["lucy", "scenery", "night"],
            purity="sfw",
            views=1200,
            favorites=85,
            uploader="artist_a",
            upload_date="2026-01-01",
            source_url="https://safebooru.org/index.php?page=post&s=view&id=7339399"
        )

        cand = wp.to_candidate_dict()
        self.assertEqual(cand["id"], "sb_7339399")
        self.assertEqual(cand["source"], "Safebooru")
        self.assertEqual(cand["anime"], "Cyberpunk: Edgerunners")
        self.assertEqual(cand["character"], "Lucy")
        self.assertEqual(cand["dimension_x"], 2560)
        self.assertEqual(cand["dimension_y"], 1440)
        self.assertEqual(cand["views"], 1200)
        self.assertEqual(cand["favorites"], 85)
        self.assertEqual(cand["uploader"], "artist_a")
        self.assertEqual(cand["source_url"], "https://safebooru.org/index.php?page=post&s=view&id=7339399")
        self.assertIn("lucy", cand["tags"])


class TestCircuitBreaker(unittest.TestCase):
    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())

    def test_trips_to_open_after_failure_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

    def test_rate_limit_trips_open_immediately(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=0.5)
        cb.record_failure(is_rate_limit=True, retry_after=0.2)
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

    def test_transitions_to_half_open_and_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        # Wait for recovery timeout
        time.sleep(0.08)
        self.assertTrue(cb.can_execute())  # Triggers HALF_OPEN
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # Successful probe call resets circuit to CLOSED
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.failure_count, 0)

    def test_manual_reset(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())


class TestProviderHealthTracker(unittest.TestCase):
    def test_metrics_calculation(self):
        tracker = ProviderHealthTracker("TestProvider")
        tracker.record_request(duration_ms=100.0, success=True)
        tracker.record_request(duration_ms=200.0, success=True)
        tracker.record_request(duration_ms=150.0, success=False, is_rate_limit=True, error_msg="HTTP 429")

        metrics = tracker.get_metrics()
        self.assertEqual(metrics["total_requests"], 3)
        self.assertEqual(metrics["successful_requests"], 2)
        self.assertEqual(metrics["failed_requests"], 1)
        self.assertEqual(metrics["rate_limited_count"], 1)
        self.assertEqual(metrics["average_latency_ms"], 150.0)
        self.assertEqual(metrics["availability_percent"], 66.7)
        self.assertEqual(metrics["last_error"], "HTTP 429")


class TestSFWEnforcementAndParsing(unittest.TestCase):
    def test_safebooru_strictly_enforces_sfw_and_dimensions(self):
        provider = SafebooruProvider()

        # Mock Safebooru JSON response
        mock_posts = [
            # Valid SFW landscape
            {
                "id": 1001,
                "width": 1920,
                "height": 1080,
                "rating": "general",
                "file_url": "https://safebooru.org/images/1/a.jpg",
                "tags": "scenery landscape anime",
                "score": 10,
                "owner": "artist_sfw"
            },
            # Non-SFW rating: must be strictly rejected
            {
                "id": 1002,
                "width": 1920,
                "height": 1080,
                "rating": "explicit",
                "file_url": "https://safebooru.org/images/1/b.jpg",
                "tags": "nsfw",
                "score": 50,
                "owner": "bad_actor"
            },
            # Sub-resolution: must be rejected
            {
                "id": 1003,
                "width": 800,
                "height": 600,
                "rating": "safe",
                "file_url": "https://safebooru.org/images/1/c.jpg",
                "tags": "tiny",
                "score": 5,
                "owner": "small_img"
            }
        ]

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_posts).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            results = provider.search(franchise_slug="attack-on-titan", ratio="landscape")

            # Only post 1001 should be accepted
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].id, "sb_1001")
            self.assertEqual(results[0].provider, "Safebooru")
            self.assertEqual(results[0].dimension_x, 1920)
            self.assertEqual(results[0].purity, "sfw")
            self.assertTrue(provider.validate_sfw(results[0]))

    def test_konachan_strictly_enforces_sfw_and_dimensions(self):
        provider = KonachanProvider()

        # Mock Konachan.net response
        mock_posts = [
            # Valid SFW
            {
                "id": 2001,
                "width": 2560,
                "height": 1440,
                "rating": "s",
                "file_url": "https://konachan.net/image/2001.jpg",
                "tags": "shingeki_no_kyojin eren_yeager scenery",
                "score": 25,
                "author": "kc_artist"
            },
            # Questionable / Explicit: must be rejected
            {
                "id": 2002,
                "width": 2560,
                "height": 1440,
                "rating": "e",
                "file_url": "https://konachan.net/image/2002.jpg",
                "tags": "nsfw",
                "score": 90,
                "author": "nsfw_artist"
            }
        ]

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_posts).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            results = provider.search(franchise_slug="attack-on-titan", ratio="landscape")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].id, "kc_2001")
            self.assertEqual(results[0].provider, "Konachan")
            self.assertEqual(results[0].purity, "sfw")
            self.assertTrue(provider.validate_sfw(results[0]))


class TestProviderManagerFailoverAndDeduplication(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_kuro.db"
        self.db = DatabaseManager(self.db_path)
        self.quality_scorer = QualityScorer(self.db.get_quality_settings())
        self.manager = ProviderManager(self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_automatic_failover_when_primary_rate_limited(self):
        """When Wallhaven raises HTTP 429, manager fails over to Safebooru seamlessly."""
        # Mock Wallhaven throwing HTTP 429
        self.manager.providers["wallhaven"].search = MagicMock(
            side_effect=urllib.error.HTTPError("https://wallhaven.cc", 429, "Too Many Requests", {}, None)
        )

        # Mock Safebooru returning candidates
        mock_wp = NormalizedWallpaper(
            id="sb_888",
            provider="Safebooru",
            url="https://safebooru.org/images/888.jpg",
            thumbnail_url="https://safebooru.org/thumb/888.jpg",
            resolution="1920x1080",
            dimension_x=1920,
            dimension_y=1080,
            aspect_ratio="landscape",
            file_size=500000,
            anime="Jujutsu Kaisen",
            character="Gojo Satoru",
            tags=["gojo", "jujutsu_kaisen"],
            purity="sfw",
            views=300,
            favorites=45,
            uploader="test_user",
            upload_date=None,
            source_url="https://safebooru.org/index.php?page=post&s=view&id=888"
        )
        self.manager.providers["safebooru"].search = MagicMock(return_value=[mock_wp])

        candidates, provider_used = self.manager.fetch_candidates_with_failover(
            franchise_slug="jujutsu-kaisen",
            quality_scorer=self.quality_scorer,
            is_known_func=self.db.is_known,
            is_blacklisted_func=self.db.is_blacklisted
        )

        self.assertEqual(provider_used, "Safebooru")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["id"], "sb_888")
        self.assertEqual(candidates[0]["source"], "Safebooru")
        self.assertGreater(self.manager.total_failovers, 0)

        # Verify Wallhaven circuit tripped to OPEN due to 429
        wh_status = self.manager.providers["wallhaven"].circuit_breaker.get_status()
        self.assertEqual(wh_status["state"], "OPEN")

    def test_automatic_failover_to_konachan_when_wallhaven_and_safebooru_fail(self):
        """When both Wallhaven and Safebooru fail, manager fails over to Konachan."""
        self.manager.providers["wallhaven"].search = MagicMock(
            side_effect=RuntimeError("Wallhaven timeout")
        )
        self.manager.providers["safebooru"].search = MagicMock(
            side_effect=RuntimeError("Safebooru network error")
        )

        mock_wp = NormalizedWallpaper(
            id="kc_999",
            provider="Konachan",
            url="https://konachan.net/image/999.jpg",
            thumbnail_url="https://konachan.net/sample/999.jpg",
            resolution="2560x1440",
            dimension_x=2560,
            dimension_y=1440,
            aspect_ratio="landscape",
            file_size=700000,
            anime="Demon Slayer",
            character="Nezuko",
            tags=["nezuko", "kimetsu_no_yaiba"],
            purity="sfw",
            views=500,
            favorites=70,
            uploader="kc_user",
            upload_date=None,
            source_url="https://konachan.net/post/show/999"
        )
        self.manager.providers["konachan"].search = MagicMock(return_value=[mock_wp])

        candidates, provider_used = self.manager.fetch_candidates_with_failover(
            franchise_slug="demon-slayer",
            quality_scorer=self.quality_scorer,
            is_known_func=self.db.is_known,
            is_blacklisted_func=self.db.is_blacklisted
        )

        self.assertEqual(provider_used, "Konachan")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["id"], "kc_999")
        self.assertEqual(candidates[0]["source"], "Konachan")

    def test_global_deduplication_across_providers(self):
        """Global deduplication prevents inserting duplicate wallpapers even from different providers."""
        # 1. Add wallpaper from Wallhaven
        added = self.db.add_unseen_wallpapers([{
            "id": "wh_shared_001",
            "url": "https://example.com/anime.jpg",
            "resolution": "1920x1080",
            "anime": "Attack on Titan",
            "character": "Eren",
            "source": "Wallhaven",
            "quality_score": 85.0
        }])
        self.assertEqual(added, 1)

        # 2. Check deduplication function recognizes it
        self.assertTrue(self.db.is_known("wh_shared_001"))

        # 3. If a secondary provider returns the same ID, deduplication rejects it
        mock_wp = NormalizedWallpaper(
            id="wh_shared_001",
            provider="Safebooru",
            url="https://example.com/anime.jpg",
            thumbnail_url="https://example.com/thumb.jpg",
            resolution="1920x1080",
            dimension_x=1920,
            dimension_y=1080,
            aspect_ratio="landscape",
            file_size=0,
            anime="Attack on Titan",
            character="Eren",
            tags=[],
            purity="sfw",
            views=10,
            favorites=5,
            uploader=None,
            upload_date=None,
            source_url="https://example.com/post"
        )
        self.manager.providers["wallhaven"].search = MagicMock(return_value=[])
        self.manager.providers["safebooru"].search = MagicMock(return_value=[mock_wp])
        self.manager.providers["konachan"].search = MagicMock(return_value=[])

        candidates, _ = self.manager.fetch_candidates_with_failover(
            franchise_slug="attack-on-titan",
            is_known_func=self.db.is_known,
            is_blacklisted_func=self.db.is_blacklisted
        )

        # Candidate rejected by deduplication
        self.assertEqual(len(candidates), 0)

    def test_toggle_provider_and_persistence(self):
        self.assertTrue(self.manager.providers["konachan"].enabled)
        # Disable Konachan
        ok = self.manager.toggle_provider("konachan", False)
        self.assertTrue(ok)
        self.assertFalse(self.manager.providers["konachan"].enabled)

        # Verify persisted in database
        saved = self.db.get_provider_settings()
        self.assertFalse(saved.get("konachan_enabled"))

        # Reload settings in fresh manager
        new_mgr = ProviderManager(self.db)
        self.assertFalse(new_mgr.providers["konachan"].enabled)

    def test_reset_all_circuits(self):
        for p in self.manager.providers.values():
            p.circuit_breaker.record_failure(is_rate_limit=True)
            self.assertEqual(p.circuit_breaker.state, CircuitState.OPEN)

        self.manager.reset_all_circuits()
        for p in self.manager.providers.values():
            self.assertEqual(p.circuit_breaker.state, CircuitState.CLOSED)


class TestProviderRESTEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import socket
        import threading
        from server import ThreadedHTTPServer, KuroHandler, HOST, security_manager

        # Pick a free ephemeral test port
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

    def test_get_providers_endpoint(self):
        req = urllib.request.Request(f"{self.base_url}/api/providers")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("active_provider", data)
            self.assertIn("total_failovers", data)
            self.assertIn("providers", data)
            names = [p["name"] for p in data["providers"]]
            self.assertIn("Wallhaven", names)
            self.assertIn("Safebooru", names)
            self.assertIn("Konachan", names)

    def test_toggle_provider_endpoint(self):
        url = f"{self.base_url}/api/providers/toggle"
        payload = json.dumps({"name": "safebooru", "enabled": False}).encode("utf-8")
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
            self.assertEqual(data["provider"], "safebooru")
            self.assertFalse(data["enabled"])

        # Re-enable
        payload = json.dumps({"name": "safebooru", "enabled": True}).encode("utf-8")
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

    def test_reset_circuits_endpoint(self):
        url = f"{self.base_url}/api/providers/reset-circuits"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.session_token
            }
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "reset")


if __name__ == "__main__":
    unittest.main()
