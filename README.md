# 🎧 Apple Music DJ

An OpenClaw skill that turns your AI assistant into a personalized Apple Music curator. Analyzes
your listening history (including Replay stats), understands your taste DNA, and creates smart
playlists directly in your Apple Music library.

## Features

- **Taste DNA Analysis** — Profiles your listening from recently played, heavy rotation, library,
  ratings, recommendations, and Apple Music Replay annual stats
- **5 Playlist Strategies:**
  - **Deep Cuts** — Hidden gems from artists you already love
  - **Mood/Activity** — Playlists for any vibe, filtered through your taste
  - **Trend Radar** — What's charting, filtered for what you'd actually like
  - **Constellation Discovery** — Gradually expands from familiar artists into new territory
  - **Playlist Refresh** — Evolve existing playlists by swapping stale tracks for fresh ones
- **Taste DNA Card** — Shareable visual summary of your listener identity and archetype
- **Compatibility Score** — How well does your taste match an artist (or another user)?
- **Listening Insights** — Timeline, streaks, milestones, and deep year-in-review
- **Catalog Gap Analysis** — Find albums you're missing from artists you love
- **Album Deep Dive** — Track-by-track breakdown: singles vs deep cuts, discography context
- **Artist Rabbit Hole** — Chain exploration from one artist outward into new territory
- **Daily Song Drop** — One perfect track per day with a reason why
- **What Should I Listen To Right Now?** — Context-aware instant pick based on time of day
- **Concert Prep** — Top songs + deep cuts playlist for upcoming shows
- **New Release Radar** — Personalized scan of new releases from your artists and genres
- **Cron Auto-Playlists** — Weekly discovery, daily song drops, new release watch on a schedule
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
- "Show me my taste card"
- "Make me a workout playlist"
- "Find deep cuts from my favorite artists"
- "What's trending that I'd actually like?"
- "Surprise me with something new"
- "Refresh my focus playlist"
- "How compatible am I with Tyler, the Creator?"
- "What albums am I missing from Radiohead?"
- "Tell me about In Rainbows"
- "Take me on a rabbit hole from Björk"
- "Give me one song for today"
- "What should I listen to right now?"
- "I'm seeing Phoebe Bridgers next week"
- "Any new releases from my artists?"
- "How was my 2025 in music?"
- "Set up a weekly discovery playlist every Monday"

## File Structure

```
apple-music-dj/
├── SKILL.md                           # Skill definition (triggers, workflows, phases)
├── README.md                          # This file
├── references/
│   ├── auth-setup.md                  # Token setup walkthrough
│   ├── api-reference.md               # Apple Music API endpoint reference
│   ├── playlist-strategies.md         # Deep playbook for all strategies
│   └── troubleshooting.md             # Step-by-step fixes for common issues
└── scripts/
    ├── _common.py                     # Shared Python utilities (API, profile, search)
    ├── apple_music_api.sh             # Bash API wrapper (25+ commands, retry logic)
    ├── taste_profiler.py              # Python taste analysis with caching & Replay
    ├── build_playlist.sh              # Playlist creation & refresh
    ├── generate_dev_token.py          # JWT generator
    ├── taste_card.py                  # Shareable Taste DNA Card (SVG/text)
    ├── compatibility.py               # Taste compatibility scoring
    ├── listening_insights.py          # Timeline, streaks, year in review
    ├── catalog_explorer.py            # Gap analysis, album dive, rabbit hole
    ├── daily_pick.py                  # Daily song drop & instant recommendation
    ├── concert_prep.sh                # Concert prep playlist builder
    ├── new_releases.sh                # Personalized new release radar
    └── verify_setup.sh                # Setup verification checker
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
    ├──────────────────────────────┐
    ▼                              ▼
Strategy Selection            Engagement Features
    │  ├─ Deep Cuts Explorer       ├─ Taste DNA Card
    │  ├─ Mood / Activity          ├─ Compatibility Score
    │  ├─ Trend Radar              ├─ Listening Insights
    │  └─ Constellation Discovery  ├─ Catalog Gap Analysis
    │                              ├─ Album Deep Dive
    │                              ├─ Artist Rabbit Hole
    │                              ├─ Daily Song Drop
    │                              ├─ Concert Prep
    │                              └─ New Release Radar
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

## Setup Verification

After installing, run the setup checker to verify everything is ready:

```bash
scripts/verify_setup.sh
```

This checks: required tools (`curl`, `jq`, `python3`), Python version, environment
variables, script presence, API connectivity, and cache status.

## Requirements

- Apple Developer Program ($99/year)
- `curl`, `jq`, `python3` (3.10+) — no pip packages for core — `PyJWT` only for token generation
- Active Apple Music subscription

## Testing

The project includes 156 unit tests covering all pure logic functions:

```bash
python3 -m pytest tests/ -v
```

Tests cover: taste profiling, archetype detection, compatibility scoring, daily pick
seeding, SVG/text card generation, and shared utilities.

## Privacy

This skill reads your Apple Music listening data (recently played, library, ratings, Replay)
via the official Apple Music API. All data stays on your machine — nothing is sent to
third-party services. The only local cache is `~/.apple-music-dj/taste_profile.json`
(7-day TTL, deletable anytime). Tokens are read from environment variables and never
stored or logged by the skill.

## API Limitations

- Recently played: max 50 unique tracks (Apple's hard cap)
- Music User Token expires ~6 months, no refresh flow
- Replay data not available in all regions
- Rate limits undocumented (~20 req/s safe)

See [references/troubleshooting.md](references/troubleshooting.md) for step-by-step fixes
to common issues.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Author

**Andernet** (Matthew Anderson) — <and3rn3t@icloud.com>

## License

MIT
