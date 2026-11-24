#!/usr/bin/env python3
"""
Automated Test Suite for Production Security, Reliability & API Hardening.
Covers:
1. Application Health Endpoint (/api/health and /api/v1/health).
2. Local Session Handshake (/api/session and /api/v1/session).
3. Origin Validation & Anti-CSRF protection (foreign origins blocked).
4. State-changing endpoint authentication (X-Kuro-Token requirement).
5. SSRF Defense in /api/favorite (arbitrary IP/domain injection blocked).
6. Path traversal defense on images and static files.
7. Input validation, payload size limits, and structured JSON errors.
8. API versioning parity (/api/v1/... and legacy /api/... aliases).
9. Cache manager bounded size & LRU eviction.
10. SQLite WAL mode integrity and checkpointing.
11. Configurable background worker lifecycle (start/stop/join).
"""

import os
import sys
import time
import json
import uuid
import shutil
import urllib.request
import urllib.error
import tempfile
import threading
import unittest
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database import DatabaseManager
from engine import WallpaperEngine
from cache_manager import CacheManager
from security import SecurityManager, MAX_CONTENT_LENGTH
from server import ThreadedHTTPServer, KuroHandler, HOST

class TestSecurityAndAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Choose a dynamic high test port
        cls.test_port = 54388
        cls.server = ThreadedHTTPServer((HOST, cls.test_port), KuroHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)
        cls.base_url = f"http://{HOST}:{cls.test_port}"

        # Fetch local session token
        req = urllib.request.Request(f"{cls.base_url}/api/v1/session")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            cls.session_token = data["session_token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_01_health_endpoint(self):
        """Verify /api/health and /api/v1/health return 200 with structured status."""
        for ep in ["/api/health", "/api/v1/health"]:
            req = urllib.request.Request(f"{self.base_url}{ep}")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertEqual(data["status"], "healthy")
                self.assertTrue(data["database"]["connected"])
                self.assertEqual(data["database"]["integrity_check"], "ok")
                self.assertTrue(data["database"]["wal_mode"])
                self.assertIn("uptime_seconds", data)
                self.assertIn("worker", data)
                self.assertIn("cache", data)
                self.assertIn("network", data)

    def test_02_session_handshake(self):
        """Verify local session token handshake is 64 hex characters (256-bit)."""
        req = urllib.request.Request(f"{self.base_url}/api/v1/session")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            token = data.get("session_token")
            self.assertIsNotNone(token)
            self.assertEqual(len(token), 64)

    def test_03_origin_validation_blocks_foreign_origins(self):
        """Verify cross-origin requests from untrusted external sites are rejected with HTTP 403."""
        # Untrusted Origin on GET
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/stats",
            headers={"Origin": "http://malicious-attacker.com"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Expected HTTP 403 on untrusted origin")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)
            err_data = json.loads(e.read().decode())
            self.assertEqual(err_data["error"]["code"], "FORBIDDEN_ORIGIN")

        # Untrusted Origin on POST
        post_req = urllib.request.Request(
            f"{self.base_url}/api/v1/reset-history",
            data=b"{}",
            headers={
                "Origin": "http://evil-site.org",
                "Content-Type": "application/json",
                "X-Kuro-Token": self.session_token
            }
        )
        try:
            with urllib.request.urlopen(post_req) as resp:
                self.fail("Expected HTTP 403 on untrusted POST origin")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)
            err_data = json.loads(e.read().decode())
            self.assertEqual(err_data["error"]["code"], "FORBIDDEN_ORIGIN")

    def test_04_state_changing_requires_valid_session_token(self):
        """Verify POST requests without valid session token are rejected with HTTP 401."""
        # Missing token
        req = urllib.request.Request(
            f"{self.base_url}/api/v1/reset-history",
            data=b"{}",
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Expected HTTP 401 on missing session token")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)
            err = json.loads(e.read().decode())
            self.assertEqual(err["error"]["code"], "UNAUTHORIZED")

        # Invalid token
        req_bad = urllib.request.Request(
            f"{self.base_url}/api/v1/reset-history",
            data=b"{}",
            headers={"Content-Type": "application/json", "X-Kuro-Token": "invalid_token_12345"}
        )
        try:
            with urllib.request.urlopen(req_bad) as resp:
                self.fail("Expected HTTP 401 on invalid session token")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)
            err = json.loads(e.read().decode())
            self.assertEqual(err["error"]["code"], "UNAUTHORIZED")

        # Valid token succeeds
        req_ok = urllib.request.Request(
            f"{self.base_url}/api/v1/reset-history",
            data=b"{}",
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.session_token}
        )
        with urllib.request.urlopen(req_ok) as resp:
            self.assertEqual(resp.status, 200)

    def test_05_ssrf_protection_on_favorite(self):
        """Verify SSRF guard blocks internal IPs, metadata endpoints, and untrusted domains."""
        blocked_targets = [
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.1/admin",
            "http://10.0.0.1:8080/secret",
            "https://arbitrary-attacker-site.com/exploit.png"
        ]

        for target in blocked_targets:
            payload = json.dumps({"id": "wp_ssrf_test", "url": target}).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/v1/favorite",
                data=payload,
                headers={"Content-Type": "application/json", "X-Kuro-Token": self.session_token}
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    self.fail(f"Expected HTTP 400 for SSRF target {target}")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 400)
                err = json.loads(e.read().decode())
                self.assertEqual(err["error"]["code"], "SSRF_REJECTED")

        # Valid Wallhaven URL is accepted
        valid_payload = json.dumps({
            "id": "wp_valid_01",
            "url": "https://w.wallhaven.cc/full/test/wallhaven-test01.jpg"
        }).encode()
        req_valid = urllib.request.Request(
            f"{self.base_url}/api/v1/favorite",
            data=valid_payload,
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.session_token}
        )
        with urllib.request.urlopen(req_valid) as resp:
            self.assertEqual(resp.status, 200)

    def test_06_path_traversal_prevention(self):
        """Verify directory traversal is strictly blocked on image endpoints and static file serving."""
        # Traversal in image ID
        traversal_ids = ["..", "../etc/passwd", "..\\boot.ini", "subdir/file", "%2e%2e%2f"]
        for bad_id in traversal_ids:
            req = urllib.request.Request(f"{self.base_url}/api/v1/image/{bad_id}")
            try:
                with urllib.request.urlopen(req) as resp:
                    self.fail(f"Expected 400 or 404 for traversal ID {bad_id}")
            except urllib.error.HTTPError as e:
                self.assertIn(e.code, [400, 404])

        # Sensitive file access blocked (database and source code)
        for sensitive in ["/kuro_database.db", "/database.py", "/server.py"]:
            req = urllib.request.Request(f"{self.base_url}{sensitive}")
            try:
                with urllib.request.urlopen(req) as resp:
                    self.fail(f"Expected 403 Forbidden for sensitive file {sensitive}")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 403)

    def test_07_input_validation_and_structured_errors(self):
        """Verify malformed JSON, invalid IDs, and oversized bodies yield structured errors."""
        # Malformed JSON
        req_malformed = urllib.request.Request(
            f"{self.base_url}/api/v1/confirm-display",
            data=b"{bad json",
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.session_token}
        )
        try:
            with urllib.request.urlopen(req_malformed) as resp:
                self.fail("Expected HTTP 400 on malformed JSON")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            err = json.loads(e.read().decode())
            self.assertEqual(err["error"]["code"], "MALFORMED_JSON")

        # Missing wallpaper ID
        req_missing = urllib.request.Request(
            f"{self.base_url}/api/v1/confirm-display",
            data=json.dumps({"reservation_token": "tok-123"}).encode(),
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.session_token}
        )
        try:
            with urllib.request.urlopen(req_missing) as resp:
                self.fail("Expected HTTP 400 on missing ID")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
            err = json.loads(e.read().decode())
            self.assertEqual(err["error"]["code"], "INVALID_INPUT")

        # 404 on nonexistent API route
        req_404 = urllib.request.Request(f"{self.base_url}/api/v1/nonexistent_route")
        try:
            with urllib.request.urlopen(req_404) as resp:
                self.fail("Expected HTTP 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_08_api_versioning_parity(self):
        """Verify v1 endpoints (/api/v1/...) and legacy endpoints (/api/...) return identical structures."""
        endpoints = ["stats", "status", "franchises", "monitors"]
        for ep in endpoints:
            req_v1 = urllib.request.Request(f"{self.base_url}/api/v1/{ep}")
            req_legacy = urllib.request.Request(f"{self.base_url}/api/{ep}")

            with urllib.request.urlopen(req_v1) as resp1, urllib.request.urlopen(req_legacy) as resp2:
                self.assertEqual(resp1.status, 200)
                self.assertEqual(resp2.status, 200)
                data1 = json.loads(resp1.read().decode())
                data2 = json.loads(resp2.read().decode())
                # Compare schema keys
                if isinstance(data1, dict):
                    self.assertEqual(set(data1.keys()), set(data2.keys()))
                elif isinstance(data1, list) and len(data1) > 0:
                    self.assertEqual(len(data1), len(data2))
                    self.assertEqual(set(data1[0].keys()), set(data2[0].keys()))

    def test_09_cache_manager_bounded_size_and_lru_eviction(self):
        """Verify CacheManager bounds disk usage and evicts oldest items first."""
        temp_dir = Path(tempfile.mkdtemp(prefix="kuro_cache_test_"))
        try:
            # Set a small limit: max 200KB or max 3 files
            cm = CacheManager(temp_dir, max_bytes=200 * 1024, max_files=3)

            # Create 5 test files with distinct access times
            files = []
            evicted_ids = []
            for i in range(5):
                f = temp_dir / f"wp_cache_{i:02d}.jpg"
                f.write_bytes(b"X" * 60 * 1024)  # 60KB each (total 300KB > 200KB limit)
                # Set distinct mtime
                os.utime(str(f), (1000 + i * 100, 1000 + i * 100))
                files.append(f)

            stats_before = cm.get_cache_stats()
            self.assertEqual(stats_before["file_count"], 5)
            self.assertGreater(stats_before["size_bytes"], 200 * 1024)

            # Run eviction
            evicted_count = cm.enforce_cache_limits(on_evict_callback=lambda id_: evicted_ids.append(id_))
            self.assertGreater(evicted_count, 0)

            stats_after = cm.get_cache_stats()
            self.assertLessEqual(stats_after["file_count"], 3)
            self.assertLessEqual(stats_after["size_bytes"], 200 * 1024)

            # Oldest files (wp_cache_00) should have been evicted first
            self.assertIn("wp_cache_00", evicted_ids)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_10_database_wal_checkpoint_and_recovery(self):
        """Verify PRAGMA quick_check integrity and WAL truncation checkpoint."""
        temp_dir = Path(tempfile.mkdtemp(prefix="kuro_db_test_"))
        try:
            db_path = temp_dir / "wal_test.db"
            db = DatabaseManager(db_path)

            # Verify integrity
            self.assertTrue(db.run_integrity_check())

            # Seed data and checkpoint
            db.add_unseen_wallpapers([
                {"id": "wp_chk_01", "url": "https://img.test/1.jpg", "anime": "Naruto"}
            ])
            self.assertTrue(db.checkpoint_wal("TRUNCATE"))
            self.assertTrue(db.run_integrity_check())
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_11_configurable_worker_lifecycle(self):
        """Verify background maintenance worker cleanly starts, runs, and stops."""
        temp_dir = Path(tempfile.mkdtemp(prefix="kuro_worker_test_"))
        try:
            db_path = temp_dir / "worker_test.db"
            db = DatabaseManager(db_path)
            eng = WallpaperEngine(db, maintenance_interval=0.2, auto_prefetch=False)

            self.assertEqual(eng.worker_state, "stopped")
            self.assertFalse(eng._running)

            # Start worker
            eng.start()
            self.assertEqual(eng.worker_state, "running")
            self.assertTrue(eng._running)
            self.assertTrue(eng.worker_thread.is_alive())

            # Stop worker gracefully
            eng.stop(timeout=2.0)
            self.assertEqual(eng.worker_state, "stopped")
            self.assertFalse(eng._running)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
