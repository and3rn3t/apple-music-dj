#!/usr/bin/env bash
# build_playlist.sh — Create or update a playlist in Apple Music
#
# Usage:
#   scripts/build_playlist.sh create <name> <description> <song_ids_file>
#   scripts/build_playlist.sh refresh <playlist_id> <song_ids_file>
#
# song_ids_file: one Apple Music catalog song ID per line
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

MODE="${1:?Usage: build_playlist.sh <create|refresh> ...}"

case "$MODE" in
  create)
    NAME="${2:?Usage: build_playlist.sh create <name> <description> <song_ids_file>}"
    DESC="${3:?Usage: build_playlist.sh create <name> <description> <song_ids_file>}"
    IDS_FILE="${4:?Usage: build_playlist.sh create <name> <description> <song_ids_file>}"
    [[ ! -f "$IDS_FILE" ]] && { echo "ERROR: File not found: ${IDS_FILE}" >&2; exit 1; }

    track_count=$(grep -c -v '^\s*$' "$IDS_FILE" 2>/dev/null || echo 0)
    [[ "$track_count" -eq 0 ]] && { echo "ERROR: No song IDs in ${IDS_FILE}" >&2; exit 1; }

    echo "🎧 Creating playlist: ${NAME} (${track_count} tracks)" >&2

    # Build tracks array
    tracks_json=$(grep -v '^\s*$' "$IDS_FILE" | jq -R '{"id": ., "type": "songs"}' | jq -s '.')

    # Build full request
    TMPFILE=$(mktemp /tmp/playlist_create_XXXXXX.json)
    jq -n \
      --arg name "$NAME" \
      --arg desc "$DESC" \
      --argjson tracks "$tracks_json" \
      '{
        "attributes": {"name": $name, "description": $desc},
        "relationships": {"tracks": {"data": $tracks}}
      }' > "$TMPFILE"

    "$SCRIPT_DIR/apple_music_api.sh" create-playlist "$TMPFILE"
    rm -f "$TMPFILE"
    ;;

  refresh)
    PID="${2:?Usage: build_playlist.sh refresh <playlist_id> <song_ids_file>}"
    IDS_FILE="${3:?Usage: build_playlist.sh refresh <playlist_id> <song_ids_file>}"
    [[ ! -f "$IDS_FILE" ]] && { echo "ERROR: File not found: ${IDS_FILE}" >&2; exit 1; }

    track_count=$(grep -c -v '^\s*$' "$IDS_FILE" 2>/dev/null || echo 0)
    [[ "$track_count" -eq 0 ]] && { echo "ERROR: No song IDs in ${IDS_FILE}" >&2; exit 1; }

    echo "🎧 Adding ${track_count} tracks to playlist ${PID}" >&2

    tracks_json=$(grep -v '^\s*$' "$IDS_FILE" | jq -R '{"id": ., "type": "songs"}' | jq -s '.')

    TMPFILE=$(mktemp /tmp/playlist_add_XXXXXX.json)
    jq -n --argjson tracks "$tracks_json" '{"data": $tracks}' > "$TMPFILE"

    "$SCRIPT_DIR/apple_music_api.sh" add-to-playlist "$PID" "$TMPFILE"
    rm -f "$TMPFILE"
    ;;

  *)
    echo "Usage: build_playlist.sh <create|refresh> ..." >&2
    echo "  create <name> <description> <song_ids_file>" >&2
    echo "  refresh <playlist_id> <song_ids_file>" >&2
    exit 1
    ;;
esac
