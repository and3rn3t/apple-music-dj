#!/usr/bin/env python3
"""
_common.py — Shared utilities for Apple Music DJ scripts.

Provides call_api(), load_profile(), and search helpers used across all scripts.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
API_SCRIPT = SCRIPT_DIR / "apple_music_api.sh"

DEFAULT_CONFIG_PATH = Path.home() / ".apple-music-dj" / "config.json"

DEFAULT_CONFIG = {
    "default_storefront": "auto",
    "preferred_genres": [],
    "excluded_artists": [],
    "playlist_size": 30,
    "cache_ttl_hours": 168,
}


def load_config(path: str | None = None) -> dict:
    """Load user configuration from JSON, falling back to defaults.

    If no path is given, looks at ~/.apple-music-dj/config.json.
    Missing keys are filled with defaults; missing file returns all defaults.
    """
    config = dict(DEFAULT_CONFIG)
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return config
    try:
        with open(config_path) as f:
            user_config = json.load(f)
        if not isinstance(user_config, dict):
            print(f"WARN: Config is not a JSON object: {config_path}", file=sys.stderr)
            return config
        config.update(user_config)
        return config
    except json.JSONDecodeError as e:
        print(f"WARN: Invalid JSON in config: {config_path} (line {e.lineno})", file=sys.stderr)
        return config
    except OSError as e:
        print(f"WARN: Could not read config: {e}", file=sys.stderr)
        return config


def save_config(config: dict, path: str | None = None):
    """Write config to JSON with restrictive permissions."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(config_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def require_env_tokens():
    """Verify Apple Music tokens are set. Call before any API usage."""
    import os
    missing = []
    if not os.environ.get("APPLE_MUSIC_DEV_TOKEN"):
        missing.append("APPLE_MUSIC_DEV_TOKEN")
    if not os.environ.get("APPLE_MUSIC_USER_TOKEN"):
        missing.append("APPLE_MUSIC_USER_TOKEN")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}", file=sys.stderr)
        print("  See references/auth-setup.md for configuration steps.", file=sys.stderr)
        sys.exit(1)


def call_api(command: str, *args, raw: bool = False) -> dict | list | str | None:
    """Call apple_music_api.sh and parse JSON output.

    If raw=True, return stdout as a stripped string instead of parsing JSON.
    """
    cmd = [str(API_SCRIPT), command] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            stderr_msg = result.stderr.strip()
            if stderr_msg:
                print(f"WARN: API call '{command}' failed: {stderr_msg}", file=sys.stderr)
            return None
        if raw:
            return result.stdout.strip()
        return json.loads(result.stdout)
    except FileNotFoundError:
        print(f"ERROR: API script not found: {API_SCRIPT}", file=sys.stderr)
        print("  Ensure apple_music_api.sh is in the scripts/ directory.", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"WARN: API call timed out: {command} {' '.join(args)}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"WARN: Malformed JSON from API call: {command}", file=sys.stderr)
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
        print(f"  Parse error at line {e.lineno}, column {e.colno}", file=sys.stderr)
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
