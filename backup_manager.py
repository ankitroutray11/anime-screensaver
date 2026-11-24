"""
Backup and Recovery Manager for KuroAnime Screensaver.
Handles online SQLite backup API operations, manifest metadata generation,
archive validation, transactional restorations with pre-restore safety snapshots,
pre-migration automated backups, and database integrity audits.
100% Python Standard Library.
"""

import os
import sys
import time
import json
import shutil
import sqlite3
import zipfile
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

class BackupManager:
    """
    Manages complete, safe, transactional backups and restorations of KuroAnime screensaver data.
    """

    def __init__(
        self,
        db_manager,
        app_dir: Optional[Path] = None,
        backups_dir: Optional[Path] = None,
        max_auto_backups: int = 5
    ):
        self.db_manager = db_manager
        if app_dir:
            self.app_dir = Path(app_dir).resolve()
        elif hasattr(db_manager, "db_path"):
            self.app_dir = Path(db_manager.db_path).resolve().parent
        else:
            self.app_dir = Path.cwd().resolve()

        self.backups_dir = Path(backups_dir).resolve() if backups_dir else (self.app_dir / "backups")
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.max_auto_backups = max(1, int(max_auto_backups))

    @staticmethod
    def compute_file_sha256(file_path: Path) -> str:
        """Computes SHA-256 hex digest for a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_system_stats(self) -> Dict[str, Any]:
        """Gathers counts and metrics across all SQLite tables for manifest metadata."""
        stats = {
            "wallpapers_total": 0,
            "wallpapers_displayed": 0,
            "favorites_count": 0,
            "collections_count": 0,
            "blacklist_count": 0,
            "preference_scores_count": 0,
            "interaction_events_count": 0,
            "schema_version": 1,
            "db_file_size_bytes": 0,
            "wal_file_size_bytes": 0
        }

        db_path = getattr(self.db_manager, "db_path", self.app_dir / "kuro_database.db")
        if db_path.exists():
            stats["db_file_size_bytes"] = db_path.stat().st_size
        wal_path = Path(str(db_path) + "-wal")
        if wal_path.exists():
            stats["wal_file_size_bytes"] = wal_path.stat().st_size

        try:
            with self.db_manager.get_connection() as conn:
                cur = conn.cursor()

                # Schema version
                try:
                    cur.execute("SELECT MAX(version) FROM schema_migrations")
                    row = cur.fetchone()
                    stats["schema_version"] = row[0] if (row and row[0] is not None) else 1
                except Exception:
                    pass

                # Wallpapers
                try:
                    cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle")
                    stats["wallpapers_total"] = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE status = 'DISPLAYED'")
                    stats["wallpapers_displayed"] = cur.fetchone()[0]
                except Exception:
                    try:
                        cur.execute("SELECT COUNT(*) FROM seen_wallpapers")
                        stats["wallpapers_displayed"] = cur.fetchone()[0]
                    except Exception:
                        pass

                # Favorites
                try:
                    cur.execute("SELECT COUNT(*) FROM favorites")
                    stats["favorites_count"] = cur.fetchone()[0]
                except Exception:
                    pass

                # Collections
                try:
                    cur.execute("SELECT COUNT(*) FROM collections")
                    stats["collections_count"] = cur.fetchone()[0]
                except Exception:
                    pass

                # Blacklist
                try:
                    cur.execute("SELECT COUNT(*) FROM blacklist")
                    stats["blacklist_count"] = cur.fetchone()[0]
                except Exception:
                    pass

                # Preferences
                try:
                    cur.execute("SELECT COUNT(*) FROM preference_scores")
                    stats["preference_scores_count"] = cur.fetchone()[0]
                except Exception:
                    pass

                # Interactions
                try:
                    cur.execute("SELECT COUNT(*) FROM interaction_events")
                    stats["interaction_events_count"] = cur.fetchone()[0]
                except Exception:
                    pass

        except Exception as e:
            stats["query_error"] = str(e)

        return stats

    def export_backup(
        self,
        backup_type: str = "manual",
        include_favorites: bool = True,
        include_cache: bool = False,
        custom_note: str = ""
    ) -> Dict[str, Any]:
        """
        Creates a versioned, self-contained backup archive using the SQLite Backup API.
        Includes SQLite database, settings, manifest with checksums, and optional assets.
        """
        temp_work_dir = Path(tempfile.mkdtemp(prefix="kuro_backup_stage_"))
        try:
            timestamp_sec = int(time.time())
            iso_timestamp = datetime.now(timezone.utc).isoformat()
            stats = self.get_system_stats()
            schema_version = stats.get("schema_version", 13)

            # 1. Export live SQLite database using sqlite3.Connection.backup()
            exported_db_path = temp_work_dir / "database.sqlite3"
            with self.db_manager.lock:
                with self.db_manager.get_connection() as src_conn:
                    # Flush pending WAL commits
                    try:
                        src_conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
                    except Exception:
                        pass
                    dest_conn = sqlite3.connect(str(exported_db_path))
                    try:
                        src_conn.backup(dest_conn)
                    finally:
                        dest_conn.close()

            # 2. Verify exported database copy integrity
            test_conn = sqlite3.connect(str(exported_db_path))
            try:
                res = test_conn.execute("PRAGMA integrity_check;").fetchall()
                if not res or res[0][0] != "ok":
                    raise sqlite3.DatabaseError(f"Exported SQLite copy failed integrity check: {res}")
            finally:
                test_conn.close()

            db_sha256 = self.compute_file_sha256(exported_db_path)
            checksums = {
                "database.sqlite3": db_sha256
            }

            # 3. Include launcher_config.json if present
            launcher_config_path = self.app_dir / "launcher_config.json"
            if launcher_config_path.is_file():
                staged_config = temp_work_dir / "launcher_config.json"
                shutil.copyfile(launcher_config_path, staged_config)
                checksums["launcher_config.json"] = self.compute_file_sha256(staged_config)

            # 4. Generate manifest.json
            manifest = {
                "app_name": "KURO // ANIME Ambient Screensaver",
                "backup_version": "1.0",
                "schema_version": schema_version,
                "created_at": iso_timestamp,
                "created_timestamp": timestamp_sec,
                "backup_type": backup_type,
                "custom_note": custom_note,
                "stats": stats,
                "includes": {
                    "database": True,
                    "launcher_config": launcher_config_path.is_file(),
                    "favorites": bool(include_favorites),
                    "cache": bool(include_cache)
                },
                "checksums": checksums
            }

            manifest_path = temp_work_dir / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            # 5. Format archive filename: kuro_backup_v{schema_version}_{timestamp}_{type}.zip
            clean_type = backup_type.replace(" ", "_").lower()
            archive_filename = f"kuro_backup_v{schema_version}_{timestamp_sec}_{clean_type}.zip"
            archive_path = self.backups_dir / archive_filename

            # 6. Build ZIP archive
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(manifest_path, arcname="manifest.json")
                zf.write(exported_db_path, arcname="database.sqlite3")

                if launcher_config_path.is_file():
                    zf.write(temp_work_dir / "launcher_config.json", arcname="launcher_config.json")

                # Optional Favorites files
                favorites_dir = self.app_dir / "favorites"
                if include_favorites and favorites_dir.is_dir():
                    for fav_file in favorites_dir.iterdir():
                        if fav_file.is_file():
                            zf.write(fav_file, arcname=f"favorites/{fav_file.name}")

                # Optional Cache files
                cache_dir = self.app_dir / ".cache" / "wallpapers"
                if include_cache and cache_dir.is_dir():
                    for cache_file in cache_dir.iterdir():
                        if cache_file.is_file():
                            zf.write(cache_file, arcname=f"cache/{cache_file.name}")

            archive_size = archive_path.stat().st_size
            archive_sha256 = self.compute_file_sha256(archive_path)

            # 7. Record in backup_records table if exists
            try:
                with self.db_manager.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS backup_records (
                            id TEXT PRIMARY KEY,
                            filename TEXT NOT NULL,
                            backup_type TEXT NOT NULL,
                            file_size INTEGER DEFAULT 0,
                            schema_version INTEGER DEFAULT 13,
                            wallpapers_count INTEGER DEFAULT 0,
                            favorites_count INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            status TEXT DEFAULT 'valid',
                            checksum TEXT
                        )
                    """)
                    cur.execute("""
                        INSERT OR REPLACE INTO backup_records (
                            id, filename, backup_type, file_size, schema_version,
                            wallpapers_count, favorites_count, checksum
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f"bkp_{timestamp_sec}",
                        archive_filename,
                        backup_type,
                        archive_size,
                        schema_version,
                        stats.get("wallpapers_total", 0),
                        stats.get("favorites_count", 0),
                        archive_sha256
                    ))
                    conn.commit()
            except Exception:
                pass

            # 8. Prune older auto-backups if this was an automatic backup
            pruned_count = 0
            if backup_type.startswith("auto_") or "auto" in backup_type:
                pruned_count = self.prune_auto_backups()

            return {
                "success": True,
                "filename": archive_filename,
                "path": str(archive_path),
                "file_size": archive_size,
                "file_size_formatted": self._format_bytes(archive_size),
                "sha256": archive_sha256,
                "backup_type": backup_type,
                "manifest": manifest,
                "pruned_old_backups": pruned_count
            }

        finally:
            shutil.rmtree(temp_work_dir, ignore_errors=True)

    def validate_backup_archive(self, archive_path: Path) -> Dict[str, Any]:
        """
        Validates archive structure, manifest integrity, checksums, SQLite integrity,
        and schema compatibility prior to restoration.
        """
        archive_path = Path(archive_path)
        result: Dict[str, Any] = {
            "valid": False,
            "errors": [],
            "warnings": [],
            "manifest": None,
            "schema_version": None,
            "archive_size": 0,
            "integrity_check": None
        }

        if not archive_path.is_file():
            result["errors"].append(f"Backup file not found: {archive_path.name}")
            return result

        result["archive_size"] = archive_path.stat().st_size

        if not zipfile.is_zipfile(archive_path):
            result["errors"].append("The specified file is not a valid ZIP archive.")
            return result

        temp_extract_dir = Path(tempfile.mkdtemp(prefix="kuro_val_stage_"))
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                file_names = zf.namelist()

                # Check required components
                if "manifest.json" not in file_names:
                    result["errors"].append("Archive is missing required 'manifest.json'.")
                if "database.sqlite3" not in file_names:
                    result["errors"].append("Archive is missing required 'database.sqlite3'.")

                if result["errors"]:
                    return result

                # Extract and parse manifest
                zf.extract("manifest.json", path=temp_extract_dir)
                try:
                    with open(temp_extract_dir / "manifest.json", "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    result["manifest"] = manifest
                    result["schema_version"] = manifest.get("schema_version")
                except Exception as e:
                    result["errors"].append(f"Failed to parse manifest.json: {e}")
                    return result

                # Verify manifest required fields
                for req_key in ("app_name", "backup_version", "checksums"):
                    if req_key not in manifest:
                        result["errors"].append(f"Manifest missing required attribute: '{req_key}'.")

                if result["errors"]:
                    return result

                # Extract database and verify checksum
                zf.extract("database.sqlite3", path=temp_extract_dir)
                extracted_db = temp_extract_dir / "database.sqlite3"
                computed_db_sha256 = self.compute_file_sha256(extracted_db)
                expected_db_sha256 = manifest.get("checksums", {}).get("database.sqlite3")

                if expected_db_sha256 and computed_db_sha256.lower() != expected_db_sha256.lower():
                    result["errors"].append(
                        f"Database checksum mismatch! Expected: {expected_db_sha256[:12]}..., Got: {computed_db_sha256[:12]}..."
                    )
                    return result

                # Run SQLite PRAGMA integrity_check on extracted database
                try:
                    check_conn = sqlite3.connect(str(extracted_db))
                    check_cur = check_conn.cursor()
                    integrity_res = check_cur.execute("PRAGMA integrity_check;").fetchall()
                    check_conn.close()

                    if not integrity_res or integrity_res[0][0] != "ok":
                        result["errors"].append(f"SQLite PRAGMA integrity check failed: {integrity_res}")
                        result["integrity_check"] = integrity_res
                        return result
                    else:
                        result["integrity_check"] = "ok"
                except Exception as e:
                    result["errors"].append(f"Failed to inspect SQLite database inside archive: {e}")
                    return result

                # Check schema version compatibility
                current_sys_ver = getattr(self.db_manager, "CURRENT_SCHEMA_VERSION", 13)
                archive_ver = manifest.get("schema_version", 1)
                if archive_ver > current_sys_ver:
                    result["warnings"].append(
                        f"Archive schema version ({archive_ver}) is newer than current application schema ({current_sys_ver}). "
                        f"Some newer tables or columns may require updating the application."
                    )

                result["valid"] = (len(result["errors"]) == 0)
                return result

        except Exception as e:
            result["errors"].append(f"Archive validation encountered an unexpected exception: {e}")
            return result
        finally:
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

    def restore_backup(
        self,
        archive_path: Path,
        confirm: bool = False,
        restore_favorites: bool = True,
        restore_cache: bool = False
    ) -> Dict[str, Any]:
        """
        Safely restores a backup archive into the active system.
        Requirements:
        - confirm must be explicitly True to prevent accidental data overwrites.
        - Automatically creates a pre-restore safety snapshot before touching live data.
        - Uses the SQLite Backup API to restore online safely without file locking issues.
        - Executes database migrations automatically if the backup has an older schema version.
        """
        archive_path = Path(archive_path)

        if not confirm:
            return {
                "success": False,
                "error": "Confirmation required: restoring will replace existing database history and settings. Set confirm=True."
            }

        # 1. Validate archive
        val_result = self.validate_backup_archive(archive_path)
        if not val_result["valid"]:
            return {
                "success": False,
                "error": "Archive validation failed. Restoration aborted.",
                "details": val_result["errors"]
            }

        # 2. Automatically create pre-restore safety snapshot
        pre_restore_snapshot = None
        try:
            pre_restore_snapshot = self.export_backup(
                backup_type="auto_pre_restore",
                include_favorites=True,
                include_cache=False,
                custom_note=f"Automatic safety snapshot prior to restoring {archive_path.name}"
            )
        except Exception as e:
            print(f"[KuroBackup WARNING] Pre-restore snapshot failed ({e}), proceeding with caution.")

        # 3. Extract verified archive contents to temporary staging area
        temp_restore_dir = Path(tempfile.mkdtemp(prefix="kuro_restore_stage_"))
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(path=temp_restore_dir)

            staged_db = temp_restore_dir / "database.sqlite3"
            if not staged_db.is_file():
                return {"success": False, "error": "Extracted archive missing database.sqlite3."}

            # 4. Online restoration using SQLite Backup API
            src_conn = sqlite3.connect(str(staged_db))
            with self.db_manager.lock:
                with self.db_manager.get_connection() as target_conn:
                    # Clear live WAL if in WAL mode
                    try:
                        target_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    except Exception:
                        pass

                    # Perform online transactional backup from staged DB into live DB connection
                    src_conn.backup(target_conn)
            src_conn.close()

            # 5. Restore launcher_config.json if present
            staged_config = temp_restore_dir / "launcher_config.json"
            if staged_config.is_file():
                dest_config = self.app_dir / "launcher_config.json"
                temp_cfg_write = self.app_dir / f"launcher_config.tmp.{int(time.time())}"
                shutil.copyfile(staged_config, temp_cfg_write)
                temp_cfg_write.replace(dest_config)

            # 6. Restore Favorites files if requested and present in archive
            fav_restored_count = 0
            staged_favs = temp_restore_dir / "favorites"
            if restore_favorites and staged_favs.is_dir():
                dest_favs = self.app_dir / "favorites"
                dest_favs.mkdir(parents=True, exist_ok=True)
                for fav_file in staged_favs.iterdir():
                    if fav_file.is_file():
                        shutil.copyfile(fav_file, dest_favs / fav_file.name)
                        fav_restored_count += 1

            # 7. Restore Cache files if requested and present in archive
            cache_restored_count = 0
            staged_cache = temp_restore_dir / "cache"
            if restore_cache and staged_cache.is_dir():
                dest_cache = self.app_dir / ".cache" / "wallpapers"
                dest_cache.mkdir(parents=True, exist_ok=True)
                for cache_file in staged_cache.iterdir():
                    if cache_file.is_file():
                        shutil.copyfile(cache_file, dest_cache / cache_file.name)
                        cache_restored_count += 1

            # 8. Run migrations on restored database in case it was an earlier schema version
            if hasattr(self.db_manager, "_run_migrations"):
                self.db_manager._run_migrations()

            # 9. Clean up any lingering reservations from the backup
            if hasattr(self.db_manager, "recover_all_reservations_on_startup"):
                self.db_manager.recover_all_reservations_on_startup()

            post_stats = self.get_system_stats()

            return {
                "success": True,
                "message": f"Successfully restored backup from {archive_path.name}",
                "manifest": val_result.get("manifest"),
                "restored_favorites_files": fav_restored_count,
                "restored_cache_files": cache_restored_count,
                "current_stats": post_stats,
                "pre_restore_safety_backup": pre_restore_snapshot.get("filename") if pre_restore_snapshot else None
            }

        except Exception as e:
            return {"success": False, "error": f"Restoration encountered an exception: {e}"}
        finally:
            shutil.rmtree(temp_restore_dir, ignore_errors=True)

    def list_backups(self) -> List[Dict[str, Any]]:
        """Lists all backup archives in backups_dir sorted newest first."""
        backups: List[Dict[str, Any]] = []
        if not self.backups_dir.is_dir():
            return backups

        for item in sorted(self.backups_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if item.is_file() and (item.suffix.lower() == ".zip" or item.name.endswith(".kurobackup")):
                size = item.stat().st_size
                mtime = item.stat().st_mtime
                manifest_info = None

                # Read manifest from zip header without full extraction
                try:
                    with zipfile.ZipFile(item, "r") as zf:
                        if "manifest.json" in zf.namelist():
                            with zf.open("manifest.json") as mf:
                                manifest_info = json.load(mf)
                except Exception:
                    pass

                backup_type = "manual"
                schema_ver = 13
                if manifest_info:
                    backup_type = manifest_info.get("backup_type", "manual")
                    schema_ver = manifest_info.get("schema_version", 13)
                elif "auto_pre_migration" in item.name:
                    backup_type = "auto_pre_migration"
                elif "auto_pre_restore" in item.name:
                    backup_type = "auto_pre_restore"
                elif "auto" in item.name:
                    backup_type = "auto"

                backups.append({
                    "filename": item.name,
                    "file_size": size,
                    "file_size_formatted": self._format_bytes(size),
                    "created_at": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
                    "mtime": mtime,
                    "backup_type": backup_type,
                    "schema_version": schema_ver,
                    "manifest": manifest_info
                })

        return backups

    def get_backup_path(self, filename: str) -> Optional[Path]:
        """Resolves a backup filename securely, preventing path traversal."""
        clean_name = os.path.basename(filename)
        target = (self.backups_dir / clean_name).resolve()
        if target.is_file() and str(target).startswith(str(self.backups_dir.resolve())):
            return target
        return None

    def delete_backup(self, filename: str) -> bool:
        """Securely deletes a backup file from backups_dir."""
        target = self.get_backup_path(filename)
        if target and target.is_file():
            try:
                target.unlink()
                # Also remove from backup_records table if present
                try:
                    with self.db_manager.get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM backup_records WHERE filename = ?", (target.name,))
                        conn.commit()
                except Exception:
                    pass
                return True
            except Exception as e:
                print(f"[KuroBackup ERROR] Failed to delete backup {target.name}: {e}")
                return False
        return False

    def prune_auto_backups(self, max_count: Optional[int] = None) -> int:
        """
        Prunes older automatic backups, retaining the newest max_count files.
        Keeps manual user backups untouched.
        """
        limit = self.max_auto_backups if max_count is None else max(1, int(max_count))
        auto_backups: List[Tuple[float, Path]] = []

        if not self.backups_dir.is_dir():
            return 0

        for item in self.backups_dir.iterdir():
            if item.is_file() and (item.suffix.lower() == ".zip" or item.name.endswith(".kurobackup")):
                # Check if it's an automatic backup
                is_auto = False
                if "auto" in item.name.lower():
                    is_auto = True
                else:
                    try:
                        with zipfile.ZipFile(item, "r") as zf:
                            if "manifest.json" in zf.namelist():
                                with zf.open("manifest.json") as mf:
                                    m = json.load(mf)
                                    b_type = m.get("backup_type", "")
                                    if "auto" in b_type:
                                        is_auto = True
                    except Exception:
                        pass

                if is_auto:
                    auto_backups.append((item.stat().st_mtime, item))

        # Sort newest first
        auto_backups.sort(key=lambda x: x[0], reverse=True)

        # Remove anything beyond limit
        pruned = 0
        if len(auto_backups) > limit:
            to_remove = auto_backups[limit:]
            for _, path_to_del in to_remove:
                try:
                    path_to_del.unlink()
                    pruned += 1
                except Exception:
                    pass

        return pruned

    def check_database_integrity(self) -> Dict[str, Any]:
        """
        Executes comprehensive database integrity diagnostics:
        - PRAGMA integrity_check
        - PRAGMA quick_check
        - PRAGMA foreign_key_check
        - Table counts and schema version validation
        """
        result = {
            "status": "healthy",
            "integrity_check": "ok",
            "quick_check": "ok",
            "foreign_key_check": "ok",
            "fk_violations": [],
            "schema_version": 13,
            "journal_mode": "wal",
            "tables_count": 0,
            "db_size_bytes": 0,
            "db_size_formatted": "0 B",
            "wal_size_bytes": 0,
            "wal_size_formatted": "0 B",
            "diagnostics": []
        }

        db_path = getattr(self.db_manager, "db_path", self.app_dir / "kuro_database.db")
        if db_path.exists():
            result["db_size_bytes"] = db_path.stat().st_size
            result["db_size_formatted"] = self._format_bytes(result["db_size_bytes"])
        wal_path = Path(str(db_path) + "-wal")
        if wal_path.exists():
            result["wal_size_bytes"] = wal_path.stat().st_size
            result["wal_size_formatted"] = self._format_bytes(result["wal_size_bytes"])

        try:
            with self.db_manager.get_connection() as conn:
                cur = conn.cursor()

                # 1. Journal mode
                try:
                    cur.execute("PRAGMA journal_mode;")
                    jm = cur.fetchone()
                    if jm:
                        result["journal_mode"] = jm[0]
                except Exception:
                    pass

                # 2. Schema version
                try:
                    cur.execute("SELECT MAX(version) FROM schema_migrations")
                    row = cur.fetchone()
                    result["schema_version"] = row[0] if (row and row[0] is not None) else 1
                except Exception:
                    pass

                # 3. Table counts
                try:
                    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
                    result["tables_count"] = cur.fetchone()[0]
                except Exception:
                    pass

                # 4. PRAGMA integrity_check
                try:
                    integ = cur.execute("PRAGMA integrity_check(100);").fetchall()
                    if not integ or integ[0][0] != "ok":
                        result["status"] = "corrupt"
                        result["integrity_check"] = [row[0] for row in integ]
                        result["diagnostics"].append(f"Integrity check failed: {result['integrity_check']}")
                except Exception as e:
                    result["status"] = "corrupt"
                    result["integrity_check"] = str(e)
                    result["diagnostics"].append(f"Integrity check query error: {e}")

                # 5. PRAGMA quick_check
                try:
                    quick = cur.execute("PRAGMA quick_check(100);").fetchall()
                    if not quick or quick[0][0] != "ok":
                        if result["status"] == "healthy":
                            result["status"] = "warning"
                        result["quick_check"] = [row[0] for row in quick]
                except Exception as e:
                    result["quick_check"] = str(e)

                # 6. PRAGMA foreign_key_check
                try:
                    fks = cur.execute("PRAGMA foreign_key_check;").fetchall()
                    if fks:
                        if result["status"] == "healthy":
                            result["status"] = "warning"
                        result["foreign_key_check"] = "violations_found"
                        result["fk_violations"] = [dict(row) if hasattr(row, "keys") else list(row) for row in fks]
                        result["diagnostics"].append(f"Foreign key violations found: {len(fks)}")
                except Exception as e:
                    result["foreign_key_check"] = str(e)

        except Exception as e:
            result["status"] = "corrupt"
            result["diagnostics"].append(f"Database connection error: {e}")

        return result

    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        """Helper to format byte count into readable KB/MB/GB."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
