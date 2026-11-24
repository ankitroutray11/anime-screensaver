"""
Slideshow Scheduling Engine for Anime Ambient Screensaver.
Supports multiple scheduling strategies:
- Fixed interval
- Random interval within a configured range
- Quality / Rating weighted duration
- Time-based scheduling (Daytime / Evening / Night)
- Franchise rotation tracking
- Manual-only mode
- Mode-specific intervals for Cinematic and Dashboard display modes
"""
from datetime import datetime
import random
from typing import Dict, Any, Optional, List

VALID_STRATEGIES = {
    "fixed",
    "random",
    "quality_weighted",
    "time_of_day",
    "franchise_rotation",
    "manual"
}

DEFAULT_SCHEDULER_SETTINGS: Dict[str, Any] = {
    "strategy": "fixed",
    "fixed_seconds": 30,
    "random_min": 15,
    "random_max": 60,
    "day_seconds": 25,
    "evening_seconds": 35,
    "night_seconds": 60,
    "cinematic_seconds": 45,
    "dashboard_seconds": 20,
    "quality_bonus_enabled": True,
    "pause_on_hidden": True,
    "franchise_rotation_interval": 5,
}

class SlideshowScheduler:
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = dict(DEFAULT_SCHEDULER_SETTINGS)
        if settings:
            self.settings.update(settings)
        self.franchise_counter = 0
        self.current_franchise_index = 0

    def update_settings(self, new_settings: Dict[str, Any]):
        for k, v in new_settings.items():
            if k in self.settings:
                self.settings[k] = v

    def get_time_period(self, hour: Optional[int] = None) -> str:
        """Determines daytime (08-17), evening (17-22), or night (22-08)."""
        if hour is None:
            hour = datetime.now().hour
        if 8 <= hour < 17:
            return "day"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"

    def calculate_slide_duration(
        self,
        wallpaper: Optional[Dict[str, Any]] = None,
        display_mode: str = "ambient",
        current_hour: Optional[int] = None,
        force_random_val: Optional[int] = None
    ) -> float:
        """
        Calculates slide duration in seconds based on active strategy,
        wallpaper quality/rating, display mode overrides, and time-of-day.
        """
        strategy = self.settings.get("strategy", "fixed")
        if strategy not in VALID_STRATEGIES:
            strategy = "fixed"

        # Manual mode has effectively infinite duration (auto-timer disabled)
        if strategy == "manual":
            return float("inf")

        # 1. Base duration calculation
        base_duration = float(self.settings.get("fixed_seconds", 30))

        if strategy == "random":
            r_min = max(5, int(self.settings.get("random_min", 15)))
            r_max = max(r_min, int(self.settings.get("random_max", 60)))
            if force_random_val is not None:
                base_duration = float(max(r_min, min(r_max, force_random_val)))
            else:
                base_duration = float(random.randint(r_min, r_max))

        elif strategy == "time_of_day":
            period = self.get_time_period(current_hour)
            if period == "day":
                base_duration = float(self.settings.get("day_seconds", 25))
            elif period == "evening":
                base_duration = float(self.settings.get("evening_seconds", 35))
            else:  # night
                base_duration = float(self.settings.get("night_seconds", 60))

        # 2. Display mode override
        # Cinematic mode: longer contemplative interval
        # Dashboard mode: faster stats overview
        if display_mode == "cinematic":
            cinematic_sec = float(self.settings.get("cinematic_seconds", 45))
            base_duration = max(base_duration, cinematic_sec)
        elif display_mode == "dashboard":
            dashboard_sec = float(self.settings.get("dashboard_seconds", 20))
            base_duration = min(base_duration, dashboard_sec)

        # 3. Quality / Rating weighting (applied if strategy == 'quality_weighted' OR if quality_bonus_enabled)
        quality_enabled = (strategy == "quality_weighted") or bool(self.settings.get("quality_bonus_enabled", True))
        if quality_enabled and wallpaper:
            multiplier = 1.0
            quality_score = wallpaper.get("quality_score")
            is_favorite = wallpaper.get("is_favorite") or wallpaper.get("favorite")

            if quality_score is not None:
                try:
                    q = float(quality_score)
                    # Quality score ranges 0..100; scores >= 70 get scaled bonus up to +40%
                    if q >= 70:
                        multiplier += ((q - 70.0) / 30.0) * 0.40
                    elif q < 40:
                        multiplier -= ((40.0 - q) / 40.0) * 0.20
                except (ValueError, TypeError):
                    pass

            base_duration = base_duration * multiplier

            # Favorites get a static bonus of 10s
            if is_favorite:
                base_duration += 10.0

        # Enforce bounds: min 5 seconds, max 600 seconds
        return round(max(5.0, min(600.0, base_duration)), 1)

    def advance_franchise_slide(self, franchise_list: List[str]) -> Optional[str]:
        """
        In franchise rotation mode, tracks number of slides displayed.
        Returns the new franchise slug when rotating, or None if still in current interval.
        """
        if not franchise_list:
            return None
        self.franchise_counter += 1
        threshold = max(1, int(self.settings.get("franchise_rotation_interval", 5)))
        if self.franchise_counter >= threshold:
            self.franchise_counter = 0
            self.current_franchise_index = (self.current_franchise_index + 1) % len(franchise_list)
            return franchise_list[self.current_franchise_index]
        return None
