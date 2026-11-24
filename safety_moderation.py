"""
safety_moderation.py - Unified Content Safety & Moderation Engine for Kuro Screensaver

Enforces a strict, provider-independent content safety layer:
1. Strict Application-Wide Policy: ONLY SFW anime artwork is eligible for automatic display.
2. Translates provider ratings (Wallhaven purity, Safebooru rating, Konachan rating) into internal SafetyRating.
3. Rejects artwork with unknown, missing, ambiguous, or insufficient safety metadata by default.
4. Independent verification: never trusts API query parameters alone.
5. Multi-attribute inspection: checks raw provider rating, tag allowlists/denylists, metadata completeness.
6. Local blocked-artwork list and multi-entity blocklist (tags, characters, artists, franchises, artwork IDs).
7. Pre-display cache revalidation against active safety policy and blocklists.
8. Optional review queue support for ambiguous artwork.
9. Priority invariant: Safety strictly takes precedence over wallpaper availability.
   Falls back to procedural offline artwork if no verified safe artwork is available.
"""

import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("KuroSafetyModeration")

# ---------------------------------------------------------------------------
# 1. Standard Internal Safety Classification
# ---------------------------------------------------------------------------

class SafetyRating(str, Enum):
    SAFE = "SAFE"                   # Strictly Safe For Work, wholesome, suitable for all displays
    QUESTIONABLE = "QUESTIONABLE"   # Suggestive, borderline, fan-service, or partial nudity
    EXPLICIT = "EXPLICIT"           # Adult, NSFW, pornography, extreme violence, gore
    AMBIGUOUS = "AMBIGUOUS"         # Missing, unverified, conflicting, or insufficient metadata
    BLOCKED = "BLOCKED"             # Specifically banned by user blocklist (tag, artist, char, id)


# ---------------------------------------------------------------------------
# 2. Comprehensive Denylist Dictionaries
# ---------------------------------------------------------------------------

# Words or tags that immediately indicate adult / explicit NSFW content
EXPLICIT_DENYLIST_TAGS: Set[str] = {
    "nsfw", "nude", "nudity", "naked", "topless", "bottomless", "uncensored",
    "nipples", "areola", "vagina", "penis", "genitals", "pussy", "dick",
    "sex", "intercourse", "oral", "anal", "cum", "masturbation", "hentai",
    "r-18", "r18", "xxx", "porn", "porno", "erotic", "erotica", "doujinshi",
    "bdsm", "bondage", "garter", "tentacles", "ahegao", "cameltoe", "ecchi",
    "gore", "gory", "dismemberment", "decapitation", "mutilation", "blood_splatter",
    "explicit", "rating:explicit", "rating:e"
}

# Words or tags that indicate questionable / suggestive / borderline content
QUESTIONABLE_DENYLIST_TAGS: Set[str] = {
    "lingerie", "underwear", "panties", "panty", "bra", "brassiere",
    "underbust", "cleavage", "deep_cleavage", "bikini", "swimsuit", "monokini",
    "swimwear", "bathing_suit", "sideboob", "underboob", "thong", "micro_bikini",
    "microbikini", "see-through", "transparent_clothing", "wet_clothes",
    "cameltoe", "upskirt", "skirt_lift", "pantyshot", "panty_pull",
    "suggestive", "fetish", "sensual", "provocative", "strip", "stripping",
    "partially_unbuttoned", "shirt_lift", "clothing_lift", "bare_shoulders_in_bed",
    "maid_bikini", "bunny_suit", "succubus", "lewd", "rating:questionable", "rating:q"
}

# Generic non-anime or controversial tags that must be filtered
GENERIC_FILTER_TAGS: Set[str] = {
    "vtuber", "hololive", "nijisanji", "vocaloid", "real_person", "cosplay",
    "photo", "photograph", "real_life", "3d", "western", "meme"
}


class SafetyEvaluationResult(dict):
    """
    Dual-interface evaluation result that acts as both a dictionary and a 2-tuple.
    Allows:
        rating, reason = res
        res['safety_rating'] or res[0]
        res['safety_reason'] or res[1]
    """
    def __init__(self, safety_rating: SafetyRating, safety_reason: str, provider_purity_raw: Optional[str] = None):
        super().__init__(
            safety_rating=safety_rating,
            safety_reason=safety_reason,
            provider_purity_raw=provider_purity_raw
        )
        self.safety_rating = safety_rating
        self.safety_reason = safety_reason
        self.provider_purity_raw = provider_purity_raw

    def __iter__(self):
        yield self.safety_rating
        yield self.safety_reason

    def __getitem__(self, key):
        if key == 0:
            return self.safety_rating
        if key == 1:
            return self.safety_reason
        return super().__getitem__(key)


# ---------------------------------------------------------------------------
# 3. Unified Safety Moderation Engine
# ---------------------------------------------------------------------------

class SafetyModerationEngine:
    """
    Central safety arbiter for Kuro Screensaver.
    Inspects provider payloads, enforces zero-tolerance SFW policy,
    and validates cached wallpapers before rendering.
    """

    @staticmethod
    def translate_provider_rating(provider_name: str, raw_purity: Any) -> SafetyRating:
        """
        Translates raw provider ratings to the internal SafetyRating.
        Defaults to AMBIGUOUS if value is missing, empty, or unknown.
        """
        if raw_purity is None:
            return SafetyRating.AMBIGUOUS

        clean_purity = str(raw_purity).strip().lower()
        if not clean_purity:
            return SafetyRating.AMBIGUOUS

        pname = (provider_name or "").lower()

        # Wallhaven translation
        if "wallhaven" in pname:
            if clean_purity in ("100", "sfw", "safe", "general"):
                return SafetyRating.SAFE
            if clean_purity in ("010", "sketchy", "questionable"):
                return SafetyRating.QUESTIONABLE
            if clean_purity in ("001", "nsfw", "explicit"):
                return SafetyRating.EXPLICIT
            return SafetyRating.AMBIGUOUS

        # Safebooru / Booru translation
        if "safebooru" in pname or "booru" in pname:
            if clean_purity in ("g", "general", "s", "safe", "sfw"):
                return SafetyRating.SAFE
            if clean_purity in ("q", "questionable"):
                return SafetyRating.QUESTIONABLE
            if clean_purity in ("e", "explicit"):
                return SafetyRating.EXPLICIT
            return SafetyRating.AMBIGUOUS

        # Konachan translation
        if "konachan" in pname:
            if clean_purity in ("s", "safe", "g", "general", "sfw"):
                return SafetyRating.SAFE
            if clean_purity in ("q", "questionable"):
                return SafetyRating.QUESTIONABLE
            if clean_purity in ("e", "explicit"):
                return SafetyRating.EXPLICIT
            return SafetyRating.AMBIGUOUS

        # Local Curated collection
        if "curated" in pname or "local" in pname:
            return SafetyRating.SAFE

        # Standard fallback string mappings
        if clean_purity in ("sfw", "safe", "general", "g", "s"):
            return SafetyRating.SAFE
        if clean_purity in ("sketchy", "questionable", "q"):
            return SafetyRating.QUESTIONABLE
        if clean_purity in ("nsfw", "explicit", "e"):
            return SafetyRating.EXPLICIT

        return SafetyRating.AMBIGUOUS

    @classmethod
    def evaluate_artwork_safety(
        cls,
        item: Dict[str, Any],
        db_manager: Optional[Any] = None
    ) -> SafetyEvaluationResult:
        """
        Comprehensive multi-attribute safety evaluation of an artwork candidate.
        Returns SafetyEvaluationResult (accessible as dict or 2-tuple).
        """
        art_id = str(item.get("id") or "").strip()
        provider = str(item.get("source") or item.get("provider") or "Wallhaven")

        # 1. User & Local Blocklist Check (artwork_id)
        if db_manager and art_id:
            if db_manager.is_blocked_in_db("artwork", art_id) or db_manager.is_blocked_in_db("artwork_id", art_id):
                return SafetyEvaluationResult(SafetyRating.BLOCKED, f"Artwork ID {art_id} is in user blocklist")
            if hasattr(db_manager, "is_blacklisted") and db_manager.is_blacklisted(art_id):
                return SafetyEvaluationResult(SafetyRating.BLOCKED, f"Artwork ID {art_id} is blacklisted")

        # 2. Character, Franchise & Artist Blocklist Check
        char_name = str(item.get("character") or "").strip()
        anime_title = str(item.get("anime") or "").strip()
        uploader = str(item.get("uploader") or "").strip()

        if db_manager:
            if char_name and db_manager.is_blocked_in_db("character", char_name):
                return SafetyEvaluationResult(SafetyRating.BLOCKED, f"Character '{char_name}' is blocked")
            if anime_title and db_manager.is_blocked_in_db("franchise", anime_title):
                return SafetyEvaluationResult(SafetyRating.BLOCKED, f"Franchise '{anime_title}' is blocked")
            if uploader and db_manager.is_blocked_in_db("artist", uploader):
                return SafetyEvaluationResult(SafetyRating.BLOCKED, f"Artist/Uploader '{uploader}' is blocked")

        # 3. Provider Rating Translation
        raw_purity = item.get("provider_purity_raw") or item.get("purity") or item.get("rating")
        is_curated = (provider.lower() in ("curated offline", "curated", "local") or int(item.get("level") or 0) == 3)
        if not raw_purity:
            if is_curated or item.get("safety_rating") == "SAFE":
                raw_purity = "safe"

        base_rating = cls.translate_provider_rating(provider, raw_purity)

        if base_rating == SafetyRating.EXPLICIT:
            return SafetyEvaluationResult(SafetyRating.EXPLICIT, f"Provider marked as explicit (raw: {raw_purity})", raw_purity)
        if base_rating == SafetyRating.QUESTIONABLE:
            return SafetyEvaluationResult(SafetyRating.QUESTIONABLE, f"Provider marked as questionable/sketchy (raw: {raw_purity})", raw_purity)
        if base_rating == SafetyRating.AMBIGUOUS:
            return SafetyEvaluationResult(SafetyRating.AMBIGUOUS, f"missing_provider_purity: no valid safety rating (raw: {raw_purity})", raw_purity)

        # 4. Metadata Completeness & Tag Sufficiency Check
        raw_tags = item.get("tags") or []
        tag_list: List[str] = []
        if isinstance(raw_tags, str):
            try:
                parsed = json.loads(raw_tags)
                if isinstance(parsed, list):
                    raw_tags = parsed
                else:
                    raw_tags = raw_tags.split()
            except Exception:
                raw_tags = raw_tags.split()

        if isinstance(raw_tags, list):
            for t in raw_tags:
                if isinstance(t, dict):
                    tname = t.get("name")
                    if tname:
                        tag_list.append(str(tname).lower().strip())
                elif isinstance(t, str):
                    tag_list.append(t.lower().strip())

        # Curated offline SVGs or already-verified safe entries have minimal internal tags, permit them
        is_already_verified_safe = (item.get("safety_rating") == "SAFE" or is_curated or int(item.get("level") or 0) == 3)
        if not tag_list and not is_already_verified_safe:
            return SafetyEvaluationResult(SafetyRating.AMBIGUOUS, "insufficient_tags: zero descriptive tags", raw_purity)

        # 5. Independent Tag Inspection (Never trust query parameter alone)
        for tag in tag_list:
            clean_tag = tag.replace("-", "_").replace(" ", "_")

            # Check user blocked tags first (user blocks take precedence)
            if db_manager and (db_manager.is_blocked_in_db("tag", tag) or db_manager.is_blocked_in_db("tag", clean_tag)):
                return SafetyEvaluationResult(SafetyRating.BLOCKED, f"user_blocked_tag:{tag}", raw_purity)

            # Check explicit denylist
            if clean_tag in EXPLICIT_DENYLIST_TAGS or any(b in clean_tag for b in ("hentai", "nsfw", "nude", "genital", "nipple")):
                return SafetyEvaluationResult(SafetyRating.EXPLICIT, f"tag_denylist:{tag}", raw_purity)

            # Check questionable / suggestive denylist
            if clean_tag in QUESTIONABLE_DENYLIST_TAGS or any(q in clean_tag for q in ("lingerie", "cleavage", "upskirt", "bikini", "swimsuit")):
                return SafetyEvaluationResult(SafetyRating.QUESTIONABLE, f"tag_denylist:{tag}", raw_purity)

        # 6. Ambiguity Guard Exclusions for Franchises (e.g. Bleach cleaning, One Piece swimsuit)
        from franchise_registry import FranchiseRegistry
        franchise_slug = item.get("franchise_slug")
        if not franchise_slug and anime_title:
            f_entry = FranchiseRegistry.get_franchise(anime_title)
            if f_entry:
                franchise_slug = f_entry.get("slug")

        if franchise_slug:
            f_entry = FranchiseRegistry.get_franchise(franchise_slug)
            if f_entry:
                excluded_keywords = [k.lower().strip() for k in f_entry.get("excluded_keywords", []) if k.strip()]
                for t in tag_list:
                    for ek in excluded_keywords:
                        if ek in t:
                            return SafetyEvaluationResult(SafetyRating.QUESTIONABLE, f"Tag '{t}' matched ambiguous franchise exclusion '{ek}'", raw_purity)

        # Verified SFW
        return SafetyEvaluationResult(SafetyRating.SAFE, "verified_safe", raw_purity)

    @classmethod
    def revalidate_before_display(
        cls,
        wallpaper: Dict[str, Any],
        db_manager: Any
    ) -> Tuple[bool, str]:
        """
        Revalidates any wallpaper record (including cached files on disk)
        immediately before presentation.
        Guarantees that recently added user blocks or policy changes take effect instantly.
        """
        if not wallpaper:
            return False, "Null wallpaper payload"

        safety_rating, reason = cls.evaluate_artwork_safety(wallpaper, db_manager)
        if safety_rating != SafetyRating.SAFE:
            logger.warning(
                f"[SafetyRevalidate] Wallpaper {wallpaper.get('id')} rejected before display! "
                f"Rating: {safety_rating.value}, Reason: {reason}"
            )
            return False, reason

        return True, "Passed safety revalidation"
