"""Tests for feedback.py — ratings and profile updates."""

import json
import sys

import pytest

import feedback as fb

HISTORY = [
    {"name": "Deep Cuts", "track_ids": ["old1", "old2"]},
    {"name": "Chill Mix", "track_ids": ["c1", "c2", "c3"]},
    {"name": "Deep Cuts", "track_ids": ["d1", "d2", "d3"]},  # newer duplicate name
]


@pytest.fixture
def history(monkeypatch):
    monkeypatch.setattr(fb, "load_history", lambda: HISTORY)


class TestResolvePositions:
    def test_named_playlist_uses_newest_match(self, history):
        assert fb.resolve_positions("deep cuts", [1, 3]) == ["d1", "d3"]

    def test_defaults_to_newest_playlist(self, history):
        assert fb.resolve_positions(None, [2]) == ["d2"]

    def test_unknown_name(self, history):
        with pytest.raises(ValueError, match="No playlist named"):
            fb.resolve_positions("Nope", [1])

    @pytest.mark.parametrize("pos", [0, 4, -1])
    def test_out_of_range(self, history, pos):
        with pytest.raises(ValueError, match="out of range"):
            fb.resolve_positions("Chill Mix", [pos])

    def test_empty_history(self, monkeypatch):
        monkeypatch.setattr(fb, "load_history", lambda: [])
        with pytest.raises(ValueError, match="No playlists"):
            fb.resolve_positions(None, [1])


class TestApplyToProfile:
    def test_dislike_moves_from_loved(self):
        p = fb.apply_to_profile({"loved_track_ids": ["a", "b"], "disliked_song_ids": []}, "dislike", ["a", "c"])
        assert p["loved_track_ids"] == ["b"] and p["disliked_song_ids"] == ["a", "c"]

    def test_like_moves_from_disliked_and_dedupes(self):
        p = fb.apply_to_profile({"loved_track_ids": ["a"], "disliked_song_ids": ["b"]}, "like", ["b", "a"])
        assert p["loved_track_ids"] == ["a", "b"] and p["disliked_song_ids"] == []

    def test_clear_removes_from_both(self):
        p = fb.apply_to_profile({"loved_track_ids": ["a"], "disliked_song_ids": ["b"]}, "clear", ["a", "b"])
        assert p["loved_track_ids"] == [] and p["disliked_song_ids"] == []

    def test_missing_keys(self):
        p = fb.apply_to_profile({}, "dislike", ["x"])
        assert p["disliked_song_ids"] == ["x"] and p["loved_track_ids"] == []


class TestRunRating:
    @pytest.fixture
    def profile_file(self, tmp_path):
        path = tmp_path / "profile.json"
        path.write_text(json.dumps({"loved_track_ids": ["s1"], "disliked_song_ids": [], "keep": 1}))
        return path

    def test_dislike_calls_rate_and_updates_profile(self, monkeypatch, profile_file):
        calls = []
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: calls.append((a, k)) or "")
        out = fb.run_rating("dislike", ["s1", "s2"], str(profile_file))
        assert calls == [(("rate", "s1", "-1", "--yes"), {"raw": True}), (("rate", "s2", "-1", "--yes"), {"raw": True})]
        assert out["profile_updated"] is True
        saved = json.loads(profile_file.read_text())
        assert saved["disliked_song_ids"] == ["s1", "s2"] and saved["loved_track_ids"] == []
        assert saved["keep"] == 1
        assert oct(profile_file.stat().st_mode & 0o777) == "0o600"

    def test_like_value(self, monkeypatch):
        calls = []
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: calls.append(a) or "{}")
        fb.run_rating("like", ["s1"], None)
        assert calls == [("rate", "s1", "1", "--yes")]

    def test_clear_uses_unrate(self, monkeypatch):
        calls = []
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: calls.append(a) or "")
        fb.run_rating("clear", ["s1"], None)
        assert calls == [("unrate", "s1", "--yes")]

    def test_failed_calls_do_not_touch_profile(self, monkeypatch, profile_file):
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: None)
        before = profile_file.read_text()
        out = fb.run_rating("dislike", ["s1"], str(profile_file))
        assert out["results"] == [{"id": "s1", "ok": False}] and out["profile_updated"] is False
        assert profile_file.read_text() == before

    def test_partial_failure_only_updates_successes(self, monkeypatch, profile_file):
        monkeypatch.setattr(fb, "call_api", lambda cmd, sid, *a, **k: "" if sid == "s2" else None)
        fb.run_rating("dislike", ["s1", "s2"], str(profile_file))
        assert json.loads(profile_file.read_text())["disliked_song_ids"] == ["s2"]


class TestTrackInfo:
    def test_info(self, monkeypatch):
        monkeypatch.setattr(fb, "call_api", lambda cmd, sf, sid, **k:
            {"data": [{"attributes": {"name": "Creep", "artistName": "Radiohead"}}]} if sid == "s1" else None)
        assert fb.track_info(["s1", "s2"], "us") == [
            {"id": "s1", "name": "Creep", "artist": "Radiohead"},
            {"id": "s2", "name": None, "artist": None},
        ]


class TestMain:
    def _run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["feedback.py", *argv])
        monkeypatch.setattr(fb, "require_env_tokens", lambda: None)
        fb.main()

    def test_dislike_by_position(self, monkeypatch, history, capsys):
        rated = []
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: rated.append(a) or "")
        self._run(monkeypatch, "dislike", "--playlist-name", "Chill Mix", "--position", "2", "--yes")
        assert rated == [("rate", "c2", "-1", "--yes")]
        assert json.loads(capsys.readouterr().out)["results"] == [{"id": "c2", "ok": True}]

    def test_ids_and_positions_combine(self, monkeypatch, history):
        rated = []
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: rated.append(a[1]) or "")
        self._run(monkeypatch, "like", "x1", "--position", "1", "--yes")
        assert rated == ["x1", "d1"]

    def test_failure_exits_nonzero(self, monkeypatch):
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: None)
        with pytest.raises(SystemExit) as e:
            self._run(monkeypatch, "dislike", "s1", "--yes")
        assert e.value.code == 1

    def test_without_yes_nothing_is_rated(self, monkeypatch, capsys):
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: pytest.fail("preview must not call the API"))
        self._run(monkeypatch, "dislike", "s1")
        out = json.loads(capsys.readouterr().out)
        assert out["applied"] is False and out["song_ids"] == ["s1"]

    def test_preview_needs_no_credentials(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["feedback.py", "dislike", "s1"])
        monkeypatch.setattr(fb, "require_env_tokens", lambda: pytest.fail("a preview makes no API call"))
        fb.main()
        assert json.loads(capsys.readouterr().out)["applied"] is False

    def test_info_does_not_rate(self, monkeypatch, capsys):
        monkeypatch.setattr(fb, "call_api", lambda cmd, *a, **k:
            {"data": [{"attributes": {"name": "N", "artistName": "A"}}]} if cmd == "song-detail"
            else pytest.fail("info must not write"))
        self._run(monkeypatch, "info", "s1")
        assert json.loads(capsys.readouterr().out)[0]["name"] == "N"

    @pytest.mark.parametrize("argv", [
        ["dislike"],                                    # nothing to rate
        ["dislike", "--playlist-name", "Chill Mix"],    # name without position
    ])
    def test_usage_errors(self, monkeypatch, argv):
        with pytest.raises(SystemExit):
            self._run(monkeypatch, *argv)

    def test_bad_position_message(self, monkeypatch, history, capsys):
        with pytest.raises(SystemExit):
            self._run(monkeypatch, "dislike", "--playlist-name", "Chill Mix", "--position", "9")
        assert "out of range" in capsys.readouterr().err

    def test_missing_profile_file(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(fb, "call_api", lambda *a, **k: pytest.fail("should stop before rating"))
        with pytest.raises(SystemExit):
            self._run(monkeypatch, "dislike", "s1", "--profile", str(tmp_path / "nope.json"), "--yes")
        assert "Profile not found" in capsys.readouterr().err
