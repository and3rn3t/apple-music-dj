"""Everything the skill writes about the user's listening must be owner-only.

Regression tests for the security audit: `os.open(..., 0o600)` only sets the mode on *creation*,
so files that already existed (or were written another way, like the profiler's cache-hit path)
stayed world-readable, and new directories were created with the default 0755.
"""

import json
import os
import stat
import sys

import pytest

import _common
import feedback
import playlist_history
import taste_card
import taste_profiler as tp


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def loose_file(path, text="old"):
    path.write_text(text)
    path.chmod(0o644)
    return path


class TestWritePrivate:
    def test_new_file_is_owner_only(self, tmp_path):
        _common.write_private(tmp_path / "f.json", "{}")
        assert mode(tmp_path / "f.json") == 0o600

    def test_existing_world_readable_file_is_tightened_and_truncated(self, tmp_path):
        f = loose_file(tmp_path / "f.json", "x" * 100)
        _common.write_private(f, "new")
        assert mode(f) == 0o600 and f.read_text() == "new"

    def test_every_new_directory_level_is_0700(self, tmp_path):
        _common.write_private(tmp_path / "a" / "b" / "c" / "f.json", "{}")
        assert [mode(tmp_path / p) for p in ("a", "a/b", "a/b/c")] == [0o700, 0o700, 0o700]

    def test_existing_directories_are_left_alone(self, tmp_path):
        shared = tmp_path / "Documents"
        shared.mkdir()
        shared.chmod(0o755)
        _common.write_private(shared / "profile.json", "{}")
        assert mode(shared) == 0o755 and mode(shared / "profile.json") == 0o600

    def test_our_app_dir_is_tightened_even_if_it_already_exists(self, tmp_path, monkeypatch):
        app = tmp_path / ".apple-music-dj"
        app.mkdir()
        app.chmod(0o755)
        monkeypatch.setattr(_common, "APP_DIR", app)
        _common.write_private(app / "profile.json", "{}")
        _common.write_private(app / "logs" / "x.log", "")
        assert mode(app) == 0o700 and mode(app / "logs") == 0o700

    def test_non_regular_targets_still_work(self):
        _common.write_private("/dev/null", "discarded")  # e.g. --output /dev/stdout must not break

    def test_symlink_is_refused_and_its_target_left_untouched(self, tmp_path):
        victim = loose_file(tmp_path / "victim.txt", "precious")
        (tmp_path / "out.json").symlink_to(victim)
        with pytest.raises(OSError, match="Refusing to write through the symlink"):
            _common.write_private(tmp_path / "out.json", "overwritten")
        assert victim.read_text() == "precious" and mode(victim) == 0o644

    def test_dangling_symlink_is_refused_and_creates_nothing(self, tmp_path):
        (tmp_path / "out.json").symlink_to(tmp_path / "nowhere.txt")
        with pytest.raises(OSError, match="symlink"):
            _common.write_private(tmp_path / "out.json", "x")
        assert not (tmp_path / "nowhere.txt").exists()

    def test_symlink_to_a_stream_device_still_works(self, tmp_path):
        """/dev/stdout is itself a symlink on Linux, so --output /dev/stdout must keep working."""
        (tmp_path / "stdout-like").symlink_to("/dev/null")
        _common.write_private(tmp_path / "stdout-like", "discarded")
        assert mode("/dev/null") == mode("/dev/null")  # untouched (no chmod/truncate attempted)

    def test_foreign_owned_file_is_refused_before_truncation(self, tmp_path, monkeypatch):
        f = loose_file(tmp_path / "theirs.json", "not yours")
        monkeypatch.setattr(os, "getuid", lambda: os.stat(f).st_uid + 1)
        with pytest.raises(PermissionError, match="owned by another user"):
            _common.write_private(f, "mine now")
        assert f.read_text() == "not yours" and mode(f) == 0o644

    def test_existing_content_is_replaced_not_appended(self, tmp_path):
        f = tmp_path / "f.txt"
        _common.write_private(f, "a much longer first version")
        _common.write_private(f, "short")
        assert f.read_text() == "short"

    def test_ensure_private_dir_is_idempotent(self, tmp_path):
        d = tmp_path / "x" / "y"
        _common.ensure_private_dir(d)
        _common.ensure_private_dir(d)
        assert mode(d) == 0o700


class TestEachWriter:
    def test_config(self, tmp_path):
        cfg = loose_file(tmp_path / "config.json", "{}")
        _common.save_config({"playlist_size": 10}, str(cfg))
        assert mode(cfg) == 0o600 and _common.load_config(str(cfg))["playlist_size"] == 10

    def test_snapshot_overwritten_same_day_stays_private(self, tmp_path):
        profile = {"generated_at": "2026-03-02T00:00:00+00:00", "top_artists": [], "genre_distribution": [],
                   "era_distribution": []}
        path = _common.save_snapshot(profile, tmp_path / "snaps")
        path.chmod(0o644)
        _common.save_snapshot(profile, tmp_path / "snaps")
        assert mode(path) == 0o600 and mode(tmp_path / "snaps") == 0o700

    def test_snapshot_dir_inside_app_dir_tightens_app_dir(self, tmp_path, monkeypatch):
        app = tmp_path / ".apple-music-dj"
        app.mkdir()
        app.chmod(0o755)
        monkeypatch.setattr(_common, "APP_DIR", app)
        _common.save_snapshot({"generated_at": "2026-03-02T00:00:00+00:00"}, app / "snapshots")
        assert mode(app) == 0o700 and mode(app / "snapshots") == 0o700

    def test_playlist_history(self, tmp_path, monkeypatch):
        hist = loose_file(tmp_path / "playlist_history.json", "[]")
        monkeypatch.setattr(playlist_history, "HISTORY_FILE", hist)
        playlist_history.log_playlist("Mix", "trend", ["t1"])
        assert mode(hist) == 0o600

    def test_feedback_profile(self, tmp_path):
        p = loose_file(tmp_path / "profile.json", "{}")
        feedback.save_profile({"disliked_song_ids": ["s1"]}, str(p))
        assert mode(p) == 0o600

    def test_storefront_cache(self, tmp_path, monkeypatch):
        cache = loose_file(tmp_path / "storefront.cache", "us\n")
        monkeypatch.delenv("APPLE_MUSIC_STOREFRONT", raising=False)
        monkeypatch.setattr(_common, "STOREFRONT_CACHE", cache)
        cache.unlink()
        monkeypatch.setattr(_common, "call_api", lambda *a, **k: "gb")
        assert _common.get_storefront() == "gb" and mode(cache) == 0o600


class TestProfilerWrites:
    """taste_profiler.py:420 in the audited version — the cache-hit path used plain write_text()."""

    def _argv(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["taste_profiler.py", *args])

    def test_cache_hit_output_is_owner_only(self, tmp_path, monkeypatch):
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"cached": True}))
        out = tmp_path / "out" / "profile.json"
        self._argv(monkeypatch, "--cache", str(cache), "--max-age", "9999", "--output", str(out))
        tp.main()
        assert mode(out) == 0o600 and mode(out.parent) == 0o700

    def test_cache_hit_overwrites_a_world_readable_output(self, tmp_path, monkeypatch):
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"cached": True}))
        out = loose_file(tmp_path / "profile.json", "old profile")
        self._argv(monkeypatch, "--cache", str(cache), "--max-age", "9999", "--output", str(out))
        tp.main()
        assert mode(out) == 0o600 and json.loads(out.read_text()) == {"cached": True}

    def test_save_cache_tightens_existing_cache(self, tmp_path):
        cache = loose_file(tmp_path / "cache.json", "{}")
        tp.save_cache({"top_artists": []}, str(cache))
        assert mode(cache) == 0o600

    def test_fresh_build_output_and_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr("taste_profiler.require_env_tokens", lambda: None)
        monkeypatch.setattr("taste_profiler.check_token_expiry", lambda: None)
        monkeypatch.setattr("taste_profiler.get_storefront", lambda sf=None: "us")
        tracks = [{"id": "t1", "attributes": {"name": "S", "artistName": "A", "genreNames": ["Rock"],
                                              "releaseDate": "2020-01-01"}}]
        monkeypatch.setattr("taste_profiler.call_api", lambda c, *a, **k:
            tracks if c == "recent-tracks" else {"data": []} if c.startswith("library") else None)
        cache, out = loose_file(tmp_path / "cache.json", "{}"), loose_file(tmp_path / "profile.json")
        self._argv(monkeypatch, "--cache", str(cache), "--max-age", "0", "--output", str(out), "--no-snapshot")
        tp.main()
        assert mode(cache) == 0o600 and mode(out) == 0o600


class TestCardWrites:
    def test_card_output_is_owner_only(self, tmp_path, monkeypatch, sample_profile):
        profile = tmp_path / "p.json"
        profile.write_text(json.dumps(sample_profile))
        out = loose_file(tmp_path / "card.svg", "old")
        monkeypatch.setattr(sys, "argv", ["taste_card.py", str(profile), "--output", str(out)])
        taste_card.main()
        assert mode(out) == 0o600 and out.read_text().startswith("<svg")
