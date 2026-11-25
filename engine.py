"""
Upgraded Wallpaper Discovery, Prefetching & Transactional Lifecycle Engine.
Integrates Centralized Anime Franchise Registry, strict tag allowlists,
character detection, exclusion filters, pagination, and exhaustion tracking.
"""

import os
import sys
import time
import json
import uuid
import socket
import secrets
import logging
import threading
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple

from database import DatabaseManager
from franchise_registry import FranchiseRegistry, FRANCHISE_REGISTRY
from cache_manager import CacheManager
from recommendation_engine import PersonalizationEngine
from quality_scorer import QualityScorer
from providers import ProviderManager

logger = logging.getLogger("kuro_engine")

def check_internet_connection(timeout: float = 0.8) -> bool:
    """Fast socket probe checking internet connectivity without hitting APIs."""
    for host, port in [("1.1.1.1", 53), ("8.8.8.8", 53)]:
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except OSError:
            continue
    return False

class WallpaperEngine:
    def __init__(
        self,
        db_manager: DatabaseManager,
        max_unseen_buffer: int = 40,
        max_cached_unseen: int = 15,
        maintenance_interval: float = 5.0,
        auto_prefetch: bool = True
    ):
        self.db = db_manager
        self.max_unseen_buffer = max_unseen_buffer
        self.max_cached_unseen = max_cached_unseen
        self.maintenance_interval = maintenance_interval
        self.min_unseen_buffer = 10
        self.lock = threading.Lock()
        self.auto_prefetch = auto_prefetch

        # Worker lifecycle
        self.worker_state = "stopped"
        self._running = False
        self._stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        # Paging state per search key: (franchise_slug, character_name, ratio) -> current_page
        self.page_tracker: Dict[str, int] = {}
        # Set of exhausted search keys
        self.exhausted_keys: Set[str] = set()

        # Rate-limiting state
        self.last_api_request_time = 0.0
        self.min_request_interval = 1.2  # seconds
        self.backoff_until = 0.0

        # Offline-first & Network state
        self.is_online = True
        self.consecutive_network_failures = 0
        self.network_backoff_until = 0.0
        self.current_backoff_delay = 3.0
        self.active_level = 1  # 1: Live Stream, 2: Local Cache, 3: Curated Offline
        self.cache_dir = Path(__file__).resolve().parent / ".cache" / "wallpapers"
        self.cache_manager = CacheManager(self.cache_dir)
        self._discovery_in_progress = False

        # Cleanup orphaned temp files from interrupted downloads
        self.cache_manager.cleanup_orphaned_temp_files()

        # Cache of validated wallpaper tags to avoid duplicate detail lookups
        self.tag_validation_cache: Dict[str, Tuple[bool, Optional[str]]] = {}

        # Intelligent recommendation & personalization engine
        self.recommendation_engine = PersonalizationEngine(self.db)
        self._async_threads: List[threading.Thread] = []

        # Intelligent artwork quality scoring engine
        self.quality_scorer = QualityScorer(self.db.get_quality_settings())
        try:
            self.db.backfill_quality_scores(self.quality_scorer)
        except Exception as e:
            logger.warning(f"Quality scores backfill skipped: {e}")

        # Multi-provider artwork failover manager (Wallhaven, Safebooru, Konachan)
        self.provider_manager = ProviderManager(self.db)

        # Automatic downloads saving manager
        self.autosaver = None

        # Recover any lingering reservations from previous crashes immediately
        self.db.recover_all_reservations_on_startup()

        # Start background prefetch & reservation recovery worker if auto_prefetch is enabled
        if self.auto_prefetch:
            self.start()

    def start(self):
        """Starts the background maintenance and prefetch worker thread."""
        with self.lock:
            if self._running:
                return
            self._running = True
            self.worker_state = "running"
            self._stop_event.clear()
            self.worker_thread = threading.Thread(
                target=self._maintenance_worker,
                name="KuroMaintenanceWorker",
                daemon=True
            )
            self.worker_thread.start()
            logger.info("Background maintenance worker started.")

    def stop(self, timeout: float = 5.0):
        """Gracefully signals and joins the background maintenance worker thread."""
        self._running = False
        self.worker_state = "stopping"
        self._stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=timeout)
        with self.lock:
            for t in self._async_threads:
                if t.is_alive():
                    t.join(timeout=1.0)
            self._async_threads.clear()
        self.worker_state = "stopped"
        logger.info("Background maintenance worker stopped cleanly.")

    def check_connectivity(self, force_probe: bool = False) -> bool:
        """
        Determines if online. If currently in exponential backoff, returns False
        immediately without blocking, preventing stalls or API hammer.
        """
        now = time.time()
        if not force_probe and now < self.network_backoff_until:
            return False

        online = check_internet_connection(timeout=0.8)
        if online:
            if not self.is_online:
                print("[KuroEngine] Network restored. Resuming Level 1 (Live Stream).")
            self.is_online = True
            self.consecutive_network_failures = 0
            self.current_backoff_delay = 3.0
            self.network_backoff_until = 0.0
            return True
        else:
            self.is_online = False
            self.consecutive_network_failures += 1
            self.network_backoff_until = now + self.current_backoff_delay
            print(f"[KuroEngine] Network offline. Backing off for {self.current_backoff_delay:.1f}s. Using local fallback.")
            self.current_backoff_delay = min(self.current_backoff_delay * 2, 60.0)
            return False

    def _maintenance_worker(self):
        """Runs periodic abandoned reservation cleanup, local caching, and prefetching."""
        while self._running:
            try:
                # 1. Recover abandoned reservations older than 45 seconds
                self.db.recover_abandoned_reservations(timeout_seconds=45.0)

                # 2. Check network connectivity status
                is_connected = self.check_connectivity()

                # 3. Enforce disk cache bounds and LRU eviction
                self.cache_manager.enforce_cache_limits(on_evict_callback=self.db.unmark_wallpaper_cached)

                # 4. If online, prefetch & cache up to 3 uncached UNSEEN wallpapers (bounded queue)
                if is_connected:
                    self._prefetch_and_cache_unseen(max_items=3)

                # 5. Check if Level 1 UNSEEN buffer needs refilling
                if is_connected:
                    stats = self.db.get_stats()
                    if stats.get("unseen_count", 0) < self.min_unseen_buffer:
                        # Pick an unexhausted franchise to replenish
                        all_franchises = FranchiseRegistry.get_all()
                        unexhausted = [f for f in all_franchises if f["slug"] not in self.exhausted_keys]
                        if unexhausted:
                            pick = unexhausted[int(time.time() * 1000) % len(unexhausted)]
                            self.fetch_and_discover(franchise_slug=pick["slug"])
            except Exception as e:
                logger.warning(f"Maintenance loop notice: {e}")

            # Sleep with early-wake on stop signal
            self._stop_event.wait(timeout=self.maintenance_interval)

    def _prefetch_and_cache_unseen(self, max_items: int = 3):
        """
        Background downloads remote UNSEEN wallpapers to .cache/wallpapers/
        and commits their local path in SQLite.
        Bounded: pauses when max_cached_unseen is reached.
        Uses atomic temp file writes to avoid corrupted images on partial downloads.
        Does NOT mark wallpapers as seen or displayed!
        """
        try:
            stats = self.db.get_stats()
            cached_unseen = stats.get("cached_unseen_count", 0)
            if cached_unseen >= self.max_cached_unseen:
                return

            allowed_downloads = min(max_items, self.max_cached_unseen - cached_unseen)
            if allowed_downloads <= 0:
                return

            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, url FROM wallpaper_lifecycle
                    WHERE status = 'UNSEEN' AND level = 1 AND is_cached = 0 AND url LIKE 'http%'
                    AND (safety_rating IS NULL OR safety_rating = 'SAFE')
                    AND id NOT IN (SELECT wallpaper_id FROM blacklist)
                    AND id NOT IN (SELECT entity_value FROM blocked_entities WHERE entity_type = 'artwork')
                    LIMIT ?
                """, (allowed_downloads,))
                rows = cur.fetchall()

            for row in rows:
                if not self._running or not self.is_online:
                    break
                img_id = row[0]
                img_url = row[1]
                ext = img_url.split(".")[-1].split("?")[0].lower()
                if ext not in ["jpg", "jpeg", "png", "webp"]:
                    ext = "jpg"
                dest_file = self.cache_dir / f"{img_id}.{ext}"

                if not dest_file.exists():
                    temp_file = dest_file.with_suffix(f".tmp.{secrets.token_hex(4)}")
                    try:
                        req = urllib.request.Request(
                            img_url,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.0"}
                        )
                        with urllib.request.urlopen(req, timeout=10) as resp, open(temp_file, "wb") as f:
                            f.write(resp.read())
                        temp_file.replace(dest_file)
                    except Exception:
                        if temp_file.exists():
                            temp_file.unlink(missing_ok=True)
                        continue

                if dest_file.exists():
                    rel_path = f".cache/wallpapers/{dest_file.name}"
                    self.db.mark_wallpaper_cached(img_id, rel_path, level=2)
        except Exception as e:
            logger.warning(f"Prefetch notice: {e}")

    def _throttle_api(self):
        """Enforces rate limits and exponential backoff on HTTP 429."""
        now = time.time()
        if now < self.backoff_until:
            wait_time = self.backoff_until - now
            time.sleep(min(wait_time, 10.0))

        elapsed = time.time() - self.last_api_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_api_request_time = time.time()

    def _make_search_key(self, franchise_slug: Optional[str], character_name: Optional[str], ratio: str) -> str:
        f_part = franchise_slug.lower() if franchise_slug else "all"
        c_part = character_name.lower() if character_name else "all"
        return f"{f_part}::{c_part}::{ratio}"

    def _fetch_wallpaper_tags(self, wallpaper_id: str) -> List[str]:
        """Fetches tag names for a wallpaper to validate against franchise allowlist."""
        self._throttle_api()
        url = f"https://wallhaven.cc/api/v1/w/{wallpaper_id}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuroScreensaver/3.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                tag_objs = data.get("data", {}).get("tags", [])
                return [t.get("name", "") for t in tag_objs if t.get("name")]
        except Exception:
            return []

    def fetch_and_discover(
        self,
        franchise_slug: Optional[str] = None,
        character_name: Optional[str] = None,
        excluded_franchises: Optional[List[str]] = None,
        excluded_characters: Optional[List[str]] = None,
        ratio: str = "landscape",
        min_resolution: str = "1920x1080",
        media_type: str = "all"
    ) -> int:
        """
        Executes franchise and character-specific discovery using resilient Multi-Provider failover.
        Queries Primary (Wallhaven) with automatic fallback to Secondary providers (Safebooru, Konachan, NekosBest)
        upon rate limits, timeouts, or exhaustion.
        Validates SFW purity, scores technical quality, and commits to SQLite in UNSEEN status.
        """
        with self.lock:
            # Resolve franchise info
            franchise = FranchiseRegistry.get_franchise(franchise_slug) if franchise_slug else None
            actual_slug = franchise["slug"] if franchise else "all"

            search_key = self._make_search_key(actual_slug, character_name, ratio) + f"_{media_type}"
            if search_key in self.exhausted_keys:
                return 0

            # Check bounded buffer per media type so GIFs never starve static wallpapers (and vice versa)
            stats = self.db.get_stats()
            if media_type == "gif":
                if stats.get("unseen_gif_count", 0) >= 25:
                    return 0
            elif stats.get("unseen_static_count", stats.get("unseen_count", 0)) >= self.max_unseen_buffer:
                return 0

            current_page = self.page_tracker.get(search_key, 1)

            try:
                candidates_to_add, used_provider = self.provider_manager.fetch_candidates_with_failover(
                    franchise_slug=actual_slug if actual_slug != "all" else None,
                    character_name=character_name,
                    ratio=ratio,
                    min_resolution=min_resolution,
                    page=current_page,
                    quality_scorer=self.quality_scorer,
                    is_known_func=self.db.is_known,
                    is_blacklisted_func=self.db.is_blacklisted,
                    media_type=media_type
                )

                wh = self.provider_manager.providers.get("wallhaven")
                if wh and wh.circuit_breaker.state.value in ("OPEN", "HALF_OPEN"):
                    self.backoff_until = max(self.backoff_until, wh.circuit_breaker.open_until)

                if not candidates_to_add:
                    self.exhausted_keys.add(search_key)
                    print(f"[KuroEngine] Search exhausted for '{search_key}' across providers (page {current_page}).")
                    return 0

                added = self.db.add_unseen_wallpapers(candidates_to_add)

                # Advance pagination tracker
                self.page_tracker[search_key] = current_page + 1

                franchise_name = franchise["name"] if franchise else "All Anime"
                if added > 0:
                    char_str = f" ({character_name})" if character_name else ""
                    print(f"[KuroEngine] Discovered {added} verified wallpapers from '{franchise_name}{char_str}' via {used_provider} (page {current_page}).")
                else:
                    self.exhausted_keys.add(search_key)
                    print(f"[KuroEngine] All items on page {current_page} of '{search_key}' were already processed. Marked exhausted.")

                return added

            except urllib.error.HTTPError as he:
                if he.code == 429:
                    print(f"[KuroEngine] Rate limited by provider (HTTP 429). Backing off 20s.")
                    self.backoff_until = time.time() + 20.0
                else:
                    print(f"[KuroEngine] HTTP error during discovery for '{search_key}': {he}")
                return 0
            except urllib.error.URLError as ue:
                self.is_online = False
                self.consecutive_network_failures += 1
                self.network_backoff_until = time.time() + self.current_backoff_delay
                print(f"[KuroEngine] Network error during discovery: {ue}. Engaging offline fallback (backoff: {self.current_backoff_delay:.1f}s).")
                self.current_backoff_delay = min(self.current_backoff_delay * 2, 60.0)
                return 0
            except Exception as e:
                print(f"[KuroEngine] Discovery error for '{search_key}': {e}")
                return 0

    def _reserve_safe_candidate(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Reserves a candidate from SQLite and revalidates against Unified Safety Policy.
        If candidate fails safety revalidation (e.g. tag blocked after download), marks it
        BLOCKED in DB, evicts any cached file, and attempts next candidate up to 5 times.
        """
        from safety_moderation import SafetyModerationEngine
        for _ in range(5):
            candidate = self.db.reserve_next_wallpaper(**kwargs)
            if not candidate:
                return None

            is_safe, reason = SafetyModerationEngine.revalidate_before_display(candidate, self.db)
            if is_safe:
                return candidate

            # Revalidation failed: block and evict
            logger.warning(
                f"[SafetyModeration] Pre-display revalidation failed for {candidate.get('id')}: {reason}. "
                f"Blocking and evicting."
            )
            self.db.add_blocked_entity("artwork", candidate["id"], reason=f"Pre-display validation failed: {reason}")
            try:
                self.cache_manager.evict(candidate["id"])
            except Exception:
                pass
        return None

    def get_next(
        self,
        anime: str = "all",
        character: Optional[str] = None,
        selected_franchises: Optional[List[str]] = None,
        excluded_franchises: Optional[List[str]] = None,
        excluded_characters: Optional[List[str]] = None,
        ratio: str = "landscape",
        media_type: str = "all"
    ) -> Dict[str, Any]:
        """
        Transactional 3-Layer Fallback Candidate Retrieval:
        LEVEL 1: LIVE WALLPAPER STREAM
        - Fetch fresh artwork from Wallhaven.
        - Background prefetch.
        - API retry and rate-limit handling.
        LEVEL 2: LOCAL IMAGE CACHE
        - Previously downloaded wallpapers (.cache/wallpapers) & favorites.
        - Cached artwork metadata & SQLite tracking.
        LEVEL 3: CURATED OFFLINE COLLECTION
        - Local curated anime wallpaper directory (curated_wallpapers/).
        - Configurable image pool & persistent tracking.
        - Zero repeated images within the same source pool.
        Never blocks slideshow transitions: discovery is off-thread on cache misses.
        """
        token = str(uuid.uuid4())

        # Resolve franchise slug
        franchise = FranchiseRegistry.get_franchise(anime) if (anime and anime.lower() != "all") else None
        target_name = franchise["name"] if franchise else ("all" if anime == "all" else anime)

        # Quick network check (non-blocking if backed off)
        is_connected = self.check_connectivity()

        # Recommendation & diversity context
        recent_franchises = self.recommendation_engine.get_recent_franchises(limit=3)
        apply_personalization = self.recommendation_engine.is_enabled()

        # Quality scoring criteria
        q_cfg = self.db.get_quality_settings()
        min_quality = q_cfg.get("min_quality_score", 50.0)

        # =========================================================================
        # PRIORITY FOR ANIMATED GIFS: CURATED LOCAL POPULAR ANIME LOOPS (Level 3)
        # Guarantees instant, zero-buffering playback of all downloaded anime loops
        # =========================================================================
        if media_type == "gif":
            reserved = self._reserve_safe_candidate(
                anime=target_name,
                character=character,
                selected_franchises=selected_franchises,
                excluded_franchises=excluded_franchises,
                excluded_characters=excluded_characters,
                token=token,
                ratio=ratio,
                target_level=3,
                recent_franchises=recent_franchises,
                apply_personalization=apply_personalization,
                min_quality=min_quality,
                media_type=media_type
            )
            if not reserved and (target_name != "all" or selected_franchises):
                # Fall back to any unviewed curated anime loop
                reserved = self._reserve_safe_candidate(
                    anime="all",
                    token=token,
                    ratio=ratio,
                    target_level=3,
                    recent_franchises=recent_franchises,
                    apply_personalization=apply_personalization,
                    media_type=media_type
                )
            if reserved:
                self.active_level = 3
                reserved["active_level"] = 3
                reserved["source"] = "Curated Offline Anime"
                reserved["offline"] = not is_connected
                return reserved

        # =========================================================================
        # LAYER 1: LIVE WALLPAPER STREAM (Level 1)
        # =========================================================================
        if is_connected:
            reserved = self._reserve_safe_candidate(
                anime=target_name,
                character=character,
                selected_franchises=selected_franchises,
                excluded_franchises=excluded_franchises,
                excluded_characters=excluded_characters,
                token=token,
                ratio=ratio,
                target_level=1,
                recent_franchises=recent_franchises,
                apply_personalization=apply_personalization,
                min_quality=min_quality,
                media_type=media_type
            )
            if reserved:
                self.active_level = 1
                reserved["active_level"] = 1
                reserved["offline"] = False
                return reserved

            # Buffer miss at Level 1: trigger async background discovery if not already running
            if self.auto_prefetch and not self._discovery_in_progress and self._running:
                def async_discover():
                    if not self._running:
                        return
                    self._discovery_in_progress = True
                    try:
                        if franchise:
                            self.fetch_and_discover(
                                franchise_slug=franchise["slug"],
                                character_name=character,
                                excluded_franchises=excluded_franchises,
                                excluded_characters=excluded_characters,
                                ratio=ratio,
                                media_type=media_type
                            )
                        elif selected_franchises:
                            unexhausted = [f for f in selected_franchises if f not in self.exhausted_keys]
                            if unexhausted:
                                pick_name = unexhausted[int(time.time() * 1000) % len(unexhausted)]
                                f_obj = FranchiseRegistry.get_franchise(pick_name)
                                if f_obj:
                                    self.fetch_and_discover(
                                        franchise_slug=f_obj["slug"],
                                        excluded_franchises=excluded_franchises,
                                        excluded_characters=excluded_characters,
                                        ratio=ratio,
                                        media_type=media_type
                                    )
                        else:
                            all_franchises = FranchiseRegistry.get_all()
                            unexhausted = [f for f in all_franchises if f["slug"] not in self.exhausted_keys]
                            if unexhausted:
                                pick = self.recommendation_engine.select_franchise_by_preference(
                                    unexhausted, recent_franchises=recent_franchises
                                )
                                self.fetch_and_discover(
                                    franchise_slug=pick["slug"],
                                    excluded_franchises=excluded_franchises,
                                    excluded_characters=excluded_characters,
                                    ratio=ratio,
                                    media_type=media_type
                                )
                    finally:
                        self._discovery_in_progress = False

                t = threading.Thread(target=async_discover, daemon=True)
                with self.lock:
                    self._async_threads = [th for th in self._async_threads if th.is_alive()]
                    self._async_threads.append(t)
                t.start()

        # =========================================================================
        # LAYER 2: LOCAL IMAGE CACHE (Level 2)
        # Previously downloaded wallpapers (.cache/wallpapers/) and favorites
        # =========================================================================
        reserved = self._reserve_safe_candidate(
            anime=target_name,
            character=character,
            selected_franchises=selected_franchises,
            excluded_franchises=excluded_franchises,
            excluded_characters=excluded_characters,
            token=token,
            ratio=ratio,
            target_level=2,
            recent_franchises=recent_franchises,
            apply_personalization=apply_personalization,
            min_quality=min_quality,
            media_type=media_type
        )
        if not reserved:
            # Also try any cached item regardless of franchise if specific franchise cache is empty
            reserved = self._reserve_safe_candidate(
                anime="all",
                token=token,
                ratio=ratio,
                target_level=2,
                recent_franchises=recent_franchises,
                apply_personalization=apply_personalization,
                min_quality=min_quality,
                media_type=media_type
            )

        if reserved:
            self.active_level = 2
            reserved["active_level"] = 2
            reserved["source"] = "Local Cache"
            reserved["offline"] = not self.is_online
            return reserved

        # =========================================================================
        # LAYER 3: CURATED OFFLINE COLLECTION (Level 3)
        # Bundled and user-added offline collection in curated_wallpapers/
        # Guarantees zero repeated images within the same source pool.
        # =========================================================================
        reserved = self._reserve_safe_candidate(
            anime=target_name,
            character=character,
            selected_franchises=selected_franchises,
            excluded_franchises=excluded_franchises,
            excluded_characters=excluded_characters,
            token=token,
            ratio=ratio,
            target_level=3,
            recent_franchises=recent_franchises,
            apply_personalization=apply_personalization,
            min_quality=min_quality,
            media_type=media_type
        )
        if not reserved:
            # Fall back to any unviewed curated artwork
            reserved = self._reserve_safe_candidate(
                anime="all",
                token=token,
                ratio=ratio,
                target_level=3,
                recent_franchises=recent_franchises,
                apply_personalization=apply_personalization,
                media_type=media_type
            )

        if reserved:
            self.active_level = 3
            reserved["active_level"] = 3
            reserved["source"] = "Curated Offline"
            reserved["offline"] = not self.is_online
            return reserved

        # =========================================================================
        # PROCEDURAL OFFLINE ARTWORK SAFETY FALLBACK
        # Safety invariant: if no verified safe image is available across layers,
        # return statically verified offline SVG artwork rather than unverified content.
        # =========================================================================
        curated_dir = self.db.db_path.parent / "curated_wallpapers"
        if curated_dir.is_dir():
            import random
            if media_type == "gif":
                gif_files = sorted(curated_dir.glob("*.gif"))
                if gif_files:
                    pick_gif = random.choice(gif_files)
                    companion_json = pick_gif.with_suffix(".json")
                    c_meta = {}
                    if companion_json.is_file():
                        try:
                            with open(companion_json, "r", encoding="utf-8") as jf:
                                c_meta = json.load(jf)
                        except Exception:
                            pass
                    return {
                        "id": pick_gif.stem,
                        "url": f"/api/image/{pick_gif.stem}",
                        "resolution": c_meta.get("resolution", "1920x1080"),
                        "aspect_ratio": c_meta.get("aspect_ratio", "16:9"),
                        "is_dual_span": False,
                        "anime": c_meta.get("anime", "Curated Animated Anime"),
                        "character": c_meta.get("character"),
                        "source": "Curated Offline",
                        "offline": True,
                        "active_level": 3,
                        "safety_rating": "SAFE",
                        "safety_reason": "procedural_fallback_gif",
                        "fallback_procedural": True,
                        "is_animated": True,
                        "media_type": "gif"
                    }

            svg_files = sorted(curated_dir.glob("*.svg"))
            if svg_files:
                import random
                # If dual-screen ratio requested, prioritize 32:9 panoramic curated artworks
                if ratio in ("dual", "32:9", "32x9", "dual_screen"):
                    dual_svgs = [f for f in svg_files if "dual" in f.name.lower()]
                    if dual_svgs:
                        svg_files = dual_svgs

                pick_svg = random.choice(svg_files)
                companion_json = pick_svg.with_suffix(".json")
                c_meta = {}
                if companion_json.is_file():
                    try:
                        with open(companion_json, "r", encoding="utf-8") as jf:
                            c_meta = json.load(jf)
                    except Exception:
                        pass
                is_dual_curated = ("dual" in pick_svg.stem or c_meta.get("is_dual_span", False))
                return {
                    "id": pick_svg.stem,
                    "url": f"/api/image/{pick_svg.stem}",
                    "resolution": c_meta.get("resolution", "3840x1080" if is_dual_curated else "3840x2160"),
                    "aspect_ratio": c_meta.get("aspect_ratio", "32:9" if is_dual_curated else "16:9"),
                    "is_dual_span": is_dual_curated,
                    "anime": c_meta.get("anime", "Curated Offline Anime"),
                    "character": c_meta.get("character"),
                    "source": "Curated Offline",
                    "offline": True,
                    "active_level": 3,
                    "safety_rating": "SAFE",
                    "safety_reason": "procedural_fallback",
                    "fallback_procedural": True
                }

        # =========================================================================
        # EXHAUSTION STATE: All layers exhausted or empty
        # Handled gracefully without blanking the screen or repeating images.
        # =========================================================================
        stats = self.db.get_stats()
        label = target_name
        if character:
            label = f"{target_name} ({character})"
        return {
            "exhausted": True,
            "offline": not self.is_online,
            "active_level": 3 if not self.is_online else 1,
            "anime": label,
            "message": f"All available wallpapers for '{label}' have been displayed across all fallback layers.",
            "displayed_count": stats.get("displayed_count", 0),
            "cached_count": stats.get("cached_count", 0),
            "curated_count": stats.get("curated_count", 0),
            "favorites_count": stats.get("favorites_count", 0)
        }

    def confirm_displayed(self, wallpaper_id: str, token: str) -> bool:
        """Confirms a wallpaper was successfully rendered in the browser."""
        success = self.db.confirm_displayed(wallpaper_id=wallpaper_id, token=token)
        if success and getattr(self, "autosaver", None):
            try:
                wp = self.db.get_wallpaper_by_id(wallpaper_id)
                if wp:
                    self.autosaver.save_wallpaper_async(wp)
            except Exception as e:
                logger.warning(f"Auto-save trigger failed for {wallpaper_id}: {e}")
        return success

    def report_failed(self, wallpaper_id: str, token: str, reason: str = "") -> bool:
        """Handles browser image load error."""
        return self.db.mark_display_failed(wallpaper_id=wallpaper_id, token=token, error_reason=reason)

    def get_stats(self) -> Dict[str, Any]:
        stats = self.db.get_stats()
        stats["online"] = self.is_online
        stats["active_level"] = self.active_level
        stats["worker_state"] = self.worker_state
        stats["consecutive_network_failures"] = self.consecutive_network_failures
        stats["backoff_remaining"] = round(max(0.0, self.network_backoff_until - time.time()), 2)
        stats["registered_franchises_count"] = len(FRANCHISE_REGISTRY)
        stats["cache"] = self.cache_manager.get_cache_stats()
        return stats

    def reset_history(self) -> bool:
        """Explicit user-requested history reset."""
        with self.lock:
            self.page_tracker.clear()
            self.exhausted_keys.clear()
            return self.db.reset_history()
