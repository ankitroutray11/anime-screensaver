"""
Database management & migration module for KuroAnime Screensaver.
Handles WAL mode, migrations, and transactional wallpaper lifecycle operations:
UNSEEN -> RESERVED -> DISPLAYED
"""

import uuid
import sqlite3
import time
import os
import json
import random
import threading
import collections
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

CURRENT_SCHEMA_VERSION = 17

class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
        self.lock = threading.RLock()
        self.write_lock = self.lock
        self._perf_lock = threading.Lock()
        self._is_shutting_down = threading.Event()
        self._active_connections = 0

        # Performance & Reliability Metrics
        self.total_sqlite_ops = 0
        self.total_sqlite_time_ms = 0.0
        self.last_sqlite_latency_ms = 0.0
        self.slow_queries_count = 0
        self._recent_latencies = collections.deque(maxlen=500)

        self.write_ops_count = 0
        self.write_time_ms = 0.0
        self.last_write_latency_ms = 0.0
        self._recent_write_latencies = collections.deque(maxlen=500)

        self.read_ops_count = 0
        self.read_time_ms = 0.0
        self.lock_retries_count = 0
        self.lock_contention_events = 0
        self.rollback_count = 0
        self.transaction_failures = 0
        self._init_db()

    @contextmanager
    def get_connection(self):
        t0 = time.perf_counter()
        with self._perf_lock:
            self._active_connections += 1
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=15.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        try:
            # WAL mode & connection-level reliability pragmas
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 10000;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA cache_size = -64000;")
            yield conn
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self._record_sqlite_latency(duration_ms)
            try:
                conn.close()
            except Exception:
                pass
            with self._perf_lock:
                self._active_connections = max(0, self._active_connections - 1)

    @contextmanager
    def write_transaction(self, retries: int = 5, backoff_base: float = 0.05, busy_timeout_ms: Optional[int] = None):
        """
        Unified SQLite Write Serialization Strategy:
        1. Thread synchronization using self.write_lock (RLock).
        2. Connection with isolation_level=None and BEGIN IMMEDIATE to prevent lock escalation deadlocks.
        3. Automatic retry with exponential backoff on sqlite3.OperationalError('database is locked' / 'busy').
        4. Automatic clean rollback on error (guaranteeing zero partial records).
        5. Detailed write latency, lock retries, and contention metrics.
        """
        if self._is_shutting_down.is_set():
            raise RuntimeError("DatabaseManager is shutting down; writes are rejected.")

        t0 = time.perf_counter()
        with self.write_lock:
            for attempt in range(retries):
                try:
                    with self.get_connection() as conn:
                        if busy_timeout_ms is not None:
                            conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms};")
                        conn.isolation_level = None
                        cur = conn.cursor()
                        cur.execute("BEGIN IMMEDIATE")
                        try:
                            yield conn, cur
                            if conn.in_transaction:
                                cur.execute("COMMIT")
                            dur_ms = (time.perf_counter() - t0) * 1000.0
                            self._record_write_latency(dur_ms)
                            return
                        except Exception:
                            try:
                                if conn.in_transaction:
                                    cur.execute("ROLLBACK")
                            except Exception:
                                pass
                            with self._perf_lock:
                                self.rollback_count += 1
                            raise
                except sqlite3.OperationalError as oe:
                    err_msg = str(oe).lower()
                    if "locked" in err_msg or "busy" in err_msg:
                        with self._perf_lock:
                            self.lock_retries_count += 1
                            self.lock_contention_events += 1
                        if attempt < retries - 1:
                            sleep_s = backoff_base * (2 ** attempt) + random.uniform(0.01, 0.05)
                            time.sleep(sleep_s)
                            continue
                    with self._perf_lock:
                        self.transaction_failures += 1
                    raise
                except Exception:
                    with self._perf_lock:
                        self.transaction_failures += 1
                    raise

    def _record_sqlite_latency(self, duration_ms: float):
        try:
            with self._perf_lock:
                self.total_sqlite_ops += 1
                self.total_sqlite_time_ms += duration_ms
                self.last_sqlite_latency_ms = duration_ms
                self._recent_latencies.append(duration_ms)
                if duration_ms >= 50.0:
                    self.slow_queries_count += 1
        except Exception:
            pass

    def _record_write_latency(self, duration_ms: float):
        try:
            with self._perf_lock:
                self.write_ops_count += 1
                self.write_time_ms += duration_ms
                self.last_write_latency_ms = duration_ms
                self._recent_write_latencies.append(duration_ms)
        except Exception:
            pass

    def get_sqlite_latency_metrics(self) -> Dict[str, Any]:
        with self._perf_lock:
            total_ops = self.total_sqlite_ops
            avg_ms = round(self.total_sqlite_time_ms / total_ops, 2) if total_ops > 0 else 0.0
            last_ms = round(self.last_sqlite_latency_ms, 2)
            slow_count = self.slow_queries_count
            lat_list = sorted(list(self._recent_latencies))
            if lat_list:
                p50_idx = int(len(lat_list) * 0.50)
                p95_idx = int(len(lat_list) * 0.95)
                p99_idx = int(len(lat_list) * 0.99)
                p50_ms = round(lat_list[min(p50_idx, len(lat_list) - 1)], 2)
                p95_ms = round(lat_list[min(p95_idx, len(lat_list) - 1)], 2)
                p99_ms = round(lat_list[min(p99_idx, len(lat_list) - 1)], 2)
                max_ms = round(lat_list[-1], 2)
                min_ms = round(lat_list[0], 2)
            else:
                p50_ms = p95_ms = p99_ms = max_ms = min_ms = 0.0

            write_ops = self.write_ops_count
            write_avg = round(self.write_time_ms / write_ops, 2) if write_ops > 0 else 0.0
            write_lats = sorted(list(self._recent_write_latencies))
            if write_lats:
                w_p95_idx = int(len(write_lats) * 0.95)
                write_p95 = round(write_lats[min(w_p95_idx, len(write_lats) - 1)], 2)
            else:
                write_p95 = 0.0

            err_rate = round((self.transaction_failures / max(1, total_ops)) * 100.0, 3)

            return {
                "total_ops": total_ops,
                "avg_latency_ms": avg_ms,
                "last_latency_ms": last_ms,
                "min_latency_ms": min_ms,
                "p50_latency_ms": p50_ms,
                "p95_latency_ms": p95_ms,
                "p99_latency_ms": p99_ms,
                "max_latency_ms": max_ms,
                "slow_queries_count": slow_count,
                "write_ops": write_ops,
                "write_avg_ms": write_avg,
                "write_p95_ms": write_p95,
                "lock_retries": self.lock_retries_count,
                "lock_contention_events": self.lock_contention_events,
                "rollbacks": self.rollback_count,
                "transaction_failures": self.transaction_failures,
                "error_rate_pct": err_rate
            }

    def reset_sqlite_latency_metrics(self):
        with self._perf_lock:
            self.total_sqlite_ops = 0
            self.total_sqlite_time_ms = 0.0
            self.last_sqlite_latency_ms = 0.0
            self.slow_queries_count = 0
            self._recent_latencies.clear()
            self.write_ops_count = 0
            self.write_time_ms = 0.0
            self.last_write_latency_ms = 0.0
            self._recent_write_latencies.clear()
            self.read_ops_count = 0
            self.read_time_ms = 0.0
            self.lock_retries_count = 0
            self.lock_contention_events = 0
            self.rollback_count = 0
            self.transaction_failures = 0

    def _init_db(self):
        try:
            self._setup_tables()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            print(f"[KuroDB WARNING] Database corruption detected ({e}). Initiating automatic corruption recovery...")
            self.auto_recover_corrupted_database()
            self._setup_tables()

    def auto_recover_corrupted_database(self) -> bool:
        """
        Quarantines a malformed/corrupted database file to a timestamped backup
        and allows clean re-initialization so the application recovers gracefully.
        """
        try:
            import gc
            gc.collect()
            timestamp = int(time.time())
            corrupt_backup = self.db_path.with_suffix(f".corrupt.{timestamp}")
            if self.db_path.is_file():
                try:
                    self.db_path.rename(corrupt_backup)
                except (PermissionError, OSError):
                    import shutil
                    shutil.copyfile(self.db_path, corrupt_backup)
                    with open(self.db_path, "wb") as f:
                        f.write(b"")
            # Also clean wal and shm files
            wal_file = Path(str(self.db_path) + "-wal")
            shm_file = Path(str(self.db_path) + "-shm")
            if wal_file.is_file():
                try:
                    wal_file.rename(self.db_path.with_suffix(f".corrupt.{timestamp}.wal"))
                except (PermissionError, OSError):
                    pass
            if shm_file.is_file():
                try:
                    shm_file.rename(self.db_path.with_suffix(f".corrupt.{timestamp}.shm"))
                except (PermissionError, OSError):
                    pass
            print(f"[KuroDB] Successfully quarantined corrupted database to {corrupt_backup.name}.")
            return True
        except Exception as err:
            print(f"[KuroDB ERROR] Failed to quarantine corrupted database: {err}")
            return False

    def _setup_tables(self):
        with self.get_connection() as conn:
            cur = conn.cursor()
            # Migration tracking table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Legacy tables if this is a fresh setup
            cur.execute("""
                CREATE TABLE IF NOT EXISTS seen_wallpapers (
                    id TEXT PRIMARY KEY,
                    url TEXT,
                    resolution TEXT,
                    mood TEXT,
                    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id TEXT PRIMARY KEY,
                    url TEXT,
                    resolution TEXT,
                    mood TEXT,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        self._run_migrations()

    def _create_pre_migration_backup(self, current_version: int):
        """
        Creates an automatic pre-migration backup before applying database schema upgrades.
        Uses the SQLite Backup API to ensure a consistent, crash-safe snapshot.
        """
        try:
            from backup_manager import BackupManager
            bm = BackupManager(self, app_dir=self.db_path.parent)
            res = bm.export_backup(
                backup_type=f"auto_pre_migration_v{current_version}",
                include_favorites=True,
                include_cache=False,
                custom_note=f"Automatic pre-migration snapshot upgrading from v{current_version} to v{CURRENT_SCHEMA_VERSION}"
            )
            print(f"[KuroDB] Automatic pre-migration backup created: {res.get('filename')}")
        except Exception as e:
            # Fallback to direct sqlite backup if BackupManager encounters any issue
            try:
                backups_dir = self.db_path.parent / "backups"
                backups_dir.mkdir(parents=True, exist_ok=True)
                timestamp_sec = int(time.time())
                dest_db_path = backups_dir / f"auto_pre_migration_v{current_version}_{timestamp_sec}.db"
                with self.get_connection() as src_conn:
                    dest_conn = sqlite3.connect(str(dest_db_path))
                    try:
                        src_conn.backup(dest_conn)
                    finally:
                        dest_conn.close()
                print(f"[KuroDB] Fallback pre-migration backup created: {dest_db_path.name}")
            except Exception as e2:
                print(f"[KuroDB WARNING] Failed to create pre-migration backup: {e2}")

    def _run_migrations(self):
        # 1. Determine current schema version
        current_version = 0
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(version) FROM schema_migrations")
            row = cur.fetchone()
            current_version = row[0] if (row and row[0] is not None) else 0

        # 2. If upgrading an existing initialized database, take automatic pre-migration backup
        if 0 < current_version < CURRENT_SCHEMA_VERSION:
            self._create_pre_migration_backup(current_version)

        # 3. Apply pending migrations
        with self.get_connection() as conn:
            cur = conn.cursor()

            if current_version < 2:
                # Migration 2: Transactional wallpaper lifecycle table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS wallpaper_lifecycle (
                        id TEXT PRIMARY KEY,
                        url TEXT NOT NULL,
                        resolution TEXT,
                        anime TEXT,
                        source TEXT DEFAULT 'Wallhaven',
                        status TEXT NOT NULL CHECK(status IN ('UNSEEN', 'RESERVED', 'DISPLAYED', 'FAILED')),
                        reserved_at REAL,
                        reservation_token TEXT,
                        displayed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_status_anime ON wallpaper_lifecycle(status, anime);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_reserved_at ON wallpaper_lifecycle(reserved_at);")

                # Migrate existing data from seen_wallpapers to wallpaper_lifecycle with DISPLAYED status
                cur.execute("""
                    INSERT OR IGNORE INTO wallpaper_lifecycle (id, url, resolution, anime, status, displayed_at)
                    SELECT id, url, resolution, mood, 'DISPLAYED', seen_at FROM seen_wallpapers
                """)

                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (2)")
                conn.commit()
                print("[KuroDB] Applied Migration v2: Transactional wallpaper lifecycle table with preserved user history.")

            if current_version < 3:
                # Migration 3: Add character and tags metadata support
                cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
                cols = [col[1] for col in cur.fetchall()]
                if "character" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN character TEXT")
                if "tags" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN tags TEXT")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_anime_char ON wallpaper_lifecycle(anime, character)")
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (3)")
                conn.commit()
                print("[KuroDB] Applied Migration v3: Added franchise character & tag metadata columns.")

            if current_version < 4:
                # Migration 4: Offline-first fallback support (local_path, is_cached, level)
                cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
                cols = [col[1] for col in cur.fetchall()]
                if "local_path" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN local_path TEXT")
                if "is_cached" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN is_cached INTEGER DEFAULT 0")
                if "level" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN level INTEGER DEFAULT 1")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_level_status ON wallpaper_lifecycle(level, status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_cached ON wallpaper_lifecycle(is_cached, status)")
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (4)")
                conn.commit()
                print("[KuroDB] Applied Migration v4: Added offline-first local_path, is_cached, and level columns.")

            if current_version < 5:
                # Migration 5: Collections, Advanced Favorites with Download Progress, and Blacklist
                cur.execute("PRAGMA table_info(favorites)")
                fav_cols = [col[1] for col in cur.fetchall()]
                if "character" not in fav_cols:
                    cur.execute("ALTER TABLE favorites ADD COLUMN character TEXT")
                if "source" not in fav_cols:
                    cur.execute("ALTER TABLE favorites ADD COLUMN source TEXT DEFAULT 'Wallhaven'")
                if "file_path" not in fav_cols:
                    cur.execute("ALTER TABLE favorites ADD COLUMN file_path TEXT")
                if "file_size" not in fav_cols:
                    cur.execute("ALTER TABLE favorites ADD COLUMN file_size INTEGER DEFAULT 0")
                if "download_status" not in fav_cols:
                    cur.execute("ALTER TABLE favorites ADD COLUMN download_status TEXT DEFAULT 'pending'")
                if "download_progress" not in fav_cols:
                    cur.execute("ALTER TABLE favorites ADD COLUMN download_progress INTEGER DEFAULT 0")
                if "error_message" not in fav_cols:
                    cur.execute("ALTER TABLE favorites ADD COLUMN error_message TEXT")

                # Collections table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS collections (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Collection items mapping (many-to-many)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS collection_items (
                        collection_id TEXT NOT NULL,
                        wallpaper_id TEXT NOT NULL,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (collection_id, wallpaper_id),
                        FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_collection_items_wp ON collection_items(wallpaper_id)")

                # Blacklist table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS blacklist (
                        wallpaper_id TEXT PRIMARY KEY,
                        url TEXT,
                        anime TEXT,
                        character TEXT,
                        resolution TEXT,
                        reason TEXT DEFAULT 'User excluded',
                        blacklisted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Seed starter collections if empty
                cur.execute("SELECT COUNT(*) FROM collections")
                if cur.fetchone()[0] == 0:
                    cur.execute("INSERT OR IGNORE INTO collections (id, name, description) VALUES ('col_masterpieces', 'Masterpieces', 'Personal showcase of top-tier anime art')")
                    cur.execute("INSERT OR IGNORE INTO collections (id, name, description) VALUES ('col_cinematic_nights', 'Cinematic Nights', 'Dark aesthetic and atmospheric wallpapers')")

                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (5)")
                conn.commit()
                print("[KuroDB] Applied Migration v5: Added Collections, Advanced Favorites, and Blacklist tables.")

            if current_version < 6:
                # Migration 6: Intelligent Recommendation & Personalization Engine
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS recommendation_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                cur.execute("INSERT OR IGNORE INTO recommendation_settings (key, value) VALUES ('personalization_enabled', '1')")
                cur.execute("INSERT OR IGNORE INTO recommendation_settings (key, value) VALUES ('diversity_penalty_enabled', '1')")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS interaction_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        wallpaper_id TEXT,
                        event_type TEXT NOT NULL,
                        anime TEXT,
                        character TEXT,
                        dwell_seconds REAL DEFAULT 0,
                        weight_delta REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_interaction_type ON interaction_events(event_type)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_interaction_anime ON interaction_events(anime)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_interaction_created ON interaction_events(created_at)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS preference_scores (
                        entity_type TEXT NOT NULL,
                        entity_name TEXT NOT NULL,
                        learned_score REAL DEFAULT 0.0,
                        manual_score REAL DEFAULT 0.0,
                        interaction_count INTEGER DEFAULT 0,
                        dwell_total_seconds REAL DEFAULT 0.0,
                        favorites_count INTEGER DEFAULT 0,
                        skips_count INTEGER DEFAULT 0,
                        revisits_count INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (entity_type, entity_name)
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_pref_scores_type ON preference_scores(entity_type)")

                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (6)")
                conn.commit()
                print("[KuroDB] Applied Migration v6: Added Recommendation & Personalization tables.")

            if current_version < 7:
                # Migration 7: Intelligent Artwork Quality Scoring System
                cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
                cols = [col[1] for col in cur.fetchall()]
                if "quality_score" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN quality_score REAL")
                if "technical_score" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN technical_score REAL")
                if "popularity_score" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN popularity_score REAL")
                if "dimension_x" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN dimension_x INTEGER")
                if "dimension_y" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN dimension_y INTEGER")
                if "file_size" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN file_size INTEGER")
                if "views" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN views INTEGER")
                if "favorites" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN favorites INTEGER")
                if "scored_at" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN scored_at TIMESTAMP")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS quality_settings (
                        id INTEGER PRIMARY KEY CHECK(id = 1),
                        min_quality_score REAL DEFAULT 50.0,
                        prefer_native_res INTEGER DEFAULT 1,
                        prefer_aspect_ratio INTEGER DEFAULT 1,
                        avoid_too_dark INTEGER DEFAULT 0,
                        avoid_too_bright INTEGER DEFAULT 1,
                        popularity_weight REAL DEFAULT 0.35,
                        technical_weight REAL DEFAULT 0.65,
                        target_resolution TEXT DEFAULT '1920x1080',
                        target_aspect_ratio TEXT DEFAULT 'landscape',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT OR IGNORE INTO quality_settings (
                        id, min_quality_score, prefer_native_res, prefer_aspect_ratio,
                        avoid_too_dark, avoid_too_bright, popularity_weight, technical_weight,
                        target_resolution, target_aspect_ratio
                    ) VALUES (1, 50.0, 1, 1, 0, 1, 0.35, 0.65, '1920x1080', 'landscape')
                """)

                cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_quality ON wallpaper_lifecycle(status, quality_score)")

                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (7)")
                conn.commit()
                print("[KuroDB] Applied Migration v7: Added Quality Scoring tables and lifecycle columns.")

            if current_version < 8:
                # Migration 8: Intelligent Slideshow Scheduling System
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scheduler_settings (
                        id INTEGER PRIMARY KEY CHECK(id = 1),
                        strategy TEXT DEFAULT 'fixed',
                        fixed_seconds INTEGER DEFAULT 30,
                        random_min INTEGER DEFAULT 15,
                        random_max INTEGER DEFAULT 60,
                        day_seconds INTEGER DEFAULT 25,
                        evening_seconds INTEGER DEFAULT 35,
                        night_seconds INTEGER DEFAULT 60,
                        cinematic_seconds INTEGER DEFAULT 45,
                        dashboard_seconds INTEGER DEFAULT 20,
                        quality_bonus_enabled INTEGER DEFAULT 1,
                        pause_on_hidden INTEGER DEFAULT 1,
                        franchise_rotation_interval INTEGER DEFAULT 5,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT OR IGNORE INTO scheduler_settings (
                        id, strategy, fixed_seconds, random_min, random_max,
                        day_seconds, evening_seconds, night_seconds,
                        cinematic_seconds, dashboard_seconds, quality_bonus_enabled,
                        pause_on_hidden, franchise_rotation_interval
                    ) VALUES (1, 'fixed', 30, 15, 60, 25, 35, 60, 45, 20, 1, 1, 5)
                """)
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (8)")
                conn.commit()
                print("[KuroDB] Applied Migration v8: Added Intelligent Slideshow Scheduling tables and settings.")

            if current_version < 9:
                # Migration 9: Ambient Soundscape Engine
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS soundscape_settings (
                        id INTEGER PRIMARY KEY CHECK(id = 1),
                        enabled INTEGER DEFAULT 0,
                        current_track TEXT DEFAULT 'rain',
                        volume INTEGER DEFAULT 40,
                        muted INTEGER DEFAULT 1,
                        crossfade_seconds REAL DEFAULT 2.5,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT OR IGNORE INTO soundscape_settings (
                        id, enabled, current_track, volume, muted, crossfade_seconds
                    ) VALUES (1, 0, 'rain', 40, 1, 2.5)
                """)
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (9)")
                conn.commit()
                print("[KuroDB] Applied Migration v9: Added Ambient Soundscape tables and settings.")

            if current_version < 10:
                # Migration 10: Intelligent Wallpaper Composition & Focal Point Protection
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS wallpaper_composition (
                        wallpaper_id TEXT PRIMARY KEY,
                        focal_x REAL DEFAULT 50.0,
                        focal_y REAL DEFAULT 50.0,
                        display_mode TEXT DEFAULT 'fill',
                        blurred_background INTEGER DEFAULT 1,
                        landscape_display_mode TEXT DEFAULT NULL,
                        portrait_display_mode TEXT DEFAULT NULL,
                        character_count INTEGER DEFAULT 1,
                        characters_json TEXT DEFAULT '[]',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (wallpaper_id) REFERENCES wallpaper_lifecycle(id) ON DELETE CASCADE
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS composition_settings (
                        id INTEGER PRIMARY KEY CHECK(id = 1),
                        default_mode_landscape TEXT DEFAULT 'fill',
                        default_mode_portrait TEXT DEFAULT 'fit',
                        default_mode_ultrawide TEXT DEFAULT 'fill',
                        blurred_backdrop_enabled INTEGER DEFAULT 1,
                        blur_intensity_px INTEGER DEFAULT 28,
                        backdrop_opacity REAL DEFAULT 0.65,
                        auto_focal_protection INTEGER DEFAULT 1,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT OR IGNORE INTO composition_settings (
                        id, default_mode_landscape, default_mode_portrait, default_mode_ultrawide,
                        blurred_backdrop_enabled, blur_intensity_px, backdrop_opacity, auto_focal_protection
                    ) VALUES (1, 'fill', 'fit', 'fill', 1, 28, 0.65, 1)
                """)
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (10)")
                conn.commit()
                print("[KuroDB] Applied Migration v10: Added Intelligent Wallpaper Composition & Focal Point tables.")

            if current_version < 11:
                # Migration 11: Enhanced Artwork Metadata (uploader, upload_date, source_url)
                cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
                cols = [col[1] for col in cur.fetchall()]
                if "uploader" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN uploader TEXT")
                if "upload_date" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN upload_date TEXT")
                if "source_url" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN source_url TEXT")
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (11)")
                conn.commit()
                print("[KuroDB] Applied Migration v11: Added Artwork Metadata columns (uploader, upload_date, source_url).")

            if current_version < 12:
                # Migration 12: Advanced Anime Ambient Control Center Settings
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS control_center_settings (
                        section TEXT NOT NULL,
                        setting_key TEXT NOT NULL,
                        setting_value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (section, setting_key)
                    )
                """)
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (12)")
                conn.commit()
                print("[KuroDB] Applied Migration v12: Added Advanced Control Center Settings table.")

            if current_version < 13:
                # Migration 13: Backup & Recovery Management
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
                cur.execute("CREATE INDEX IF NOT EXISTS idx_backup_created ON backup_records(created_at)")
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (13)")
                conn.commit()
                print("[KuroDB] Applied Migration v13: Added Backup & Recovery management tables.")

            if current_version < 14:
                # Migration 14: Verified Franchise Tag Intelligence System
                cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
                cols = [col[1] for col in cur.fetchall()]
                if "query_strategy" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN query_strategy TEXT DEFAULT 'verified_tag_id'")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS verified_tag_cache (
                        tag_id INTEGER PRIMARY KEY,
                        tag_name TEXT NOT NULL,
                        category TEXT,
                        purity TEXT,
                        verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        raw_metadata TEXT
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tag_cache_name ON verified_tag_cache(tag_name)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS franchise_catalog (
                        slug TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        catalog_json TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (14)")
                conn.commit()
                print("[KuroDB] Applied Migration v14: Added Verified Franchise Tag Intelligence schema.")

            if current_version < 15:
                # Migration 15: Unified Artwork Safety and Moderation Layer
                cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
                cols = [col[1] for col in cur.fetchall()]
                if "safety_rating" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN safety_rating TEXT DEFAULT 'SAFE'")
                if "safety_reason" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN safety_reason TEXT DEFAULT 'verified_sfw'")
                if "provider_purity_raw" not in cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN provider_purity_raw TEXT")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS blocked_entities (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity_type TEXT NOT NULL,
                        entity_value TEXT NOT NULL,
                        reason TEXT,
                        blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(entity_type, entity_value)
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_blocked_entities_lookup ON blocked_entities(entity_type, entity_value)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS wallpaper_review_queue (
                        id TEXT PRIMARY KEY,
                        wallpaper_json TEXT NOT NULL,
                        failure_reason TEXT NOT NULL,
                        safety_rating TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        reviewed_at TIMESTAMP,
                        review_decision TEXT DEFAULT 'PENDING'
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_review_queue_decision ON wallpaper_review_queue(review_decision)")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS safety_policy_settings (
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        strict_mode INTEGER DEFAULT 1,
                        min_tags_required INTEGER DEFAULT 1,
                        allow_review_queue INTEGER DEFAULT 1,
                        auto_block_reported INTEGER DEFAULT 1,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT OR IGNORE INTO safety_policy_settings (
                        id, strict_mode, min_tags_required, allow_review_queue, auto_block_reported
                    ) VALUES (1, 1, 1, 1, 1)
                """)
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (15)")
                conn.commit()
                print("[KuroDB] Applied Migration v15: Added Unified Artwork Safety and Moderation Layer schema.")

            if current_version < 16:
                # Migration 16: Wallhaven API Compatibility & Contract Engine
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS wallhaven_compatibility_status (
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        status TEXT NOT NULL DEFAULT 'COMPATIBLE',
                        schema_version TEXT DEFAULT 'v1',
                        last_checked_at TIMESTAMP,
                        last_success_at TIMESTAMP,
                        is_live_check INTEGER DEFAULT 0,
                        verified_params_json TEXT DEFAULT '[]',
                        degraded_params_json TEXT DEFAULT '[]',
                        rejected_params_json TEXT DEFAULT '[]',
                        uncertain_params_json TEXT DEFAULT '[]',
                        diagnostics_json TEXT DEFAULT '[]',
                        raw_meta_json TEXT DEFAULT '{}',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT OR IGNORE INTO wallhaven_compatibility_status (
                        id, status, schema_version, last_checked_at, last_success_at, is_live_check,
                        verified_params_json, degraded_params_json, rejected_params_json, uncertain_params_json,
                        diagnostics_json, raw_meta_json
                    ) VALUES (
                        1, 'COMPATIBLE', 'v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0,
                        '["categories", "purity", "sorting", "order", "page", "seed", "ratios", "atleast", "q", "id:", "api_key_auth", "anonymous_pagination", "rate_limiting_429"]',
                        '[]', '[]', '[]', '[]', '{"api_version": "v1", "provider": "Wallhaven"}'
                    )
                """)
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (16)")
                conn.commit()
                print("[KuroDB] Applied Migration v16: Added Wallhaven API Compatibility & Contract Engine schema.")

            if current_version < 17:
                # Migration 17: High-Resolution Animated GIF Support
                cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
                lifecycle_cols = [col[1] for col in cur.fetchall()]
                if "is_animated" not in lifecycle_cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN is_animated INTEGER DEFAULT 0")
                if "media_type" not in lifecycle_cols:
                    cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN media_type TEXT DEFAULT 'static'")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS gif_settings (
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        enabled INTEGER DEFAULT 1,
                        mode TEXT DEFAULT 'all',
                        prefer_hd INTEGER DEFAULT 1,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT OR IGNORE INTO gif_settings (id, enabled, mode, prefer_hd)
                    VALUES (1, 1, 'all', 1)
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_media_type ON wallpaper_lifecycle(status, is_animated, media_type)")
                cur.execute("INSERT OR REPLACE INTO schema_migrations (version) VALUES (17)")
                conn.commit()
                print("[KuroDB] Applied Migration v17: High-Resolution Animated GIF Support schema.")

            # Performance index for fast historical explorer queries
            cur.execute("PRAGMA table_info(wallpaper_lifecycle)")
            cols = [col[1] for col in cur.fetchall()]
            if "displayed_at" not in cols:
                cur.execute("ALTER TABLE wallpaper_lifecycle ADD COLUMN displayed_at TIMESTAMP")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_displayed_at ON wallpaper_lifecycle(status, displayed_at)")
            conn.commit()

        # Index curated local collection if directory exists
        base_dir = self.db_path.parent
        curated_dir = base_dir / "curated_wallpapers"
        if curated_dir.is_dir():
            self.index_curated_collection(curated_dir)

    def recover_abandoned_reservations(self, timeout_seconds: float = 60.0) -> int:
        """
        Recovers reservations that were abandoned due to application crash,
        network dropout, or client timeout, returning them to UNSEEN status.
        """
        threshold = time.time() - timeout_seconds
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET status = 'UNSEEN', reservation_token = NULL, reserved_at = NULL
                WHERE status = 'RESERVED' AND (reserved_at IS NULL OR reserved_at < ?)
            """, (threshold,))
            count = cur.rowcount
            conn.commit()
            if count > 0:
                print(f"[KuroDB] Recovered {count} abandoned wallpaper reservation(s).")
            return count

    def recover_all_reservations_on_startup(self) -> int:
        """
        On application boot, any wallpaper left in RESERVED status from a previous
        abrupt termination is safely restored to UNSEEN.
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET status = 'UNSEEN', reservation_token = NULL, reserved_at = NULL
                WHERE status = 'RESERVED'
            """)
            count = cur.rowcount
            conn.commit()
            if count > 0:
                print(f"[KuroDB] Startup recovery: restored {count} lingering reserved wallpaper(s) to UNSEEN.")
            return count

    def is_known(self, wallpaper_id: str) -> bool:
        """Checks if a wallpaper ID is already in any lifecycle state (UNSEEN, RESERVED, or DISPLAYED)."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM wallpaper_lifecycle WHERE id = ?", (wallpaper_id,))
            return cur.fetchone() is not None

    def is_displayed(self, wallpaper_id: str) -> bool:
        """Checks if a wallpaper ID was ever displayed."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM wallpaper_lifecycle WHERE id = ? AND status = 'DISPLAYED'", (wallpaper_id,))
            return cur.fetchone() is not None

    def mark_wallpaper_cached(self, wallpaper_id: str, local_path: str, level: int = 2) -> bool:
        """Records that a wallpaper file is downloaded locally and ready for offline viewing."""
        with self.write_transaction() as (conn, cur):
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET is_cached = 1, local_path = ?, level = CASE WHEN level = 3 THEN 3 ELSE ? END
                WHERE id = ?
            """, (local_path, level, wallpaper_id))
            return cur.rowcount > 0

    def unmark_wallpaper_cached(self, wallpaper_id: str) -> bool:
        """Removes cached status when a file is evicted by the cache manager."""
        with self.write_transaction() as (conn, cur):
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET is_cached = 0, local_path = NULL, level = CASE WHEN level = 2 THEN 1 ELSE level END
                WHERE id = ?
            """, (wallpaper_id,))
            return cur.rowcount > 0

    def get_wallpaper_url(self, wallpaper_id: str) -> Optional[str]:
        """Returns the verified URL for a wallpaper ID (SSRF defense)."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT url FROM wallpaper_lifecycle WHERE id = ?", (wallpaper_id,))
            row = cur.fetchone()
            return row[0] if row else None

    def get_wallpaper_by_id(self, wallpaper_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves full wallpaper record by ID with attached composition if present."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM wallpaper_lifecycle WHERE id = ?", (wallpaper_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["composition"] = self.get_wallpaper_composition(wallpaper_id)
            return res

    get_wallpaper_details = get_wallpaper_by_id

    def revisit_wallpaper(self, wallpaper_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves historical wallpaper for revisit without modifying its lifecycle status
        or creating duplicate records in wallpaper_lifecycle.
        Only returns artwork that has been DISPLAYED.
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM wallpaper_lifecycle WHERE id = ? AND status = 'DISPLAYED'", (wallpaper_id,))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            res["composition"] = self.get_wallpaper_composition(wallpaper_id)
            return res

    def diagnose_database_integrity(self) -> Dict[str, Any]:
        """
        Deep database integrity checks and actionable corruption diagnostics:
        1. PRAGMA quick_check
        2. PRAGMA integrity_check(100)
        3. PRAGMA foreign_key_check
        4. WAL & SHM physical file inspection (size, presence)
        5. PRAGMA wal_checkpoint(PASSIVE) stats (busy, log pages, checkpointed pages)
        6. PRAGMA user_version and journal_mode verification
        7. Actionable recommendations and status classification ('healthy', 'degraded', 'corrupt')
        """
        status = "healthy"
        issues = []
        recommendations = []

        quick_check_ok = False
        integrity_check_ok = False
        integrity_messages = []
        fk_violations = []
        wal_checkpoint_stats = {"busy": 0, "log_pages": 0, "checkpointed_pages": 0}
        schema_version = 0
        tables_count = 0
        journal_mode = "unknown"

        db_size = 0
        try:
            db_size = self.db_path.stat().st_size
        except OSError:
            db_size = 0

        wal_path = self.db_path.with_name(self.db_path.name + "-wal")
        shm_path = self.db_path.with_name(self.db_path.name + "-shm")

        wal_size = 0
        try:
            wal_size = wal_path.stat().st_size
        except OSError:
            wal_size = 0

        shm_size = 0
        try:
            shm_size = shm_path.stat().st_size
        except OSError:
            shm_size = 0

        try:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # User / Schema version
                cur.execute("SELECT MAX(version) FROM schema_migrations;")
                v_row = cur.fetchone()
                schema_version = v_row[0] if v_row and v_row[0] is not None else 0

                # Table count
                cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                t_row = cur.fetchone()
                tables_count = t_row[0] if t_row else 0

                # Journal mode
                cur.execute("PRAGMA journal_mode;")
                j_row = cur.fetchone()
                journal_mode = str(j_row[0]).lower() if j_row else "unknown"
                if journal_mode != "wal":
                    issues.append(f"Database journal_mode is '{journal_mode}', expected 'wal'")
                    recommendations.append("Execute 'PRAGMA journal_mode = WAL;' to restore high-concurrency WAL mode.")
                    status = "degraded"

                # Quick check
                cur.execute("PRAGMA quick_check;")
                qc_row = cur.fetchone()
                quick_check_ok = bool(qc_row and qc_row[0] == "ok")
                if not quick_check_ok:
                    issues.append(f"PRAGMA quick_check failed: {qc_row[0] if qc_row else 'None'}")
                    status = "corrupt"

                # Integrity check (up to 100 errors)
                cur.execute("PRAGMA integrity_check(100);")
                ic_rows = cur.fetchall()
                if ic_rows and ic_rows[0][0] == "ok" and len(ic_rows) == 1:
                    integrity_check_ok = True
                else:
                    integrity_check_ok = False
                    integrity_messages = [r[0] for r in ic_rows[:20]]
                    issues.append(f"PRAGMA integrity_check reported {len(ic_rows)} error(s): {integrity_messages[:3]}")
                    status = "corrupt"
                    recommendations.append("Database corruption detected. Run auto_recover_corrupted_database() or restore from latest backup.")

                # Foreign key check
                cur.execute("PRAGMA foreign_key_check;")
                fk_rows = cur.fetchall()
                if fk_rows:
                    if status != "corrupt":
                        status = "degraded"
                    for fkr in fk_rows[:25]:
                        fk_violations.append({
                            "table": fkr[0],
                            "rowid": fkr[1],
                            "parent": fkr[2],
                            "fkid": fkr[3]
                        })
                    issues.append(f"Detected {len(fk_rows)} foreign key constraint violation(s).")
                    recommendations.append("Resolve orphaned child records or repair foreign key references.")

                # Passive WAL checkpoint status
                cur.execute("PRAGMA wal_checkpoint(PASSIVE);")
                chk_row = cur.fetchone()
                if chk_row:
                    wal_checkpoint_stats = {
                        "busy": chk_row[0],
                        "log_pages": chk_row[1],
                        "checkpointed_pages": chk_row[2]
                    }
                    if chk_row[0] != 0:
                        issues.append("WAL checkpoint reported BUSY (active readers/writers blocking full checkpoint).")
                        recommendations.append("Ensure background queries and connections are closed properly.")

        except Exception as e:
            status = "corrupt"
            issues.append(f"Diagnostic inspection exception: {str(e)}")
            recommendations.append("Database corruption detected. Run auto_recover_corrupted_database() or restore from latest backup.")
            recommendations.append("Database file may be locked or inaccessible. Verify file permissions and process ownership.")

        # Check for excessive WAL size (>50MB)
        if wal_size > 50 * 1024 * 1024:
            if status == "healthy":
                status = "degraded"
            issues.append(f"WAL file is unusually large ({round(wal_size / (1024 * 1024), 2)} MB).")
            recommendations.append("Run checkpoint_wal('TRUNCATE') to flush and truncate the write-ahead log.")

        metrics = self.get_sqlite_latency_metrics()
        if metrics.get("lock_retries", 0) > 50:
            recommendations.append("Elevated lock retries detected. Verify write transactions are short-lived.")

        return {
            "status": status,
            "healthy": status == "healthy",
            "quick_check": "ok" if quick_check_ok else "failed",
            "integrity_check": "ok" if integrity_check_ok else "failed",
            "integrity_errors": integrity_messages,
            "foreign_key_check": "ok" if not fk_violations else "violations",
            "fk_violations": fk_violations,
            "fk_violations_count": len(fk_violations),
            "schema_version": schema_version,
            "tables_count": tables_count,
            "journal_mode": journal_mode,
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
            "wal_size_bytes": wal_size,
            "wal_size_mb": round(wal_size / (1024 * 1024), 2),
            "shm_size_bytes": shm_size,
            "wal_checkpoint_stats": wal_checkpoint_stats,
            "issues": issues,
            "recommendations": recommendations,
            "metrics": metrics
        }

    def run_integrity_check(self) -> bool:
        """Verifies database file integrity using diagnose_database_integrity."""
        try:
            diag = self.diagnose_database_integrity()
            return bool(diag.get("healthy", False))
        except Exception:
            return False

    def checkpoint_wal(self, mode: str = "TRUNCATE") -> bool:
        """Checkpoints SQLite WAL journal back into main database file on shutdown."""
        try:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(f"PRAGMA wal_checkpoint({mode});")
                return True
        except Exception as e:
            print(f"[KuroDB] WAL checkpoint warning: {e}")
            return False

    def close_and_checkpoint(self, timeout: float = 5.0) -> bool:
        """
        Gracefully drains active transactions and checkpoints WAL on application shutdown:
        1. Sets _is_shutting_down so new write transactions are rejected cleanly.
        2. Waits up to timeout seconds for in-flight database operations to finish.
        3. Acquires write_lock.
        4. Executes PRAGMA wal_checkpoint(TRUNCATE) to merge all journaled pages into
           the main database and truncate the WAL file.
        """
        self._is_shutting_down.set()
        start = time.time()
        while time.time() - start < timeout:
            with self._perf_lock:
                if self._active_connections <= 0:
                    break
            time.sleep(0.05)

        with self.write_lock:
            try:
                conn = sqlite3.connect(str(self.db_path), timeout=timeout)
                try:
                    cur = conn.cursor()
                    cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    row = cur.fetchone()
                    return bool(row and row[0] == 0)
                finally:
                    conn.close()
            except Exception as e:
                print(f"[KuroDB] Error during close_and_checkpoint: {e}")
                return False

    def reopen(self):
        """Resets the shutdown flag to allow operations after a clean checkpoint."""
        self._is_shutting_down.clear()

    def index_curated_collection(self, curated_dir: Path) -> int:
        """
        Indexes curated local wallpapers from curated_wallpapers/ into SQLite as Level 3.
        Supports .svg, .jpg, .jpeg, .png, .webp with companion .json metadata.
        Uses INSERT OR IGNORE so displayed status is preserved across restarts.
        Guarantees zero repeat wallpapers within the curated pool.
        """
        if not curated_dir.is_dir():
            return 0
        added = 0
        supported_exts = {".svg", ".jpg", ".jpeg", ".png", ".webp", ".gif"}
        with self.get_connection() as conn:
            cur = conn.cursor()
            for file_path in sorted(curated_dir.iterdir()):
                if file_path.is_file() and file_path.suffix.lower() in supported_exts:
                    stem = file_path.stem
                    item_id = stem
                    rel_path = f"curated_wallpapers/{file_path.name}"

                    # Read companion JSON if present
                    json_path = curated_dir / f"{stem}.json"
                    meta = {}
                    if json_path.is_file():
                        try:
                            import json
                            with open(json_path, "r", encoding="utf-8") as jf:
                                meta = json.load(jf)
                        except Exception:
                            pass

                    anime = meta.get("anime") or "Curated Anime"
                    character = meta.get("character")
                    resolution = meta.get("resolution") or ("1920x1080" if file_path.suffix.lower() == ".gif" else "3840x2160")
                    tags = json.dumps(meta.get("tags", ["offline", "curated", anime.lower()]))
                    url = f"/api/image/{item_id}"
                    is_gif = 1 if (file_path.suffix.lower() == ".gif" or meta.get("is_animated") or meta.get("media_type") == "gif") else 0
                    m_type = "gif" if is_gif else "static"

                    try:
                        cur.execute("""
                            INSERT INTO wallpaper_lifecycle (
                                id, url, resolution, anime, character, tags, source, status, level, is_cached, local_path,
                                safety_rating, safety_reason, provider_purity_raw, is_animated, media_type
                            ) VALUES (?, ?, ?, ?, ?, ?, 'Curated Offline', 'UNSEEN', 3, 1, ?, 'SAFE', 'curated_offline', 'safe', ?, ?)
                        """, (item_id, url, resolution, anime, character, tags, rel_path, is_gif, m_type))
                        added += 1
                    except sqlite3.IntegrityError:
                        # Ensure level, is_cached, and local_path are set if missing
                        cur.execute("""
                            UPDATE wallpaper_lifecycle
                            SET level = 3, is_cached = 1, local_path = ?,
                                is_animated = COALESCE(is_animated, ?),
                                media_type = COALESCE(media_type, ?),
                                safety_rating = COALESCE(safety_rating, 'SAFE'),
                                safety_reason = COALESCE(safety_reason, 'curated_offline')
                            WHERE id = ? AND (local_path IS NULL OR is_cached != 1)
                        """, (rel_path, is_gif, m_type, item_id))
            conn.commit()
        if added > 0:
            print(f"[KuroDB] Indexed {added} new curated offline artwork(s) into Level 3 pool.")
        return added

    def add_unseen_wallpapers(self, items: List[Dict[str, Any]]) -> int:
        """
        Inserts newly discovered wallpapers into the UNSEEN state.
        Stores anime franchise and character metadata.
        Uses UNIQUE constraint on ID to guarantee zero duplicates.
        """
        added = 0
        with self.write_transaction() as (conn, cur):
            for item in items:
                img_id = item.get("id")
                img_url = item.get("url")
                if not img_id or not img_url:
                    continue
                try:
                    tags_raw = item.get("tags")
                    if isinstance(tags_raw, (list, dict)):
                        tags_val = json.dumps(tags_raw)
                    else:
                        tags_val = str(tags_raw) if tags_raw is not None else None

                    is_anim = 1 if (item.get("is_animated") or str(img_url).lower().endswith(".gif") or item.get("media_type") == "gif") else 0
                    m_type = "gif" if is_anim else item.get("media_type", "static")

                    cur.execute("""
                        INSERT INTO wallpaper_lifecycle (
                            id, url, resolution, anime, character, tags, source, status, level, is_cached, local_path,
                            quality_score, technical_score, popularity_score, dimension_x, dimension_y, file_size, views, favorites, scored_at,
                            uploader, upload_date, source_url, query_strategy,
                            safety_rating, safety_reason, provider_purity_raw, is_animated, media_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'UNSEEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        img_id,
                        img_url,
                        item.get("resolution", "High Res"),
                        item.get("anime", "Popular Anime"),
                        item.get("character"),
                        tags_val,
                        item.get("source", "Wallhaven"),
                        item.get("level", 1),
                        item.get("is_cached", 0),
                        item.get("local_path"),
                        item.get("quality_score"),
                        item.get("technical_score"),
                        item.get("popularity_score"),
                        item.get("dimension_x"),
                        item.get("dimension_y"),
                        item.get("file_size"),
                        item.get("views"),
                        item.get("favorites"),
                        time.strftime("%Y-%m-%d %H:%M:%S") if item.get("quality_score") is not None else None,
                        item.get("uploader"),
                        item.get("upload_date"),
                        item.get("source_url"),
                        item.get("query_strategy", "verified_tag_id"),
                        item.get("safety_rating", "SAFE"),
                        item.get("safety_reason", "verified_sfw"),
                        item.get("provider_purity_raw"),
                        is_anim,
                        m_type
                    ))
                    added += 1
                except sqlite3.IntegrityError:
                    # Update metadata if previously missing
                    cur.execute("""
                        UPDATE wallpaper_lifecycle
                        SET uploader = COALESCE(uploader, ?),
                            upload_date = COALESCE(upload_date, ?),
                            source_url = COALESCE(source_url, ?),
                            file_size = COALESCE(file_size, ?),
                            views = COALESCE(views, ?),
                            favorites = COALESCE(favorites, ?),
                            query_strategy = COALESCE(query_strategy, ?),
                            safety_rating = COALESCE(safety_rating, ?),
                            safety_reason = COALESCE(safety_reason, ?),
                            provider_purity_raw = COALESCE(provider_purity_raw, ?),
                            is_animated = COALESCE(is_animated, ?),
                            media_type = COALESCE(media_type, ?)
                        WHERE id = ?
                    """, (
                        item.get("uploader"),
                        item.get("upload_date"),
                        item.get("source_url"),
                        item.get("file_size"),
                        item.get("views"),
                        item.get("favorites"),
                        item.get("query_strategy"),
                        item.get("safety_rating"),
                        item.get("safety_reason"),
                        item.get("provider_purity_raw"),
                        is_anim,
                        m_type,
                        img_id
                    ))
                    continue
        return added

    def reserve_next_wallpaper(
        self,
        anime: str = "all",
        character: Optional[str] = None,
        selected_franchises: Optional[List[str]] = None,
        excluded_franchises: Optional[List[str]] = None,
        excluded_characters: Optional[List[str]] = None,
        token: str = "",
        ratio: str = "landscape",
        target_level: Optional[int] = None,
        require_cached: bool = False,
        recent_franchises: Optional[List[str]] = None,
        apply_personalization: bool = True,
        min_quality: Optional[float] = None,
        media_type: str = "all"
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically reserves the next available UNSEEN wallpaper.
        Supports:
        - Fallback levels: Level 1 (Live), Level 2 (Local Cache), Level 3 (Curated Offline)
        - Character-specific filtering
        - Franchise-specific filtering
        - Selected-franchises-only mode (multi-franchise filter)
        - Franchise and character exclusions
        - Diversity guard: penalizes recent franchises to prevent repetitive visual clustering
        - Explainable local preference scoring: boosts favorites, dwell time, and manual preferences
        - Prefers higher-resolution artwork matching orientation (4K > 1440p > 1080p, Portrait, Ultrawide)
        - Atomic subquery UPDATE with RETURNING and transaction lock.
        """
        with self.lock:
            with self.get_connection() as conn:
                conn.isolation_level = None
                cur = conn.cursor()
                now = time.time()
                cur.execute("BEGIN IMMEDIATE")
                try:
                    clauses = ["status = 'UNSEEN'"]
                    clauses.append("id NOT IN (SELECT wallpaper_id FROM blacklist)")
                    clauses.append("(safety_rating IS NULL OR safety_rating = 'SAFE')")
                    clauses.append("id NOT IN (SELECT entity_value FROM blocked_entities WHERE entity_type = 'artwork')")
                    params = [token, now]

                    # Target level filter
                    if target_level is not None:
                        clauses.append("level = ?")
                        params.append(target_level)
                    elif require_cached:
                        clauses.append("(is_cached = 1 OR level = 3)")

                    # Franchise filtering
                    if selected_franchises:
                        placeholders = ",".join(["?" for _ in selected_franchises])
                        clauses.append(f"LOWER(anime) IN ({placeholders})")
                        params.extend([f.lower().strip() for f in selected_franchises])
                    elif anime and anime.lower() != "all":
                        clauses.append("LOWER(anime) = LOWER(?)")
                        params.append(anime.strip())

                    # Character filtering
                    if character and character.lower() != "all":
                        clauses.append("LOWER(character) = LOWER(?)")
                        params.append(character.strip())

                    # Franchise exclusions
                    if excluded_franchises:
                        placeholders = ",".join(["?" for _ in excluded_franchises])
                        clauses.append(f"LOWER(anime) NOT IN ({placeholders})")
                        params.extend([f.lower().strip() for f in excluded_franchises])

                    # Character exclusions
                    if excluded_characters:
                        placeholders = ",".join(["?" for _ in excluded_characters])
                        clauses.append(f"(character IS NULL OR LOWER(character) NOT IN ({placeholders}))")
                        params.extend([c.lower().strip() for c in excluded_characters])

                    # Minimum quality filter
                    if min_quality is not None and min_quality > 0:
                        clauses.append("(quality_score IS NULL OR quality_score >= ?)")
                        params.append(min_quality)

                    # Media type filter (Static vs Animated GIF)
                    if media_type == "static":
                        clauses.append("(is_animated = 0 OR is_animated IS NULL)")
                    elif media_type == "gif":
                        clauses.append("(is_animated = 1 OR media_type = 'gif' OR url LIKE '%.gif')")

                    where_sql = " AND ".join(clauses)

                    order_by_terms = []

                    # 1. Diversity Recency Penalty: penalize last 1-3 displayed franchises
                    if recent_franchises and anime == "all" and not selected_franchises:
                        recency_cases = []
                        for rank, rf in enumerate(recent_franchises[:3]):
                            if rf and rf.strip():
                                penalty = 100 - (rank * 30)
                                escaped = rf.lower().strip().replace("'", "''")
                                recency_cases.append(f"WHEN LOWER(anime) = '{escaped}' THEN {penalty}")
                        if recency_cases:
                            order_by_terms.append("CASE " + " ".join(recency_cases) + " ELSE 0 END ASC")

                    # 2. Resolution matching
                    resolution_sql = f"""CASE
                        WHEN '{ratio}' = 'portrait' AND (resolution LIKE '%x1920' OR resolution LIKE '%x2560' OR resolution LIKE '%x3840' OR resolution LIKE '1080x%' OR resolution LIKE '1440x%') THEN 1
                        WHEN '{ratio}' = 'ultrawide' AND (resolution LIKE '3440%' OR resolution LIKE '5120%' OR resolution LIKE '2560x1080') THEN 1
                        WHEN resolution LIKE '3840%' OR resolution LIKE '4096%' THEN 2
                        WHEN resolution LIKE '2560%' THEN 3
                        WHEN resolution LIKE '1920%' THEN 4
                        ELSE 5
                    END ASC"""
                    order_by_terms.append(resolution_sql)

                    # 3. Preference Scoring (Learned + Manual)
                    if apply_personalization:
                        score_sql = """(
                            COALESCE((SELECT learned_score + manual_score FROM preference_scores WHERE entity_type = 'franchise' AND LOWER(entity_name) = LOWER(wallpaper_lifecycle.anime)), 0.0) * 1.0 +
                            COALESCE((SELECT learned_score + manual_score FROM preference_scores WHERE entity_type = 'character' AND character IS NOT NULL AND LOWER(entity_name) = LOWER(wallpaper_lifecycle.character)), 0.0) * 1.5
                        ) DESC"""
                        order_by_terms.append(score_sql)

                    # 4. Intelligent Quality Scoring Order
                    order_by_terms.append("COALESCE(quality_score, 50.0) DESC")

                    order_by_terms.append("created_at ASC")
                    order_by_clause = ",\n                                ".join(order_by_terms)

                    query = f"""
                        UPDATE wallpaper_lifecycle
                        SET status = 'RESERVED', reservation_token = ?, reserved_at = ?
                        WHERE id = (
                            SELECT id FROM wallpaper_lifecycle
                            WHERE {where_sql}
                            ORDER BY
                                {order_by_clause}
                            LIMIT 1
                        )
                        RETURNING id, url, resolution, anime, character, source, level, is_cached, local_path, quality_score, technical_score, popularity_score, dimension_x, dimension_y, file_size, views, favorites, uploader, upload_date, source_url, tags, safety_rating, safety_reason, provider_purity_raw, is_animated, media_type
                    """

                    cur.execute(query, params)
                    row = cur.fetchone()
                    if not row and media_type == "gif":
                        # Auto-recycle displayed gifs so animated GIF playback never halts
                        cur.execute("""
                            UPDATE wallpaper_lifecycle
                            SET status = 'UNSEEN'
                            WHERE (is_animated = 1 OR media_type = 'gif' OR url LIKE '%.gif')
                              AND status = 'DISPLAYED'
                              AND id NOT IN (SELECT wallpaper_id FROM blacklist)
                        """)
                        if cur.rowcount > 0:
                            cur.execute(query, params)
                            row = cur.fetchone()
                    cur.execute("COMMIT")
                    if row:
                        row_id = row[0]
                        raw_url = row[1]
                        row_level = row[6] if len(row) > 6 and row[6] is not None else 1
                        is_cached = row[7] if len(row) > 7 and row[7] is not None else 0
                        local_path = row[8] if len(row) > 8 else None

                        resolved_url = raw_url
                        if local_path or is_cached == 1 or row_level in (2, 3):
                            resolved_url = f"/api/image/{row_id}"

                        comp = self.get_wallpaper_composition(row_id)
                        return {
                            "id": row_id,
                            "url": resolved_url,
                            "raw_url": raw_url,
                            "resolution": row[2],
                            "anime": row[3],
                            "character": row[4],
                            "source": row[5],
                            "level": row_level,
                            "is_cached": is_cached,
                            "local_path": local_path,
                            "quality_score": round(row[9], 1) if len(row) > 9 and row[9] is not None else 50.0,
                            "technical_score": round(row[10], 1) if len(row) > 10 and row[10] is not None else 50.0,
                            "popularity_score": round(row[11], 1) if len(row) > 11 and row[11] is not None else 50.0,
                            "dimension_x": row[12] if len(row) > 12 else None,
                            "dimension_y": row[13] if len(row) > 13 else None,
                            "file_size": row[14] if len(row) > 14 else None,
                            "views": row[15] if len(row) > 15 else None,
                            "favorites": row[16] if len(row) > 16 else None,
                            "uploader": row[17] if len(row) > 17 else None,
                            "upload_date": row[18] if len(row) > 18 else None,
                            "source_url": row[19] if len(row) > 19 else None,
                            "tags": row[20] if len(row) > 20 else None,
                            "safety_rating": row[21] if len(row) > 21 and row[21] is not None else "SAFE",
                            "safety_reason": row[22] if len(row) > 22 and row[22] is not None else "verified_sfw",
                            "provider_purity_raw": row[23] if len(row) > 23 and row[23] is not None else "sfw",
                            "is_animated": bool(row[24]) if len(row) > 24 and row[24] is not None else (1 if raw_url.lower().endswith(".gif") else 0),
                            "media_type": row[25] if len(row) > 25 and row[25] is not None else ("gif" if raw_url.lower().endswith(".gif") else "static"),
                            "composition": comp,
                            "status": "RESERVED",
                            "reservation_token": token
                        }
                    return None
                except Exception:
                    cur.execute("ROLLBACK")
                    raise

    def confirm_displayed(self, wallpaper_id: str, token: str) -> bool:
        """
        Commits a RESERVED wallpaper to DISPLAYED status upon frontend confirmation.
        Ensures wallpaper is permanently marked as displayed.
        """
        with self.write_transaction() as (conn, cur):
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET status = 'DISPLAYED', displayed_at = CURRENT_TIMESTAMP, reservation_token = NULL, reserved_at = NULL
                WHERE id = ? AND status = 'RESERVED' AND reservation_token = ?
            """, (wallpaper_id, token))

            success = cur.rowcount == 1
            if success:
                # Also synchronize legacy seen_wallpapers for backward compatibility
                cur.execute("""
                    INSERT OR IGNORE INTO seen_wallpapers (id, url, resolution, mood, seen_at)
                    SELECT id, url, resolution, anime, CURRENT_TIMESTAMP
                    FROM wallpaper_lifecycle WHERE id = ?
                """, (wallpaper_id,))
            return success

    def mark_display_failed(self, wallpaper_id: str, token: str, error_reason: str = "") -> bool:
        """
        Handles image decoding or network load failure reported by the client.
        Marks as FAILED so it is not immediately re-served or burned.
        """
        with self.write_transaction() as (conn, cur):
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET status = 'FAILED', reservation_token = NULL, reserved_at = NULL
                WHERE id = ? AND status = 'RESERVED' AND reservation_token = ?
            """, (wallpaper_id, token))
            success = cur.rowcount == 1
            if success:
                print(f"[KuroDB] Marked wallpaper {wallpaper_id} as FAILED. Reason: {error_reason}")
            return success

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) as cnt FROM wallpaper_lifecycle GROUP BY status")
            counts = {row["status"]: row["cnt"] for row in cur.fetchall()}
            cur.execute("SELECT COUNT(*) FROM favorites")
            fav_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE is_cached = 1")
            cached_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE level = 3")
            curated_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE level = 3 AND status = 'UNSEEN'")
            curated_unseen = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE is_cached = 1 AND status = 'UNSEEN'")
            cached_unseen = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE (is_animated = 1 OR media_type = 'gif' OR url LIKE '%.gif') AND status = 'UNSEEN'")
            unseen_gifs = cur.fetchone()[0]

            return {
                "unseen_count": counts.get("UNSEEN", 0),
                "unseen_gif_count": unseen_gifs,
                "reserved_count": counts.get("RESERVED", 0),
                "displayed_count": counts.get("DISPLAYED", 0),
                "failed_count": counts.get("FAILED", 0),
                "favorites_count": fav_count,
                "cached_count": cached_count,
                "cached_unseen_count": cached_unseen,
                "curated_count": curated_count,
                "curated_unseen_count": curated_unseen,
                "total_catalog": sum(counts.values())
            }

    def get_unseen_gif_count(self) -> int:
        """Returns the number of unseen animated GIF candidates in the database."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE (is_animated = 1 OR media_type = 'gif' OR url LIKE '%.gif') AND status = 'UNSEEN'")
            row = cur.fetchone()
            return row[0] if row else 0

    def get_recent_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, url, resolution, anime, source, displayed_at
                FROM wallpaper_lifecycle
                WHERE status = 'DISPLAYED'
                ORDER BY displayed_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _compute_similarity_group(item: Dict[str, Any]) -> str:
        """
        Classifies an artwork into a recognizable visual similarity cluster
        based on franchise, aspect ratio framing, character, and quality tier.
        """
        anime = item.get("anime") or "Popular Anime"
        char = item.get("character")
        dim_x = item.get("dimension_x") or 0
        dim_y = item.get("dimension_y") or 0

        aspect = "Landscape"
        if dim_x and dim_y:
            r = dim_x / dim_y
            if r >= 2.0:
                aspect = "Ultrawide"
            elif r <= 0.8:
                aspect = "Portrait"

        q = item.get("quality_score") or 50.0
        if q >= 80:
            tier = "Masterpiece"
        elif q >= 65:
            tier = "High Fidelity"
        else:
            tier = "Standard"

        if char:
            return f"{anime} · {char} ({aspect})"
        return f"{anime} · {aspect} ({tier})"

    def get_wallpaper_history(
        self,
        page: int = 1,
        page_size: int = 24,
        franchise: Optional[str] = None,
        character: Optional[str] = None,
        date_filter: Optional[str] = None,
        resolution: Optional[str] = None,
        favorites_only: bool = False,
        sort_by: str = "newest",
        search_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves paginated, filtered, and sorted historical wallpapers.
        Includes favorite status, similarity group, resolution, and formatted timestamps.
        Blazing fast with SQLite index coverage.
        """
        conditions = ["w.status = 'DISPLAYED'"]
        params: List[Any] = []

        # 1. Search Query
        if search_query and search_query.strip():
            conditions.append("(w.anime LIKE ? OR w.character LIKE ? OR w.id LIKE ? OR w.tags LIKE ?)")
            term = f"%{search_query.strip()}%"
            params.extend([term, term, term, term])

        # 2. Franchise Filter
        if franchise and franchise != "all":
            conditions.append("w.anime = ?")
            params.append(franchise)

        # 3. Character Filter
        if character and character != "all":
            conditions.append("w.character = ?")
            params.append(character)

        # 4. Favorites Only Filter
        if favorites_only:
            conditions.append("f.id IS NOT NULL")

        # 5. Date Filter
        if date_filter and date_filter != "all":
            df = date_filter.lower()
            if df == "today":
                conditions.append("date(w.displayed_at, 'localtime') = date('now', 'localtime')")
            elif df == "yesterday":
                conditions.append("date(w.displayed_at, 'localtime') = date('now', '-1 day', 'localtime')")
            elif df in ["week", "7d", "last7"]:
                conditions.append("w.displayed_at >= datetime('now', '-7 days')")
            elif df in ["month", "30d", "last30"]:
                conditions.append("w.displayed_at >= datetime('now', '-30 days')")

        # 6. Resolution Filter
        if resolution and resolution != "all":
            res_lower = resolution.lower()
            if res_lower in ["4k", "3840x2160"]:
                conditions.append("(w.resolution LIKE '3840%' OR w.dimension_x >= 3840 OR w.dimension_y >= 3840)")
            elif res_lower in ["1440p", "2560x1440"]:
                conditions.append("(w.resolution LIKE '2560%' OR (w.dimension_x >= 2560 AND w.dimension_x < 3840))")
            elif res_lower in ["1080p", "1920x1080"]:
                conditions.append("(w.resolution LIKE '1920%' OR (w.dimension_x >= 1920 AND w.dimension_x < 2560))")
            elif res_lower == "ultrawide":
                conditions.append("((CAST(w.dimension_x AS REAL) / CAST(NULLIF(w.dimension_y, 0) AS REAL) >= 2.0) OR w.resolution LIKE '3440%' OR w.resolution LIKE '2560x1080%' OR w.resolution LIKE '5120x1440%')")
            elif res_lower == "portrait":
                conditions.append("((CAST(w.dimension_x AS REAL) / CAST(NULLIF(w.dimension_y, 0) AS REAL) <= 0.8) OR w.dimension_y > w.dimension_x)")
            else:
                conditions.append("w.resolution LIKE ?")
                params.append(f"%{resolution}%")

        where_clause = " WHERE " + " AND ".join(conditions)

        # Sorting
        if sort_by == "oldest":
            order_sql = "ORDER BY w.displayed_at ASC"
        elif sort_by == "popularity":
            order_sql = "ORDER BY COALESCE(w.favorites, w.popularity_score, 0) DESC, w.displayed_at DESC"
        elif sort_by == "quality":
            order_sql = "ORDER BY COALESCE(w.quality_score, 0) DESC, w.displayed_at DESC"
        else: # "newest"
            order_sql = "ORDER BY w.displayed_at DESC"

        limit = max(1, min(100, int(page_size)))
        offset = max(0, (int(page) - 1) * limit)

        count_sql = f"""
            SELECT COUNT(DISTINCT w.id)
            FROM wallpaper_lifecycle w
            LEFT JOIN favorites f ON w.id = f.id
            {where_clause}
        """

        data_sql = f"""
            SELECT 
                w.id,
                w.url,
                w.resolution,
                w.dimension_x,
                w.dimension_y,
                w.anime,
                w.character,
                w.source,
                w.source_url,
                w.displayed_at,
                w.quality_score,
                w.technical_score,
                w.popularity_score,
                w.views,
                w.favorites AS wallhaven_favorites,
                w.is_cached,
                w.local_path,
                CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END AS is_favorite
            FROM wallpaper_lifecycle w
            LEFT JOIN favorites f ON w.id = f.id
            {where_clause}
            {order_sql}
            LIMIT ? OFFSET ?
        """

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(count_sql, params)
            total_count = cur.fetchone()[0]

            cur.execute(data_sql, params + [limit, offset])
            rows = cur.fetchall()

            # Retrieve distinct displayed franchises for filter dropdown
            cur.execute("SELECT DISTINCT anime FROM wallpaper_lifecycle WHERE status = 'DISPLAYED' AND anime IS NOT NULL ORDER BY anime ASC")
            displayed_franchises = [r[0] for r in cur.fetchall() if r[0]]

            # Total favorites in displayed history
            cur.execute("""
                SELECT COUNT(DISTINCT w.id)
                FROM wallpaper_lifecycle w
                INNER JOIN favorites f ON w.id = f.id
                WHERE w.status = 'DISPLAYED'
            """)
            total_favs_in_history = cur.fetchone()[0]

        items = []
        for r in rows:
            it = dict(r)
            it["similarity_group"] = self._compute_similarity_group(it)
            it["is_favorite"] = bool(it["is_favorite"])
            it["displayed_at_formatted"] = str(it.get("displayed_at") or "")
            if not it.get("source_url") and it.get("id"):
                it["source_url"] = f"https://wallhaven.cc/w/{it['id']}"
            if it.get("is_cached") or it.get("local_path"):
                it["stream_url"] = f"/api/image/{it['id']}"
            else:
                it["stream_url"] = it.get("url") or f"/api/image/{it['id']}"
            items.append(it)

        total_pages = max(1, (total_count + limit - 1) // limit) if total_count > 0 else 1

        return {
            "items": items,
            "total": total_count,
            "page": int(page),
            "page_size": limit,
            "total_pages": total_pages,
            "has_more": int(page) < total_pages,
            "franchises": displayed_franchises,
            "stats": {
                "total_displayed": total_count,
                "total_favorites": total_favs_in_history
            }
        }

    def export_wallpaper_history(
        self,
        export_format: str = "json",
        franchise: Optional[str] = None,
        character: Optional[str] = None,
        date_filter: Optional[str] = None,
        resolution: Optional[str] = None,
        favorites_only: bool = False,
        search_query: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Exports complete history metadata matching filters in JSON or RFC 4180 CSV format.
        """
        res = self.get_wallpaper_history(
            page=1,
            page_size=10000,
            franchise=franchise,
            character=character,
            date_filter=date_filter,
            resolution=resolution,
            favorites_only=favorites_only,
            search_query=search_query
        )
        items = res.get("items", [])

        if export_format.lower() == "csv":
            import io
            import csv
            output = io.StringIO()
            fieldnames = [
                "id", "displayed_at", "anime", "character", "resolution",
                "dimension_x", "dimension_y", "is_favorite", "quality_score",
                "technical_score", "popularity_score", "views", "wallhaven_favorites",
                "similarity_group", "source_url"
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for it in items:
                writer.writerow(it)
            return output.getvalue(), "text/csv; charset=utf-8"
        else:
            export_payload = {
                "application": "Kuro Anime Screensaver",
                "export_type": "wallpaper_history_metadata",
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "total_records": len(items),
                "filters_applied": {
                    "franchise": franchise or "all",
                    "character": character or "all",
                    "date_filter": date_filter or "all",
                    "resolution": resolution or "all",
                    "favorites_only": favorites_only,
                    "search_query": search_query or ""
                },
                "history": items
            }
            return json.dumps(export_payload, indent=2), "application/json; charset=utf-8"

    def reset_history(self) -> bool:
        """Resets displayed and reserved wallpapers back to UNSEEN."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE wallpaper_lifecycle SET status = 'UNSEEN', reservation_token = NULL, reserved_at = NULL, displayed_at = NULL")
            cur.execute("DELETE FROM seen_wallpapers")
            conn.commit()
            return True


    # -------------------------------------------------------------
    # FAVORITES MANAGEMENT
    # -------------------------------------------------------------
    def add_favorite(self, item: Dict[str, Any]) -> bool:
        """
        Adds or updates a favorite wallpaper in the database.
        Includes metadata, download status, and progress tracking.
        """
        wallpaper_id = item.get("id")
        url = item.get("url")
        if not wallpaper_id or not url:
            return False

        resolution = item.get("resolution", "")
        mood = item.get("anime") or item.get("mood", "Anime")
        character = item.get("character")
        source = item.get("source", "Wallhaven")
        file_path = item.get("file_path")
        file_size = item.get("file_size", 0)
        status = item.get("download_status", "pending")
        progress = item.get("download_progress", 0)
        error_msg = item.get("error_message")

        with self.write_transaction() as (conn, cur):
            cur.execute("""
                INSERT INTO favorites (
                    id, url, resolution, mood, character, source,
                    file_path, file_size, download_status, download_progress, error_message, saved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    url = excluded.url,
                    resolution = COALESCE(excluded.resolution, favorites.resolution),
                    mood = COALESCE(excluded.mood, favorites.mood),
                    character = COALESCE(excluded.character, favorites.character),
                    source = COALESCE(excluded.source, favorites.source),
                    file_path = COALESCE(excluded.file_path, favorites.file_path),
                    file_size = CASE WHEN excluded.file_size > 0 THEN excluded.file_size ELSE favorites.file_size END,
                    download_status = CASE WHEN favorites.download_status = 'completed' AND excluded.download_status != 'completed' THEN favorites.download_status ELSE excluded.download_status END,
                    download_progress = CASE WHEN favorites.download_status = 'completed' THEN 100 ELSE excluded.download_progress END
            """, (wallpaper_id, url, resolution, mood, character, source, file_path, file_size, status, progress, error_msg))
            return True


    def update_favorite_download(
        self,
        wallpaper_id: str,
        status: str,
        progress: int = 100,
        file_path: Optional[str] = None,
        file_size: int = 0,
        error_message: Optional[str] = None
    ) -> bool:
        """Updates download status, progress, and local file path for a favorite."""
        with self.write_transaction() as (conn, cur):
            cur.execute("""
                UPDATE favorites
                SET download_status = ?,
                    download_progress = ?,
                    file_path = COALESCE(?, file_path),
                    file_size = CASE WHEN ? > 0 THEN ? ELSE file_size END,
                    error_message = ?
                WHERE id = ?
            """, (status, progress, file_path, file_size, file_size, error_message, wallpaper_id))
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT OR IGNORE INTO favorites (id, url, download_status, download_progress, file_path, file_size, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (wallpaper_id, file_path or "", status, progress, file_path, file_size, error_message))
            return cur.rowcount > 0

    def remove_favorite(self, wallpaper_id: str) -> Optional[str]:
        """
        Removes a wallpaper from favorites and returns its local file_path (if any)
        so the caller can delete the physical file.
        """
        file_path = None
        with self.write_transaction() as (conn, cur):
            cur.execute("SELECT file_path FROM favorites WHERE id = ?", (wallpaper_id,))
            row = cur.fetchone()
            if row:
                file_path = row[0]
            cur.execute("DELETE FROM favorites WHERE id = ?", (wallpaper_id,))
        return file_path

    def get_favorites(
        self,
        franchise: Optional[str] = None,
        resolution: Optional[str] = None,
        character: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves favorites with optional franchise, resolution, character, and text search filters.
        """
        clauses = []
        params = []

        if franchise and franchise.lower() != "all":
            clauses.append("LOWER(mood) = LOWER(?)")
            params.append(franchise.strip())

        if resolution and resolution.lower() != "all":
            clauses.append("resolution = ?")
            params.append(resolution.strip())

        if character and character.lower() != "all":
            clauses.append("LOWER(character) = LOWER(?)")
            params.append(character.strip())

        if search and search.strip():
            kw = f"%{search.strip().lower()}%"
            clauses.append("(LOWER(id) LIKE ? OR LOWER(mood) LIKE ? OR LOWER(character) LIKE ? OR LOWER(source) LIKE ?)")
            params.extend([kw, kw, kw, kw])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT id, url, resolution, mood as anime, character, source,
                   file_path, file_size, download_status, download_progress, error_message, saved_at
            FROM favorites
            {where_sql}
            ORDER BY saved_at DESC
        """

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def get_favorite_by_id(self, wallpaper_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, url, resolution, mood as anime, character, source,
                       file_path, file_size, download_status, download_progress, error_message, saved_at
                FROM favorites WHERE id = ?
            """, (wallpaper_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def is_favorite(self, wallpaper_id: str) -> bool:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM favorites WHERE id = ?", (wallpaper_id,))
            return cur.fetchone() is not None

    # -------------------------------------------------------------
    # COLLECTIONS MANAGEMENT
    # -------------------------------------------------------------
    def create_collection(self, name: str, description: str = "") -> Dict[str, Any]:
        """Creates a new custom collection."""
        col_id = f"col_{uuid.uuid4().hex[:10]}"
        clean_name = name.strip()
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO collections (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (col_id, clean_name, description.strip()))
            conn.commit()
        return {
            "id": col_id,
            "name": clean_name,
            "description": description.strip(),
            "item_count": 0
        }

    def rename_collection(self, collection_id: str, new_name: str, new_description: Optional[str] = None) -> bool:
        """Renames a custom collection and optionally updates description."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            if new_description is not None:
                cur.execute("""
                    UPDATE collections
                    SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_name.strip(), new_description.strip(), collection_id))
            else:
                cur.execute("""
                    UPDATE collections
                    SET name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_name.strip(), collection_id))
            success = cur.rowcount > 0
            conn.commit()
            return success

    def delete_collection(self, collection_id: str) -> bool:
        """Deletes a collection and its item associations."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM collection_items WHERE collection_id = ?", (collection_id,))
            cur.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            success = cur.rowcount > 0
            conn.commit()
            return success

    def get_collections(self) -> List[Dict[str, Any]]:
        """Lists all collections with item count and sample cover thumbnail."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.id, c.name, c.description, c.created_at, c.updated_at,
                       COUNT(ci.wallpaper_id) as item_count,
                       (
                           SELECT COALESCE(wl.local_path, wl.url, fav.url)
                           FROM collection_items ci2
                           LEFT JOIN wallpaper_lifecycle wl ON ci2.wallpaper_id = wl.id
                           LEFT JOIN favorites fav ON ci2.wallpaper_id = fav.id
                           WHERE ci2.collection_id = c.id
                           LIMIT 1
                       ) as cover_url
                FROM collections c
                LEFT JOIN collection_items ci ON c.id = ci.collection_id
                GROUP BY c.id
                ORDER BY c.created_at ASC
            """)
            return [dict(row) for row in cur.fetchall()]

    def add_to_collection(self, collection_id: str, wallpaper_id: str) -> bool:
        """Adds a wallpaper to a collection."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO collection_items (collection_id, wallpaper_id, added_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (collection_id, wallpaper_id))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Already in collection
                return True

    def remove_from_collection(self, collection_id: str, wallpaper_id: str) -> bool:
        """Removes a wallpaper from a collection."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM collection_items
                WHERE collection_id = ? AND wallpaper_id = ?
            """, (collection_id, wallpaper_id))
            success = cur.rowcount > 0
            conn.commit()
            return success

    def get_collection_wallpapers(
        self,
        collection_id: str,
        franchise: Optional[str] = None,
        resolution: Optional[str] = None,
        character: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all wallpapers in a specific collection, joined with wallpaper metadata,
        and filtered by franchise, resolution, character, or keyword.
        """
        clauses = ["ci.collection_id = ?"]
        params = [collection_id]

        if franchise and franchise.lower() != "all":
            clauses.append("(LOWER(COALESCE(wl.anime, fav.mood)) = LOWER(?))")
            params.append(franchise.strip())

        if resolution and resolution.lower() != "all":
            clauses.append("(COALESCE(wl.resolution, fav.resolution) = ?)")
            params.append(resolution.strip())

        if character and character.lower() != "all":
            clauses.append("(LOWER(COALESCE(wl.character, fav.character)) = LOWER(?))")
            params.append(character.strip())

        if search and search.strip():
            kw = f"%{search.strip().lower()}%"
            clauses.append("""(
                LOWER(ci.wallpaper_id) LIKE ? OR
                LOWER(COALESCE(wl.anime, fav.mood, '')) LIKE ? OR
                LOWER(COALESCE(wl.character, fav.character, '')) LIKE ?
            )""")
            params.extend([kw, kw, kw])

        where_sql = " AND ".join(clauses)
        query = f"""
            SELECT
                ci.wallpaper_id as id,
                COALESCE(wl.url, fav.url) as url,
                COALESCE(wl.resolution, fav.resolution) as resolution,
                COALESCE(wl.anime, fav.mood) as anime,
                COALESCE(wl.character, fav.character) as character,
                COALESCE(wl.source, fav.source, 'Unknown') as source,
                COALESCE(wl.level, 1) as level,
                COALESCE(wl.is_cached, 0) as is_cached,
                COALESCE(wl.local_path, fav.file_path) as local_path,
                fav.download_status,
                fav.download_progress,
                ci.added_at
            FROM collection_items ci
            LEFT JOIN wallpaper_lifecycle wl ON ci.wallpaper_id = wl.id
            LEFT JOIN favorites fav ON ci.wallpaper_id = fav.id
            WHERE {where_sql}
            ORDER BY ci.added_at DESC
        """

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    # -------------------------------------------------------------
    # WALLPAPER BLACKLIST MANAGEMENT
    # -------------------------------------------------------------
    def add_to_blacklist(self, wallpaper_id: str, reason: str = "User excluded") -> bool:
        """
        Permanently blacklists a wallpaper so it is NEVER reserved or prefetched again.
        Cancels any active reservation in wallpaper_lifecycle.
        """
        with self.write_transaction() as (conn, cur):
            # Lookup metadata from lifecycle or favorites
            cur.execute("""
                SELECT url, anime, character, resolution FROM wallpaper_lifecycle WHERE id = ?
                UNION
                SELECT url, mood as anime, character, resolution FROM favorites WHERE id = ?
                LIMIT 1
            """, (wallpaper_id, wallpaper_id))
            row = cur.fetchone()
            url = row[0] if row else None
            anime = row[1] if row else None
            character = row[2] if row else None
            resolution = row[3] if row else None

            cur.execute("""
                INSERT OR REPLACE INTO blacklist (wallpaper_id, url, anime, character, resolution, reason, blacklisted_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (wallpaper_id, url, anime, character, resolution, reason))

            # Cancel reservation if currently reserved
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET status = 'FAILED', reservation_token = NULL, reserved_at = NULL
                WHERE id = ? AND status = 'RESERVED'
            """, (wallpaper_id,))
            return True


    def restore_from_blacklist(self, wallpaper_id: str) -> bool:
        """
        Restores a blacklisted wallpaper, allowing it to re-enter circulation as UNSEEN
        (unless it was already displayed).
        """
        with self.write_transaction() as (conn, cur):
            cur.execute("DELETE FROM blacklist WHERE wallpaper_id = ?", (wallpaper_id,))
            deleted = cur.rowcount > 0
            if deleted:
                # If was not displayed, reset to UNSEEN
                cur.execute("""
                    UPDATE wallpaper_lifecycle
                    SET status = 'UNSEEN', reservation_token = NULL, reserved_at = NULL
                    WHERE id = ? AND status != 'DISPLAYED'
                """, (wallpaper_id,))
            return deleted

    def get_blacklist(self) -> List[Dict[str, Any]]:
        """Returns all blacklisted wallpapers."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT wallpaper_id as id, url, anime, character, resolution, reason, blacklisted_at
                FROM blacklist
                ORDER BY blacklisted_at DESC
            """)
            return [dict(row) for row in cur.fetchall()]

    def is_blacklisted(self, wallpaper_id: str) -> bool:
        """Checks if a wallpaper ID is blacklisted."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM blacklist WHERE wallpaper_id = ?", (wallpaper_id,))
            return cur.fetchone() is not None

    # -------------------------------------------------------------
    # LIBRARY STATISTICS & STORAGE UTILIZATION
    # -------------------------------------------------------------
    def get_library_stats(self, base_dir: Optional[Path] = None) -> Dict[str, Any]:
        """
        Computes aggregate statistics:
        - Total unique wallpapers displayed
        - Total favorites saved
        - Total custom collections
        - Total blacklisted items
        - Total distinct franchises explored
        - Disk storage metrics (favorites & cache breakdown)
        """
        root_dir = base_dir or self.db_path.parent
        fav_dir = root_dir / "favorites"
        cache_dir = root_dir / ".cache" / "wallpapers"

        def _dir_usage(d: Path) -> Tuple[int, int]:
            size = 0
            count = 0
            if d.is_dir():
                try:
                    for entry in os.scandir(str(d)):
                        if entry.is_file() and not entry.name.endswith(".tmp"):
                            try:
                                size += entry.stat().st_size
                                count += 1
                            except OSError:
                                pass
                except Exception:
                    pass
            return size, count

        fav_bytes, fav_files = _dir_usage(fav_dir)
        cache_bytes, cache_files = _dir_usage(cache_dir)
        total_storage_bytes = fav_bytes + cache_bytes

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE status = 'DISPLAYED'")
            displayed_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM favorites")
            favorites_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM collections")
            collections_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM blacklist")
            blacklist_count = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(DISTINCT LOWER(anime))
                FROM wallpaper_lifecycle
                WHERE status = 'DISPLAYED' AND anime IS NOT NULL AND anime != ''
            """)
            franchises_explored = cur.fetchone()[0]

            # Cache utilization: 500MB max limit by default
            max_cache_bytes = 500 * 1024 * 1024
            cache_percent = round((cache_bytes / max_cache_bytes) * 100, 1) if max_cache_bytes > 0 else 0

            return {
                "total_displayed": displayed_count,
                "total_favorites": favorites_count,
                "total_collections": collections_count,
                "total_blacklisted": blacklist_count,
                "franchises_explored": franchises_explored,
                "storage": {
                    "favorites_bytes": fav_bytes,
                    "favorites_mb": round(fav_bytes / (1024 * 1024), 2),
                    "favorites_files": fav_files,
                    "cache_bytes": cache_bytes,
                    "cache_mb": round(cache_bytes / (1024 * 1024), 2),
                    "cache_files": cache_files,
                    "total_bytes": total_storage_bytes,
                    "total_mb": round(total_storage_bytes / (1024 * 1024), 2),
                    "total_gb": round(total_storage_bytes / (1024 * 1024 * 1024), 3)
                },
                "cache_utilization": {
                    "used_bytes": cache_bytes,
                    "used_mb": round(cache_bytes / (1024 * 1024), 2),
                    "max_bytes": max_cache_bytes,
                    "max_mb": round(max_cache_bytes / (1024 * 1024), 2),
                    "percent": min(cache_percent, 100.0),
                    "file_count": cache_files
                }
            }

    # =========================================================================
    # RECOMMENDATION & PERSONALIZATION ENGINE (MIGRATION v6)
    # =========================================================================

    def is_personalization_enabled(self) -> bool:
        """Checks if local recommendation & personalization engine is active."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM recommendation_settings WHERE key = 'personalization_enabled'")
            row = cur.fetchone()
            return bool(row and row[0] == "1")

    def set_personalization_enabled(self, enabled: bool) -> bool:
        """Toggles personalization on or off."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO recommendation_settings (key, value)
                VALUES ('personalization_enabled', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, ("1" if enabled else "0",))
            conn.commit()
            return True


    def is_diversity_penalty_enabled(self) -> bool:
        """Checks if recency diversity penalty is enabled to avoid repeating similar art."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM recommendation_settings WHERE key = 'diversity_penalty_enabled'")
            row = cur.fetchone()
            return bool(row and row[0] == "1")

    def set_diversity_penalty_enabled(self, enabled: bool) -> bool:
        """Toggles recency diversity guard on or off."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO recommendation_settings (key, value)
                VALUES ('diversity_penalty_enabled', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, ("1" if enabled else "0",))
            conn.commit()
            return True


    def record_interaction_event(
        self,
        wallpaper_id: Optional[str],
        event_type: str,
        anime: Optional[str] = None,
        character: Optional[str] = None,
        dwell_seconds: float = 0.0,
        weight_delta: float = 0.0
    ) -> int:
        """Logs an explainable interaction event for preference learning."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO interaction_events
                    (wallpaper_id, event_type, anime, character, dwell_seconds, weight_delta)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (wallpaper_id, event_type, anime, character, dwell_seconds, weight_delta))
            event_id = cur.lastrowid
            conn.commit()
            return event_id

    def update_entity_preference(
        self,
        entity_type: str,
        entity_name: str,
        delta: float,
        event_type: str,
        dwell_seconds: float = 0.0
    ) -> None:
        """
        Updates learned score and interaction metrics for a franchise or character.
        Clamps learned_score within [-50.0, +100.0] for stability.
        """
        if not entity_name or not entity_name.strip():
            return
        clean_name = entity_name.strip()
        is_fav = 1 if event_type in ("favorite", "favorite_add") else 0
        is_skip = 1 if event_type in ("skip", "skipped") else 0
        is_revisit = 1 if event_type in ("revisit", "manual_revisit") else 0

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO preference_scores (
                    entity_type, entity_name, learned_score, manual_score,
                    interaction_count, dwell_total_seconds,
                    favorites_count, skips_count, revisits_count, updated_at
                ) VALUES (
                    ?, ?, MAX(-50.0, MIN(100.0, ?)), 0.0,
                    1, ?,
                    ?, ?, ?, CURRENT_TIMESTAMP
                )
                ON CONFLICT(entity_type, entity_name) DO UPDATE SET
                    learned_score = MAX(-50.0, MIN(100.0, preference_scores.learned_score + ?)),
                    interaction_count = preference_scores.interaction_count + 1,
                    dwell_total_seconds = preference_scores.dwell_total_seconds + ?,
                    favorites_count = preference_scores.favorites_count + ?,
                    skips_count = preference_scores.skips_count + ?,
                    revisits_count = preference_scores.revisits_count + ?,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                entity_type, clean_name, delta,
                dwell_seconds, is_fav, is_skip, is_revisit,
                delta, dwell_seconds, is_fav, is_skip, is_revisit
            ))
            conn.commit()

    def set_manual_entity_preference(
        self,
        entity_type: str,
        entity_name: str,
        manual_score: float
    ) -> bool:
        """Allows user to manually bias or override preference scores for a franchise or character."""
        if not entity_name or not entity_name.strip():
            return False
        clean_name = entity_name.strip()
        clamped_score = max(-50.0, min(100.0, float(manual_score)))

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO preference_scores (
                    entity_type, entity_name, learned_score, manual_score,
                    interaction_count, dwell_total_seconds,
                    favorites_count, skips_count, revisits_count, updated_at
                ) VALUES (
                    ?, ?, 0.0, ?,
                    0, 0.0,
                    0, 0, 0, CURRENT_TIMESTAMP
                )
                ON CONFLICT(entity_type, entity_name) DO UPDATE SET
                    manual_score = ?,
                    updated_at = CURRENT_TIMESTAMP
            """, (entity_type, clean_name, clamped_score, clamped_score))
            conn.commit()
            return True


    def get_preference_scores(
        self,
        entity_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Returns sorted preference scores with transparent metrics breakdown."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            if entity_type:
                cur.execute("""
                    SELECT entity_type, entity_name, learned_score, manual_score,
                           (learned_score + manual_score) as total_score,
                           interaction_count, dwell_total_seconds,
                           favorites_count, skips_count, revisits_count, updated_at
                    FROM preference_scores
                    WHERE entity_type = ?
                    ORDER BY total_score DESC, interaction_count DESC
                    LIMIT ?
                """, (entity_type, limit))
            else:
                cur.execute("""
                    SELECT entity_type, entity_name, learned_score, manual_score,
                           (learned_score + manual_score) as total_score,
                           interaction_count, dwell_total_seconds,
                           favorites_count, skips_count, revisits_count, updated_at
                    FROM preference_scores
                    ORDER BY total_score DESC, interaction_count DESC
                    LIMIT ?
                """, (limit,))
            rows = cur.fetchall()
            return [
                {
                    "entity_type": r[0],
                    "entity_name": r[1],
                    "learned_score": round(r[2], 2),
                    "manual_score": round(r[3], 2),
                    "total_score": round(r[4], 2),
                    "interaction_count": r[5],
                    "dwell_total_seconds": round(r[6], 1),
                    "favorites_count": r[7],
                    "skips_count": r[8],
                    "revisits_count": r[9],
                    "updated_at": r[10]
                }
                for r in rows
            ]

    def reset_personalization_data(self) -> bool:
        """
        Resets all learned preference scores and interaction logs back to neutral.
        Preserves the wallpaper lifecycle, seen history, favorites, and collections.
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM interaction_events")
            cur.execute("DELETE FROM preference_scores")
            cur.execute("INSERT OR REPLACE INTO recommendation_settings (key, value) VALUES ('personalization_enabled', '1')")
            cur.execute("INSERT OR REPLACE INTO recommendation_settings (key, value) VALUES ('diversity_penalty_enabled', '1')")
            conn.commit()
            return True


    def get_recent_displayed_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns the most recently displayed wallpapers for diversity checking and UI history."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, url, resolution, anime, character, source, level, displayed_at
                FROM wallpaper_lifecycle
                WHERE status = 'DISPLAYED'
                ORDER BY displayed_at DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "url": r[1],
                    "resolution": r[2],
                    "anime": r[3],
                    "character": r[4],
                    "source": r[5],
                    "level": r[6],
                    "displayed_at": r[7]
                }
                for r in rows
            ]

    def get_personalization_profile(self) -> Dict[str, Any]:
        """Provides a comprehensive, explainable profile of the user's learned artwork tastes."""
        enabled = self.is_personalization_enabled()
        diversity = self.is_diversity_penalty_enabled()

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM interaction_events")
            total_events = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*), COALESCE(SUM(dwell_seconds), 0) FROM interaction_events WHERE event_type LIKE '%dwell%'")
            dwell_row = cur.fetchone()
            total_dwell_events = dwell_row[0]
            total_dwell_sec = dwell_row[1]

            cur.execute("SELECT COUNT(*) FROM interaction_events WHERE event_type LIKE '%skip%'")
            total_skips = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM interaction_events WHERE event_type LIKE '%revisit%'")
            total_revisits = cur.fetchone()[0]

        top_franchises = self.get_preference_scores(entity_type="franchise", limit=8)
        top_characters = self.get_preference_scores(entity_type="character", limit=8)

        # Separate positive affinity vs negative suppressed
        positive_franchises = [f for f in top_franchises if f["total_score"] > 0]
        negative_franchises = [f for f in top_franchises if f["total_score"] < 0]

        return {
            "enabled": enabled,
            "diversity_penalty_enabled": diversity,
            "total_interaction_events": total_events,
            "stats": {
                "dwell_sessions": total_dwell_events,
                "total_dwell_seconds": round(total_dwell_sec, 1),
                "total_dwell_minutes": round(total_dwell_sec / 60.0, 1),
                "total_skips": total_skips,
                "total_revisits": total_revisits
            },
            "top_franchises": positive_franchises,
            "suppressed_franchises": negative_franchises,
            "top_characters": top_characters
        }

    # =========================================================================
    # ARTWORK QUALITY SCORING ENGINE (MIGRATION v7)
    # =========================================================================

    def get_quality_settings(self) -> Dict[str, Any]:
        """Retrieves active quality scoring thresholds and weight configurations."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT min_quality_score, prefer_native_res, prefer_aspect_ratio,
                       avoid_too_dark, avoid_too_bright, popularity_weight, technical_weight,
                       target_resolution, target_aspect_ratio, updated_at
                FROM quality_settings WHERE id = 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    "min_quality_score": float(row[0]),
                    "prefer_native_res": bool(row[1]),
                    "prefer_aspect_ratio": bool(row[2]),
                    "avoid_too_dark": bool(row[3]),
                    "avoid_too_bright": bool(row[4]),
                    "popularity_weight": float(row[5]),
                    "technical_weight": float(row[6]),
                    "target_resolution": str(row[7]),
                    "target_aspect_ratio": str(row[8]),
                    "updated_at": str(row[9])
                }
            return {
                "min_quality_score": 50.0,
                "prefer_native_res": True,
                "prefer_aspect_ratio": True,
                "avoid_too_dark": False,
                "avoid_too_bright": True,
                "popularity_weight": 0.35,
                "technical_weight": 0.65,
                "target_resolution": "1920x1080",
                "target_aspect_ratio": "landscape",
                "updated_at": None
            }

    def update_quality_settings(self, settings: Dict[str, Any]) -> bool:
        """Updates quality scoring criteria and persists to quality_settings table."""
        current = self.get_quality_settings()
        min_q = float(settings.get("min_quality_score", current["min_quality_score"]))
        pref_res = int(settings.get("prefer_native_res", current["prefer_native_res"]))
        pref_ratio = int(settings.get("prefer_aspect_ratio", current["prefer_aspect_ratio"]))
        avoid_dark = int(settings.get("avoid_too_dark", current["avoid_too_dark"]))
        avoid_bright = int(settings.get("avoid_too_bright", current["avoid_too_bright"]))
        pop_w = float(settings.get("popularity_weight", current["popularity_weight"]))
        tech_w = float(settings.get("technical_weight", current["technical_weight"]))
        t_res = str(settings.get("target_resolution", current["target_resolution"]))
        t_ratio = str(settings.get("target_aspect_ratio", current["target_aspect_ratio"]))

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE quality_settings
                SET min_quality_score = ?, prefer_native_res = ?, prefer_aspect_ratio = ?,
                    avoid_too_dark = ?, avoid_too_bright = ?, popularity_weight = ?,
                    technical_weight = ?, target_resolution = ?, target_aspect_ratio = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (min_q, pref_res, pref_ratio, avoid_dark, avoid_bright, pop_w, tech_w, t_res, t_ratio))
            conn.commit()
            return True

    def get_gif_settings(self) -> Dict[str, Any]:
        """Retrieves animated GIF playback settings."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute("SELECT enabled, mode, prefer_hd FROM gif_settings WHERE id = 1")
                row = cur.fetchone()
                if row:
                    return {
                        "enabled": bool(row[0]),
                        "mode": str(row[1] or "all"),
                        "prefer_hd": bool(row[2])
                    }
            except Exception:
                pass
            return {"enabled": True, "mode": "all", "prefer_hd": True}

    def save_gif_settings(self, enabled: bool = True, mode: str = "all", prefer_hd: bool = True) -> bool:
        """Persists animated GIF playback preferences."""
        clean_mode = mode if mode in ("all", "static", "gif") else "all"
        with self.write_transaction() as (conn, cur):
            cur.execute("""
                INSERT INTO gif_settings (id, enabled, mode, prefer_hd, updated_at)
                VALUES (1, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    enabled = excluded.enabled,
                    mode = excluded.mode,
                    prefer_hd = excluded.prefer_hd,
                    updated_at = CURRENT_TIMESTAMP
            """, (1 if enabled else 0, clean_mode, 1 if prefer_hd else 0))
            return cur.rowcount > 0

    def update_wallpaper_quality(
        self,
        wallpaper_id: str,
        quality_score: float,
        technical_score: float,
        popularity_score: float,
        dim_x: Optional[int] = None,
        dim_y: Optional[int] = None,
        file_size: Optional[int] = None,
        views: Optional[int] = None,
        favorites: Optional[int] = None
    ) -> bool:
        """Stores calculated quality scores in SQLite to avoid recalculating unnecessarily."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET quality_score = ?, technical_score = ?, popularity_score = ?,
                    dimension_x = COALESCE(?, dimension_x),
                    dimension_y = COALESCE(?, dimension_y),
                    file_size = COALESCE(?, file_size),
                    views = COALESCE(?, views),
                    favorites = COALESCE(?, favorites),
                    scored_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (quality_score, technical_score, popularity_score, dim_x, dim_y, file_size, views, favorites, wallpaper_id))
            conn.commit()
            return cur.rowcount > 0

    def backfill_quality_scores(self, scorer: Any, limit: int = 500) -> int:
        """
        Backfills missing quality scores for unscored catalog wallpapers in SQLite.
        Avoids recalculating items that already have quality_score populated.
        """
        updated = 0
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, resolution, tags, source, dimension_x, dimension_y, file_size, views, favorites
                FROM wallpaper_lifecycle
                WHERE quality_score IS NULL
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()

            for row in rows:
                w_id = row[0]
                res_str = row[1]
                colors_raw = row[2]
                dim_x = row[4]
                dim_y = row[5]
                f_size = row[6]
                views = row[7]
                favs = row[8]

                item_dict = {
                    "resolution": res_str,
                    "dimension_x": dim_x,
                    "dimension_y": dim_y,
                    "file_size": f_size,
                    "views": views,
                    "favorites": favs,
                    "colors": colors_raw
                }
                res = scorer.score_wallpaper(item_dict)
                cur.execute("""
                    UPDATE wallpaper_lifecycle
                    SET quality_score = ?, technical_score = ?, popularity_score = ?,
                        scored_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (res["quality_score"], res["technical_score"], res["popularity_score"], w_id))
                updated += 1

            conn.commit()
        if updated > 0:
            print(f"[KuroDB] Backfilled quality scores for {updated} catalog wallpaper(s).")
        return updated

    def get_quality_scores_summary(self) -> Dict[str, Any]:
        """Provides quality score metrics, averages, and highest quality catalog artwork."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(quality_score) as scored,
                    AVG(quality_score) as avg_quality,
                    AVG(technical_score) as avg_technical,
                    AVG(popularity_score) as avg_popularity,
                    MIN(quality_score) as min_quality,
                    MAX(quality_score) as max_quality
                FROM wallpaper_lifecycle
            """)
            row = cur.fetchone()

            cur.execute("""
                SELECT id, anime, character, resolution, quality_score, technical_score, popularity_score, source
                FROM wallpaper_lifecycle
                WHERE quality_score IS NOT NULL
                ORDER BY quality_score DESC
                LIMIT 10
            """)
            top_rows = cur.fetchall()
            top_items = [
                {
                    "id": r[0], "anime": r[1], "character": r[2], "resolution": r[3],
                    "quality_score": round(r[4], 1) if r[4] is not None else 0.0,
                    "technical_score": round(r[5], 1) if r[5] is not None else 0.0,
                    "popularity_score": round(r[6], 1) if r[6] is not None else 0.0,
                    "source": r[7]
                }
                for r in top_rows
            ]

            return {
                "total_wallpapers": row[0] or 0,
                "scored_wallpapers": row[1] or 0,
                "avg_quality": round(row[2] or 0.0, 1),
                "avg_technical": round(row[3] or 0.0, 1),
                "avg_popularity": round(row[4] or 0.0, 1),
                "min_quality": round(row[5] or 0.0, 1),
                "max_quality": round(row[6] or 0.0, 1),
                "top_scored": top_items,
                "disclaimer": (
                    "Technical Image Quality measures objective rendering fidelity (resolution, aspect ratio, "
                    "detail density, luminance). Community Popularity reflects audience favorites and views. "
                    "Subjective artistic quality is unmeasured."
                )
            }

    # =========================================================================
    # INTELLIGENT SLIDESHOW SCHEDULING (MIGRATION v8)
    # =========================================================================

    def get_scheduler_settings(self) -> Dict[str, Any]:
        """Retrieves active slideshow scheduling configuration."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT strategy, fixed_seconds, random_min, random_max,
                       day_seconds, evening_seconds, night_seconds,
                       cinematic_seconds, dashboard_seconds, quality_bonus_enabled,
                       pause_on_hidden, franchise_rotation_interval, updated_at
                FROM scheduler_settings WHERE id = 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    "strategy": str(row[0]),
                    "fixed_seconds": int(row[1]),
                    "random_min": int(row[2]),
                    "random_max": int(row[3]),
                    "day_seconds": int(row[4]),
                    "evening_seconds": int(row[5]),
                    "night_seconds": int(row[6]),
                    "cinematic_seconds": int(row[7]),
                    "dashboard_seconds": int(row[8]),
                    "quality_bonus_enabled": bool(row[9]),
                    "pause_on_hidden": bool(row[10]),
                    "franchise_rotation_interval": int(row[11]),
                    "updated_at": str(row[12])
                }
            return {
                "strategy": "fixed",
                "fixed_seconds": 30,
                "random_min": 15,
                "random_max": 60,
                "day_seconds": 25,
                "evening_seconds": 35,
                "night_seconds": 60,
                "cinematic_seconds": 45,
                "dashboard_seconds": 20,
                "quality_bonus_enabled": True,
                "pause_on_hidden": True,
                "franchise_rotation_interval": 5,
                "updated_at": None
            }

    def update_scheduler_settings(self, settings: Dict[str, Any]) -> bool:
        """Updates slideshow scheduling preferences in scheduler_settings."""
        current = self.get_scheduler_settings()
        strategy = str(settings.get("strategy", current["strategy"]))
        fixed_sec = max(5, min(600, int(settings.get("fixed_seconds", current["fixed_seconds"]))))
        rand_min = max(5, min(600, int(settings.get("random_min", current["random_min"]))))
        rand_max = max(rand_min, min(600, int(settings.get("random_max", current["random_max"]))))
        day_sec = max(5, min(600, int(settings.get("day_seconds", current["day_seconds"]))))
        eve_sec = max(5, min(600, int(settings.get("evening_seconds", current["evening_seconds"]))))
        night_sec = max(5, min(600, int(settings.get("night_seconds", current["night_seconds"]))))
        cin_sec = max(5, min(600, int(settings.get("cinematic_seconds", current["cinematic_seconds"]))))
        dash_sec = max(5, min(600, int(settings.get("dashboard_seconds", current["dashboard_seconds"]))))
        q_bonus = int(settings.get("quality_bonus_enabled", current["quality_bonus_enabled"]))
        pause_hid = int(settings.get("pause_on_hidden", current["pause_on_hidden"]))
        franchise_rot = max(1, min(50, int(settings.get("franchise_rotation_interval", current["franchise_rotation_interval"]))))

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE scheduler_settings
                SET strategy = ?, fixed_seconds = ?, random_min = ?, random_max = ?,
                    day_seconds = ?, evening_seconds = ?, night_seconds = ?,
                    cinematic_seconds = ?, dashboard_seconds = ?, quality_bonus_enabled = ?,
                    pause_on_hidden = ?, franchise_rotation_interval = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (
                strategy, fixed_sec, rand_min, rand_max,
                day_sec, eve_sec, night_sec,
                cin_sec, dash_sec, q_bonus,
                pause_hid, franchise_rot
            ))
            conn.commit()
            return cur.rowcount > 0

    # =========================================================================
    # OPTIONAL AMBIENT SOUNDSCAPE ENGINE (MIGRATION v9)
    # =========================================================================

    def get_soundscape_settings(self) -> Dict[str, Any]:
        """Retrieves active ambient soundscape configuration."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT enabled, current_track, volume, muted, crossfade_seconds, updated_at
                FROM soundscape_settings WHERE id = 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    "enabled": bool(row[0]),
                    "current_track": str(row[1]),
                    "volume": int(row[2]),
                    "muted": bool(row[3]),
                    "crossfade_seconds": float(row[4]),
                    "updated_at": str(row[5])
                }
            return {
                "enabled": False,
                "current_track": "rain",
                "volume": 40,
                "muted": True,
                "crossfade_seconds": 2.5,
                "updated_at": None
            }

    def update_soundscape_settings(self, settings: Dict[str, Any]) -> bool:
        """Updates soundscape configuration in soundscape_settings."""
        current = self.get_soundscape_settings()
        enabled = int(settings.get("enabled", current["enabled"]))
        track = str(settings.get("current_track", current["current_track"]))
        vol = max(0, min(100, int(settings.get("volume", current["volume"]))))
        muted = int(settings.get("muted", current["muted"]))
        crossfade = max(0.5, min(10.0, float(settings.get("crossfade_seconds", current["crossfade_seconds"]))))

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE soundscape_settings
                SET enabled = ?, current_track = ?, volume = ?, muted = ?,
                    crossfade_seconds = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (enabled, track, vol, muted, crossfade))
            conn.commit()
            return cur.rowcount > 0

    # =========================================================================
    # WALLPAPER COMPOSITION & FOCAL POINT PROTECTION (MIGRATION v10)
    # =========================================================================

    def get_composition_settings(self) -> Dict[str, Any]:
        """Retrieves global composition & focal protection settings."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT default_mode_landscape, default_mode_portrait, default_mode_ultrawide,
                       blurred_backdrop_enabled, blur_intensity_px, backdrop_opacity, auto_focal_protection, updated_at
                FROM composition_settings WHERE id = 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    "default_mode_landscape": str(row[0]),
                    "default_mode_portrait": str(row[1]),
                    "default_mode_ultrawide": str(row[2]),
                    "blurred_backdrop_enabled": bool(row[3]),
                    "blur_intensity_px": int(row[4]),
                    "backdrop_opacity": float(row[5]),
                    "auto_focal_protection": bool(row[6]),
                    "updated_at": str(row[7])
                }
            return {
                "default_mode_landscape": "fill",
                "default_mode_portrait": "fit",
                "default_mode_ultrawide": "fill",
                "blurred_backdrop_enabled": True,
                "blur_intensity_px": 28,
                "backdrop_opacity": 0.65,
                "auto_focal_protection": True,
                "updated_at": None
            }

    def update_composition_settings(self, settings: Dict[str, Any]) -> bool:
        """Updates global wallpaper composition settings."""
        current = self.get_composition_settings()
        mode_land = str(settings.get("default_mode_landscape", current["default_mode_landscape"]))
        mode_port = str(settings.get("default_mode_portrait", current["default_mode_portrait"]))
        mode_ultra = str(settings.get("default_mode_ultrawide", current["default_mode_ultrawide"]))
        blur_enabled = int(settings.get("blurred_backdrop_enabled", current["blurred_backdrop_enabled"]))
        blur_px = max(0, min(100, int(settings.get("blur_intensity_px", current["blur_intensity_px"]))))
        opacity = max(0.0, min(1.0, float(settings.get("backdrop_opacity", current["backdrop_opacity"]))))
        auto_focal = int(settings.get("auto_focal_protection", current["auto_focal_protection"]))

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE composition_settings
                SET default_mode_landscape = ?, default_mode_portrait = ?, default_mode_ultrawide = ?,
                    blurred_backdrop_enabled = ?, blur_intensity_px = ?, backdrop_opacity = ?,
                    auto_focal_protection = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (mode_land, mode_port, mode_ultra, blur_enabled, blur_px, opacity, auto_focal))
            conn.commit()
            return cur.rowcount > 0

    def get_wallpaper_composition(self, wallpaper_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves custom focal coordinates and composition for a specific wallpaper."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT focal_x, focal_y, display_mode, blurred_background,
                       landscape_display_mode, portrait_display_mode, character_count, characters_json, updated_at
                FROM wallpaper_composition WHERE wallpaper_id = ?
            """, (wallpaper_id,))
            row = cur.fetchone()
            if row:
                chars = []
                try:
                    chars = json.loads(row[7]) if row[7] else []
                except Exception:
                    pass
                return {
                    "wallpaper_id": wallpaper_id,
                    "focal_x": float(row[0]),
                    "focal_y": float(row[1]),
                    "display_mode": str(row[2]),
                    "blurred_background": bool(row[3]),
                    "landscape_display_mode": row[4],
                    "portrait_display_mode": row[5],
                    "character_count": int(row[6]),
                    "characters": chars,
                    "updated_at": str(row[8])
                }
            return None

    def save_wallpaper_composition(self, wallpaper_id: str, comp: Dict[str, Any]) -> bool:
        """Saves or updates custom focal coordinates and composition for a wallpaper."""
        focal_x = max(0.0, min(100.0, float(comp.get("focal_x", 50.0))))
        focal_y = max(0.0, min(100.0, float(comp.get("focal_y", 50.0))))
        mode = str(comp.get("display_mode", "fill"))
        if mode not in ("fill", "fit", "original"):
            mode = "fill"
        blurred = int(comp.get("blurred_background", 1))
        land_mode = comp.get("landscape_display_mode")
        port_mode = comp.get("portrait_display_mode")
        chars = comp.get("characters", [])
        chars_json = json.dumps(chars) if isinstance(chars, list) else "[]"
        char_count = len(chars) if isinstance(chars, list) else 1

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO wallpaper_composition (
                    wallpaper_id, focal_x, focal_y, display_mode, blurred_background,
                    landscape_display_mode, portrait_display_mode, character_count, characters_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (wallpaper_id, focal_x, focal_y, mode, blurred, land_mode, port_mode, char_count, chars_json))
            conn.commit()
            return True


    def delete_wallpaper_composition(self, wallpaper_id: str) -> bool:
        """Removes custom composition settings for a wallpaper (resetting to defaults)."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM wallpaper_composition WHERE wallpaper_id = ?", (wallpaper_id,))
            conn.commit()
            return cur.rowcount > 0

    # =========================================================================
    # ARTWORK INFORMATION & EXTENDED METADATA (MIGRATION v11)
    # =========================================================================

    def get_artwork_details(self, wallpaper_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves comprehensive artwork metadata for the interactive Information Panel.
        Never invents missing metadata; preserves authentic source fields from SQLite.
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, url, resolution, anime, character, tags, source, status,
                       level, is_cached, local_path, quality_score, technical_score,
                       popularity_score, dimension_x, dimension_y, file_size, views,
                       favorites, scored_at, created_at, displayed_at, uploader,
                       upload_date, source_url
                FROM wallpaper_lifecycle
                WHERE id = ?
            """, (wallpaper_id,))
            row = cur.fetchone()
            if not row:
                return None

            # Favorite status
            cur.execute("SELECT 1 FROM favorites WHERE id = ?", (wallpaper_id,))
            is_fav = bool(cur.fetchone())

            # Blacklist status
            cur.execute("SELECT 1 FROM blacklist WHERE wallpaper_id = ?", (wallpaper_id,))
            is_black = bool(cur.fetchone())

            # Total displayed count up to now (for sequence calculation)
            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE status = 'DISPLAYED'")
            total_displayed = cur.fetchone()[0]

            dim_x = row[14]
            dim_y = row[15]
            res_str = row[2] or "High Res"

            # Parse dimensions from resolution if dim_x/dim_y are null
            if (not dim_x or not dim_y) and res_str and "x" in res_str.lower():
                try:
                    parts = res_str.lower().split("x")
                    dim_x = int(parts[0].strip())
                    dim_y = int(parts[1].strip())
                except Exception:
                    pass

            # Calculate precise aspect ratio
            aspect_ratio_str = None
            if dim_x and dim_y and dim_y > 0:
                ratio_val = round(dim_x / dim_y, 2)
                # Classify common geometry
                if abs(ratio_val - 1.78) <= 0.05:
                    geom = "16:9"
                elif abs(ratio_val - 2.33) <= 0.10:
                    geom = "21:9 Ultrawide"
                elif abs(ratio_val - 0.56) <= 0.05:
                    geom = "9:16 Portrait"
                elif abs(ratio_val - 1.60) <= 0.05:
                    geom = "16:10"
                elif abs(ratio_val - 1.33) <= 0.05:
                    geom = "4:3"
                else:
                    geom = f"{dim_x}:{dim_y}"
                aspect_ratio_str = f"{geom} ({ratio_val}:1)"

            # Source URL fallback
            raw_source = row[6] or "Wallhaven"
            src_url = row[24]
            if not src_url and raw_source.lower() == "wallhaven":
                src_url = f"https://wallhaven.cc/w/{wallpaper_id}"
            elif not src_url and row[8] and str(row[8]).startswith("curated_"):
                src_url = "Local Curated Archive"

            # Resolved image URL for frontend
            raw_url = row[1]
            resolved_url = raw_url
            if row[10] or row[9] == 1 or row[8] in (2, 3):
                resolved_url = f"/api/image/{wallpaper_id}"

            # Format file size if known
            fsize = row[16]
            formatted_size = None
            if fsize and fsize > 0:
                if fsize >= 1024 * 1024:
                    formatted_size = f"{fsize / (1024 * 1024):.2f} MB"
                elif fsize >= 1024:
                    formatted_size = f"{fsize / 1024:.1f} KB"
                else:
                    formatted_size = f"{fsize} B"

            comp = self.get_wallpaper_composition(wallpaper_id)

            return {
                "id": str(row[0]),
                "url": resolved_url,
                "raw_url": raw_url,
                "resolution": res_str,
                "dimension_x": dim_x,
                "dimension_y": dim_y,
                "aspect_ratio": aspect_ratio_str,
                "anime": str(row[3]) if row[3] else "Popular Anime",
                "character": str(row[4]) if row[4] else None,
                "source": raw_source,
                "source_url": src_url,
                "uploader": str(row[22]) if row[22] else None,
                "upload_date": str(row[23]) if row[23] else None,
                "file_size": fsize,
                "file_size_formatted": formatted_size,
                "views": int(row[17]) if row[17] is not None else None,
                "favorites": int(row[18]) if row[18] is not None else None,
                "quality_score": round(float(row[11]), 1) if row[11] is not None else 50.0,
                "technical_score": round(float(row[12]), 1) if row[12] is not None else 50.0,
                "popularity_score": round(float(row[13]), 1) if row[13] is not None else 50.0,
                "level": int(row[8]) if row[8] is not None else 1,
                "is_cached": bool(row[9]),
                "status": str(row[7]),
                "created_at": str(row[20]) if row[20] else None,
                "displayed_at": str(row[21]) if row[21] else None,
                "is_favorite": is_fav,
                "is_blacklisted": is_black,
                "total_displayed_history": total_displayed,
                "composition": comp
            }

    # =========================================================================
    # ADVANCED ANIME AMBIENT CONTROL CENTER PREFERENCES
    # =========================================================================

    def get_control_center_settings(self, section: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves consolidated settings for all control center sections or a specific section.
        Always merges stored overrides with safe defaults so all expected fields exist.
        """
        defaults_copy: Dict[str, Any] = {}
        for sec, items in CONTROL_CENTER_DEFAULTS.items():
            defaults_copy[sec] = dict(items)

        with self.get_connection() as conn:
            cur = conn.cursor()
            if section:
                cur.execute(
                    "SELECT section, setting_key, setting_value FROM control_center_settings WHERE section = ?",
                    (section,)
                )
            else:
                cur.execute("SELECT section, setting_key, setting_value FROM control_center_settings")

            rows = cur.fetchall()

        for sec, k, v in rows:
            if sec not in defaults_copy:
                defaults_copy[sec] = {}
            # Deserialize value based on JSON or primitive
            try:
                parsed = json.loads(v)
            except Exception:
                parsed = v
            defaults_copy[sec][k] = parsed

        if section:
            return defaults_copy.get(section, {})
        return defaults_copy

    def save_control_center_settings(self, section: str, settings: Dict[str, Any]) -> bool:
        """
        Persists validated settings for a specific section (general, wallpaper, visual, display, performance, privacy).
        Never silently resets existing settings outside of the provided keys.
        """
        if not section or not isinstance(settings, dict):
            return False

        with self.get_connection() as conn:
            cur = conn.cursor()
            for key, val in settings.items():
                if isinstance(val, (dict, list, bool, int, float)):
                    val_str = json.dumps(val)
                elif val is None:
                    val_str = json.dumps(None)
                else:
                    val_str = str(val)

                cur.execute("""
                    INSERT OR REPLACE INTO control_center_settings (section, setting_key, setting_value, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (section, key, val_str))
            conn.commit()
        return True

    def reset_control_center_section(self, section: str) -> Dict[str, Any]:
        """
        Resets only the specified section to its default values without modifying other sections.
        """
        if section not in CONTROL_CENTER_DEFAULTS:
            return {}

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM control_center_settings WHERE section = ?", (section,))
            conn.commit()

        return dict(CONTROL_CENTER_DEFAULTS[section])

    def get_provider_settings(self) -> Dict[str, Any]:
        """Returns the configured artwork provider settings."""
        return self.get_control_center_settings("providers")

    def save_provider_settings(self, settings: Dict[str, Any]) -> bool:
        """Persists updated artwork provider settings."""
        return self.save_control_center_settings("providers", settings)

    def export_full_configuration(self) -> Dict[str, Any]:
        """
        Exports complete consolidated application settings for backup or migration.
        """
        ctrl_settings = self.get_control_center_settings()
        sched_settings = self.get_scheduler_settings()
        qual_settings = self.get_quality_settings()
        sound_settings = self.get_soundscape_settings()
        comp_settings = self.get_composition_settings()

        return {
            "schema_version": 12,
            "application": "Anime Ambient Screensaver",
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "control_center": ctrl_settings,
            "scheduler": sched_settings,
            "quality": qual_settings,
            "soundscape": sound_settings,
            "composition": comp_settings
        }

    def import_full_configuration(self, config: Dict[str, Any]) -> bool:
        """
        Safely imports full configuration, validating sections and preserving existing favorites.
        """
        if not isinstance(config, dict):
            return False

        ctrl = config.get("control_center", {})
        if isinstance(ctrl, dict):
            for sec, vals in ctrl.items():
                if sec in CONTROL_CENTER_DEFAULTS and isinstance(vals, dict):
                    self.save_control_center_settings(sec, vals)

        if "scheduler" in config and isinstance(config["scheduler"], dict):
            self.update_scheduler_settings(config["scheduler"])
        if "quality" in config and isinstance(config["quality"], dict):
            self.update_quality_settings(config["quality"])
        if "soundscape" in config and isinstance(config["soundscape"], dict):
            self.update_soundscape_settings(config["soundscape"])
        if "composition" in config and isinstance(config["composition"], dict):
            self.update_composition_settings(config["composition"])

        return True

    def factory_reset_configuration(self) -> bool:
        """
        Resets all control center preferences, scheduler, quality, soundscapes, and composition
        to factory defaults while strictly preserving user saved favorites and curated images.
        """
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM control_center_settings")
            conn.commit()

        # Re-initialize scheduler, quality, soundscape, composition defaults
        self.update_scheduler_settings({
            "strategy": "fixed",
            "base_interval_sec": 30,
            "random_min_sec": 15,
            "random_max_sec": 60,
            "time_day_sec": 25,
            "time_evening_sec": 35,
            "time_night_sec": 60,
            "cinematic_sec": 45,
            "dashboard_sec": 20,
            "franchise_rotation_interval": 5,
            "quality_weighted_bonus": True,
            "pause_on_hidden": True
        })
        self.update_quality_settings({
            "min_quality_threshold": 50,
            "prefer_native_res": True,
            "strict_aspect_ratio": True,
            "avoid_blinding_bright": True,
            "avoid_pitch_dark": False,
            "popularity_weight": 0.35
        })
        self.update_soundscape_settings({
            "enabled": False,
            "current_track": "rain",
            "volume": 40,
            "crossfade_sec": 2.5,
            "muted": True
        })
        self.update_composition_settings({
            "default_mode_landscape": "fill",
            "default_mode_portrait": "fit",
            "default_mode_ultrawide": "fill",
            "blurred_backdrop_enabled": True,
            "blur_intensity_px": 28,
            "backdrop_opacity": 0.65,
            "auto_focal_protection": True
        })
        return True

    def get_backup_manager(self):
        """Returns an initialized BackupManager instance bound to this database."""
        from backup_manager import BackupManager
        privacy_settings = self.get_control_center_settings("privacy")
        max_auto = privacy_settings.get("privacy_max_auto_backups", 5)
        return BackupManager(self, app_dir=self.db_path.parent, max_auto_backups=max_auto)

    # ---------------------------------------------------------------------------
    # Verified Franchise Tag Intelligence Cache & Catalog Storage (Migration v14)
    # ---------------------------------------------------------------------------

    def cache_verified_tag(
        self,
        tag_id: int,
        tag_name: str,
        category: Optional[str] = None,
        purity: Optional[str] = None,
        raw_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Caches live verified tag information from Wallhaven into SQLite."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO verified_tag_cache (tag_id, tag_name, category, purity, last_checked_at, raw_metadata)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(tag_id) DO UPDATE SET
                    tag_name = excluded.tag_name,
                    category = excluded.category,
                    purity = excluded.purity,
                    last_checked_at = CURRENT_TIMESTAMP,
                    raw_metadata = excluded.raw_metadata
            """, (
                int(tag_id),
                tag_name.strip(),
                category,
                purity,
                json.dumps(raw_metadata) if raw_metadata else None
            ))
            conn.commit()
            return True


    def get_cached_tag(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves cached verified tag details by numeric tag ID."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM verified_tag_cache WHERE tag_id = ?", (int(tag_id),))
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("raw_metadata"):
                try:
                    res["raw_metadata"] = json.loads(res["raw_metadata"])
                except Exception:
                    pass
            return res

    def get_all_cached_tags(self) -> List[Dict[str, Any]]:
        """Returns list of all cached verified tag IDs and metadata."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM verified_tag_cache ORDER BY tag_name ASC")
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if item.get("raw_metadata"):
                    try:
                        item["raw_metadata"] = json.loads(item["raw_metadata"])
                    except Exception:
                        pass
                results.append(item)
            return results

    def save_franchise_catalog_db(self, slug: str, name: str, catalog_json: str) -> bool:
        """Stores administrative override of franchise catalog in SQLite."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO franchise_catalog (slug, name, catalog_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(slug) DO UPDATE SET
                    name = excluded.name,
                    catalog_json = excluded.catalog_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (slug.strip().lower(), name.strip(), catalog_json))
            conn.commit()
            return True


    def load_franchise_catalog_db(self) -> Dict[str, Dict[str, Any]]:
        """Loads custom franchise catalog records from SQLite."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM franchise_catalog")
            rows = cur.fetchall()
            result = {}
            for r in rows:
                try:
                    data = json.loads(r["catalog_json"])
                    result[r["slug"]] = data
                except Exception:
                    pass
            return result

    # =========================================================================
    # Safety and Moderation Layer Helper Methods
    # =========================================================================

    def is_blocked_in_db(self, entity_type: str, entity_value: str) -> bool:
        """
        Checks if an entity (artwork, tag, character, artist, franchise) is actively blocked.
        Performs case-insensitive matching.
        """
        if not entity_value:
            return False
        val_clean = str(entity_value).strip().lower()
        t_clean = str(entity_type).strip().lower()

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM blocked_entities WHERE LOWER(entity_type) = ? AND LOWER(entity_value) = ?",
                (t_clean, val_clean)
            )
            if cur.fetchone() is not None:
                return True

            if t_clean == "artwork":
                cur.execute("SELECT 1 FROM blacklist WHERE LOWER(wallpaper_id) = ?", (val_clean,))
                if cur.fetchone() is not None:
                    return True
        return False

    def get_blocked_entities(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves blocked entities, optionally filtered by type."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            if entity_type:
                cur.execute(
                    "SELECT * FROM blocked_entities WHERE LOWER(entity_type) = ? ORDER BY blocked_at DESC",
                    (entity_type.strip().lower(),)
                )
            else:
                cur.execute("SELECT * FROM blocked_entities ORDER BY blocked_at DESC")
            return [dict(r) for r in cur.fetchall()]

    def add_blocked_entity(self, entity_type: str, entity_value: str, reason: str = "") -> bool:
        """
        Adds a blocked entity (artwork, tag, character, artist, franchise).
        Cascades artwork blocks to blacklist and wallpaper_lifecycle tables.
        """
        if not entity_type or not entity_value:
            return False
        t_clean = entity_type.strip().lower()
        v_clean = entity_value.strip()

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO blocked_entities (entity_type, entity_value, reason, blocked_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(entity_type, entity_value) DO UPDATE SET
                    reason = COALESCE(NULLIF(excluded.reason, ''), blocked_entities.reason),
                    blocked_at = CURRENT_TIMESTAMP
            """, (t_clean, v_clean, reason.strip()))

            if t_clean == "artwork":
                # Maintain legacy blacklist table synchronization
                cur.execute("""
                    INSERT OR IGNORE INTO blacklist (wallpaper_id, reason, blacklisted_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (v_clean, reason or "moderation_block"))

                # Mark in lifecycle
                cur.execute("""
                    UPDATE wallpaper_lifecycle
                    SET status = 'FAILED',
                        safety_rating = 'BLOCKED',
                        safety_reason = ?
                    WHERE id = ?
                """, (reason or "user_blocked", v_clean))

            conn.commit()
            return True


    def remove_blocked_entity(
        self,
        entity_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_value: Optional[str] = None
    ) -> bool:
        """Removes a blocked entity by ID or type+value pair."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            if entity_id is not None:
                cur.execute("SELECT entity_type, entity_value FROM blocked_entities WHERE id = ?", (entity_id,))
                row = cur.fetchone()
                if row:
                    t_val = row["entity_type"].lower()
                    v_val = row["entity_value"]
                    cur.execute("DELETE FROM blocked_entities WHERE id = ?", (entity_id,))
                    if t_val == "artwork":
                        cur.execute("DELETE FROM blacklist WHERE LOWER(wallpaper_id) = ?", (v_val.lower(),))
                        cur.execute("UPDATE wallpaper_lifecycle SET status = 'UNSEEN', safety_rating = 'SAFE' WHERE id = ? AND safety_rating = 'BLOCKED'", (v_val,))
                    conn.commit()
                    return True
                return False
            elif entity_type and entity_value:
                t_clean = entity_type.strip().lower()
                v_clean = entity_value.strip()
                cur.execute(
                    "DELETE FROM blocked_entities WHERE LOWER(entity_type) = ? AND LOWER(entity_value) = ?",
                    (t_clean, v_clean.lower())
                )
                if t_clean == "artwork":
                    cur.execute("DELETE FROM blacklist WHERE LOWER(wallpaper_id) = ?", (v_clean.lower(),))
                    cur.execute("UPDATE wallpaper_lifecycle SET status = 'UNSEEN', safety_rating = 'SAFE' WHERE id = ? AND safety_rating = 'BLOCKED'", (v_clean,))
                conn.commit()
                return cur.rowcount > 0
            return False

    def report_and_block_artwork(
        self,
        wallpaper_id: str,
        reason: str = "User reported unsafe content",
        block_character: bool = False,
        block_artist: bool = False
    ) -> Dict[str, Any]:
        """
        Reports and permanently hides/blocks an individual artwork.
        Optionally cascades blocks to associated character and artist/uploader.
        """
        blocked_items = []
        wallpaper_id = str(wallpaper_id).strip()

        # 1. Block artwork
        self.add_blocked_entity("artwork", wallpaper_id, reason=reason)
        blocked_items.append({"type": "artwork", "value": wallpaper_id})

        # 2. Inspect record for character / artist cascading
        rec = self.get_wallpaper_by_id(wallpaper_id)
        if rec:
            if block_character and rec.get("character"):
                char_val = str(rec["character"]).strip()
                if char_val and char_val.lower() != "none" and char_val.lower() != "unknown":
                    self.add_blocked_entity("character", char_val, reason=f"Cascaded from reported artwork {wallpaper_id}")
                    blocked_items.append({"type": "character", "value": char_val})

            if block_artist and rec.get("uploader"):
                artist_val = str(rec["uploader"]).strip()
                if artist_val and artist_val.lower() != "none" and artist_val.lower() != "unknown":
                    self.add_blocked_entity("artist", artist_val, reason=f"Cascaded from reported artwork {wallpaper_id}")
                    blocked_items.append({"type": "artist", "value": artist_val})

        return {
            "status": "success",
            "wallpaper_id": wallpaper_id,
            "blocked_entities": blocked_items,
            "reason": reason
        }

    def add_to_review_queue(self, wallpaper_dict: Dict[str, Any], failure_reason: str, safety_rating: str) -> bool:
        """Queues an ambiguous or unclassified artwork for manual user inspection."""
        wall_id = str(wallpaper_dict.get("id", "")).strip()
        if not wall_id:
            return False
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO wallpaper_review_queue (
                    id, wallpaper_json, failure_reason, safety_rating, created_at, review_decision
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'PENDING')
                ON CONFLICT(id) DO UPDATE SET
                    wallpaper_json = excluded.wallpaper_json,
                    failure_reason = excluded.failure_reason,
                    safety_rating = excluded.safety_rating,
                    review_decision = 'PENDING'
            """, (wall_id, json.dumps(wallpaper_dict), failure_reason, safety_rating))
            conn.commit()
            return True


    def get_review_queue(self, limit: int = 50, decision: str = "PENDING") -> List[Dict[str, Any]]:
        """Fetches items in the manual review queue."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM wallpaper_review_queue
                WHERE review_decision = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (decision.upper(), int(limit)))
            rows = cur.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["wallpaper"] = json.loads(item["wallpaper_json"])
                except Exception:
                    item["wallpaper"] = {}
                results.append(item)
            return results

    def action_review_queue_item(self, wallpaper_id: str, decision: str) -> bool:
        """
        Applies a review decision ('APPROVE' or 'REJECT') to a queued item.
        APPROVE: adds to UNSEEN safe pool.
        REJECT: blocks artwork.
        """
        wall_id = str(wallpaper_id).strip()
        dec_clean = decision.strip().upper()
        if dec_clean not in ("APPROVE", "REJECT"):
            return False

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT wallpaper_json FROM wallpaper_review_queue WHERE id = ?", (wall_id,))
            row = cur.fetchone()
            wallpaper_data = {}
            if row:
                try:
                    wallpaper_data = json.loads(row["wallpaper_json"])
                except Exception:
                    pass

            cur.execute("""
                UPDATE wallpaper_review_queue
                SET review_decision = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (dec_clean, wall_id))
            conn.commit()

        if dec_clean == "APPROVE":
            if wallpaper_data:
                wallpaper_data["safety_rating"] = "SAFE"
                wallpaper_data["safety_reason"] = "manual_review_approved"
                self.add_unseen_wallpapers([wallpaper_data])
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE wallpaper_lifecycle
                    SET safety_rating = 'SAFE',
                        safety_reason = 'manual_review_approved',
                        status = CASE WHEN status = 'BLOCKED' THEN 'UNSEEN' ELSE status END
                    WHERE id = ?
                """, (wall_id,))
                conn.commit()
        elif dec_clean == "REJECT":
            self.add_blocked_entity("artwork", wall_id, reason="Rejected via Manual Safety Review")

        return True

    def get_safety_policy_settings(self) -> Dict[str, Any]:
        """Loads unified safety policy configuration."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM safety_policy_settings WHERE id = 1")
            row = cur.fetchone()
            if not row:
                return {
                    "strict_mode": True,
                    "min_tags_required": 1,
                    "allow_review_queue": True,
                    "auto_block_reported": True
                }
            return {
                "strict_mode": bool(row["strict_mode"]),
                "min_tags_required": int(row["min_tags_required"]),
                "allow_review_queue": bool(row["allow_review_queue"]),
                "auto_block_reported": bool(row["auto_block_reported"]),
                "updated_at": row["updated_at"]
            }

    def save_safety_policy_settings(self, settings: Dict[str, Any]) -> bool:
        """Persists safety policy configuration."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE safety_policy_settings
                SET strict_mode = ?,
                    min_tags_required = ?,
                    allow_review_queue = ?,
                    auto_block_reported = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (
                1 if settings.get("strict_mode", True) else 0,
                int(settings.get("min_tags_required", 1)),
                1 if settings.get("allow_review_queue", True) else 0,
                1 if settings.get("auto_block_reported", True) else 0
            ))
            conn.commit()
            return True

    def get_wallhaven_compatibility_status(self) -> Dict[str, Any]:
        """Retrieves the latest Wallhaven API compatibility contract status."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM wallhaven_compatibility_status WHERE id = 1")
            row = cur.fetchone()
            if not row:
                return {}
            cols = [col[0] for col in cur.description]
            res = dict(zip(cols, row))
            for json_col in ("verified_params_json", "degraded_params_json", "rejected_params_json", "uncertain_params_json", "diagnostics_json", "raw_meta_json"):
                if json_col in res and isinstance(res[json_col], str):
                    try:
                        clean_key = json_col.replace("_json", "")
                        res[clean_key] = json.loads(res[json_col])
                    except Exception:
                        pass
            return res

    def save_wallhaven_compatibility_status(self, report: Dict[str, Any]) -> bool:
        """Persists the results of a Wallhaven API compatibility check."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO wallhaven_compatibility_status (
                    id, status, schema_version, last_checked_at, last_success_at, is_live_check,
                    verified_params_json, degraded_params_json, rejected_params_json, uncertain_params_json,
                    diagnostics_json, raw_meta_json, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    schema_version = excluded.schema_version,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = COALESCE(excluded.last_success_at, wallhaven_compatibility_status.last_success_at),
                    is_live_check = excluded.is_live_check,
                    verified_params_json = excluded.verified_params_json,
                    degraded_params_json = excluded.degraded_params_json,
                    rejected_params_json = excluded.rejected_params_json,
                    uncertain_params_json = excluded.uncertain_params_json,
                    diagnostics_json = excluded.diagnostics_json,
                    raw_meta_json = excluded.raw_meta_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                report.get("status", "COMPATIBLE"),
                report.get("schema_version", "v1"),
                report.get("last_checked_at"),
                report.get("last_success_at"),
                1 if report.get("is_live_check") else 0,
                json.dumps(report.get("verified_parameters", [])),
                json.dumps(report.get("degraded_parameters", [])),
                json.dumps(report.get("rejected_parameters", [])),
                json.dumps(report.get("uncertain_parameters", [])),
                json.dumps(report.get("diagnostics", [])),
                json.dumps(report.get("raw_meta", {}))
            ))
            conn.commit()
            return True


CONTROL_CENTER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "general": {
        "display_mode": "ambient",
        "slideshow_interval": 30,
        "scheduler_strategy": "fixed",
        "startup_launch_mode": "kiosk",
        "startup_win_boot": False,
        "clock_time_format": "12",
        "clock_show_seconds": True,
        "clock_date_format": "full",
        "clock_second_tz": "none",
        "weather_temp_unit": "C",
        "weather_city": ""
    },
    "wallpaper": {
        "wallpaper_franchise": "all",
        "wallpaper_character": "all",
        "wallpaper_franchise_weights": {},
        "wallpaper_min_popularity": "0.35",
        "wallpaper_min_resolution": "any",
        "wallpaper_aspect_ratio": "auto",
        "wallpaper_duplicate_sensitivity": "strict"
    },
    "visual": {
        "visual_theme": "kuro-dark",
        "visual_dynamic_accent": True,
        "visual_accent_color": "#38bdf8",
        "visual_transition_style": "random",
        "visual_transition_duration": 2.5,
        "visual_motion_style": "random",
        "visual_animation_intensity": "normal",
        "visual_reduced_motion": False,
        "visual_particles_enabled": True,
        "visual_particle_density": "medium",
        "visual_particle_speed": "normal",
        "visual_hud_opacity": 100,
        "visual_idle_opacity": 15,
        "visual_auto_dim_delay": 3.5
    },
    "display": {
        "display_target_monitor": "auto",
        "display_orientation": "auto",
        "display_resolution": "native",
        "display_scaling": True,
        "display_ui_scale": "100%",
        "display_wallpaper_fitting": "fill",
        "display_blurred_backdrop": True,
        "display_blur_intensity": 28,
        "display_focal_point": "auto"
    },
    "performance": {
        "perf_prefetch_queue_size": 6,
        "perf_cache_limit_mb": 2048,
        "perf_worker_count": 2,
        "perf_download_limit": 2,
        "perf_animation_quality": "60fps",
        "perf_quality_profile": "auto",
        "perf_max_concurrent_decodes": 1,
        "perf_monitor_enabled": True
    },
    "privacy": {
        "privacy_local_history": True,
        "privacy_preference_learning": True,
        "privacy_clear_cache_on_exit": False,
        "privacy_max_auto_backups": 5
    },
    "providers": {
        "wallhaven_enabled": True,
        "safebooru_enabled": True,
        "konachan_enabled": True,
        "primary_provider": "wallhaven",
        "circuit_breaker_timeout": 60,
        "max_failover_retries": 3
    },
    "moderation": {
        "strict_mode": True,
        "min_tags_required": 1,
        "allow_review_queue": True,
        "auto_block_reported": True,
        "block_unrated_content": True
    }
}
