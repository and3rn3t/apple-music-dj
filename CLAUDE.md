# CLAUDE.md — apple-music-dj

**Read `AGENTS.md` first** — it holds the layout, commands, mock-API workflow and
conventions. This file only adds Claude-specific notes.

OpenClaw skill for Apple Music curation (bash + stdlib Python), published to ClawHub.

## Claude-specific notes

- Done gate: `make ci` (ruff + ShellCheck + mypy, tests at the 90% coverage floor, actionlint).
- Test against `scripts/demo.py serve` + `APPLE_MUSIC_API_BASE`, not the real API, unless
  the user asks for a live run. Never echo `APPLE_MUSIC_DEV_TOKEN` / `APPLE_MUSIC_USER_TOKEN`.
- A new root file must be excluded in **both** `.clawhubignore` and `.clawignore` (or added
  to `ALLOWED_ROOT` in `tests/test_packaging.py`), or the packaging tests fail.
- Changing a script's hosts, env vars or written files means updating SKILL.md's claims
  (`tests/test_trust_claims.py`).
- Don't bump versions, tag, publish, commit or push unless asked.
