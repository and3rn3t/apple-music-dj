# Roadmap

Where Apple Music DJ goes next, ordered by expected impact on adoption. The goal: more people go
from *finding the skill on ClawHub* to *a playlist on their phone*, and more of them share it.

Done in 3.3.0: demo mode (`demo.py`), one-step token setup (`setup_auth.py`), token-age warnings,
corrected OpenClaw/ClawHub links and install command, the "What it can change" safety table, and
broader listing tags.

## Now — listing and launch

- [ ] **Demo GIF / short video at the top of the README and listing.** 20–30 s: say "songs like
      Phoebe Bridgers" in OpenClaw → the playlist appears in Apple Music on an iPhone. Record the
      no-account version with `demo.py tour` too, for people without tokens.
- [ ] **Publish 3.3.0 to ClawHub** and check the security verdict comes back *Pass*; once it is
      stable, add a "ClawHub: Pass" badge to the README.
- [ ] **Submit to the community "Awesome OpenClaw Skills" list** (Music / Media section).
- [ ] **Launch posts** with the GIF: OpenClaw Discord/community showcase, r/AppleMusic,
      r/selfhosted. Pitch to listeners ("Spotify-grade discovery for Apple Music"), not as a dev tool.
- [ ] **One write-up** on the energy-arc sequencing and taste drift — the distinctive ideas here,
      and something to link from the listing.

## Next — features that spread

- [ ] **Taste card as PNG, Instagram Story size (1080×1920)**, with a small
      "apple-music-dj · ClawHub" footer. `taste_card.py` already renders SVG; add a PNG export
      (optional dependency, e.g. `cairosvg`, with the SVG as the fallback).
- [ ] **Blend share codes.** Today a blend needs the other person's full profile JSON. Add
      `taste_profiler.py --share-code` that exports a compact, ID-free, base64 summary (genre/era
      weights + top artists — the same data as a snapshot), and let `--profile-b` accept a code.
      "Send me your code" is a much easier ask than a file.
- [ ] **Monthly recap / "Wrapped"-style year in review** as a shareable card, timed for December,
      with a ready-made caption. Builds on `listening_insights.py` and the snapshots.
- [ ] **Spotify-switcher landing section.** Lead a README section and listing line with "Moving
      from Spotify? Bring your playlists" (`import_playlist.py`), plus a short guide on exporting
      Spotify playlists to CSV.

## Later — remove the remaining setup friction

- [ ] **Richer demo catalog.** The demo uses the 12-song test catalog; a separate ~150-song demo
      catalog (still fictional-listener, real-ish metadata) would make demo playlists full length.
      Keep the tests on the small catalog so their assertions stay stable.
- [ ] **Hosted token helper (investigate).** The $99/yr Apple Developer membership is the biggest
      barrier. A hosted page that issues user tokens under a shared developer key would remove it,
      but means running a service, holding a signing key and checking Apple's MusicKit terms.
      Write an ADR before building anything.
- [ ] **Renewal nudge in scheduled jobs.** Cron output only goes to a log; when a token is within
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
- [ ] **Self-audit before each publish.** Run `SKILL.md` and `scripts/` through a review prompt
      that mimics ClawHub's concerns (undisclosed writes, unattended actions, credentials, network
      destinations, shell injection) and fix what it flags before the release is published.
- [ ] **Log the verdict per version.** `release_checks.check_verdict` already reads it; keep a
      short table (version → verdict → what changed) to see which edits cause a "Review" flip.
- [ ] Enable GitHub private vulnerability reporting (repo settings → Security) and point
      `SECURITY.md` at it.
- [ ] Optional hardening: signed tags, build provenance for releases.

## Ongoing

- Ship a release with one headline feature and a short clip every 4–6 weeks, so the listing
  always shows recent activity.
- Keep the ClawHub description's first three sentences focused on what a listener gets
  (`tests/test_listing.py` guards their length and the trigger phrases).
