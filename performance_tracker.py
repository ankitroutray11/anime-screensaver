#!/usr/bin/env python3
"""
Application Performance Monitoring & Metrics Aggregator for KuroAnime Screensaver.
Tracks HTTP response times, API failure rates, SQLite query latencies, cache hit rates,
prefetch queue depth, active worker threads, and adaptive rendering parameters.
Pure Python standard library implementation.
"""

import time
import threading
import collections
from typing import Dict, Any, List, Optional

class PerformanceTracker:
    def __init__(self, max_samples: int = 200):
        self._lock = threading.Lock()
        self.max_samples = max_samples
        self._recent_latencies = collections.deque(maxlen=max_samples)
        self._status_counts: Dict[str, int] = collections.defaultdict(int)
        self.total_requests: int = 0
        self.failed_requests: int = 0
        self.total_duration_ms: float = 0.0
        self.last_duration_ms: float = 0.0
        self.start_time: float = time.time()

    def record_request(self, path: str, duration_ms: float, status_code: int):
        """
        Records a completed HTTP request with its execution time and status code.
        """
        with self._lock:
            self.total_requests += 1
            self.total_duration_ms += duration_ms
            self.last_duration_ms = duration_ms
            self._recent_latencies.append(duration_ms)

            # Categorize status code
            if 200 <= status_code < 300:
                self._status_counts["2xx"] += 1
            elif 300 <= status_code < 400:
                self._status_counts["3xx"] += 1
            elif 400 <= status_code < 500:
                self._status_counts["4xx"] += 1
                self.failed_requests += 1
            elif status_code >= 500:
                self._status_counts["5xx"] += 1
                self.failed_requests += 1
            else:
                self._status_counts["other"] += 1

    def get_latency_metrics(self) -> Dict[str, Any]:
        """Calculates average, last, minimum, maximum, and P95 latency."""
        with self._lock:
            total = self.total_requests
            last = round(self.last_duration_ms, 2)
            avg = round(self.total_duration_ms / total, 2) if total > 0 else 0.0

            samples = sorted(list(self._recent_latencies))
            if samples:
                p95_idx = int(len(samples) * 0.95)
                p95 = round(samples[min(p95_idx, len(samples) - 1)], 2)
                min_val = round(samples[0], 2)
                max_val = round(samples[-1], 2)
            else:
                p95 = 0.0
                min_val = 0.0
                max_val = 0.0

            return {
                "total_requests": total,
                "avg_latency_ms": avg,
                "last_latency_ms": last,
                "p95_latency_ms": p95,
                "min_latency_ms": min_val,
                "max_latency_ms": max_val
            }

    def get_failure_metrics(self) -> Dict[str, Any]:
        """Calculates API failure rate percentage and HTTP status breakdown."""
        with self._lock:
            total = self.total_requests
            failed = self.failed_requests
            rate = round((failed / total) * 100.0, 2) if total > 0 else 0.0
            return {
                "total_requests": total,
                "failed_requests": failed,
                "failure_rate_percent": rate,
                "status_distribution": {
                    "2xx": self._status_counts.get("2xx", 0),
                    "3xx": self._status_counts.get("3xx", 0),
                    "4xx": self._status_counts.get("4xx", 0),
                    "5xx": self._status_counts.get("5xx", 0)
                }
            }

    def reset_metrics(self):
        """Resets all rolling latency and error counters."""
        with self._lock:
            self.total_requests = 0
            self.failed_requests = 0
            self.total_duration_ms = 0.0
            self.last_duration_ms = 0.0
            self._recent_latencies.clear()
            self._status_counts.clear()
            self.start_time = time.time()

    def get_performance_snapshot(
        self,
        engine,
        db_manager,
        cache_manager,
        server_start_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Consolidates backend latency, API failure rates, SQLite latency,
        cache hit rate, prefetch buffer depth, and worker health.
        """
        uptime_base = server_start_time or self.start_time
        uptime_sec = round(time.time() - uptime_base, 1)

        db_stats = db_manager.get_stats() if db_manager else {}
        sqlite_metrics = db_manager.get_sqlite_latency_metrics() if db_manager else {}
        cache_stats = cache_manager.get_cache_stats() if cache_manager else {}
        perf_settings = db_manager.get_control_center_settings("performance") if db_manager else {}

        unseen_count = db_stats.get("unseen_count", 0)
        cached_unseen = db_stats.get("cached_unseen_count", 0)
        max_buffer = getattr(engine, "max_unseen_buffer", 40)
        max_cached = getattr(engine, "max_cached_unseen", 15)

        queue_health = "healthy"
        if unseen_count < 5:
            queue_health = "critical_low"
        elif unseen_count < 15:
            queue_health = "refilling"

        worker_alive = bool(engine.worker_thread and engine.worker_thread.is_alive()) if engine else False
        worker_state = getattr(engine, "worker_state", "stopped") if engine else "stopped"
        is_online = getattr(engine, "is_online", True) if engine else True
        active_level = getattr(engine, "active_level", 1) if engine else 1

        return {
            "server_uptime_seconds": uptime_sec,
            "backend_latency": self.get_latency_metrics(),
            "api_failures": self.get_failure_metrics(),
            "sqlite_latency": sqlite_metrics,
            "cache": cache_stats,
            "prefetch_queue": {
                "unseen_count": unseen_count,
                "cached_unseen_count": cached_unseen,
                "max_unseen_buffer": max_buffer,
                "max_cached_unseen": max_cached,
                "queue_health": queue_health
            },
            "workers": {
                "active_threads": threading.active_count(),
                "prefetch_worker_alive": worker_alive,
                "worker_state": worker_state,
                "is_online": is_online,
                "active_level": active_level
            },
            "providers": engine.provider_manager.get_diagnostics() if (engine and hasattr(engine, "provider_manager")) else {},
            "quality_profile": perf_settings.get("perf_quality_profile", "auto"),
            "max_concurrent_decodes": perf_settings.get("perf_max_concurrent_decodes", 1),
            "timestamp": int(time.time())
        }
