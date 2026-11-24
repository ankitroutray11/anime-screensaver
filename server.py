#!/usr/bin/env python3
"""
KURO // ANIME — Dark Anime Screensaver Local Server (Production Hardened)
Features:
- Thread-safe HTTP request handling on strictly 127.0.0.1.
- SQLite WAL mode with safe transactions & graceful shutdown checkpointing.
- Multi-layer API versioning (/api/v1/... and /api/... backward compatibility).
- Local session token verification on state-changing endpoints (Anti-CSRF).
- Origin and Referer validation (Anti-DNS Rebinding).
- SSRF prevention on favorite image downloads.
- Path traversal prevention on local image streaming & static files.
- Bounded request size and strict regex/length input validation.
- Standardized structured JSON error responses.
- Application health endpoint (/api/health and /api/v1/health).
- Standard library rotating file logging (kuro_server.log).
"""

import os
import sys
import json
import time
import signal
import socket
import logging
import secrets
import mimetypes
import threading
import webbrowser
import urllib.parse
import urllib.request
from logging.handlers import RotatingFileHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from database import DatabaseManager
from engine import WallpaperEngine
from franchise_registry import FranchiseRegistry, FRANCHISE_REGISTRY
from monitor_detector import MonitorDetector
from security import SecurityManager, MAX_CONTENT_LENGTH
from cache_manager import CacheManager
from favorites_downloader import FavoritesDownloader
from quality_scorer import QualityScorer
from scheduler import SlideshowScheduler
from soundscape_manager import SoundscapeManager
from backup_manager import BackupManager
from performance_tracker import PerformanceTracker
from download_autosaver import DownloadAutoSaver

PORT = 54321
HOST = "127.0.0.1"
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
FAVORITES_DIR = BASE_DIR / "favorites"
DB_PATH = BASE_DIR / "kuro_database.db"
LOG_PATH = BASE_DIR / "kuro_server.log"
PID_FILE = BASE_DIR / ".kuro.pid"
PORT_FILE = BASE_DIR / ".kuro.port"
CONFIG_FILE = BASE_DIR / "launcher_config.json"

CACHE_DIR.mkdir(exist_ok=True)
FAVORITES_DIR.mkdir(exist_ok=True)

# --- PRODUCTION LOGGING & ROTATION ---
logger = logging.getLogger("kuro_server")
logger.setLevel(logging.INFO)

# Rotating File Handler: max 5MB, keep 3 backup logs
file_handler = RotatingFileHandler(
    str(LOG_PATH),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s: %(message)s")
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Standard console stream handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(file_formatter)
logger.addHandler(console_handler)

# --- SYSTEM INITIALIZATION ---
SERVER_START_TIME = time.time()
security_manager = SecurityManager()
db_manager = DatabaseManager(DB_PATH)
engine = WallpaperEngine(db_manager)
scheduler = SlideshowScheduler(db_manager.get_scheduler_settings())
engine.scheduler = scheduler
soundscape_manager = SoundscapeManager(BASE_DIR / "soundscapes")
favorites_downloader = FavoritesDownloader(db_manager, FAVORITES_DIR)
backup_manager = BackupManager(db_manager, BASE_DIR)
performance_tracker = PerformanceTracker()
autosaver = DownloadAutoSaver(base_dir=BASE_DIR)
engine.autosaver = autosaver
GLOBAL_SHUTDOWN_FUNC = None
SECONDARY_BROWSER_PROC = None


class DualScreenManager:
    """Coordinates dual-monitor screensaver state, 32:9 panorama span, and synchronized playback."""
    _lock = threading.Lock()
    _state: Dict[str, Any] = {
        "mode": "span",  # "span" | "sync" | "independent"
        "active_span_wallpaper": None,
        "screen_wallpapers": {},
        "last_transition_id": "",
        "timestamp": 0.0,
        "bezel_compensation_px": 0
    }

    @classmethod
    def get_state(cls) -> Dict[str, Any]:
        with cls._lock:
            st = dict(cls._state)
            st["screen_wallpapers"] = dict(cls._state["screen_wallpapers"])
            return st

    @classmethod
    def update_state(cls, updates: Dict[str, Any]) -> Dict[str, Any]:
        with cls._lock:
            for k in ["mode", "bezel_compensation_px"]:
                if k in updates:
                    cls._state[k] = updates[k]
            cls._state["timestamp"] = time.time()
            return dict(cls._state)

    @classmethod
    def set_active_span_wallpaper(cls, wallpaper: Dict[str, Any]) -> str:
        with cls._lock:
            cls._state["active_span_wallpaper"] = wallpaper
            tid = secrets.token_hex(4)
            cls._state["last_transition_id"] = tid
            cls._state["timestamp"] = time.time()
            return tid

    @classmethod
    def get_active_span_wallpaper(cls) -> Optional[Dict[str, Any]]:
        with cls._lock:
            return cls._state.get("active_span_wallpaper")

    @classmethod
    def set_screen_wallpaper(cls, screen_id: str, wallpaper: Dict[str, Any]):
        with cls._lock:
            cls._state["screen_wallpapers"][str(screen_id)] = {
                "wallpaper": wallpaper,
                "timestamp": time.time()
            }

    @classmethod
    def get_screen_wallpaper(cls, screen_id: str) -> Optional[Dict[str, Any]]:
        with cls._lock:
            entry = cls._state["screen_wallpapers"].get(str(screen_id))
            return entry.get("wallpaper") if entry else None

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.is_running = True

class KuroHandler(BaseHTTPRequestHandler):
    server_version = "KuroAnimeHTTP/3.5"

    def send_response(self, code, message=None):
        self._status_code = code
        super().send_response(code, message)

    def send_cors_headers(self, origin: Optional[str] = None):
        """Sends security-hardened CORS headers validating localhost origins."""
        port = self.server.server_address[1]
        if origin and SecurityManager.is_trusted_origin(origin, port):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Kuro-Token")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")

    def send_json_response(self, data: Any, status: int = 200, origin: Optional[str] = None):
        """Sends a JSON response with appropriate headers."""
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors_headers(origin)
        self.end_headers()
        self.wfile.write(body)

    def send_json_error(self, code: str, message: str, status: int = 400, details: Any = None, origin: Optional[str] = None):
        """Sends a structured JSON error response."""
        err_payload, _ = SecurityManager.json_error(code, message, status=status, details=details)
        self.send_json_response(err_payload, status=status, origin=origin)

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        port = self.server.server_address[1]
        if origin and not SecurityManager.is_trusted_origin(origin, port):
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.send_cors_headers(origin)
        self.end_headers()

    def _normalize_route(self, raw_path: str) -> str:
        """Normalizes versioned /api/v1/... and legacy /api/... endpoints to canonical path."""
        p = raw_path
        if p.startswith("/api/v1/"):
            p = "/api/" + p[8:]
        return p

    def do_GET(self):
        t0 = time.perf_counter()
        try:
            self._do_GET_internal()
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            status_code = getattr(self, "_status_code", 200)
            performance_tracker.record_request(self.path, duration_ms, status_code)

    def _do_GET_internal(self):
        parsed = urllib.parse.urlparse(self.path)
        raw_path = parsed.path
        path = self._normalize_route(raw_path)
        query = urllib.parse.parse_qs(parsed.query)
        origin = self.headers.get("Origin")
        referer = self.headers.get("Referer")
        port = self.server.server_address[1]

        # Origin validation: Reject foreign origins on API endpoints
        if (origin and not SecurityManager.is_trusted_origin(origin, port)) or \
           (referer and not SecurityManager.is_trusted_origin(referer, port)):
            logger.warning(f"Rejected untrusted origin/referer: Origin={origin}, Referer={referer}")
            self.send_json_error("FORBIDDEN_ORIGIN", "Cross-origin access restricted to localhost", status=403, origin=origin)
            return

        # -------------------------------------------------------------
        # 1. Health & Diagnostics Endpoint (/api/health & /api/v1/health)
        # -------------------------------------------------------------
        if path == "/api/health":
            db_healthy = db_manager.run_integrity_check()
            worker_alive = bool(engine.worker_thread and engine.worker_thread.is_alive())
            overall_status = "healthy" if (db_healthy and worker_alive) else "degraded"

            health_info = {
                "status": overall_status,
                "uptime_seconds": round(time.time() - SERVER_START_TIME, 2),
                "server": {
                    "version": self.server_version,
                    "host": HOST,
                    "port": port
                },
                "database": {
                    "connected": True,
                    "integrity_check": "ok" if db_healthy else "failed",
                    "wal_mode": True
                },
                "worker": {
                    "state": engine.worker_state,
                    "alive": worker_alive
                },
                "network": {
                    "online": engine.is_online,
                    "consecutive_failures": engine.consecutive_network_failures,
                    "active_level": engine.active_level
                },
                "cache": engine.cache_manager.get_cache_stats(),
                "timestamp": int(time.time())
            }
            self.send_json_response(health_info, status=200 if db_healthy else 503, origin=origin)
            return

        # -------------------------------------------------------------
        # Diagnostics & Performance Metrics (/api/metrics & /api/v1/metrics)
        # -------------------------------------------------------------
        if path in ["/api/metrics", "/api/v1/metrics"]:
            metrics_snapshot = performance_tracker.get_performance_snapshot(
                engine=engine,
                db_manager=db_manager,
                cache_manager=engine.cache_manager,
                server_start_time=SERVER_START_TIME
            )
            self.send_json_response(metrics_snapshot, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Artwork Providers & Failover Status (/api/providers & /api/v1/providers)
        # -------------------------------------------------------------
        if path in ["/api/providers", "/api/v1/providers"]:
            prov_diag = engine.provider_manager.get_diagnostics() if hasattr(engine, "provider_manager") else {}
            self.send_json_response(prov_diag, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 2. Local Session Handshake (/api/session & /api/v1/session)
        # -------------------------------------------------------------
        if path in ["/api/session", "/api/auth/token"]:
            # Only delivers token to trusted local clients
            self.send_json_response({"session_token": security_manager.session_token}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 3. Next Wallpaper Candidate (/api/next & /api/v1/next)
        # -------------------------------------------------------------
        if path == "/api/next":
            raw_anime = query.get("anime", query.get("mood", ["all"]))[0]
            raw_char = query.get("character", [None])[0]
            raw_ratio = query.get("ratio", ["landscape"])[0]
            raw_screen = query.get("screen", [None])[0]
            raw_dual_mode = query.get("dual_mode", [None])[0]
            raw_media_type = query.get("media_type", [None])[0]

            # Input validation & sanitization
            anime = SecurityManager.sanitize_string(raw_anime, max_len=64, default="all")
            character = SecurityManager.sanitize_string(raw_char, max_len=64, default="") if raw_char and raw_char != "all" else None
            ratio = SecurityManager.sanitize_string(raw_ratio, max_len=16, default="landscape")
            screen = SecurityManager.sanitize_string(raw_screen, max_len=16, default="") if raw_screen else None
            dual_mode = SecurityManager.sanitize_string(raw_dual_mode, max_len=16, default="") if raw_dual_mode else DualScreenManager.get_state().get("mode", "span")

            if raw_media_type:
                media_type = SecurityManager.sanitize_string(raw_media_type, max_len=16, default="all")
            else:
                gif_cfg = db_manager.get_gif_settings()
                media_type = gif_cfg.get("mode", "all") if gif_cfg.get("enabled", True) else "static"

            selected_f = query.get("selected_franchises", [None])[0]
            selected_franchises = [
                SecurityManager.sanitize_string(s, max_len=64)
                for s in selected_f.split(",") if SecurityManager.sanitize_string(s, max_len=64)
            ] if selected_f else None

            excluded_f = query.get("excluded_franchises", [None])[0]
            excluded_franchises = [
                SecurityManager.sanitize_string(s, max_len=64)
                for s in excluded_f.split(",") if SecurityManager.sanitize_string(s, max_len=64)
            ] if excluded_f else None

            excluded_c = query.get("excluded_characters", [None])[0]
            excluded_characters = [
                SecurityManager.sanitize_string(s, max_len=64)
                for s in excluded_c.split(",") if SecurityManager.sanitize_string(s, max_len=64)
            ] if excluded_c else None

            # Handle dual-screen span mode synchronization & prevent mirroring
            s0_wp = DualScreenManager.get_screen_wallpaper("0")
            s0_id = s0_wp.get("id") if s0_wp else None

            if dual_mode == "span" and screen in ("1", "right", "secondary"):
                active_span = DualScreenManager.get_active_span_wallpaper()
                st = DualScreenManager.get_state()
                if active_span and (time.time() - st.get("timestamp", 0) < 90):
                    dim_x = active_span.get("dimension_x") or 0
                    dim_y = active_span.get("dimension_y") or 1
                    is_true_32_9 = (
                        active_span.get("is_dual_span") or
                        active_span.get("aspect_ratio") in ("32:9", "dual", "32x9") or
                        active_span.get("ratio") == "32:9" or
                        (dim_x / dim_y >= 2.8)
                    )
                    if is_true_32_9:
                        item = dict(active_span)
                        item["screen_index"] = 1
                        item["is_dual_span"] = True
                        item["span_role"] = "right"
                        self.send_json_response(item, status=200, origin=origin)
                        return

            query_ratio = "dual" if (dual_mode == "span" and screen not in ("1", "right", "secondary") and ratio in ("dual", "32:9", "32x9", "dual_screen", "landscape")) else ratio
            item = engine.get_next(
                anime=anime,
                character=character,
                selected_franchises=selected_franchises,
                excluded_franchises=excluded_franchises,
                excluded_characters=excluded_characters,
                ratio=query_ratio,
                media_type=media_type
            )

            # Never mirror Screen 0 on Screen 1 if it's not a 32:9 span
            if screen in ("1", "right", "secondary") and s0_id and item.get("id") == s0_id:
                item = engine.get_next(
                    anime=anime,
                    character=character,
                    selected_franchises=selected_franchises,
                    excluded_franchises=excluded_franchises,
                    excluded_characters=excluded_characters,
                    ratio="landscape",
                    media_type=media_type
                )

            dim_x = item.get("dimension_x") or 0
            dim_y = item.get("dimension_y") or 1
            is_dual_span = (query_ratio == "dual" or item.get("aspect_ratio") in ("32:9", "dual", "32x9") or (dim_x / dim_y >= 2.8))
            if is_dual_span and dual_mode == "span":
                DualScreenManager.set_active_span_wallpaper(item)
                item["is_dual_span"] = True
                item["span_role"] = "left" if screen in ("0", "left", "primary", None) else "right"
                item["screen_index"] = 0 if screen in ("0", "left", "primary", None) else 1
            else:
                item["is_dual_span"] = False
                item["span_role"] = "single"
                item["screen_index"] = 1 if screen in ("1", "right", "secondary") else 0

            if screen:
                DualScreenManager.set_screen_wallpaper(screen, item)
            else:
                DualScreenManager.set_screen_wallpaper("0", item)

            self.send_json_response(item, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 4. Stream Local/Cached/Curated Image (/api/image/<id>)
        # -------------------------------------------------------------
        if path.startswith("/api/image/"):
            img_id = path.replace("/api/image/", "").strip()
            if not SecurityManager.validate_id(img_id):
                self.send_json_error("INVALID_IMAGE_ID", "Invalid or malformed image identifier", status=400, origin=origin)
                return

            found_file = None

            # 1. Check database for committed local_path
            with db_manager.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT local_path FROM wallpaper_lifecycle WHERE id = ?", (img_id,))
                row = cur.fetchone()

            if row and row[0]:
                candidate = (BASE_DIR / row[0]).resolve()
                if candidate.is_file() and candidate.is_relative_to(BASE_DIR):
                    found_file = candidate

            # 2. Check curated_wallpapers/
            if not found_file:
                curated_dir = BASE_DIR / "curated_wallpapers"
                for ext in [".svg", ".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                    c_cand = (curated_dir / f"{img_id}{ext}").resolve()
                    if c_cand.is_file() and c_cand.is_relative_to(BASE_DIR):
                        found_file = c_cand
                        break

            # 3. Check .cache/wallpapers/
            if not found_file:
                cache_dir = BASE_DIR / ".cache" / "wallpapers"
                for ext in [".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif"]:
                    c_cand = (cache_dir / f"{img_id}{ext}").resolve()
                    if c_cand.is_file() and c_cand.is_relative_to(BASE_DIR):
                        found_file = c_cand
                        break

            # 4. Check favorites/
            if not found_file:
                fav_dir = BASE_DIR / "favorites"
                for ext in [".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif"]:
                    f_cand = (fav_dir / f"{img_id}{ext}").resolve()
                    if f_cand.is_file() and f_cand.is_relative_to(BASE_DIR):
                        found_file = f_cand
                        break

            if found_file and found_file.is_file():
                # Disallow unexpected non-image file formats
                allowed_exts = {".svg", ".jpg", ".jpeg", ".png", ".webp", ".gif"}
                if found_file.suffix.lower() not in allowed_exts:
                    self.send_json_error("FORBIDDEN_FILE_TYPE", "File type not allowed", status=403, origin=origin)
                    return

                # Record cache hit if found_file is inside .cache/wallpapers
                is_hit = False
                try:
                    cache_dir = (BASE_DIR / ".cache" / "wallpapers").resolve()
                    if found_file.resolve().is_relative_to(cache_dir):
                        is_hit = True
                except Exception:
                    pass
                engine.cache_manager.record_lookup(hit=is_hit)

                mime_type, _ = mimetypes.guess_type(str(found_file))
                mime_type = mime_type or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(found_file.stat().st_size))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_cors_headers(origin)
                self.end_headers()
                with open(found_file, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                engine.cache_manager.record_lookup(hit=False)
                self.send_json_error("IMAGE_NOT_FOUND", "Requested image not found in local cache or curated pool", status=404, origin=origin)
                return

        # -------------------------------------------------------------
        # 5. Franchise Registry & Tag Intelligence (/api/franchises, /api/franchises/catalog, /api/franchises/tags/cached)
        # -------------------------------------------------------------
        if path in ["/api/franchises/catalog", "/api/v1/franchises/catalog"]:
            catalog = FranchiseRegistry.get_catalog()
            cached_tags = db_manager.get_all_cached_tags()
            self.send_json_response({
                "catalog": catalog,
                "total_franchises": len(catalog),
                "cached_tags_count": len(cached_tags)
            }, status=200, origin=origin)
            return

        if path in ["/api/franchises/tags/cached", "/api/v1/franchises/tags/cached"]:
            cached_tags = db_manager.get_all_cached_tags()
            self.send_json_response({"cached_tags": cached_tags, "count": len(cached_tags)}, status=200, origin=origin)
            return

        if path in ["/api/franchises", "/api/anime-list"]:
            franchise_summary = [
                {
                    "slug": f["slug"],
                    "name": f["name"],
                    "characters": list(f.get("characters", {}).keys()),
                    "wallhaven_tag_ids": f.get("wallhaven_tag_ids", [])
                }
                for f in FranchiseRegistry.get_all()
            ]
            self.send_json_response(franchise_summary, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 6. Monitors Topology (/api/monitors & /api/v1/monitors)
        # -------------------------------------------------------------
        if path == "/api/monitors":
            monitors = MonitorDetector.get_connected_monitors()
            dual_topo = MonitorDetector.get_dual_monitor_topology()
            self.send_json_response({
                "monitors": monitors,
                "count": len(monitors),
                "dual_topology": dual_topo
            }, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 6b. Dual Screen Synchronization State (/api/dual/state)
        # -------------------------------------------------------------
        if path in ["/api/dual/state", "/api/v1/dual/state"]:
            st = DualScreenManager.get_state()
            topo = MonitorDetector.get_dual_monitor_topology()
            self.send_json_response({
                "dual_state": st,
                "topology": topo
            }, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 6c. Auto-Saved Downloads Status (/api/downloads/status)
        # -------------------------------------------------------------
        if path in ["/api/downloads/status", "/api/v1/downloads/status"]:
            self.send_json_response(autosaver.get_stats(), status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 6d. Animated GIF Playback Settings (/api/gif/settings)
        # -------------------------------------------------------------
        if path in ["/api/gif/settings", "/api/v1/gif/settings"]:
            self.send_json_response(db_manager.get_gif_settings(), status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 7. Statistics & Status (/api/stats & /api/status)
        # -------------------------------------------------------------
        if path in ["/api/stats", "/api/status", "/api/network-status"]:
            stats = engine.get_stats()
            self.send_json_response(stats, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 8. Wallpaper History & Explorer (/api/history & /api/history/export)
        # -------------------------------------------------------------
        if path in ["/api/history/export", "/api/v1/history/export"]:
            export_fmt = query.get("format", ["json"])[0]
            franchise = query.get("franchise", [None])[0]
            character = query.get("character", [None])[0]
            date_filter = query.get("date_filter", [None])[0]
            resolution = query.get("resolution", [None])[0]
            favs_only = query.get("favorites_only", ["0"])[0].lower() in ["1", "true", "yes"]
            search_q = query.get("q", query.get("search", [None]))[0]

            content, content_type = db_manager.export_wallpaper_history(
                export_format=export_fmt,
                franchise=franchise,
                character=character,
                date_filter=date_filter,
                resolution=resolution,
                favorites_only=favs_only,
                search_query=search_q
            )
            body_bytes = content.encode("utf-8")
            ext = "csv" if export_fmt.lower() == "csv" else "json"
            filename = f"kuro_wallpaper_history_{int(time.time())}.{ext}"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body_bytes)))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        if path in ["/api/history", "/api/v1/history", "/api/history/explorer", "/api/v1/history/explorer"]:
            is_explorer_view = (
                path.endswith("/explorer") or
                "page" in query or
                "search" in query or
                "q" in query or
                "franchise" in query or
                "character" in query or
                "date_filter" in query or
                "resolution" in query or
                "favorites_only" in query or
                "sort_by" in query or
                query.get("view", [""])[0] == "explorer"
            )

            if is_explorer_view:
                try:
                    page = max(1, int(query.get("page", ["1"])[0]))
                except ValueError:
                    page = 1

                try:
                    page_size = max(1, min(100, int(query.get("page_size", query.get("limit", ["24"]))[0])))
                except ValueError:
                    page_size = 24

                franchise = query.get("franchise", [None])[0]
                character = query.get("character", [None])[0]
                date_filter = query.get("date_filter", [None])[0]
                resolution = query.get("resolution", [None])[0]
                favs_only = query.get("favorites_only", ["0"])[0].lower() in ["1", "true", "yes"]
                sort_by = query.get("sort_by", ["newest"])[0]
                search_q = query.get("q", query.get("search", [None]))[0]

                history_data = db_manager.get_wallpaper_history(
                    page=page,
                    page_size=page_size,
                    franchise=franchise,
                    character=character,
                    date_filter=date_filter,
                    resolution=resolution,
                    favorites_only=favs_only,
                    sort_by=sort_by,
                    search_query=search_q
                )
                self.send_json_response(history_data, status=200, origin=origin)
                return
            else:
                try:
                    limit_val = int(query.get("limit", ["50"])[0])
                except ValueError:
                    limit_val = 50
                history = db_manager.get_recent_history(limit=limit_val)
                self.send_json_response(history, status=200, origin=origin)
                return

        # -------------------------------------------------------------
        # 9. Favorites List & Filters (/api/favorites & /api/v1/favorites)
        # -------------------------------------------------------------
        if path in ["/api/favorites", "/api/favorite"]:
            franchise = query.get("franchise", query.get("mood", [None]))[0]
            resolution = query.get("resolution", [None])[0]
            character = query.get("character", [None])[0]
            search = query.get("search", [None])[0]
            favs = db_manager.get_favorites(
                franchise=franchise,
                resolution=resolution,
                character=character,
                search=search
            )
            self.send_json_response(favs, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 10. Collections & Collection Items (/api/collections & items)
        # -------------------------------------------------------------
        if path.startswith("/api/collections/") and path.endswith("/items"):
            prefix_len = len("/api/collections/")
            col_id = path[prefix_len:-len("/items")].strip("/")
            franchise = query.get("franchise", [None])[0]
            resolution = query.get("resolution", [None])[0]
            character = query.get("character", [None])[0]
            search = query.get("search", [None])[0]
            items = db_manager.get_collection_wallpapers(
                collection_id=col_id,
                franchise=franchise,
                resolution=resolution,
                character=character,
                search=search
            )
            self.send_json_response(items, status=200, origin=origin)
            return

        if path in ["/api/collections", "/api/collection-list"]:
            collections = db_manager.get_collections()
            self.send_json_response(collections, status=200, origin=origin)
            return

        if path == "/api/collections/items":
            col_id = query.get("id", query.get("collection_id", [None]))[0]
            if not col_id:
                self.send_json_error("MISSING_PARAM", "Missing collection ID parameter", status=400, origin=origin)
                return
            franchise = query.get("franchise", [None])[0]
            resolution = query.get("resolution", [None])[0]
            character = query.get("character", [None])[0]
            search = query.get("search", [None])[0]
            items = db_manager.get_collection_wallpapers(
                collection_id=col_id,
                franchise=franchise,
                resolution=resolution,
                character=character,
                search=search
            )
            self.send_json_response(items, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 11. Blacklist Query (/api/blacklist & /api/v1/blacklist)
        # -------------------------------------------------------------
        if path in ["/api/blacklist"]:
            b_list = db_manager.get_blacklist()
            self.send_json_response(b_list, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 12. Library Statistics & Storage (/api/library/stats)
        # -------------------------------------------------------------
        if path in ["/api/library/stats", "/api/library-stats"]:
            l_stats = db_manager.get_library_stats(BASE_DIR)
            self.send_json_response(l_stats, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 13. Launcher Config (/api/launcher/config & /api/v1/launcher/config)
        # -------------------------------------------------------------
        if path in ["/api/launcher/config", "/api/launcher-config"]:
            cfg = {}
            if CONFIG_FILE.is_file():
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            self.send_json_response(cfg, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 14. Recommendations & Personalization Profile (/api/recommendations/profile)
        # -------------------------------------------------------------
        if path in ["/api/recommendations/profile", "/api/recommendations/stats", "/api/preferences/profile"]:
            profile = engine.recommendation_engine.get_profile()
            self.send_json_response(profile, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 15. Artwork Quality Scoring Settings & Statistics (/api/quality/settings, /api/quality/scores)
        # -------------------------------------------------------------
        if path in ["/api/quality/settings", "/api/v1/quality/settings"]:
            settings = db_manager.get_quality_settings()
            self.send_json_response(settings, status=200, origin=origin)
            return

        if path in ["/api/quality/scores", "/api/v1/quality/scores", "/api/quality/stats"]:
            summary = db_manager.get_quality_scores_summary()
            self.send_json_response(summary, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 16. Slideshow Scheduler Settings (/api/scheduler/settings)
        # -------------------------------------------------------------
        if path in ["/api/scheduler/settings", "/api/v1/scheduler/settings"]:
            settings = db_manager.get_scheduler_settings()
            self.send_json_response(settings, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 17. Ambient Soundscape Catalog & Settings (/api/soundscapes)
        # -------------------------------------------------------------
        if path in ["/api/soundscapes", "/api/v1/soundscapes"]:
            catalog = soundscape_manager.list_soundscapes()
            self.send_json_response({"soundscapes": catalog}, status=200, origin=origin)
            return

        if path in ["/api/soundscapes/settings", "/api/v1/soundscapes/settings"]:
            settings = db_manager.get_soundscape_settings()
            self.send_json_response(settings, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 18. Detailed Artwork Metadata (/api/wallpaper/<id>)
        # -------------------------------------------------------------
        if path.startswith("/api/wallpaper/") or path.startswith("/api/v1/wallpaper/"):
            prefix = "/api/v1/wallpaper/" if path.startswith("/api/v1/wallpaper/") else "/api/wallpaper/"
            raw_id = path[len(prefix):]
            img_id = SecurityManager.sanitize_string(raw_id, max_len=64)
            if not SecurityManager.validate_id(img_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return

            details = db_manager.get_artwork_details(img_id)
            if details:
                self.send_json_response(details, status=200, origin=origin)
            else:
                self.send_json_error("NOT_FOUND", f"Artwork {img_id} not found", status=404, origin=origin)
            return

        # -------------------------------------------------------------
        # 19. Wallpaper Composition & Focal Point (/api/composition)
        # -------------------------------------------------------------
        if path in ["/api/composition/settings", "/api/v1/composition/settings"]:
            settings = db_manager.get_composition_settings()
            self.send_json_response(settings, status=200, origin=origin)
            return

        if path.startswith("/api/composition/") or path.startswith("/api/v1/composition/"):
            prefix = "/api/v1/composition/" if path.startswith("/api/v1/composition/") else "/api/composition/"
            raw_id = path[len(prefix):]
            img_id = SecurityManager.sanitize_string(raw_id, max_len=64)
            if not SecurityManager.validate_id(img_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return
            comp = db_manager.get_wallpaper_composition(img_id)
            if comp:
                self.send_json_response(comp, status=200, origin=origin)
            else:
                self.send_json_response({
                    "wallpaper_id": img_id,
                    "focal_x": 50.0,
                    "focal_y": 50.0,
                    "display_mode": "fill",
                    "blurred_background": True,
                    "landscape_display_mode": None,
                    "portrait_display_mode": None,
                    "character_count": 1,
                    "characters": [],
                    "is_custom": False
                }, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 20. Advanced Control Center Settings (/api/settings)
        # -------------------------------------------------------------
        if path in ["/api/settings", "/api/v1/settings"]:
            query_section = query.get("section", [None])[0]
            settings_data = db_manager.get_control_center_settings(query_section)
            self.send_json_response({"status": "ok", "settings": settings_data}, status=200, origin=origin)
            return

        if path in ["/api/settings/export", "/api/v1/settings/export"]:
            export_data = db_manager.export_full_configuration()
            self.send_json_response({"status": "ok", "export": export_data}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 21. Backup & Recovery Management (/api/backups, /api/database/integrity)
        # -------------------------------------------------------------
        if path in ["/api/backups", "/api/v1/backups"]:
            backup_manager.db_manager = db_manager
            backups_list = backup_manager.list_backups()
            integrity_info = backup_manager.check_database_integrity()
            self.send_json_response({
                "status": "ok",
                "backups": backups_list,
                "database_integrity": integrity_info,
                "total_backups": len(backups_list)
            }, status=200, origin=origin)
            return

        if path in ["/api/backups/download", "/api/v1/backups/download"]:
            filename = query.get("filename", [""])[0]
            if not filename:
                self.send_json_error("INVALID_INPUT", "Must specify filename query parameter", status=400, origin=origin)
                return
            target_path = backup_manager.get_backup_path(filename)
            if not target_path or not target_path.is_file():
                self.send_json_error("NOT_FOUND", f"Backup archive '{filename}' not found", status=404, origin=origin)
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{target_path.name}"')
            self.send_header("Content-Length", str(target_path.stat().st_size))
            self.send_header("Cache-Control", "no-cache")
            self.send_cors_headers(origin)
            self.end_headers()
            with open(target_path, "rb") as bf:
                while chunk := bf.read(65536):
                    self.wfile.write(chunk)
            return

        if path in ["/api/database/integrity", "/api/v1/database/integrity"]:
            integrity_report = db_manager.diagnose_database_integrity()
            self.send_json_response(integrity_report, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Content Safety & Moderation Layer (GET Endpoints)
        # -------------------------------------------------------------
        if path in ["/api/moderation/blocked", "/api/v1/moderation/blocked"]:
            entity_type = query.get("entity_type", [None])[0]
            blocked = db_manager.get_blocked_entities(entity_type=entity_type)
            self.send_json_response({"status": "ok", "blocked_entities": blocked, "total": len(blocked)}, status=200, origin=origin)
            return

        if path in ["/api/moderation/review-queue", "/api/v1/moderation/review-queue"]:
            try:
                limit_val = int(query.get("limit", ["50"])[0])
            except ValueError:
                limit_val = 50
            decision_val = query.get("decision", ["PENDING"])[0]
            items = db_manager.get_review_queue(limit=limit_val, decision=decision_val)
            self.send_json_response({"status": "ok", "queue": items, "total": len(items)}, status=200, origin=origin)
            return

        if path in ["/api/moderation/settings", "/api/v1/moderation/settings"]:
            settings = db_manager.get_safety_policy_settings()
            self.send_json_response({"status": "ok", "settings": settings}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 8b. Wallhaven API Contract & Compatibility Diagnostics
        # -------------------------------------------------------------
        if path in ["/api/diagnostics/wallhaven-compatibility", "/api/v1/diagnostics/wallhaven-compatibility"]:
            from wallhaven_compatibility import WallhavenCompatibilityManager
            comp_mgr = WallhavenCompatibilityManager(db_manager)
            status_report = comp_mgr.get_status()
            self.send_json_response({"status": "ok", "report": status_report}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 9. Secure Static File Delivery with Path Traversal Protection
        # -------------------------------------------------------------
        req_path = raw_path.lstrip("/")
        if not req_path:
            file_path = (BASE_DIR / "index.html").resolve()
        else:
            file_path = (BASE_DIR / req_path).resolve()

        # Security: verify file is strictly inside BASE_DIR
        try:
            if not file_path.is_relative_to(BASE_DIR):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return
        except AttributeError:
            if os.path.commonpath([str(BASE_DIR), str(file_path)]) != str(BASE_DIR):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return

        # Do not serve sensitive system or database files directly
        restricted_extensions = {".db", ".db-wal", ".db-shm", ".py", ".bat", ".vbs", ".log"}
        if file_path.suffix.lower() in restricted_extensions:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return

        if file_path.is_file():
            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.send_header("Cache-Control", "no-cache")
            self.send_cors_headers(origin)
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        t0 = time.perf_counter()
        try:
            self._do_POST_internal()
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            status_code = getattr(self, "_status_code", 200)
            performance_tracker.record_request(self.path, duration_ms, status_code)

    def _do_POST_internal(self):
        parsed = urllib.parse.urlparse(self.path)
        raw_path = parsed.path
        path = self._normalize_route(raw_path)
        origin = self.headers.get("Origin")
        referer = self.headers.get("Referer")
        port = self.server.server_address[1]

        # 1. Origin & Referer Validation (Anti-CSRF / Anti-Rebinding)
        if (origin and not SecurityManager.is_trusted_origin(origin, port)) or \
           (referer and not SecurityManager.is_trusted_origin(referer, port)):
            logger.warning(f"Rejected POST from untrusted origin: {origin or referer}")
            self.send_json_error("FORBIDDEN_ORIGIN", "State-changing operations restricted to localhost", status=403, origin=origin)
            return

        # 2. Payload size bounding (Protection against Denial of Service / Memory Exhaustion)
        content_length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(content_length_header)
        except ValueError:
            self.send_json_error("INVALID_CONTENT_LENGTH", "Malformed Content-Length header", status=400, origin=origin)
            return

        if length > MAX_CONTENT_LENGTH:
            self.send_json_error("PAYLOAD_TOO_LARGE", f"Request body exceeds {MAX_CONTENT_LENGTH} byte limit", status=413, origin=origin)
            return

        # Read body
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            self.send_json_error("MALFORMED_JSON", "Request body must be valid JSON", status=400, origin=origin)
            return

        # 3. Session Token Verification on State-Changing Endpoints
        client_token = self.headers.get("X-Kuro-Token") or payload.get("session_token")
        if not security_manager.verify_session_token(client_token):
            logger.warning(f"Rejected state-changing POST on {path}: Missing or invalid session token.")
            self.send_json_error("UNAUTHORIZED", "Missing or invalid session token (X-Kuro-Token)", status=401, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Dual Screen Synchronization (/api/dual/sync & /api/v1/dual/sync)
        # -------------------------------------------------------------
        if path in ["/api/dual/sync", "/api/v1/dual/sync"]:
            mode = payload.get("mode")
            bezel = payload.get("bezel_compensation_px")
            active_wp = payload.get("active_wallpaper")
            screen_id = payload.get("screen")
            updates = {}
            if mode in ["span", "sync", "independent"]:
                updates["mode"] = mode
            if isinstance(bezel, (int, float)):
                updates["bezel_compensation_px"] = int(bezel)
            if active_wp and isinstance(active_wp, dict):
                tid = DualScreenManager.set_active_span_wallpaper(active_wp)
                updates["last_transition_id"] = tid
            if screen_id and active_wp:
                DualScreenManager.set_screen_wallpaper(str(screen_id), active_wp)
            new_st = DualScreenManager.update_state(updates)
            self.send_json_response({"success": True, "dual_state": new_st}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Dual Screen Extension Launcher (/api/dual/launch & /api/dual/toggle)
        # -------------------------------------------------------------
        if path in ["/api/dual/launch", "/api/dual/toggle", "/api/v1/dual/launch", "/api/v1/dual/toggle"]:
            global SECONDARY_BROWSER_PROC
            action = "toggle" if "toggle" in path else payload.get("action", "launch")

            is_running = False
            if SECONDARY_BROWSER_PROC:
                try:
                    if SECONDARY_BROWSER_PROC.poll() is None:
                        is_running = True
                    else:
                        SECONDARY_BROWSER_PROC = None
                except Exception:
                    SECONDARY_BROWSER_PROC = None

            if is_running and action in ("toggle", "stop", "close"):
                try:
                    SECONDARY_BROWSER_PROC.terminate()
                    SECONDARY_BROWSER_PROC = None
                except Exception:
                    pass
                self.send_json_response({
                    "success": True,
                    "status": "closed",
                    "is_running": False,
                    "message": "Screen 2 extension closed."
                }, status=200, origin=origin)
                return

            if is_running:
                self.send_json_response({
                    "success": True,
                    "status": "already_running",
                    "is_running": True,
                    "message": "Screen 2 is already running on secondary monitor."
                }, status=200, origin=origin)
                return

            monitors = MonitorDetector.get_monitors_horizontal()
            dual_topo = MonitorDetector.get_dual_monitor_topology()
            sec_mon = None
            if len(monitors) >= 2:
                sec_mon = monitors[1]
            elif dual_topo.get("right_monitor"):
                sec_mon = dual_topo["right_monitor"]

            from launcher import get_browser_executable, load_launcher_config, DEFAULT_CONFIG
            cfg = load_launcher_config() or DEFAULT_CONFIG
            browser_exe, _ = get_browser_executable(cfg.get("browser_path"))

            if not browser_exe:
                self.send_json_error("BROWSER_NOT_FOUND", "No supported Chromium browser found (Chrome, Edge, Brave)", status=500, origin=origin)
                return

            port = self.server.server_address[1]
            url = f"http://127.0.0.1:{port}/?screen=1&dual=1&dual_mode=span"
            prof_dir = BASE_DIR / ".browser_profile_screen_1"
            prof_dir.mkdir(exist_ok=True)

            m_left = sec_mon["left"] if sec_mon else 1920
            m_top = sec_mon["top"] if sec_mon else 0
            m_w = sec_mon["width"] if sec_mon else 1920
            m_h = sec_mon["height"] if sec_mon else 1080

            args = [
                browser_exe,
                f"--app={url}",
                f"--window-position={m_left},{m_top}",
                f"--window-size={m_w},{m_h}",
                f"--user-data-dir={str(prof_dir)}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-translate",
                "--disable-infobars",
                "--start-fullscreen"
            ]

            try:
                proc = subprocess.Popen(args, close_fds=True)
                SECONDARY_BROWSER_PROC = proc
                self.send_json_response({
                    "success": True,
                    "status": "launched",
                    "is_running": True,
                    "pid": proc.pid,
                    "monitor": sec_mon,
                    "message": f"Extended Kuro to Monitor 2 ({m_w}x{m_h} at {m_left},{m_top})."
                }, status=200, origin=origin)
            except Exception as e:
                self.send_json_error("LAUNCH_FAILED", f"Failed to spawn secondary browser: {e}", status=500, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Confirm Display (RESERVED -> DISPLAYED)
        # -------------------------------------------------------------
        if path in ["/api/displayed", "/api/confirm-display"]:
            wallpaper_id = payload.get("id")
            token = payload.get("reservation_token", payload.get("token"))

            if not SecurityManager.validate_id(wallpaper_id):
                self.send_json_error("INVALID_INPUT", "Invalid or missing wallpaper ID", status=400, origin=origin)
                return
            if not SecurityManager.validate_token_format(token):
                self.send_json_error("INVALID_INPUT", "Invalid or missing reservation token", status=400, origin=origin)
                return

            success = engine.confirm_displayed(wallpaper_id=wallpaper_id, token=token)
            if success:
                self.send_json_response({"success": True, "id": wallpaper_id}, status=200, origin=origin)
            else:
                self.send_json_error("CONFLICT", "Reservation token mismatch or wallpaper not in RESERVED status", status=409, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Display Failed (RESERVED -> FAILED)
        # -------------------------------------------------------------
        if path in ["/api/display-failed"]:
            wallpaper_id = payload.get("id")
            token = payload.get("reservation_token", payload.get("token"))
            reason = SecurityManager.sanitize_string(payload.get("reason", "decode_error"), max_len=128)

            if not SecurityManager.validate_id(wallpaper_id) or not SecurityManager.validate_token_format(token):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID or reservation token", status=400, origin=origin)
                return

            success = engine.report_failed(wallpaper_id=wallpaper_id, token=token, reason=reason)
            self.send_json_response({"success": success, "id": wallpaper_id}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Auto-Save Downloads Endpoints
        # -------------------------------------------------------------
        if path in ["/api/downloads/save-previewed", "/api/v1/downloads/save-previewed"]:
            wp_data = payload.get("wallpaper") or payload
            wp_id = wp_data.get("id")
            if not wp_id or not SecurityManager.validate_id(str(wp_id)):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return
            db_wp = db_manager.get_wallpaper_by_id(str(wp_id))
            if db_wp:
                merged = dict(db_wp)
                merged.update({k: v for k, v in wp_data.items() if v})
                wp_data = merged
            autosaver.save_wallpaper_async(wp_data)
            self.send_json_response({"success": True, "id": str(wp_id), "status": "saving"}, status=200, origin=origin)
            return

        if path in ["/api/downloads/open", "/api/v1/downloads/open"]:
            ok, msg = autosaver.open_folder()
            if ok:
                self.send_json_response({"success": True, "message": msg, "folder": str(autosaver.downloads_dir)}, status=200, origin=origin)
            else:
                self.send_json_error("OPEN_FAILED", msg, status=500, origin=origin)
            return

        if path in ["/api/downloads/settings", "/api/v1/downloads/settings"]:
            if "enabled" in payload:
                autosaver.enabled = bool(payload["enabled"])
            if "downloads_dir" in payload and payload["downloads_dir"]:
                new_path = SecurityManager.sanitize_string(payload["downloads_dir"], max_len=260)
                try:
                    autosaver.downloads_dir = Path(new_path)
                    autosaver.downloads_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self.send_json_error("INVALID_PATH", f"Cannot use folder path: {e}", status=400, origin=origin)
                    return
            autosaver.save_config()
            self.send_json_response(autosaver.get_stats(), status=200, origin=origin)
            return

        if path in ["/api/gif/settings", "/api/v1/gif/settings"]:
            enabled = payload.get("enabled", True)
            mode = payload.get("mode", "all")
            prefer_hd = payload.get("prefer_hd", True)
            db_manager.save_gif_settings(enabled=bool(enabled), mode=str(mode), prefer_hd=bool(prefer_hd))
            self.send_json_response(db_manager.get_gif_settings(), status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Favorite (SSRF-Protected Download & Chunked Progress Tracking)
        # -------------------------------------------------------------
        if path in ["/api/favorite", "/api/favorites"]:
            img_id = payload.get("id", payload.get("wallpaper_id"))
            img_url = payload.get("url")

            if not SecurityManager.validate_id(img_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return

            # SSRF Protection: verify download target
            known_url = db_manager.get_wallpaper_url(img_id)
            if not SecurityManager.validate_download_url(img_url, known_url):
                logger.warning(f"SSRF attempt blocked in /api/favorite for ID {img_id}: URL={img_url}")
                self.send_json_error("SSRF_REJECTED", "Untrusted or unauthorized download URL", status=400, origin=origin)
                return

            resolution = SecurityManager.sanitize_string(payload.get("resolution", ""), max_len=32)
            anime = SecurityManager.sanitize_string(payload.get("anime", payload.get("mood", "")), max_len=64)
            character = SecurityManager.sanitize_string(payload.get("character", ""), max_len=64) if payload.get("character") else None
            source = SecurityManager.sanitize_string(payload.get("source", "Wallhaven"), max_len=32)

            db_manager.add_favorite({
                "id": img_id,
                "url": img_url,
                "resolution": resolution,
                "anime": anime,
                "character": character,
                "source": source,
                "download_status": "pending",
                "download_progress": 0
            })

            # Asynchronously download high-resolution image with chunked progress tracking
            target_download_url = img_url
            if target_download_url.startswith("/api/image/"):
                db_url = db_manager.get_wallpaper_url(img_id)
                if db_url and db_url.startswith("http"):
                    target_download_url = db_url

            favorites_downloader.start_download(img_id, target_download_url)
            engine.recommendation_engine.record_favorite(img_id, anime, character)
            self.send_json_response({"status": "saved", "id": img_id}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Remove Favorite
        # -------------------------------------------------------------
        if path in ["/api/favorite/remove", "/api/favorites/remove"]:
            img_id = payload.get("id", payload.get("wallpaper_id"))
            if not SecurityManager.validate_id(img_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return
            fav_item = db_manager.get_favorite_by_id(img_id)
            file_path = db_manager.remove_favorite(img_id)
            favorites_downloader.delete_favorite_file(img_id, file_path)
            engine.recommendation_engine.record_favorite_removed(
                img_id,
                fav_item.get("anime") if fav_item else None,
                fav_item.get("character") if fav_item else None
            )
            self.send_json_response({"status": "removed", "id": img_id}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Collections Management (Create, Rename, Delete, Items)
        # -------------------------------------------------------------
        if path in ["/api/collections", "/api/collections/create"]:
            name = SecurityManager.sanitize_string(payload.get("name", ""), max_len=64)
            if not name:
                self.send_json_error("INVALID_INPUT", "Collection name cannot be empty", status=400, origin=origin)
                return
            desc = SecurityManager.sanitize_string(payload.get("description", ""), max_len=256)
            try:
                col = db_manager.create_collection(name, desc)
                self.send_json_response(col, status=200, origin=origin)
            except Exception as e:
                self.send_json_error("COLLECTION_EXISTS", str(e), status=400, origin=origin)
            return

        if path in ["/api/collections/rename", "/api/collection/rename"]:
            col_id = SecurityManager.sanitize_string(payload.get("id", payload.get("collection_id", "")), max_len=64)
            name = SecurityManager.sanitize_string(payload.get("name", ""), max_len=64)
            desc = SecurityManager.sanitize_string(payload.get("description", ""), max_len=256) if "description" in payload else None
            if not col_id or not name:
                self.send_json_error("INVALID_INPUT", "Collection ID and name are required", status=400, origin=origin)
                return
            success = db_manager.rename_collection(col_id, name, desc)
            self.send_json_response({"success": success, "id": col_id}, status=200, origin=origin)
            return

        if path in ["/api/collections/delete", "/api/collection/delete"]:
            col_id = SecurityManager.sanitize_string(payload.get("id", payload.get("collection_id", "")), max_len=64)
            if not col_id:
                self.send_json_error("INVALID_INPUT", "Collection ID is required", status=400, origin=origin)
                return
            success = db_manager.delete_collection(col_id)
            self.send_json_response({"success": success, "id": col_id}, status=200, origin=origin)
            return

        if path in ["/api/collections/add-item", "/api/collections/items/add"]:
            col_id = SecurityManager.sanitize_string(payload.get("collection_id", payload.get("id", "")), max_len=64)
            wp_id = SecurityManager.sanitize_string(payload.get("wallpaper_id", ""), max_len=64)
            if not col_id or not wp_id or not SecurityManager.validate_id(wp_id):
                self.send_json_error("INVALID_INPUT", "Invalid collection ID or wallpaper ID", status=400, origin=origin)
                return
            success = db_manager.add_to_collection(col_id, wp_id)
            self.send_json_response({"success": success, "collection_id": col_id, "wallpaper_id": wp_id}, status=200, origin=origin)
            return

        if path in ["/api/collections/remove-item", "/api/collections/items/remove"]:
            col_id = SecurityManager.sanitize_string(payload.get("collection_id", payload.get("id", "")), max_len=64)
            wp_id = SecurityManager.sanitize_string(payload.get("wallpaper_id", ""), max_len=64)
            if not col_id or not wp_id:
                self.send_json_error("INVALID_INPUT", "Invalid collection ID or wallpaper ID", status=400, origin=origin)
                return
            success = db_manager.remove_from_collection(col_id, wp_id)
            self.send_json_response({"success": success, "collection_id": col_id, "wallpaper_id": wp_id}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Blacklist Management (Add, Restore)
        # -------------------------------------------------------------
        if path in ["/api/blacklist"]:
            wp_id = SecurityManager.sanitize_string(payload.get("id", payload.get("wallpaper_id", "")), max_len=64)
            if not wp_id or not SecurityManager.validate_id(wp_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return
            reason = SecurityManager.sanitize_string(payload.get("reason", "User excluded"), max_len=128)
            success = db_manager.add_to_blacklist(wp_id, reason)
            b_anime = SecurityManager.sanitize_string(payload.get("anime", ""), max_len=64) if payload.get("anime") else None
            b_char = SecurityManager.sanitize_string(payload.get("character", ""), max_len=64) if payload.get("character") else None
            engine.recommendation_engine.record_blacklist(wp_id, b_anime, b_char)
            self.send_json_response({"status": "blacklisted", "id": wp_id, "success": success}, status=200, origin=origin)
            return

        if path in ["/api/blacklist/restore", "/api/blacklist/remove"]:
            wp_id = SecurityManager.sanitize_string(payload.get("id", payload.get("wallpaper_id", "")), max_len=64)
            if not wp_id or not SecurityManager.validate_id(wp_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return
            success = db_manager.restore_from_blacklist(wp_id)
            self.send_json_response({"status": "restored", "id": wp_id, "success": success}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Cache Purge
        # -------------------------------------------------------------
        if path in ["/api/cache/purge"]:
            purged = engine.cache_manager.purge_cache(on_evict_callback=db_manager.unmark_wallpaper_cached)
            self.send_json_response({"status": "purged", "purged_count": purged}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Revisit Historical Artwork (/api/history/revisit)
        # -------------------------------------------------------------
        if path in ["/api/history/revisit", "/api/v1/history/revisit"]:
            wp_id = SecurityManager.sanitize_string(payload.get("id", payload.get("wallpaper_id", "")), max_len=64)
            if not wp_id or not SecurityManager.validate_id(wp_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return

            item = db_manager.get_wallpaper_details(wp_id)
            if not item:
                self.send_json_error("NOT_FOUND", "Historical artwork not found in database", status=404, origin=origin)
                return

            # Record revisit interaction for recommendation learning (strictly no duplicate display record added)
            engine.recommendation_engine.record_revisit(wp_id, item.get("anime"), item.get("character"))

            self.send_json_response({
                "status": "success",
                "message": f"Historical artwork '{wp_id}' ready for display",
                "wallpaper": item
            }, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Reset History
        # -------------------------------------------------------------
        if path == "/api/reset-history":
            engine.reset_history()
            logger.info("User requested wallpaper history reset.")
            self.send_json_response({"status": "history_reset"}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Reset Performance Metrics (/api/metrics/reset)
        # -------------------------------------------------------------
        if path in ["/api/metrics/reset", "/api/v1/metrics/reset"]:
            performance_tracker.reset_metrics()
            db_manager.reset_sqlite_latency_metrics()
            engine.cache_manager.reset_hit_rate_metrics()
            self.send_json_response({
                "status": "success",
                "message": "Performance metrics counters reset successfully."
            }, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Quality Profile Selection (/api/settings/quality-profile)
        # -------------------------------------------------------------
        if path in ["/api/settings/quality-profile", "/api/v1/settings/quality-profile"]:
            raw_profile = payload.get("profile", "auto")
            profile = SecurityManager.sanitize_string(raw_profile, max_len=16, default="auto").lower()
            if profile not in ["auto", "high", "balanced", "low"]:
                self.send_json_error("INVALID_PROFILE", "Quality profile must be auto, high, balanced, or low", status=400, origin=origin)
                return
            db_manager.save_control_center_settings("performance", {"perf_quality_profile": profile})
            self.send_json_response({
                "status": "success",
                "profile": profile,
                "message": f"Adaptive quality profile set to '{profile}'."
            }, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Graceful Server Shutdown (/api/shutdown & /api/v1/shutdown)
        # -------------------------------------------------------------
        if path in ["/api/shutdown", "/api/v1/shutdown"]:
            logger.info("Graceful shutdown requested via API.")
            self.send_json_response({"status": "shutting_down", "message": "Server shutting down"}, status=200, origin=origin)
            if GLOBAL_SHUTDOWN_FUNC:
                threading.Thread(target=lambda: (time.sleep(0.4), GLOBAL_SHUTDOWN_FUNC()), daemon=True).start()
            return

        # -------------------------------------------------------------
        # API: Launcher Config Update (/api/launcher/config & /api/v1/launcher/config)
        # -------------------------------------------------------------
        if path in ["/api/launcher/config", "/api/launcher-config"]:
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                self.send_json_response({"status": "saved", "config": payload}, status=200, origin=origin)
            except Exception as e:
                self.send_json_error("CONFIG_WRITE_ERROR", str(e), status=500, origin=origin)
            return

        # -------------------------------------------------------------
        # API: Interaction & Recommendation Events
        # -------------------------------------------------------------
        if path in ["/api/interaction/dwell", "/api/v1/interaction/dwell"]:
            wp_id = SecurityManager.sanitize_string(payload.get("id", ""), max_len=64)
            dwell_sec = float(payload.get("dwell_seconds", 0.0))
            was_skipped = bool(payload.get("was_skipped", False))
            anime = SecurityManager.sanitize_string(payload.get("anime", ""), max_len=64) if payload.get("anime") else None
            char = SecurityManager.sanitize_string(payload.get("character", ""), max_len=64) if payload.get("character") else None
            res = engine.recommendation_engine.record_dwell_and_transition(
                wallpaper_id=wp_id,
                dwell_seconds=dwell_sec,
                was_skipped=was_skipped,
                anime=anime,
                character=char
            )
            self.send_json_response({"status": "recorded", "result": res}, status=200, origin=origin)
            return

        if path in ["/api/interaction/revisit", "/api/v1/interaction/revisit"]:
            wp_id = SecurityManager.sanitize_string(payload.get("id", ""), max_len=64)
            anime = SecurityManager.sanitize_string(payload.get("anime", ""), max_len=64) if payload.get("anime") else None
            char = SecurityManager.sanitize_string(payload.get("character", ""), max_len=64) if payload.get("character") else None
            engine.recommendation_engine.record_revisit(wp_id, anime, char)
            self.send_json_response({"status": "recorded", "event": "revisit"}, status=200, origin=origin)
            return

        if path in ["/api/interaction/select", "/api/v1/interaction/select"]:
            franchise_name = SecurityManager.sanitize_string(payload.get("franchise", ""), max_len=64)
            if franchise_name:
                engine.recommendation_engine.record_franchise_selection(franchise_name)
            self.send_json_response({"status": "recorded", "franchise": franchise_name}, status=200, origin=origin)
            return

        if path in ["/api/recommendations/adjust", "/api/v1/recommendations/adjust"]:
            entity_type = SecurityManager.sanitize_string(payload.get("entity_type", "franchise"), max_len=16)
            entity_name = SecurityManager.sanitize_string(payload.get("entity_name", ""), max_len=64)
            if not entity_name:
                self.send_json_error("INVALID_INPUT", "Entity name required", status=400, origin=origin)
                return
            manual_score = float(payload.get("manual_score", 0.0))
            ok = engine.recommendation_engine.set_manual_score(entity_type, entity_name, manual_score)
            self.send_json_response({"status": "updated", "success": ok, "entity_name": entity_name, "manual_score": manual_score}, status=200, origin=origin)
            return

        if path in ["/api/recommendations/toggle", "/api/v1/recommendations/toggle"]:
            if "enabled" in payload:
                engine.recommendation_engine.set_enabled(bool(payload["enabled"]))
            if "diversity_penalty_enabled" in payload:
                engine.recommendation_engine.set_diversity_enabled(bool(payload["diversity_penalty_enabled"]))
            profile = engine.recommendation_engine.get_profile()
            self.send_json_response({"status": "toggled", "profile": profile}, status=200, origin=origin)
            return

        if path in ["/api/recommendations/reset", "/api/v1/recommendations/reset"]:
            ok = engine.recommendation_engine.reset_learning()
            self.send_json_response({"status": "reset", "success": ok}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Quality Scoring Settings & Rescoring
        # -------------------------------------------------------------
        if path in ["/api/quality/settings", "/api/v1/quality/settings"]:
            ok = db_manager.update_quality_settings(payload)
            if hasattr(engine, "quality_scorer"):
                engine.quality_scorer = QualityScorer(db_manager.get_quality_settings())
            updated = db_manager.get_quality_settings()
            self.send_json_response({"status": "updated", "settings": updated}, status=200, origin=origin)
            return

        if path in ["/api/quality/rescore", "/api/v1/quality/rescore"]:
            if hasattr(engine, "quality_scorer"):
                engine.quality_scorer = QualityScorer(db_manager.get_quality_settings())
                re_count = db_manager.backfill_quality_scores(engine.quality_scorer, limit=500)
            else:
                re_count = 0
            summary = db_manager.get_quality_scores_summary()
            self.send_json_response({"status": "rescored", "rescored_count": re_count, "summary": summary}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Slideshow Scheduler Settings
        # -------------------------------------------------------------
        if path in ["/api/scheduler/settings", "/api/v1/scheduler/settings"]:
            ok = db_manager.update_scheduler_settings(payload)
            if hasattr(engine, "scheduler"):
                engine.scheduler.update_settings(db_manager.get_scheduler_settings())
            updated = db_manager.get_scheduler_settings()
            self.send_json_response({"status": "updated", "settings": updated}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Ambient Soundscape Settings
        # -------------------------------------------------------------
        if path in ["/api/soundscapes/settings", "/api/v1/soundscapes/settings"]:
            ok = db_manager.update_soundscape_settings(payload)
            updated = db_manager.get_soundscape_settings()
            self.send_json_response({"status": "updated", "settings": updated}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Composition Settings & Per-Wallpaper Composition
        # -------------------------------------------------------------
        if path in ["/api/composition/settings", "/api/v1/composition/settings"]:
            ok = db_manager.update_composition_settings(payload)
            updated = db_manager.get_composition_settings()
            self.send_json_response({"status": "updated", "settings": updated}, status=200, origin=origin)
            return

        if path.startswith("/api/composition/") or path.startswith("/api/v1/composition/"):
            prefix = "/api/v1/composition/" if path.startswith("/api/v1/composition/") else "/api/composition/"
            raw_id = path[len(prefix):]
            img_id = SecurityManager.sanitize_string(raw_id, max_len=64)
            if not SecurityManager.validate_id(img_id):
                self.send_json_error("INVALID_INPUT", "Invalid wallpaper ID", status=400, origin=origin)
                return

            if payload.get("reset"):
                db_manager.delete_wallpaper_composition(img_id)
                self.send_json_response({"status": "reset", "wallpaper_id": img_id}, status=200, origin=origin)
                return

            focal_x = payload.get("focal_x", 50.0)
            focal_y = payload.get("focal_y", 50.0)
            try:
                focal_x = float(focal_x)
                focal_y = float(focal_y)
                if not (0.0 <= focal_x <= 100.0 and 0.0 <= focal_y <= 100.0):
                    self.send_json_error("INVALID_INPUT", "Focal coordinates must be between 0.0 and 100.0", status=400, origin=origin)
                    return
            except (ValueError, TypeError):
                self.send_json_error("INVALID_INPUT", "Focal coordinates must be numeric", status=400, origin=origin)
                return

            disp_mode = str(payload.get("display_mode", "fill"))
            if disp_mode not in ("fill", "fit", "original"):
                self.send_json_error("INVALID_INPUT", "Invalid display_mode (must be fill, fit, or original)", status=400, origin=origin)
                return

            ok = db_manager.save_wallpaper_composition(img_id, payload)
            saved = db_manager.get_wallpaper_composition(img_id)
            self.send_json_response({"status": "saved", "composition": saved}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Provider Management Endpoints (/api/providers/toggle, /api/providers/priority, /api/providers/reset-circuits)
        # -------------------------------------------------------------
        if path in ["/api/providers/toggle", "/api/v1/providers/toggle"]:
            name = payload.get("name")
            enabled = payload.get("enabled")
            if not name or enabled is None:
                self.send_json_error("INVALID_INPUT", "Must specify provider 'name' and boolean 'enabled'", status=400, origin=origin)
                return
            if not hasattr(engine, "provider_manager"):
                self.send_json_error("UNAVAILABLE", "Provider manager not initialized", status=503, origin=origin)
                return
            ok = engine.provider_manager.toggle_provider(str(name), bool(enabled))
            if not ok:
                self.send_json_error("NOT_FOUND", f"Unknown provider: {name}", status=404, origin=origin)
                return
            self.send_json_response({"status": "updated", "provider": name, "enabled": bool(enabled)}, status=200, origin=origin)
            return

        if path in ["/api/providers/priority", "/api/v1/providers/priority"]:
            order = payload.get("order")
            if not isinstance(order, list):
                self.send_json_error("INVALID_INPUT", "'order' must be an array of provider names", status=400, origin=origin)
                return
            if not hasattr(engine, "provider_manager"):
                self.send_json_error("UNAVAILABLE", "Provider manager not initialized", status=503, origin=origin)
                return
            engine.provider_manager.set_priority(order)
            self.send_json_response({"status": "updated", "order": order}, status=200, origin=origin)
            return

        if path in ["/api/providers/reset-circuits", "/api/v1/providers/reset-circuits"]:
            if hasattr(engine, "provider_manager"):
                engine.provider_manager.reset_all_circuits()
            self.send_json_response({"status": "reset", "message": "All provider circuit breakers reset to CLOSED"}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Franchise Catalog & Tag Intelligence Administration
        # -------------------------------------------------------------
        if path in ["/api/franchises/catalog/update", "/api/v1/franchises/catalog/update"]:
            slug = payload.get("slug")
            entry = payload.get("entry", payload)
            if not slug or not isinstance(entry, dict):
                self.send_json_error("INVALID_INPUT", "Must provide 'slug' and 'entry' dictionary", status=400, origin=origin)
                return
            try:
                updated = FranchiseRegistry.update_franchise_catalog_entry(str(slug), entry, save_file=True)
                db_manager.save_franchise_catalog_db(str(slug), updated.get("name", str(slug)), json.dumps(updated))
                self.send_json_response({"status": "updated", "slug": slug, "entry": updated}, status=200, origin=origin)
                return
            except Exception as e:
                self.send_json_error("UPDATE_FAILED", str(e), status=400, origin=origin)
                return

        if path in ["/api/franchises/catalog/verify-tag", "/api/v1/franchises/catalog/verify-tag"]:
            tag_id = payload.get("tag_id")
            if tag_id is None:
                self.send_json_error("INVALID_INPUT", "Must provide numeric 'tag_id'", status=400, origin=origin)
                return
            try:
                tid = int(tag_id)
                res = FranchiseRegistry.verify_tag_id_online(tid)
                if res.get("is_valid"):
                    db_manager.cache_verified_tag(
                        tag_id=tid,
                        tag_name=res.get("name", f"Tag {tid}"),
                        category=res.get("category"),
                        purity=res.get("purity"),
                        raw_metadata=res
                    )
                self.send_json_response({"status": "verified" if res.get("is_valid") else "failed", "tag": res}, status=200, origin=origin)
                return
            except Exception as e:
                self.send_json_error("VERIFICATION_FAILED", str(e), status=400, origin=origin)
                return

        if path in ["/api/franchises/catalog/reset", "/api/v1/franchises/catalog/reset"]:
            catalog = FranchiseRegistry.reset_catalog_to_defaults(save_file=True)
            self.send_json_response({
                "status": "reset",
                "message": "Franchise catalog reset to factory verified defaults",
                "total_franchises": len(catalog)
            }, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Control Center Settings API (/api/settings, /api/settings/reset, /api/settings/import)
        # -------------------------------------------------------------
        if path in ["/api/settings", "/api/v1/settings"]:
            if not isinstance(payload, dict):
                self.send_json_error("INVALID_INPUT", "Payload must be a JSON object", status=400, origin=origin)
                return

            section = payload.get("section")
            settings = payload.get("settings", payload)

            if section:
                if section not in ("general", "wallpaper", "visual", "display", "performance", "privacy", "providers"):
                    self.send_json_error("INVALID_INPUT", f"Unknown section: {section}", status=400, origin=origin)
                    return

                if "slideshow_interval" in settings:
                    try:
                        iv = int(settings["slideshow_interval"])
                        if not (5 <= iv <= 600):
                            self.send_json_error("INVALID_INPUT", "slideshow_interval must be between 5 and 600", status=400, origin=origin)
                            return
                    except (ValueError, TypeError):
                        self.send_json_error("INVALID_INPUT", "slideshow_interval must be integer", status=400, origin=origin)
                        return

                if "perf_prefetch_queue_size" in settings:
                    try:
                        pq = int(settings["perf_prefetch_queue_size"])
                        if not (2 <= pq <= 30):
                            self.send_json_error("INVALID_INPUT", "perf_prefetch_queue_size must be between 2 and 30", status=400, origin=origin)
                            return
                    except (ValueError, TypeError):
                        self.send_json_error("INVALID_INPUT", "perf_prefetch_queue_size must be integer", status=400, origin=origin)
                        return

                if "perf_cache_limit_mb" in settings:
                    try:
                        cl = int(settings["perf_cache_limit_mb"])
                        if not (200 <= cl <= 20000):
                            self.send_json_error("INVALID_INPUT", "perf_cache_limit_mb must be between 200 and 20000", status=400, origin=origin)
                            return
                    except (ValueError, TypeError):
                        self.send_json_error("INVALID_INPUT", "perf_cache_limit_mb must be integer", status=400, origin=origin)
                        return

                db_manager.save_control_center_settings(section, settings)
            else:
                for sec, sec_settings in settings.items():
                    if sec in ("general", "wallpaper", "visual", "display", "performance", "privacy") and isinstance(sec_settings, dict):
                        db_manager.save_control_center_settings(sec, sec_settings)

            updated = db_manager.get_control_center_settings(section)
            self.send_json_response({"status": "saved", "settings": updated}, status=200, origin=origin)
            return

        if path in ["/api/settings/reset", "/api/v1/settings/reset"]:
            section = payload.get("section")
            is_factory = payload.get("factory_reset", False)
            if is_factory:
                db_manager.factory_reset_configuration()
                updated = db_manager.get_control_center_settings()
                self.send_json_response({"status": "reset", "message": "Factory reset complete", "settings": updated}, status=200, origin=origin)
                return
            elif section:
                if section not in ("general", "wallpaper", "visual", "display", "performance", "privacy"):
                    self.send_json_error("INVALID_INPUT", f"Unknown section: {section}", status=400, origin=origin)
                    return
                updated = db_manager.reset_control_center_section(section)
                self.send_json_response({"status": "reset", "section": section, "settings": updated}, status=200, origin=origin)
                return
            else:
                self.send_json_error("INVALID_INPUT", "Must specify section or factory_reset", status=400, origin=origin)
                return

        if path in ["/api/settings/import", "/api/v1/settings/import"]:
            config = payload.get("config", payload)
            if not isinstance(config, dict):
                self.send_json_error("INVALID_INPUT", "Import configuration must be a JSON object", status=400, origin=origin)
                return
            ok = db_manager.import_full_configuration(config)
            if ok:
                all_settings = db_manager.get_control_center_settings()
                self.send_json_response({"status": "imported", "message": "Configuration successfully imported", "settings": all_settings}, status=200, origin=origin)
            else:
                self.send_json_error("IMPORT_FAILED", "Failed to import configuration", status=400, origin=origin)
            return

        # -------------------------------------------------------------
        # 22. Backup & Recovery Operations (Create, Validate, Restore, Delete, Upload)
        # -------------------------------------------------------------
        if path in ["/api/backups", "/api/v1/backups"]:
            backup_manager.db_manager = db_manager
            include_favs = bool(payload.get("include_favorites", True))
            include_cache = bool(payload.get("include_cache", False))
            note = SecurityManager.sanitize_string(payload.get("note", payload.get("custom_note", "")), max_len=256)
            b_type = SecurityManager.sanitize_string(payload.get("backup_type", "manual"), max_len=32)
            export_res = backup_manager.export_backup(
                backup_type=b_type,
                include_favorites=include_favs,
                include_cache=include_cache,
                custom_note=note
            )
            self.send_json_response(export_res, status=200, origin=origin)
            return

        if path in ["/api/backups/validate", "/api/v1/backups/validate"]:
            backup_manager.db_manager = db_manager
            filename = SecurityManager.sanitize_string(payload.get("filename", ""), max_len=128)
            if not filename:
                self.send_json_error("INVALID_INPUT", "Must specify filename", status=400, origin=origin)
                return
            target_path = backup_manager.get_backup_path(filename)
            if not target_path:
                self.send_json_error("NOT_FOUND", f"Backup '{filename}' not found", status=404, origin=origin)
                return
            val_res = backup_manager.validate_backup_archive(target_path)
            self.send_json_response(val_res, status=200 if val_res["valid"] else 400, origin=origin)
            return

        if path in ["/api/backups/restore", "/api/v1/backups/restore"]:
            backup_manager.db_manager = db_manager
            filename = SecurityManager.sanitize_string(payload.get("filename", ""), max_len=128)
            confirm = bool(payload.get("confirm", False))
            if not confirm:
                self.send_json_error(
                    "CONFIRMATION_REQUIRED",
                    "Confirmation required: restoring replaces current database and settings. Set confirm=True.",
                    status=400,
                    origin=origin
                )
                return
            if not filename:
                self.send_json_error("INVALID_INPUT", "Must specify filename", status=400, origin=origin)
                return
            target_path = backup_manager.get_backup_path(filename)
            if not target_path:
                self.send_json_error("NOT_FOUND", f"Backup '{filename}' not found", status=404, origin=origin)
                return

            restore_favs = bool(payload.get("restore_favorites", True))
            restore_cache = bool(payload.get("restore_cache", False))
            rest_res = backup_manager.restore_backup(
                target_path,
                confirm=confirm,
                restore_favorites=restore_favs,
                restore_cache=restore_cache
            )
            if rest_res["success"]:
                self.send_json_response(rest_res, status=200, origin=origin)
            else:
                self.send_json_error(
                    "RESTORE_FAILED",
                    rest_res.get("error", "Restore failed"),
                    details=rest_res.get("details"),
                    status=400,
                    origin=origin
                )
            return

        if path in ["/api/backups/delete", "/api/v1/backups/delete"]:
            backup_manager.db_manager = db_manager
            filename = SecurityManager.sanitize_string(payload.get("filename", ""), max_len=128)
            if not filename:
                self.send_json_error("INVALID_INPUT", "Must specify filename", status=400, origin=origin)
                return
            ok = backup_manager.delete_backup(filename)
            self.send_json_response({"success": ok, "filename": filename}, status=200 if ok else 400, origin=origin)
            return

        if path in ["/api/backups/upload", "/api/v1/backups/upload"]:
            import base64
            backup_manager.db_manager = db_manager
            raw_b64 = payload.get("data") or payload.get("archive_base64")
            raw_name = SecurityManager.sanitize_string(
                payload.get("filename", f"uploaded_backup_{int(time.time())}.zip"),
                max_len=128
            )
            if not raw_name.endswith(".zip") and not raw_name.endswith(".kurobackup"):
                raw_name += ".zip"
            if not raw_b64:
                self.send_json_error("INVALID_INPUT", "Missing data or archive_base64 payload", status=400, origin=origin)
                return
            try:
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                decoded = base64.b64decode(raw_b64)
                save_path = backup_manager.backups_dir / raw_name
                with open(save_path, "wb") as uf:
                    uf.write(decoded)
                val_res = backup_manager.validate_backup_archive(save_path)
                self.send_json_response({
                    "status": "uploaded",
                    "filename": save_path.name,
                    "file_size": len(decoded),
                    "validation": val_res
                }, status=200, origin=origin)
            except Exception as e:
                self.send_json_error("UPLOAD_ERROR", f"Failed to process uploaded backup archive: {e}", status=400, origin=origin)
            return

        if path in ["/api/database/integrity/check", "/api/v1/database/integrity/check"]:
            report = db_manager.diagnose_database_integrity()
            self.send_json_response(report, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # Content Safety & Moderation Layer (POST Endpoints)
        # -------------------------------------------------------------
        if path in ["/api/moderation/block", "/api/v1/moderation/block"]:
            entity_type = payload.get("entity_type")
            entity_value = payload.get("entity_value")
            reason = payload.get("reason", "")
            if not entity_type or not entity_value:
                self.send_json_error("INVALID_INPUT", "Must provide entity_type and entity_value", status=400, origin=origin)
                return
            ok = db_manager.add_blocked_entity(str(entity_type), str(entity_value), reason=str(reason))
            if str(entity_type).lower() == "artwork":
                try:
                    engine.cache_manager.evict(str(entity_value))
                except Exception:
                    pass
            self.send_json_response({
                "status": "blocked",
                "entity_type": entity_type,
                "entity_value": entity_value,
                "success": ok
            }, status=200, origin=origin)
            return

        if path in ["/api/moderation/unblock", "/api/v1/moderation/unblock"]:
            entity_id = payload.get("entity_id")
            entity_type = payload.get("entity_type")
            entity_value = payload.get("entity_value")
            if entity_id is None and (not entity_type or not entity_value):
                self.send_json_error("INVALID_INPUT", "Must provide entity_id or (entity_type, entity_value)", status=400, origin=origin)
                return
            ok = db_manager.remove_blocked_entity(entity_id=entity_id, entity_type=entity_type, entity_value=entity_value)
            self.send_json_response({"status": "unblocked", "success": ok}, status=200 if ok else 400, origin=origin)
            return

        if path in ["/api/moderation/report", "/api/v1/moderation/report"]:
            wallpaper_id = payload.get("wallpaper_id") or payload.get("id")
            reason = payload.get("reason", "User reported unsafe content")
            block_char = bool(payload.get("block_character", False))
            block_artist = bool(payload.get("block_artist", False))
            if not wallpaper_id:
                self.send_json_error("INVALID_INPUT", "Must provide wallpaper_id", status=400, origin=origin)
                return
            rep_res = db_manager.report_and_block_artwork(
                wallpaper_id=str(wallpaper_id),
                reason=str(reason),
                block_character=block_char,
                block_artist=block_artist
            )
            try:
                engine.cache_manager.evict(str(wallpaper_id))
            except Exception:
                pass
            self.send_json_response(rep_res, status=200, origin=origin)
            return

        if path in ["/api/moderation/review-action", "/api/v1/moderation/review-action"]:
            wallpaper_id = payload.get("wallpaper_id") or payload.get("id")
            decision = payload.get("decision")
            if not wallpaper_id or not decision:
                self.send_json_error("INVALID_INPUT", "Must provide wallpaper_id and decision ('APPROVE' or 'REJECT')", status=400, origin=origin)
                return
            ok = db_manager.action_review_queue_item(str(wallpaper_id), str(decision))
            if str(decision).upper() == "REJECT":
                try:
                    engine.cache_manager.evict(str(wallpaper_id))
                except Exception:
                    pass
            self.send_json_response({"status": "success", "wallpaper_id": wallpaper_id, "decision": decision, "applied": ok}, status=200 if ok else 400, origin=origin)
            return

        if path in ["/api/moderation/settings", "/api/v1/moderation/settings"]:
            if not isinstance(payload, dict):
                self.send_json_error("INVALID_INPUT", "Settings payload must be JSON object", status=400, origin=origin)
                return
            db_manager.save_safety_policy_settings(payload)
            updated = db_manager.get_safety_policy_settings()
            self.send_json_response({"status": "saved", "settings": updated}, status=200, origin=origin)
            return

        # -------------------------------------------------------------
        # 24. Wallhaven API Contract Audit Runner
        # -------------------------------------------------------------
        if path in ["/api/diagnostics/wallhaven-compatibility/run", "/api/v1/diagnostics/wallhaven-compatibility/run"]:
            is_live = bool(payload.get("live", False))
            api_key = payload.get("api_key")
            from wallhaven_compatibility import WallhavenCompatibilityManager
            comp_mgr = WallhavenCompatibilityManager(db_manager)
            report = comp_mgr.run_audit(live=is_live, api_key=api_key)
            self.send_json_response({"status": "ok", "report": report}, status=200, origin=origin)
            return

        self.send_json_error("NOT_FOUND", f"Endpoint {raw_path} not found", status=404, origin=origin)

    def log_message(self, format, *args):
        """Routes HTTP request messages to standard logger instead of stderr."""
        logger.debug(f"{self.address_string()} - {format % args}")

def run_server(port=PORT):
    # Security: Bind strictly to localhost (127.0.0.1)
    server = None
    actual_port = port

    # Port conflict recovery: try port, if occupied try next port
    for p in range(port, port + 10):
        try:
            server = ThreadedHTTPServer((HOST, p), KuroHandler)
            actual_port = p
            break
        except OSError:
            continue

    if not server:
        logger.critical(f"Could not bind to any port in range {port}-{port+9}.")
        sys.exit(1)

    # Recover any stale or abandoned reservations so all items are instantly available
    try:
        db_manager.recover_abandoned_reservations(timeout_seconds=0.0)
    except Exception as e:
        logger.warning(f"Could not clear stale reservations on boot: {e}")

    url = f"http://{HOST}:{actual_port}"
    logger.info("=" * 65)
    logger.info("  KURO // ANIME — Production Hardened Local Server Running")
    logger.info(f"  URL: {url}")
    logger.info(f"  Binding: {HOST}:{actual_port} (Strict Loopback)")
    logger.info("  Engine: UNSEEN -> RESERVED -> DISPLAYED (WAL Mode Active)")
    logger.info(f"  Session Security Token Active: {security_manager.session_token[:8]}***")
    logger.info("=" * 65)

    # Write PID & Port for launcher & system integration
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        PORT_FILE.write_text(str(actual_port), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not write PID/Port file: {e}")

    # Graceful shutdown handler
    shutdown_done = threading.Event()

    def graceful_shutdown(signum=None, frame=None):
        if shutdown_done.is_set():
            return
        shutdown_done.set()
        logger.info("\n[Kuro] Initiating graceful server shutdown...")

        # 1. Stop background workers
        engine.stop(timeout=4.0)

        # 2. Checkpoint SQLite WAL journal back to main database
        db_manager.close_and_checkpoint(timeout=4.0)

        # 3. Clean up PID & Port files
        try:
            PID_FILE.unlink(missing_ok=True)
            PORT_FILE.unlink(missing_ok=True)
        except Exception:
            pass

        # 4. Shutdown HTTP server socket
        threading.Thread(target=server.shutdown, daemon=True).start()
        logger.info("[Kuro] Server shutdown complete. Goodbye.")

    global GLOBAL_SHUTDOWN_FUNC
    GLOBAL_SHUTDOWN_FUNC = graceful_shutdown

    # Register OS signals if running in main thread
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, graceful_shutdown)

    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        graceful_shutdown()
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
            PORT_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        server.server_close()

if __name__ == "__main__":
    run_server()
