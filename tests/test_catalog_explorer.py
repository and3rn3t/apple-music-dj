"""Tests for catalog_explorer.py — gap analysis, album dive, rabbit hole."""


import json
import sys

import pytest

import catalog_explorer as ce
from catalog_explorer import cmd_album_dive, cmd_gap_analysis, cmd_rabbit_hole


# ── cmd_gap_analysis ─────────────────────────────────────────────

class TestCmdGapAnalysis:
    def test_returns_expected_keys(self, monkeypatch, sample_profile):
        def mock_api(cmd, *args, **kw):
            if cmd == "artist-albums":
                return {"data": []}
            return None

        monkeypatch.setattr("catalog_explorer.call_api", mock_api)
        monkeypatch.setattr("catalog_explorer.search_artist",
                            lambda sf, name: {"id": "a1", "attributes": {"name": name}})
        result = cmd_gap_analysis(sample_profile, "us")
        assert "artists_analyzed" in result
        assert "total_albums_missing" in result
        assert "results" in result

    def test_counts_missing_albums(self, monkeypatch, sample_profile):
        def mock_api(cmd, *args, **kw):
            if cmd == "artist-albums":
                return {
                    "data": [
                        {
                            "id": "alb1",
                            "attributes": {
                                "name": "OK Computer",
                                "trackCount": 12,
                                "releaseDate": "1997-06-16",
                                "isSingle": False,
                            },
                        },
                        {
                            "id": "alb2",
                            "attributes": {
                                "name": "Kid A",
                                "trackCount": 10,
                                "releaseDate": "2000-10-02",
                                "isSingle": False,
                            },
                        },
                    ]
                }
            if cmd == "album-tracks":
                # Return tracks — none in the user's library
                album_id = args[1] if len(args) > 1 else ""
                return {
                    "data": [{
                        "relationships": {
                            "tracks": {
                                "data": [
                                    {"id": f"{album_id}_t1", "attributes": {"name": "Track 1"}},
                                ]
                            }
                        }
                    }]
                }
            return None

        monkeypatch.setattr("catalog_explorer.call_api", mock_api)
        monkeypatch.setattr("catalog_explorer.search_artist",
                            lambda sf, name: {"id": "a1", "attributes": {"name": name}})

        result = cmd_gap_analysis(sample_profile, "us")
        assert result["total_albums_missing"] >= 0

    def test_skips_singles(self, monkeypatch, sample_profile):
        def mock_api(cmd, *args, **kw):
            if cmd == "artist-albums":
                return {
                    "data": [{
                        "id": "single1",
                        "attributes": {
                            "name": "Single Track",
                            "trackCount": 1,
                            "releaseDate": "2024",
                            "isSingle": True,
                        },
                    }]
                }
            return None

        monkeypatch.setattr("catalog_explorer.call_api", mock_api)
        monkeypatch.setattr("catalog_explorer.search_artist",
                            lambda sf, name: {"id": "a1", "attributes": {"name": name}})

        result = cmd_gap_analysis(sample_profile, "us")
        # Singles should be excluded — no albums should appear in results
        for r in result["results"]:
            assert r["missing_count"] == 0
            assert r["heard_count"] == 0

    def test_empty_profile(self, monkeypatch, empty_profile):
        result = cmd_gap_analysis(empty_profile, "us")
        assert result["artists_analyzed"] == 0
        assert result["total_albums_missing"] == 0

    def test_uses_top_10_artists(self, monkeypatch):
        """Only top 10 artists should be analyzed."""
        artists = [{"name": f"Artist_{i}", "id": f"id_{i}"} for i in range(20)]
        profile = {"top_artists": artists, "library_song_ids": []}
        analyzed_ids = set()

        def mock_api(cmd, *args, **kw):
            if cmd == "artist-albums":
                analyzed_ids.add(args[1])
                return {"data": []}
            return None

        monkeypatch.setattr("catalog_explorer.call_api", mock_api)
        monkeypatch.setattr("catalog_explorer.search_artist",
                            lambda sf, name: {"id": name.replace("Artist_", "id_"),
                                              "attributes": {"name": name}})

        cmd_gap_analysis(profile, "us")
        assert len(analyzed_ids) <= 10


# ── cmd_album_dive ───────────────────────────────────────────────

class TestCmdAlbumDive:
    def test_returns_error_on_not_found(self, monkeypatch):
        monkeypatch.setattr("catalog_explorer.search_album", lambda sf, q: None)
        result = cmd_album_dive("us", "NonExistentAlbum")
        assert "error" in result

    def test_returns_expected_keys(self, monkeypatch):
        mock_album = {
            "id": "alb1",
            "attributes": {
                "name": "OK Computer",
                "artistName": "Radiohead",
                "releaseDate": "1997-06-16",
                "genreNames": ["Alternative", "Rock"],
            },
        }
        mock_tracks = [
            {"id": "t1", "attributes": {"name": "Airbag", "trackNumber": 1,
                                         "durationInMillis": 280000, "artistName": "Radiohead"}},
            {"id": "t2", "attributes": {"name": "Paranoid Android", "trackNumber": 2,
                                         "durationInMillis": 384000, "artistName": "Radiohead"}},
        ]

        monkeypatch.setattr("catalog_explorer.search_album", lambda sf, q: mock_album)
        monkeypatch.setattr("catalog_explorer.get_album_tracks", lambda sf, aid: mock_tracks)
        monkeypatch.setattr("catalog_explorer.search_artist",
                            lambda sf, name: {"id": "a1", "attributes": {"name": name}})

        def mock_api(cmd, *args, **kw):
            if cmd == "artist-top":
                return {
                    "data": [{
                        "views": {
                            "top-songs": {
                                "data": [{"attributes": {"name": "Paranoid Android"}}]
                            }
                        }
                    }]
                }
            if cmd == "artist-albums":
                return {
                    "data": [{
                        "id": "alb1",
                        "attributes": {"releaseDate": "1997-06-16"},
                    }]
                }
            return None

        monkeypatch.setattr("catalog_explorer.call_api", mock_api)

        result = cmd_album_dive("us", "OK Computer")
        assert result["album"] == "OK Computer"
        assert result["artist"] == "Radiohead"
        assert result["track_count"] == 2
        assert "tracks" in result
        assert "deep_cut_count" in result
        assert "recommended_deep_cuts" in result

    def test_classifies_singles_and_deep_cuts(self, monkeypatch):
        mock_album = {
            "id": "alb1",
            "attributes": {"name": "Album", "artistName": "Artist",
                           "releaseDate": "2020", "genreNames": ["Pop"]},
        }
        mock_tracks = [
            {"id": "t1", "attributes": {"name": "Hit Song", "trackNumber": 1,
                                         "durationInMillis": 200000, "artistName": "Artist"}},
            {"id": "t2", "attributes": {"name": "Hidden Gem", "trackNumber": 5,
                                         "durationInMillis": 300000, "artistName": "Artist"}},
        ]

        monkeypatch.setattr("catalog_explorer.search_album", lambda sf, q: mock_album)
        monkeypatch.setattr("catalog_explorer.get_album_tracks", lambda sf, aid: mock_tracks)
        monkeypatch.setattr("catalog_explorer.search_artist",
                            lambda sf, name: {"id": "a1", "attributes": {"name": name}})

        def mock_api(cmd, *args, **kw):
            if cmd == "artist-top":
                return {
                    "data": [{
                        "views": {
                            "top-songs": {
                                "data": [{"attributes": {"name": "Hit Song"}}]
                            }
                        }
                    }]
                }
            if cmd == "artist-albums":
                return {"data": [{"id": "alb1", "attributes": {"releaseDate": "2020"}}]}
            return None

        monkeypatch.setattr("catalog_explorer.call_api", mock_api)
        result = cmd_album_dive("us", "Album")

        hit = next(t for t in result["tracks"] if t["name"] == "Hit Song")
        deep = next(t for t in result["tracks"] if t["name"] == "Hidden Gem")
        assert hit["is_single"] is True
        assert hit["is_deep_cut"] is False
        assert deep["is_single"] is False
        assert deep["is_deep_cut"] is True


# ── cmd_rabbit_hole ──────────────────────────────────────────────

class TestCmdRabbitHole:
    def test_returns_expected_keys(self, monkeypatch, sample_profile):
        search_count = {"n": 0}

        def mock_search_artist(sf, name):
            search_count["n"] += 1
            return {
                "id": f"a{search_count['n']}",
                "attributes": {"name": name, "genreNames": ["Rock"]},
            }

        def mock_api(cmd, *args, **kw):
            if cmd == "artist-top":
                return {
                    "data": [{
                        "views": {
                            "top-songs": {
                                "data": [{"id": "t1", "attributes": {"name": "Song"}}]
                            }
                        }
                    }]
                }
            if cmd == "search":
                return {
                    "results": {
                        "artists": {
                            "data": [
                                {"id": f"next_{search_count['n']}",
                                 "attributes": {"name": f"Next Artist {search_count['n']}"}}
                            ]
                        }
                    }
                }
            return None

        monkeypatch.setattr("catalog_explorer.search_artist", mock_search_artist)
        monkeypatch.setattr("catalog_explorer.call_api", mock_api)

        result = cmd_rabbit_hole(sample_profile, "us", "Radiohead", depth=2)
        assert "start_artist" in result
        assert "chain_length" in result
        assert "chain" in result
        assert "playlist_tracks" in result
        assert "zones_reached" in result
        assert result["start_artist"] == "Radiohead"

    def test_first_step_is_origin(self, monkeypatch, sample_profile):
        def mock_search_artist(sf, name):
            return {"id": "a1", "attributes": {"name": name, "genreNames": ["Rock"]}}

        def mock_api(cmd, *args, **kw):
            if cmd == "artist-top":
                return {"data": [{"views": {"top-songs": {"data": []}}}]}
            return None

        monkeypatch.setattr("catalog_explorer.search_artist", mock_search_artist)
        monkeypatch.setattr("catalog_explorer.call_api", mock_api)

        result = cmd_rabbit_hole(sample_profile, "us", "Radiohead", depth=1)
        assert result["chain"][0]["zone"] == "origin"

    def test_stops_on_no_artist(self, monkeypatch, sample_profile):
        monkeypatch.setattr("catalog_explorer.search_artist", lambda sf, name: None)
        monkeypatch.setattr("catalog_explorer.call_api", lambda *a, **kw: None)

        result = cmd_rabbit_hole(sample_profile, "us", "Unknown", depth=4)
        assert result["chain_length"] == 0

    def test_familiar_zone(self, monkeypatch, sample_profile):
        """Artists in user's library should be classified as 'familiar'."""
        call_n = {"n": 0}

        def mock_search(sf, name):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return {"id": "origin_id", "attributes": {"name": "Start", "genreNames": ["Rock"]}}
            return {"id": "a2", "attributes": {"name": "Radiohead", "genreNames": ["Alternative"]}}

        def mock_api(cmd, *args, **kw):
            if cmd == "artist-top":
                return {"data": [{"views": {"top-songs": {"data": []}}}]}
            if cmd == "search":
                return {
                    "results": {
                        "artists": {
                            "data": [{"id": "a2", "attributes": {"name": "Radiohead"}}]
                        }
                    }
                }
            return None

        monkeypatch.setattr("catalog_explorer.search_artist", mock_search)
        monkeypatch.setattr("catalog_explorer.call_api", mock_api)

        result = cmd_rabbit_hole(sample_profile, "us", "Start", depth=2)
        zones = [c["zone"] for c in result["chain"]]
        assert "familiar" in zones

    def test_playlist_tracks_collected(self, monkeypatch, sample_profile):
        def mock_search(sf, name):
            return {"id": "a1", "attributes": {"name": name, "genreNames": ["Rock"]}}

        def mock_api(cmd, *args, **kw):
            if cmd == "artist-top":
                return {
                    "data": [{
                        "views": {
                            "top-songs": {
                                "data": [
                                    {"id": "t1", "attributes": {"name": "Song 1"}},
                                    {"id": "t2", "attributes": {"name": "Song 2"}},
                                ]
                            }
                        }
                    }]
                }
            return None

        monkeypatch.setattr("catalog_explorer.search_artist", mock_search)
        monkeypatch.setattr("catalog_explorer.call_api", mock_api)

        result = cmd_rabbit_hole(sample_profile, "us", "Radiohead", depth=1)
        assert len(result["playlist_tracks"]) >= 1
        assert all("id" in t for t in result["playlist_tracks"])


# ── --add-missing ────────────────────────────────────────────────

GAP = {"results": [
    {"artist": "A", "albums_missing": [
        {"name": "Old", "id": "1", "release_date": "1999-01-01"},
        {"name": "New", "id": "2", "release_date": "2024-01-01"}]},
    {"artist": "B", "albums_missing": [
        {"name": "Mid", "id": "3", "release_date": "2010-01-01"},
        {"name": "NoId", "id": "", "release_date": "2030-01-01"}]},
]}


class TestAddMissing:
    def test_plan_picks_newest_first_and_skips_idless(self):
        assert [a["id"] for a in ce.plan_missing_albums(GAP, 2)] == ["2", "3"]
        assert [a["id"] for a in ce.plan_missing_albums(GAP, 10)] == ["2", "3", "1"]

    def test_dry_run_never_calls_api(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("dry run must not call the API")
        monkeypatch.setattr(ce, "call_api", boom)
        out = ce.run_add_missing(GAP, 2, confirmed=False)
        assert out["dry_run"] is True and len(out["albums"]) == 2
        assert "--yes" in out["note"]

    def test_confirmed_adds_in_batches(self, monkeypatch):
        calls = []
        monkeypatch.setattr(ce, "call_api", lambda *a, **k: calls.append((a, k)) or "")
        many = {"results": [{"artist": "A", "albums_missing": [
            {"name": f"Al{i}", "id": str(i), "release_date": f"20{i:02d}-01-01"} for i in range(25)]}]}
        out = ce.run_add_missing(many, 25, confirmed=True)
        assert len(out["added"]) == 25 and out["failed"] == []
        assert len(calls) == 3  # 10 + 10 + 5
        cmd, kind, ids = calls[0][0]
        assert (cmd, kind) == ("add-to-library", "albums") and len(ids.split(",")) == 10
        assert calls[0][1] == {"raw": True}

    def test_failed_batch_reported(self, monkeypatch):
        monkeypatch.setattr(ce, "call_api", lambda *a, **k: None)
        out = ce.run_add_missing(GAP, 2, confirmed=True)
        assert out["added"] == [] and len(out["failed"]) == 2

    def _run(self, monkeypatch, tmp_path, capsys, extra):
        profile = tmp_path / "p.json"
        profile.write_text("{}")
        monkeypatch.setattr(ce, "cmd_gap_analysis", lambda p, sf: json.loads(json.dumps(GAP)))
        monkeypatch.setattr(sys, "argv", ["catalog_explorer.py", "gap-analysis", str(profile), "us", *extra])
        ce.main()
        return json.loads(capsys.readouterr().out)

    def test_cli_default_has_no_add_section(self, monkeypatch, tmp_path, capsys):
        assert "add_missing" not in self._run(monkeypatch, tmp_path, capsys, [])

    def test_cli_preview_without_yes(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(ce, "call_api", lambda *a, **k: pytest.fail("must not write"))
        out = self._run(monkeypatch, tmp_path, capsys, ["--add-missing", "1"])
        assert out["add_missing"]["dry_run"] is True

    def test_cli_yes_writes(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(ce, "call_api", lambda *a, **k: "")
        out = self._run(monkeypatch, tmp_path, capsys, ["--add-missing", "1", "--yes"])
        assert out["add_missing"]["dry_run"] is False
        assert [a["id"] for a in out["add_missing"]["added"]] == ["2"]

    @pytest.mark.parametrize("extra", [["--add-missing", "0"], ["--yes"]])
    def test_cli_rejects_bad_flags(self, monkeypatch, tmp_path, capsys, extra):
        with pytest.raises(SystemExit):
            self._run(monkeypatch, tmp_path, capsys, extra)
