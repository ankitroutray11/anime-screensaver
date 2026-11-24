# Wallhaven API v1 Compatibility & Contract Specification

**Module:** `wallhaven_compatibility.py`  
**Test Suite:** [`test_wallhaven_compatibility.py`](file:///C:/Users/ankit/.gemini/antigravity/scratch/anime-screensaver/test_wallhaven_compatibility.py)  
**Schema Version:** `v1`  
**Target API:** `https://wallhaven.cc/api/v1`  
**Last Verified:** November 2026  

---

## 1. Executive Overview

The Kuro Anime Ambient Screensaver relies on the Wallhaven REST API as its primary live artwork discovery provider. To ensure continuous operational resilience, strict SFW content guarantees, and zero-crash tolerance against upstream API schema drift or parameter deprecation, this document establishes the formal contract, parameter behavioral classifications, and failure degradation guidelines.

---

## 2. Behavioral Verification Taxonomy

Every Wallhaven API parameter and assumption in Kuro is audited and classified into one of three verification tiers:

| Status | Definition | Operational Handling in Kuro |
| :--- | :--- | :--- |
| **OFFICIALLY_VERIFIED** | Formally documented by Wallhaven API v1 and empirically verified via contract test suite. | Active by default in all primary search query plans. |
| **EXPERIMENTALLY_VERIFIED** | Not formally specified in API docs or depends on empirical observations, but proven stable via live probing and test fixtures. | Active with automated schema validation and parameter fallback guards. |
| **UNCERTAIN** | Undocumented edge cases, account-specific features, or behavior subject to silent upstream modification. | Gated behind diagnostic logging; safely ignored or substituted if server returns unexpected payloads. |

---

## 3. Comprehensive Parameter Audit Matrix

| Parameter | Syntax / Format | Verification Status | Observed & Expected Behavior | Degradation / Fail-Safe Strategy |
| :--- | :--- | :---: | :--- | :--- |
| `categories` | 3-digit bitmask<br>`010` (Anime only) | **OFFICIALLY_VERIFIED** | Bitmask format: `General` (100), `Anime` (010), `People` (001). Kuro strictly passes `010`. Returned objects have `category: "anime"`. | **SAFETY INVARIANT:** Never relax or omit. If rejected or violated, fail closed to secondary providers. |
| `purity` | 3-digit bitmask<br>`100` (SFW only) | **OFFICIALLY_VERIFIED** | Bitmask format: `SFW` (100), `Sketchy` (010), `NSFW` (001). Kuro strictly enforces `100`. Returned objects have `purity: "sfw"`. Passing `001` or `111` without API key returns HTTP 401. | **SAFETY INVARIANT:** Inviolable. If purity parameter fails, mark `INCOMPATIBLE_SAFETY_VIOLATION` and disable Wallhaven provider. |
| `sorting` | String enum:<br>`favorites`, `toplist`, `date_added`, `relevance`, `random`, `views` | **OFFICIALLY_VERIFIED** | Sorts response array by selected criterion. Kuro uses `favorites` (default) and `relevance` for keyword searches. | If `favorites` degraded, substitute with `date_added` or `relevance` automatically. |
| `order` | `desc` or `asc` | **OFFICIALLY_VERIFIED** | Default is `desc` (highest favorites / newest first). Kuro explicitly requests `desc` or relies on default. | If order parameter ignored, accept default descending order without failing. |
| `page` | Integer $\ge 1$ | **OFFICIALLY_VERIFIED** | 1-based pagination. Response `meta.current_page` mirrors requested page; `meta.per_page` is 24. Out of bounds returns empty `data: []`. | If page exceeds `last_page`, mark search key as exhausted in engine. |
| `seed` | 6-char alphanumeric<br>`[a-zA-Z0-9]{6}` | **EXPERIMENTALLY_VERIFIED** | Used exclusively when `sorting=random`. Guarantees deterministic, non-repeating pagination order across consecutive page requests. | If seed rejected or unsupported, omit seed and allow random reshuffle. |
| `ratios` | Comma-separated ratios:<br>`16x9,16x10`, `9x16,10x16`, `21x9,32x9` | **OFFICIALLY_VERIFIED** | Server-side aspect ratio filter. Landscape: width > height (ratio $\ge 1.33$). Portrait: height > width (ratio $\le 0.75$). Ultrawide: ratio $\ge 2.2$. | If server returns mismatched ratio, client-side composition engine dynamically frames or blurs backdrop. |
| `atleast` | `WIDTHxHEIGHT`<br>(e.g. `1920x1080`, `3840x2160`) | **OFFICIALLY_VERIFIED** | Filters images having both dimensions $\ge$ specified values. Kuro uses `1920x1080` to exclude low-resolution assets. | If `atleast` ignored on small tags, Kuro local quality scoring filters low-res assets pre-reservation. |
| `q` | URL-encoded string:<br>keywords, phrases, exclusions | **OFFICIALLY_VERIFIED** | Supports exact phrase quoting (`"Demon Slayer"`), tag matching (`+anime`), and negative term exclusions (`-original -cosplay`). | If complex query fails, degrade to single exact phrase or tag ID. |
| `id:` | `id:<numeric_tag_id>`<br>(e.g. `id:84088`, `id:1405`) | **OFFICIALLY_VERIFIED** | Wallhaven search syntax for numeric tag IDs. Prevents false positive keyword matches and resolves franchise aliases. | If numeric tag search returns 0 results, fall back to keyword strategy. |
| `apikey` / `X-API-Key` | String (32-char alphanumeric) | **OFFICIALLY_VERIFIED** | Authenticated requests accept header `X-API-Key: <key>` or query parameter `apikey=<key>`. Expands rate limits from 20 to 45 req/min. | If user API key is invalid (HTTP 401), fall back to anonymous SFW mode and notify user. |
| Anonymous Pagination | Implicit limit | **EXPERIMENTALLY_VERIFIED** | Anonymous sessions are rate-limited or depth-capped (typically page 100 max) compared to authenticated sessions. | Local deduplication and SQLite lifecycle tracking ensure unseen wallpapers are reserved without deep pagination. |
| Rate-Limit Headers (429) | HTTP 429 status code + headers | **OFFICIALLY_VERIFIED** | Wallhaven returns HTTP 429 when quota exceeded. Standard headers: `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`. | Circuit breaker transitions to `OPEN`, parses `Retry-After` (or defaults to 20s), and engages secondary Booru failover. |

---

## 4. Safety Invariants & Fail-Closed Protocol

> [!IMPORTANT]
> **The Principle of Inviolable Purity:**  
> The application content policy mandates that **only SFW anime artwork** may be displayed. Under no circumstances will the application relax, ignore, or strip `purity=100` or `categories=010` to satisfy an image request.

1. **Failure Containment:** If Wallhaven API alters the syntax of `purity` (e.g., rejecting `purity=100` with HTTP 400), the compatibility manager immediately marks Wallhaven status as `INCOMPATIBLE_SAFETY_VIOLATION`.
2. **Immediate Failover:** Wallhaven is temporarily quarantined, and the multi-provider engine switches immediately to Safebooru or Konachan (enforcing independent SFW translation).
3. **Offline Fallback Guarantee:** If all upstream providers are compromised or unreachable, the screensaver displays verified procedural offline SVG artwork (`curated_wallpapers/`).

---

## 5. Response Contract Specifications

### 5.1 Search Endpoint (`/api/v1/search`)

```json
{
  "data": [
    {
      "id": "9m9wkd",
      "url": "https://wallhaven.cc/w/9m9wkd",
      "short_url": "https://whvn.cc/9m9wkd",
      "views": 15420,
      "favorites": 845,
      "source": "https://pixiv.net/artworks/...",
      "purity": "sfw",
      "category": "anime",
      "dimension_x": 3840,
      "dimension_y": 2160,
      "resolution": "3840x2160",
      "ratio": "1.78",
      "file_size": 4512030,
      "file_type": "image/jpeg",
      "created_at": "2024-05-10 14:22:01",
      "colors": ["#000000", "#ffffff", "#4285f4"],
      "path": "https://w.wallhaven.cc/full/9m/wallhaven-9m9wkd.jpg",
      "thumbs": {
        "large": "https://th.wallhaven.cc/lg/9m/9m9wkd.jpg",
        "original": "https://th.wallhaven.cc/orig/9m/9m9wkd.jpg",
        "small": "https://th.wallhaven.cc/small/9m/9m9wkd.jpg"
      }
    }
  ],
  "meta": {
    "current_page": 1,
    "last_page": 42,
    "per_page": 24,
    "total": 1008,
    "query": "id:84088 -original -cosplay",
    "seed": null
  }
}
```

### 5.2 Tag Endpoint (`/api/v1/tag/{id}`)

```json
{
  "data": {
    "id": 84088,
    "name": "Kimetsu no Yaiba",
    "alias": ["Demon Slayer", "Blade of Demon Destruction"],
    "category_id": 1,
    "category": "Anime",
    "purity": "sfw",
    "created_at": "2019-04-06 14:00:00"
  }
}
```

---

## 6. Compatibility & Diagnostic Tooling

- **Offline Mock Contract Tests:**
  ```powershell
  python -m unittest test_wallhaven_compatibility.py
  ```
  Executes all 17 parameter mock audits in $<0.3$s with zero network dependencies.

- **Opt-In Live Contract Probes:**
  ```powershell
  $env:KURO_WALLHAVEN_LIVE_TESTS="1"; python -m unittest test_wallhaven_compatibility.TestWallhavenLiveContract
  ```
  Performs throttled, non-destructive live validation against live endpoints.

- **REST Diagnostics Endpoints:**
  - `GET /api/diagnostics/wallhaven-compatibility` — Inspects the latest audited contract status, verified parameters, and diagnostic warnings.
  - `POST /api/diagnostics/wallhaven-compatibility/run` — Triggers an on-demand contract re-evaluation (`live: false` by default, or `live: true` when explicitly opted in).
