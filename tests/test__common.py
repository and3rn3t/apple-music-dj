"""Tests for _common.py — load_profile, get_album_tracks."""

import json
import os
import tempfile

import pytest

from _common import get_album_tracks, load_profile


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
