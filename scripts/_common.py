#!/usr/bin/env python3
"""
_common.py — Shared utilities for Apple Music DJ scripts.

Provides call_api(), load_profile(), and search helpers used across all scripts.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
API_SCRIPT = SCRIPT_DIR / "apple_music_api.sh"


def call_api(command: str, *args, raw: bool = False) -> dict | list | str | None:
    """Call apple_music_api.sh and parse JSON output.

    If raw=True, return stdout as a stripped string instead of parsing JSON.
    """
    cmd = [str(API_SCRIPT), command] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        if raw:
            return result.stdout.strip()
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print(f"WARN: API call timed out: {command} {' '.join(args)}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def load_profile(path: str) -> dict:
    """Load a taste profile JSON with user-friendly error handling."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Profile not found: {path}", file=sys.stderr)
        print("  Run the taste profiler first: python3 scripts/taste_profiler.py", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in profile: {path}", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        print("  Try regenerating: python3 scripts/taste_profiler.py --max-age 0", file=sys.stderr)
        sys.exit(1)


def search_artist(sf: str, name: str) -> dict | None:
    """Search for an artist by name and return the top match."""
    result = call_api("search", sf, name, "artists")
    if not result:
        return None
    artists = result.get("results", {}).get("artists", {}).get("data", [])
    return artists[0] if artists else None


def search_album(sf: str, query: str) -> dict | None:
    """Search for an album by name and return the top match."""
    result = call_api("search", sf, query, "albums")
    if not result:
        return None
    albums = result.get("results", {}).get("albums", {}).get("data", [])
    return albums[0] if albums else None


def get_album_tracks(sf: str, album_id: str) -> list:
    """Fetch tracks for an album, returning a flat list of track dicts."""
    detail = call_api("album-tracks", sf, album_id)
    if not detail or "data" not in detail:
        return []
    tracks = []
    for album_data in detail.get("data", []):
        track_rel = album_data.get("relationships", {}).get("tracks", {}).get("data", [])
        tracks.extend(track_rel)
    return tracks
