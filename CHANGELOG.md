# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] — 2026-02-24

### Added

- **Taste DNA Card** — shareable SVG/text visual of listener identity and archetype (`taste_card.py`)
- **Compatibility Score** — taste match percentage against any artist or another user (`compatibility.py`)
- **Listening Insights** — timeline, streaks, milestones, and year-in-review (`listening_insights.py`)
- **Catalog Gap Analysis** — find missing albums from favorite artists (`catalog_explorer.py`)
- **Album Deep Dive** — track-by-track breakdown with singles vs deep cuts (`catalog_explorer.py`)
- **Artist Rabbit Hole** — chain exploration from one artist outward (`catalog_explorer.py`)
- **Daily Song Drop** — one perfect track per day with rationale (`daily_pick.py`)
- **What Should I Listen To Right Now?** — time-of-day-aware instant pick (`daily_pick.py`)
- **Concert Prep Playlist** — top songs + deep cuts for upcoming shows (`concert_prep.sh`)
- **New Release Radar** — personalized scan of new releases (`new_releases.sh`)
- New API commands: `artist-detail`, `album-tracks`, `song-detail`, `library-playlists` in `apple_music_api.sh`
- Exponential backoff retry logic (429 rate limit handling) in `apple_music_api.sh`
- Heavy rotation and recommendations track extraction in taste profiler
- Library song IDs extraction (with catalog ID preference) in taste profiler
- Cron support for daily song drops and new release watch
- 12 new trigger phrases in SKILL.md

### Changed

- **SKILL.md** — version bumped to 3.0.0, expanded with all engagement features
- `taste_profiler.py` — `call_api()` now accepts `raw=True` for non-JSON outputs
- `taste_profiler.py` — fixed `detect_storefront()` to use raw API mode
- Cache TTL documented as 7-day (was incorrectly stated as 24h)
- Artist repeat gap corrected to 5 tracks (was documented as 4)
- CLI flags updated: `--cache` + `--max-age 0` replaces `--force-refresh`

### Fixed

- `disliked_artist_ids` renamed to `disliked_song_ids` (matched actual API data)
- Homepage URL pointed to correct GitHub user (`and3rn3t`)
- README strategy count corrected from 4 to 5

## [2.0.0] — 2026-02-23

### Added

- Taste profiler with 7 data sources (recently played, heavy rotation, library, ratings, recommendations, Replay)
- 5 playlist strategies: Deep Cuts, Mood/Activity, Trend Radar, Constellation Discovery, Playlist Refresh
- Apple Music API wrapper with 20+ commands
- Playlist builder with direct Apple Music library integration
- Developer token generator (PyJWT)
- Cron support for weekly auto-playlists
- Full reference docs: auth setup, API reference, playlist strategies

## [1.0.0] — 2026-02-22

### Added

- Initial skill scaffold
- Basic Apple Music API integration
- README and SKILL.md
