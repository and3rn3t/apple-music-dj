"""Tests for import_playlist.py — parsing, ISRC/search matching, reporting, CLI."""

import json
import sys

import pytest

import import_playlist as ip


def _song(sid, name, artist, isrc=None):
    attrs = {"name": name, "artistName": artist}
    if isrc:
        attrs["isrc"] = isrc
    return {"id": sid, "attributes": attrs}


class TestParsing:
    def test_spotify_style_csv(self):
        text = ("﻿Track URI,Track Name,Artist Name(s),ISRC\n"
                "spotify:track:1,Creep,Radiohead,gbaye9200070\n"
                'spotify:track:2,"Hello, Goodbye",The Beatles;Paul,GBAYE0601477\n'
                "spotify:track:3,No Isrc,Some Band,\n")
        rows = ip.parse_csv(text.lstrip("﻿"))
        assert rows[0] == {"title": "Creep", "artist": "Radiohead", "isrc": "GBAYE9200070"}
        assert rows[1]["title"] == "Hello, Goodbye" and rows[1]["artist"] == "The Beatles"  # first artist only
        assert rows[2]["isrc"] is None

    def test_exportify_style_artist_credits(self):
        """Exportify joins artists with ", " (and escapes commas inside a name as "\\,"); only ";" splits
        to the first artist, so a comma credit is kept whole and matched as a collaboration."""
        text = ("Track URI,Track Name,Artist Name(s),ISRC\n"
                'spotify:track:1,Collab,"Artist A, Artist B",\n'
                'spotify:track:2,Solo,"Tyler\\, The Creator",\n')
        rows = ip.parse_csv(text)
        assert rows[0]["artist"] == "Artist A, Artist B"
        assert rows[1]["artist"] == "Tyler\\, The Creator"
        assert ip.artist_credited(rows[0]["artist"], "Artist A & Artist B")
        assert ip.artist_credited(rows[1]["artist"], "Tyler, The Creator")

    def test_csv_isrc_only(self):
        assert ip.parse_csv("isrc\nGBAYE9200070\nnot-an-isrc\n") == [
            {"title": "", "artist": "", "isrc": "GBAYE9200070"}]

    def test_csv_quoted_newline_in_field(self):
        rows = ip.parse_csv('title,artist\n"Two\nLines",Band\n')
        assert rows == [{"title": "Two\nLines", "artist": "Band", "isrc": None}]

    def test_csv_missing_columns(self):
        with pytest.raises(ValueError, match="ISRC column"):
            ip.parse_csv("foo,bar\n1,2\n")

    def test_text_lines(self):
        rows = ip.parse_text("# my list\n\nRadiohead - Creep\nBjörk – Hyperballad\nCSS - Let's Make Love - Remix\nbadline\n")
        assert [(r["artist"], r["title"]) for r in rows] == [
            ("Radiohead", "Creep"), ("Björk", "Hyperballad"), ("CSS", "Let's Make Love - Remix")]

    def test_parse_file_dispatches_on_suffix(self, tmp_path):
        (tmp_path / "a.csv").write_text("title,artist\nCreep,Radiohead\n")
        (tmp_path / "a.txt").write_text("Radiohead - Creep\n")
        assert ip.parse_file(str(tmp_path / "a.csv")) == ip.parse_file(str(tmp_path / "a.txt"))


class TestNormalize:
    @pytest.mark.parametrize("raw,expected", [
        ("Creep (Remastered 2009)", "creep"),
        ("Karma Police - Remastered", "karma police"),
        ("Song [Live]", "song"),
        ("Hey Jude feat. Someone", "hey jude"),
        ("Don't Stop!", "don t stop"),
    ])
    def test_title(self, raw, expected):
        assert ip.normalize_title(raw) == expected

    def test_artist(self):
        assert ip.normalize_artist("The Beatles") == "beatles"
        assert ip.normalize_artist("  AC/DC ") == "ac dc"


class TestBestSearchMatch:
    ROW = {"title": "Creep", "artist": "Radiohead", "isrc": None}

    def test_accepts_remaster_variant(self):
        m = ip.best_search_match(self.ROW, [_song("1", "Creep (Remastered)", "Radiohead")])
        assert m["id"] == "1"

    def test_rejects_wrong_artist(self):
        assert ip.best_search_match(self.ROW, [_song("1", "Creep", "TLC")]) is None

    def test_rejects_different_song_by_same_artist(self):
        assert ip.best_search_match(self.ROW, [_song("1", "Karma Police", "Radiohead")]) is None

    def test_prefers_closest_title(self):
        songs = [_song("1", "Creeper", "Radiohead"), _song("2", "Creep", "Radiohead")]
        assert ip.best_search_match(self.ROW, songs)["id"] == "2"

    def test_artist_credit_may_be_longer(self):
        assert ip.best_search_match(self.ROW, [_song("1", "Creep", "Radiohead & Friends")])["id"] == "1"

    @pytest.mark.parametrize("credit", ["Museum", "Radiohead Tribute Band", "Radioheads", "Not Radiohead"])
    def test_artist_must_match_whole_credit_not_a_substring(self, credit):
        assert ip.best_search_match(self.ROW, [_song("1", "Creep", credit)]) is None

    def test_empty(self):
        assert ip.best_search_match(self.ROW, []) is None


class TestArtistCredited:
    @pytest.mark.parametrize("want,credit", [
        ("Muse", "Muse"), ("The Beatles", "Beatles"), ("Queen", "Queen & David Bowie"),
        ("David Bowie", "Queen & David Bowie"), ("Drake", "Drake feat. Rihanna"),
        ("Tyler, the Creator", "Tyler, the Creator"), ("Simon & Garfunkel", "Simon & Garfunkel"),
        ("Beyonce", "Jay-Z, Beyonce"), ("Kendrick Lamar", "SZA x Kendrick Lamar"),
    ])
    def test_credited(self, want, credit):
        assert ip.artist_credited(want, credit)

    @pytest.mark.parametrize("want,credit", [
        ("Muse", "Museum"), ("Queen", "Queens of the Stone Age"), ("Queen", "Queen Latifah"),
        ("Muse", ""), ("", "Muse"), ("Drake", "Drake Bell"),
    ])
    def test_not_credited(self, want, credit):
        assert not ip.artist_credited(want, credit)


class TestMatching:
    def test_isrc_batches_of_25(self, monkeypatch):
        calls = []
        isrcs = [f"GBAYE{i:07d}" for i in range(60)]

        def api(cmd, sf, ids, *a, **k):
            calls.append(ids.split(","))
            return {"data": [_song(f"id{i[-3:]}", "t", "a", i) for i in ids.split(",")]}

        monkeypatch.setattr(ip, "call_api", api)
        found = ip.match_by_isrc([{"isrc": i, "title": "", "artist": ""} for i in isrcs] +
                                 [{"isrc": isrcs[0], "title": "", "artist": ""}], "us")  # duplicate row
        assert [len(c) for c in calls] == [25, 25, 10]
        assert len(found) == 60

    def test_exact_then_fuzzy_then_unmatched(self, monkeypatch):
        def api(cmd, sf, arg, *a, **k):
            if cmd == "songs-by-isrc":
                return {"data": [_song("e1", "Creep", "Radiohead", "GBAYE9200070")]}
            if cmd == "search":
                if "Karma" in arg:
                    return {"results": {"songs": {"data": [_song("f1", "Karma Police", "Radiohead")]}}}
                return {"results": {}}
            return None

        monkeypatch.setattr(ip, "call_api", api)
        rows = [{"title": "Creep", "artist": "Radiohead", "isrc": "GBAYE9200070"},
                {"title": "Karma Police", "artist": "Radiohead", "isrc": None},
                {"title": "Nope", "artist": "Nobody", "isrc": None}]
        results = ip.match_rows(rows, "us")
        assert [r["how"] for r in results] == ["exact", "fuzzy", "unmatched"]

    def test_isrc_miss_falls_back_to_search(self, monkeypatch):
        def api(cmd, sf, arg, *a, **k):
            if cmd == "songs-by-isrc":
                return {"data": []}
            return {"results": {"songs": {"data": [_song("f1", "Creep", "Radiohead")]}}}

        monkeypatch.setattr(ip, "call_api", api)
        r = ip.match_rows([{"title": "Creep", "artist": "Radiohead", "isrc": "GBAYE9200070"}], "us")[0]
        assert r["how"] == "fuzzy"

    def test_isrc_only_row_without_match_is_unmatched(self, monkeypatch):
        monkeypatch.setattr(ip, "call_api", lambda *a, **k: None)
        r = ip.match_rows([{"title": "", "artist": "", "isrc": "GBAYE9200070"}], "us")[0]
        assert r["how"] == "unmatched" and r["match"] is None


class TestReport:
    def test_counts_dedupe_and_order(self):
        a = {"id": "1", "name": "A", "artist": "X"}
        b = {"id": "2", "name": "B", "artist": "X"}
        results = [
            {"input": {"title": "A"}, "match": a, "how": "exact"},
            {"input": {"title": "?"}, "match": None, "how": "unmatched"},
            {"input": {"title": "A again"}, "match": a, "how": "fuzzy"},
            {"input": {"title": "B"}, "match": b, "how": "fuzzy"},
        ]
        rep = ip.build_report(results)
        assert rep["counts"] == {"total": 4, "exact": 1, "fuzzy": 2, "unmatched": 1, "duplicates": 1}
        assert [t["id"] for t in rep["tracks"]] == ["1", "2"]
        assert rep["unmatched"] == [{"title": "?"}]
        assert len(rep["fuzzy"]) == 2


class TestMain:
    @pytest.fixture
    def env(self, monkeypatch, tmp_path):
        f = tmp_path / "list.txt"
        f.write_text("Radiohead - Creep\nNobody - Nothing\n")
        monkeypatch.setattr(ip, "require_env_tokens", lambda: None)
        monkeypatch.setattr(ip, "get_storefront", lambda sf=None: "us")
        monkeypatch.setattr(ip, "load_config", lambda: {})
        monkeypatch.setattr(ip, "call_api", lambda cmd, sf, arg, *a, **k:
            {"results": {"songs": {"data": [_song("s1", "Creep", "Radiohead")]}}} if "Creep" in arg
            else {"results": {}})

        def run(*argv):
            monkeypatch.setattr(sys, "argv", ["import_playlist.py", str(f), *argv])
            ip.main()
        return run

    def test_preview_writes_nothing(self, env, monkeypatch, capsys):
        monkeypatch.setattr("strategy_engine.create_playlist_from_tracks",
                            lambda *a: pytest.fail("preview must not create"))
        env()
        out = json.loads(capsys.readouterr().out)
        assert out["counts"]["fuzzy"] == 1 and out["counts"]["unmatched"] == 1
        assert "created" not in out

    def test_create_builds_and_logs(self, env, monkeypatch, capsys):
        created, logged = [], []
        monkeypatch.setattr("strategy_engine.create_playlist_from_tracks",
                            lambda tracks, name, desc: created.append((tracks, name)) or True)
        monkeypatch.setattr("playlist_history.log_playlist", lambda *a: logged.append(a))
        env("--create", "--name", "Imported")
        assert json.loads(capsys.readouterr().out)["created"] == "Imported"
        assert created[0][1] == "Imported" and [t["id"] for t in created[0][0]] == ["s1"]
        assert logged == [("Imported", "import", ["s1"])]

    def test_create_needs_name(self, env):
        with pytest.raises(SystemExit):
            env("--create")

    def test_create_failure_exits(self, env, monkeypatch):
        monkeypatch.setattr("strategy_engine.create_playlist_from_tracks", lambda *a: False)
        with pytest.raises(SystemExit):
            env("--create", "--name", "X")

    def test_nothing_matched_creates_nothing(self, env, monkeypatch):
        monkeypatch.setattr(ip, "call_api", lambda *a, **k: {"results": {}})
        monkeypatch.setattr("strategy_engine.create_playlist_from_tracks",
                            lambda *a: pytest.fail("nothing to create"))
        with pytest.raises(SystemExit):
            env("--create", "--name", "X")

    def test_empty_file(self, monkeypatch, tmp_path, capsys):
        f = tmp_path / "empty.txt"
        f.write_text("# nothing\n")
        monkeypatch.setattr(sys, "argv", ["import_playlist.py", str(f)])
        with pytest.raises(SystemExit):
            ip.main()
        assert "No usable rows" in capsys.readouterr().err

    def test_missing_file(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sys, "argv", ["import_playlist.py", str(tmp_path / "nope.csv")])
        with pytest.raises(SystemExit):
            ip.main()
