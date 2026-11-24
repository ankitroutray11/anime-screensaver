"""
Comprehensive unit and integration test suite for KuroAnime Screensaver
Backup & Recovery System and Database Schema Versioning.
Tests:
1. Online safe SQLite backup via sqlite3.Connection.backup() API.
2. Full backup archive generation (manifest, database, config, favorites, cache).
3. Archive validation (checksums, schema compatibility, SQLite integrity).
4. Rejection of tampered or corrupt archives.
5. Restoration requiring explicit confirmation.
6. Automatic pre-restore safety snapshot before applying restore.
7. Automatic pre-migration snapshot during database schema upgrade.
8. Configurable retention limit & pruning of automatic snapshots.
9. Database integrity diagnostics API.
10. REST API endpoints (/api/backups, /api/backups/restore, /api/database/integrity).
100% Python Standard Library.
"""

import os
import sys
import json
import time
import shutil
import sqlite3
import zipfile
import tempfile
import unittest
import urllib.request
import urllib.error
import threading
from pathlib import Path

import database
import server
from backup_manager import BackupManager

class TestBackupAndRecovery(unittest.TestCase):
    """Verifies complete backup, validation, restoration, and integrity capabilities in an isolated temp directory."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_backup_test_"))
        self.db_path = self.test_dir / "test_kuro.db"
        self.backups_dir = self.test_dir / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.favorites_dir = self.test_dir / "favorites"
        self.favorites_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.test_dir / ".cache" / "wallpapers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy launcher_config.json
        self.config_path = self.test_dir / "launcher_config.json"
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"mode": "kiosk", "target_monitor": "auto"}, f)

        # Create dummy favorite image
        (self.favorites_dir / "fav_01.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest")
        # Create dummy cache image
        (self.cache_dir / "cache_01.jpg").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIFtest")

        self.db = database.DatabaseManager(self.db_path)
        self.backup_mgr = BackupManager(
            db_manager=self.db,
            app_dir=self.test_dir,
            backups_dir=self.backups_dir,
            max_auto_backups=3
        )

    def tearDown(self):
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_01_sqlite_backup_api(self):
        """Verifies online SQLite backup using sqlite3.Connection.backup()."""
        # Insert test data into lifecycle
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO wallpaper_lifecycle (id, url, anime, status)
                VALUES ('wp_test_backup_01', 'https://example.com/art1.png', 'Attack on Titan', 'DISPLAYED')
            """)
            conn.commit()

        # Backup to a separate file using SQLite backup API
        target_db = self.test_dir / "online_copy.db"
        with self.db.get_connection() as src_conn:
            dest_conn = sqlite3.connect(str(target_db))
            src_conn.backup(dest_conn)
            dest_conn.close()

        # Verify target database has the data and passes integrity check
        check_conn = sqlite3.connect(str(target_db))
        row = check_conn.execute("SELECT anime, status FROM wallpaper_lifecycle WHERE id='wp_test_backup_01'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Attack on Titan")
        self.assertEqual(row[1], "DISPLAYED")

        integ = check_conn.execute("PRAGMA integrity_check;").fetchall()
        self.assertEqual(integ[0][0], "ok")
        check_conn.close()

    def test_02_export_backup_archive_structure(self):
        """Verifies full backup archive generation with manifest, checksums, and optional assets."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO wallpaper_lifecycle (id, url, anime, status)
                VALUES ('wp_arch_01', 'https://example.com/art.png', 'Demon Slayer', 'DISPLAYED')
            """)
            conn.commit()

        res = self.backup_mgr.export_backup(
            backup_type="manual",
            include_favorites=True,
            include_cache=True,
            custom_note="Test manual backup export"
        )

        self.assertTrue(res["success"])
        archive_path = Path(res["path"])
        self.assertTrue(archive_path.is_file())
        self.assertTrue(zipfile.is_zipfile(archive_path))

        with zipfile.ZipFile(archive_path, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            self.assertIn("database.sqlite3", namelist)
            self.assertIn("launcher_config.json", namelist)
            self.assertIn("favorites/fav_01.png", namelist)
            self.assertIn("cache/cache_01.jpg", namelist)

            with zf.open("manifest.json") as mf:
                manifest = json.load(mf)
                self.assertEqual(manifest["app_name"], "KURO // ANIME Ambient Screensaver")
                self.assertGreaterEqual(manifest["schema_version"], 12)
                self.assertEqual(manifest["backup_type"], "manual")
                self.assertIn("database.sqlite3", manifest["checksums"])
                self.assertIn("launcher_config.json", manifest["checksums"])

    def test_03_validate_backup_archive_valid_and_tampered(self):
        """Verifies archive validation detects healthy archives and rejects tampered/corrupt files."""
        res = self.backup_mgr.export_backup(backup_type="manual")
        archive_path = Path(res["path"])

        # 1. Healthy archive validates successfully
        val_res = self.backup_mgr.validate_backup_archive(archive_path)
        self.assertTrue(val_res["valid"])
        self.assertEqual(val_res["errors"], [])
        self.assertEqual(val_res["integrity_check"], "ok")

        # 2. Corrupt zip file fails validation
        corrupt_zip = self.test_dir / "corrupt.zip"
        corrupt_zip.write_bytes(b"NOT_A_VALID_ZIP_ARCHIVE_DATA")
        val_bad_zip = self.backup_mgr.validate_backup_archive(corrupt_zip)
        self.assertFalse(val_bad_zip["valid"])
        self.assertIn("not a valid ZIP archive", val_bad_zip["errors"][0])

        # 3. Mismatched checksum in manifest fails validation
        tampered_zip = self.test_dir / "tampered.zip"
        with zipfile.ZipFile(archive_path, "r") as src_z, zipfile.ZipFile(tampered_zip, "w") as dst_z:
            for item in src_z.namelist():
                if item == "manifest.json":
                    with src_z.open(item) as mf:
                        m = json.load(mf)
                        m["checksums"]["database.sqlite3"] = "deadbeef" * 8
                    dst_z.writestr("manifest.json", json.dumps(m))
                else:
                    dst_z.writestr(item, src_z.read(item))

        val_tampered = self.backup_mgr.validate_backup_archive(tampered_zip)
        self.assertFalse(val_tampered["valid"])
        self.assertTrue(any("checksum mismatch" in err for err in val_tampered["errors"]))

    def test_04_restore_requires_confirmation(self):
        """Verifies restoring without confirm=True is strictly rejected to prevent data loss."""
        res = self.backup_mgr.export_backup(backup_type="manual")
        archive_path = Path(res["path"])

        # Attempt restore with confirm=False
        attempt = self.backup_mgr.restore_backup(archive_path, confirm=False)
        self.assertFalse(attempt["success"])
        self.assertIn("Confirmation required", attempt["error"])

    def test_05_restore_successful_with_auto_pre_restore_snapshot(self):
        """Verifies successful restoration restores database and creates an auto_pre_restore snapshot."""
        # State 1: anime = Steins;Gate
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO wallpaper_lifecycle (id, url, anime, status)
                VALUES ('wp_sg_01', 'https://example.com/sg.png', 'Steins;Gate', 'DISPLAYED')
            """)
            conn.commit()

        # Backup State 1
        bkp1 = self.backup_mgr.export_backup(backup_type="manual")
        archive_path = Path(bkp1["path"])

        # State 2: anime = Jujutsu Kaisen
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM wallpaper_lifecycle")
            cur.execute("""
                INSERT OR REPLACE INTO wallpaper_lifecycle (id, url, anime, status)
                VALUES ('wp_jjk_01', 'https://example.com/jjk.png', 'Jujutsu Kaisen', 'DISPLAYED')
            """)
            conn.commit()

        # Verify State 2 is active
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT anime FROM wallpaper_lifecycle WHERE id='wp_jjk_01'")
            self.assertEqual(cur.fetchone()[0], "Jujutsu Kaisen")

        # Restore State 1 with confirmation
        restore_res = self.backup_mgr.restore_backup(archive_path, confirm=True)
        self.assertTrue(restore_res["success"])

        # Verify State 1 data is restored
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT anime FROM wallpaper_lifecycle WHERE id='wp_sg_01'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "Steins;Gate")

            # State 2 should be gone
            cur.execute("SELECT 1 FROM wallpaper_lifecycle WHERE id='wp_jjk_01'")
            self.assertIsNone(cur.fetchone())

        # Verify an automatic pre-restore backup was generated
        pre_restores = [p for p in self.backups_dir.iterdir() if "auto_pre_restore" in p.name]
        self.assertGreaterEqual(len(pre_restores), 1)

    def test_06_pre_migration_backup_creation(self):
        """Verifies database schema upgrade automatically snapshots existing database before migrating."""
        v5_db_path = self.test_dir / "v5_test.db"
        v5_backups_dir = self.test_dir / "backups"

        # Create a database with schema version 5
        conn = sqlite3.connect(str(v5_db_path))
        conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP)")
        conn.execute("INSERT INTO schema_migrations (version) VALUES (5)")
        conn.execute("""
            CREATE TABLE wallpaper_lifecycle (
                id TEXT PRIMARY KEY,
                url TEXT,
                resolution TEXT,
                anime TEXT,
                character TEXT,
                tags TEXT,
                source TEXT,
                status TEXT,
                local_path TEXT,
                is_cached INTEGER,
                level INTEGER
            )
        """)
        conn.execute("INSERT INTO wallpaper_lifecycle (id, url, anime, status) VALUES ('wp_v5', 'http://a.com', 'Bleach', 'DISPLAYED')")
        conn.commit()
        conn.close()

        # Initialize DatabaseManager on the v5 database - it should trigger migrations up to CURRENT_SCHEMA_VERSION (13)
        # and automatically create a pre-migration backup!
        db_mgr_mig = database.DatabaseManager(v5_db_path)

        # Verify pre-migration backup was created
        pre_mig_backups = [p for p in v5_backups_dir.iterdir() if "auto_pre_migration" in p.name]
        self.assertGreaterEqual(len(pre_mig_backups), 1)

        # Verify database successfully migrated to current schema version (13)
        with db_mgr_mig.get_connection() as c:
            cur = c.cursor()
            cur.execute("SELECT MAX(version) FROM schema_migrations")
            v = cur.fetchone()[0]
            self.assertEqual(v, database.CURRENT_SCHEMA_VERSION)

            # Data was preserved
            cur.execute("SELECT anime FROM wallpaper_lifecycle WHERE id='wp_v5'")
            self.assertEqual(cur.fetchone()[0], "Bleach")

    def test_07_pruning_automatic_backups(self):
        """Verifies configurable retention prunes oldest automatic backups without touching manual backups."""
        # Create 1 manual backup
        self.backup_mgr.export_backup(backup_type="manual")

        # Create 5 automatic backups with slight sleep to ensure distinct timestamps
        for i in range(5):
            time.sleep(0.05)
            self.backup_mgr.export_backup(backup_type=f"auto_snapshot_{i}")

        # List all auto backups
        all_backups = self.backup_mgr.list_backups()
        auto_count = sum(1 for b in all_backups if "auto" in b["backup_type"])
        manual_count = sum(1 for b in all_backups if b["backup_type"] == "manual")

        # With max_auto_backups = 3, auto backups should be pruned to 3
        self.assertEqual(auto_count, 3)
        # Manual backup should remain intact
        self.assertEqual(manual_count, 1)

    def test_08_database_integrity_diagnostics(self):
        """Verifies check_database_integrity reports healthy status on valid database."""
        report = self.backup_mgr.check_database_integrity()
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["integrity_check"], "ok")
        self.assertEqual(report["quick_check"], "ok")
        self.assertEqual(report["foreign_key_check"], "ok")
        self.assertGreaterEqual(report["schema_version"], 12)
        self.assertGreater(report["tables_count"], 10)


class TestBackupAPIEndpoints(unittest.TestCase):
    """Verifies REST API endpoints for backups and database integrity."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = Path(tempfile.mkdtemp(prefix="kuro_backup_api_test_"))
        cls.db_path = cls.test_dir / "test_api_kuro.db"
        cls.backups_dir = cls.test_dir / "backups"
        cls.backups_dir.mkdir(parents=True, exist_ok=True)

        cls.db = database.DatabaseManager(cls.db_path)
        cls.orig_db = server.db_manager
        cls.orig_backup_mgr = server.backup_manager

        server.db_manager = cls.db
        server.backup_manager = BackupManager(cls.db, cls.test_dir, cls.backups_dir)

        # Spin up test server on a high port
        cls.port = 59876
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
        server.backup_manager = cls.orig_backup_mgr
        try:
            shutil.rmtree(cls.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_09_api_list_and_create_backup(self):
        """Verifies GET /api/backups and POST /api/backups."""
        # 1. Create backup via POST /api/backups
        req = urllib.request.Request(
            f"{self.base_url}/api/backups",
            data=json.dumps({"backup_type": "manual", "include_favorites": False, "note": "API test"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertIn("filename", data)
            created_filename = data["filename"]

        # 2. List backups via GET /api/backups
        with urllib.request.urlopen(f"{self.base_url}/api/backups") as resp:
            self.assertEqual(resp.status, 200)
            list_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(list_data["status"], "ok")
            self.assertGreaterEqual(len(list_data["backups"]), 1)
            filenames = [b["filename"] for b in list_data["backups"]]
            self.assertIn(created_filename, filenames)

        # 3. Download backup via GET /api/backups/download?filename=...
        dl_url = f"{self.base_url}/api/backups/download?filename={urllib.parse.quote(created_filename)}"
        with urllib.request.urlopen(dl_url) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read()
            self.assertTrue(content.startswith(b"PK"))  # Standard ZIP signature

        # 4. Check integrity via GET /api/database/integrity
        with urllib.request.urlopen(f"{self.base_url}/api/database/integrity") as resp:
            self.assertEqual(resp.status, 200)
            integ_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(integ_data["status"], "healthy")

        # 5. Restore backup via POST /api/backups/restore without confirm should fail
        req_bad = urllib.request.Request(
            f"{self.base_url}/api/backups/restore",
            data=json.dumps({"filename": created_filename, "confirm": False}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.token}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_bad)
        self.assertEqual(ctx.exception.code, 400)

        # 6. Restore backup via POST /api/backups/restore with confirm should succeed
        req_ok = urllib.request.Request(
            f"{self.base_url}/api/backups/restore",
            data=json.dumps({"filename": created_filename, "confirm": True}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.token}
        )
        with urllib.request.urlopen(req_ok) as resp:
            self.assertEqual(resp.status, 200)
            rest_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(rest_data["success"])

        # 7. Delete backup via POST /api/backups/delete
        req_del = urllib.request.Request(
            f"{self.base_url}/api/backups/delete",
            data=json.dumps({"filename": created_filename}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Kuro-Token": self.token}
        )
        with urllib.request.urlopen(req_del) as resp:
            self.assertEqual(resp.status, 200)
            del_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(del_data["success"])

    def test_10_preservation_of_workspace_database(self):
        """Verifies the workspace database (kuro_database.db) is preserved and undamaged."""
        ws_db_path = Path("kuro_database.db").resolve()
        if ws_db_path.exists():
            c = sqlite3.connect(str(ws_db_path))
            try:
                res = c.execute("PRAGMA integrity_check;").fetchall()
                self.assertEqual(res[0][0], "ok")
            finally:
                c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
