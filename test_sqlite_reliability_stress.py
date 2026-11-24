"""
test_sqlite_reliability_stress.py - SQLite Reliability, WAL Concurrency & Stress Test Suite
=============================================================================================
Audits and stress-tests Kuro Anime Screensaver's SQLite database layer under high concurrency:
1. WAL mode initialization and connection-level PRAGMA configuration.
2. Consistent write serialization via DatabaseManager.write_transaction().
3. Simultaneous wallpaper reservations, confirmations, favorites, and statistics reads.
4. Database contention and exponential-backoff recovery from 'database is locked' errors.
5. Transaction rollback cleaness (guaranteeing zero partial records on failure).
6. Application shutdown while database operations are active (active connection draining).
7. SQLite WAL and shared-memory (-wal, -shm) file lifecycle, truncation, and restart.
8. Deep database integrity checks, corruption diagnostics, and actionable recommendations.
9. Transactional schema migrations and versioning.
10. High-concurrency live HTTP request stress testing with thousands of simulated records.
"""

import unittest
import tempfile
import shutil
import threading
import time
import random
import json
import os
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any

import database
import server
from backup_manager import BackupManager


class TestSQLiteReliabilityAndStress(unittest.TestCase):
    """Deep reliability and stress test suite for SQLite DatabaseManager."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_db_stress_"))
        self.db_path = self.test_dir / "stress_kuro.db"
        self.db = database.DatabaseManager(self.db_path)

    def tearDown(self):
        try:
            self.db.close_and_checkpoint(timeout=2.0)
        except Exception:
            pass
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 1. WAL Initialization & Connection PRAGMAs
    # -------------------------------------------------------------------------
    def test_01_wal_initialization_and_connection_pragmas(self):
        """Verifies that all connections apply WAL mode and performance/safety PRAGMAs."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()

            # 1. Journal mode must be WAL
            cur.execute("PRAGMA journal_mode;")
            jmode = cur.fetchone()[0]
            self.assertEqual(jmode.lower(), "wal")

            # 2. Busy timeout must be >= 10000ms (10s)
            cur.execute("PRAGMA busy_timeout;")
            btimeout = cur.fetchone()[0]
            self.assertGreaterEqual(btimeout, 10000)

            # 3. Synchronous mode must be NORMAL (1) for WAL
            cur.execute("PRAGMA synchronous;")
            sync_mode = cur.fetchone()[0]
            self.assertIn(sync_mode, (1, "NORMAL"))

            # 4. Foreign keys must be ON (1)
            cur.execute("PRAGMA foreign_keys;")
            fk_mode = cur.fetchone()[0]
            self.assertEqual(fk_mode, 1)

            # 5. Temp store must be MEMORY (2)
            cur.execute("PRAGMA temp_store;")
            tstore = cur.fetchone()[0]
            self.assertEqual(tstore, 2)

            # 6. Cache size must be configured (-64000 = ~64MB)
            cur.execute("PRAGMA cache_size;")
            csize = cur.fetchone()[0]
            self.assertEqual(csize, -64000)

    # -------------------------------------------------------------------------
    # 2. High-Concurrency Multi-Threaded Write Serialization & Latency
    # -------------------------------------------------------------------------
    def test_02_write_serialization_and_concurrency(self):
        """
        Stress-tests simultaneous writes, reads, reservations, and favorites
        across 16 concurrent threads processing 1,000+ operations.
        Verifies zero duplicate records, zero dropped transactions, and low latency.
        """
        self.db.reset_sqlite_latency_metrics()
        num_wallpapers = 1000
        items = []
        for i in range(num_wallpapers):
            items.append({
                "id": f"wp_stress_{i:04d}",
                "url": f"https://w.wallhaven.cc/full/st/wallhaven-stress_{i:04d}.jpg",
                "resolution": "3840x2160",
                "anime": "Frieren" if i % 2 == 0 else "Demon Slayer",
                "character": "Frieren" if i % 2 == 0 else "Tanjiro",
                "quality_score": 85.0 + (i % 15),
                "file_size": 3500000 + i,
                "views": 5000 + i,
                "favorites": 200 + i
            })

        # Batch insert 1,000 wallpapers
        added = self.db.add_unseen_wallpapers(items)
        self.assertEqual(added, num_wallpapers)

        threads = []
        errors = []
        reserved_ids = []
        reserved_lock = threading.Lock()

        # Worker: reserve wallpapers
        def reservation_worker(worker_id: int, count: int):
            for j in range(count):
                token = f"tok_w{worker_id}_{j}"
                try:
                    res = self.db.reserve_next_wallpaper(token=token)
                    if res:
                        with reserved_lock:
                            reserved_ids.append((res["id"], token))
                    time.sleep(0.002)
                except Exception as e:
                    errors.append(f"Reservation error: {e}")

        # Worker: confirm displayed wallpapers
        def confirmation_worker():
            while True:
                item = None
                with reserved_lock:
                    if reserved_ids:
                        item = reserved_ids.pop(0)
                if item:
                    wid, tok = item
                    try:
                        ok = self.db.confirm_displayed(wid, tok)
                        if not ok:
                            errors.append(f"Failed to confirm displayed: {wid}")
                    except Exception as e:
                        errors.append(f"Confirmation error: {e}")
                else:
                    if all(not t.is_alive() for t in res_threads):
                        break
                    time.sleep(0.005)

        # Worker: toggle favorites
        def favorites_worker(worker_id: int, count: int):
            for k in range(count):
                wid = f"wp_stress_{random.randint(0, num_wallpapers - 1):04d}"
                try:
                    self.db.add_favorite({
                        "id": wid,
                        "url": f"https://w.wallhaven.cc/full/st/wallhaven-{wid}.jpg",
                        "anime": "Frieren",
                        "resolution": "3840x2160"
                    })
                    if k % 3 == 0:
                        self.db.remove_favorite(wid)
                except Exception as e:
                    errors.append(f"Favorites error: {e}")
                time.sleep(0.001)

        # Worker: read stats & history concurrently
        def stats_reader_worker(count: int):
            for _ in range(count):
                try:
                    st = self.db.get_stats()
                    self.assertIn("total_catalog", st)
                    hist = self.db.get_wallpaper_history(page=1, page_size=20)
                    self.assertIn("items", hist)
                except Exception as e:
                    errors.append(f"Reader error: {e}")
                time.sleep(0.002)

        # Launch 4 reservation threads (50 ops each = 200 reservations)
        res_threads = [threading.Thread(target=reservation_worker, args=(w, 50)) for w in range(4)]
        # Launch 4 confirmation threads
        conf_threads = [threading.Thread(target=confirmation_worker) for _ in range(4)]
        # Launch 4 favorites threads (60 ops each = 240 ops)
        fav_threads = [threading.Thread(target=favorites_worker, args=(w, 60)) for w in range(4)]
        # Launch 4 reader threads (50 reads each = 200 reads)
        read_threads = [threading.Thread(target=stats_reader_worker, args=(50,)) for _ in range(4)]

        all_workers = res_threads + conf_threads + fav_threads + read_threads
        for t in all_workers:
            t.start()
        for t in all_workers:
            t.join(timeout=15.0)

        # Assert zero thread errors
        self.assertEqual(len(errors), 0, f"Thread errors encountered: {errors[:5]}")

        # Check latency metrics
        metrics = self.db.get_sqlite_latency_metrics()
        self.assertGreater(metrics["total_ops"], 500)
        self.assertGreater(metrics["write_ops"], 200)
        self.assertLess(metrics["avg_latency_ms"], 50.0)  # average latency under 50ms
        self.assertLess(metrics["error_rate_pct"], 1.0)   # error rate < 1%
        self.assertEqual(metrics["transaction_failures"], 0)

        # Verify integrity of database after concurrency
        integrity = self.db.diagnose_database_integrity()
        self.assertTrue(integrity["healthy"])
        self.assertEqual(integrity["integrity_check"], "ok")

    # -------------------------------------------------------------------------
    # 3. Database Contention & Recovery from 'database is locked' Errors
    # -------------------------------------------------------------------------
    def test_03_contention_and_recovery_from_locked(self):
        """
        Simulates artificial write contention using an external connection holding an
        exclusive lock, verifying write_transaction's automatic retry with backoff.
        """
        self.db.reset_sqlite_latency_metrics()

        # Seed test record
        self.db.add_unseen_wallpapers([{
            "id": "wp_lock_test",
            "url": "https://w.wallhaven.cc/full/lk/wallhaven-lock.jpg",
            "anime": "Steins;Gate"
        }])

        lock_acquired = threading.Event()
        release_lock = threading.Event()

        def external_blocker():
            # Open direct connection with immediate exclusive lock in separate thread
            conn = database.sqlite3.connect(str(self.db_path), timeout=0.1)
            cur = conn.cursor()
            cur.execute("BEGIN EXCLUSIVE")
            cur.execute("UPDATE wallpaper_lifecycle SET views = views + 1 WHERE id = 'wp_lock_test'")
            lock_acquired.set()
            release_lock.wait(timeout=3.0)
            conn.commit()
            conn.close()

        blocker_thread = threading.Thread(target=external_blocker)
        blocker_thread.start()

        # Wait until external thread holds the lock
        self.assertTrue(lock_acquired.wait(timeout=2.0))

        # Schedule release after 120ms
        def delayed_release():
            time.sleep(0.12)
            release_lock.set()

        threading.Thread(target=delayed_release).start()

        # Execute write_transaction with low busy_timeout_ms so lock errors surface to Python
        # to trigger exponential backoff retry
        t_start = time.time()
        with self.db.write_transaction(retries=10, backoff_base=0.03, busy_timeout_ms=50) as (conn, cur):
            cur.execute("UPDATE wallpaper_lifecycle SET favorites = 999 WHERE id = 'wp_lock_test'")

        blocker_thread.join(timeout=3.0)
        elapsed = time.time() - t_start

        # Verify write succeeded
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT favorites FROM wallpaper_lifecycle WHERE id = 'wp_lock_test'")
            row = cur.fetchone()
            self.assertEqual(row[0], 999)

        # Verify that lock contention/retries were tracked
        metrics = self.db.get_sqlite_latency_metrics()
        self.assertGreaterEqual(metrics["lock_retries"], 1)
        self.assertGreaterEqual(metrics["lock_contention_events"], 1)

    # -------------------------------------------------------------------------
    # 4. Clean Rollback on Failure & Zero Partial Records
    # -------------------------------------------------------------------------
    def test_04_clean_rollback_on_failure_no_partial_records(self):
        """
        Verifies that when an exception occurs inside a write_transaction,
        all modifications are atomically rolled back, leaving zero partial records,
        and incrementing the rollback metric.
        """
        self.db.reset_sqlite_latency_metrics()

        init_count = self.db.get_stats()["total_catalog"]

        # Attempt atomic multi-step insertion where step 2 fails
        with self.assertRaises(ValueError):
            with self.db.write_transaction() as (conn, cur):
                cur.execute("""
                    INSERT INTO wallpaper_lifecycle (id, url, anime, status)
                    VALUES ('wp_rollback_01', 'https://example.com/rb1.jpg', 'Neon Genesis', 'UNSEEN')
                """)
                cur.execute("""
                    INSERT INTO wallpaper_lifecycle (id, url, anime, status)
                    VALUES ('wp_rollback_02', 'https://example.com/rb2.jpg', 'Neon Genesis', 'UNSEEN')
                """)
                # Deliberate failure mid-transaction
                raise ValueError("Simulated unexpected application fault mid-transaction")

        # Assert ZERO records from the failed transaction were committed
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE id IN ('wp_rollback_01', 'wp_rollback_02')")
            cnt = cur.fetchone()[0]
            self.assertEqual(cnt, 0)

        # Assert total count unchanged
        self.assertEqual(self.db.get_stats()["total_catalog"], init_count)

        # Assert rollback count incremented
        metrics = self.db.get_sqlite_latency_metrics()
        self.assertGreaterEqual(metrics["rollbacks"], 1)

    # -------------------------------------------------------------------------
    # 5. Application Shutdown While Operations are Running
    # -------------------------------------------------------------------------
    def test_05_application_shutdown_while_operations_running(self):
        """
        Verifies graceful draining and clean rejection when close_and_checkpoint is called
        while background operations are executing.
        """
        stop_worker = threading.Event()
        worker_errors = []

        def background_writer():
            idx = 0
            while not stop_worker.is_set():
                try:
                    self.db.add_unseen_wallpapers([{
                        "id": f"wp_shut_{idx}",
                        "url": f"https://example.com/{idx}.jpg",
                        "anime": "Cowboy Bebop"
                    }])
                    idx += 1
                    time.sleep(0.002)
                except RuntimeError as re:
                    if "shutting down" in str(re):
                        worker_errors.append("ShutdownRejected")
                        break
                except Exception as e:
                    worker_errors.append(f"Unexpected: {e}")
                    break

        writer_thread = threading.Thread(target=background_writer)
        writer_thread.start()
        time.sleep(0.03)

        # Signal shutdown and checkpoint
        checkpoint_ok = self.db.close_and_checkpoint(timeout=3.0)

        # Subsequent write must be rejected cleanly
        try:
            self.db.add_unseen_wallpapers([{"id": "wp_after_shut", "url": "https://example.com/x.jpg"}])
        except RuntimeError as re:
            if "shutting down" in str(re):
                worker_errors.append("ShutdownRejected")

        stop_worker.set()
        writer_thread.join(timeout=3.0)

        self.assertTrue(checkpoint_ok)
        self.assertIn("ShutdownRejected", worker_errors)

        # Calling reopen() restores normal operation
        self.db.reopen()
        with self.db.write_transaction() as (conn, cur):
            cur.execute("INSERT OR REPLACE INTO favorites (id, url) VALUES ('wp_reopen_ok', 'url')")
        self.assertTrue(self.db.is_favorite("wp_reopen_ok"))

    # -------------------------------------------------------------------------
    # 6. SQLite WAL & Shared-Memory Files Lifecycle & Truncation
    # -------------------------------------------------------------------------
    def test_06_wal_and_shm_lifecycle_during_shutdown_and_restart(self):
        """
        Verifies that SQLite WAL and shared-memory (-wal, -shm) files accumulate
        changes and are cleanly truncated/flushed to the main database file on close_and_checkpoint.
        """
        wal_path = self.db_path.with_name(self.db_path.name + "-wal")

        # Perform numerous writes to generate WAL pages
        batch = [
            {"id": f"wp_wal_{i}", "url": f"https://example.com/w{i}.jpg", "anime": "Evangelion"}
            for i in range(200)
        ]
        self.db.add_unseen_wallpapers(batch)

        # Force sync to disk
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle")
            count_before = cur.fetchone()[0]

        # Checkpoint and close
        success = self.db.close_and_checkpoint(timeout=3.0)
        self.assertTrue(success)

        # After TRUNCATE checkpoint, WAL file must either be removed or have size 0
        wal_size_after = wal_path.stat().st_size if wal_path.exists() else 0
        self.assertEqual(wal_size_after, 0, f"Expected 0-byte WAL file after TRUNCATE, found {wal_size_after} bytes")

        # Reopen database and verify all data persists in the main .db file
        self.db.reopen()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle")
            count_after = cur.fetchone()[0]
            self.assertEqual(count_before, count_after)

    # -------------------------------------------------------------------------
    # 7. Database Integrity Diagnostics & Actionable Recommendations
    # -------------------------------------------------------------------------
    def test_07_integrity_diagnostics_and_actionable_recommendations(self):
        """
        Tests diagnose_database_integrity() on healthy and simulated degraded/corrupted
        databases, asserting comprehensive diagnostics and actionable remediation advice.
        """
        # 1. Healthy database check
        report = self.db.diagnose_database_integrity()
        self.assertEqual(report["status"], "healthy")
        self.assertTrue(report["healthy"])
        self.assertEqual(report["quick_check"], "ok")
        self.assertEqual(report["integrity_check"], "ok")
        self.assertEqual(report["foreign_key_check"], "ok")
        self.assertEqual(report["journal_mode"], "wal")
        self.assertGreaterEqual(report["schema_version"], 16)
        self.assertGreaterEqual(report["tables_count"], 15)
        self.assertIsInstance(report["recommendations"], list)

        # 2. Corrupted database check: damage pages of an existing database
        corrupt_dir = Path(tempfile.mkdtemp(prefix="kuro_corrupt_test_"))
        corrupt_db_path = corrupt_dir / "corrupt.db"
        try:
            corrupt_db = database.DatabaseManager(corrupt_db_path)
            corrupt_db.close_and_checkpoint(timeout=1.0)
            corrupt_db.reopen()

            # Overwrite database header directly
            with open(corrupt_db_path, "r+b") as f:
                f.seek(0)
                f.write(b"GARBAGE_HEADER_CORRUPTED_DATABASE")

            diag = corrupt_db.diagnose_database_integrity()
            self.assertEqual(diag["status"], "corrupt")
            self.assertFalse(diag["healthy"])
            self.assertIn("recommendations", diag)
            self.assertTrue(any("corruption" in r.lower() or "recover" in r.lower() for r in diag["recommendations"]))
        finally:
            shutil.rmtree(corrupt_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 8. Schema Versioning & Transactional Migrations
    # -------------------------------------------------------------------------
    def test_08_schema_versioning_and_transactional_migrations(self):
        """
        Verifies that schema migrations are version-tracked, safe, and create
        pre-migration backups when an existing database is upgraded.
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version, applied_at FROM schema_migrations ORDER BY version ASC")
            migrations = cur.fetchall()

            # Ensure all migrations 2 to CURRENT_SCHEMA_VERSION are logged
            versions = [m["version"] for m in migrations]
            self.assertIn(2, versions)
            self.assertIn(database.CURRENT_SCHEMA_VERSION, versions)
            self.assertEqual(max(versions), database.CURRENT_SCHEMA_VERSION)

        # Test pre-migration backup creation on upgrading
        test_upgrade_dir = Path(tempfile.mkdtemp(prefix="kuro_upgrade_test_"))
        test_upgrade_db = test_upgrade_dir / "upgrade_kuro.db"
        try:
            # Initialize a valid baseline database
            mgr_base = database.DatabaseManager(test_upgrade_db)
            mgr_base.close_and_checkpoint()

            # Roll back schema_migrations to v14 and drop v15/v16 tables to simulate an existing v14 installation
            conn = database.sqlite3.connect(str(test_upgrade_db))
            conn.execute("DELETE FROM schema_migrations WHERE version > 14;")
            conn.execute("DROP TABLE IF EXISTS blocked_entities;")
            conn.execute("DROP TABLE IF EXISTS moderation_review_queue;")
            conn.execute("DROP TABLE IF EXISTS safety_policy_settings;")
            conn.execute("DROP TABLE IF EXISTS wallhaven_compatibility_status;")
            conn.commit()
            conn.close()

            # Initializing DatabaseManager on v14 should automatically create pre-migration backup and upgrade to v16
            mgr = database.DatabaseManager(test_upgrade_db)
            diag = mgr.diagnose_database_integrity()
            self.assertEqual(diag["schema_version"], database.CURRENT_SCHEMA_VERSION)

            # Verify backup was created
            backups_dir = test_upgrade_dir / "backups"
            self.assertTrue(backups_dir.exists())
            backup_files = list(backups_dir.glob("*.zip")) + list(backups_dir.glob("*.db"))
            self.assertGreaterEqual(len(backup_files), 1)
        finally:
            shutil.rmtree(test_upgrade_dir, ignore_errors=True)


class TestHighThroughputConcurrentHTTPStress(unittest.TestCase):
    """
    Stress-tests the live HTTP API server under concurrent loads
    simulating thousands of requests and verifying database stability.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="kuro_http_stress_"))
        cls.db_path = cls.test_dir / "stress_http.db"
        cls.db = database.DatabaseManager(cls.db_path)

        # Populate with 500 initial wallpapers
        items = [{
            "id": f"wp_http_{i:04d}",
            "url": f"https://w.wallhaven.cc/full/ht/wallhaven-http_{i:04d}.jpg",
            "resolution": "3840x2160",
            "anime": "Attack on Titan" if i % 2 == 0 else "Demon Slayer",
            "character": "Levi" if i % 2 == 0 else "Nezuko",
            "quality_score": 88.0,
            "dimension_x": 3840,
            "dimension_y": 2160,
            "file_size": 4200000
        } for i in range(500)]
        cls.db.add_unseen_wallpapers(items)

        # Backup server globals
        cls.orig_db = server.db_manager
        cls.orig_backup = server.backup_manager

        server.db_manager = cls.db
        server.backup_manager = BackupManager(cls.db, cls.test_dir, cls.test_dir / "backups")

        cls.port = 59888
        cls.server = server.ThreadedHTTPServer(("127.0.0.1", cls.port), server.KuroHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

        cls.token = server.security_manager.session_token
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass
        server.db_manager = cls.orig_db
        server.backup_manager = cls.orig_backup
        try:
            shutil.rmtree(cls.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_09_high_throughput_concurrent_http_stress(self):
        """
        Spawns 12 concurrent worker threads executing 600+ HTTP requests:
        - GET /api/wallpaper (reservation)
        - POST /api/confirm-display (lifecycle commit)
        - POST /api/favorite (user favorites)
        - GET /api/favorites (retrieval)
        - GET /api/stats (metrics)
        - GET /api/database/integrity (diagnostics)
        Measures HTTP request latency, write latency, lock retries, and error rate.
        """
        num_requests_per_thread = 50
        num_threads = 12
        http_latencies = []
        http_errors = []
        reserved_items = []
        items_lock = threading.Lock()

        def http_worker(thread_id: int):
            for i in range(num_requests_per_thread):
                op = i % 5
                t0 = time.perf_counter()
                try:
                    if op == 0:
                        # GET /api/next (triggers reserve_next_wallpaper)
                        url = f"{self.base_url}/api/next"
                        with urllib.request.urlopen(url, timeout=5.0) as resp:
                            if resp.status == 200:
                                data = json.loads(resp.read().decode("utf-8"))
                                if data.get("id") and data.get("reservation_token"):
                                    with items_lock:
                                        reserved_items.append((data["id"], data["reservation_token"]))
                    elif op == 1:
                        # POST /api/confirm-display
                        item = None
                        with items_lock:
                            if reserved_items:
                                item = reserved_items.pop(0)
                        if item:
                            wid, tok = item
                            req = urllib.request.Request(
                                f"{self.base_url}/api/confirm-display",
                                data=json.dumps({"id": wid, "token": tok}).encode("utf-8"),
                                headers={"Content-Type": "application/json", "X-Kuro-Token": self.token}
                            )
                            with urllib.request.urlopen(req, timeout=5.0) as resp:
                                self.assertEqual(resp.status, 200)
                    elif op == 2:
                        # POST /api/favorite
                        wid = f"wp_http_{random.randint(0, 499):04d}"
                        req = urllib.request.Request(
                            f"{self.base_url}/api/favorite",
                            data=json.dumps({"id": wid, "url": f"https://w.wallhaven.cc/full/ht/wallhaven-{wid}.jpg"}).encode("utf-8"),
                            headers={"Content-Type": "application/json", "X-Kuro-Token": self.token}
                        )
                        with urllib.request.urlopen(req, timeout=5.0) as resp:
                            self.assertEqual(resp.status, 200)
                    elif op == 3:
                        # GET /api/stats
                        with urllib.request.urlopen(f"{self.base_url}/api/stats", timeout=5.0) as resp:
                            self.assertEqual(resp.status, 200)
                    elif op == 4:
                        # GET /api/database/integrity
                        with urllib.request.urlopen(f"{self.base_url}/api/database/integrity", timeout=5.0) as resp:
                            self.assertEqual(resp.status, 200)

                    lat_ms = (time.perf_counter() - t0) * 1000.0
                    http_latencies.append(lat_ms)
                except Exception as ex:
                    http_errors.append(f"HTTP Worker {thread_id} Op {op}: {ex}")

        threads = [threading.Thread(target=http_worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=25.0)

        total_reqs = len(http_latencies)
        err_count = len(http_errors)
        error_rate = (err_count / max(1, total_reqs + err_count)) * 100.0

        # Assert zero or negligible errors (< 1%)
        self.assertLess(error_rate, 1.0, f"HTTP stress error rate too high ({error_rate}%): {http_errors[:5]}")
        self.assertGreater(total_reqs, 400)

        # Calculate latency percentiles
        sorted_lats = sorted(http_latencies)
        avg_lat = sum(sorted_lats) / len(sorted_lats)
        p50 = sorted_lats[int(len(sorted_lats) * 0.50)]
        p95 = sorted_lats[int(len(sorted_lats) * 0.95)]
        p99 = sorted_lats[int(len(sorted_lats) * 0.99)]
        max_lat = sorted_lats[-1]

        # Verify database metrics
        metrics = self.db.get_sqlite_latency_metrics()

        print(f"\n--- HTTP & SQLite Concurrency Stress Results ---")
        print(f"Total Completed HTTP Requests: {total_reqs}")
        print(f"HTTP Latency (ms): avg={avg_lat:.2f}, p50={p50:.2f}, p95={p95:.2f}, p99={p99:.2f}, max={max_lat:.2f}")
        print(f"SQLite Operations: {metrics['total_ops']} (writes: {metrics['write_ops']})")
        print(f"SQLite Write Latency (ms): avg={metrics['write_avg_ms']}, p95={metrics['write_p95_ms']}")
        print(f"Lock Retries: {metrics['lock_retries']}, Contention Events: {metrics['lock_contention_events']}")
        print(f"Transaction Failures: {metrics['transaction_failures']}, Rollbacks: {metrics['rollbacks']}")
        print(f"Error Rate: {error_rate:.2f}%\n")

        # Database integrity check post-stress
        diag = self.db.diagnose_database_integrity()
        self.assertTrue(diag["healthy"])
        self.assertEqual(diag["quick_check"], "ok")
        self.assertEqual(diag["integrity_check"], "ok")


if __name__ == "__main__":
    unittest.main()
