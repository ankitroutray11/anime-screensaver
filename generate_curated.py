#!/usr/bin/env python3
"""
Generates starter high-resolution vector artwork and metadata for the
Level 3 Curated Offline Anime Wallpaper Collection.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
curated_dir = BASE_DIR / "curated_wallpapers"
curated_dir.mkdir(exist_ok=True)

artworks = [
    {
        "id": "curated_01_jujutsu_kaisen_gojo",
        "file": "curated_01_jujutsu_kaisen_gojo.svg",
        "anime": "Jujutsu Kaisen",
        "character": "Satoru Gojo",
        "resolution": "3840x2160",
        "title": "Domain Expansion: Unlimited Void",
        "theme_color": "#00F0FF",
        "kanji": "領域展開・無量空処",
        "quote": "Throughout Heaven and Earth, I alone am the honored one.",
        "bg1": "#030712",
        "bg2": "#08182B",
        "accent": "#00F0FF",
        "accent2": "#3B82F6",
        "sub": "#93C5FD"
    },
    {
        "id": "curated_02_demon_slayer_tanjiro",
        "file": "curated_02_demon_slayer_tanjiro.svg",
        "anime": "Demon Slayer",
        "character": "Tanjiro Kamado",
        "resolution": "3840x2160",
        "title": "Hinokami Kagura: Sun Breathing",
        "theme_color": "#FF3B30",
        "kanji": "日の神神楽・碧羅の天",
        "quote": "No matter how many people you may lose, you have no choice but to go on living.",
        "bg1": "#0D0505",
        "bg2": "#240A0A",
        "accent": "#FF3B30",
        "accent2": "#FF9500",
        "sub": "#00C896"
    },
    {
        "id": "curated_03_attack_on_titan_levi",
        "file": "curated_03_attack_on_titan_levi.svg",
        "anime": "Attack on Titan",
        "character": "Levi Ackerman",
        "resolution": "3840x2160",
        "title": "Survey Corps: Wings of Freedom",
        "theme_color": "#10B981",
        "kanji": "進撃の巨人・自由の翼",
        "quote": "The only thing we are allowed to do is believe that we won't regret the choice we made.",
        "bg1": "#040D0A",
        "bg2": "#0C1C14",
        "accent": "#10B981",
        "accent2": "#34D399",
        "sub": "#EAB308"
    },
    {
        "id": "curated_04_solo_leveling_jinwoo",
        "file": "curated_04_solo_leveling_jinwoo.svg",
        "anime": "Solo Leveling",
        "character": "Sung Jin-Woo",
        "resolution": "3840x2160",
        "title": "Shadow Monarch: Arise",
        "theme_color": "#8B5CF6",
        "kanji": "影の君主・起きろ",
        "quote": "I am the Monarch of Shadows. Arise.",
        "bg1": "#070410",
        "bg2": "#140A2E",
        "accent": "#8B5CF6",
        "accent2": "#A78BFA",
        "sub": "#38BDF8"
    },
    {
        "id": "curated_05_chainsaw_man_denji",
        "file": "curated_05_chainsaw_man_denji.svg",
        "anime": "Chainsaw Man",
        "character": "Denji",
        "resolution": "3840x2160",
        "title": "Chainsaw Devil: Tokyo Requiem",
        "theme_color": "#F97316",
        "kanji": "チェンソーマン・血の暴走",
        "quote": "If I have to die, I want to eat jam on toast first.",
        "bg1": "#110603",
        "bg2": "#270F07",
        "accent": "#F97316",
        "accent2": "#EF4444",
        "sub": "#FDE047"
    },
    {
        "id": "curated_06_frieren_journey",
        "file": "curated_06_frieren_journey.svg",
        "anime": "Frieren",
        "character": "Frieren",
        "resolution": "3840x2160",
        "title": "Zoltraak: Beyond Journey's End",
        "theme_color": "#38BDF8",
        "kanji": "葬送のフリーレン・魂の眠る地",
        "quote": "It is only one one-hundredth of our journey. Yet it changed everything.",
        "bg1": "#030814",
        "bg2": "#0A182E",
        "accent": "#38BDF8",
        "accent2": "#E0E7FF",
        "sub": "#FBBF24"
    },
    {
        "id": "curated_07_cyberpunk_edgerunners",
        "file": "curated_07_cyberpunk_edgerunners.svg",
        "anime": "Cyberpunk: Edgerunners",
        "character": "David Martinez",
        "resolution": "3840x2160",
        "title": "Night City: Sandevistan Overdrive",
        "theme_color": "#FEE500",
        "kanji": "サイバーパンク・ナイトシティ",
        "quote": "I'm going to take you there myself. To the moon.",
        "bg1": "#090412",
        "bg2": "#190A2E",
        "accent": "#FEE500",
        "accent2": "#EC4899",
        "sub": "#06B6D4"
    },
    {
        "id": "curated_08_evangelion_unit01",
        "file": "curated_08_evangelion_unit01.svg",
        "anime": "Neon Genesis Evangelion",
        "character": "Shinji Ikari",
        "resolution": "3840x2160",
        "title": "Evangelion Unit-01: Berserk Awakening",
        "theme_color": "#A855F7",
        "kanji": "新世紀エヴァンゲリオン・初号機",
        "quote": "I mustn't run away. I mustn't run away.",
        "bg1": "#0A0512",
        "bg2": "#17092A",
        "accent": "#A855F7",
        "accent2": "#22C55E",
        "sub": "#EF4444"
    }
]

for art in artworks:
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3840 2160" width="3840" height="2160">
  <defs>
    <radialGradient id="grad-bg" cx="50%" cy="45%" r="70%">
      <stop offset="0%" stop-color="{art['bg2']}" />
      <stop offset="100%" stop-color="{art['bg1']}" />
    </radialGradient>
    <linearGradient id="grad-accent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{art['accent']}" stop-opacity="0.9" />
      <stop offset="100%" stop-color="{art['accent2']}" stop-opacity="0.4" />
    </linearGradient>
    <radialGradient id="grad-glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{art['accent']}" stop-opacity="0.35" />
      <stop offset="100%" stop-color="{art['accent']}" stop-opacity="0" />
    </radialGradient>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="40" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="3840" height="2160" fill="url(#grad-bg)" />
  <circle cx="1920" cy="1080" r="900" fill="url(#grad-glow)" />

  <!-- Geometric Grid & Circuit Lines -->
  <g stroke="{art['accent']}" stroke-opacity="0.08" stroke-width="2">
    <line x1="0" y1="1080" x2="3840" y2="1080" />
    <line x1="1920" y1="0" x2="1920" y2="2160" />
    <circle cx="1920" cy="1080" r="500" fill="none" stroke-dasharray="12 12" />
    <circle cx="1920" cy="1080" r="750" fill="none" stroke-width="1.5" />
    <circle cx="1920" cy="1080" r="1050" fill="none" stroke-dasharray="8 16" />
  </g>

  <!-- Central Emblem Elements -->
  <g transform="translate(1920, 1080)" filter="url(#glow)">
    <polygon points="0,-320 277,-160 277,160 0,320 -277,160 -277,-160" 
             fill="none" stroke="url(#grad-accent)" stroke-width="6" />
    <polygon points="0,-260 225,-130 225,130 0,260 -225,130 -225,-130" 
             fill="none" stroke="{art['sub']}" stroke-width="2" stroke-dasharray="10 20" opacity="0.6" />
    
    <!-- Core Ring -->
    <circle cx="0" cy="0" r="120" fill="none" stroke="{art['accent']}" stroke-width="4" />
    <circle cx="0" cy="0" r="40" fill="{art['accent']}" opacity="0.8" />
  </g>

  <!-- Japanese Kanji Typography -->
  <text x="1920" y="580" 
        font-family="'Noto Sans JP', 'Hiragino Kaku Gothic ProN', sans-serif" 
        font-size="54" 
        font-weight="900" 
        letter-spacing="18" 
        fill="{art['accent']}" 
        text-anchor="middle" 
        opacity="0.85" 
        filter="url(#glow)">
    {art['kanji']}
  </text>

  <!-- Franchise Name -->
  <text x="1920" y="670" 
        font-family="'Inter', 'Montserrat', sans-serif" 
        font-size="36" 
        font-weight="800" 
        letter-spacing="12" 
        fill="#FFFFFF" 
        text-anchor="middle" 
        opacity="0.95">
    {art['anime'].upper()}
  </text>

  <!-- Character & Title -->
  <text x="1920" y="1560" 
        font-family="'Inter', 'Montserrat', sans-serif" 
        font-size="42" 
        font-weight="700" 
        letter-spacing="8" 
        fill="{art['sub']}" 
        text-anchor="middle" 
        opacity="0.9">
    {art['character']}
  </text>

  <text x="1920" y="1630" 
        font-family="'Inter', 'Outfit', sans-serif" 
        font-size="24" 
        font-weight="500" 
        letter-spacing="6" 
        fill="#94A3B8" 
        text-anchor="middle">
    {art['title']}
  </text>

  <!-- Quote -->
  <text x="1920" y="1720" 
        font-family="'Inter', italic" 
        font-size="20" 
        letter-spacing="3" 
        fill="#64748B" 
        text-anchor="middle" 
        font-style="italic">
    "{art['quote']}"
  </text>

  <!-- Technical Overlay Details -->
  <text x="160" y="180" font-family="monospace" font-size="20" fill="{art['accent']}" opacity="0.6">KURO // CURATED OFFLINE MASTER [LEVEL 3]</text>
  <text x="160" y="215" font-family="monospace" font-size="16" fill="#64748B">FRANCHISE_ID: {art['anime'].lower().replace(' ', '_')} | RESOLUTION: {art['resolution']}</text>
  <text x="3680" y="180" font-family="monospace" font-size="20" fill="{art['accent']}" opacity="0.6" text-anchor="end">ORIGIN: MASTER ARCHIVE</text>
  <text x="3680" y="215" font-family="monospace" font-size="16" fill="#64748B" text-anchor="end">SECURE LOCALHOST STREAM</text>

  <!-- Bottom HUD accents -->
  <line x1="160" y1="2000" x2="1000" y2="2000" stroke="{art['accent']}" stroke-width="2" opacity="0.4" />
  <line x1="2840" y1="2000" x2="3680" y2="2000" stroke="{art['accent']}" stroke-width="2" opacity="0.4" />
</svg>
"""
    svg_path = curated_dir / art["file"]
    svg_path.write_text(svg_content, encoding="utf-8")

    meta_path = curated_dir / f"{art['id']}.json"
    meta_path.write_text(json.dumps(art, indent=2), encoding="utf-8")

# ==============================================================================
# 32:9 DUAL-MONITOR PANORAMIC ARTWORKS (3840 x 1080)
# Designed specifically to span across two side-by-side 1080p / 1440p displays
# ==============================================================================
dual_artworks = [
    {
        "id": "curated_dual_01_frieren_panorama",
        "file": "curated_dual_01_frieren_panorama.svg",
        "anime": "Frieren",
        "character": "Frieren & Fern",
        "resolution": "3840x1080",
        "aspect_ratio": "32:9",
        "is_dual_span": True,
        "title": "Beyond Journey's End: Celestial Horizon (32:9 Panoramic)",
        "theme_color": "#38BDF8",
        "kanji_left": "葬送のフリーレン",
        "kanji_right": "魂の眠る地へ",
        "subtitle_left": "FRIEREN · MAGE OF THE HERO PARTY",
        "subtitle_right": "FERN & STARK · THE NEW DAWN",
        "quote": "A journey that spanned ten years, yet lives forever across the stars.",
        "bg1": "#030712",
        "bg2": "#0A192F",
        "accent": "#38BDF8",
        "accent2": "#C084FC",
        "sub": "#FBBF24"
    },
    {
        "id": "curated_dual_02_jujutsu_kaisen_clash",
        "file": "curated_dual_02_jujutsu_kaisen_clash.svg",
        "anime": "Jujutsu Kaisen",
        "character": "Gojo & Sukuna",
        "resolution": "3840x1080",
        "aspect_ratio": "32:9",
        "is_dual_span": True,
        "title": "Duality of Infinity: Void & Shrine (32:9 Panoramic)",
        "theme_color": "#00F0FF",
        "kanji_left": "無量空処・六眼",
        "kanji_right": "伏魔御廚子・呪いの王",
        "subtitle_left": "SATORU GOJO · UNLIMITED VOID",
        "subtitle_right": "RYOMEN SUKUNA · MALEVOLENT SHRINE",
        "quote": "Throughout Heaven and Earth, two monsters shape the boundary of jujutsu.",
        "bg1": "#05020A",
        "bg2": "#1E0824",
        "accent": "#00F0FF",
        "accent2": "#EF4444",
        "sub": "#A855F7"
    },
    {
        "id": "curated_dual_03_cyberpunk_neon_horizon",
        "file": "curated_dual_03_cyberpunk_neon_horizon.svg",
        "anime": "Cyberpunk: Edgerunners",
        "character": "David & Lucy",
        "resolution": "3840x1080",
        "aspect_ratio": "32:9",
        "is_dual_span": True,
        "title": "Night City Megastructure to Lunar Sky (32:9 Panoramic)",
        "theme_color": "#FEE500",
        "kanji_left": "ナイトシティ・電脳",
        "kanji_right": "月への約束・夢",
        "subtitle_left": "DAVID MARTINEZ · SANDEVISTAN",
        "subtitle_right": "LUCY KUSHINADA · DEEP NET",
        "quote": "I couldn't wait for you then. But now you're flying to the moon.",
        "bg1": "#07080C",
        "bg2": "#1A092A",
        "accent": "#FEE500",
        "accent2": "#EC4899",
        "sub": "#06B6D4"
    }
]

for dart in dual_artworks:
    d_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3840 1080" width="3840" height="1080">
  <defs>
    <linearGradient id="dgrad-bg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{dart['bg1']}" />
      <stop offset="50%" stop-color="{dart['bg2']}" />
      <stop offset="100%" stop-color="{dart['bg1']}" />
    </linearGradient>
    <linearGradient id="dgrad-accent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{dart['accent']}" stop-opacity="0.9" />
      <stop offset="100%" stop-color="{dart['accent2']}" stop-opacity="0.5" />
    </linearGradient>
    <radialGradient id="dgrad-glow-left" cx="25%" cy="50%" r="40%">
      <stop offset="0%" stop-color="{dart['accent']}" stop-opacity="0.32" />
      <stop offset="100%" stop-color="{dart['accent']}" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="dgrad-glow-right" cx="75%" cy="50%" r="40%">
      <stop offset="0%" stop-color="{dart['accent2']}" stop-opacity="0.32" />
      <stop offset="100%" stop-color="{dart['accent2']}" stop-opacity="0" />
    </radialGradient>
    <filter id="dglow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="30" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  </defs>

  <!-- Background spanning both displays -->
  <rect width="3840" height="1080" fill="url(#dgrad-bg)" />
  <rect width="1920" height="1080" fill="url(#dgrad-glow-left)" />
  <rect x="1920" width="1920" height="1080" fill="url(#dgrad-glow-right)" />

  <!-- Continuous Horizon Connection Lines -->
  <g stroke="{dart['accent']}" stroke-opacity="0.12" stroke-width="1.5">
    <line x1="0" y1="540" x2="3840" y2="540" />
    <line x1="0" y1="620" x2="3840" y2="620" stroke-dasharray="16 16" />
    <line x1="0" y1="460" x2="3840" y2="460" stroke-dasharray="8 24" />
  </g>

  <!-- Physical Bezel Center Seam Marker (Subtle guide at x=1920) -->
  <line x1="1920" y1="0" x2="1920" y2="1080" stroke="{dart['accent']}" stroke-opacity="0.08" stroke-width="1" stroke-dasharray="4 8" />

  <!-- LEFT MONITOR COMPOSITION (Center: x=960, y=540) -->
  <g transform="translate(960, 540)" filter="url(#dglow)">
    <polygon points="0,-180 156,-90 156,90 0,180 -156,90 -156,-90" fill="none" stroke="{dart['accent']}" stroke-width="4" />
    <circle cx="0" cy="0" r="80" fill="none" stroke="{dart['sub']}" stroke-width="2" stroke-dasharray="6 12" />
    <circle cx="0" cy="0" r="28" fill="{dart['accent']}" opacity="0.8" />
  </g>
  <text x="960" y="260" font-family="'Noto Sans JP', sans-serif" font-size="34" font-weight="900" letter-spacing="12" fill="{dart['accent']}" text-anchor="middle" filter="url(#dglow)">{dart['kanji_left']}</text>
  <text x="960" y="320" font-family="'Inter', sans-serif" font-size="22" font-weight="800" letter-spacing="6" fill="#FFFFFF" text-anchor="middle">{dart['subtitle_left']}</text>
  <text x="960" y="780" font-family="'Inter', monospace" font-size="14" fill="{dart['accent']}" opacity="0.7" letter-spacing="4" text-anchor="middle">[ DISPLAY 1 · LEFT WING ]</text>

  <!-- RIGHT MONITOR COMPOSITION (Center: x=2880, y=540) -->
  <g transform="translate(2880, 540)" filter="url(#dglow)">
    <polygon points="0,-180 156,-90 156,90 0,180 -156,90 -156,-90" fill="none" stroke="{dart['accent2']}" stroke-width="4" />
    <circle cx="0" cy="0" r="80" fill="none" stroke="{dart['sub']}" stroke-width="2" stroke-dasharray="6 12" />
    <circle cx="0" cy="0" r="28" fill="{dart['accent2']}" opacity="0.8" />
  </g>
  <text x="2880" y="260" font-family="'Noto Sans JP', sans-serif" font-size="34" font-weight="900" letter-spacing="12" fill="{dart['accent2']}" text-anchor="middle" filter="url(#dglow)">{dart['kanji_right']}</text>
  <text x="2880" y="320" font-family="'Inter', sans-serif" font-size="22" font-weight="800" letter-spacing="6" fill="#FFFFFF" text-anchor="middle">{dart['subtitle_right']}</text>
  <text x="2880" y="780" font-family="'Inter', monospace" font-size="14" fill="{dart['accent2']}" opacity="0.7" letter-spacing="4" text-anchor="middle">[ DISPLAY 2 · RIGHT WING ]</text>

  <!-- Center Quote Spanning Seam -->
  <text x="1920" y="960" font-family="'Inter', italic" font-size="18" letter-spacing="4" fill="#94A3B8" text-anchor="middle" font-style="italic">"{dart['quote']}"</text>
  <text x="1920" y="1000" font-family="'Inter', sans-serif" font-size="14" font-weight="700" letter-spacing="8" fill="{dart['accent']}" text-anchor="middle" opacity="0.8">KURO // DUAL-MONITOR 32:9 CINEMATIC PANORAMA · 3840×1080</text>
</svg>
"""
    svg_p = curated_dir / dart["file"]
    svg_p.write_text(d_svg, encoding="utf-8")
    meta_p = curated_dir / f"{dart['id']}.json"
    meta_p.write_text(json.dumps(dart, indent=2), encoding="utf-8")

print(f"Generated {len(artworks)} 16:9 and {len(dual_artworks)} 32:9 dual-monitor wallpapers in {curated_dir}")
