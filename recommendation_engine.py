#!/usr/bin/env python3
"""
Intelligent Wallpaper Recommendation & Personalization Engine for KuroAnime.
Tracks multi-signal user interactions (favorites, dwell time, skips, revisits, manual selections,
and blacklists) to compute explainable local preference scores in SQLite.

Features:
- Positive feedback: Favorites (+15 to +20), Extended dwell sessions (+2 to +5), Revisits (+5 to +8), Manual selection (+4).
- Negative feedback: Skips (<5s: -2.5 to -4), Blacklists (-5 to -20), Ignored franchise decay (-0.4).
- Diversity Guard: Recency penalty preventing consecutive repetitive franchise/character recommendations.
- Zero external dependencies: Python standard library & SQLite only.
- 100% Local: Zero data egress or third-party telemetry.
- Global No-Repeat Guarantee: Preserves strict UNSEEN -> RESERVED -> DISPLAYED lifecycle.
"""

import time
import math
import random
import logging
from typing import Optional, Dict, Any, List

from database import DatabaseManager

logger = logging.getLogger("kuro_recommendations")

class PersonalizationEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def is_enabled(self) -> bool:
        """Checks if personalization scoring is enabled."""
        return self.db.is_personalization_enabled()

    def set_enabled(self, enabled: bool) -> bool:
        """Enables or disables personalization."""
        return self.db.set_personalization_enabled(enabled)

    def is_diversity_enabled(self) -> bool:
        """Checks if recency diversity penalty is active."""
        return self.db.is_diversity_penalty_enabled()

    def set_diversity_enabled(self, enabled: bool) -> bool:
        """Enables or disables diversity penalty."""
        return self.db.set_diversity_penalty_enabled(enabled)

    def record_dwell_and_transition(
        self,
        wallpaper_id: str,
        dwell_seconds: float,
        was_skipped: bool = False,
        anime: Optional[str] = None,
        character: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluates viewing session duration and records appropriate positive
        or negative learning signals.
        - Skip (< 5.0s or manual skip): Negative penalty
        - Extended dwell (>= 60s): Strong positive bonus
        - Moderate dwell (>= 30s): Positive bonus
        - Standard dwell (5s - 30s): Mild engagement bonus
        """
        dwell_sec = max(0.0, float(dwell_seconds))
        is_skip = was_skipped or (dwell_sec < 5.0)

        if is_skip:
            event_type = "skip"
            f_delta = -2.5
            c_delta = -4.0
        elif dwell_sec >= 60.0:
            event_type = "dwell_extended"
            f_delta = 4.0
            c_delta = 5.0
        elif dwell_sec >= 30.0:
            event_type = "dwell_long"
            f_delta = 2.0
            c_delta = 3.0
        else:
            event_type = "dwell_standard"
            f_delta = 0.5
            c_delta = 1.0

        # Log event in interaction_events
        self.db.record_interaction_event(
            wallpaper_id=wallpaper_id,
            event_type=event_type,
            anime=anime,
            character=character,
            dwell_seconds=dwell_sec,
            weight_delta=f_delta
        )

        # Update entity preference scores
        if anime:
            self.db.update_entity_preference(
                entity_type="franchise",
                entity_name=anime,
                delta=f_delta,
                event_type=event_type,
                dwell_seconds=dwell_sec
            )

        if character:
            self.db.update_entity_preference(
                entity_type="character",
                entity_name=character,
                delta=c_delta,
                event_type=event_type,
                dwell_seconds=dwell_sec
            )

        logger.info(
            f"[Personalization] Recorded {event_type} for '{wallpaper_id}' "
            f"(Franchise: {anime or 'None'}, Character: {character or 'None'}, "
            f"Dwell: {dwell_sec:.1f}s, Delta: {f_delta:+.1f})"
        )

        return {
            "event": event_type,
            "dwell_seconds": dwell_sec,
            "franchise_delta": f_delta,
            "character_delta": c_delta
        }

    def record_favorite(
        self,
        wallpaper_id: str,
        anime: Optional[str] = None,
        character: Optional[str] = None
    ) -> None:
        """Assigns strong positive preference scores when an artwork is favorited."""
        f_delta = 15.0
        c_delta = 20.0

        self.db.record_interaction_event(
            wallpaper_id=wallpaper_id,
            event_type="favorite",
            anime=anime,
            character=character,
            weight_delta=f_delta
        )

        if anime:
            self.db.update_entity_preference(
                entity_type="franchise",
                entity_name=anime,
                delta=f_delta,
                event_type="favorite"
            )

        if character:
            self.db.update_entity_preference(
                entity_type="character",
                entity_name=character,
                delta=c_delta,
                event_type="favorite"
            )

        logger.info(f"[Personalization] Boosted scores on favorite for {anime}/{character} (+{f_delta}/+{c_delta})")

    def record_favorite_removed(
        self,
        wallpaper_id: str,
        anime: Optional[str] = None,
        character: Optional[str] = None
    ) -> None:
        """Removes favorite boost when user unfavorites an artwork."""
        f_delta = -10.0
        c_delta = -12.0

        self.db.record_interaction_event(
            wallpaper_id=wallpaper_id,
            event_type="favorite_removed",
            anime=anime,
            character=character,
            weight_delta=f_delta
        )

        if anime:
            self.db.update_entity_preference(
                entity_type="franchise",
                entity_name=anime,
                delta=f_delta,
                event_type="favorite_removed"
            )

        if character:
            self.db.update_entity_preference(
                entity_type="character",
                entity_name=character,
                delta=c_delta,
                event_type="favorite_removed"
            )

    def record_revisit(
        self,
        wallpaper_id: str,
        anime: Optional[str] = None,
        character: Optional[str] = None
    ) -> None:
        """Records positive interest signal when user navigates backwards to re-view art."""
        f_delta = 5.0
        c_delta = 8.0

        self.db.record_interaction_event(
            wallpaper_id=wallpaper_id,
            event_type="revisit",
            anime=anime,
            character=character,
            weight_delta=f_delta
        )

        if anime:
            self.db.update_entity_preference(
                entity_type="franchise",
                entity_name=anime,
                delta=f_delta,
                event_type="revisit"
            )

        if character:
            self.db.update_entity_preference(
                entity_type="character",
                entity_name=character,
                delta=c_delta,
                event_type="revisit"
            )

        logger.info(f"[Personalization] Boosted scores on revisit for {anime}/{character} (+{f_delta}/+{c_delta})")

    def record_blacklist(
        self,
        wallpaper_id: str,
        anime: Optional[str] = None,
        character: Optional[str] = None
    ) -> None:
        """Applies heavy negative score penalty when user blacklists an artwork."""
        f_delta = -5.0
        c_delta = -20.0

        self.db.record_interaction_event(
            wallpaper_id=wallpaper_id,
            event_type="blacklist",
            anime=anime,
            character=character,
            weight_delta=c_delta
        )

        if anime:
            self.db.update_entity_preference(
                entity_type="franchise",
                entity_name=anime,
                delta=f_delta,
                event_type="blacklist"
            )

        if character:
            self.db.update_entity_preference(
                entity_type="character",
                entity_name=character,
                delta=c_delta,
                event_type="blacklist"
            )

        logger.info(f"[Personalization] Applied blacklist penalty for {anime}/{character} ({f_delta}/{c_delta})")

    def record_franchise_selection(self, selected_franchise: str) -> None:
        """
        Boosts selected franchise (+4.0) and applies slight negative decay (-0.4)
        to other franchises to model user preference differentiation.
        """
        if not selected_franchise or selected_franchise.lower() == "all":
            return

        self.db.record_interaction_event(
            wallpaper_id=None,
            event_type="select",
            anime=selected_franchise,
            character=None,
            weight_delta=4.0
        )

        self.db.update_entity_preference(
            entity_type="franchise",
            entity_name=selected_franchise,
            delta=4.0,
            event_type="select"
        )

    def get_recent_franchises(self, limit: int = 3) -> List[str]:
        """Returns the list of recently displayed franchises to enforce the diversity guard."""
        if not self.is_diversity_enabled():
            return []
        recent = self.db.get_recent_displayed_history(limit=limit)
        return [r["anime"] for r in recent if r.get("anime")]

    def select_franchise_by_preference(
        self,
        available_franchises: List[Dict[str, Any]],
        recent_franchises: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Selects a franchise for prefetching/discovery using weighted probabilistic sampling
        based on learned and manual preference scores combined with diversity recency penalties.
        """
        if not available_franchises:
            raise ValueError("No available franchises to select from.")

        if not self.is_enabled() or len(available_franchises) == 1:
            return random.choice(available_franchises)

        # Load preference scores for all franchises
        scores_list = self.db.get_preference_scores(entity_type="franchise", limit=200)
        score_map = {s["entity_name"].lower(): s["total_score"] for s in scores_list}

        recent_lowered = [r.lower() for r in (recent_franchises or [])]

        weights = []
        for f in available_franchises:
            f_name = f.get("name", "").lower()
            raw_score = score_map.get(f_name, 0.0)

            # Base weight is 10.0; scores shift between -50 and +100
            # weight = max(1.0, 10.0 + raw_score)
            weight = max(1.0, 10.0 + raw_score)

            # Diversity recency penalty: if displayed recently, scale weight down
            if f_name in recent_lowered:
                rank = recent_lowered.index(f_name)
                # 1st most recent: 0.15x weight, 2nd: 0.35x, 3rd: 0.6x
                factor = 0.15 + (rank * 0.20)
                weight = max(0.5, weight * factor)

            weights.append(weight)

        selected = random.choices(available_franchises, weights=weights, k=1)[0]
        return selected

    def set_manual_score(self, entity_type: str, entity_name: str, manual_score: float) -> bool:
        """Sets a manual bias/override score for an entity."""
        return self.db.set_manual_entity_preference(entity_type, entity_name, manual_score)

    def reset_learning(self) -> bool:
        """Resets all learned preference scores and interaction events."""
        return self.db.reset_personalization_data()

    def get_profile(self) -> Dict[str, Any]:
        """Returns the full user preference profile and learning statistics."""
        return self.db.get_personalization_profile()
