"""Tests for _common.py — load_profile, get_album_tracks, call_api, config, search."""

import base64
import json
import os
import subprocess
import time

import pytest

from _common import (
    call_api,
    check_token_expiry,
    filter_generic_genres,
    get_album_tracks,
    get_storefront,
    load_config,
    load_profile,
    require_env_tokens,
    save_config,
    track_energy,
    GENRE_ENERGY,
    MAX_SNAPSHOTS,
    list_snapshots,
    make_snapshot,
    save_snapshot,
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


# ── filter_generic_genres ────────────────────────────────────────

class TestFilterGenericGenres:
    def test_removes_music(self):
        assert filter_generic_genres(["Rock", "Music", "Pop"]) == ["Rock", "Pop"]

    def test_case_insensitive(self):
        assert filter_generic_genres(["MUSIC", "music", "Rock"]) == ["Rock"]

    def test_empty_list(self):
        assert filter_generic_genres([]) == []

    def test_no_generic(self):
        assert filter_generic_genres(["Rock", "Pop"]) == ["Rock", "Pop"]

    def test_all_generic(self):
        assert filter_generic_genres(["Music"]) == []


# ── check_token_expiry ───────────────────────────────────────────

class TestCheckTokenExpiry:
    def _make_token(self, exp_offset_secs):
        """Create a fake JWT with given expiry offset from now."""
        header = base64.urlsafe_b64encode(b'{"alg":"ES256"}').rstrip(b"=").decode()
        payload_dict = {"iss": "team", "iat": int(time.time()), "exp": int(time.time()) + exp_offset_secs}
        payload = base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).rstrip(b"=").decode()
        return f"{header}.{payload}.fakesig"

    def test_returns_none_when_no_token(self, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_DEV_TOKEN", raising=False)
        assert check_token_expiry() is None

    def test_valid_token(self, monkeypatch):
        token = self._make_token(90 * 86400)  # 90 days
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", token)
        result = check_token_expiry()
        assert result is not None
        assert result["expired"] is False
        assert result["warning"] is False
        assert result["days_remaining"] > 14

    def test_expiring_soon_warns(self, monkeypatch):
        token = self._make_token(5 * 86400)  # 5 days
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", token)
        result = check_token_expiry(warn_days=14)
        assert result["expired"] is False
        assert result["warning"] is True

    def test_expired_token(self, monkeypatch):
        token = self._make_token(-86400)  # expired yesterday
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", token)
        result = check_token_expiry()
        assert result["expired"] is True
        assert result["warning"] is True

    def test_malformed_token(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", "not-a-jwt")
        assert check_token_expiry() is None

    def test_token_without_exp(self, monkeypatch):
        header = base64.urlsafe_b64encode(b'{"alg":"ES256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(b'{"iss":"team"}').rstrip(b"=").decode()
        token = f"{header}.{payload}.sig"
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", token)
        assert check_token_expiry() is None


# ── get_storefront ───────────────────────────────────────────────

class TestGetStorefront:
    def test_explicit_override(self):
        assert get_storefront("gb") == "gb"

    def test_auto_falls_through(self, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_STOREFRONT", raising=False)
        monkeypatch.setattr("_common.STOREFRONT_CACHE", type("P", (), {
            "exists": lambda self: False,
        })())
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: None)
        result = get_storefront("auto")
        assert result == "us"  # fallback

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_STOREFRONT", "de")
        assert get_storefront() == "de"

    def test_cache_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_STOREFRONT", raising=False)
        cache = tmp_path / "storefront.cache"
        cache.write_text("jp\n")
        monkeypatch.setattr("_common.STOREFRONT_CACHE", cache)
        assert get_storefront() == "jp"

    def test_invalid_cache_ignored(self, tmp_path, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_STOREFRONT", raising=False)
        cache = tmp_path / "storefront.cache"
        cache.write_text("invalid_long_string\n")
        monkeypatch.setattr("_common.STOREFRONT_CACHE", cache)
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: None)
        result = get_storefront()
        assert result == "us"

    def test_api_detection(self, tmp_path, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_STOREFRONT", raising=False)
        cache = tmp_path / "storefront.cache"
        monkeypatch.setattr("_common.STOREFRONT_CACHE", cache)
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: "fr")
        result = get_storefront()
        assert result == "fr"
        # Should have cached
        assert cache.read_text().strip() == "fr"

    def test_api_returns_invalid(self, tmp_path, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_STOREFRONT", raising=False)
        cache = tmp_path / "storefront.cache"
        monkeypatch.setattr("_common.STOREFRONT_CACHE", cache)
        monkeypatch.setattr("_common.call_api", lambda *a, **kw: "invalid")
        result = get_storefront()
        assert result == "us"


class TestTrackEnergy:
    def test_unknown_genres_default_to_mid(self):
        assert track_energy([]) == 0.5
        assert track_energy(["Polka"]) == 0.5

    def test_averages_known_genres(self):
        assert track_energy(["Metal", "Ambient"]) == pytest.approx((0.95 + 0.1) / 2)

    def test_ignores_unknown_when_mixed(self):
        assert track_energy(["Rock", "Polka"]) == GENRE_ENERGY["Rock"]

    def test_all_values_in_range(self):
        assert all(0.0 <= v <= 1.0 for v in GENRE_ENERGY.values())


class TestSnapshots:
    def _profile(self, day="2026-03-02"):
        return {
            "top_artists": [{"name": "Radiohead", "id": "a1", "count": 5, "play_weight": 0.2}],
            "genre_distribution": [{"genre": "Rock", "count": 9, "weight": 0.9}],
            "era_distribution": [{"decade": "2000s", "count": 3, "weight": 1.0}],
            "energy_profile": "chill", "variety_score": 0.4, "mainstream_score": 0.2,
            "library_song_ids": ["secret1"], "loved_track_ids": ["secret2"],
            "generated_at": f"{day}T08:00:00+00:00",
        }

    def test_make_snapshot_drops_ids(self):
        snap = make_snapshot(self._profile())
        assert "secret1" not in json.dumps(snap) and "a1" not in json.dumps(snap)
        assert snap["top_artists"] == [{"name": "Radiohead", "weight": 0.2}]

    def test_save_uses_date_name_and_private_perms(self, tmp_path):
        path = save_snapshot(self._profile(), tmp_path / "snaps")
        assert path.name == "2026-03-02.json"
        assert oct(path.stat().st_mode & 0o777) == "0o600"
        assert json.loads(path.read_text())["energy_profile"] == "chill"

    def test_same_day_overwrites(self, tmp_path):
        save_snapshot(self._profile(), tmp_path)
        p = self._profile()
        p["energy_profile"] = "high-energy"
        save_snapshot(p, tmp_path)
        assert len(list_snapshots(tmp_path)) == 1
        assert json.loads((tmp_path / "2026-03-02.json").read_text())["energy_profile"] == "high-energy"

    def test_prunes_to_max(self, tmp_path):
        for i in range(MAX_SNAPSHOTS + 3):
            (tmp_path / f"2025-01-{i + 1:02d}.json" if i < 28 else tmp_path / f"2025-02-{i - 27:02d}.json").write_text("{}")
        save_snapshot(self._profile("2026-03-02"), tmp_path)
        snaps = list_snapshots(tmp_path)
        assert len(snaps) == MAX_SNAPSHOTS
        assert snaps[-1][0] == "2026-03-02"
        assert snaps[0][0] != "2025-01-01"

    def test_list_ignores_other_files_and_missing_dir(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")
        assert list_snapshots(tmp_path) == []
        assert list_snapshots(tmp_path / "nope") == []
