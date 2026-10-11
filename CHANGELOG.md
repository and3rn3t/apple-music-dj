# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.1] — 2026-10-11

### Changed

- The privacy section lists the two stored files it had missed (`storefront.cache`, the optional `config.json`) and says plainly that tokens reach `curl` through a short-lived owner-only temp file that is deleted on exit.
- `CODE_OF_CONDUCT.md` has a real enforcement contact instead of a placeholder.
- Released versions in this changelog now carry their release dates (3.2.0–3.3.0 still said "Unreleased").

### Added

- `tests/test_trust_claims.py` keeps `SKILL.md`'s claims true: scripts may only contact `api.music.apple.com` (plus MusicKit JS for the local sign-in page and loopback test hooks), no `eval`/`sudo`/piped installers/`shell=True`, and every `APPLE_*` variable and every file under `~/.apple-music-dj/` must be documented.
- The same test file checks, from the script itself, that every `apple_music_api.sh` command that writes to the account calls `_confirm`, so a new write command can't skip `--yes`. `test_listing.py` fails if a released changelog section has no date.

## [3.3.0] — 2026-10-10

Easier to try, easier to set up.

### Added

- **Demo mode — try it with no account or tokens.** `python3 scripts/demo.py tour` runs the real scripts against a fictional listener and a small sample catalog served on `127.0.0.1` for the length of the command: Taste DNA card, a "songs like" playlist, a decade throwback, a daily pick and a compatibility score. `demo.py run <script> [args]` runs any skill script the same way (`DEMO_PROFILE` stands for the demo profile). The sandbox gets its own `HOME` (`~/.apple-music-dj-demo/`), placeholder tokens and no real `APPLE_*` variables; `setup_cron.py`, `setup_auth.py` and paths into the real `~/.apple-music-dj/` are refused. `demo.py reset` removes the demo data. The mock API moved from `tests/mock_api.py` (now a re-export) to `scripts/demo.py` so it ships.
- **One-step token setup.** `python3 scripts/setup_auth.py` signs the developer token from your MusicKit key (or reuses a valid one), opens a local page where you sign in with Apple, and prints both `export` lines (`--env-file PATH` writes them `0600` instead). The page is served on `127.0.0.1` at a random path, refuses foreign `Host` and cross-origin requests, and stops once the token arrives. `setup_auth.py status` shows how long each token has left.
- **User-token age warning.** The user token carries no expiry, so the skill records when it first saw it (by a 16-hex-digit SHA-256 fingerprint, never the token) and the profiler and `verify_setup.sh` warn as it nears the ~6 months these last.
- `ROADMAP.md` (not shipped).

### Changed

- **Listing:** README links point to openclaw.ai / clawhub.ai (was openclaw.dev), the install command is `openclaw skills install apple-music-dj` (plus "start a new session"), a "Try it first" section and a "What it can change" safety table are near the top, stale "5 strategies" counts are fixed, and `clawhub.json` carries the same tags as `SKILL.md` (plus `music-discovery`, `spotify-import`, `demo`).
- `SKILL.md` tells the agent to offer the demo when tokens are missing and to have the user run `setup_auth.py` in their own terminal; the description mentions the demo and adds "set up Apple Music tokens" and "try the demo" triggers.
- Missing- or expired-token messages now point to `setup_auth.py` (and the demo) instead of the manual steps; `troubleshooting.md` no longer shows a wrong `generate_dev_token.py` invocation.
- `generate_dev_token.py` exposes `make_dev_token()` for reuse; its CLI is unchanged.
- **The Apple tokens are no longer hard requirements in the skill metadata.** They move from `requires.env` to `metadata.openclaw.envVars` with `required: false` (ClawHub's documented form for optional variables), so OpenClaw loads the skill before setup and the agent can offer the demo. Scripts still check for the tokens at run time. All other `APPLE_*` variables the scripts read are now declared there too, with descriptions; `clawhub.json` mirrors the change.

## [3.2.5] — 2026-10-10

### Security

ClawHub's review of 3.2.4 said some account-changing commands could "directly alter playlists or ratings without an enforced confirmation step". Fair: the safeguards lived in the callers.

- **`apple_music_api.sh` now enforces confirmation itself.** `create-playlist`, `add-to-playlist`, `remove-from-playlist`, `add-to-library`, `favorite`, `rate` and `unrate` only print `WOULD …` and exit 3 unless `--yes` is passed. The scripts that already gate their own writes (`--create`, `--yes`, `--apply`, `--confirm`) pass it after that gate.
- **`build_playlist.sh create|refresh|remove` also preview** unless `--yes` is the last argument (its callers pass it after their own gates), so the helper is no longer a way around the wrapper check.
- **`feedback.py like|dislike|clear` previews by default** and needs `--yes` to rate songs or touch the profile; a preview needs no credentials.
- **`weekly-mix` is now opt-in** (`setup_cron.py install --jobs weekly-mix`). It is the one scheduled job that writes to your library unattended; a plain `install` now schedules only the report-only jobs. Existing crontab entries are untouched.

### Changed

- SKILL.md now lists the optional requirements (`APPLE_MUSIC_STOREFRONT`, `crontab`, the `.p8` key variables and PyJWT for `generate_dev_token.py`) and notes ClawHub's MIT-0 distribution.

## [3.2.4] — 2026-10-11

### Security

Hardening from the ClawHub review of 3.2.3 (whose verdict flipped between Pass and Review on identical code; these are the points that were fair):

- **`playlist_health.py fix --apply`** replaces `--auto`: `fix` only previews (`WOULD remove …`) unless `--apply` is given, and "auto" read as "unattended". It removes duplicate copies and *adds* a replacement for each unavailable track (the unavailable entry itself stays); its messages now say exactly that. The old `--auto` still works as a hidden alias, and the result keeps the legacy `auto_applied` key beside the new `applied`.
- **Clearer disclosure** in `SKILL.md`: editing an existing playlist can *remove tracks* (`fix --apply`, `build_playlist.sh refresh|remove`); it is listed in the "data written to your account" table and in the At a glance safety note, the scheduled health check is stated to be report-only, and ratings are only written on the user's explicit say-so.
- **`verify_setup.sh` cleans up its token temp file on interrupt** (Ctrl-C / `kill`) and honors the same loopback-only `APPLE_MUSIC_API_BASE` test hook as the API wrapper, so it is now tested end to end.
- The API wrapper's cleanup names its exact temp-file kinds instead of a broad `am_*` pattern.
- Docs no longer suggest `rm -rf ~/.apple-music-dj/`: they say to list the folder first and delete it deliberately (and that an agent must never do it unprompted); the troubleshooting guide removes only the cached profile.

## [3.2.3] — 2026-10-10

### Security

Follow-up to the ClawHub audit of 3.2.2, which flagged that a documented workflow could write to the account without the confirmation the skill promises:

- **`concert_prep.sh` now previews by default**: it prints the proposed playlist (name, description, track list) as JSON and writes nothing; `--create` is required to build it (the flag can go anywhere). Previously it created the playlist unconditionally. `SKILL.md` tells the agent to show the preview and re-run with `--create` only after a yes. The preview reports `name_exists`, and `--create` on a taken name reports `created: false` with a `skipped_reason` instead of claiming success (the builder skips such playlists quietly).
- **"Nothing is written by default" is now tested** across every write-capable entry point (concert prep, similar/era/trend strategies, gap analysis, playlist health fix, new releases, playlist import, cron install).
- `SKILL.md` is explicit that scheduled jobs run unattended (installing one is the approval), instead of implying every write is confirmed per run.

### Fixed

- **Two default cron jobs never worked since v3.0**: `new-releases` passed the storefront where `new_releases.sh` expects `<profile.json> <storefront>` (it exited 1), and `daily-drop` passed `--profile` to `daily_pick.py`, which takes positional `<profile.json> <storefront>` (it exited 2). Cron only writes to a log, so both failed silently. Both now run, and a new test executes every default job's real command.

## [3.2.2] — 2026-10-11

### Changed

- **Clearer ClawHub listing**: the `SKILL.md` description now opens with a short pitch before the trigger list (the page cuts the summary off after a few sentences), keeps every trigger phrase, and adds "more like" and "how has my taste changed". New tags `listening-history`, `taste-profile` and `playlist-import`.
- **"At a glance" section at the top of `SKILL.md`** (what it does, things to say, what it needs, the safety model), and an intro that no longer says it "writes everything directly" to your library.
- **README samples** replace the "coming soon" placeholder: a sample Taste DNA card (`assets/sample-taste-card.svg`), a "songs like" playlist and a taste-drift report, generated by the real scripts from a fictional profile / demo catalog.

### Added

- `tests/test_listing.py` guards the listing: version agreement across `pyproject.toml`, `SKILL.md` and `clawhub.json`, a crisp description opening, no dropped trigger phrases, valid README images, and no flagged `--seed <value>` pattern in shipped docs.

## [3.2.1] — 2026-10-10

### Security

Follow-up to the ClawHub audit of 3.2.0:

- **Cron install now requires confirmation, enforced in code** (`setup_cron.py`): `install --dry-run` prints the exact crontab lines plus a digest, and `install` only proceeds with `--confirm <digest>`. A bare `install` changes nothing and exits 2; a digest only matches the exact lines it was printed for. Previously the review step was only a documented instruction.

### Changed

- **Renamed the "seed" strategy to "similar"**: `--strategy similar --similar-to "<artist or song>" [--similar-type artist|song]`. A security scanner read the old flag example in `SKILL.md` as a crypto seed phrase passed on the command line. The 3.2.0 spellings (the `seed` strategy name and the old seed flags) still work as hidden aliases and playlists are now logged with strategy `similar`.

## [3.2.0] — 2026-10-10

### Added

- **Similar strategy** (shipped as "seed", renamed in 3.2.1) — songs like an artist or song, via similar artists and the user's taste
- **Era strategy** — `--strategy era --decade 90s`: a throwback built from the user's own artists (defaults to their top era)
- **Blend strategy** — `--strategy blend --profile-b other.json`: one playlist for two listeners, capped at 60% from either, with a compatibility score
- **Taste drift** — `taste_profiler.py` now saves a compact dated snapshot per fresh build (`~/.apple-music-dj/snapshots/`, last 52, no song IDs; skip with `--no-snapshot`); new `taste_drift.py` reports rising/falling genres, new top artists, era shift, score changes and archetype change; drift card via `taste_card.py --mode drift`; opt-in `monthly-drift` cron job
- **Playlist import** — `import_playlist.py` rebuilds a playlist from a CSV (ISRC or title + artist) or text file; ISRC first, then strict title + artist matching, with a match report
- **Feedback** — `feedback.py like|dislike|clear|info` rates songs in Apple Music (by ID or playlist position) and updates the cached profile
- `--favorite` (with `--create`) adds a generated playlist's tracks to Apple Music favorites
- `gap-analysis --add-missing N` previews adding the newest N missing albums to the library; `--yes` is required to write
- Profile signals from recently added library items and recent radio-station titles (`recently_added_artists`, `station_genres`)
- New `apple_music_api.sh` commands: `similar-artists`, `songs-by-isrc`, `recently-added`, `recent-stations`, `add-to-library`, `favorite`, `rate`, `unrate`
- Real energy-arc sequencing: `sequence_tracks(arc=wave|ascending|descending|none)` driven by a shared `GENRE_ENERGY` map; moods pick their arc
- Local mock Apple Music API (`tests/mock_api.py`) and end-to-end tests that run the real scripts against it; `APPLE_MUSIC_API_BASE` (loopback addresses only) points the wrapper at it
- Ruff lint config (`[tool.ruff]`), `make ruff`, and lint + ShellCheck jobs in CI and pre-commit
- pip caching in CI

### Security

Addresses the ClawHub security audit of v3.1.0:

- **Cron injection** (`setup_cron.py`): `--profile`, `--log-dir`, `--python`, `--storefront` and `--jobs` are now validated (no newlines/control characters/`%`; `--python` must be an executable file; storefront must be a two-letter code), the log path is shell-quoted like every other value, and a line containing a newline or `%` is refused. Jobs run under `umask 077`. New `install --dry-run` prints the exact crontab lines without installing anything.
- **Cron logs readable by other users**: log directories are created `0700` and log files `0600` *before* cron writes to them; symlinked or foreign-owned log directories/files and directories other users can write to are rejected.
- **Symlink / ownership safety for every write**: `write_private()` opens without truncating and with `O_NOFOLLOW`, and only truncates after `fstat` confirms a regular file you own — a symlinked `--output` (or a file owned by someone else) is refused instead of clobbered. `/dev/stdout`-style stream devices still work.
- **`--jobs` handling in `setup_cron.py`**: an explicit empty value (`--jobs ''`, `,`) used to fall back to *all* default jobs — and `remove` removed every job. It is now rejected, and unknown job names are rejected up front.
- **Profiles written with loose permissions**: `os.open(..., 0o600)` only applies to newly created files, and the profiler's cache-hit `--output` path used a plain `write_text`. All writers now go through `write_private()`, which enforces `0600` on existing files too and creates directories `0700`; `~/.apple-music-dj/` is tightened to `0700`.

### Changed

- **Minimum Python is now 3.10** (3.9 is end-of-life); CI tests 3.10, 3.12 and 3.14
- Loosened the `cryptography` pin to `>=50,<51` so patch releases no longer need a dependency PR
- `infer_energy_profile` now reads the shared `GENRE_ENERGY` map (same results as before)

### Fixed

- `apple_music_api.sh`: URLs containing `[` `]` (e.g. `replay-summary <year>` → `filter[year]=`) failed with curl's "bad range" error — curl now runs with `-g`
- `apple_music_api.sh`: on bash 4+/5 (Linux, Homebrew bash) every API call aborted with `tmpfile: unbound variable` because `RETURN` traps stay armed after their function returns; one helper's trap also replaced another's, leaving the token-bearing curl config in `$TMPDIR`. Temp files are now removed explicitly after each call, with `EXIT`/`INT`/`TERM` traps as a backstop that removes by a PID-tagged name pattern (no registry to race against a signal); curl runs under `wait`, so Ctrl-C/TERM acts immediately, kills curl, and exits 130/143 instead of waiting out the request (this also fixes `add-to-playlist` / `remove-from-playlist` aborting after succeeding)
- `refresh` no longer suggests songs already in the library (`--include-library` opts back in)

### Removed

- Unused imports and dead assignments found by Ruff
- Placeholder Lighthouse workflow and duplicate Markdown issue templates (the YAML forms remain)

## [3.1.0] — 2026-03-02

### Added

- **Python 3.9+ compatibility** — removed `X | Y` union syntax, works on 3.9, 3.11, and 3.13
- **Genre filter** — `filter_generic_genres()` strips generic "Music" tag from taste data
- **Token expiry warning** — `check_token_expiry()` warns when dev token is near expiration
- **Playlist deduplication** — playlist health checker detects and removes duplicate tracks
- **Storefront auto-detection** — `get_storefront()` resolves storefront from env, cache, or API
- **verify_setup overhaul** — improved output, token validation, and connectivity checks
- **Playlist history** — `playlist_history.py` tracks created playlists with freshness checking
- **clawhub.json** — skill metadata for OpenClaw skill registry
- **Test coverage to 87%** — 431 tests across 12 modules (up from 156 tests / 5 modules)
- **New test suites** — `generate_dev_token`, `playlist_health`, `playlist_history`, `setup_cron`
- **GitHub Actions CI** — Python 3.9/3.11/3.13 matrix with 80% coverage gate
- **Makefile** — `make test`, `make coverage`, `make coverage-html` commands
- **`.env.example`** — template for required environment variables

### Changed

- **README.md** — full rewrite with badges, feature list, quick start, and development section
- **pyproject.toml** — added classifiers, project URLs, `pytest-cov` dev dependency
- **CONTRIBUTING.md** — updated Python version requirement to 3.9+
- **`.gitignore`** — expanded to cover `coverage_html/`, `node_modules/`, `.coverage`

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
- **Shared module** — `_common.py` with `call_api`, `load_profile`, `require_env_tokens`, search helpers
- **Test suite** — 156 pytest unit tests across 5 modules (taste_profiler, compatibility, daily_pick, taste_card, _common)
- **pyproject.toml** — project metadata, pytest config, Python 3.10+ requirement
- **Skill icon** — SVG icon for OpenClaw skill listing
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
- Python minimum version updated to 3.10+ (uses `X | Y` union type syntax)
- CONTRIBUTING.md updated with test instructions and corrected Python version

### Fixed — Code Quality (30 issues)

- Extracted shared `_common.py` module — eliminated duplicated API/profile code across 5 scripts
- `score_candidate()` now accepts `rng` as keyword argument (was positional-only, caused crash)
- `genre_evolution` in `extract_replay_highlights()` used wrong data field
- Hardcoded year 2026 replaced with dynamic `datetime.now().year`
- Double-seeded RNG in `cmd_daily` — seeded `random.Random` was passed correctly
- `KeyError` → `.get()` protection across all scripts
- Progress indicators added (stderr) for long-running API operations
- `while read` loops replaced unsafe `for` loops in bash scripts (whitespace safety)
- `grep -qxF` for exact dedup matching in `concert_prep.sh`

### Fixed — Error Handling (25 issues)

- `call_api` propagates stderr from failed API calls
- `score_candidate` signature crash on missing keyword arg
- `build_playlist.sh` checks return codes from API calls
- Environment variable validation via `require_env_tokens()` before any API usage
- Network error detection and user-friendly messages
- Year validation (2015–current) in listening insights
- `JSONDecodeError` reports line/column only (no content leak)

### Fixed — Security (15 issues)

- Tokens passed via `curl -K` config files instead of CLI arguments (prevents `ps aux` exposure)
- Token echo truncated to first 20 chars in verify_setup
- File permissions set to `0o600` for all generated files (cache, cards, config)
- `$TMPDIR` used for temporary files instead of predictable paths
- `.clawignore` expanded: `.env.*` wildcard, tests/, dev artifacts
- Input validation added for all user-supplied arguments (ratings, limits, storefronts)
- `JSONDecodeError` handler no longer leaks file content in error messages

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
