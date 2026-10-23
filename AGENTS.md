# Project Guidelines (AGENTS.md)

<!--
  Single source of truth for AI assistant instructions in this repo.
  CLAUDE.md is a thin pointer to this file — edit HERE.
-->

## Project Overview

**Apple Music DJ** is an OpenClaw skill (published to ClawHub as `apple-music-dj`) that
curates Apple Music from the user's real listening: taste profiling, eight playlist
strategies (deep cuts, mood, trend radar, constellation, refresh, similar, era throwback,
blend) and engagement features (taste card, compatibility, insights, catalog gaps, taste
drift, Spotify import, daily pick, concert prep, new releases, cron curation).
`SKILL.md` is what OpenClaw reads; everything else supports it. A built-in demo
(`scripts/demo.py`) works with no tokens.

Runs on macOS and Linux. Needs `curl`, `jq`, `python3` (3.11+). Account writes are opt-in
and confirmed before they happen.

## Layout

```
SKILL.md              # skill definition: frontmatter, workflows, scripts table, quick commands
clawhub.json          # registry metadata (version must match SKILL.md and pyproject.toml)
scripts/
  apple_music_api.sh  # bash wrapper for every Apple Music API endpoint SKILL.md uses
  build_playlist.sh, new_releases.sh, concert_prep.sh, verify_setup.sh
  _common.py          # shared helpers + Python-version guard
  taste_profiler.py, strategy_engine.py, …  # one Python script per feature
  demo.py             # local stand-in for the Apple Music API (ships with the skill)
  generate_dev_token.py, setup_auth.py      # MusicKit token setup (PyJWT + cryptography)
references/           # auth setup, API reference, playlist strategies, Spotify import, troubleshooting
assets/               # icon, demo SVG, sample taste card / Spotify CSV
tests/                # pytest; mock_api.py re-exports scripts/demo.py
.github/scripts/      # release_checks.py, self_audit.py, demo/social-preview generators
```

## Build & Test

```bash
make test           # pytest tests/ -v
make coverage       # pytest with --cov-fail-under=80 (CI's floor)
make ruff           # ruff check scripts tests .github/scripts + shellcheck scripts/*.sh
make lint           # syntax-check every scripts/*.py and scripts/*.sh
make actionlint     # lint workflows
make ci             # ruff + coverage + actionlint — everything CI checks
make audit          # pre-publish self-audit (trust claims, listing, packaging, diff since last tag)
make demo-svg       # regenerate assets/demo-tour.svg after the demo tour changes
```

Dev deps: `pip install -e ".[dev]"` (pytest, pytest-cov, ruff, pyyaml); token generation
needs `requirements.txt` (`PyJWT`, `cryptography`). ShellCheck and actionlint come from the
system (e.g. Homebrew).

Without an Apple Developer account, test against the mock:

```bash
python3 scripts/demo.py tour                        # quickest look
python3 scripts/demo.py serve &                     # http://127.0.0.1:8765
export APPLE_MUSIC_API_BASE=http://127.0.0.1:8765   # loopback only — enforced by apple_music_api.sh
export APPLE_MUSIC_DEV_TOKEN=x APPLE_MUSIC_USER_TOKEN=y
scripts/apple_music_api.sh recently-added 5
```

`tests/test_integration_mock_api.py` runs the real scripts (curl, jq and all) against it.

## Configuration

Env vars (see `.env.example`): `APPLE_MUSIC_DEV_TOKEN`, `APPLE_MUSIC_USER_TOKEN`, optional
`APPLE_MUSIC_STOREFRONT`. Never commit `.env`, `*.p8` or `*.pem`, and never print tokens.

## Conventions

- **Core scripts are stdlib-only.** `PyJWT`/`cryptography` are the only exceptions, for
  token generation.
- Bash: `set -euo pipefail`, quote every variable, `[[ ]]` conditionals, `snake_case`
  functions. Python: `snake_case` functions, `PascalCase` classes; ruff line length 120.
- Anything that writes listening data must create files/dirs owner-only
  (`tests/test_private_writes.py`).
- `tests/test_trust_claims.py` enforces SKILL.md's claims about network hosts, env vars,
  stored files and risky constructs: a new host, env var or stored file must be documented
  in SKILL.md before the tests pass.
- **Packaging:** `.clawhubignore` and `.clawignore` must stay identical, and
  `tests/test_packaging.py` whitelists the files that ship. A new root file must be added
  to `ALLOWED_ROOT` or to both ignore files on purpose.
- Keep SKILL.md example commands free of flag names that read like secrets (ClawHub's
  review once flagged `--seed "<value>"`).
- New feature: script in `scripts/`, plus SKILL.md feature section, Scripts table row,
  Quick Commands entry and Example Interaction; README features list; strategies also go in
  `references/playlist-strategies.md`; `CHANGELOG.md` under `[Unreleased]`.
- Conventional commits; branches `type/short-description`. License is MIT-0.

## Releasing

Publishing a GitHub release `vX.Y.Z` triggers `publish-clawhub.yml` (verify job, then a
reviewer-gated `clawhub` environment). Before that: `make audit`, bump the version in
`SKILL.md`, `pyproject.toml` and `clawhub.json` (must agree), add a `## [X.Y.Z]` CHANGELOG
section. Details in `CONTRIBUTING.md`. Never bump, tag, publish, commit or push unless asked.
