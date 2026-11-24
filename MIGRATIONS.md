# 🗄️ KURO // ANIME — Database Schema Versioning & Migration Architecture

This document serves as the formal technical specification for the SQLite transactional schema, migration history (v1 through v13), data integrity constraints, backup mechanisms, and disaster recovery procedures in the **KURO // ANIME Ambient Screensaver**.

---

## 🏛️ Database Engine Architecture

- **Engine:** SQLite 3 (Standard Library `sqlite3`)
- **Default Database File:** `kuro_database.db`
- **Concurrency Mode:** `PRAGMA journal_mode = WAL;` (Write-Ahead Logging)
- **Synchronous Level:** `PRAGMA synchronous = NORMAL;` (Crash-safe and high performance)
- **Foreign Key Constraints:** `PRAGMA foreign_keys = ON;`
- **Busy Timeout:** `PRAGMA busy_timeout = 5000;` (5-second lock queue before timeout)
- **Thread Safety:** Single write lock (`threading.Lock()`) with multi-reader concurrency; check_same_thread disabled for pool safety.
- **Current Schema Version:** `v13` (Tracked in `schema_migrations`)

---

## 🛡️ Backup & Disaster Recovery Standards

1. **Online Transactional Backups:** All database exports and snapshots utilize the official `sqlite3.Connection.backup()` API. This avoids filesystem-level locking conflicts on Windows and guarantees consistent, non-corrupted point-in-time snapshots even under high concurrent traffic.
2. **Pre-Migration Automatic Snapshots:** Whenever an existing database (`version > 0`) is initialized and requires schema upgrades (`version < CURRENT_SCHEMA_VERSION`), `DatabaseManager` creates an automatic backup archive (`backups/auto_pre_migration_v{version}_{timestamp}.zip`) before executing any migration statements.
3. **Pre-Restore Safety Snapshots:** Before any backup restoration replaces active data, an automatic safety snapshot (`backups/auto_pre_restore_{timestamp}.zip`) is generated. Users can undo a restore if necessary.
4. **Manifest & Checksum Verification:** Every exported backup archive (`.zip`) includes a `manifest.json` containing table record counts, system metrics, and SHA-256 digests. Restorations rigorously validate the archive ZIP structure, SHA-256 checksums, SQLite `PRAGMA integrity_check`, and schema compatibility.
5. **Configurable Retention:** Automatic snapshots (`auto_*`) are pruned to retain a configurable number of snapshots (`max_auto_backups`, default: 5) to prevent unbounded disk usage. Manual user backups are never pruned automatically.
6. **Corruption Quarantine:** If SQLite detects low-level file corruption on startup (`sqlite3.DatabaseError`), `auto_recover_corrupted_database()` immediately quarantines the damaged `.db`, `.db-wal`, and `.db-shm` files to timestamped `.corrupt.{timestamp}` files and initializes a fresh database.

---

## 📜 Complete Migration History (v1 to v13)

### Migration v1 — Baseline Historical Schema
* **Purpose:** Initial legacy tracking of displayed wallpapers and saved favorites.
* **Tables Created:**
  - `schema_migrations` (`version INTEGER PRIMARY KEY`, `applied_at TIMESTAMP`)
  - `seen_wallpapers` (`id TEXT PRIMARY KEY`, `url TEXT`, `resolution TEXT`, `mood TEXT`, `seen_at TIMESTAMP`)
  - `favorites` (`id TEXT PRIMARY KEY`, `url TEXT`, `resolution TEXT`, `mood TEXT`, `saved_at TIMESTAMP`)

---

### Migration v2 — Transactional Wallpaper Lifecycle Engine
* **Purpose:** Zero-repetition state machine preventing race conditions across multi-monitor setups.
* **State Invariant:** `UNSEEN -> RESERVED -> DISPLAYED` (or `FAILED`).
* **Tables Created:**
  - `wallpaper_lifecycle`:
    - `id TEXT PRIMARY KEY`
    - `url TEXT NOT NULL`
    - `resolution TEXT`
    - `anime TEXT`
    - `source TEXT DEFAULT 'Wallhaven'`
    - `status TEXT NOT NULL CHECK(status IN ('UNSEEN', 'RESERVED', 'DISPLAYED', 'FAILED'))`
    - `reserved_at REAL`
    - `reservation_token TEXT`
    - `displayed_at TIMESTAMP`
    - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
* **Indexes:**
  - `idx_lifecycle_status_anime ON wallpaper_lifecycle(status, anime)`
  - `idx_lifecycle_reserved_at ON wallpaper_lifecycle(reserved_at)`
* **Data Migration:** Migrated existing records from `seen_wallpapers` into `wallpaper_lifecycle` with `status = 'DISPLAYED'`.

---

### Migration v3 — Franchise, Character & Tag Metadata
* **Purpose:** Character-level indexing and search for anime franchises.
* **Columns Added to `wallpaper_lifecycle`:**
  - `character TEXT`
  - `tags TEXT` (JSON-encoded array of tag strings)
* **Indexes:**
  - `idx_lifecycle_anime_char ON wallpaper_lifecycle(anime, character)`

---

### Migration v4 — 3-Layer Offline Fallback System
* **Purpose:** Offline-first caching and Level 3 curated local collection tracking.
* **Columns Added to `wallpaper_lifecycle`:**
  - `local_path TEXT`
  - `is_cached INTEGER DEFAULT 0`
  - `level INTEGER DEFAULT 1` (1 = Live Stream, 2 = Local Cache, 3 = Curated Collection)
* **Indexes:**
  - `idx_lifecycle_level_status ON wallpaper_lifecycle(level, status)`
  - `idx_lifecycle_cached ON wallpaper_lifecycle(is_cached, status)`

---

### Migration v5 — Personal Collections, Resilient Favorites & Blacklist
* **Purpose:** Full collection library, chunked background downloads, and exclusion blacklist.
* **Columns Added to `favorites`:**
  - `character TEXT`, `source TEXT`, `file_path TEXT`, `file_size INTEGER`, `download_status TEXT`, `download_progress INTEGER`, `error_message TEXT`
* **Tables Created:**
  - `collections` (`id TEXT PRIMARY KEY`, `name TEXT NOT NULL UNIQUE`, `description TEXT`, `created_at TIMESTAMP`, `updated_at TIMESTAMP`)
  - `collection_items` (`collection_id TEXT`, `wallpaper_id TEXT`, `added_at TIMESTAMP`, PRIMARY KEY (`collection_id`, `wallpaper_id`), FOREIGN KEY `collection_id` REFERENCES `collections(id)` ON DELETE CASCADE)
  - `blacklist` (`wallpaper_id TEXT PRIMARY KEY`, `url TEXT`, `anime TEXT`, `character TEXT`, `resolution TEXT`, `reason TEXT`, `blacklisted_at TIMESTAMP`)
* **Starter Seed:** Seeded default collections: *Masterpieces* and *Cinematic Nights*.

---

### Migration v6 — Intelligent Personalization & Taste Learning Engine
* **Purpose:** Privacy-first, local SQLite learning of user aesthetic preferences.
* **Tables Created:**
  - `recommendation_settings` (`key TEXT PRIMARY KEY`, `value TEXT NOT NULL`)
  - `interaction_events`:
    - `id INTEGER PRIMARY KEY AUTOINCREMENT`
    - `wallpaper_id TEXT`, `event_type TEXT`, `anime TEXT`, `character TEXT`, `dwell_seconds REAL`, `weight_delta REAL`, `created_at TIMESTAMP`
  - `preference_scores`:
    - `entity_type TEXT NOT NULL`, `entity_name TEXT NOT NULL`, `learned_score REAL DEFAULT 0.0`, `manual_score REAL DEFAULT 0.0`, `interaction_count INTEGER`, `dwell_total_seconds REAL`, `favorites_count INTEGER`, `skips_count INTEGER`, `revisits_count INTEGER`, `updated_at TIMESTAMP`
    - `PRIMARY KEY (entity_type, entity_name)`

---

### Migration v7 — Artwork Technical Quality & Popularity Scoring
* **Purpose:** Pre-queue evaluation of technical image quality and audience popularity.
* **Columns Added to `wallpaper_lifecycle`:**
  - `quality_score REAL`, `technical_score REAL`, `popularity_score REAL`, `dimension_x INTEGER`, `dimension_y INTEGER`, `file_size INTEGER`, `views INTEGER`, `favorites INTEGER`, `scored_at TIMESTAMP`
* **Tables Created:**
  - `quality_settings` (`id INTEGER PRIMARY KEY CHECK(id = 1)`, `min_quality_score REAL`, `prefer_native_res INTEGER`, `prefer_aspect_ratio INTEGER`, `avoid_too_dark INTEGER`, `avoid_too_bright INTEGER`, `popularity_weight REAL`, `technical_weight REAL`, `target_resolution TEXT`, `target_aspect_ratio TEXT`, `updated_at TIMESTAMP`)

---

### Migration v8 — Intelligent Slideshow Scheduling System
* **Purpose:** Configurable pacing strategies (fixed, random, quality-weighted, dayparting, franchise rotation, manual).
* **Tables Created:**
  - `scheduler_settings` (`id INTEGER PRIMARY KEY CHECK(id = 1)`, `strategy TEXT DEFAULT 'fixed'`, `fixed_seconds INTEGER`, `random_min INTEGER`, `random_max INTEGER`, `day_seconds INTEGER`, `evening_seconds INTEGER`, `night_seconds INTEGER`, `cinematic_seconds INTEGER`, `dashboard_seconds INTEGER`, `quality_bonus_enabled INTEGER`, `pause_on_hidden INTEGER`, `franchise_rotation_interval INTEGER`, `updated_at TIMESTAMP`)

---

### Migration v9 — Ambient Nature Soundscape Engine
* **Purpose:** Local procedural audio synthesis, volume control, mute state, and crossfading.
* **Tables Created:**
  - `soundscape_settings` (`id INTEGER PRIMARY KEY CHECK(id = 1)`, `enabled INTEGER DEFAULT 0`, `current_track TEXT DEFAULT 'rain'`, `volume INTEGER DEFAULT 40`, `muted INTEGER DEFAULT 1`, `crossfade_seconds REAL DEFAULT 2.5`, `updated_at TIMESTAMP`)

---

### Migration v10 — Intelligent Composition & Focal-Point Protection
* **Purpose:** Hardware-composited multi-monitor framing and multi-character centroid anchors.
* **Tables Created:**
  - `wallpaper_composition` (`wallpaper_id TEXT PRIMARY KEY`, `focal_x REAL DEFAULT 50.0`, `focal_y REAL DEFAULT 50.0`, `display_mode TEXT DEFAULT 'fill'`, `blurred_background INTEGER DEFAULT 1`, `landscape_display_mode TEXT`, `portrait_display_mode TEXT`, `character_count INTEGER DEFAULT 1`, `characters_json TEXT DEFAULT '[]'`, `updated_at TIMESTAMP`, FOREIGN KEY `wallpaper_id` REFERENCES `wallpaper_lifecycle(id)` ON DELETE CASCADE)
  - `composition_settings` (`id INTEGER PRIMARY KEY CHECK(id = 1)`, `default_mode_landscape TEXT`, `default_mode_portrait TEXT`, `default_mode_ultrawide TEXT`, `blurred_backdrop_enabled INTEGER`, `blur_intensity_px INTEGER`, `backdrop_opacity REAL`, `auto_focal_protection INTEGER`, `updated_at TIMESTAMP`)

---

### Migration v11 — Enhanced Artwork Provenance Metadata
* **Purpose:** Transparent attribution on the interactive artwork information panel (<kbd>I</kbd>).
* **Columns Added to `wallpaper_lifecycle`:**
  - `uploader TEXT`
  - `upload_date TEXT`
  - `source_url TEXT`

---

### Migration v12 — Advanced Anime Ambient Control Center Settings
* **Purpose:** Key-value persistence for all 6 Control Center sections (General, Wallpaper, Visual, Display, Performance, Privacy).
* **Tables Created:**
  - `control_center_settings` (`section TEXT NOT NULL`, `setting_key TEXT NOT NULL`, `setting_value TEXT NOT NULL`, `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`, `PRIMARY KEY (section, setting_key)`)

---

### Migration v13 — Backup, Recovery & Audit Management
* **Purpose:** Backup archive cataloging, integrity auditing, and automated pre-migration/pre-restore snapshot tracking.
* **Tables Created:**
  - `backup_records`:
    - `id TEXT PRIMARY KEY`
    - `filename TEXT NOT NULL`
    - `backup_type TEXT NOT NULL`
    - `file_size INTEGER DEFAULT 0`
    - `schema_version INTEGER DEFAULT 13`
    - `wallpapers_count INTEGER DEFAULT 0`
    - `favorites_count INTEGER DEFAULT 0`
    - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `status TEXT DEFAULT 'valid'`
    - `checksum TEXT` (SHA-256 digest of the archive)
* **Indexes:**
  - `idx_backup_created ON backup_records(created_at)`

---

### Migration v14 — Verified Franchise Tag Intelligence & Provenance Tracking
* **Purpose:** Enhances the franchise search engine with verified Wallhaven numeric tag IDs (`id:<tag_id>`), alias resolutions, character tag mappings, ambiguity guard exclusions, and local tag metadata caching.
* **Columns Added:**
  - `wallpaper_lifecycle.query_strategy TEXT DEFAULT 'verified_tag_id'` (Records provenance: `verified_tag_id`, `character_tag_id`, `franchise_keyword`, `alias_keyword`, `character_keyword`, `booru_failover`).
* **Tables Created:**
  - `verified_tag_cache`:
    - `tag_id INTEGER PRIMARY KEY`
    - `tag_name TEXT NOT NULL`
    - `category TEXT`
    - `purity TEXT`
    - `verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `raw_metadata TEXT` (JSON-encoded live API response)
  - `franchise_catalog`:
    - `slug TEXT PRIMARY KEY`
    - `name TEXT NOT NULL`
    - `catalog_json TEXT NOT NULL`
    - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
* **Indexes:**
  - `idx_tag_cache_name ON verified_tag_cache(tag_name)`

---

### Migration v15 — Unified Artwork Safety and Moderation Layer
* **Purpose:** Establishes a provider-independent content safety layer enforcing strict SFW anime artwork compliance, multi-attribute tag inspection, cascading blocklists, and manual review queue.
* **Columns Added to `wallpaper_lifecycle`:**
  - `safety_rating TEXT DEFAULT 'SAFE'` (Internal classification: `SAFE`, `QUESTIONABLE`, `EXPLICIT`, `AMBIGUOUS`, `BLOCKED`)
  - `safety_reason TEXT DEFAULT 'verified_sfw'` (Auditing rationale for classification)
  - `provider_purity_raw TEXT` (Original untouched upstream rating: e.g. `100`, `sfw`, `general`, `q`)
* **Tables Created:**
  - `blocked_entities`:
    - `id INTEGER PRIMARY KEY AUTOINCREMENT`
    - `entity_type TEXT NOT NULL` (`artwork`, `tag`, `character`, `franchise`, `artist`)
    - `entity_value TEXT NOT NULL`
    - `reason TEXT`
    - `blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `UNIQUE(entity_type, entity_value)`
  - `wallpaper_review_queue`:
    - `id TEXT PRIMARY KEY`
    - `wallpaper_json TEXT NOT NULL`
    - `failure_reason TEXT NOT NULL`
    - `safety_rating TEXT NOT NULL`
    - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
    - `reviewed_at TIMESTAMP`
    - `review_decision TEXT DEFAULT 'PENDING'` (`PENDING`, `APPROVED`, `REJECTED`)
  - `safety_policy_settings`:
    - `id INTEGER PRIMARY KEY CHECK(id=1)`
    - `strict_mode INTEGER DEFAULT 1`
    - `min_tags_required INTEGER DEFAULT 1`
    - `allow_review_queue INTEGER DEFAULT 1`
    - `auto_block_reported INTEGER DEFAULT 1`
    - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
* **Indexes:**
  - `idx_blocked_entities_lookup ON blocked_entities(entity_type, entity_value)`
  - `idx_review_queue_decision ON wallpaper_review_queue(review_decision)`

---

### Migration v16 — Wallhaven API Compatibility & Contract Engine
* **Purpose:** Persists Wallhaven API v1 contract test outcomes, schema version tracking, verified vs degraded parameter states, and failure diagnostics.
* **Tables Created:**
  - `wallhaven_compatibility_status`:
    - `id INTEGER PRIMARY KEY CHECK(id=1)`
    - `status TEXT NOT NULL DEFAULT 'COMPATIBLE'` (`COMPATIBLE`, `DEGRADED`, `INCOMPATIBLE_SAFETY_VIOLATION`, `INCOMPATIBLE`)
    - `schema_version TEXT DEFAULT 'v1'`
    - `last_checked_at TIMESTAMP`
    - `last_success_at TIMESTAMP`
    - `is_live_check INTEGER DEFAULT 0`
    - `verified_params_json TEXT DEFAULT '[]'`
    - `degraded_params_json TEXT DEFAULT '[]'`
    - `rejected_params_json TEXT DEFAULT '[]'`
    - `uncertain_params_json TEXT DEFAULT '[]'`
    - `diagnostics_json TEXT DEFAULT '[]'`
    - `raw_meta_json TEXT DEFAULT '{}'`
    - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

---

## 🔍 Database Integrity Checking Protocol

KURO provides multi-stage automated and on-demand database verification:

1. **Quick Check:** Executed during normal health probes via `PRAGMA quick_check;`.
2. **Deep Integrity Check:** Available via `GET /api/database/integrity`, executing:
   - `PRAGMA integrity_check(100);` — Inspects B-trees, page references, freelists, and record headers.
   - `PRAGMA foreign_key_check;` — Verifies relational constraints across collections and composition tables.
   - Table census comparing SQLite schema catalog against expected table counts.
3. **Archive Pre-Restore Verification:** Every backup archive must pass an internal `PRAGMA integrity_check` on its extracted SQLite database copy before any restoration is allowed to proceed.
