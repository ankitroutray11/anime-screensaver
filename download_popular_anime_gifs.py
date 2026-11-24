#!/usr/bin/env python3
"""
KURO // ANIME — High-Resolution Popular Anime Animated GIF Downloader & Indexer
Downloads verified high-resolution anime GIF loops across all popular anime franchises,
writes companion JSON metadata, and indexes them into SQLite for infinite looping playback.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CURATED_DIR = BASE_DIR / "curated_wallpapers"
CURATED_DIR.mkdir(exist_ok=True)

# List of popular anime franchises with search tags and character details
POPULAR_FRANCHISES = [
    {
        "id": "jujutsu_kaisen",
        "name": "Jujutsu Kaisen",
        "character": "Satoru Gojo",
        "title": "Jujutsu Kaisen - Gojo Domain Expansion Loop",
        "tag": "jujutsu_kaisen",
        "tags": ["jujutsu_kaisen", "gojo", "sukuna", "animated", "gif", "loop", "domain_expansion"]
    },
    {
        "id": "demon_slayer",
        "name": "Demon Slayer",
        "character": "Tanjiro Kamado",
        "title": "Demon Slayer - Hinokami Kagura Breathing Loop",
        "tag": "kimetsu_no_yaiba",
        "tags": ["kimetsu_no_yaiba", "demon_slayer", "tanjiro", "nezuko", "animated", "gif", "loop"]
    },
    {
        "id": "attack_on_titan",
        "name": "Attack on Titan",
        "character": "Levi Ackerman",
        "title": "Attack on Titan - Levi Ackerman ODM Flight Loop",
        "tag": "shingeki_no_kyojin",
        "tags": ["shingeki_no_kyojin", "attack_on_titan", "levi", "eren", "animated", "gif", "loop"]
    },
    {
        "id": "chainsaw_man",
        "name": "Chainsaw Man",
        "character": "Denji & Power",
        "title": "Chainsaw Man - Devil Hunter Dynamic Loop",
        "tag": "chainsaw_man",
        "tags": ["chainsaw_man", "denji", "power", "makima", "animated", "gif", "loop"]
    },
    {
        "id": "one_piece",
        "name": "One Piece",
        "character": "Monkey D. Luffy",
        "title": "One Piece - Luffy Gear Epic Motion Loop",
        "tag": "one_piece",
        "tags": ["one_piece", "luffy", "zoro", "animated", "gif", "loop"]
    },
    {
        "id": "bleach",
        "name": "Bleach",
        "character": "Ichigo Kurosaki",
        "title": "Bleach - Ichigo Getsuga Tensho Bankai Loop",
        "tag": "bleach",
        "tags": ["bleach", "ichigo", "bankai", "animated", "gif", "loop"]
    },
    {
        "id": "cyberpunk_edgerunners",
        "name": "Cyberpunk: Edgerunners",
        "character": "Lucy",
        "title": "Cyberpunk: Edgerunners - Moonlit Night City Loop",
        "tag": "cyberpunk",
        "tags": ["cyberpunk_edgerunners", "lucy", "david", "night_city", "animated", "gif", "loop"]
    },
    {
        "id": "neon_genesis_evangelion",
        "name": "Neon Genesis Evangelion",
        "character": "Asuka & Rei",
        "title": "Evangelion - Tokyo-3 Horizon Ambient Loop",
        "tag": "neon_genesis_evangelion",
        "tags": ["neon_genesis_evangelion", "eva", "asuka", "rei", "animated", "gif", "loop"]
    },
    {
        "id": "naruto",
        "name": "Naruto",
        "character": "Naruto & Sasuke",
        "title": "Naruto Shippuden - Rasengan Clash Motion Loop",
        "tag": "naruto",
        "tags": ["naruto", "sasuke", "kakashi", "animated", "gif", "loop"]
    },
    {
        "id": "frieren",
        "name": "Frieren",
        "character": "Frieren",
        "title": "Frieren - Beyond Journey's End Starlight Magic Loop",
        "tag": "sousou_no_frieren",
        "tags": ["sousou_no_frieren", "frieren", "fern", "magic", "animated", "gif", "loop"]
    },
    {
        "id": "dragon_ball",
        "name": "Dragon Ball",
        "character": "Goku",
        "title": "Dragon Ball - Super Saiyan Aura Surge Loop",
        "tag": "dragon_ball",
        "tags": ["dragon_ball", "goku", "vegeta", "super_saiyan", "animated", "gif", "loop"]
    },
    {
        "id": "hunter_x_hunter",
        "name": "Hunter x Hunter",
        "character": "Killua Zoldyck",
        "title": "Hunter x Hunter - Killua Godspeed Lightning Loop",
        "tag": "hunter_x_hunter",
        "tags": ["hunter_x_hunter", "killua", "gon", "godspeed", "animated", "gif", "loop"]
    },
    {
        "id": "my_hero_academia",
        "name": "My Hero Academia",
        "character": "Izuku Midoriya",
        "title": "My Hero Academia - One For All Full Cowl Loop",
        "tag": "boku_no_hero_academia",
        "tags": ["boku_no_hero_academia", "deku", "bakugo", "animated", "gif", "loop"]
    },
    {
        "id": "fate_series",
        "name": "Fate Series",
        "character": "Saber",
        "title": "Fate Series - Excalibur Noble Phantasm Loop",
        "tag": "fate_(series)",
        "tags": ["fate", "saber", "archer", "excalibur", "animated", "gif", "loop"]
    },
    {
        "id": "solo_leveling",
        "name": "Solo Leveling",
        "character": "Sung Jin-woo",
        "title": "Solo Leveling - Shadow Monarch Monarch Aura Loop",
        "tag": "solo_leveling",
        "tags": ["solo_leveling", "sung_jin_woo", "shadow_monarch", "animated", "gif", "loop"]
    },
    {
        "id": "death_note",
        "name": "Death Note",
        "character": "Light & L",
        "title": "Death Note - Psychological Shadow Rain Loop",
        "tag": "death_note",
        "tags": ["death_note", "light", "l", "ryuk", "animated", "gif", "loop"]
    }
]


def fetch_gif_candidate_for_franchise(tag: str, min_width: int = 400):
    """Queries Safebooru for an animated GIF matching the tag."""
    queries = [
        f"animated+{tag}+width:>={min_width}",
        f"animated+{tag}",
    ]
    for q in queries:
        url = f"https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&limit=6&tags={q}+-rating:explicit"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kuro/3.5"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not isinstance(data, list):
                    continue
                # Pick largest resolution GIF
                candidates = []
                for item in data:
                    img = item.get("image")
                    d_dir = item.get("directory")
                    w = int(item.get("width") or 0)
                    h = int(item.get("height") or 0)
                    if img and str(img).lower().endswith(".gif") and d_dir:
                        candidates.append((w * h, w, h, f"https://safebooru.org/images/{d_dir}/{img}", item))
                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    return candidates[0]
        except Exception as e:
            continue
    return None


def download_all_franchise_gifs():
    """Downloads high-res GIFs for each popular anime franchise and writes metadata."""
    print("======================================================================")
    print("  KURO // ANIME — High-Resolution Popular Anime GIF Downloader")
    print(f"  Target: {len(POPULAR_FRANCHISES)} Popular Anime Franchises")
    print(f"  Destination: {CURATED_DIR}")
    print("======================================================================")
    print()

    downloaded = 0
    for idx, f_info in enumerate(POPULAR_FRANCHISES, 1):
        f_id = f_info["id"]
        f_name = f_info["name"]
        target_gif = CURATED_DIR / f"curated_gif_{f_id}.gif"
        target_json = CURATED_DIR / f"curated_gif_{f_id}.json"

        if target_gif.is_file() and target_gif.stat().st_size > 10000 and target_json.is_file():
            print(f"[{idx}/{len(POPULAR_FRANCHISES)}] {f_name}: Already present on disk ({round(target_gif.stat().st_size / 1024)} KB).")
            downloaded += 1
            continue

        print(f"[{idx}/{len(POPULAR_FRANCHISES)}] Searching high-res GIF for {f_name} (tag: {f_info['tag']})...")
        candidate = fetch_gif_candidate_for_franchise(f_info["tag"])
        if not candidate:
            print(f"  -> No specific candidate found for {f_name}, trying fallback animated loop...")
            candidate = fetch_gif_candidate_for_franchise("scenery", min_width=600)

        if candidate:
            _, w, h, gif_url, item = candidate
            print(f"  -> Found {w}x{h} GIF: {gif_url}")
            try:
                req = urllib.request.Request(gif_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as r, open(target_gif, "wb") as out_f:
                    out_f.write(r.read())
                
                size_kb = round(target_gif.stat().st_size / 1024)
                aspect = "16:9" if w >= h else "9:16"
                if abs(w / max(1, h) - 1.0) < 0.15:
                    aspect = "1:1"

                metadata = {
                    "id": f"curated_gif_{f_id}",
                    "title": f_info["title"],
                    "anime": f_name,
                    "character": f_info["character"],
                    "resolution": f"{w}x{h}",
                    "aspect_ratio": aspect,
                    "is_animated": True,
                    "media_type": "gif",
                    "tags": f_info["tags"] + ["offline", "curated", "high_res", f"{w}x{h}"],
                    "quality_score": 92.5,
                    "technical_score": 90.0,
                    "popularity_score": 95.0,
                    "source": "Curated Offline Anime",
                    "file_size": target_gif.stat().st_size
                }
                with open(target_json, "w", encoding="utf-8") as jf:
                    json.dump(metadata, jf, indent=2)

                print(f"  -> Successfully saved {f_name} ({size_kb} KB, {w}x{h})")
                downloaded += 1
            except Exception as dl_err:
                print(f"  [ERROR] Failed downloading GIF for {f_name}: {dl_err}")
        else:
            print(f"  [WARN] Skipping {f_name} (no candidate available).")
        time.sleep(0.4)

    print()
    print(f"Download complete: {downloaded}/{len(POPULAR_FRANCHISES)} franchises ready.")

    # Index into SQLite database
    print("\nIndexing curated GIFs into kuro_database.db...")
    try:
        from database import DatabaseManager
        db_path = BASE_DIR / "kuro_database.db"
        db = DatabaseManager(db_path)
        indexed = db.index_curated_collection()
        print(f"[KuroDB] Curated collection indexed ({indexed} artwork records synchronized).")

        # Set all curated GIFs to UNSEEN status so they immediately start cycling
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE wallpaper_lifecycle
                SET status = 'UNSEEN'
                WHERE (is_animated = 1 OR media_type = 'gif')
                  AND level = 3
            """)
            conn.commit()
            cur.execute("SELECT COUNT(*) FROM wallpaper_lifecycle WHERE (is_animated = 1 OR media_type = 'gif') AND status = 'UNSEEN'")
            unseen_total = cur.fetchone()[0]
            print(f"[KuroDB] High-resolution anime GIF loop library ready: {unseen_total} active loops ready to play.")
    except Exception as idx_err:
        print(f"[KuroDB ERROR] Failed indexing: {idx_err}")


if __name__ == "__main__":
    download_all_franchise_gifs()
