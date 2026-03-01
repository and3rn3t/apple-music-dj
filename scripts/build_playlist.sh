#!/usr/bin/env bash
# build_playlist.sh — Create or update a playlist in Apple Music
#
# Usage:
#   scripts/build_playlist.sh create <name> <description> <song_ids_file>
#   scripts/build_playlist.sh refresh <playlist_id> <song_ids_file>
#
# song_ids_file: one Apple Music catalog song ID per line
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

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

    # Build tracks array (filter blank/whitespace-only lines)
    tracks_json=$(grep -v '^\s*$' "$IDS_FILE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | jq -R '{"id": ., "type": "songs"}' | jq -s '.')

    # Build full request
    TMPFILE=$(mktemp "${TMPDIR:-/tmp}/playlist_create_XXXXXX.json")
    trap 'rm -f "$TMPFILE"' EXIT
    jq -n \
      --arg name "$NAME" \
      --arg desc "$DESC" \
      --argjson tracks "$tracks_json" \
      '{
        "attributes": {"name": $name, "description": $desc},
        "relationships": {"tracks": {"data": $tracks}}
      }' > "$TMPFILE"

    if ! "$SCRIPT_DIR/apple_music_api.sh" create-playlist "$TMPFILE"; then
      echo "ERROR: Failed to create playlist '${NAME}'" >&2
      exit 1
    fi
    ;;

  refresh)
    PID="${2:?Usage: build_playlist.sh refresh <playlist_id> <song_ids_file>}"
    IDS_FILE="${3:?Usage: build_playlist.sh refresh <playlist_id> <song_ids_file>}"
    [[ ! -f "$IDS_FILE" ]] && { echo "ERROR: File not found: ${IDS_FILE}" >&2; exit 1; }

    track_count=$(grep -c -v '^\s*$' "$IDS_FILE" 2>/dev/null || echo 0)
    [[ "$track_count" -eq 0 ]] && { echo "ERROR: No song IDs in ${IDS_FILE}" >&2; exit 1; }

    echo "🎧 Adding ${track_count} tracks to playlist ${PID}" >&2

    tracks_json=$(grep -v '^\s*$' "$IDS_FILE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | jq -R '{"id": ., "type": "songs"}' | jq -s '.')

    TMPFILE=$(mktemp "${TMPDIR:-/tmp}/playlist_add_XXXXXX.json")
    trap 'rm -f "$TMPFILE"' EXIT
    jq -n --argjson tracks "$tracks_json" '{"data": $tracks}' > "$TMPFILE"

    if ! "$SCRIPT_DIR/apple_music_api.sh" add-to-playlist "$PID" "$TMPFILE"; then
      echo "ERROR: Failed to add tracks to playlist ${PID}" >&2
      exit 1
    fi
    ;;

  remove)
    PID="${2:?Usage: build_playlist.sh remove <playlist_id> <song_ids_file>}"
    IDS_FILE="${3:?Usage: build_playlist.sh remove <playlist_id> <song_ids_file>}"
    [[ ! -f "$IDS_FILE" ]] && { echo "ERROR: File not found: ${IDS_FILE}" >&2; exit 1; }

    track_count=$(grep -c -v '^\s*$' "$IDS_FILE" 2>/dev/null || echo 0)
    [[ "$track_count" -eq 0 ]] && { echo "ERROR: No song IDs in ${IDS_FILE}" >&2; exit 1; }

    echo "🎧 Removing ${track_count} tracks from playlist ${PID}" >&2

    tracks_json=$(grep -v '^\s*$' "$IDS_FILE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | jq -R '{"id": ., "type": "songs"}' | jq -s '.')

    TMPFILE=$(mktemp "${TMPDIR:-/tmp}/playlist_remove_XXXXXX.json")
    trap 'rm -f "$TMPFILE"' EXIT
    jq -n --argjson tracks "$tracks_json" '{"data": $tracks}' > "$TMPFILE"

    if ! "$SCRIPT_DIR/apple_music_api.sh" remove-from-playlist "$PID" "$TMPFILE"; then
      echo "ERROR: Failed to remove tracks from playlist ${PID}" >&2
      exit 1
    fi
    ;;

  *)
    echo "Usage: build_playlist.sh <create|refresh|remove> ..." >&2
    echo "  create <name> <description> <song_ids_file>" >&2
    echo "  refresh <playlist_id> <song_ids_file>" >&2
    echo "  remove <playlist_id> <song_ids_file>" >&2
    exit 1
    ;;
esac
