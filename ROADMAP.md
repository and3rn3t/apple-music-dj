# Roadmap

Where Apple Music DJ goes next, ordered by expected impact on adoption. The goal: more people go
from *finding the skill on ClawHub* to *a playlist on their phone*, and more of them share it.

Done in 3.3.0: demo mode (`demo.py`), one-step token setup (`setup_auth.py`), token-age warnings,
corrected OpenClaw/ClawHub links and install command, the "What it can change" safety table, and
broader listing tags.

## Now — listing and launch

- [x] **Animated demo in the README** — a replay of `demo.py tour` (`assets/demo-tour.svg`,
      regenerate with `make demo-svg`).
- [x] **GitHub presence:** About box, topics and homepage point at ClawHub; Discussions on (Q&A,
      Show and tell); social preview card (`make social-preview`, uploaded by hand); CI keeps the
      README coverage badge honest; good-first-issues seeded from this roadmap.
- [ ] **Screen recording for the listing.** 20–30 s: say "songs like Phoebe Bridgers" in OpenClaw →
      the playlist appears in Apple Music on an iPhone. Needs a real device and account, so it is
      recorded by hand.
- [ ] **Publish 3.3.0 to ClawHub** and check the security verdict comes back *Pass*; once it is
      stable, add a "ClawHub: Pass" badge to the README.
- [ ] **Submit to the community "Awesome OpenClaw Skills" list** (Music / Media section).
- [ ] **Launch posts** with the GIF: OpenClaw Discord/community showcase, r/AppleMusic,
      r/selfhosted. Pitch to listeners ("Spotify-grade discovery for Apple Music"), not as a dev tool.
- [ ] **One write-up** on the energy-arc sequencing and taste drift — the distinctive ideas here,
      and something to link from the listing.

## Next — features that spread

- [ ] **Taste card as PNG, Instagram Story size (1080×1920)** ([#48](https://github.com/and3rn3t/apple-music-dj/issues/48)), with a small
      "apple-music-dj · ClawHub" footer. `taste_card.py` already renders SVG; add a PNG export
      (optional dependency, e.g. `cairosvg`, with the SVG as the fallback).
- [x] **Blend share codes.** `share_code.py make` prints an ID-free `amdj1:` taste code, and
      `--profile-b` (blend, compatibility) accepts it. "Send me your code" is a much easier ask than a file.
- [ ] **Monthly recap / "Wrapped"-style year in review** as a shareable card, timed for December,
      with a ready-made caption. Builds on `listening_insights.py` and the snapshots.
- [x] **Spotify-switcher section** in the README plus `references/spotify-import.md`, with a sample
      export to try. Still open: a line for the ClawHub listing description ([#49](https://github.com/and3rn3t/apple-music-dj/issues/49)) (keep
      `tests/test_listing.py`'s opening-sentence limits in mind).

## Later — remove the remaining setup friction

- [ ] **Richer demo catalog** ([#46](https://github.com/and3rn3t/apple-music-dj/issues/46)). The demo uses the 12-song test catalog; a separate ~150-song demo
      catalog (still fictional-listener, real-ish metadata) would make demo playlists full length.
      Keep the tests on the small catalog so their assertions stay stable.
- [ ] **Hosted token helper (investigate).** The $99/yr Apple Developer membership is the biggest
      barrier. A hosted page that issues user tokens under a shared developer key would remove it,
      but means running a service, holding a signing key and checking Apple's MusicKit terms.
      Write an ADR before building anything.
- [x] **Renewal nudge in scheduled jobs** ([#47](https://github.com/and3rn3t/apple-music-dj/issues/47)). Cron output only goes to a log; when a token is within
      14 days of expiry, have the daily-drop job surface the warning where the user will see it
      (e.g. in the day's pick message).
- [ ] **Verify response shapes against the live API** and record any differences in the mock, so
      the demo and the tests keep matching the real service.

## Trust and reviews — keep the ClawHub verdict at Pass

ClawHub's reviewer sees only the shipped package (not `tests/` or `CHANGELOG.md`), and its verdict
once flipped between Pass and Review on identical code. So: remove anything it could plausibly
read as a risk, rather than waiting to be flagged.

- [x] Claims in `SKILL.md` (hosts, env vars, stored files, no risky constructs, every account write
      confirmed) are enforced by `tests/test_trust_claims.py`.
- [x] **Self-audit before each publish:** `make audit` runs the trust checks, lists the shipped files
      changed since the last tag and prints a review prompt for ClawHub's concerns (see
      `CONTRIBUTING.md`). The model review itself stays manual: CI holds no model key.
- [ ] **Log the verdict per version** in the table below (`release_checks.check_verdict` prints
      it after each publish), to see which edits cause a "Review" flip.
- [x] Frontmatter matches the OpenClaw/ClawHub spec (`os`, `emoji`, `install` under
      `metadata.openclaw`; no unread gating keys; MIT-0; `{baseDir}` script paths), enforced by
      `tests/test_openclaw_metadata.py`.
- [x] Enable GitHub private vulnerability reporting (repo settings → Security) and point
      `SECURITY.md` at it.
- [ ] Optional hardening: signed tags, build provenance for releases.

### Verdict log

| Version | ClawHub verdict | What changed |
|---|---|---|

## Ongoing

- Ship a release with one headline feature and a short clip every 4–6 weeks, so the listing
  always shows recent activity.
- Keep the ClawHub description's first three sentences focused on what a listener gets
  (`tests/test_listing.py` guards their length and the trigger phrases).
