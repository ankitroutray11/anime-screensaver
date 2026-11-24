"""
providers.py - Multi-Provider Anime Artwork Retrieval & Failover Engine

Architecture:
- NormalizedWallpaper: Unified metadata dataclass across all providers.
- CircuitBreaker: Circuit breaker pattern (CLOSED, OPEN, HALF_OPEN) with exponential backoff.
- ProviderHealthTracker: Thread-safe latency, availability, and error tracking.
- ArtworkProvider: Abstract base class enforcing rate limits, SFW validation, and timeouts.
- WallhavenProvider: Primary provider (Wallhaven API, purity=100).
- SafebooruProvider: Secondary provider (Safebooru DAPI, strictly SFW).
- KonachanProvider: Secondary provider (Konachan.net API, rating:s SFW).
- ProviderManager: High-level manager orchestrating automatic failovers, circuit resets,
  and user configuration persistence.

Standard Library only (urllib.request, json, time, threading, dataclasses).
"""

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("KuroProviders")

# ---------------------------------------------------------------------------
# 1. Normalized Wallpaper Data Structure
# ---------------------------------------------------------------------------

@dataclass
class NormalizedWallpaper:
    id: str                         # Unique ID, e.g. "wh_12345", "sb_6549491", "kc_410935"
    provider: str                   # "Wallhaven", "Safebooru", "Konachan"
    url: str                        # Direct high-resolution image URL
    thumbnail_url: str              # Small preview / sample URL
    resolution: str                 # e.g. "1920x1080"
    dimension_x: int                # Width in pixels
    dimension_y: int                # Height in pixels
    aspect_ratio: str               # "landscape", "ultrawide", "portrait", or ratio string
    file_size: int                  # Bytes
    anime: str                      # Franchise name
    character: Optional[str]        # Identified character name
    tags: List[str]                 # Associated tags
    purity: str                     # "sfw", "safe", "general"
    views: int                      # Views count
    favorites: int                  # Favorites count
    uploader: Optional[str]         # Uploader username / artist
    upload_date: Optional[str]      # Upload date (ISO string or unix timestamp)
    source_url: str                 # Original web page URL for this artwork
    query_strategy: str = "verified_tag_id"  # "verified_tag_id", "character_tag_id", "franchise_keyword", "alias_keyword", "character_keyword", "booru_failover"
    safety_rating: str = "SAFE"
    safety_reason: str = "verified_sfw"
    provider_purity_raw: Optional[str] = None
    media_type: str = "static"      # "static" or "gif"
    is_animated: bool = False       # True for high-res animated loops

    def to_candidate_dict(self) -> Dict[str, Any]:
        """Converts normalized wallpaper to Kuro database candidate format."""
        return {
            "id": self.id,
            "url": self.url,
            "resolution": self.resolution,
            "anime": self.anime,
            "character": self.character,
            "tags": json.dumps(self.tags) if isinstance(self.tags, list) else str(self.tags),
            "source": self.provider,
            "dimension_x": self.dimension_x,
            "dimension_y": self.dimension_y,
            "aspect_ratio": self.aspect_ratio,
            "file_size": self.file_size,
            "views": self.views,
            "favorites": self.favorites,
            "uploader": self.uploader,
            "upload_date": self.upload_date,
            "source_url": self.source_url,
            "thumbnail_url": self.thumbnail_url,
            "purity": self.purity,
            "query_strategy": self.query_strategy,
            "safety_rating": self.safety_rating,
            "safety_reason": self.safety_reason,
            "provider_purity_raw": self.provider_purity_raw,
            "media_type": self.media_type,
            "is_animated": 1 if self.is_animated else 0
        }


# ---------------------------------------------------------------------------
# 2. Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = "CLOSED"         # Normal operation, calls allowed
    OPEN = "OPEN"             # Tripped, calls blocked until cooldown expires
    HALF_OPEN = "HALF_OPEN"   # Probing single trial call


class CircuitBreaker:
    """
    Thread-safe Circuit Breaker for remote API providers.
    Trips to OPEN on repeated failures or rate limits (HTTP 429).
    Transitions to HALF_OPEN after recovery timeout.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        backoff_factor: float = 2.0,
        max_recovery_timeout: float = 300.0
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.backoff_factor = backoff_factor
        self.max_recovery_timeout = max_recovery_timeout

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.open_until = 0.0
        self.current_timeout = recovery_timeout
        self.lock = threading.Lock()

    def can_execute(self) -> bool:
        """Checks if a request is permitted to proceed."""
        with self.lock:
            now = time.time()
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if now >= self.open_until:
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                return True
            return False

    def record_success(self):
        """Records a successful request, resetting failures and closing circuit."""
        with self.lock:
            self.failure_count = 0
            self.state = CircuitState.CLOSED
            self.current_timeout = self.recovery_timeout

    def record_failure(self, is_rate_limit: bool = False, retry_after: Optional[float] = None):
        """Records an error or rate limit, tripping circuit if threshold reached."""
        with self.lock:
            now = time.time()
            self.failure_count += 1
            self.last_failure_time = now

            if is_rate_limit:
                trip_timeout = retry_after if (retry_after and retry_after > 0) else self.current_timeout
                self.state = CircuitState.OPEN
                self.open_until = now + trip_timeout
                self.current_timeout = min(self.current_timeout * self.backoff_factor, self.max_recovery_timeout)
            elif self.failure_count >= self.failure_threshold or self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.open_until = now + self.current_timeout
                self.current_timeout = min(self.current_timeout * self.backoff_factor, self.max_recovery_timeout)

    def reset(self):
        """Manually forces the circuit breaker back to CLOSED state."""
        with self.lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0.0
            self.open_until = 0.0
            self.current_timeout = self.recovery_timeout

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state and timing for diagnostics."""
        with self.lock:
            now = time.time()
            time_left = max(0.0, self.open_until - now) if self.state == CircuitState.OPEN else 0.0
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "time_remaining_seconds": round(time_left, 1),
                "is_available": (self.state == CircuitState.CLOSED or (self.state == CircuitState.OPEN and now >= self.open_until))
            }


# ---------------------------------------------------------------------------
# 3. Provider Health Tracker
# ---------------------------------------------------------------------------

class ProviderHealthTracker:
    """Tracks latency, availability, rate limits, and error diagnostics per provider."""

    def __init__(self, name: str):
        self.name = name
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.rate_limited_count = 0
        self.consecutive_failures = 0
        self.total_latency_ms = 0.0
        self.last_latency_ms = 0.0
        self.last_error: Optional[str] = None
        self.last_error_time = 0.0
        self.last_success_time = 0.0
        self.lock = threading.Lock()

    def record_request(
        self,
        duration_ms: float,
        success: bool,
        is_rate_limit: bool = False,
        error_msg: Optional[str] = None
    ):
        with self.lock:
            self.total_requests += 1
            self.last_latency_ms = round(duration_ms, 2)
            self.total_latency_ms += duration_ms
            now = time.time()
            if success:
                self.successful_requests += 1
                self.consecutive_failures = 0
                self.last_success_time = now
            else:
                self.failed_requests += 1
                self.consecutive_failures += 1
                self.last_error = error_msg
                self.last_error_time = now
                if is_rate_limit:
                    self.rate_limited_count += 1

    def get_metrics(self) -> Dict[str, Any]:
        with self.lock:
            avg_latency = (self.total_latency_ms / self.total_requests) if self.total_requests > 0 else 0.0
            availability = (self.successful_requests / self.total_requests * 100.0) if self.total_requests > 0 else 100.0
            return {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "rate_limited_count": self.rate_limited_count,
                "consecutive_failures": self.consecutive_failures,
                "average_latency_ms": round(avg_latency, 2),
                "last_latency_ms": self.last_latency_ms,
                "availability_percent": round(availability, 1),
                "last_error": self.last_error,
                "last_error_time": self.last_error_time,
                "last_success_time": self.last_success_time
            }


# ---------------------------------------------------------------------------
# 4. Franchise & Booru Tag Registry Translation
# ---------------------------------------------------------------------------

FRANCHISE_BOORU_TAGS: Dict[str, List[str]] = {
    "jujutsu-kaisen": ["jujutsu_kaisen"],
    "demon-slayer": ["kimetsu_no_yaiba"],
    "attack-on-titan": ["shingeki_no_kyojin"],
    "solo-leveling": ["solo_leveling"],
    "chainsaw-man": ["chainsaw_man"],
    "one-piece": ["one_piece"],
    "bleach": ["bleach"],
    "cyberpunk-edgerunners": ["cyberpunk_edgerunners", "cyberpunk"],
    "neon-genesis-evangelion": ["neon_genesis_evangelion"],
    "naruto": ["naruto", "naruto_shippuuden"],
    "dragon-ball": ["dragon_ball", "dragon_ball_z"],
    "death-note": ["death_note"],
    "hunter-x-hunter": ["hunter_x_hunter"],
    "frieren": ["sousou_no_frieren"],
    "my-hero-academia": ["boku_no_hero_academia"],
    "vinland-saga": ["vinland_saga"],
    "black-clover": ["black_clover"],
    "fate-series": ["fate_(series)", "fate/stay_night", "fate/grand_order"]
}


# ---------------------------------------------------------------------------
# 5. Base Artwork Provider
# ---------------------------------------------------------------------------

class ArtworkProvider:
    """Common interface and base class for all anime artwork providers."""

    def __init__(
        self,
        name: str,
        display_name: str,
        priority: int,
        min_request_interval: float = 1.3,
        timeout: float = 8.0,
        enabled: bool = True
    ):
        self.name = name
        self.display_name = display_name
        self.priority = priority
        self.min_request_interval = min_request_interval
        self.timeout = timeout
        self.enabled = enabled

        self.circuit_breaker = CircuitBreaker()
        self.health_tracker = ProviderHealthTracker(name)
        self.last_request_time = 0.0
        self.lock = threading.Lock()

    def _throttle(self):
        """Enforces rate intervals between queries to respect provider limits."""
        with self.lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
            self.last_request_time = time.time()

    def search(
        self,
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080",
        page: int = 1,
        limit: int = 24,
        media_type: str = "all"
    ) -> List[NormalizedWallpaper]:
        """Must be implemented by subclasses. Returns a list of NormalizedWallpaper."""
        raise NotImplementedError("Subclasses must implement search()")

    def validate_sfw(self, wallpaper: NormalizedWallpaper) -> bool:
        """Guarantees strictly safe-for-work content using Unified Safety Layer."""
        from safety_moderation import SafetyModerationEngine, SafetyRating
        eval_res = SafetyModerationEngine.evaluate_artwork_safety(wallpaper.to_candidate_dict())
        wallpaper.safety_rating = eval_res["safety_rating"].value
        wallpaper.safety_reason = eval_res["safety_reason"]
        wallpaper.provider_purity_raw = eval_res.get("provider_purity_raw")
        return eval_res["safety_rating"] == SafetyRating.SAFE

    def get_health_status(self) -> str:
        """Determines provider health badge status."""
        cb_status = self.circuit_breaker.get_status()
        metrics = self.health_tracker.get_metrics()
        if not self.enabled:
            return "disabled"
        if cb_status["state"] == "OPEN":
            return "rate_limited" if metrics["rate_limited_count"] > 0 else "circuit_open"
        if cb_status["state"] == "HALF_OPEN":
            return "probing"
        if metrics["consecutive_failures"] > 0:
            return "degraded"
        return "healthy"

    def get_status(self) -> Dict[str, Any]:
        """Returns combined health, metrics, and circuit breaker status."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "priority": self.priority,
            "enabled": self.enabled,
            "health_status": self.get_health_status(),
            "circuit": self.circuit_breaker.get_status(),
            "metrics": self.health_tracker.get_metrics()
        }


# ---------------------------------------------------------------------------
# 6. Wallhaven Provider (Primary)
# ---------------------------------------------------------------------------

class WallhavenProvider(ArtworkProvider):
    """
    Primary Provider: Wallhaven API (https://wallhaven.cc/api/v1/search).
    Enforces purity=100 (SFW only), high-res filters, and allowlist validation.
    """

    def __init__(self, priority: int = 1, enabled: bool = True):
        super().__init__(
            name="Wallhaven",
            display_name="Wallhaven (Primary)",
            priority=priority,
            min_request_interval=1.3,
            timeout=8.0,
            enabled=enabled
        )

    def _fetch_wallhaven_api(self, url: str) -> List[Dict[str, Any]]:
        """Executes a single Wallhaven search API request with throttling and circuit breaker."""
        self._throttle()
        t0 = time.perf_counter()
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                duration_ms = (time.perf_counter() - t0) * 1000.0
                self.circuit_breaker.record_success()
                self.health_tracker.record_request(duration_ms, success=True)
                # Contract schema drift detection
                if isinstance(data, dict):
                    try:
                        from wallhaven_compatibility import WallhavenContractValidator
                        is_valid, errs, meta = WallhavenContractValidator.validate_search_response(data)
                        if not is_valid:
                            logger.warning(f"[{self.name}] Schema drift detected: {errs[:2]}")
                    except Exception:
                        pass
                return data.get("data", []) if isinstance(data, dict) else []
        except urllib.error.HTTPError as he:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            is_429 = (he.code == 429)
            retry_after = 20.0 if is_429 else None
            if is_429 and hasattr(he, "headers") and he.headers:
                try:
                    from wallhaven_compatibility import WallhavenContractValidator
                    parsed_hdr = WallhavenContractValidator.parse_rate_limit_headers(he.headers)
                    if parsed_hdr.get("retry_after_seconds"):
                        retry_after = float(parsed_hdr["retry_after_seconds"])
                except Exception:
                    pass
            self.circuit_breaker.record_failure(is_rate_limit=is_429, retry_after=retry_after)
            self.health_tracker.record_request(
                duration_ms, success=False, is_rate_limit=is_429, error_msg=f"HTTP {he.code}: {he.reason}"
            )
            logger.warning(f"[{self.name}] HTTP error {he.code} querying {url}: {he.reason} (retry_after={retry_after}s)")
            raise
        except Exception as ex:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self.circuit_breaker.record_failure(is_rate_limit=False)
            self.health_tracker.record_request(duration_ms, success=False, error_msg=str(ex))
            logger.warning(f"[{self.name}] Request failed querying {url}: {ex}")
            raise

    def search(
        self,
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080",
        page: int = 1,
        limit: int = 24,
        media_type: str = "all"
    ) -> List[NormalizedWallpaper]:
        from franchise_registry import FranchiseRegistry

        if media_type == "gif":
            # Wallhaven specializes in high-resolution static desktop artwork
            return []

        if not self.circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker for {self.name} is OPEN.")

        from wallhaven_compatibility import WallhavenCompatibilityManager
        comp_mgr = WallhavenCompatibilityManager()
        if not comp_mgr.is_safe_to_query():
            raise RuntimeError(f"Safety invariant violated: Wallhaven API marked {comp_mgr.get_status().get('status')}")

        franchise_obj = FranchiseRegistry.get_franchise(franchise_slug) if franchise_slug else None
        anime_title = franchise_obj["name"] if franchise_obj else "Popular Anime"

        # Construct distinct query plans across strategies:
        # Strategy A: Verified Tag ID (numeric 'id:<tag_id>')
        # Strategy B: Keyword / Phrase search ('"<exact_phrase>"')
        # Strategy C: Character Tag ID (numeric 'id:<char_tag_id>')
        query_plans: List[Dict[str, Any]] = []

        if character_name and franchise_obj:
            char_tag_ids = franchise_obj.get("character_tag_ids", {}).get(character_name, [])
            for ctid in char_tag_ids:
                query_plans.append({
                    "strategy": "character_tag_id",
                    "url": FranchiseRegistry.build_wallhaven_tag_query(
                        tag_id=ctid,
                        negative_keywords=franchise_obj.get("negative_keywords"),
                        page=page,
                        ratio=ratio,
                        min_resolution=min_resolution
                    )
                })
            # Supplement/fallback with character keyword
            query_plans.append({
                "strategy": "character_keyword",
                "url": FranchiseRegistry.build_wallhaven_keyword_query(
                    keyword=character_name,
                    negative_keywords=franchise_obj.get("negative_keywords"),
                    page=page,
                    ratio=ratio,
                    min_resolution=min_resolution
                )
            })
        elif franchise_obj:
            tag_ids = franchise_obj.get("wallhaven_tag_ids", [])
            for tid in tag_ids:
                query_plans.append({
                    "strategy": "verified_tag_id",
                    "url": FranchiseRegistry.build_wallhaven_tag_query(
                        tag_id=tid,
                        negative_keywords=franchise_obj.get("negative_keywords"),
                        page=page,
                        ratio=ratio,
                        min_resolution=min_resolution
                    )
                })
            # Secondary strategy: franchise search keyword
            queries = franchise_obj.get("search_queries", [])
            if queries:
                query_plans.append({
                    "strategy": "franchise_keyword",
                    "url": FranchiseRegistry.build_wallhaven_keyword_query(
                        keyword=queries[0],
                        negative_keywords=franchise_obj.get("negative_keywords"),
                        page=page,
                        ratio=ratio,
                        min_resolution=min_resolution
                    )
                })
            # Tertiary strategy: aliases
            for alias in franchise_obj.get("english_aliases", [])[:1]:
                if alias != anime_title and alias not in queries:
                    query_plans.append({
                        "strategy": "alias_keyword",
                        "url": FranchiseRegistry.build_wallhaven_keyword_query(
                            keyword=alias,
                            negative_keywords=franchise_obj.get("negative_keywords"),
                            page=page,
                            ratio=ratio,
                            min_resolution=min_resolution
                        )
                    })
        else:
            # Fallback to general anime search
            query_plans.append({
                "strategy": "franchise_keyword",
                "url": FranchiseRegistry.build_wallhaven_keyword_query(
                    keyword="Anime",
                    negative_keywords=["-original", "-cosplay"],
                    page=page,
                    ratio=ratio,
                    min_resolution=min_resolution
                )
            })

        deduped: Dict[str, NormalizedWallpaper] = {}
        last_error = None
        executed_strategies = []

        # Prepare ambiguity filters
        excluded_keywords = [
            k.lower().strip() for k in (franchise_obj.get("excluded_keywords", []) if franchise_obj else []) if k.strip()
        ]
        excluded_tag_ids = set(franchise_obj.get("excluded_tag_ids", []) if franchise_obj else [])

        for plan in query_plans:
            strat_name = plan["strategy"]
            url = plan["url"]
            try:
                raw_items = self._fetch_wallhaven_api(url)
                executed_strategies.append(strat_name)
            except Exception as e:
                last_error = e
                logger.info(f"[{self.name}] Strategy {strat_name} failed ({e}), attempting next fallback strategy.")
                continue

            for item in raw_items:
                img_id = str(item.get("id"))
                img_url = item.get("path")
                if not img_id or not img_url:
                    continue

                # 1. Enforce SFW purity
                purity_raw = item.get("purity", "sfw")
                if purity_raw != "100" and purity_raw != "sfw":
                    continue

                # 2. Ambiguity & Exclusion Guard
                tags_raw = item.get("tags") or []
                item_tag_names = []
                item_tag_ids = []
                if isinstance(tags_raw, list):
                    for t in tags_raw:
                        if isinstance(t, dict):
                            if t.get("name"):
                                item_tag_names.append(str(t["name"]).lower().strip())
                            if t.get("id"):
                                item_tag_ids.append(int(t["id"]))
                        elif isinstance(t, str):
                            item_tag_names.append(t.lower().strip())

                # Check excluded tag IDs
                if any(tid in excluded_tag_ids for tid in item_tag_ids):
                    continue

                # Check excluded ambiguity keywords in tag names, source, or colors
                colors = item.get("colors", [])
                text_to_check = " ".join(item_tag_names + [str(c).lower() for c in colors] + [str(item.get("source", "")).lower()])
                if any(ek in text_to_check for ek in excluded_keywords):
                    continue

                # 3. Deduplication: only keep the first occurrence across strategies
                if img_id in deduped:
                    continue

                dim_x = int(item.get("dimension_x", 1920))
                dim_y = int(item.get("dimension_y", 1080))
                file_size = int(item.get("file_size", 0))
                views = int(item.get("views", 0))
                favorites = int(item.get("favorites", 0))
                uploader_raw = item.get("uploader")
                uploader_name = (
                    uploader_raw.get("username")
                    if isinstance(uploader_raw, dict)
                    else (uploader_raw if isinstance(uploader_raw, str) else None)
                )
                upload_date = item.get("created_at")
                source_url = item.get("source") or item.get("url") or f"https://wallhaven.cc/w/{img_id}"

                deduped[img_id] = NormalizedWallpaper(
                    id=img_id,
                    provider=self.name,
                    url=img_url,
                    thumbnail_url=item.get("thumbs", {}).get("small") or item.get("thumbs", {}).get("large") or img_url,
                    resolution=item.get("resolution", f"{dim_x}x{dim_y}"),
                    dimension_x=dim_x,
                    dimension_y=dim_y,
                    aspect_ratio="32:9" if (dim_x and dim_y and (dim_x / max(1, dim_y)) >= 2.85) else ratio,
                    file_size=file_size,
                    anime=anime_title,
                    character=character_name,
                    tags=item_tag_names if item_tag_names else (colors if isinstance(colors, list) else []),
                    purity="sfw",
                    views=views,
                    favorites=favorites,
                    uploader=uploader_name,
                    upload_date=upload_date,
                    source_url=source_url,
                    query_strategy=strat_name,
                    provider_purity_raw=str(purity_raw)
                )

                if len(deduped) >= limit:
                    break

            # If we achieved enough items from the primary strategy, stop early
            if len(deduped) >= min(limit, 12):
                break

        if not deduped and last_error is not None:
            raise last_error

        return list(deduped.values())


# ---------------------------------------------------------------------------
# 7. Safebooru Provider (Secondary)
# ---------------------------------------------------------------------------

class SafebooruProvider(ArtworkProvider):
    """
    Secondary Provider: Safebooru DAPI (https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1).
    Strictly Safe For Work by policy. Enforces -rating:questionable -rating:explicit
    and checks post rating is 'general' or 'safe'.
    """

    def __init__(self, priority: int = 2, enabled: bool = True):
        super().__init__(
            name="Safebooru",
            display_name="Safebooru (Secondary Booru)",
            priority=priority,
            min_request_interval=1.2,
            timeout=8.0,
            enabled=enabled
        )

    def _translate_tags(
        self,
        franchise_slug: Optional[str],
        character_name: Optional[str],
        ratio: str,
        media_type: str = "all"
    ) -> str:
        tags: List[str] = ["-rating:questionable", "-rating:explicit"]

        if media_type == "gif" or ratio == "gif":
            tags.append("animated")

        if franchise_slug and franchise_slug in FRANCHISE_BOORU_TAGS:
            booru_tag = FRANCHISE_BOORU_TAGS[franchise_slug][0]
            tags.append(booru_tag)
        elif franchise_slug and franchise_slug != "all":
            clean_f = re.sub(r"[^a-zA-Z0-9]+", "_", franchise_slug.lower()).strip("_")
            tags.append(clean_f)
        elif media_type != "gif" and ratio != "gif":
            # General high-quality scenic anime
            tags.append("scenery")

        if character_name and character_name.lower() != "all":
            clean_c = re.sub(r"[^a-zA-Z0-9]+", "_", character_name.lower()).strip("_")
            tags.append(clean_c)

        if media_type == "gif" or ratio == "gif":
            tags.append("width:>=800")
        elif ratio == "landscape":
            tags.append("width:>=1920")
        elif ratio in ("dual", "32:9", "32x9", "dual_screen"):
            tags.append("width:>=3840")
            tags.append("wide_shot")
        elif ratio == "ultrawide":
            tags.append("width:>=2560")
        elif ratio == "portrait":
            tags.append("height:>=1080")

        return " ".join(tags)

    def search(
        self,
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080",
        page: int = 1,
        limit: int = 24,
        media_type: str = "all"
    ) -> List[NormalizedWallpaper]:
        if not self.circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker for {self.name} is OPEN.")

        self._throttle()
        t0 = time.perf_counter()

        query_tags = self._translate_tags(franchise_slug, character_name, ratio, media_type=media_type)
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": "1",
            "limit": str(limit),
            "pid": str(max(0, page - 1)),
            "tags": query_tags
        }
        url = "https://safebooru.org/index.php?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else []
                duration_ms = (time.perf_counter() - t0) * 1000.0
                self.circuit_breaker.record_success()
                self.health_tracker.record_request(duration_ms, success=True)

            if not isinstance(data, list):
                return []

            from franchise_registry import FranchiseRegistry
            franchise_obj = FranchiseRegistry.get_franchise(franchise_slug) if franchise_slug else None
            anime_title = franchise_obj["name"] if franchise_obj else "Popular Anime"

            results: List[NormalizedWallpaper] = []
            for item in data:
                # SFW Verification: rating must be general/safe/g
                rating = str(item.get("rating", "")).lower()
                if rating not in ("general", "safe", "g", "s"):
                    continue

                raw_id = item.get("id")
                if not raw_id:
                    continue
                img_id = f"sb_{raw_id}"

                file_url = item.get("file_url")
                if not file_url:
                    directory = item.get("directory")
                    image = item.get("image")
                    if directory and image:
                        file_url = f"https://safebooru.org/images/{directory}/{image}"
                if not file_url:
                    continue

                if file_url.startswith("//"):
                    file_url = "https:" + file_url

                preview_url = item.get("preview_url") or item.get("sample_url") or file_url
                if preview_url.startswith("//"):
                    preview_url = "https:" + preview_url

                dim_x = int(item.get("width") or 0)
                dim_y = int(item.get("height") or 0)

                tags_str = item.get("tags", "")
                tag_list = tags_str.split() if isinstance(tags_str, str) else []
                is_gif = (file_url and file_url.lower().endswith(".gif")) or ("animated" in tag_list)

                # Ratio & resolution check
                if media_type == "gif" or ratio == "gif":
                    if not is_gif:
                        continue
                    if dim_x < 480 or dim_y < 270:
                        continue
                elif ratio == "landscape":
                    if dim_x < 1920 or dim_x <= dim_y:
                        continue
                elif ratio in ("dual", "32:9", "32x9", "dual_screen"):
                    if dim_x < 2560 or (dim_x / max(1, dim_y)) < 2.8:
                        continue
                elif ratio == "ultrawide":
                    if dim_x < 2560 or (dim_x / max(1, dim_y)) < 1.95:
                        continue
                elif ratio == "portrait":
                    if dim_y < 1080 or dim_y <= dim_x:
                        continue

                score = int(item.get("score") or 0)
                owner = item.get("owner")
                source_url = f"https://safebooru.org/index.php?page=post&s=view&id={raw_id}"

                results.append(NormalizedWallpaper(
                    id=img_id,
                    provider=self.name,
                    url=file_url,
                    thumbnail_url=preview_url,
                    resolution=f"{dim_x}x{dim_y}",
                    dimension_x=dim_x,
                    dimension_y=dim_y,
                    aspect_ratio="32:9" if (dim_x and dim_y and (dim_x / max(1, dim_y)) >= 2.85) else ratio,
                    file_size=0,
                    anime=anime_title,
                    character=character_name,
                    tags=tag_list[:15],
                    purity="sfw",
                    views=max(1, score * 10),
                    favorites=max(0, score),
                    uploader=owner,
                    upload_date=None,
                    source_url=source_url,
                    query_strategy="booru_failover",
                    provider_purity_raw=str(item.get("rating", "g")),
                    media_type="gif" if is_gif else "static",
                    is_animated=is_gif
                ))

            return results

        except urllib.error.HTTPError as he:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            is_429 = (he.code == 429)
            self.circuit_breaker.record_failure(is_rate_limit=is_429)
            self.health_tracker.record_request(
                duration_ms, success=False, is_rate_limit=is_429, error_msg=f"HTTP {he.code}: {he.reason}"
            )
            logger.warning(f"[{self.name}] HTTP error {he.code}: {he.reason}")
            raise
        except Exception as ex:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self.circuit_breaker.record_failure(is_rate_limit=False)
            self.health_tracker.record_request(duration_ms, success=False, error_msg=str(ex))
            logger.warning(f"[{self.name}] Request failed: {ex}")
            raise


# ---------------------------------------------------------------------------
# 8. Konachan Provider (Secondary)
# ---------------------------------------------------------------------------

class KonachanProvider(ArtworkProvider):
    """
    Secondary Provider: Konachan (STRICTLY https://konachan.net/post.json).
    Always specifies tag rating:s (safe only) and verifies post rating == 's'.
    Provides high-resolution anime desktop wallpapers.
    """

    def __init__(self, priority: int = 3, enabled: bool = True):
        super().__init__(
            name="Konachan",
            display_name="Konachan.net (Secondary Hi-Res)",
            priority=priority,
            min_request_interval=1.5,
            timeout=8.0,
            enabled=enabled
        )

    def _translate_tags(self, franchise_slug: Optional[str], character_name: Optional[str], media_type: str = "all") -> str:
        tags: List[str] = ["rating:s"]

        if media_type == "gif":
            tags.append("animated")

        if franchise_slug and franchise_slug in FRANCHISE_BOORU_TAGS:
            booru_tag = FRANCHISE_BOORU_TAGS[franchise_slug][0]
            tags.append(booru_tag)
        elif franchise_slug and franchise_slug != "all":
            clean_f = re.sub(r"[^a-zA-Z0-9]+", "_", franchise_slug.lower()).strip("_")
            tags.append(clean_f)
        elif media_type != "gif":
            tags.append("landscape")

        if character_name and character_name.lower() != "all":
            clean_c = re.sub(r"[^a-zA-Z0-9]+", "_", character_name.lower()).strip("_")
            tags.append(clean_c)

        return " ".join(tags)

    def search(
        self,
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080",
        page: int = 1,
        limit: int = 24,
        media_type: str = "all"
    ) -> List[NormalizedWallpaper]:
        if not self.circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker for {self.name} is OPEN.")

        self._throttle()
        t0 = time.perf_counter()

        query_tags = self._translate_tags(franchise_slug, character_name, media_type=media_type)
        params = {
            "page": str(page),
            "limit": str(limit),
            "tags": query_tags
        }
        url = "https://konachan.net/post.json?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else []
                duration_ms = (time.perf_counter() - t0) * 1000.0
                self.circuit_breaker.record_success()
                self.health_tracker.record_request(duration_ms, success=True)

            if not isinstance(data, list):
                return []

            from franchise_registry import FranchiseRegistry
            franchise_obj = FranchiseRegistry.get_franchise(franchise_slug) if franchise_slug else None
            anime_title = franchise_obj["name"] if franchise_obj else "Popular Anime"

            results: List[NormalizedWallpaper] = []
            for item in data:
                # SFW Verification: rating must be 's' or 'safe'
                rating = str(item.get("rating", "")).lower()
                if rating not in ("s", "safe"):
                    continue

                raw_id = item.get("id")
                if not raw_id:
                    continue
                img_id = f"kc_{raw_id}"

                file_url = item.get("file_url") or item.get("jpeg_url")
                if not file_url:
                    continue

                if file_url.startswith("//"):
                    file_url = "https:" + file_url

                preview_url = item.get("preview_url") or item.get("sample_url") or file_url
                if preview_url.startswith("//"):
                    preview_url = "https:" + preview_url

                dim_x = int(item.get("width") or 0)
                dim_y = int(item.get("height") or 0)

                tags_str = item.get("tags", "")
                tag_list = tags_str.split() if isinstance(tags_str, str) else []
                is_gif = (file_url and file_url.lower().endswith(".gif")) or ("animated" in tag_list)

                # Ratio & resolution check
                if media_type == "gif" or ratio == "gif":
                    if not is_gif:
                        continue
                    if dim_x < 480 or dim_y < 270:
                        continue
                elif ratio == "landscape":
                    if dim_x < 1920 or dim_x <= dim_y:
                        continue
                elif ratio in ("dual", "32:9", "32x9", "dual_screen"):
                    if dim_x < 2560 or (dim_x / max(1, dim_y)) < 2.8:
                        continue
                elif ratio == "ultrawide":
                    if dim_x < 2560 or (dim_x / max(1, dim_y)) < 1.95:
                        continue
                elif ratio == "portrait":
                    if dim_y < 1080 or dim_y <= dim_x:
                        continue

                score = int(item.get("score") or 0)
                author = item.get("author")
                created_at = item.get("created_at")
                file_size = int(item.get("file_size") or 0)
                source_url = f"https://konachan.net/post/show/{raw_id}"

                results.append(NormalizedWallpaper(
                    id=img_id,
                    provider=self.name,
                    url=file_url,
                    thumbnail_url=preview_url,
                    resolution=f"{dim_x}x{dim_y}",
                    dimension_x=dim_x,
                    dimension_y=dim_y,
                    aspect_ratio="32:9" if (dim_x and dim_y and (dim_x / max(1, dim_y)) >= 2.85) else ratio,
                    file_size=file_size,
                    anime=anime_title,
                    character=character_name,
                    tags=tag_list[:15],
                    purity="sfw",
                    views=max(1, score * 15),
                    favorites=max(0, score),
                    uploader=author,
                    upload_date=str(created_at) if created_at else None,
                    source_url=source_url,
                    query_strategy="booru_failover",
                    provider_purity_raw=str(item.get("rating", "g")),
                    media_type="gif" if is_gif else "static",
                    is_animated=is_gif
                ))

            return results

        except urllib.error.HTTPError as he:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            is_429 = (he.code == 429)
            self.circuit_breaker.record_failure(is_rate_limit=is_429)
            self.health_tracker.record_request(
                duration_ms, success=False, is_rate_limit=is_429, error_msg=f"HTTP {he.code}: {he.reason}"
            )
            logger.warning(f"[{self.name}] HTTP error {he.code}: {he.reason}")
            raise
        except Exception as ex:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self.circuit_breaker.record_failure(is_rate_limit=False)
            self.health_tracker.record_request(duration_ms, success=False, error_msg=str(ex))
            logger.warning(f"[{self.name}] Request failed: {ex}")
            raise


# ---------------------------------------------------------------------------
# 8b. nekos.best Provider (High-Resolution Animated GIFs)
# ---------------------------------------------------------------------------

class NekosBestGifProvider(ArtworkProvider):
    """
    Dedicated high-resolution animated anime GIF provider querying nekos.best API v2.
    Returns 100% SFW anime loops with authentic anime series attribution.
    """
    ANIMATED_CATEGORIES = [
        "dance", "smile", "wave", "laugh", "sleep", "nod", "thumbsup",
        "stare", "wink", "happy", "think", "cheer", "blush", "bored",
        "peck", "handhold", "pout", "yawn", "highfive", "lurk"
    ]

    def __init__(self, priority: int = 4, enabled: bool = True):
        super().__init__(
            name="NekosBest",
            display_name="nekos.best (Animated GIFs)",
            priority=priority,
            min_request_interval=1.0,
            timeout=8.0,
            enabled=enabled
        )

    def search(
        self,
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080",
        page: int = 1,
        limit: int = 20,
        media_type: str = "all",
        category: Optional[str] = None
    ) -> List[NormalizedWallpaper]:
        if not self.circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker for {self.name} is OPEN.")

        self._throttle()
        t0 = time.perf_counter()

        chosen_cat = category if (category and category in self.ANIMATED_CATEGORIES) else None
        if not chosen_cat:
            cat_idx = max(0, page - 1) % len(self.ANIMATED_CATEGORIES)
            chosen_cat = self.ANIMATED_CATEGORIES[cat_idx]

        url = f"https://nekos.best/api/v2/{chosen_cat}?amount={min(limit, 20)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.5"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
                duration_ms = (time.perf_counter() - t0) * 1000.0
                self.circuit_breaker.record_success()
                self.health_tracker.record_request(duration_ms, success=True)

            items = data.get("results", [])
            if not isinstance(items, list):
                return []

            results: List[NormalizedWallpaper] = []
            for item in items:
                gif_url = item.get("url")
                if not gif_url or not gif_url.lower().endswith(".gif"):
                    continue

                slug_part = gif_url.split("/")[-1].replace(".gif", "")
                img_id = f"nb_{slug_part[:24]}"

                dims = item.get("dimensions", {})
                dim_x = int(dims.get("width") or 800)
                dim_y = int(dims.get("height") or 450)

                anime_title = item.get("anime_name") or "Anime Animation"
                source_url = item.get("source_url") or gif_url

                results.append(NormalizedWallpaper(
                    id=img_id,
                    provider=self.name,
                    url=gif_url,
                    thumbnail_url=gif_url,
                    resolution=f"{dim_x}x{dim_y}",
                    dimension_x=dim_x,
                    dimension_y=dim_y,
                    aspect_ratio="landscape" if dim_x >= dim_y else "portrait",
                    file_size=0,
                    anime=anime_title,
                    character=character_name,
                    tags=["animated", "gif", chosen_cat, "sfw"],
                    purity="sfw",
                    views=150,
                    favorites=25,
                    uploader="nekos.best",
                    upload_date=None,
                    source_url=source_url,
                    query_strategy="nekos_best_gif",
                    safety_rating="SAFE",
                    safety_reason="verified_sfw",
                    provider_purity_raw="sfw",
                    media_type="gif",
                    is_animated=True
                ))

            return results
        except urllib.error.HTTPError as he:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            is_429 = (he.code == 429)
            self.circuit_breaker.record_failure(is_rate_limit=is_429)
            self.health_tracker.record_request(
                duration_ms, success=False, is_rate_limit=is_429, error_msg=f"HTTP {he.code}: {he.reason}"
            )
            logger.warning(f"[{self.name}] HTTP error {he.code}: {he.reason}")
            raise
        except Exception as ex:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            self.circuit_breaker.record_failure(is_rate_limit=False)
            self.health_tracker.record_request(duration_ms, success=False, error_msg=str(ex))
            logger.warning(f"[{self.name}] Request failed: {ex}")
            raise


# ---------------------------------------------------------------------------
# 9. Provider Manager & Failover Coordinator
# ---------------------------------------------------------------------------

class ProviderManager:
    """
    Coordinates multi-provider failover, health tracking, and circuit breaker states.
    Automatically transitions from Primary (Wallhaven) to Secondary (Safebooru / Konachan / NekosBest)
    on rate limit, timeout, or exhaustion.
    """

    def __init__(self, db_manager: Optional[Any] = None):
        self.db = db_manager
        self.providers: Dict[str, ArtworkProvider] = {
            "wallhaven": WallhavenProvider(priority=1, enabled=True),
            "safebooru": SafebooruProvider(priority=2, enabled=True),
            "konachan": KonachanProvider(priority=3, enabled=True),
            "nekos_best": NekosBestGifProvider(priority=4, enabled=True)
        }
        self.active_provider_name: str = "Wallhaven"
        self.total_failovers: int = 0
        self.last_failover_reason: Optional[str] = None
        self.lock = threading.Lock()

        # Load persisted provider preferences if database manager is supplied
        if self.db:
            self._load_persisted_settings()

    def _load_persisted_settings(self):
        """Loads enabled/disabled flags and priority order from database."""
        try:
            settings = self.db.get_control_center_settings("providers")
            if settings:
                if "wallhaven_enabled" in settings:
                    self.providers["wallhaven"].enabled = bool(settings["wallhaven_enabled"])
                if "safebooru_enabled" in settings:
                    self.providers["safebooru"].enabled = bool(settings["safebooru_enabled"])
                if "konachan_enabled" in settings:
                    self.providers["konachan"].enabled = bool(settings["konachan_enabled"])
                if "nekos_best_enabled" in settings:
                    self.providers["nekos_best"].enabled = bool(settings["nekos_best_enabled"])
        except Exception as e:
            logger.warning(f"Could not load provider settings: {e}")

    def get_providers_in_priority_order(self) -> List[ArtworkProvider]:
        """Returns enabled providers sorted by priority ascending (1 = highest priority)."""
        with self.lock:
            enabled = [p for p in self.providers.values() if p.enabled]
            return sorted(enabled, key=lambda x: x.priority)

    def fetch_candidates_with_failover(
        self,
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080",
        page: int = 1,
        quality_scorer: Optional[Any] = None,
        is_known_func: Optional[Callable[[str], bool]] = None,
        is_blacklisted_func: Optional[Callable[[str], bool]] = None,
        media_type: str = "all"
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Attempts retrieval across configured providers in priority order.
        Fails over cleanly when a provider is rate limited, times out, or trips its circuit breaker.
        Returns (candidate_dictionaries, successful_provider_name).
        """
        ordered_providers = self.get_providers_in_priority_order()
        if not ordered_providers:
            logger.warning("[ProviderManager] All artwork providers are disabled.")
            return [], "None"

        # If GIFs are specifically requested, reorder to providers with animated GIF support
        if media_type == "gif":
            gif_providers = [p for p in ordered_providers if isinstance(p, (SafebooruProvider, KonachanProvider, NekosBestGifProvider))]
            if gif_providers:
                ordered_providers = gif_providers

        primary = ordered_providers[0]

        for i, provider in enumerate(ordered_providers):
            # Check circuit breaker before attempting connection
            if not provider.circuit_breaker.can_execute():
                status = provider.circuit_breaker.get_status()
                logger.info(
                    f"[ProviderManager] Skipping {provider.name} (Circuit {status['state']}, "
                    f"cooldown: {status['time_remaining_seconds']}s remaining)."
                )
                if provider == primary:
                    self.total_failovers += 1
                    self.last_failover_reason = f"{provider.name} circuit open"
                continue

            try:
                logger.info(f"[ProviderManager] Attempting artwork retrieval from {provider.display_name}...")
                wallpapers = provider.search(
                    franchise_slug=franchise_slug,
                    character_name=character_name,
                    ratio=ratio,
                    min_resolution=min_resolution,
                    page=page,
                    media_type=media_type
                )

                if not wallpapers:
                    logger.info(f"[ProviderManager] {provider.name} returned 0 results for page {page}.")
                    # If this was the primary and returned empty, we try failover to secondary
                    if i < len(ordered_providers) - 1:
                        self.total_failovers += 1
                        self.last_failover_reason = f"{provider.name} returned empty results"
                        continue
                    else:
                        return [], provider.name

                candidates: List[Dict[str, Any]] = []
                for wp in wallpapers:
                    # Enforce strict SFW filter & Moderation Layer
                    from safety_moderation import SafetyModerationEngine, SafetyRating
                    eval_res = SafetyModerationEngine.evaluate_artwork_safety(
                        wp.to_candidate_dict(),
                        db_manager=self.db
                    )
                    wp.safety_rating = eval_res["safety_rating"].value
                    wp.safety_reason = eval_res["safety_reason"]
                    wp.provider_purity_raw = eval_res.get("provider_purity_raw")

                    if eval_res["safety_rating"] != SafetyRating.SAFE:
                        logger.warning(
                            f"[SafetyModeration] Rejecting {wp.id} ({provider.name}): "
                            f"{eval_res['safety_rating'].value} - {eval_res['safety_reason']}"
                        )
                        # Queue ambiguous artwork for optional manual review
                        if eval_res["safety_rating"] == SafetyRating.AMBIGUOUS and self.db:
                            try:
                                self.db.add_to_review_queue(
                                    wp.to_candidate_dict(),
                                    eval_res["safety_reason"],
                                    eval_res["safety_rating"].value
                                )
                            except Exception:
                                pass
                        continue

                    # Deduplication check against SQLite database
                    if is_known_func and is_known_func(wp.id):
                        continue
                    if is_blacklisted_func and is_blacklisted_func(wp.id):
                        continue
                    if self.db and self.db.is_blocked_in_db("artwork", wp.id):
                        continue

                    cand = wp.to_candidate_dict()

                    # Quality scoring
                    if quality_scorer:
                        score_res = quality_scorer.score_wallpaper({
                            "resolution": wp.resolution,
                            "dimension_x": wp.dimension_x,
                            "dimension_y": wp.dimension_y,
                            "file_size": wp.file_size,
                            "views": wp.views,
                            "favorites": wp.favorites,
                            "colors": wp.tags
                        })
                        cand["quality_score"] = score_res["quality_score"]
                        cand["technical_score"] = score_res["technical_score"]
                        cand["popularity_score"] = score_res["popularity_score"]
                    else:
                        cand["quality_score"] = 75.0
                        cand["technical_score"] = 75.0
                        cand["popularity_score"] = 75.0

                    candidates.append(cand)

                if candidates:
                    if provider.name != primary.name:
                        logger.info(
                            f"[ProviderManager] Successfully failed over to {provider.name}: "
                            f"{len(candidates)} new candidates discovered."
                        )
                    self.active_provider_name = provider.name
                    return candidates, provider.name
                else:
                    # All results were already known/blacklisted, try next provider
                    logger.info(f"[ProviderManager] All items from {provider.name} were already known.")
                    if i < len(ordered_providers) - 1:
                        self.total_failovers += 1
                        self.last_failover_reason = f"{provider.name} candidates already known"
                        continue

            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, Exception) as err:
                is_429 = isinstance(err, urllib.error.HTTPError) and getattr(err, "code", None) == 429
                reason = "HTTP 429 Rate Limit" if is_429 else str(err)
                provider.circuit_breaker.record_failure(is_rate_limit=is_429)
                logger.warning(f"[ProviderManager] {provider.name} failed ({reason}). Switching to next provider...")
                self.total_failovers += 1
                self.last_failover_reason = f"{provider.name} error: {reason}"
                continue

        logger.warning("[ProviderManager] All available artwork providers failed or were exhausted.")
        return [], "Exhausted"

    def toggle_provider(self, name: str, enabled: bool) -> bool:
        """Enables or disables a specific provider and persists setting."""
        with self.lock:
            key = name.lower().strip()
            if key not in self.providers:
                return False
            self.providers[key].enabled = enabled

            if self.db:
                curr = self.db.get_control_center_settings("providers") or {}
                curr[f"{key}_enabled"] = enabled
                self.db.save_control_center_settings("providers", curr)
            return True

    def set_priority(self, order: List[str]) -> bool:
        """Sets priority order (e.g. ['safebooru', 'wallhaven', 'konachan'])."""
        with self.lock:
            for rank, name in enumerate(order, start=1):
                key = name.lower().strip()
                if key in self.providers:
                    self.providers[key].priority = rank
            return True

    def reset_all_circuits(self):
        """Manually resets all tripped circuit breakers across providers."""
        with self.lock:
            for p in self.providers.values():
                p.circuit_breaker.reset()
            logger.info("[ProviderManager] All provider circuit breakers reset to CLOSED.")

    def get_diagnostics(self) -> Dict[str, Any]:
        """Provides full diagnostics report for REST API and diagnostics UI."""
        with self.lock:
            return {
                "active_provider": self.active_provider_name,
                "total_failovers": self.total_failovers,
                "last_failover_reason": self.last_failover_reason,
                "providers": [p.get_status() for p in self.providers.values()]
            }
