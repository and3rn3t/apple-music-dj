"""Tests for playlist_health.py — playlist health checking and maintenance."""

import sys
from unittest.mock import MagicMock

import pytest

import playlist_health as phealth


# ── check_playlist ───────────────────────────────────────────────

class TestCheckPlaylist:
    def test_returns_error_when_no_tracks(self, monkeypatch):
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: None)
        result = phealth.check_playlist("pl1", "us")
        assert result["error"] == "Could not fetch playlist tracks"
        assert result["total_tracks"] == 0

    def test_returns_error_when_no_data_key(self, monkeypatch):
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: {"no": "data"})
        result = phealth.check_playlist("pl1", "us")
        assert "error" in result

    def test_healthy_playlist(self, monkeypatch):
        tracks = [
            {
                "id": "t1",
                "attributes": {"name": "Song A", "artistName": "Artist A"},
                "relationships": {"catalog": {"data": [{"id": "cat1"}]}},
            },
        ]

        def mock_api(command, *args, **kwargs):
            if command == "playlist-tracks":
                return {"data": tracks}
            elif command == "song-detail":
                return {"data": [{"id": "cat1"}]}
            return None

        monkeypatch.setattr("playlist_health.call_api", mock_api)
        result = phealth.check_playlist("pl1", "us")
        assert result["healthy"] is True
        assert result["removed_count"] == 0
        assert result["duplicate_count"] == 0
        assert result["total_tracks"] == 1

    def test_detects_removed_tracks(self, monkeypatch):
        tracks = [
            {
                "id": "t1",
                "attributes": {"name": "Gone Song", "artistName": "Artist A"},
                "relationships": {"catalog": {"data": [{"id": "cat1"}]}},
            },
        ]

        def mock_api(command, *args, **kwargs):
            if command == "playlist-tracks":
                return {"data": tracks}
            elif command == "song-detail":
                return {"data": []}  # track not found
            return None

        monkeypatch.setattr("playlist_health.call_api", mock_api)
        result = phealth.check_playlist("pl1", "us")
        assert result["removed_count"] == 1
        assert result["removed"][0]["name"] == "Gone Song"
        assert result["healthy"] is False

    def test_detects_duplicates(self, monkeypatch):
        tracks = [
            {
                "id": "t1",
                "attributes": {"name": "Song A", "artistName": "A"},
                "relationships": {"catalog": {"data": [{"id": "cat1"}]}},
            },
            {
                "id": "t2",
                "attributes": {"name": "Song A", "artistName": "A"},
                "relationships": {"catalog": {"data": [{"id": "cat1"}]}},
            },
        ]

        def mock_api(command, *args, **kwargs):
            if command == "playlist-tracks":
                return {"data": tracks}
            elif command == "song-detail":
                return {"data": [{"id": "cat1"}]}
            return None

        monkeypatch.setattr("playlist_health.call_api", mock_api)
        result = phealth.check_playlist("pl1", "us")
        assert result["duplicate_count"] == 1
        assert result["duplicates"][0]["count"] == 2

    def test_fallback_to_track_id_when_no_catalog(self, monkeypatch):
        tracks = [
            {
                "id": "t1",
                "attributes": {"name": "Song A", "artistName": "A"},
                "relationships": {},
            },
        ]

        def mock_api(command, *args, **kwargs):
            if command == "playlist-tracks":
                return {"data": tracks}
            elif command == "song-detail":
                return {"data": [{"id": "t1"}]}
            return None

        monkeypatch.setattr("playlist_health.call_api", mock_api)
        result = phealth.check_playlist("pl1", "us")
        assert result["total_tracks"] == 1
        assert result["healthy"] is True


# ── find_replacement ─────────────────────────────────────────────

class TestFindReplacement:
    def test_exact_artist_match(self, monkeypatch):
        search_result = {
            "results": {
                "songs": {
                    "data": [
                        {"id": "new1", "attributes": {"name": "Song A", "artistName": "Artist X"}},
                    ]
                }
            }
        }
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: search_result)
        result = phealth.find_replacement("us", "Song A", "Artist X")
        assert result is not None
        assert result["id"] == "new1"
        assert "approximate" not in result

    def test_approximate_match_when_no_exact(self, monkeypatch):
        search_result = {
            "results": {
                "songs": {
                    "data": [
                        {"id": "new1", "attributes": {"name": "Song A (Live)", "artistName": "Different Artist"}},
                    ]
                }
            }
        }
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: search_result)
        result = phealth.find_replacement("us", "Song A", "Artist X")
        assert result is not None
        assert result["approximate"] is True

    def test_returns_none_when_no_results(self, monkeypatch):
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: {"results": {"songs": {"data": []}}})
        result = phealth.find_replacement("us", "Song A", "Artist X")
        assert result is None

    def test_returns_none_when_api_fails(self, monkeypatch):
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: None)
        result = phealth.find_replacement("us", "Song A", "Artist X")
        assert result is None


# ── cmd_check ────────────────────────────────────────────────────

class TestCmdCheck:
    def test_check_single_playlist(self, monkeypatch):
        def mock_api(command, *args, **kwargs):
            if command == "playlist-tracks":
                return {"data": []}
            return None

        monkeypatch.setattr("playlist_health.call_api", mock_api)
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = None
        result = phealth.cmd_check(args)
        assert result["playlist_id"] == "pl1"

    def test_check_all_playlists(self, monkeypatch):
        def mock_api(command, *args, **kwargs):
            if command == "library-playlists":
                return {"data": [
                    {"id": "pl1", "attributes": {"name": "Mix 1"}},
                    {"id": "pl2", "attributes": {"name": "Mix 2"}},
                ]}
            elif command == "playlist-tracks":
                return {"data": []}
            return None

        monkeypatch.setattr("playlist_health.call_api", mock_api)
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})

        args = MagicMock()
        args.playlist_id = "all"
        args.storefront = None
        result = phealth.cmd_check(args)
        assert result["playlists_checked"] == 2

    def test_check_all_api_failure(self, monkeypatch):
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: None)
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {})

        args = MagicMock()
        args.playlist_id = "all"
        args.storefront = "us"
        result = phealth.cmd_check(args)
        assert "error" in result

    def test_check_uses_storefront_override(self, monkeypatch):
        captured_sf = {}

        def mock_check(pid, sf):
            captured_sf["sf"] = sf
            return {"playlist_id": pid, "total_tracks": 0, "removed": [],
                    "removed_count": 0, "duplicates": [], "duplicate_count": 0, "healthy": True}

        monkeypatch.setattr("playlist_health.check_playlist", mock_check)
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {})

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = "gb"
        phealth.cmd_check(args)
        assert captured_sf["sf"] == "gb"


# ── cmd_fix ──────────────────────────────────────────────────────

class TestCmdFix:
    def test_fix_no_issues(self, monkeypatch):
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "playlist_id": pid, "total_tracks": 5, "removed": [], "removed_count": 0,
            "duplicates": [], "duplicate_count": 0, "healthy": True,
        })

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = None
        args.apply = False
        result = phealth.cmd_fix(args)
        assert result["issues_found"] == 0

    def test_fix_dry_run_duplicates(self, monkeypatch):
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "playlist_id": pid, "total_tracks": 5, "removed": [], "removed_count": 0,
            "duplicates": [{"id": "cat1", "count": 3}], "duplicate_count": 1, "healthy": False,
        })

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = None
        args.apply = False
        result = phealth.cmd_fix(args)
        assert len(result["actions_taken"]) == 1
        assert "WOULD remove" in result["actions_taken"][0]

    def test_fix_auto_duplicates(self, monkeypatch):
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "playlist_id": pid, "total_tracks": 5, "removed": [], "removed_count": 0,
            "duplicates": [{"id": "cat1", "count": 2}], "duplicate_count": 1, "healthy": False,
        })
        monkeypatch.setattr("playlist_health.run_script", lambda *a, **kw: MagicMock(returncode=0))

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = None
        args.apply = True
        result = phealth.cmd_fix(args)
        assert result["applied"] is True and result["auto_applied"] is True
        assert any("Removed" in a for a in result["actions_taken"])

    def test_fix_removed_tracks_dry_run(self, monkeypatch):
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "playlist_id": pid, "total_tracks": 5,
            "removed": [{"id": "cat1", "name": "Gone", "artist": "Artist"}],
            "removed_count": 1, "duplicates": [], "duplicate_count": 0, "healthy": False,
        })
        monkeypatch.setattr("playlist_health.find_replacement", lambda sf, n, a: {
            "id": "new1", "name": "Gone (Remaster)", "artist": "Artist",
        })

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = None
        args.apply = False
        result = phealth.cmd_fix(args)
        assert any("WOULD add" in a and "as a replacement for" in a for a in result["actions_taken"])

    def test_fix_removed_no_replacement(self, monkeypatch):
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "playlist_id": pid, "total_tracks": 5,
            "removed": [{"id": "cat1", "name": "Gone", "artist": "Artist"}],
            "removed_count": 1, "duplicates": [], "duplicate_count": 0, "healthy": False,
        })
        monkeypatch.setattr("playlist_health.find_replacement", lambda sf, n, a: None)

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = None
        args.apply = False
        result = phealth.cmd_fix(args)
        assert any("No replacement" in a for a in result["actions_taken"])

    def test_fix_auto_removed_with_replacement(self, monkeypatch):
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "playlist_id": pid, "total_tracks": 5,
            "removed": [{"id": "cat1", "name": "Gone", "artist": "Artist"}],
            "removed_count": 1, "duplicates": [], "duplicate_count": 0, "healthy": False,
        })
        monkeypatch.setattr("playlist_health.find_replacement", lambda sf, n, a: {
            "id": "new1", "name": "Gone (Remaster)", "artist": "Artist",
        })
        monkeypatch.setattr("playlist_health.run_script", lambda *a, **kw: MagicMock(returncode=0))

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = None
        args.apply = True
        result = phealth.cmd_fix(args)
        assert any("Added replacement" in a for a in result["actions_taken"])

    def test_fix_returns_error_from_check(self, monkeypatch):
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "error": "fail", "playlist_id": pid,
        })

        args = MagicMock()
        args.playlist_id = "pl1"
        args.storefront = "us"
        args.apply = False
        result = phealth.cmd_fix(args)
        assert result["error"] == "fail"


# ── main ─────────────────────────────────────────────────────────

class TestMain:
    def test_main_check(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["playlist_health.py", "check", "pl1"])
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.call_api", lambda *a, **kw: {"data": []})
        phealth.main()
        captured = capsys.readouterr()
        assert "playlist_id" in captured.out

    def test_main_fix(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["playlist_health.py", "fix", "pl1"])
        monkeypatch.setattr("playlist_health.require_env_tokens", lambda: None)
        monkeypatch.setattr("playlist_health.load_config", lambda: {"default_storefront": "us"})
        monkeypatch.setattr("playlist_health.check_playlist", lambda pid, sf: {
            "playlist_id": pid, "total_tracks": 0, "removed": [], "removed_count": 0,
            "duplicates": [], "duplicate_count": 0, "healthy": True,
        })
        phealth.main()
        captured = capsys.readouterr()
        assert "issues_found" in captured.out

    def test_main_no_command_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["playlist_health.py"])
        with pytest.raises(SystemExit):
            phealth.main()


# ── The fix command only changes a playlist when asked: --apply (formerly --auto) ──

class TestFixFlag:
    def _run(self, monkeypatch, *flags):
        import sys
        seen = {}
        monkeypatch.setattr(phealth, "cmd_fix", lambda args: seen.update(apply=args.apply) or {"ok": True})
        monkeypatch.setattr(sys, "argv", ["playlist_health.py", "fix", "p.1", *flags])
        phealth.main()
        return seen["apply"]

    def test_default_is_preview_only(self, monkeypatch):
        assert self._run(monkeypatch) is False

    def test_apply_turns_it_on(self, monkeypatch):
        assert self._run(monkeypatch, "--apply") is True

    def test_old_auto_spelling_still_works(self, monkeypatch):
        assert self._run(monkeypatch, "--auto") is True

    def test_help_advertises_apply_but_not_the_old_name(self, monkeypatch, capsys):
        import sys
        monkeypatch.setattr(sys, "argv", ["playlist_health.py", "fix", "--help"])
        with pytest.raises(SystemExit):
            phealth.main()
        text = capsys.readouterr().out
        assert "--apply" in text and "--auto" not in text and "only previews" in text

    def _fix(self, monkeypatch, apply):
        runs = []
        monkeypatch.setattr(phealth, "require_env_tokens", lambda: None)
        monkeypatch.setattr(phealth, "load_config", lambda: {})
        monkeypatch.setattr(phealth, "check_playlist", lambda pid, sf: {
            "duplicates": [{"id": "t1", "count": 3}], "removed": [], "removed_count": 0, "duplicate_count": 1})
        monkeypatch.setattr(phealth, "run_script", lambda *cmd, **k: runs.append(list(cmd)) or MagicMock(returncode=0))
        args = MagicMock(playlist_id="p.1", storefront="us", profile=None, apply=apply)
        return phealth.cmd_fix(args), runs

    def test_a_preview_never_removes_anything(self, monkeypatch):
        result, runs = self._fix(monkeypatch, apply=False)
        assert runs == [], "a preview must not call the playlist builder"
        assert result["applied"] is False and result["auto_applied"] is False
        assert result["actions_taken"] == ["WOULD remove 2 duplicate(s) of t1 (use --apply to apply)"]

    def test_apply_removes_the_extra_copies(self, monkeypatch):
        result, runs = self._fix(monkeypatch, apply=True)
        assert len(runs) == 1 and runs[0][:3] == ["build_playlist.sh", "remove", "p.1"] and runs[0][-1] == "--yes"
        assert result["applied"] is True and result["actions_taken"] == ["Removed 2 duplicate(s) of t1"]

    @pytest.mark.parametrize("outcome", [MagicMock(returncode=1, stderr="boom\n"), OSError("gone")])
    def test_a_failed_removal_is_not_reported_as_done(self, monkeypatch, capsys, outcome):
        def fake(*a, **k):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        self._fix(monkeypatch, apply=False)  # installs the check_playlist stubs
        monkeypatch.setattr(phealth, "run_script", fake)
        args = MagicMock(playlist_id="p.1", storefront="us", profile=None, apply=True)
        result = phealth.cmd_fix(args)
        assert result["actions_taken"] == ["Couldn't remove 2 duplicate(s) of t1"]
        assert "WARN: build_playlist.sh remove" in capsys.readouterr().err

