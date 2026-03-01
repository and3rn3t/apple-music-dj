"""Tests for _common.py — load_profile, get_album_tracks, call_api, config, search."""

import json
import os
import subprocess
import tempfile

import pytest

from _common import (
    call_api,
    get_album_tracks,
    load_config,
    load_profile,
    require_env_tokens,
    save_config,
    search_album,
    search_artist,
    DEFAULT_CONFIG,
)


# ── load_profile ─────────────────────────────────────────────────

class TestLoadProfile:
    def test_loads_valid_json(self, tmp_path):
        data = {"genre_distribution": [{"genre": "Rock", "weight": 0.5}]}
        f = tmp_path / "profile.json"
        f.write_text(json.dumps(data))
        result = load_profile(str(f))
        assert result == data

    def test_file_not_found_exits(self):
        with pytest.raises(SystemExit):
            load_profile("/nonexistent/path/profile.json")

    def test_invalid_json_exits(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{invalid json")
        with pytest.raises(SystemExit):
            load_profile(str(f))

    def test_empty_object(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("{}")
        assert load_profile(str(f)) == {}

    def test_returns_dict(self, tmp_path):
        data = {"key": "value"}
        f = tmp_path / "p.json"
        f.write_text(json.dumps(data))
        assert isinstance(load_profile(str(f)), dict)


# ── get_album_tracks ─────────────────────────────────────────────

class TestGetAlbumTracks:
    """Test the data-flattening logic of get_album_tracks.

    Since get_album_tracks calls call_api internally, we mock call_api.
    """

    def test_flattens_nested_tracks(self, monkeypatch):
        mock_data = {
            "data": [
                {
                    "relationships": {
                        "tracks": {
                            "data": [
                                {"id": "t1", "attributes": {"name": "Song 1"}},
                                {"id": "t2", "attributes": {"name": "Song 2"}},
                            ]
                        }
                    }
                }
            ]
        }
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: mock_data)
        tracks = get_album_tracks("us", "album123")
        assert len(tracks) == 2
        assert tracks[0]["id"] == "t1"

    def test_multiple_albums(self, monkeypatch):
        mock_data = {
            "data": [
                {"relationships": {"tracks": {"data": [{"id": "t1"}]}}},
                {"relationships": {"tracks": {"data": [{"id": "t2"}]}}},
            ]
        }
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: mock_data)
        tracks = get_album_tracks("us", "album123")
        assert len(tracks) == 2

    def test_api_returns_none(self, monkeypatch):
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: None)
        assert get_album_tracks("us", "album123") == []

    def test_missing_data_key(self, monkeypatch):
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: {"results": []})
        assert get_album_tracks("us", "album123") == []

    def test_missing_relationships(self, monkeypatch):
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: {"data": [{}]})
        tracks = get_album_tracks("us", "album123")
        assert tracks == []

    def test_empty_tracks(self, monkeypatch):
        mock_data = {
            "data": [
                {"relationships": {"tracks": {"data": []}}}
            ]
        }
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: mock_data)
        assert get_album_tracks("us", "album123") == []


# ── require_env_tokens ───────────────────────────────────────────

class TestRequireEnvTokens:
    def test_exits_when_dev_token_missing(self, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_DEV_TOKEN", raising=False)
        monkeypatch.delenv("APPLE_MUSIC_USER_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            require_env_tokens()

    def test_exits_when_user_token_missing(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", "test_dev")
        monkeypatch.delenv("APPLE_MUSIC_USER_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            require_env_tokens()

    def test_passes_when_both_set(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", "test_dev")
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "test_user")
        require_env_tokens()  # should not raise


# ── call_api ─────────────────────────────────────────────────────

class TestCallApi:
    def test_returns_parsed_json(self, monkeypatch):
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"data": []}', stderr=""
        )
        monkeypatch.setattr("_common.subprocess.run", lambda *a, **kw: mock_result)
        result = call_api("recent-tracks")
        assert result == {"data": []}

    def test_returns_raw_string(self, monkeypatch):
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="us\n", stderr=""
        )
        monkeypatch.setattr("_common.subprocess.run", lambda *a, **kw: mock_result)
        result = call_api("user-storefront", raw=True)
        assert result == "us"

    def test_returns_none_on_nonzero_exit(self, monkeypatch):
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error"
        )
        monkeypatch.setattr("_common.subprocess.run", lambda *a, **kw: mock_result)
        assert call_api("verify") is None

    def test_returns_none_on_timeout(self, monkeypatch):
        def mock_run(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="test", timeout=30)
        monkeypatch.setattr("_common.subprocess.run", mock_run)
        assert call_api("slow-command") is None

    def test_returns_none_on_malformed_json(self, monkeypatch):
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json{", stderr=""
        )
        monkeypatch.setattr("_common.subprocess.run", lambda *a, **kw: mock_result)
        assert call_api("broken") is None

    def test_returns_none_on_missing_script(self, monkeypatch):
        def mock_run(*a, **kw):
            raise FileNotFoundError("No such file")
        monkeypatch.setattr("_common.subprocess.run", mock_run)
        assert call_api("any") is None


# ── search_artist ────────────────────────────────────────────────

class TestSearchArtist:
    def test_returns_first_match(self, monkeypatch):
        mock = {
            "results": {
                "artists": {
                    "data": [
                        {"id": "a1", "attributes": {"name": "Radiohead"}},
                        {"id": "a2", "attributes": {"name": "Radiohead Tribute"}},
                    ]
                }
            }
        }
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: mock)
        result = search_artist("us", "Radiohead")
        assert result["id"] == "a1"

    def test_returns_none_on_no_results(self, monkeypatch):
        mock = {"results": {"artists": {"data": []}}}
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: mock)
        assert search_artist("us", "nobody") is None

    def test_returns_none_on_api_failure(self, monkeypatch):
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: None)
        assert search_artist("us", "test") is None


# ── search_album ─────────────────────────────────────────────────

class TestSearchAlbum:
    def test_returns_first_match(self, monkeypatch):
        mock = {
            "results": {
                "albums": {
                    "data": [
                        {"id": "alb1", "attributes": {"name": "OK Computer"}},
                    ]
                }
            }
        }
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: mock)
        result = search_album("us", "OK Computer")
        assert result["id"] == "alb1"

    def test_returns_none_on_empty(self, monkeypatch):
        mock = {"results": {"albums": {"data": []}}}
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: mock)
        assert search_album("us", "nothing") is None

    def test_returns_none_on_api_failure(self, monkeypatch):
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: None)
        assert search_album("us", "test") is None


# ── load_config / save_config ────────────────────────────────────

class TestConfig:
    def test_defaults_when_no_file(self, tmp_path):
        result = load_config(str(tmp_path / "nonexistent.json"))
        assert result == DEFAULT_CONFIG

    def test_loads_valid_config(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"default_storefront": "gb", "playlist_size": 50}))
        result = load_config(str(cfg))
        assert result["default_storefront"] == "gb"
        assert result["playlist_size"] == 50
        # Defaults still present for unset keys
        assert result["preferred_genres"] == []

    def test_invalid_json_returns_defaults(self, tmp_path):
        cfg = tmp_path / "bad.json"
        cfg.write_text("{broken")
        result = load_config(str(cfg))
        assert result == DEFAULT_CONFIG

    def test_non_dict_returns_defaults(self, tmp_path):
        cfg = tmp_path / "list.json"
        cfg.write_text("[1, 2, 3]")
        result = load_config(str(cfg))
        assert result == DEFAULT_CONFIG

    def test_save_and_load_roundtrip(self, tmp_path):
        cfg_path = str(tmp_path / "config.json")
        config = {"default_storefront": "jp", "playlist_size": 25,
                  "preferred_genres": ["Rock"], "excluded_artists": [],
                  "cache_ttl_hours": 72}
        save_config(config, cfg_path)
        loaded = load_config(cfg_path)
        assert loaded["default_storefront"] == "jp"
        assert loaded["playlist_size"] == 25

    def test_save_creates_directory(self, tmp_path):
        cfg_path = str(tmp_path / "subdir" / "config.json")
        save_config({"default_storefront": "us"}, cfg_path)
        assert os.path.exists(cfg_path)

    def test_saved_file_permissions(self, tmp_path):
        cfg_path = str(tmp_path / "config.json")
        save_config(DEFAULT_CONFIG, cfg_path)
        mode = os.stat(cfg_path).st_mode & 0o777
        assert mode == 0o600
