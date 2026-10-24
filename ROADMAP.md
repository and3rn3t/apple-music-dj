# Roadmap

Where Apple Music DJ goes next. The goal: more people go from *finding the skill on ClawHub* to *a
playlist on their phone*, and more of them share what it made.

Each item has a one-line reason and a rough size: **XS** under an hour, **S** a few hours, **M** a
day or two, **L** several days. Shipped work lives in [CHANGELOG.md](CHANGELOG.md), not here.

Issues are scheduled in milestones: [Launch](https://github.com/and3rn3t/apple-music-dj/milestone/2) (due mid-November),
[3.6 — Year in review](https://github.com/and3rn3t/apple-music-dj/milestone/3) (early December), [3.7 — New strategies](https://github.com/and3rn3t/apple-music-dj/milestone/4) (end of January) and
[Later](https://github.com/and3rn3t/apple-music-dj/milestone/1). Tech debt and trust items sit in whichever release needs them first.

**Recently shipped:** demo mode and one-step token setup (3.3.0); taste codes, the animated README
demo, the Spotify-switcher guide and the pre-publish self-audit (3.4.0); and, in 3.5.0, `--minutes`
([#105](https://github.com/and3rn3t/apple-music-dj/issues/105)), remix any Apple Music playlist
([#101](https://github.com/and3rn3t/apple-music-dj/issues/101)), clean mode
([#109](https://github.com/and3rn3t/apple-music-dj/issues/109)), a bigger demo catalog
([#46](https://github.com/and3rn3t/apple-music-dj/issues/46)), the token-on-disk fix
([#60](https://github.com/and3rn3t/apple-music-dj/issues/60)), the `strategy_engine.py` split and the
test and CI tech debt ([#111](https://github.com/and3rn3t/apple-music-dj/issues/111)–[#115](https://github.com/and3rn3t/apple-music-dj/issues/115)), plus likes and
dislikes steering playlists ([#64](https://github.com/and3rn3t/apple-music-dj/issues/64)),
`config.json` preferences, the token-renewal nudge in the daily drop
([#47](https://github.com/and3rn3t/apple-music-dj/issues/47)), a leaner SKILL.md
([#63](https://github.com/and3rn3t/apple-music-dj/issues/63)), weighted taste profiles and the
curation-quality test.

## Now: launch (3.5)

- [ ] **Screen recording for the listing** ([#80](https://github.com/and3rn3t/apple-music-dj/issues/80)):
      20–30 s of "songs like Phoebe Bridgers" in OpenClaw turning into a playlist on an iPhone; the
      listing has no motion yet. Recorded by hand on a real account. *S*
- [ ] **Log the ClawHub verdict per release, then add a "ClawHub: Pass" badge**
      ([#81](https://github.com/and3rn3t/apple-music-dj/issues/81)): the verdict once flipped on
      identical code, so a per-version log shows which edits cause it. *XS*
- [ ] **Submit to "Awesome OpenClaw Skills"** (Music / Media)
      ([#82](https://github.com/and3rn3t/apple-music-dj/issues/82)): the main place people browse
      skills outside ClawHub. *XS*
- [ ] **Launch posts** ([#83](https://github.com/and3rn3t/apple-music-dj/issues/83)) in the OpenClaw
      showcase, r/AppleMusic and r/selfhosted, pitched to listeners ("Spotify-grade discovery for
      Apple Music") rather than to developers. *S*

## Next: standout features (3.6 and 3.7)

The ones that make people say "wait, it can do *that*?" and share the result.

- [ ] **World Tour** ([#103](https://github.com/and3rn3t/apple-music-dj/issues/103)): other
      countries' charts, filtered to your taste and to what plays in your storefront. Gives you new,
      already-proven music instead of the same local hits every week. *M*
- [ ] **Group blend for 3–8 listeners** ([#104](https://github.com/and3rn3t/apple-music-dj/issues/104)):
      road-trip and party playlists from everyone's taste codes, with a fairness rule and who each
      track is "for". *M*
- [ ] **Taste drift timeline card** ([#108](https://github.com/and3rn3t/apple-music-dj/issues/108)):
      an animated picture of how your genres and artists rose and faded across every snapshot. The
      drift card we have (`taste_card.py --mode drift`) is a static SVG comparing two points in
      time; a whole year in motion is what people share. *M*
- [ ] **Taste card as a PNG, Instagram Story size** ([#48](https://github.com/and3rn3t/apple-music-dj/issues/48)):
      SVG doesn't post anywhere. Optional `cairosvg`, with SVG as the fallback. *S*
- [ ] **Year in review ready for December** ([#85](https://github.com/and3rn3t/apple-music-dj/issues/85)):
      the card and caption work end to end. Still left: confirm Replay against the live API
      ([#66](https://github.com/and3rn3t/apple-music-dj/issues/66)) and the PNG export (#48). *S*

## Later

- [ ] **Swipe before you save** ([#102](https://github.com/and3rn3t/apple-music-dj/issues/102)): a
      local preview page with Apple's 30-second previews and the reason for each track. You keep or
      skip each one, and every swipe becomes a rating the engine learns from. *L*
- [ ] **Living playlists** ([#106](https://github.com/and3rn3t/apple-music-dj/issues/106)): an opt-in
      weekly job that rotates a DJ playlist (drops what you disliked or what has been there longest,
      adds fresh picks) and keeps a changelog. A playlist that stays fresh keeps people coming back.
      *L*
- [ ] **Dolby Atmos and lossless showcase** ([#107](https://github.com/and3rn3t/apple-music-dj/issues/107)):
      spatial audio is a reason to pick Apple Music, and nothing helps people find Atmos mixes of
      music they like. Needs a real account to confirm the album `audioVariants` data. *M*
- [ ] **Library doctor** ([#110](https://github.com/and3rn3t/apple-music-dj/issues/110)): a read-only
      report of duplicate editions (by ISRC), explicit/clean pairs and songs no longer playable. Big
      libraries pile these up and Apple Music never shows them. *M*
- [ ] **Verify the mock against the live API** ([#87](https://github.com/and3rn3t/apple-music-dj/issues/87)),
      starting with Replay ([#66](https://github.com/and3rn3t/apple-music-dj/issues/66)), so the
      demo and the tests keep matching the real service. *M*
- [ ] **Write-up on energy-arc sequencing and taste drift**
      ([#84](https://github.com/and3rn3t/apple-music-dj/issues/84)): explains the distinctive ideas
      and gives the listing something to link to. *M*
- [ ] **Hosted token helper (investigate)** ([#86](https://github.com/and3rn3t/apple-music-dj/issues/86)):
      the $99/yr Apple Developer membership is the biggest barrier, but a hosted helper means
      running a service, holding a signing key and checking Apple's MusicKit terms. Write an ADR
      before any code. *L*

## Trust and reviews: keep the ClawHub verdict at Pass

ClawHub's reviewer sees only the shipped package (not `tests/` or `CHANGELOG.md`), and its verdict
once flipped between Pass and Review on identical code. So remove anything it could plausibly read
as a risk, rather than waiting to be flagged. Already in place: `tests/test_trust_claims.py`,
`tests/test_openclaw_metadata.py`, `make audit` before each publish, and private vulnerability
reporting.

- [ ] **Log the verdict per version** ([#81](https://github.com/and3rn3t/apple-music-dj/issues/81))
      in the table below (`release_checks.check_verdict` prints it after each publish). *XS*
- [ ] **Signed tags and build provenance for releases** ([#88](https://github.com/and3rn3t/apple-music-dj/issues/88)):
      optional hardening, so users can check a release came from this repo. *M*

### Verdict log

| Version | ClawHub verdict | What changed |
|---|---|---|

## Ongoing

- Ship a release with one headline feature and a short clip every 4–6 weeks, so the listing
  always shows recent activity. The *Next* section is the queue for those headlines.
- Keep the ClawHub description's first three sentences focused on what a listener gets
  (`tests/test_listing.py` guards their length and the trigger phrases).
- Every new strategy goes into `tests/test_curation_quality.py`, so "did playlists get worse?"
  always has an answer.
