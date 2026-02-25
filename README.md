# 🎧 Apple Music DJ

An OpenClaw skill that turns your AI assistant into a personalized Apple Music curator. Analyzes
your listening history (including Replay stats), understands your taste DNA, and creates smart
playlists directly in your Apple Music library.

## Features

- **Taste DNA Analysis** — Profiles your listening from recently played, heavy rotation, library,
  ratings, recommendations, and Apple Music Replay annual stats
- **4 Playlist Strategies:**
  - **Deep Cuts** — Hidden gems from artists you already love
  - **Mood/Activity** — Playlists for any vibe, filtered through your taste
  - **Trend Radar** — What's charting, filtered for what you'd actually like
  - **Constellation Discovery** — Gradually expands from familiar artists into new territory
- **Playlist Refresh** — Evolve existing playlists by swapping stale tracks for fresh ones
- **Cron Auto-Playlists** — Weekly discovery, trending, or workout refresh on a schedule
- **Direct Integration** — Playlists appear instantly in Apple Music on all your devices

## Quick Start

### 1. Install

```bash
clawhub install apple-music-dj
# Or paste the repo URL into your OpenClaw chat
```

### 2. Authenticate

You need an Apple Developer account and two tokens. The skill walks you through setup.

```bash
export APPLE_MUSIC_DEV_TOKEN="your_jwt_here"
export APPLE_MUSIC_USER_TOKEN="your_user_token_here"
scripts/apple_music_api.sh verify
```

### 3. Use It

Talk naturally:
- "Analyze my Apple Music taste"
- "Make me a workout playlist"
- "Find deep cuts from my favorite artists"
- "What's trending that I'd actually like?"
- "Surprise me with something new"
- "Refresh my focus playlist"
- "Set up a weekly discovery playlist every Monday"

## File Structure

```
apple-music-dj/
├── SKILL.md                           # Skill definition (triggers, workflows, phases)
├── README.md                          # This file
├── references/
│   ├── auth-setup.md                  # Token setup walkthrough
│   ├── api-reference.md               # Apple Music API endpoint reference
│   └── playlist-strategies.md         # Deep playbook for all 4 strategies
└── scripts/
    ├── apple_music_api.sh             # Bash API wrapper (20 commands)
    ├── taste_profiler.py              # Python taste analysis with caching & Replay
    ├── build_playlist.sh              # Playlist creation & refresh
    └── generate_dev_token.py          # JWT generator
```

## Architecture

```
User Request
    │
    ▼
Taste Analysis (Python)
    │  ├─ Recently played (50 tracks)
    │  ├─ Heavy rotation
    │  ├─ Library (songs + artists)
    │  ├─ Ratings (loved / disliked)
    │  ├─ Recommendations
    │  └─ Replay summaries (annual stats)
    │
    ▼
Strategy Selection
    │  ├─ Deep Cuts Explorer
    │  ├─ Mood / Activity Matcher
    │  ├─ Trend Radar
    │  └─ Constellation Discovery
    │
    ▼
Playlist Assembly (sequencing, dedup, quality gates)
    │
    ▼
Apple Music API → POST /v1/me/library/playlists
    │
    ▼
Playlist live on all user's devices
```

## Requirements

- Apple Developer Program ($99/year)
- `curl`, `jq`, `python3` (no pip packages for core — `PyJWT` only for token generation)
- Active Apple Music subscription

## API Limitations

- Recently played: max 50 unique tracks (Apple's hard cap)
- Music User Token expires ~6 months, no refresh flow
- Replay data not available in all regions
- Rate limits undocumented (~20 req/s safe)

## License

MIT
