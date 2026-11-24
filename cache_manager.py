#!/usr/bin/env python3
"""
Cache Management & LRU Eviction Module for KuroAnime Backend.
Enforces disk space limits, item count thresholds, temporary file cleanup,
and database cache state synchronization.
"""

import os
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("kuro_cache")

# Default limits
DEFAULT_MAX_CACHE_BYTES = 500 * 1024 * 1024  # 500 Megabytes
DEFAULT_MAX_CACHE_FILES = 200                # Max 200 cached images

class CacheManager:
    def __init__(
        self,
        cache_dir: Path,
        max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
        max_files: int = DEFAULT_MAX_CACHE_FILES
    ):
        self.cache_dir = cache_dir
        self.max_bytes = max_bytes
        self.max_files = max_files
        self._stats_lock = threading.Lock()
        self.total_lookups = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def record_lookup(self, hit: bool):
        """Records an image cache lookup event (hit vs miss)."""
        with self._stats_lock:
            self.total_lookups += 1
            if hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

    def get_hit_rate_metrics(self) -> Dict[str, Any]:
        """Returns hit rate, hits, misses, and total lookups."""
        with self._stats_lock:
            lookups = self.total_lookups
            hits = self.cache_hits
            misses = self.cache_misses
            rate = round((hits / lookups) * 100.0, 1) if lookups > 0 else 100.0
            return {
                "lookups": lookups,
                "hits": hits,
                "misses": misses,
                "hit_rate_percent": rate
            }

    def reset_hit_rate_metrics(self):
        """Resets hit rate lookup counters."""
        with self._stats_lock:
            self.total_lookups = 0
            self.cache_hits = 0
            self.cache_misses = 0

    def cleanup_orphaned_temp_files(self) -> int:
        """Removes leftover .tmp files from abruptly terminated downloads."""
        removed = 0
        try:
            for item in self.cache_dir.glob("*.tmp*"):
                if item.is_file():
                    try:
                        item.unlink(missing_ok=True)
                        removed += 1
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Error during temp file cleanup: {e}")
        return removed

    def get_cache_stats(self) -> Dict[str, Any]:
        """Calculates total disk usage and file count in the wallpaper cache."""
        total_size = 0
        file_count = 0
        try:
            for entry in os.scandir(str(self.cache_dir)):
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        total_size += stat.st_size
                        file_count += 1
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Error computing cache statistics: {e}")

        hit_metrics = self.get_hit_rate_metrics()
        return {
            "file_count": file_count,
            "size_bytes": total_size,
            "size_mb": round(total_size / (1024 * 1024), 2),
            "max_bytes": self.max_bytes,
            "max_mb": round(self.max_bytes / (1024 * 1024), 2),
            "max_files": self.max_files,
            "usage_percent": round((total_size / self.max_bytes) * 100, 1) if self.max_bytes > 0 else 0,
            **hit_metrics
        }

    def enforce_cache_limits(self, on_evict_callback=None) -> int:
        """
        Enforces maximum cache size and file count using LRU (Least Recently Used) policy.
        If limits are exceeded, evicts oldest accessed files until usage drops below 85% of threshold.
        Optionally invokes on_evict_callback(wallpaper_id) to update SQLite tracking.
        """
        files_info: List[Dict[str, Any]] = []
        total_size = 0

        try:
            for entry in os.scandir(str(self.cache_dir)):
                if entry.is_file() and not entry.name.endswith(".tmp"):
                    try:
                        stat = entry.stat()
                        total_size += stat.st_size
                        # Use st_atime if available, fallback to st_mtime
                        access_time = max(stat.st_atime, stat.st_mtime)
                        files_info.append({
                            "path": Path(entry.path),
                            "name": entry.name,
                            "id": Path(entry.name).stem,
                            "size": stat.st_size,
                            "access_time": access_time
                        })
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Error scanning cache for eviction: {e}")
            return 0

        # Check if eviction is necessary
        needs_eviction = (total_size > self.max_bytes) or (len(files_info) > self.max_files)
        if not needs_eviction:
            return 0

        # Sort files by access time ascending (oldest first)
        files_info.sort(key=lambda x: x["access_time"])

        target_bytes = int(self.max_bytes * 0.85)
        target_files = int(self.max_files * 0.85)

        evicted_count = 0
        current_size = total_size
        current_files = len(files_info)

        for f in files_info:
            if current_size <= target_bytes and current_files <= target_files:
                break

            try:
                f["path"].unlink(missing_ok=True)
                current_size -= f["size"]
                current_files -= 1
                evicted_count += 1

                if on_evict_callback:
                    try:
                        on_evict_callback(f["id"])
                    except Exception:
                        pass
            except OSError as err:
                logger.warning(f"Could not delete cache file {f['path']}: {err}")

        if evicted_count > 0:
            logger.info(f"LRU Eviction complete: removed {evicted_count} files, freed {round((total_size - current_size)/(1024*1024), 2)} MB.")

        return evicted_count

    def purge_cache(self, on_evict_callback=None) -> int:
        """
        Manually clears all cached wallpapers from disk and notifies callback.
        """
        purged = 0
        try:
            for entry in os.scandir(str(self.cache_dir)):
                if entry.is_file():
                    try:
                        p = Path(entry.path)
                        stem = p.stem.split(".")[0]
                        p.unlink(missing_ok=True)
                        purged += 1
                        if on_evict_callback:
                            try:
                                on_evict_callback(stem)
                            except Exception:
                                pass
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Error purging cache: {e}")
        return purged
