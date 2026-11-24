#!/usr/bin/env python3
"""
Favorites Downloader & Storage Management Module for KuroAnime.
Handles high-resolution image streaming, chunked download progress tracking,
atomic file writes, duplicate prevention, and interrupted download recovery.
"""

import os
import sys
import time
import secrets
import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any

from database import DatabaseManager

logger = logging.getLogger("kuro_favorites")

CHUNK_SIZE = 64 * 1024  # 64 KB per stream chunk

class FavoritesDownloader:
    def __init__(self, db_manager: DatabaseManager, favorites_dir: Path):
        self.db = db_manager
        self.favorites_dir = favorites_dir
        self.favorites_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.active_downloads: Dict[str, threading.Thread] = {}
        self._cancelled: set = set()

        # Startup recovery of interrupted downloads
        self.cleanup_interrupted()

    def cleanup_interrupted(self) -> int:
        """
        Cleans up leftover .tmp files from crashes/interruptions and
        resets dangling 'downloading' states in the database.
        """
        cleaned_files = 0
        try:
            for item in self.favorites_dir.glob("*.tmp*"):
                if item.is_file():
                    try:
                        item.unlink(missing_ok=True)
                        cleaned_files += 1
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Error during favorites temp cleanup: {e}")

        # Reconcile database state
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, file_path FROM favorites WHERE download_status = 'downloading'")
            dangling = cur.fetchall()
            for row in dangling:
                fav_id = row[0]
                fav_path = row[1]
                # Check if final file actually exists
                resolved = (self.favorites_dir.parent / fav_path).resolve() if fav_path else None
                if resolved and resolved.is_file() and resolved.stat().st_size > 0:
                    cur.execute("""
                        UPDATE favorites
                        SET download_status = 'completed', download_progress = 100, file_size = ?
                        WHERE id = ?
                    """, (resolved.stat().st_size, fav_id))
                else:
                    cur.execute("""
                        UPDATE favorites
                        SET download_status = 'failed', download_progress = 0,
                            error_message = 'Interrupted by server restart'
                        WHERE id = ?
                    """, (fav_id,))
            conn.commit()

        if cleaned_files > 0:
            logger.info(f"Cleaned {cleaned_files} orphaned favorites temporary file(s).")
        return cleaned_files

    def start_download(self, wallpaper_id: str, url: str) -> bool:
        """
        Asynchronously streams high-resolution image to favorites directory.
        Tracks chunked progress in SQLite.
        """
        with self.lock:
            if wallpaper_id in self.active_downloads and self.active_downloads[wallpaper_id].is_alive():
                logger.info(f"Download for {wallpaper_id} already active.")
                return True

            self._cancelled.discard(wallpaper_id)
            thread = threading.Thread(
                target=self._download_worker,
                args=(wallpaper_id, url),
                name=f"FavDownload-{wallpaper_id[:8]}",
                daemon=True
            )
            self.active_downloads[wallpaper_id] = thread
            thread.start()
            return True

    def _download_worker(self, wallpaper_id: str, url: str):
        # Determine file extension
        raw_ext = url.split(".")[-1].split("?")[0].lower()
        ext = raw_ext if raw_ext in ["jpg", "jpeg", "png", "webp", "svg"] else "jpg"

        dest_file = self.favorites_dir / f"{wallpaper_id}.{ext}"
        rel_path = f"favorites/{wallpaper_id}.{ext}"

        # Duplicate download check: if destination already exists and size > 0
        if dest_file.is_file() and dest_file.stat().st_size > 0:
            file_size = dest_file.stat().st_size
            self.db.update_favorite_download(
                wallpaper_id=wallpaper_id,
                status="completed",
                progress=100,
                file_path=rel_path,
                file_size=file_size
            )
            with self.lock:
                self.active_downloads.pop(wallpaper_id, None)
            return

        # Initialize status as downloading
        self.db.update_favorite_download(
            wallpaper_id=wallpaper_id,
            status="downloading",
            progress=0,
            file_path=rel_path,
            file_size=0
        )

        temp_token = secrets.token_hex(4)
        temp_file = self.favorites_dir / f"{wallpaper_id}.{ext}.tmp.{temp_token}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.0"}
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                total_bytes = resp.headers.get("Content-Length")
                total_size = int(total_bytes) if total_bytes and total_bytes.isdigit() else 0

                downloaded = 0
                last_reported_pct = 0

                with open(temp_file, "wb") as out_f:
                    while True:
                        if wallpaper_id in self._cancelled:
                            raise InterruptedError("Download cancelled by user")

                        chunk = resp.read(CHUNK_SIZE)
                        if not chunk:
                            break

                        out_f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            pct = min(int((downloaded / total_size) * 100), 99)
                            if pct >= last_reported_pct + 5:
                                last_reported_pct = pct
                                self.db.update_favorite_download(
                                    wallpaper_id=wallpaper_id,
                                    status="downloading",
                                    progress=pct,
                                    file_size=downloaded
                                )

                # Atomic finalize
                temp_file.replace(dest_file)
                final_size = dest_file.stat().st_size
                self.db.update_favorite_download(
                    wallpaper_id=wallpaper_id,
                    status="completed",
                    progress=100,
                    file_path=rel_path,
                    file_size=final_size
                )
                logger.info(f"Successfully saved favorite {wallpaper_id} ({round(final_size / (1024*1024), 2)} MB).")

        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError:
                    pass

            error_msg = str(e)
            logger.warning(f"Download failed for favorite {wallpaper_id}: {error_msg}")
            self.db.update_favorite_download(
                wallpaper_id=wallpaper_id,
                status="failed",
                progress=0,
                error_message=error_msg
            )
        finally:
            with self.lock:
                self.active_downloads.pop(wallpaper_id, None)
                self._cancelled.discard(wallpaper_id)

    def cancel_download(self, wallpaper_id: str):
        """Cancels an in-flight download."""
        with self.lock:
            if wallpaper_id in self.active_downloads:
                self._cancelled.add(wallpaper_id)

    def delete_favorite_file(self, wallpaper_id: str, file_path: Optional[str] = None):
        """Cancels download if in-flight and removes local physical file."""
        self.cancel_download(wallpaper_id)

        target = None
        if file_path:
            target = (self.favorites_dir.parent / file_path).resolve()
        else:
            for ext in [".jpg", ".jpeg", ".png", ".webp", ".svg"]:
                cand = self.favorites_dir / f"{wallpaper_id}{ext}"
                if cand.is_file():
                    target = cand
                    break

        if target and target.is_file() and target.is_relative_to(self.favorites_dir.parent):
            try:
                target.unlink(missing_ok=True)
                logger.info(f"Removed physical favorite file {target.name}")
            except OSError as e:
                logger.warning(f"Could not delete favorite file {target}: {e}")

        # Also purge any dangling temp files for this ID
        for tmp_file in self.favorites_dir.glob(f"{wallpaper_id}.*.tmp*"):
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
