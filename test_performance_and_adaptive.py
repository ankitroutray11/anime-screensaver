#!/usr/bin/env python3
"""
Unit and integration test suite for Performance Monitoring and Adaptive Rendering.
Verifies:
1. SQLite query latency metrics tracking & percentiles in DatabaseManager.
2. Cache hit rate tracking (lookups, hits, misses, hit rate %) in CacheManager.
3. PerformanceTracker latency stats, failure rates, and consolidated snapshot.
4. HTTP API endpoints: GET /api/metrics, GET /api/v1/metrics, POST /api/metrics/reset,
   and POST /api/settings/quality-profile.
5. Non-degradation guarantee of original saved wallpaper images.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
import threading
import urllib.request
import urllib.error
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database import DatabaseManager, CURRENT_SCHEMA_VERSION
from cache_manager import CacheManager
from performance_tracker import PerformanceTracker
from security import SecurityManager

class TestSQLiteLatencyTracking(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_perf_db.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_latency_recording_on_queries(self):
        # Database setup executes multiple operations
        metrics = self.db.get_sqlite_latency_metrics()
        self.assertGreater(metrics["total_ops"], 0)
        self.assertGreaterEqual(metrics["avg_latency_ms"], 0.0)
        self.assertGreaterEqual(metrics["last_latency_ms"], 0.0)
        self.assertGreaterEqual(metrics["p95_latency_ms"], 0.0)
        self.assertIn("slow_queries_count", metrics)

        initial_ops = metrics["total_ops"]
        # Run additional queries
        with self.db.get_connection() as conn:
            conn.execute("SELECT 1")
            conn.execute("SELECT 2")

        new_metrics = self.db.get_sqlite_latency_metrics()
        self.assertEqual(new_metrics["total_ops"], initial_ops + 1)

    def test_reset_latency_metrics(self):
        with self.db.get_connection() as conn:
            conn.execute("SELECT 42")
        self.assertGreater(self.db.get_sqlite_latency_metrics()["total_ops"], 0)

        self.db.reset_sqlite_latency_metrics()
        reset_metrics = self.db.get_sqlite_latency_metrics()
        self.assertEqual(reset_metrics["total_ops"], 0)
        self.assertEqual(reset_metrics["avg_latency_ms"], 0.0)
        self.assertEqual(reset_metrics["last_latency_ms"], 0.0)
        self.assertEqual(reset_metrics["slow_queries_count"], 0)

class TestCacheHitRateTracking(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir) / "wallpapers"
        self.cache = CacheManager(self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hit_rate_calculation(self):
        # Initial empty state
        initial = self.cache.get_hit_rate_metrics()
        self.assertEqual(initial["lookups"], 0)
        self.assertEqual(initial["hits"], 0)
        self.assertEqual(initial["misses"], 0)
        self.assertEqual(initial["hit_rate_percent"], 100.0)

        # 3 hits, 1 miss -> 75.0%
        self.cache.record_lookup(hit=True)
        self.cache.record_lookup(hit=True)
        self.cache.record_lookup(hit=True)
        self.cache.record_lookup(hit=False)

        metrics = self.cache.get_hit_rate_metrics()
        self.assertEqual(metrics["lookups"], 4)
        self.assertEqual(metrics["hits"], 3)
        self.assertEqual(metrics["misses"], 1)
        self.assertEqual(metrics["hit_rate_percent"], 75.0)

        # Included in get_cache_stats()
        stats = self.cache.get_cache_stats()
        self.assertEqual(stats["lookups"], 4)
        self.assertEqual(stats["hit_rate_percent"], 75.0)

    def test_reset_hit_rate_metrics(self):
        self.cache.record_lookup(hit=True)
        self.cache.record_lookup(hit=False)
        self.cache.reset_hit_rate_metrics()

        reset_stats = self.cache.get_hit_rate_metrics()
        self.assertEqual(reset_stats["lookups"], 0)
        self.assertEqual(reset_stats["hits"], 0)
        self.assertEqual(reset_stats["misses"], 0)

class TestPerformanceTrackerModule(unittest.TestCase):
    def setUp(self):
        self.tracker = PerformanceTracker(max_samples=50)

    def test_record_and_latency_percentiles(self):
        durations = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        for dur in durations:
            self.tracker.record_request("/api/test", dur, 200)

        lat = self.tracker.get_latency_metrics()
        self.assertEqual(lat["total_requests"], 10)
        self.assertEqual(lat["min_latency_ms"], 10.0)
        self.assertEqual(lat["max_latency_ms"], 100.0)
        self.assertEqual(lat["avg_latency_ms"], 55.0)
        self.assertEqual(lat["last_latency_ms"], 100.0)
        self.assertGreaterEqual(lat["p95_latency_ms"], 90.0)

    def test_failure_rate_tracking(self):
        self.tracker.record_request("/api/ok1", 5.0, 200)
        self.tracker.record_request("/api/ok2", 5.0, 204)
        self.tracker.record_request("/api/notfound", 5.0, 404)
        self.tracker.record_request("/api/err", 5.0, 500)

        fail = self.tracker.get_failure_metrics()
        self.assertEqual(fail["total_requests"], 4)
        self.assertEqual(fail["failed_requests"], 2)
        self.assertEqual(fail["failure_rate_percent"], 50.0)
        self.assertEqual(fail["status_distribution"]["2xx"], 2)
        self.assertEqual(fail["status_distribution"]["4xx"], 1)
        self.assertEqual(fail["status_distribution"]["5xx"], 1)

    def test_reset_metrics(self):
        self.tracker.record_request("/api/test", 10.0, 200)
        self.tracker.record_request("/api/err", 5.0, 500)
        self.tracker.reset_metrics()

        lat = self.tracker.get_latency_metrics()
        fail = self.tracker.get_failure_metrics()
        self.assertEqual(lat["total_requests"], 0)
        self.assertEqual(fail["total_requests"], 0)
        self.assertEqual(fail["failed_requests"], 0)
        self.assertEqual(fail["failure_rate_percent"], 0.0)

    def test_snapshot_aggregation(self):
        temp_dir = tempfile.mkdtemp()
        try:
            db_path = Path(temp_dir) / "snap_db.db"
            db = DatabaseManager(db_path)
            cache = CacheManager(Path(temp_dir) / "cache")
            self.tracker.record_request("/api/metrics", 8.0, 200)

            snapshot = self.tracker.get_performance_snapshot(
                engine=None,
                db_manager=db,
                cache_manager=cache
            )
            self.assertIn("server_uptime_seconds", snapshot)
            self.assertIn("backend_latency", snapshot)
            self.assertIn("api_failures", snapshot)
            self.assertIn("sqlite_latency", snapshot)
            self.assertIn("cache", snapshot)
            self.assertIn("prefetch_queue", snapshot)
            self.assertIn("workers", snapshot)
            self.assertIn("quality_profile", snapshot)
            self.assertEqual(snapshot["quality_profile"], "auto")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

class TestServerMetricsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server_module = server
        # Start server on an ephemeral port
        cls.port = 54399
        server.PORT = cls.port
        cls.httpd = server.ThreadedHTTPServer(("127.0.0.1", cls.port), server.KuroHandler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)
        cls.token = server.security_manager.session_token

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_get_metrics_endpoint(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/metrics",
            headers={"Origin": f"http://127.0.0.1:{self.port}"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertIn("backend_latency", data)
        self.assertIn("sqlite_latency", data)
        self.assertIn("cache", data)
        self.assertIn("prefetch_queue", data)
        self.assertIn("workers", data)
        self.assertIn("quality_profile", data)

    def test_get_versioned_metrics_endpoint(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/v1/metrics",
            headers={"Origin": f"http://127.0.0.1:{self.port}"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertIn(data["prefetch_queue"]["queue_health"], ("healthy", "refilling"))

    def test_quality_profile_update(self):
        # Update quality profile to balanced
        payload = json.dumps({"profile": "balanced"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/settings/quality-profile",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": f"http://127.0.0.1:{self.port}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res["profile"], "balanced")

        # Verify reflected in /api/metrics
        m_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/metrics",
            headers={"Origin": f"http://127.0.0.1:{self.port}"}
        )
        with urllib.request.urlopen(m_req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["quality_profile"], "balanced")

        # Revert back to auto
        payload_auto = json.dumps({"profile": "auto"}).encode("utf-8")
        req_auto = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/settings/quality-profile",
            data=payload_auto,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": f"http://127.0.0.1:{self.port}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req_auto) as resp:
            self.assertEqual(resp.status, 200)

    def test_invalid_quality_profile_rejected(self):
        payload = json.dumps({"profile": "ultra_extreme"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/settings/quality-profile",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": f"http://127.0.0.1:{self.port}"
            },
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_metrics_reset_endpoint(self):
        payload = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/metrics/reset",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": self.token,
                "Origin": f"http://127.0.0.1:{self.port}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res["status"], "success")

    def test_quality_profile_preserves_image_files(self):
        # Rule 1: Never reduce original saved image quality or alter image files
        curated_dir = BASE_DIR / "curated_wallpapers"
        if curated_dir.is_dir():
            files = list(curated_dir.glob("*.jpg")) + list(curated_dir.glob("*.png"))
            if files:
                original_sizes = {f.name: f.stat().st_size for f in files[:3]}
                # Toggle profiles across low, balanced, high
                for prof in ["low", "balanced", "high"]:
                    self.server_module.db_manager.save_control_center_settings("performance", {"perf_quality_profile": prof})
                # Verify sizes unchanged
                for f_name, orig_size in original_sizes.items():
                    current_size = (curated_dir / f_name).stat().st_size
                    self.assertEqual(current_size, orig_size, f"Image file {f_name} was modified by quality profile")

if __name__ == "__main__":
    unittest.main()
