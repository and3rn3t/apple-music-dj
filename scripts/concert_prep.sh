#!/usr/bin/env bash
# concert_prep.sh — Build a concert prep playlist for an upcoming show.
#
# Fetches the artist's top songs + deep cuts and creates a playlist
# to get ready for a live performance.
#
# Usage:
#   scripts/concert_prep.sh <storefront> <artist_name> [playlist_name]
#
# Requires: APPLE_MUSIC_DEV_TOKEN and APPLE_MUSIC_USER_TOKEN
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API="$SCRIPT_DIR/apple_music_api.sh"

SF="${1:?Usage: concert_prep.sh <storefront> <artist_name> [playlist_name]}"
ARTIST_QUERY="${2:?Usage: concert_prep.sh <storefront> <artist_name> [playlist_name]}"

# ── Find artist ──────────────────────────────────────────────────
echo "🔍 Searching for ${ARTIST_QUERY}..." >&2
search_result=$("$API" search "$SF" "$ARTIST_QUERY" "artists")
artist_id=$(echo "$search_result" | jq -r '.results.artists.data[0].id // empty')
artist_name=$(echo "$search_result" | jq -r '.results.artists.data[0].attributes.name // empty')

if [[ -z "$artist_id" ]]; then
  echo "ERROR: Could not find artist: ${ARTIST_QUERY}" >&2
  exit 1
fi

PLAYLIST_NAME="${3:-Concert Prep · ${artist_name} · $(date +"%b %Y")}"
echo "🎤 Found: ${artist_name} (${artist_id})" >&2

# ── Gather top songs ─────────────────────────────────────────────
echo "📋 Fetching top songs..." >&2
top_result=$("$API" artist-top "$SF" "$artist_id")
top_ids=$(echo "$top_result" | jq -r '
  .data[0].views["top-songs"].data[].id // empty
' 2>/dev/null | head -15)

top_count=$(echo "$top_ids" | grep -c -v '^\s*$' 2>/dev/null || echo 0)
echo "  Got ${top_count} top songs" >&2

# ── Gather deep cuts from albums ─────────────────────────────────
echo "💿 Fetching discography for deep cuts..." >&2
albums_result=$("$API" artist-albums "$SF" "$artist_id")
album_ids=$(echo "$albums_result" | jq -r '.data[].id' 2>/dev/null | head -5)

deep_cut_ids=""
for album_id in $album_ids; do
  album_detail=$("$API" album-tracks "$SF" "$album_id" 2>/dev/null) || continue
  # Get tracks that are NOT in the top songs
  album_tracks=$(echo "$album_detail" | jq -r '
    .data[0].relationships.tracks.data[].id // empty
  ' 2>/dev/null)
  for tid in $album_tracks; do
    # Check if this track is already in top songs
    if ! echo "$top_ids" | grep -q "^${tid}$"; then
      deep_cut_ids="${deep_cut_ids}${tid}\n"
    fi
  done
done

# Take up to 10 deep cuts
deep_cut_ids=$(echo -e "$deep_cut_ids" | grep -v '^\s*$' | head -10)
deep_count=$(echo "$deep_cut_ids" | grep -c -v '^\s*$' 2>/dev/null || echo 0)
echo "  Got ${deep_count} deep cuts" >&2

# ── Combine: top songs first, then deep cuts ─────────────────────
TMPIDS=$(mktemp /tmp/concert_ids_XXXXXX.txt)
{
  echo "$top_ids"
  echo "$deep_cut_ids"
} | grep -v '^\s*$' > "$TMPIDS"

total=$(grep -c -v '^\s*$' "$TMPIDS" 2>/dev/null || echo 0)
if [[ "$total" -eq 0 ]]; then
  echo "ERROR: No tracks found for ${artist_name}" >&2
  rm -f "$TMPIDS"
  exit 1
fi

echo "🎧 Building playlist: ${PLAYLIST_NAME} (${total} tracks)" >&2

# ── Create playlist description ──────────────────────────────────
DESC="Get ready for ${artist_name} live. ${top_count} essential tracks + ${deep_count} deep cuts to know before the show."

# ── Build and create ─────────────────────────────────────────────
"$SCRIPT_DIR/build_playlist.sh" create "$PLAYLIST_NAME" "$DESC" "$TMPIDS"
rm -f "$TMPIDS"

echo "" >&2
echo "✅ Concert prep playlist created!" >&2
echo "  ${total} tracks: ${top_count} hits + ${deep_count} deep cuts" >&2
echo "  Listen through before the show 🎤" >&2
