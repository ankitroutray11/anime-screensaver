#!/usr/bin/env python3
"""
KURO // ANIME — Wallpaper Download & Auto-Save Manager
Saves every wallpaper previewed/displayed on screen to a local folder in Windows Downloads:
%USERPROFILE%\\Downloads\\Kuro Wallpapers

Features:
- Zero-latency asynchronous background copying & streaming.
- Intelligent, human-readable file naming:
  "<Anime> - <Character> [<id>].<ext>"
- Instant local cache reuse (if already downloaded by browser/cache, copies without network re-fetch).
- Direct high-resolution streaming fallback if not locally cached.
- Atomic file writes (.tmp -> target) preventing incomplete or corrupted images.
- Native Windows File Explorer folder opening via os.startfile.
- Duplicate detection & persistent tracking.
"""

import os
import re
import sys
import json
import time
import shutil
import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

logger = logging.getLogger("kuro_autosaver")

DEFAULT_DOWNLOADS_DIR = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads" / "Kuro Wallpapers"
CONFIG_FILE = Path(__file__).resolve().parent / "launcher_config.json"


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Removes invalid Windows filesystem characters and truncates safely."""
    # Replace invalid chars: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
    # Collapse whitespace and underscores
    cleaned = re.sub(r'[\s_]+', ' ', cleaned).strip()
    if not cleaned:
        cleaned = "Anime"
    return cleaned[:max_length].strip()


class DownloadAutoSaver:
    def __init__(self, downloads_dir: Optional[Path] = None, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.downloads_dir = Path(downloads_dir) if downloads_dir else DEFAULT_DOWNLOADS_DIR
        self.enabled = True
        self.lock = threading.Lock()
        self.saved_ids: set = set()
        self.active_threads: Dict[str, threading.Thread] = {}

        # Load persisted settings from config
        self._load_config()

        # Ensure target folder exists
        try:
            self.downloads_dir.mkdir(parents=True, exist_ok=True)
            self.cleanup_orphaned_temp_files()
        except Exception as e:
            logger.warning(f"Could not create downloads directory {self.downloads_dir}: {e}")

        # Scan existing saved files to populate saved_ids
        self._scan_existing_saved()

    def cleanup_orphaned_temp_files(self):
        """Cleans up any lingering .tmp_* files from interrupted downloads."""
        if not self.downloads_dir.is_dir():
            return
        try:
            for item in self.downloads_dir.iterdir():
                if item.is_file() and (".tmp" in item.name or item.name.startswith(".tmp")):
                    try:
                        item.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Error cleaning temp files in downloads: {e}")

    def _load_config(self):
        """Loads auto-save preferences from launcher_config.json."""
        if CONFIG_FILE.is_file():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.enabled = cfg.get("auto_save_previews", True)
                    custom_path = cfg.get("downloads_save_path")
                    if custom_path:
                        self.downloads_dir = Path(custom_path)
            except Exception:
                pass

    def save_config(self):
        """Saves auto-save preferences to launcher_config.json."""
        try:
            cfg = {}
            if CONFIG_FILE.is_file():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["auto_save_previews"] = self.enabled
            cfg["downloads_save_path"] = str(self.downloads_dir)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            logger.warning(f"Error saving autosaver config: {e}")

    def _scan_existing_saved(self):
        """Scans downloads folder for existing wallpaper IDs in filenames [id]."""
        if not self.downloads_dir.is_dir():
            return
        id_regex = re.compile(r'\[([a-zA-Z0-9_\-]+)\]\.[a-zA-Z0-9]+$')
        try:
            for item in self.downloads_dir.iterdir():
                if item.is_file():
                    match = id_regex.search(item.name)
                    if match:
                        self.saved_ids.add(match.group(1))
                    else:
                        # Fallback: check filename stem
                        self.saved_ids.add(item.stem)
        except Exception as e:
            logger.warning(f"Error scanning existing saved wallpapers: {e}")

    def get_target_filename(self, wallpaper: Dict[str, Any]) -> str:
        """
        Constructs a clean human-readable filename:
        "<Anime> - <Character> [<id>].<ext>"
        """
        wp_id = str(wallpaper.get("id", "wallpaper")).strip()
        anime = sanitize_filename(wallpaper.get("anime") or "Anime", max_length=45)
        character = sanitize_filename(wallpaper.get("character") or "", max_length=35) if wallpaper.get("character") else ""

        # Determine extension from url or local_path
        url = wallpaper.get("url", "")
        local_path = wallpaper.get("local_path", "")
        ext = ".gif" if (wallpaper.get("is_animated") or wallpaper.get("media_type") == "gif") else ".jpg"
        for candidate in [url, local_path, str(wallpaper.get("file", ""))]:
            if candidate:
                clean_cand = candidate.split("?")[0].lower()
                for e in [".gif", ".png", ".jpg", ".jpeg", ".webp", ".svg"]:
                    if clean_cand.endswith(e):
                        ext = e
                        break

        if character and character.lower() not in ("all", "none", "unknown"):
            base_name = f"{anime} - {character} [{wp_id}]{ext}"
        else:
            base_name = f"{anime} [{wp_id}]{ext}"

        return base_name

    def save_wallpaper_async(self, wallpaper: Dict[str, Any]):
        """Non-blocking background launcher to save previewed artwork."""
        if not self.enabled:
            return

        wp_id = str(wallpaper.get("id", "")).strip()
        if not wp_id:
            return

        with self.lock:
            if wp_id in self.saved_ids:
                return
            if wp_id in self.active_threads and self.active_threads[wp_id].is_alive():
                return

            t = threading.Thread(
                target=self._save_worker,
                args=(dict(wallpaper),),
                name=f"AutoSave-{wp_id[:8]}",
                daemon=True
            )
            self.active_threads[wp_id] = t
            t.start()

    def _save_worker(self, wallpaper: Dict[str, Any]):
        """Worker thread executing local cache copy or high-res network stream."""
        wp_id = str(wallpaper.get("id", "")).strip()
        target_name = self.get_target_filename(wallpaper)
        target_path = self.downloads_dir / target_name
        temp_path = self.downloads_dir / f"{target_name}.tmp_{int(time.time())}"

        # 1. Fast Path: Check if wallpaper exists locally in cache or curated
        source_file = None

        local_path = wallpaper.get("local_path")
        if local_path:
            cand = (self.base_dir / local_path).resolve()
            if cand.is_file():
                source_file = cand

        if not source_file:
            cache_cand = self.base_dir / ".cache" / "wallpapers" / f"{wp_id}.jpg"
            for ext in [".gif", ".jpg", ".png", ".webp", ".jpeg", ".svg"]:
                c = self.base_dir / ".cache" / "wallpapers" / f"{wp_id}{ext}"
                if c.is_file():
                    source_file = c
                    break

        if not source_file:
            curated_cand = self.base_dir / "curated_wallpapers" / f"{wp_id}.svg"
            if curated_cand.is_file():
                source_file = curated_cand
            else:
                for ext in [".gif", ".svg", ".png", ".jpg", ".webp"]:
                    c = self.base_dir / "curated_wallpapers" / f"{wp_id}{ext}"
                    if c.is_file():
                        source_file = c
                        break

        # If a valid local file was found, copy atomically
        if source_file and source_file.is_file():
            try:
                self.downloads_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, temp_path)
                temp_path.replace(target_path)
                with self.lock:
                    self.saved_ids.add(wp_id)
                logger.info(f"[AutoSaver] Copied previewed wallpaper to Downloads: {target_path.name}")
                return
            except Exception as e:
                logger.warning(f"[AutoSaver] Failed copying local file {source_file}: {e}")
                temp_path.unlink(missing_ok=True)

        # 2. Network Stream Path: Download from remote source URL
        remote_url = wallpaper.get("url")
        if not remote_url or remote_url.startswith("/api/"):
            return

        try:
            self.downloads_dir.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(
                remote_url,
                headers={"User-Agent": "KuroAnimeScreensaver/3.5"}
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                if resp.status == 200:
                    with open(temp_path, "wb") as out_f:
                        while True:
                            chunk = resp.read(64 * 1024)
                            if not chunk:
                                break
                            out_f.write(chunk)

                    if temp_path.is_file() and temp_path.stat().st_size > 0:
                        temp_path.replace(target_path)
                        with self.lock:
                            self.saved_ids.add(wp_id)
                        logger.info(f"[AutoSaver] Downloaded previewed wallpaper to Downloads: {target_path.name}")
                        return
        except Exception as e:
            logger.warning(f"[AutoSaver] Failed downloading remote wallpaper {wp_id}: {e}")
        finally:
            temp_path.unlink(missing_ok=True)

    def open_folder(self) -> Tuple[bool, str]:
        """Opens the local Downloads folder in Windows File Explorer."""
        try:
            self.downloads_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(self.downloads_dir))
                return True, f"Opened folder: {self.downloads_dir}"
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(self.downloads_dir)])
                return True, f"Opened folder: {self.downloads_dir}"
        except Exception as e:
            return False, f"Could not open folder: {e}"

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics of saved wallpapers in Downloads folder."""
        file_count = 0
        total_bytes = 0
        recent_files = []

        if self.downloads_dir.is_dir():
            try:
                items = sorted(
                    [f for f in self.downloads_dir.iterdir() if f.is_file() and not f.name.endswith(".tmp")],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                file_count = len(items)
                total_bytes = sum(f.stat().st_size for f in items)
                for f in items[:5]:
                    recent_files.append({
                        "name": f.name,
                        "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                        "mtime": f.stat().st_mtime
                    })
            except Exception as e:
                logger.warning(f"Error computing autosaver stats: {e}")

        return {
            "enabled": self.enabled,
            "folder": str(self.downloads_dir),
            "saved_count": file_count,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "recent_files": recent_files
        }
