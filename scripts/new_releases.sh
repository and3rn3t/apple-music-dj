#!/usr/bin/env bash
# new_releases.sh — Enhanced personalized new release radar.
#
# Checks for new releases from the user's top artists AND adjacent artists
# discovered via taste profile genre matching.
#
# Usage:
#   scripts/new_releases.sh <profile.json> <storefront> [--create-playlist]
#
# Output: JSON with new releases, optionally creates a playlist.
# Designed for cron (daily at 8 AM) or on-demand use.
#
# Requires: APPLE_MUSIC_DEV_TOKEN and APPLE_MUSIC_USER_TOKEN
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API="$SCRIPT_DIR/apple_music_api.sh"

PROFILE="${1:?Usage: new_releases.sh <profile.json> <storefront> [--create-playlist]}"
SF="${2:?Usage: new_releases.sh <profile.json> <storefront> [--create-playlist]}"
CREATE_PLAYLIST="${3:-}"

if [[ ! -f "$PROFILE" ]]; then
  echo "ERROR: Profile not found: ${PROFILE}" >&2
  exit 1
fi

# ── Extract top artists from profile ─────────────────────────────
echo "📡 Scanning for new releases..." >&2

artist_names=$(jq -r '.top_artists[:20] | .[].name' "$PROFILE" 2>/dev/null)
artist_ids=$(jq -r '.top_artists[:20] | .[] | select(.id != null) | .id' "$PROFILE" 2>/dev/null)
top_genres=$(jq -r '.genre_distribution[:3] | .[].genre' "$PROFILE" 2>/dev/null)

releases="[]"
checked=0
found=0

# ── Check each artist for recent albums ──────────────────────────
for artist_id in $artist_ids; do
  (( checked++ )) || true
  albums=$("$API" artist-albums "$SF" "$artist_id" 2>/dev/null) || continue

  # Filter for albums released in the last 7 days
  recent=$(echo "$albums" | jq --arg cutoff "$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d '7 days ago' +%Y-%m-%d 2>/dev/null || echo '2026-02-17')" '
    [.data[] |
      select(.attributes.releaseDate >= $cutoff) |
      {
        album: .attributes.name,
        artist: .attributes.artistName,
        release_date: .attributes.releaseDate,
        album_id: .id,
        track_count: .attributes.trackCount,
        is_single: .attributes.isSingle,
        genre: (.attributes.genreNames // [])
      }
    ]
  ' 2>/dev/null)

  if [[ -n "$recent" && "$recent" != "[]" ]]; then
    releases=$(echo "$releases" "$recent" | jq -s '.[0] + .[1]')
    new_count=$(echo "$recent" | jq 'length')
    (( found += new_count )) || true
  fi

  # Rate limiting — don't hammer the API
  [[ $checked -gt 20 ]] && break
done

# ── Also check charts for genre-relevant new releases ────────────
echo "📊 Checking charts for genre-relevant releases..." >&2
for genre_name in $top_genres; do
  # Search for recent releases in user's genres
  search_result=$("$API" search "$SF" "new $genre_name 2026" "albums" 2>/dev/null) || continue
  chart_releases=$(echo "$search_result" | jq --arg cutoff "$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d '7 days ago' +%Y-%m-%d 2>/dev/null || echo '2026-02-17')" '
    [.results.albums.data[] |
      select(.attributes.releaseDate >= $cutoff) |
      {
        album: .attributes.name,
        artist: .attributes.artistName,
        release_date: .attributes.releaseDate,
        album_id: .id,
        track_count: .attributes.trackCount,
        is_single: .attributes.isSingle,
        genre: (.attributes.genreNames // []),
        source: "genre_discovery"
      }
    ]
  ' 2>/dev/null) || continue

  if [[ -n "$chart_releases" && "$chart_releases" != "[]" ]]; then
    releases=$(echo "$releases" "$chart_releases" | jq -s '.[0] + .[1]')
  fi
done

# ── Deduplicate ──────────────────────────────────────────────────
releases=$(echo "$releases" | jq '[group_by(.album_id) | .[] | .[0]]')
total=$(echo "$releases" | jq 'length')

echo "  Checked ${checked} artists, found ${total} new releases" >&2

# ── Output ───────────────────────────────────────────────────────
result=$(jq -n \
  --argjson releases "$releases" \
  --arg date "$(date +%Y-%m-%d)" \
  --arg sf "$SF" \
  '{
    scan_date: $date,
    storefront: $sf,
    total_releases: ($releases | length),
    releases: $releases
  }')

echo "$result" | jq .

# ── Optionally create a playlist ─────────────────────────────────
if [[ "$CREATE_PLAYLIST" == "--create-playlist" && "$total" -gt 0 ]]; then
  echo "" >&2
  echo "🎧 Creating New Releases playlist..." >&2

  # Collect first track from each album
  TMPIDS=$(mktemp /tmp/new_release_ids_XXXXXX.txt)
  for album_id in $(echo "$releases" | jq -r '.[].album_id'); do
    detail=$("$API" album-tracks "$SF" "$album_id" 2>/dev/null) || continue
    first_track=$(echo "$detail" | jq -r '
      .data[0].relationships.tracks.data[0].id // empty
    ' 2>/dev/null)
    [[ -n "$first_track" ]] && echo "$first_track" >> "$TMPIDS"
  done

  track_count=$(grep -c -v '^\s*$' "$TMPIDS" 2>/dev/null || echo 0)
  if [[ "$track_count" -gt 0 ]]; then
    PNAME="New Releases · $(date +"%b %d, %Y")"
    PDESC="Fresh releases from your artists and genre discoveries. ${track_count} tracks."
    "$SCRIPT_DIR/build_playlist.sh" create "$PNAME" "$PDESC" "$TMPIDS"
  fi
  rm -f "$TMPIDS"
fi
