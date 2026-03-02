# 🎧 Apple Music DJ

**Your AI-powered Apple Music curator.** Analyzes your listening history, understands your taste DNA, and creates intelligent playlists directly in your Apple Music library — on all your devices.

Built as an [OpenClaw](https://openclaw.dev) skill. Talk naturally, get playlists.

---

## ✨ Features

- **🧬 Taste DNA Profiling** — Deep analysis of your listening from recently played, heavy rotation, library, ratings, recommendations, and Apple Music Replay
- **🎵 5 Playlist Strategies** — Deep cuts, mood/activity, trend radar, constellation discovery, playlist refresh
- **🃏 Taste DNA Card** — Shareable visual summary of your listener identity
- **🎯 Compatibility Scoring** — How well does your taste match an artist (or another listener)?
- **📊 Listening Insights** — Timeline, streaks, milestones, year-in-review
- **🔍 Catalog Gap Analysis** — Find albums you're missing from artists you love
- **💿 Album Deep Dive** — Track-by-track breakdown with context
- **🐇 Artist Rabbit Hole** — Chain exploration from familiar artists into new territory
- **🎧 Daily Song Drop** — One perfect track per day with a reason why
- **⏰ What Should I Listen To Now?** — Context-aware instant picks
- **🎤 Concert Prep** — Setlist-ready playlists for upcoming shows
- **📡 New Release Radar** — Personalized scan of new releases
- **🤖 Cron Auto-Playlists** — Weekly discovery, daily drops, and new release watch on a schedule
- **📱 Direct Integration** — Playlists appear instantly in Apple Music on all your devices

## 📋 Requirements

| Requirement | Details |
|---|---|
| **Apple Developer Account** | [$99/year](https://developer.apple.com/programs/) — needed for MusicKit API access |
| **Apple Music subscription** | Active subscription on your Apple ID |
| **Python** | 3.9+ (no pip packages needed for core features) |
| **OpenClaw** | [openclaw.dev](https://openclaw.dev) |
| **CLI tools** | `curl`, `jq` (usually pre-installed on macOS) |

## 🚀 Quick Install

```bash
# Via ClawhHub (recommended)
clawhub install apple-music-dj

# Or clone directly
git clone https://github.com/and3rn3t/apple-music-dj.git ~/.openclaw/workspace/skills/apple-music-dj
```

## ⚡ 5 Minutes to First Playlist

### 1. Generate your tokens

You need two tokens. The skill walks you through setup — see [`references/auth-setup.md`](references/auth-setup.md) for the full guide.

```bash
# Set your tokens
export APPLE_MUSIC_DEV_TOKEN="your_jwt_here"
export APPLE_MUSIC_USER_TOKEN="your_user_token_here"
```

### 2. Verify setup

```bash
scripts/verify_setup.sh
```

### 3. Talk to your DJ

Open OpenClaw and say:

> "Analyze my Apple Music taste and make me a playlist"

That's it. Your taste profile is built, a playlist is generated, and it appears in Apple Music.

## 🎛️ Available Commands

Just talk naturally. Here's what the DJ understands:

| You say... | What happens |
|---|---|
| "Analyze my taste" | Builds your Taste DNA profile |
| "Show my taste card" | Generates a shareable taste identity card |
| "Make me a workout playlist" | Mood/activity-matched playlist |
| "Find deep cuts from my favorites" | Hidden gems from artists you love |
| "What's trending that I'd like?" | Charts filtered through your taste |
| "Surprise me" | Constellation discovery — familiar → frontier |
| "Refresh my focus playlist" | Evolves an existing playlist with fresh tracks |
| "How compatible am I with Radiohead?" | Taste compatibility score |
| "What albums am I missing from Björk?" | Catalog gap analysis |
| "Tell me about In Rainbows" | Album deep dive |
| "Rabbit hole from Radiohead" | Artist chain exploration |
| "Give me one song for today" | Daily song drop |
| "What should I listen to right now?" | Context-aware instant pick |
| "I'm seeing Phoebe Bridgers next week" | Concert prep playlist |
| "Any new releases for me?" | Personalized new release scan |
| "How was my 2025 in music?" | Year-in-review analysis |
| "Set up weekly playlists" | Cron automation |

## 📁 Project Structure

```
apple-music-dj/
├── SKILL.md                    # Full skill definition (triggers, workflows, phases)
├── README.md                   # This file
├── clawhub.json                # Package metadata
├── pyproject.toml              # Python project config
├── references/
│   ├── auth-setup.md           # Token setup walkthrough
│   ├── api-reference.md        # Apple Music API endpoint reference
│   ├── playlist-strategies.md  # Deep playbook for all 5 strategies
│   └── troubleshooting.md      # Step-by-step fixes for common issues
└── scripts/
    ├── _common.py              # Shared utilities (API, profile, token checks)
    ├── apple_music_api.sh      # Bash API wrapper (25+ commands, retry logic)
    ├── taste_profiler.py       # Taste DNA profiler with caching & Replay
    ├── build_playlist.sh       # Playlist creation & refresh with dedup
    ├── strategy_engine.py      # 5 playlist strategies + sequencing
    ├── taste_card.py           # Shareable Taste DNA Card (SVG/text)
    ├── compatibility.py        # Taste compatibility scoring
    ├── listening_insights.py   # Timeline, streaks, year-in-review
    ├── catalog_explorer.py     # Gap analysis, album dive, rabbit hole
    ├── daily_pick.py           # Daily song drop & instant recommendation
    ├── playlist_history.py     # Playlist creation history tracking
    ├── playlist_health.py      # Playlist health check & maintenance
    ├── concert_prep.sh         # Concert prep playlist builder
    ├── new_releases.sh         # Personalized new release radar
    ├── generate_dev_token.py   # JWT generator (requires PyJWT)
    ├── setup_cron.py           # Cron automation setup
    └── verify_setup.sh         # Setup verification checker
```

## 📸 Screenshots & Examples

> _Coming soon — taste cards, playlist examples, and compatibility scores._

## 🔒 Privacy

All data stays on your machine. The skill reads your Apple Music listening data via the official API and caches it locally at `~/.apple-music-dj/`. Nothing is sent to third-party services. Tokens are read from environment variables and never stored or logged.

## 🧪 Testing

```bash
python3 -m pytest tests/ -v
```

156 unit tests covering taste profiling, archetype detection, compatibility scoring, card generation, and shared utilities.

## 📖 Full Documentation

See [**SKILL.md**](SKILL.md) for the complete skill definition — triggers, workflows, all strategies, cron setup, error handling, and presentation guidelines.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## 📄 License

[MIT](LICENSE) — © 2025 Andernet (Matthew Anderson)

## 👤 Author

**Andernet** (Matthew Anderson) — [GitHub](https://github.com/and3rn3t)
