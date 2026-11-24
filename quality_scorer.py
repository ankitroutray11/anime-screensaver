"""
KURO // ANIME — Intelligent Artwork Quality Scoring Engine
Evaluates technical image quality and community popularity before discovered
wallpapers enter the display queue.

Guiding Principles:
1. Technical Image Quality: Evaluates objective rendering criteria (resolution,
   pixel scale factor, aspect ratio fit, sharpness / detail density, and luminance balance).
2. Community Popularity: Evaluates public community acclaim (favorites, views, and engagement ratio).
3. Clear Distinction: Technical image quality is separated from community popularity.
   Subjective artistic quality is intentionally not claimed to be evaluated by algorithms.
4. Lightweight: Pure Python standard library with sub-millisecond execution and SQLite caching.
"""

import math
import re
from typing import Dict, Any, List, Optional, Tuple


class QualityScorer:
    """
    Lightweight, configurable quality scoring engine for anime wallpapers.
    Computes technical quality, community popularity, and composite scores on a 0-100 scale.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.min_quality_score: float = float(cfg.get("min_quality_score", 50.0))
        self.prefer_native_res: bool = bool(cfg.get("prefer_native_res", True))
        self.prefer_aspect_ratio: bool = bool(cfg.get("prefer_aspect_ratio", True))
        self.avoid_too_dark: bool = bool(cfg.get("avoid_too_dark", False))
        self.avoid_too_bright: bool = bool(cfg.get("avoid_too_bright", True))
        self.technical_weight: float = float(cfg.get("technical_weight", 0.65))
        self.popularity_weight: float = float(cfg.get("popularity_weight", 0.35))
        self.target_resolution: str = str(cfg.get("target_resolution", "1920x1080"))
        self.target_aspect_ratio: str = str(cfg.get("target_aspect_ratio", "landscape"))

    @staticmethod
    def parse_dimensions(res_str: Optional[str], dim_x: Optional[int] = None, dim_y: Optional[int] = None) -> Tuple[int, int]:
        """Extracts (width, height) integers from resolution string or explicit dimensions."""
        if dim_x and dim_y and dim_x > 0 and dim_y > 0:
            return int(dim_x), int(dim_y)
        if res_str:
            match = re.search(r"(\d+)\s*[xX×]\s*(\d+)", res_str)
            if match:
                return int(match.group(1)), int(match.group(2))
        return 1920, 1080

    @staticmethod
    def parse_target_resolution(target_str: str) -> Tuple[int, int]:
        """Resolves target resolution string to (width, height)."""
        target_map = {
            "1080p": (1920, 1080),
            "1440p": (2560, 1440),
            "4k": (3840, 2160),
            "uhd": (3840, 2160),
            "ultrawide": (3440, 1440),
            "portrait": (1080, 1920),
            "portrait_1440": (1440, 2560)
        }
        low = target_str.lower().strip()
        if low in target_map:
            return target_map[low]
        return QualityScorer.parse_dimensions(target_str)

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        """Converts '#RRGGBB' to (r, g, b)."""
        s = hex_str.strip().lstrip("#")
        if len(s) == 3:
            s = "".join([c * 2 for c in s])
        if len(s) == 6:
            try:
                return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            except ValueError:
                pass
        return 128, 128, 128

    @staticmethod
    def calculate_luminance(r: int, g: int, b: int) -> float:
        """Computes relative luminance Y via ITU-R BT.709 standard [0.0 - 255.0]."""
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @classmethod
    def analyze_palette(cls, colors: List[str]) -> Tuple[float, float, float, float]:
        """
        Analyzes color palette hex list to extract:
        (mean_luminance, min_luminance, max_luminance, std_dev_contrast).
        """
        if not colors:
            return 100.0, 50.0, 150.0, 30.0

        lum_list = []
        for c in colors:
            if isinstance(c, str) and c.startswith("#"):
                r, g, b = cls.hex_to_rgb(c)
                lum_list.append(cls.calculate_luminance(r, g, b))

        if not lum_list:
            return 100.0, 50.0, 150.0, 30.0

        mean_y = sum(lum_list) / len(lum_list)
        min_y = min(lum_list)
        max_y = max(lum_list)
        variance = sum((y - mean_y) ** 2 for y in lum_list) / len(lum_list)
        std_dev = math.sqrt(variance)

        return mean_y, min_y, max_y, std_dev

    @classmethod
    def color_distance(cls, c1_hex: str, c2_hex: str) -> float:
        """Normalized Euclidean distance in RGB color space [0.0 = identical, 1.0 = opposite]."""
        r1, g1, b1 = cls.hex_to_rgb(c1_hex)
        r2, g2, b2 = cls.hex_to_rgb(c2_hex)
        dist = math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
        return dist / (255.0 * math.sqrt(3.0))

    def score_resolution(self, width: int, height: int, target_w: int, target_h: int) -> Tuple[float, float, bool]:
        """
        Scores resolution out of 40.0 points.
        Prefers native-resolution artwork; penalizes low-resolution images requiring upscaling.
        Returns: (score, min_scale, is_native_or_higher)
        """
        scale_w = width / max(target_w, 1)
        scale_h = height / max(target_h, 1)
        min_scale = min(scale_w, scale_h)

        if min_scale >= 1.0:
            is_native = True
            # Native match (1.0 scale) gets 30 pts; higher resolution (supersampled 1440p/4K) scales up to 40 pts
            extra = min(1.0, min_scale - 1.0)
            score = 30.0 + (10.0 * extra)
        else:
            is_native = False
            # Upscaling deficit: 1080p on 4K is scale=0.5 -> deficit=0.5 -> penalty 35 * 0.5 = 17.5 pts
            deficit = 1.0 - min_scale
            penalty = 35.0 * deficit
            score = max(5.0, 30.0 - penalty)

        return round(score, 1), round(min_scale, 2), is_native

    def score_aspect_ratio(self, width: int, height: int, target_ratio_mode: str) -> Tuple[float, float]:
        """
        Scores aspect ratio compatibility out of 20.0 points.
        Returns: (score, relative_error)
        """
        img_ratio = width / max(height, 1)

        # Map target ratio mode to numeric ratio
        mode = target_ratio_mode.lower().strip()
        if mode in ("landscape", "16:9", "16/9"):
            target_r = 16.0 / 9.0  # 1.7778
        elif mode in ("ultrawide", "21:9", "21/9"):
            target_r = 3440.0 / 1440.0  # 2.3889
        elif mode in ("portrait", "9:16", "9/16"):
            target_r = 9.0 / 16.0  # 0.5625
        elif mode == "any":
            return 20.0, 0.0
        else:
            # Try parsing custom ratio like "16:10"
            m = re.match(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", mode)
            if m:
                target_r = float(m.group(1)) / max(float(m.group(2)), 0.01)
            else:
                target_r = 16.0 / 9.0

        rel_error = abs(img_ratio - target_r) / target_r

        if rel_error <= 0.02:
            score = 20.0
        elif rel_error <= 0.08:
            # Minor cropping (e.g. 1.78 vs 1.7778)
            score = 20.0 - (50.0 * (rel_error - 0.02))
        elif rel_error <= 0.20:
            # Moderate letterboxing / crop (e.g. 16:10)
            score = 17.0 - (40.0 * (rel_error - 0.08))
        else:
            # Severe orientation mismatch (e.g. portrait on landscape)
            score = max(0.0, 12.0 - (30.0 * (rel_error - 0.20)))

        return round(score, 1), round(rel_error, 3)

    def score_sharpness_and_detail(self, width: int, height: int, file_size: Optional[int]) -> float:
        """
        Scores image sharpness and detail density out of 10.0 points.
        Uses bits-per-pixel (BPP) when file size is present; estimates from megapixel count otherwise.
        """
        if file_size and file_size > 0:
            total_pixels = width * height
            if total_pixels > 0:
                bpp = (file_size * 8.0) / total_pixels
                if bpp >= 1.5:
                    return 10.0
                elif bpp >= 1.0:
                    return round(8.0 + (4.0 * (bpp - 1.0)), 1)
                elif bpp >= 0.5:
                    return round(5.0 + (6.0 * (bpp - 0.5)), 1)
                else:
                    return max(2.0, round(5.0 * (bpp / 0.5), 1))

        # Fallback estimation based on native pixel count
        pixels_mp = (width * height) / 1_000_000.0
        if pixels_mp >= 8.0:  # 4K UHD
            return 9.5
        elif pixels_mp >= 3.5:  # 1440p
            return 8.5
        elif pixels_mp >= 2.0:  # 1080p
            return 7.5
        else:
            return 5.0

    def score_tone_and_luminance(
        self,
        colors: List[str]
    ) -> Tuple[float, float, float, float, List[str]]:
        """
        Scores tone, contrast, and brightness out of 10.0 points.
        Checks for harsh blinding white backgrounds or pitch-dark unreadable artwork.
        Returns: (tone_score, mean_y, contrast_std_dev, filter_penalty, filter_flags)
        """
        mean_y, min_y, max_y, std_dev = self.analyze_palette(colors)
        dynamic_range = max_y - min_y

        # Dynamic range & contrast scoring (0 - 10 pts)
        if dynamic_range >= 80.0 and std_dev >= 25.0:
            tone_score = 10.0
        else:
            contrast_factor = min(1.0, std_dev / 25.0)
            range_factor = min(1.0, dynamic_range / 80.0)
            tone_score = max(3.0, round(10.0 * contrast_factor * range_factor, 1))

        filter_penalty = 0.0
        filter_flags = []

        if self.avoid_too_bright:
            if mean_y >= 210.0:
                filter_penalty += 20.0
                filter_flags.append("too_bright")
            elif mean_y >= 185.0:
                filter_penalty += 8.0

        if self.avoid_too_dark:
            if mean_y <= 18.0:
                filter_penalty += 20.0
                filter_flags.append("too_dark")
            elif mean_y <= 32.0:
                filter_penalty += 8.0

        return tone_score, round(mean_y, 1), round(std_dev, 1), filter_penalty, filter_flags

    def score_community_popularity(self, favorites: Optional[int], views: Optional[int]) -> float:
        """
        Scores community popularity out of 20.0 points.
        Uses logarithmic scaling on favorites and engagement ratio (fav / view).
        If favorites/views are missing (e.g. offline curated artwork), returns a neutral 12.0/20 (60%).
        """
        if favorites is None and views is None:
            return 12.0

        fav = max(0, favorites or 0)
        vw = max(0, views or 0)

        # Logarithmic favorites curve (0 to 15 pts)
        fav_score = min(15.0, math.log10(fav + 1) * 4.3)

        # Engagement ratio bonus (0 to 5 pts)
        er = fav / max(vw, 50)
        engagement_bonus = min(5.0, er * 50.0)

        return round(min(20.0, fav_score + engagement_bonus), 1)

    def calculate_perceptual_similarity_penalty(
        self,
        candidate_colors: List[str],
        recent_colors_list: Optional[List[List[str]]]
    ) -> float:
        """
        Calculates penalty (0 to 15 pts) if candidate's dominant color is overly similar
        to the dominant color of the most recently displayed 1-3 wallpapers.
        """
        if not candidate_colors or not recent_colors_list:
            return 0.0

        candidate_dom = candidate_colors[0]
        max_similarity = 0.0

        for prev_palette in recent_colors_list[:3]:
            if prev_palette:
                prev_dom = prev_palette[0]
                dist = self.color_distance(candidate_dom, prev_dom)
                sim = 1.0 - dist
                if sim > max_similarity:
                    max_similarity = sim

        # If similarity > 0.85 (nearly identical palette scheme), apply penalty
        if max_similarity >= 0.85:
            penalty = 15.0 * ((max_similarity - 0.85) / 0.15)
            return round(min(15.0, penalty), 1)

        return 0.0

    def score_wallpaper(
        self,
        wallpaper: Dict[str, Any],
        target_res: Optional[str] = None,
        target_ratio: Optional[str] = None,
        recent_colors_list: Optional[List[List[str]]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete quality scoring evaluation for a wallpaper candidate.
        Returns composite quality_score (0-100), technical_score (0-100),
        popularity_score (0-100), and detailed metrics breakdown.
        """
        res_str = wallpaper.get("resolution")
        dim_x = wallpaper.get("dimension_x")
        dim_y = wallpaper.get("dimension_y")
        width, height = self.parse_dimensions(res_str, dim_x, dim_y)

        # Parse target resolution & ratio
        t_res_str = target_res or self.target_resolution
        target_w, target_h = self.parse_target_resolution(t_res_str)
        t_ratio = target_ratio or self.target_aspect_ratio

        # 1. Technical components (sum max = 80.0)
        res_pts, min_scale, is_native = self.score_resolution(width, height, target_w, target_h)
        ratio_pts, aspect_err = self.score_aspect_ratio(width, height, t_ratio)
        sharp_pts = self.score_sharpness_and_detail(width, height, wallpaper.get("file_size"))

        # Palette colors
        raw_colors = wallpaper.get("colors")
        if isinstance(raw_colors, str):
            try:
                import json
                colors = json.loads(raw_colors)
            except Exception:
                colors = []
        elif isinstance(raw_colors, list):
            colors = raw_colors
        else:
            colors = []

        tone_pts, mean_y, contrast_sd, filter_penalty, filter_flags = self.score_tone_and_luminance(colors)

        # Technical Score (normalized to 0-100)
        tech_raw = res_pts + ratio_pts + sharp_pts + tone_pts  # Max: 40 + 20 + 10 + 10 = 80
        technical_score = round(min(100.0, (tech_raw / 80.0) * 100.0), 1)

        # 2. Community Popularity (raw max = 20.0, normalized to 0-100)
        pop_raw = self.score_community_popularity(wallpaper.get("favorites"), wallpaper.get("views"))
        popularity_score = round(min(100.0, (pop_raw / 20.0) * 100.0), 1)

        # 3. Perceptual Similarity Penalty
        sim_penalty = self.calculate_perceptual_similarity_penalty(colors, recent_colors_list)

        # 4. Composite Quality Score (0 - 100)
        composite = (technical_score * self.technical_weight) + (popularity_score * self.popularity_weight)
        composite -= (filter_penalty + sim_penalty)
        final_score = round(max(0.0, min(100.0, composite)), 1)

        passes_threshold = final_score >= self.min_quality_score
        if not passes_threshold:
            filter_flags.append("below_min_threshold")

        return {
            "quality_score": final_score,
            "technical_score": technical_score,
            "popularity_score": popularity_score,
            "passes_threshold": passes_threshold,
            "filter_flags": filter_flags,
            "breakdown": {
                "width": width,
                "height": height,
                "target_width": target_w,
                "target_height": target_h,
                "scale_factor": min_scale,
                "is_native_or_higher": is_native,
                "resolution_score": res_pts,
                "aspect_ratio_score": ratio_pts,
                "aspect_ratio_error": aspect_err,
                "sharpness_score": sharp_pts,
                "tone_score": tone_pts,
                "mean_luminance": mean_y,
                "contrast_std_dev": contrast_sd,
                "community_score": pop_raw,
                "filter_penalty": filter_penalty,
                "similarity_penalty": sim_penalty
            },
            "disclaimer": (
                "Technical Image Quality measures objective rendering fidelity (resolution, aspect ratio, "
                "detail density, luminance). Community Popularity reflects audience favorites and views. "
                "Subjective artistic quality is unmeasured."
            )
        }
