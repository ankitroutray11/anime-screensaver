# 🌌 KURO // ANIME — Dark Anime Screensaver for Windows & Multi-Monitor

An ultra-clean, high-aesthetic, production-grade dark anime screensaver designed specifically for secondary and primary monitors on Windows. Built with zero runtime third-party Python dependencies (Standard Library only) and a framework-free vanilla JavaScript/CSS3 frontend.

Features continuous zero-repetition live streaming, a 3-layer offline-first fallback engine, personal collection management, OLED burn-in mitigation, and native Windows integration with browser kiosk multi-monitor targeting.

---

## ✨ System Highlights

- **Zero Repetition Lifecycle:** Tracks every artwork shown in a transactional SQLite WAL database (`kuro_database.db`). New art is continuously prefetched from live anime feeds (Wallhaven & curated libraries) with state transitions: `UNSEEN -> RESERVED -> DISPLAYED`.
- **3-Layer Offline Fallback System:**
  - **Level 1 (Live Stream):** High-resolution art streaming from Wallhaven with backoff & rate-limit handling.
  - **Level 2 (Local Cache):** Cached high-resolution wallpapers stored locally in `.cache/wallpapers/` with bounded LRU disk management.
  - **Level 3 (Curated Collection):** Local curated anime collection in `curated_wallpapers/` guaranteeing non-stop aesthetic presentation during total internet outages.
- **3 Display Modes:**
  - **Ambient Mode:** Balanced minimal digital clock, full calendar date, compact Open-Meteo weather widget, and auto-dimming HUD.
  - **Cinematic Mode:** Borderless artwork occupying the entire display with floating micro-metadata and subtle ambient particles.
  - **Dashboard Mode:** Comprehensive layout with enlarged clock, weather metrics, franchise metadata, slideshow controls, and cache utilization.
- **Intelligent Personalization & Taste Engine:**
  - **Local Privacy-First Scoring:** Tracks favorites, viewing dwell sessions, backward history revisits, rapid skips (< 5s), and manual blacklists completely locally in SQLite WAL (`interaction_events`, `preference_scores`, `recommendation_settings`). Zero data egress or third-party telemetry.
  - **Explainable Scoring Weights:** Favorites (+15 franchise, +20 character), viewing dwell ($\ge 30$s: $+2/+3$; $\ge 60$s: $+4/+5$), history revisits (+5/+8), skips ($-2.5/-4.0$), and manual franchise selection (+4.0 with soft unselected decay).
  - **Diversity Guard:** Dynamic recency penalty window scales down the probability of repeating the last 1–3 displayed franchises consecutively, ensuring vibrant visual diversity without artificial repetition.
  - **Deterministic Zero-Repeat Preservation:** Combines learned preferences with franchise weights for discovery while strictly maintaining the global transactional `UNSEEN -> RESERVED -> DISPLAYED` guarantee.
  - **Transparent Control:** Live taste profile chips with +/- score visualization, manual bias adjustment slider (-50 to +50), master toggle, and one-click learning history reset to neutral.
- **Intelligent Artwork Quality Scoring System:**
  - **Pre-Queue Quality Evaluation:** Evaluates every discovered wallpaper on a 0–100 scale before it enters the reservation and display queue.
  - **Objective Technical Image Quality (65% Weight):**
    - *Native Resolution Priority:* Rewards native display matching (30 pts) and supersampled 4K/UHD renders (up to 40 pts); penalizes low-resolution images requiring software upscaling.
    - *Aspect Ratio Compatibility:* Scores aspect ratio fit (16:9, 21:9 Ultrawide, 9:16 Portrait) up to 20 pts; penalizes mismatched geometry to avoid letterboxing.
    - *Sharpness & Detail Density:* Measures bits-per-pixel (BPP) and entropy to award up to 10 pts for crisp, compression-artifact-free art.
    - *Dynamic Range & Contrast:* Analyzes palette color distributions to award up to 10 pts for vivid dynamic range.
  - **Community Popularity (35% Weight):** Logarithmic favorites scaling combined with view-to-favorite engagement ratio; serves as a secondary audience signal rather than the sole arbiter of quality.
  - **Perceptual Similarity Guard:** Automatically detects color palette clustering against recently displayed artwork and applies a diversity penalty (-15 pts) to prevent visually repetitive palettes.
  - **OLED & Ambient Vision Filters:** Optional automated exclusion of blindingly bright artwork ($Y > 210$) and pitch-black unreadable artwork ($Y < 18$).
  - **SQLite WAL Persistence:** Stores technical and popularity scores directly in `wallpaper_lifecycle`, completely eliminating redundant re-evaluations.
  - **Clear Quality Distinction:** Transparently separates technical fidelity from community popularity; explicitly disclaims evaluating subjective artistic merit.
- **Intelligent Slideshow Scheduling Engine:**
  - **6 Configurable Pacing Strategies:**
    1. *Fixed Interval:* Constant baseline transition interval (5s to 600s, default 30s).
    2. *Random Interval:* Dynamic uniform jitter randomly selected within a configured range (e.g. 15s to 60s) to keep pacing fresh.
    3. *Quality & Rating Weighted Duration:* Dynamically scales slide duration according to artwork technical quality ($Q \ge 70$ receives up to $+40\%$ viewing bonus; low-quality $Q < 40$ transitions faster) and awards favorited artwork an extra $+10$s dwelling bonus.
    4. *Time-Based Scheduling:* Automatic diurnal dayparting adjusting interval according to local wall-clock hours:
       - **Daytime (08:00 – 17:00):** Energetic pacing (default 25s).
       - **Evening (17:00 – 22:00):** Balanced atmospheric pacing (default 35s).
       - **Night (22:00 – 08:00):** Extended ambient slow-drift pacing (default 60s).
    5. *Franchise Rotation:* Automatically cycles active anime franchise every $N$ slides (default 5 slides) with subtle notifications.
    6. *Manual-Only Mode:* Auto-advance timer completely disengaged; slideshow advances strictly on explicit user demand (<kbd>→</kbd>, <kbd>←</kbd>, or on-screen controls).
  - **Display Mode Overrides:**
    - *Cinematic Mode Override:* Extended contemplative presentation (default 45s).
    - *Dashboard Mode Override:* Accelerated glanceable stats overview (default 20s).
  - **Zero Transition Collisions & Race Prevention:**
    - Prevents interruption of transitions in progress via strict mutual exclusion (`STATE.isTransitioning` lock).
    - All existing timer tickets and RAF loops are cleanly cancelled before scheduling new slides.
  - **Smart Visibility & Inactivity Pause:**
    - Automatically pauses slideshow countdown when the browser window or tab is minimized or hidden (`document.visibilitychange`), freezing elapsed time.
    - Resumes seamlessly when brought back into focus with zero skip or visual stutter.
    - Preserves user manual pause state across temporary network dropouts or backend reconnections.
  - **HUD Countdown & Progress Indicator:**
    - Displays exact remaining countdown seconds in the HUD (`#progress-timer-text`) alongside elapsed and total durations.
  - **Persistent Local Configuration:**
    - Synchronized to SQLite WAL (`scheduler_settings` table via `GET /api/scheduler/settings` & `POST /api/scheduler/settings` with CSRF protection) and backed up to `localStorage` for instant client-side offline hydration.
- **Personal Collection Management:**
  - Save original high-resolution art to `favorites/` with chunked streaming and atomic temp file finalization.
  - Create and manage custom collections (e.g., *Masterpieces*, *Cinematic Nights*).
  - Search by character, filter by anime franchise, and filter by resolution (4K, 1440p, 1080p, Ultrawide, Portrait).
  - Permanent artwork blacklist to exclude unwanted art from reservations and prefetch queues.
- **Multi-Monitor & DPI Topology:**
  - Automatically queries Windows API (`EnumDisplayMonitors`) and calculates exact virtual desktop coordinates.
  - Supports 16:9 (1080p, 1440p, 4K UHD), 21:9 Ultrawide, and 9:16 Portrait pivot displays.
  - Intelligent character-focal crop algorithms ensure character faces are never cut off during aspect ratio adjustments.
- **OLED Burn-in Protection:**
  - Sub-pixel orbital micro-shift (`driftX`/`driftY`) to prevent static element phosphor wear.
  - Inactivity HUD auto-dimming with smooth mouse wake.
  - Luminance softening and configurable darkening scrim overlays for nighttime viewing.
- **Enterprise Security Hardening:**
  - Binds strictly to `127.0.0.1` loopback with localhost origin and referer validation.
  - Cryptographic 256-bit local session token (`X-Kuro-Token`) required for all state-changing endpoints.
  - SSRF protection blocks loopback/LAN traversal, private IP ranges (RFC 1918), and cloud instance metadata services (AWS/GCP/Azure).
  - Path traversal defense restricts disk operations to designated sandbox roots.
- **Intelligent Wallpaper Composition & Focal-Point Protection:**
  - **Non-Destructive Multi-Monitor Framing:** Dynamically handles 16:9 Landscape, 21:9 Ultrawide, and 9:16 Portrait pivot displays without permanently altering source image files on disk. 100% GPU CSS hardware-composited transforms.
  - **3 Display Modes:**
    - *Fill (Cover):* Fills the viewport with zoom centered on the focal coordinate.
    - *Fit (Contain):* Renders the complete artwork uncropped with optional ambient backdrop fill.
    - *Original (1:1):* Displays pixels unscaled centered on the focal point for maximum native crispness.
  - **Blurred Ambient Backdrop Fill:** Dynamic aspect-ratio-matched background layer (`.wallpaper-backdrop`) applying high-radius CSS blur and ambient saturation boost to eliminate harsh black letterbox bars during `fit` mode.
  - **Interactive Framing & Focal Reticle:** Interactive modal (<kbd>O</kbd>) featuring a draggable focal-point reticle, coordinate readout, and quick preset framing (Center, Upper Third, Character Left, Character Right).
  - **Multi-Character Centroid Framing:** Supports multiple character pin markers within a single image; automatically calculates the bounding centroid to keep ensemble casts in frame.
  - **Orientation-Specific Preferences:** Configurable separate defaults for portrait vs landscape displays.
  - **Honest Positioning Standard:** Default `{ x: 50, y: 50 }` center / upper-third focal coordinates; does not claim pseudo-AI face detection when computer vision heuristics are unavailable.
  - **SQLite WAL Persistence:** Stores wallpaper-specific focal coordinates and display preferences in `wallpaper_composition` with global fallbacks in `composition_settings`.
- **Interactive Artwork Information Panel (<kbd>I</kbd>):**
  - **Comprehensive Live Artwork Dossier:** Instant glassmorphic overlay displaying authentic metadata without interrupting active slideshow playback.
  - **Verified Metadata Specs:**
    - *Anime Franchise & Characters:* Verified franchise title and character tags.
    - *Image Attributes:* Original pixel resolution, calculated aspect ratio, and formatted disk file size.
    - *Wallhaven Provenance:* Wallpaper ID, direct source link, views count, favorites count, uploader username, and upload date.
    - *Playback Metrics:* Current session sequence number and technical quality score (0–100).
    - *Authenticity Standard:* Honest labeling of missing attributes as `<Unavailable>` or `Unverified` rather than fabricating synthetic data.
  - **Quick Keyboard & Mouse Actions:**
    - <kbd>O</kbd> / Open Source: Opens original Wallhaven or external source page in browser.
    - <kbd>C</kbd> / Copy Link: Copies high-resolution direct image URL to clipboard.
    - <kbd>L</kbd> / Favorite: Instantly downloads original high-resolution art to favorites.
    - <kbd>V</kbd> / Full Res: Opens uncompressed image directly in browser.
    - <kbd>H</kbd> / Skip: Skips current artwork.
    - <kbd>B</kbd> / Blacklist: Permanently excludes artwork from future rotations.
  - **Non-Blocking Execution:** Transitions and countdown timers continue smoothly in the background; the panel dynamically refreshes its metadata when the next slide advances.
- **Optional Ambient Soundscape Engine:**
  - **Local-Only Audio Architecture:** 100% locally stored and synthesized soundscapes. Zero third-party web streaming, zero external bandwidth consumption, and zero bundled copyrighted commercial music.
  - **8 Curated Atmospheric Categories:**
    - *Rain:* Continuous soothing rainfall with multi-layer pink noise & water drop transient bursts.
    - *Thunderstorm:* Deep rolling low-frequency rumbling with atmospheric rain curtain.
    - *Japanese Forest:* Gentle wind breeze through leaves with soft bamboo shishi-odoshi water chime strikes.
    - *Night City Ambience:* Distant metropolitan low rumble with filtered urban background resonance.
    - *Ocean Waves:* Rhythmic swell and ebb surge with low-frequency wave crests and foam wash.
    - *Wind:* Whistling high/low pressure wind gusts with smooth Gaussian modulation.
    - *Fireplace:* Warm crackling wood embers with high-frequency timber pop transients.
    - *Space Ambience:* Ethereal sub-bass cosmic drone with detuned stereo harmonics and slow LFO drift.
  - **Built-in Procedural Audio Synthesizer:** `soundscape_generator.py` uses only Python standard library (`wave`, `struct`, `math`, `random`) to synthesize high-quality 16-bit 22,050 Hz stereo PCM audio with zero external binary dependencies.
  - **Seamless Pop-Free Loop Bounds:** Mathematically blended 0.5s cosine crossfade applied across beginning and end boundaries so audio loops indefinitely without pops or clicks.
  - **Dual-Channel A/B Equal-Power Crossfading:** Seamless fading between environments via two parallel HTML5 audio channels; Channel A attenuates along an equal-power curve while Channel B ramps up to target volume over a configurable duration (1s–10s).
  - **Safe Autoplay Compliance:** Soundscapes start muted and disabled by default (`enabled: false`, `muted: true`), respecting browser autoplay security policies while persisting preferences in SQLite WAL (`soundscape_settings`).
  - **Custom User Audio Support:** Automatically scans `soundscapes/` directory for user-provided audio files (`.wav`, `.mp3`, `.ogg`, `.flac`, `.m4a`) with strict path traversal isolation.
  - **Clean Process Termination:** Audio playback halts immediately on application exit, window unload, or `Ctrl+Q`.
- **Advanced Anime Ambient Control Center (<kbd>S</kbd>):**
  - **Glassmorphic Two-Pane Control Suite:** Transformed the simple preferences modal into a comprehensive, high-aesthetic control center with sidebar tab navigation, real-time live search, and instant setting counts.
  - **6 Dedicated Configuration Sections:**
    1. *General:* Default display mode, baseline slideshow interval (5s–600s), startup behavior (Windows boot autostart, kiosk vs windowed launch), clock styling (12h/24h, seconds display, date format, secondary timezone offset), and weather metrics (°C/°F, manual city override, auto geolocation).
    2. *Wallpaper:* Franchise multi-selection, character filters, franchise weights/taste bias (-50 to +50), minimum popularity rating threshold (favorites count), minimum resolution (Any, 1080p, 1440p, 4K UHD, 8K), target aspect ratio, and duplicate sensitivity / diversity guard window.
    3. *Visual:* 5 handcrafted anime aesthetic themes (*Kuro Dark Anime*, *Cyberpunk Neon*, *Sakura Blossom*, *Midnight Minimal*, *Tokyo Noir*), dynamic color extraction vs custom hex/swatch accent palette, transition style & duration (0.5s–5.0s), animation intensity with reduced motion support, ambient floating particle density and speed, HUD base opacity, and OLED care darkening scrim.
    4. *Display:* Physical monitor selection (queried live from Windows display topology via `EnumDisplayMonitors`), display orientation readout, native resolution profile, Windows display scaling & UI zoom (85%–125%), wallpaper fitting mode (`fill`, `fit`, `original`), blurred ambient backdrop fill, and backdrop blur radius (10px–80px).
    5. *Performance:* Prefetch queue depth (3–15 candidates), bounded LRU wallpaper disk cache limit (500MB–5000MB), parallel download worker threads (1–4), per-request image download limits, and rendering framerate target (60 FPS, 30 FPS, low power).
    6. *Privacy:* Local history tracking breakdown (seen count, one-click history clearing), privacy-first preference learning engine controls (master toggle, dwell session stats, taste reset), one-click `.cache/` cache purge, configuration export/import (`kuro_config_backup.json`), and non-destructive factory reset (preserving saved favorites).
  - **Real-Time Interactive Search:** Dynamically filters controls across all 6 sections simultaneously with live per-section match count badges and a quick-clear button (<kbd>✕</kbd>).
  - **Non-Destructive Live Visual Preview:** Changes to themes, accent swatches, UI scaling, HUD opacity, and backdrop blur render immediately in the background while browsing; clicking **Cancel** or pressing <kbd>Esc</kbd> cleanly restores previous visual styling.
  - **Section-Isolated Reset:** Individual section reset button ("↺ Reset Section") reverts only the active tab to factory defaults without affecting preferences in other sections.
  - **Robust Client & Server Validation:** Boundary and type validation on all numeric inputs, dropdowns, and text values; state changes persist transactionally in SQLite WAL (`control_center_settings`) and `localStorage` with CSRF token authentication (`X-Kuro-Token`).
- **Complete Backup, Disaster Recovery & Database Integrity System:**
  - **Online Safe SQLite Backups:** Utilizes Python's native `sqlite3.Connection.backup()` API to capture live, point-in-time snapshots of the active SQLite database without risking WAL file locking or concurrency conflicts on Windows.
  - **Self-Contained Versioned Archives:** Packages database snapshots, `launcher_config.json`, and optional favorites (`favorites/`) or cache (`.cache/wallpapers/`) into versioned ZIP archives (`kuro_backup_v{schema_version}_{timestamp}_{type}.zip`).
  - **Cryptographic Manifest & Checksum Validation:** Manifest includes table census, schema version, and SHA-256 digests. Archive validation rigorously checks ZIP integrity, SHA-256 consistency, and executes `PRAGMA integrity_check` before permitting any restore.
  - **Pre-Migration Automated Backups:** Automatically creates a backup snapshot whenever an existing database is initialized and requires schema migrations to current schema version (`v13`).
  - **Zero Overwrite Without Confirmation & Pre-Restore Safety Snapshots:** Restoring from any backup strictly requires explicit confirmation (`confirm=True`) and automatically snapshots the current live state (`auto_pre_restore`) prior to applying changes.
  - **Configurable Retention:** Automatically prunes old automatic snapshots beyond a configurable limit (`max_auto_backups`, default 5), keeping manual exports preserved permanently.
  - **Database Diagnostics:** REST API and UI endpoints (`GET /api/database/integrity`) run deep diagnostics including `PRAGMA integrity_check(100)`, `PRAGMA quick_check(100)`, and `PRAGMA foreign_key_check`.
- **Application Performance Monitoring & Adaptive Rendering System (<kbd>D</kbd>):**
  - **Comprehensive Client & Server Performance Tracking:**
    - *Browser Memory Usage:* Feature-detected JS heap memory monitor (`performance.memory`) displaying used heap, total heap, and heap limits with a clean `<Unavailable>` fallback for non-Chromium browsers.
    - *Frontend Frame Rate (FPS):* Rolling 1-second `requestAnimationFrame` framerate calculation with color-coded health indicators (green $\ge 50$, amber $30-49$, red $< 30$).
    - *Wallpaper Image Load & Decode Latency:* Nanosecond-precision duration tracking (`performance.now()`) measuring both network/cache fetch and off-thread GPU decode (`img.decode()`).
    - *Prefetch Queue Buffer Depth:* Tracks unseen candidates, cached unseen items, and buffer headroom against target thresholds.
    - *Image Cache Hit Rate:* Tracks total lookups, cache hits, misses, and rolling hit rate percentage ($H / L \times 100\%$).
    - *Backend HTTP Response Latency:* Rolling average, P95, minimum, maximum, and last latency across all server endpoints.
    - *SQLite Operation Latency:* Real-time database query latency timer wrapping every connection and transaction; tracks average latency, P95, and slow queries ($> 50$ms).
    - *API Failure Rate:* Tracks total HTTP requests, 4xx/5xx responses, failure rate percentage, and status code distribution.
    - *Active Worker Threads:* Monitors prefetch worker thread liveness, worker state, and active thread count.
  - **Compact Glassmorphic Diagnostics Panel:**
    - Instant overlay toggled via shortcut <kbd>D</kbd>, header close button, or the bottom HUD lightning button (`⚡`).
    - 3x3 metrics grid with status badges, monospace figures, and a one-click rolling metrics reset button.
  - **3 Adaptive Visual Quality Profiles:**
    - **High Quality (Default):** Full-resolution artwork, cinematic Ken Burns pan/zoom animations, ambient particle canvas, dynamic accent color extraction, and 28px blurred backdrop fill.
    - **Balanced:** Full-resolution artwork, reduced animation scale transforms (1.03x), 12px blur backdrop, moderate particle count, and optimized palette extraction.
    - **Low Resource:** Full-resolution artwork (Rule 1: Never reduces original saved image quality!), disabled backdrop blur (solid dark `#07090e`), paused particle canvas loop, fixed default accent color (`#38bdf8`), and clean 0.8s crossfades.
    - **Auto Mode:** Dynamically steps quality profiles down if rolling FPS drops below 35 or under severe memory pressure, and smoothly steps back up when framerate stabilizes above 55 FPS.
  - **Memory & Resource Safeguards:**
    - *Single Concurrent Image Decode Queue:* Restricts simultaneous image decoding to 1 at a time, eliminating UI freezes when decoding heavy 4K/UHD artwork.
    - *Object URL Registry:* Tracks all generated Blob URLs and instantly revokes unused URLs to prevent browser memory leaks.
    - *Strict Polling Discipline:* Diagnostics API polling occurs only while the panel is visible; monitoring immediately halts when the panel is closed or when the browser tab is hidden (`document.visibilitychange`).
- **Visual Wallpaper History Explorer:**
  - **Comprehensive History Overview:** Dedicated modal interface (toggle with shortcut <kbd>Y</kbd>, header History tab, or bottom HUD scroll button `📜`) displaying all previously shown anime artworks with zero performance lag.
  - **Visual Thumbnail Grid:** Lazy-loaded thumbnail cards (`loading="lazy"`) with fallback error handling, resolution badge, technical quality score badge, anime franchise title, character name, display timestamp, and similarity group tags.
  - **Server-Side Pagination:** Fast paged queries (`GET /api/history` & `/api/history/explorer`) supporting page size selection (12, 24, 48, 96) and First/Prev/Next/Last controls.
  - **Multi-Parameter Search & Filter Engine:**
    - *Search Query ($q$):* Free-text search matching across franchise, character name, and wallpaper ID.
    - *Anime Franchise Filter:* Dynamic dropdown auto-populated from discovered history and catalog franchises.
    - *Display Date Filters:* Today ($< 24$h), Yesterday ($24-48$h), Past Week ($< 7$d), and Past Month ($< 30$d).
    - *Resolution Filters:* 4K UHD, 1440p, 1080p, Ultrawide (21:9), and Portrait (9:16).
    - *Favorites-Only Toggle:* Filter down to favorited artwork with a single click.
  - **Multi-Criteria Sorting:** Sort by Newest (default), Oldest, Popularity (views + favorites), and Technical Quality score.
  - **Zero-Duplicate Revisit Guarantee:** Revisiting any historical artwork seamlessly transitions it to the screen via `POST /api/history/revisit` without inserting new rows into `wallpaper_lifecycle`, incrementing display counters, or breaking the global zero-repeat guarantee. Logs a positive revisit interaction in `preference_scores` for personalization taste learning.
  - **Direct Favoriting & External Source:** Add/remove any historical artwork to favorites directly from its card and open original source links on Wallhaven (`https://wallhaven.cc/w/<id>`).
  - **Metadata Export:** Download complete filtered history metadata with one click in both structured JSON format and RFC 4180 CSV format (`GET /api/history/export?format=json|csv`).
- **Resilient Multi-Provider Anime Artwork Failover:**
  - **Three-Tiered Provider Hierarchy:**
    - **Primary Provider (Wallhaven):** Rich tag curation and community metadata querying `https://wallhaven.cc/api/v1/search` with mandatory `purity=100` (strict SFW).
    - **Secondary Booru Provider (Safebooru):** High-availability SFW booru querying `https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1` with query tags `-rating:questionable -rating:explicit` and post-fetch verification (`rating in ('general', 'safe', 'g')`).
    - **Secondary Hi-Res Provider (Konachan.net):** High-resolution desktop wallpapers querying strictly `https://konachan.net/post.json` (never .com) with mandatory `rating:s` tag and client-side rating verification (`rating in ('s', 'safe')`).
  - **Common Normalized Wallpaper Interface (`NormalizedWallpaper`):** Standardizes all provider payloads into a unified metadata structure (`id`, `provider`, `url`, `thumbnail_url`, `resolution`, `dimension_x`, `dimension_y`, `aspect_ratio`, `file_size`, `anime`, `character`, `tags`, `purity`, `views`, `favorites`, `uploader`, `upload_date`, `source_url`).
  - **Circuit Breaker Pattern (`CircuitBreaker`):**
    - `CLOSED`: Normal operation; calls proceed with per-provider rate intervals (Wallhaven: 1.3s, Safebooru: 1.2s, Konachan: 1.5s).
    - `OPEN`: Tripped upon reaching failure threshold (3 consecutive errors) or on HTTP 429 rate limits; fails calls immediately without hammering remote APIs for a 60s cooldown with exponential backoff.
    - `HALF_OPEN`: Cooldown elapsed; allows a single probe trial request. Resets to `CLOSED` on success or re-trips to `OPEN` on failure.
  - **Automatic Seamless Failover:** Automatically switches from Wallhaven to Safebooru to Konachan when a provider is rate-limited, unavailable, or exhausts search results for a given query, logging all transitions.
  - **Global Deduplication Invariant:** All providers feed into the single `wallpaper_lifecycle` table in SQLite WAL (`UNSEEN -> RESERVED -> DISPLAYED`). ID prefixes (`sb_<id>`, `kc_<id>`) and URL deduplication guarantee zero duplicate entries regardless of which provider discovered the art.
  - **Filter Preservation:** Preserves franchise allowlist mapping, orientation constraints (landscape, ultrawide, portrait), minimum resolution ($\ge 1920\times 1080$), and pre-queue quality scoring across all providers.
  - **Never Weakened SFW Policy:** SFW enforcement is hard-coded at both the API query level and the client-side validation level; questionable and explicit content is strictly rejected.
  - **Provenance Transparency:** The Artwork Information panel (<kbd>I</kbd>) displays the real source provider (`Wallhaven`, `Safebooru`, `Konachan`) and links directly to that provider's original post.
  - **Provider Management & Diagnostics:**
    - Live health badges and toggles in the Control Center under Wallpaper/Providers.
    - Diagnostic metrics and active provider status in the Performance Diagnostics panel (<kbd>D</kbd>).
    - REST endpoints: `GET /api/providers`, `POST /api/providers/toggle`, `POST /api/providers/priority`, `POST /api/providers/reset-circuits`.
- **Verified Franchise Tag Intelligence System:**
  - **100% Live-Verified Tag IDs:** Every anime franchise is mapped to verified Wallhaven numeric tag IDs (`id:<tag_id>`) discovered directly from official Wallhaven API tag endpoints (`https://wallhaven.cc/api/v1/tag/{id}`) rather than fragile synthetic guessing:
    - *Bleach:* Series `id:1405`, Character `id:1570` (Ichigo Kurosaki)
    - *One Piece:* Series `id:1394`, Characters `id:1550` (Monkey D. Luffy), `id:1551` (Roronoa Zoro)
    - *Jujutsu Kaisen:* Series `id:108966`, Character `id:109009` (Satoru Gojo)
    - *Demon Slayer:* Series `id:84088` (Kimetsu no Yaiba), Characters `id:89202` (Kyojuro Rengoku), `id:145609` (Akaza)
    - *Attack on Titan:* Series `id:140` (Shingeki no Kyojin), Characters `id:4386` (Levi Ackerman), `id:139326` (Zeke Yeager)
    - *Solo Leveling:* Series `id:91996`, Character `id:91997` (Sung Jin-woo)
    - *Chainsaw Man:* Series `id:98223`, Character `id:102138` (Reze)
    - *Cyberpunk: Edgerunners:* Series `id:167190`, Character `id:136622` (Lucyna Kushinada)
    - *Neon Genesis Evangelion:* Series `id:781`, Characters `id:2342` (Rei Ayanami), `id:749` (Asuka), `id:3120` (Kaworu)
    - *Naruto:* Series `id:541`, Characters `id:1188` (Naruto Uzumaki), `id:1568` (Sasuke), `id:4312` (Sakura)
    - *Dragon Ball:* Series `id:1898`, Character `id:17286` (Son Goku)
    - *Death Note:* Series `id:5989`, Character `id:9525` (Light Yagami)
    - *Hunter x Hunter:* Series `id:6051`, Character `id:17609` (Chrollo Lucifer)
    - *Frieren:* Series `id:117482`, Character `id:148110` (Frieren)
    - *My Hero Academia:* Series `id:36796`, Character `id:45465` (Katsuki Bakugo)
    - *Vinland Saga:* Series `id:90014`, Character `id:90018` (Thorfinn)
    - *Black Clover:* Series `id:71091`, Character `id:183964` (Megicula)
    - *Fate Series:* Series `id:878` / `id:81992`, Character `id:705` (Saber)
  - **Multi-Strategy Query Execution:**
    - *Strategy A (`verified_tag_id`):* Numeric tag search `q=id:<tag_id>` ensuring exact official classification.
    - *Strategy B (`franchise_keyword`):* Exact phrase matching `q="<title>"` with negative keywords.
    - *Strategy C (`character_tag_id`):* Direct character numeric tag search `q=id:<char_tag_id>`.
    - *Strategy D (`alias_keyword` / `character_keyword`):* English, Japanese romanized, and alternative character names.
  - **Strict Deduplication & Provenance Recording:** All candidates across query strategies are deduplicated by ID, tagging each artwork with its originating `query_strategy` in `wallpaper_lifecycle` and displaying the strategy badge in the Artwork Info modal (<kbd>I</kbd>).
  - **Ambiguity Guard Exclusions:**
    - Prevents ambiguous keywords and homonyms from polluting search results:
      - *One Piece:* Excludes tag `id:243` (`swimsuit`), `monokini`, `bikini`, and `swimwear`.
      - *Bleach:* Excludes `cleaning`, `detergent`, `laundry`, `wash`, and `soap`.
      - *Death Note:* Excludes `notebook`, `paper note`, and `stationery`.
      - *Chainsaw Man:* Excludes `chainsaw carving`, `power tool`, and `lumberjack`.
      - *Black Clover:* Excludes `four-leaf clover`, `shamrock`, and `clover field`.
  - **Administrative Catalog Management Without Code Changes:**
    - Stored in persistent `franchise_catalog.json` and mirrored in SQLite table `franchise_catalog`.
    - Interactive "Franchise Tag Intelligence" card in the Control Center (<kbd>S</kbd>) under Wallpaper tab.
    - Live tag verification tool contacting `https://wallhaven.cc/api/v1/tag/{id}` directly with instant validation pills and local caching in `verified_tag_cache`.
    - REST endpoints: `GET /api/franchises/catalog`, `POST /api/franchises/catalog/update`, `POST /api/franchises/catalog/verify-tag`, `POST /api/franchises/catalog/reset`, `GET /api/franchises/tags/cached`.
  - **Graceful Error Fallback:** Automatically degrades to keyword search if a tag query is unavailable or times out, followed by secondary Booru failover.

---

### 🛡️ Unified Artwork Safety and Moderation Layer (Migration v15)
- **Strict Application-Wide SFW Policy:** Only verified safe-for-work (SFW) anime artwork is eligible for automatic display across all upstream sources. Safety strictly takes precedence over wallpaper availability; if no verified safe artwork exists, the system gracefully falls back to local curated procedural offline artwork.
- **Provider-Independent Rating Translation:** Normalizes disparate purity rating schemas into a single internal standard (`SAFE`, `QUESTIONABLE`, `EXPLICIT`, `AMBIGUOUS`, `BLOCKED`):
  - *Wallhaven:* `sfw` (100) ➔ `SAFE`, `sketchy` (010) ➔ `QUESTIONABLE`, `nsfw` (001) ➔ `EXPLICIT`.
  - *Safebooru / Konachan:* `g`/`general`/`s`/`safe`/`sfw` ➔ `SAFE`, `q`/`questionable` ➔ `QUESTIONABLE`, `e`/`explicit` ➔ `EXPLICIT`.
- **Query Deception Rejection:** Never trusts API query parameters alone as proof of safety. Every candidate's tags are independently inspected against strict explicit and suggestive denylists. Rejects artwork with missing, ambiguous, or insufficient tags by default.
- **User Blocklist & One-Click Reporting (<kbd>R</kbd>):**
  - Allows users to report and permanently hide inappropriate artwork directly from the HUD or Artwork Info Panel (<kbd>I</kbd>).
  - Supports blocking specific tags, characters, franchises, and artists.
  - Cascades instantly to running slideshows and disk caches.
- **Manual Review Queue:**
  - Ambiguous or borderline artwork is safely isolated in `wallpaper_review_queue`.
  - Users can inspect thumbnail previews, tags, and failure reasons in the Control Center under the **Moderation** tab, with one-click Approve / Reject actions.
- **Pre-Display Cache Revalidation:**
  - Before any cached or reserved wallpaper transitions to the screen, it is re-evaluated against current blocklists and policy rules. Recently blocked entities immediately evict matching cached files and trigger fallback.
- **REST Endpoints:**
  - `GET /api/moderation/blocked` / `POST /api/moderation/block` / `POST /api/moderation/unblock`
  - `POST /api/moderation/report`
  - `GET /api/moderation/review-queue` / `POST /api/moderation/review-action`
  - `GET /api/moderation/settings` / `POST /api/moderation/settings`

---

### 📡 Wallhaven API Compatibility & Contract Test Suite (Migration v16)
- **13 Parameter Audit Suite:** Strictly audits every Wallhaven API assumption currently used by the application (`categories`, `purity`, `sorting`, `order`, `page`, `seed`, `ratios`, `atleast`, `q`, `id:`, API key auth, anonymous pagination, and rate-limit HTTP 429 parsing).
- **Separated Mocked vs Opt-In Live Tests:**
  - Standard offline tests execute via Python standard library `unittest` in $<0.3$s with zero network dependencies (`python -m unittest test_wallhaven_compatibility.py`).
  - Live integration tests are strictly opt-in (`$env:KURO_WALLHAVEN_LIVE_TESTS="1"`), preventing accidental quota consumption on startup or normal runs.
- **Dimensional & Ratio Integrity:** Validates that landscape (`16x9`, `16x10`), ultrawide (`21x9`), and portrait (`9x16`, `10x16`) queries deliver actual matching pixel dimensions before display.
- **Inviolable Purity Safety Invariant:** Never relaxes or drops `purity` or `categories` filtering when an API parameter is rejected. If safety parameters are compromised, the engine marks the provider `INCOMPATIBLE_SAFETY_VIOLATION` and fails closed to secondary Booru providers or offline curated SVG.
- **Resilient Parameter Degradation:** Non-critical parameters (e.g. `seed` or `sorting=favorites`) automatically degrade or substitute safe defaults without crashing the slideshow.
- **Schema & Diagnostic Persistence:** Persists compatibility status, verified parameters, and diagnostics to SQLite table `wallhaven_compatibility_status` (`Migration v16`).
- **REST Endpoints:**
  - `GET /api/diagnostics/wallhaven-compatibility` — Returns current compatibility state, schema version, verified parameters, and diagnostics.
  - `POST /api/diagnostics/wallhaven-compatibility/run` — Executes on-demand compatibility re-evaluation (`live: false` by default, `live: true` when opted in).
- **Comprehensive Documentation:** Full contract specification and taxonomy in [`WALLHAVEN_API_CONTRACT.md`](file:///C:/Users/ankit/.gemini/antigravity/scratch/anime-screensaver/WALLHAVEN_API_CONTRACT.md).

---

## 🚀 One-Click Windows Launch

### 1. Interactive Fullscreen (Recommended)
Double-click:
```cmd
start_screensaver.bat
```
Automatically verifies single-instance locking, starts the Python backend, detects installed Chromium browsers (Chrome, Edge, Brave), and launches the screensaver in kiosk mode on the target monitor.

### 2. Silent Background Mode (No Console Window)
Double-click:
```cmd
start_silent.vbs
```
Launches silently via VBScript without displaying command prompt windows.

### 3. Graceful Exit
- Click the power button (`⏻`) in the bottom-right HUD controls.
- Press <kbd>Ctrl+Q</kbd> anywhere on screen.
- Or double-click `stop_screensaver.bat` (or execute `python launcher.py stop`).

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| <kbd>Space</kbd> | Pause / Resume slideshow timer |
| <kbd>→</kbd> | Skip to next fresh wallpaper |
| <kbd>←</kbd> | Return to previous wallpaper in session |
| <kbd>M</kbd> | Cycle Display Modes (*Ambient* ➔ *Cinematic* ➔ *Dashboard*) |
| <kbd>F</kbd> or <kbd>F11</kbd> | Toggle Fullscreen / Kiosk mode |
| <kbd>H</kbd> | Toggle HUD Visibility (Instant Zen mode) |
| <kbd>D</kbd> | Toggle Performance Diagnostics & Adaptive Rendering Panel |
| <kbd>I</kbd> | Toggle Interactive Artwork Information Panel |
| <kbd>O</kbd> | Open Composition & Framing modal (or Open Original Source if Info Panel open) |
| <kbd>V</kbd> | View Artwork in Original 1:1 Resolution (in Info Panel) |
| <kbd>A</kbd> | Toggle Ambient Soundscape Mute / Unmute |
| <kbd>[</kbd> | Decrease Soundscape Volume (-5%) |
| <kbd>]</kbd> | Increase Soundscape Volume (+5%) |
| <kbd>N</kbd> | Next Soundscape Track (with equal-power crossfade) |
| <kbd>P</kbd> | Previous Soundscape Track (with equal-power crossfade) |
| <kbd>Y</kbd> | Open Visual Wallpaper History Explorer (or click 📜 in HUD) |
| <kbd>L</kbd> | Save current artwork to Favorites |
| <kbd>B</kbd> | Blacklist current artwork (permanently excludes from rotation) |
| <kbd>R</kbd> | Report current artwork (blocks artwork & instantly evicts from cache) |
| <kbd>X</kbd> | Toggle Curated Offline Collection mode |
| <kbd>C</kbd> | Open Collection Management modal (or Copy URL if Info Panel open) |
| <kbd>S</kbd> | Open Preferences & Settings modal |
| <kbd>Ctrl+Q</kbd> | Gracefully shut down screensaver and exit |

---

## 📁 Architecture & File Layout

```
anime-screensaver/
├── index.html                  # Semantic, accessible HTML5 screensaver interface
├── styles.css                  # Dark anime theme (#05070a), glassmorphic panels & animations
├── app.js                      # Framework-free frontend controller (transitions, weather, OLED, UI)
├── launcher.py                 # Windows multi-monitor detection, browser launch & startup manager
├── server.py                   # Thread-safe standard library HTTP server with REST API v1
├── database.py                 # SQLite WAL transaction manager, lifecycle engine & migrations
├── engine.py                   # 3-layer candidate retrieval, rate limiting & prefetch queues
├── providers.py                # Multi-provider anime artwork failover engine (Wallhaven, Safebooru, Konachan)
├── quality_scorer.py           # Intelligent artwork quality scoring engine (technical & popularity)
├── recommendation_engine.py    # Intelligent personalization, weighted sampling & diversity guard
├── performance_tracker.py      # Performance monitoring & metrics aggregation (latencies, failures, workers)
├── cache_manager.py            # Bounded LRU wallpaper disk cache manager with hit rate tracking
├── favorites_downloader.py     # Resilient chunked background downloader for favorites
├── security.py                 # SSRF validator, origin checks, session tokens & sanitization
├── monitor_detector.py         # Native Windows display topology and resolution detector
├── franchise_registry.py       # Curated registry of verified popular anime franchises & tags
├── generate_curated.py         # Curated Level 3 offline wallpaper collection generator
├── soundscape_generator.py     # Procedural audio generator (WAV synthesis using wave & struct)
├── soundscape_manager.py       # Local soundscape catalog scanner & path traversal guard
├── backup_manager.py           # Complete backup, recovery & integrity manager (SQLite backup API)
├── MIGRATIONS.md               # Formal database schema versioning & migration specification (v1–v13)
│
├── start_screensaver.bat       # One-click Windows batch launcher
├── start_silent.vbs            # Silent VBScript launcher without console windows
├── stop_screensaver.bat        # Clean process shutdown script
├── launcher_config.json        # User preferences (monitor, browser, startup, display mode)
├── kuro_database.db            # Persistent SQLite database in WAL mode
│
├── curated_wallpapers/         # Level 3 offline fallback wallpapers
├── favorites/                  # User saved high-resolution wallpapers
├── .cache/wallpapers/          # Level 2 downloaded wallpaper cache
├── soundscapes/                # Local ambient soundscapes (8 procedural nature WAVs + custom audio)
├── backups/                    # Versioned backup archives and automatic pre-migration/restore snapshots
│
├── qa_audit_scenarios.py       # 24-scenario end-to-end senior QA audit suite
├── test_multi_provider.py      # Multi-provider failover, circuit breakers, SFW validation & deduplication
├── test_performance_and_adaptive.py # Performance monitoring, cache hit rate, SQLite latency & adaptive profiles
├── test_backup_and_recovery.py # Backup, restoration, pre-migration & integrity API tests
├── test_control_center.py      # Control center 6-section schema, validation, export/import & reset tests
├── test_artwork_info_and_composition.py # Artwork info panel, composition & focal-point API tests
├── test_soundscapes.py         # Ambient soundscape generation, catalog & API integration tests
├── test_scheduler.py           # Slideshow scheduling, timing strategies & pause resume tests
├── test_quality_scoring.py     # Artwork quality scoring, resolution, aspect ratio & popularity tests
├── test_sqlite_reliability_stress.py # SQLite concurrency stress, WAL truncation, rollback & reliability tests
├── test_wallhaven_compatibility.py # Wallhaven API contract, schema audit & fail-safe tests
├── test_safety_and_moderation.py # Artwork safety classification, review queue & moderation tests
├── test_franchise_intelligence.py # Franchise catalog, verified tag ID & query strategy tests
├── test_multi_provider.py         # Multi-provider failover, circuit breakers & normalization tests
├── test_performance_and_adaptive.py # Performance monitor, memory, FPS & adaptive quality tests
├── test_artwork_info_and_composition.py # Interactive artwork info overlay (I) & visual composition tests
├── test_control_center.py         # Anime Ambient Control Center (6 sections) settings tests
├── test_backup_and_recovery.py    # Backup & Recovery manager, SQLite backup API & restore tests
├── test_recommendations.py     # Recommendation engine, scoring & diversity guard tests
├── test_history_explorer.py    # Visual wallpaper history, search/filter, CSV/JSON export & revisit tests
├── test_lifecycle.py           # Lifecycle state machine & concurrency unit tests
├── test_security_and_api.py    # Security, SSRF, CORS & API versioning tests
├── test_collection_management.py # Collections, favorites, blacklist & statistics tests
└── test_windows_integration.py # Multi-monitor, registry & Windows startup integration tests
```

---

## 🛡️ SQLite Concurrency & Long-Running Reliability

The Kuro database engine (`database.py`) is engineered for mission-critical reliability under long-running execution:

* **WAL Initialization & PRAGMA Tuning:** Every database connection executes under `PRAGMA journal_mode = WAL;`, `PRAGMA busy_timeout = 10000;`, `PRAGMA synchronous = NORMAL;`, `PRAGMA foreign_keys = ON;`, `PRAGMA temp_store = MEMORY;`, and `PRAGMA cache_size = -64000;` (~64MB in-memory cache).
* **Write Serialization Strategy:** All mutating operations route through the unified `write_transaction()` context manager. It serializes writers at the process level via re-entrant locking (`RLock`) while executing `BEGIN IMMEDIATE` to prevent read-to-write lock escalation deadlocks in SQLite.
* **Locked & Busy Contention Recovery:** Automatic retry loop with exponential backoff and random jitter (`backoff_base * (2^attempt) + jitter`) gracefully recovers from transient lock contention events.
* **Atomic Rollback Guarantee:** Any unhandled exception within a write transaction immediately executes `ROLLBACK`, guaranteeing zero partial records and incrementing the rollback metric.
* **Shutdown Draining & WAL Truncation:** On application shutdown, `close_and_checkpoint(timeout=4.0)` rejects new write transactions, drains in-flight connections, acquires the write lock, and executes `PRAGMA wal_checkpoint(TRUNCATE);` to merge all journaled pages into the primary `.db` file and truncate the `-wal` file to 0 bytes.
* **Deep Integrity Diagnostics:** The `diagnose_database_integrity()` engine executes `PRAGMA quick_check;`, `PRAGMA integrity_check(100);`, `PRAGMA foreign_key_check;`, and passive WAL page censuses, returning structured diagnostic reports and actionable remediation recommendations via `/api/database/integrity`.

---

## 🧪 Comprehensive Quality Assurance

The application includes automated test suites covering end-to-end integration, performance benchmarks, and unit test verification:

### 1. Running the 28 End-to-End QA Audit Scenarios
Tests all 28 production scenarios (fresh installation, timeouts, rate limiting, network disconnect/reconnect, SQLite corruption recovery, memory leaks, 4K/Ultrawide topologies, multi-provider failover, franchise intelligence, safety moderation, Wallhaven contract integrity, and SQLite concurrency stress):
```cmd
python qa_audit_scenarios.py
```

### 2. Running All 220 Unit, Integration & Stress Tests across 16 Test Suites
```cmd
python -m unittest discover -s . -p "test_*.py"
```
Or targeted execution:
```cmd
python -m unittest test_sqlite_reliability_stress.py
python -m unittest test_wallhaven_compatibility.py
```

### 3. Checking Server & Monitor Status
```cmd
python launcher.py status
```

---

## ⚙️ Configuration & Customization

All preferences persist locally across reboots in `launcher_config.json` and `kuro_database.db`:

* **Target Monitor:** Choose which physical display to launch on via the Settings dialog (<kbd>S</kbd>) or CLI flag (`python launcher.py start --monitor secondary`).
* **Browser Selection:** Automatically detects Chrome, Edge, and Brave; custom browser executable paths can be set in Preferences.
* **Windows Autostart:** Enable automatic startup on Windows boot with `python launcher.py startup enable` or the in-app toggle.
* **Wallpaper Timing:** Configurable slideshow interval (10s to 10m) and transition styles (Ken Burns pan/zoom, crossfade, cinematic fade, or minimal instant).
* **Weather & Clock:** Open-Meteo live weather with auto-IP geolocation or manual city override; 12h/24h digital clock formats.
