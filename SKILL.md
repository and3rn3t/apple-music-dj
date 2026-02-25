---
name: apple-music-dj
description: >
  Ultimate personalization engine for Apple Music. Analyzes listening history, Apple Music Replay
  stats, library data, and taste patterns to create intelligent playlists directly in the user's
  Apple Music library via the MusicKit API. Supports deep cuts discovery, mood/activity playlists,
  trend scouting, constellation discovery ("surprise me"), playlist refresh/evolution, and
  automated weekly curation via cron. Use this skill whenever the user mentions Apple Music,
  playlists, music recommendations, listening habits, music taste, "what should I listen to",
  discovering new music, mood playlists, workout playlists, deep cuts, hidden gems, trending music,
  "surprise me", refreshing a playlist, or anything related to curating their music experience.
  Also trigger on: "DJ", "mix", "playlist for", "music for", "songs like", "similar to",
  "what's hot", "new releases for me", or OpenClaw in the context of music.
version: 2.0.0
emoji: 🎧
homepage: https://github.com/yourusername/apple-music-dj
metadata:
  openclaw:
    requires:
      env:
        - APPLE_MUSIC_DEV_TOKEN
        - APPLE_MUSIC_USER_TOKEN
      bins:
        - curl
        - jq
        - python3
    primaryEnv: APPLE_MUSIC_DEV_TOKEN
---

# Apple Music DJ 🎧

An intelligent Apple Music personalization engine for OpenClaw. Reads your listening history,
Replay stats, ratings, and library to build a deep taste profile — then generates playlists
using five strategies and writes them directly to your Apple Music library.

## Architecture

```
User Request
     │
     ▼
┌─────────────┐    ┌──────────────────────────────────────────────┐
│  Taste       │◄──│  Apple Music API (read)                      │
│  Profiler    │    │  · recently played    · library songs/artists│
│  (cached)    │    │  · heavy rotation     · ratings (loved/hated)│
│              │    │  · recommendations    · Replay summaries     │
└──────┬───────┘    └──────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐    ┌──────────────────────────────────────────────┐
│  Strategy    │───▶│  Apple Music API (catalog)                   │
│  Engine      │    │  · search · charts · artist albums/top songs │
│              │    │  · genres · new releases                     │
└──────┬───────┘    └──────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐    ┌──────────────────────────────────────────────┐
│  Playlist    │───▶│  Apple Music API (write)                     │
│  Builder     │    │  · POST /me/library/playlists                │
│              │    │  · POST /me/library/playlists/{id}/tracks     │
└─────────────┘    └──────────────────────────────────────────────┘
```

## Prerequisites

Two environment variables must be set. If the user doesn't have them, walk them through
`references/auth-setup.md` before doing anything else.

| Variable | Purpose |
|---|---|
| `APPLE_MUSIC_DEV_TOKEN` | JWT signed with MusicKit private key (Apple Developer portal) |
| `APPLE_MUSIC_USER_TOKEN` | Per-user authorization token (obtained via MusicKit JS `authorize()`) |

Verify with: `scripts/apple_music_api.sh verify`

## Taste Profiling

Before generating any playlist, build (or load from cache) a taste profile.

Run: `python3 scripts/taste_profiler.py [--force-refresh] [--storefront us]`

The profiler pulls from **all available data sources**:

| Source | Endpoint | Signal |
|---|---|---|
| Loved/disliked songs | `GET /v1/me/ratings/songs` | ★★★★★ Explicit intent |
| Heavy rotation | `GET /v1/me/history/heavy-rotation` | ★★★★☆ Repeated engagement |
| Recently played | `GET /v1/me/recent/played/tracks` | ★★★★☆ Current mood |
| Replay summaries | `GET /v1/me/music-summaries` | ★★★★☆ Annual deep data |
| Library songs | `GET /v1/me/library/songs?include=catalog` | ★★★☆☆ Broad taste |
| Library artists | `GET /v1/me/library/artists` | ★★★☆☆ Artist affinity |
| Recommendations | `GET /v1/me/recommendations` | ★★☆☆☆ Apple's inference |

**Output:** Taste DNA profile cached at `~/.apple-music-dj/taste_profile.json` (24h TTL).

The profile includes: top artists (weighted), genre distribution, era profile, energy
classification, variety score, loved/disliked IDs, library song IDs, and Replay highlights.

### Sparse Data Handling

If the user has limited history:
1. Check Replay data — covers a full year even if recent history is short
2. Lean on `/me/recommendations`
3. Ask user to name 3–5 artists/songs they love as manual seeds
4. Use catalog search with those seeds to bootstrap

## Playlist Strategies

Five strategies. Read detailed algorithms in `references/playlist-strategies.md`.

### Strategy 1: Deep Cuts Explorer
**Triggers:** "deep cuts", "hidden gems", "B-sides", "underrated", "album tracks"
Find tracks from artists the user loves but hasn't heard yet. Excludes top songs, singles,
and anything in library.

### Strategy 2: Mood / Activity Matcher
**Triggers:** "workout", "chill", "focus", "party", "sleep", "cooking", "driving",
"running", "morning", "sad", "study", "dinner" — any mood/activity word.
Maps mood to musical attributes, filters through user's taste.

### Strategy 3: Trend Radar
**Triggers:** "trending", "what's hot", "charts", "popular", "new releases"
Current charts filtered through user's genre preferences. Includes wildcard picks.

### Strategy 4: Constellation Discovery
**Triggers:** "surprise me", "something new", "expand my taste", "I'm bored", "discovery"
Journey from familiar artists outward to new territory in 3 "rings" of distance.

### Strategy 5: Playlist Refresh / Evolution
**Triggers:** "refresh my [playlist]", "update my [playlist]", "evolve", "getting stale"
Analyzes existing playlist's sonic signature, adds fresh matching tracks, optionally
prunes overplayed songs.

## Quick Commands

| User says | Action |
|---|---|
| "Analyze my taste" | Run taste profiler, present Taste DNA report |
| "Make me a playlist" | Ask what kind, then select strategy |
| "Surprise me" | Constellation Discovery — no questions asked |
| "More like [artist]" | Deep Cuts + Constellation hybrid seeded from named artist |
| "Refresh my workout playlist" | Strategy 5 on the named playlist |
| "What have I been into?" | Present recent listening summary |
| "Set up weekly playlists" | Configure cron (see below) |

## Cron / Automated Playlists

OpenClaw has first-class cron and heartbeat support. This skill can automate:

**Weekly Mix** (recommended default):
```
Schedule: Every Sunday at 9:00 AM (user's local time)
Task:
  1. Refresh taste profile cache
  2. Run Trend Radar (15 tracks)
  3. Run Constellation Discovery (10 tracks)
  4. Merge into "Weekly Mix · {date}" playlist
  5. Create in library
  6. Notify user: "🎧 Your weekly mix is ready — 25 fresh tracks"
```

**New Release Watch:**
```
Schedule: Daily at 8:00 AM
Task:
  1. Get user's top 20 artists from profile
  2. Search for releases in the last 24h
  3. If found: notify user with artist + album/single name
```

**Playlist Health Check:**
```
Schedule: Weekly (Saturday)
Task:
  1. Scan user's playlists
  2. Flag any tracks removed from Apple Music catalog (404 on lookup)
  3. Suggest replacements
```

When the user asks to set up automation, configure via OpenClaw's cron system and
confirm the schedule with them before activating.

## Assembly Rules

After any strategy produces candidate tracks, apply before creating:

**Sequencing:**
1. Tracks 1–3: Open strong (high-confidence picks)
2. Tracks 4–8: Build energy, introduce variety
3. Tracks 9–15: Peak — best discoveries here
4. Tracks 16–22: Sustain interest, new textures
5. Tracks 23–28: Wind down
6. Final track: Memorable closer, not filler

**Hard rules:**
- Min 4 tracks between same-artist repeats
- Max 2 tracks from same album
- No tracks from disliked artists
- No explicit content unless user's library already has it
- All IDs must be catalog IDs (not library IDs)
- Target: 25–40 tracks unless user specifies otherwise

**Naming:** `{Strategy} · {Context} · {Mon YYYY}`

## Storefront Detection

Catalog endpoints need a storefront code (us, gb, jp...).
Detection order:
1. `APPLE_MUSIC_STOREFRONT` env var → use it
2. `GET /v1/me/storefront` → auto-detect and cache
3. Fall back to `us`, warn user

## Error Handling

| Code | Meaning | Action |
|---|---|---|
| 401 | Dev token invalid/expired | Regenerate JWT. See `references/auth-setup.md` |
| 403 | User token expired (~6mo) | Re-authorize via browser. No refresh flow exists |
| 404 | Resource removed from catalog | Skip, log warning, continue |
| 429 | Rate limited | Exponential backoff: 1s→2s→4s→8s, max 3 retries |
| Empty data | New user or privacy settings | Fall back: Replay → recs → manual seeds |

## Presenting Results

After creating a playlist:
1. ✅ Confirmation with playlist name
2. Brief explanation connecting the curation to their taste
3. Track listing (# · Song · Artist)
4. Offer refinement: "Want me to adjust the energy, swap tracks, or make it longer?"

**Tone:** Music-savvy friend. Be specific about why tracks were chosen.
Say "I noticed you've been deep into shoegaze lately, so I pulled Slowdive deep cuts and
some bands in that orbit" — not "Here's an awesome playlist just for you!"

## Reference Files

| File | Read when... |
|---|---|
| `references/auth-setup.md` | User needs token setup help |
| `references/api-reference.md` | Need endpoint details, formats, genre IDs |
| `references/playlist-strategies.md` | Before executing any playlist strategy |

## Scripts

| Script | Lang | Purpose |
|---|---|---|
| `scripts/apple_music_api.sh` | Bash | API wrapper — all endpoints, retry logic |
| `scripts/taste_profiler.py` | Python | Taste DNA profiler with caching |
| `scripts/build_playlist.sh` | Bash | Playlist creation & refresh (create or add tracks) |
| `scripts/generate_dev_token.py` | Python | Developer JWT generator |

## Example Interactions

**"I've been in a funk, make me something uplifting"**
→ Strategy 2 (Mood). Target: uplifting energy from their preferred genres.

**"I keep listening to the same 20 songs"**
→ Strategy 4 (Constellation). Start from heavy rotation, expand outward.

**"Make me a running playlist"**
→ Strategy 2 (Activity). 140–180 BPM feel, high energy, filtered through taste.

**"What's trending that I'd actually like?"**
→ Strategy 3 (Trend Radar). Charts filtered through taste fingerprint + wildcards.

**"I love Radiohead and Björk but I've heard everything"**
→ Strategy 1 (Deep Cuts) + Strategy 4 (Constellation) combined.

**"My gym playlist is getting stale"**
→ Strategy 5 (Refresh). Analyze vibe, add fresh tracks, prune overplayed ones.

**"Set me up with weekly auto-playlists"**
→ Cron config. Confirm schedule, set up weekly Trend Radar + Constellation mix.
