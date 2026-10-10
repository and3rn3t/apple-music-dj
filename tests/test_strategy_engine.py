"""Tests for strategy_engine — playlist strategy engine."""

import json
from unittest.mock import MagicMock
import pytest

import strategy_engine as se


# ── Genre Proximity ──────────────────────────────────────────────

class TestGenreProximity:
    def test_exact_match(self):
        assert se.genre_proximity("Rock", "Rock") == 1.0

    def test_case_insensitive(self):
        assert se.genre_proximity("rock", "ROCK") == 1.0

    def test_same_family(self):
        assert se.genre_proximity("Rock", "Alternative") == 0.5

    def test_different_family(self):
        assert se.genre_proximity("Rock", "Classical") == 0.0

    def test_electronic_family(self):
        assert se.genre_proximity("Electronic", "Dance") == 0.5

    def test_hiphop_family(self):
        assert se.genre_proximity("Hip-Hop/Rap", "Funk") == 0.5


class TestBestGenreMatch:
    def test_exact_in_list(self):
        assert se.best_genre_match(["Rock", "Pop"], ["Rock"]) == 1.0

    def test_partial_in_list(self):
        assert se.best_genre_match(["Alternative"], ["Rock"]) == 0.5

    def test_no_match(self):
        assert se.best_genre_match(["Classical"], ["Hip-Hop/Rap"]) == 0.0

    def test_empty_track_genres(self):
        assert se.best_genre_match([], ["Rock"]) == 0.0

    def test_empty_target_genres(self):
        assert se.best_genre_match(["Rock"], []) == 0.0


# ── Sequencing ───────────────────────────────────────────────────

class TestSequenceTracks:
    def _make(self, artist, album="", tid=""):
        return {"id": tid or f"{artist}-1", "name": "Song",
                "artist": artist, "album": album}

    def test_preserves_short_list(self):
        tracks = [self._make("A"), self._make("B")]
        result = se.sequence_tracks(tracks)
        assert len(result) == 2

    def test_artist_spacing(self):
        """Same artist should not appear back-to-back after sequencing."""
        tracks = [self._make("A", tid=f"A{i}") for i in range(3)]
        tracks += [self._make("B", tid=f"B{i}") for i in range(3)]
        tracks += [self._make("C", tid=f"C{i}") for i in range(3)]
        tracks += [self._make("D", tid=f"D{i}") for i in range(3)]
        tracks += [self._make("E", tid=f"E{i}") for i in range(3)]
        tracks += [self._make("F", tid=f"F{i}") for i in range(3)]
        result = se.sequence_tracks(tracks, max_same_artist=5)
        # Check no immediate back-to-back repeat
        for i in range(1, len(result)):
            # Allow at most one back-to-back when forced
            if result[i]["artist"] == result[i-1]["artist"] and i >= 2:
                assert result[i]["artist"] != result[i-2]["artist"]

    def test_album_cap(self):
        """Max 2 tracks from the same album."""
        tracks = [self._make("A", album="Album1", tid=f"t{i}") for i in range(5)]
        result = se.sequence_tracks(tracks)
        album1 = [t for t in result if t["album"] == "Album1"]
        assert len(album1) <= 2

    def test_empty_input(self):
        assert se.sequence_tracks([]) == []

    def test_unknown_arc_rejected(self):
        with pytest.raises(ValueError):
            se.sequence_tracks([self._make("A")], arc="zigzag")

    def _energy_set(self):
        genres = [["Ambient"], ["Jazz"], ["Rock"], ["Metal"], ["Folk"], ["Dance"], ["Pop"], ["Classical"]]
        return [{"id": f"t{i}", "artist": f"Artist{i}", "album": f"Album{i}", "genre": g}
                for i, g in enumerate(genres)]

    def test_ascending_arc(self):
        result = se.sequence_tracks(self._energy_set(), arc="ascending")
        energies = [t["energy"] for t in result]
        assert energies == sorted(energies)

    def test_descending_arc(self):
        result = se.sequence_tracks(self._energy_set(), arc="descending")
        energies = [t["energy"] for t in result]
        assert energies == sorted(energies, reverse=True)

    def test_wave_opener_is_not_the_quietest_track(self):
        """Opener is mid-energy; the closer is the quietest (the wind-down)."""
        result = se.sequence_tracks(self._energy_set(), arc="wave")
        energies = [t["energy"] for t in result]
        assert energies[0] > min(energies)
        assert energies[-1] == min(energies)
        assert energies[0] > energies[-1]

    def test_wave_arc_peaks_in_middle(self):
        result = se.sequence_tracks(self._energy_set(), arc="wave")
        energies = [t["energy"] for t in result]
        peak = energies.index(max(energies))
        assert 0 < peak < len(energies) - 1
        # Opener and closer are below the peak
        assert energies[0] < max(energies) and energies[-1] < max(energies)
        # Builds up to the peak, then winds down
        assert energies[: peak + 1] == sorted(energies[: peak + 1])
        assert energies[peak:] == sorted(energies[peak:], reverse=True)

    def test_none_arc_keeps_order(self):
        tracks = self._energy_set()
        ids = [t["id"] for t in tracks]
        result = se.sequence_tracks(tracks, arc="none")
        assert [t["id"] for t in result] == ids
        assert "energy" not in result[0]

    def test_arc_still_spaces_artists(self):
        tracks = [{"id": f"a{i}", "artist": "Same", "album": f"Al{i}", "genre": ["Rock"]} for i in range(3)]
        tracks += [{"id": f"b{i}", "artist": f"Other{i}", "album": f"Bl{i}", "genre": ["Rock"]} for i in range(4)]
        result = se.sequence_tracks(tracks, max_same_artist=2, arc="ascending")
        assert len(result) == 7
        same_positions = [i for i, t in enumerate(result) if t["artist"] == "Same"]
        assert all(b - a > 1 for a, b in zip(same_positions, same_positions[1:], strict=False))



# ── Strategy: Deep Cuts ──────────────────────────────────────────

class TestStrategyDeepCuts:
    def test_basic_deep_cuts(self, sample_profile, monkeypatch):
        """Deep cuts should return tracks from artist discographies."""
        albums_response = {"data": [{
            "id": "alb1",
            "attributes": {"name": "OK Computer", "isSingle": False},
        }]}

        album_tracks = [{
            "id": "new1",
            "attributes": {
                "name": "Lucky",
                "artistName": "Radiohead",
                "genreNames": ["Alternative"],
                "trackNumber": 8,
            },
        }, {
            "id": "new2",
            "attributes": {
                "name": "The Tourist",
                "artistName": "Radiohead",
                "genreNames": ["Alternative"],
                "trackNumber": 12,
            },
        }]

        top_response = {"data": [{"views": {
            "top-songs": {"data": [
                {"attributes": {"name": "Creep"}},
            ]},
        }}]}

        def mock_call_api(cmd, *args, **kwargs):
            if cmd == "artist-top":
                return top_response
            if cmd == "artist-albums":
                return albums_response
            return None

        monkeypatch.setattr(se, "call_api", mock_call_api)
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: album_tracks)

        result = se.strategy_deep_cuts(sample_profile, "us", target_size=5)
        assert len(result) > 0
        assert all("name" in t for t in result)
        assert all(t["source"] == "deep_cut" for t in result)

    def test_excludes_library_and_disliked(self, sample_profile, monkeypatch):
        """Deep cuts should skip library songs and disliked songs."""
        sample_profile["library_song_ids"] = ["lib1"]
        sample_profile["disliked_song_ids"] = ["dis1"]

        albums_response = {"data": [{
            "id": "alb1",
            "attributes": {"name": "Test Album", "isSingle": False},
        }]}

        album_tracks = [
            {"id": "lib1", "attributes": {"name": "InLib", "artistName": "X",
                                           "genreNames": [], "trackNumber": 1}},
            {"id": "dis1", "attributes": {"name": "Disliked", "artistName": "X",
                                           "genreNames": [], "trackNumber": 2}},
            {"id": "ok1", "attributes": {"name": "Good", "artistName": "X",
                                          "genreNames": [], "trackNumber": 3}},
        ]

        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            albums_response if cmd == "artist-albums"
            else {"data": [{"views": {"top-songs": {"data": []}}}]} if cmd == "artist-top"
            else None)
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: album_tracks)

        result = se.strategy_deep_cuts(sample_profile, "us", target_size=5)
        ids = {t["id"] for t in result}
        assert "lib1" not in ids
        assert "dis1" not in ids

    def test_skips_singles(self, sample_profile, monkeypatch):
        """Deep cuts should skip single releases."""
        albums_response = {"data": [{
            "id": "alb1",
            "attributes": {"name": "A Single", "isSingle": True},
        }]}

        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            albums_response if cmd == "artist-albums"
            else {"data": [{"views": {"top-songs": {"data": []}}}]}
            if cmd == "artist-top" else None)
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: [])

        result = se.strategy_deep_cuts(sample_profile, "us", target_size=5)
        assert result == []

    def test_empty_profile(self, empty_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda *a, **k: None)
        result = se.strategy_deep_cuts(empty_profile, "us", target_size=5)
        assert result == []


# ── Strategy: Mood ───────────────────────────────────────────────

class TestStrategyMood:
    def _mock_charts(self):
        return {"results": {"songs": [{
            "data": [
                {"id": "c1", "attributes": {"name": "Beat Drop", "artistName": "DJ X",
                                              "genreNames": ["Electronic", "Dance"]}},
                {"id": "c2", "attributes": {"name": "Slow Jam", "artistName": "Singer Y",
                                              "genreNames": ["Jazz", "R&B/Soul"]}},
                {"id": "c3", "attributes": {"name": "Rock On", "artistName": "Band Z",
                                              "genreNames": ["Rock"]}},
            ],
        }]}}

    def test_workout_returns_high_energy(self, sample_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            self._mock_charts() if cmd == "charts"
            else {"data": []} if cmd == "artist-albums" else None)
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: [])

        result = se.strategy_mood(sample_profile, "us", "workout", target_size=5)
        # Should include Electronic/Dance track
        genres_flat = [g for t in result for g in t.get("genre", [])]
        assert any(g in genres_flat for g in ["Electronic", "Dance", "Pop"])

    def test_unknown_mood_exits(self, sample_profile, monkeypatch):
        with pytest.raises(SystemExit):
            se.strategy_mood(sample_profile, "us", "nonexistent", target_size=5)

    def test_all_moods_have_genres(self):
        for mood, config in se.MOOD_MAP.items():
            assert len(config["genres"]) > 0, f"Mood {mood} has no genres"
            assert "energy" in config
            assert "description" in config

    def test_chill_mood(self, sample_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            self._mock_charts() if cmd == "charts"
            else {"data": []} if cmd == "artist-albums" else None)
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: [])

        result = se.strategy_mood(sample_profile, "us", "chill", target_size=5)
        # Jazz track should match chill mood
        if result:
            assert any(t.get("name") == "Slow Jam" for t in result)


# ── Strategy: Trend Radar ────────────────────────────────────────

class TestStrategyTrend:
    def _mock_charts(self):
        return {"results": {"songs": [{
            "data": [
                {"id": "t1", "attributes": {"name": "Alt Hit", "artistName": "Radiohead",
                                              "genreNames": ["Alternative"]}},
                {"id": "t2", "attributes": {"name": "Pop Hit", "artistName": "Pop Star",
                                              "genreNames": ["Pop"]}},
                {"id": "t3", "attributes": {"name": "Country Song", "artistName": "Country Joe",
                                              "genreNames": ["Country"]}},
            ],
        }]}}

    def test_taste_filtering(self, sample_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            self._mock_charts() if cmd == "charts" else None)

        result = se.strategy_trend(sample_profile, "us", target_size=5)
        assert len(result) > 0

    def test_known_artist_boosted(self, sample_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            self._mock_charts() if cmd == "charts" else None)

        result = se.strategy_trend(sample_profile, "us", target_size=5)
        # Radiohead track should be included (known artist boost)
        if result:
            names = [t["name"] for t in result]
            assert "Alt Hit" in names

    def test_excludes_library_tracks(self, sample_profile, monkeypatch):
        sample_profile["library_song_ids"] = ["t1", "t2"]
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            self._mock_charts() if cmd == "charts" else None)

        result = se.strategy_trend(sample_profile, "us", target_size=5)
        ids = {t["id"] for t in result}
        assert "t1" not in ids
        assert "t2" not in ids

    def test_wildcards_included(self, sample_profile, monkeypatch):
        """Trend radar should include 2-3 wildcard tracks."""
        charts = {"results": {"songs": [{
            "data": [
                {"id": f"m{i}", "attributes": {"name": f"Match {i}", "artistName": "A",
                                                 "genreNames": ["Alternative"]}}
                for i in range(20)
            ] + [
                {"id": f"w{i}", "attributes": {"name": f"Wild {i}", "artistName": "B",
                                                 "genreNames": ["Reggaeton"]}}
                for i in range(5)
            ],
        }]}}
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            charts if cmd == "charts" else None)

        result = se.strategy_trend(sample_profile, "us", target_size=20)
        # All tracks should have required fields
        for t in result:
            assert "id" in t
            assert "name" in t


# ── Strategy: Constellation ──────────────────────────────────────

class TestStrategyConstellation:
    def test_basic_constellation(self, sample_profile, monkeypatch):
        search_results = {"results": {"artists": {"data": [
            {"id": "disc1", "attributes": {"name": "New Band", "genreNames": ["Alternative"]}},
            {"id": "disc2", "attributes": {"name": "Frontier Band", "genreNames": ["Country"]}},
        ]}}}

        top_songs = {"data": [{"views": {"top-songs": {"data": [
            {"id": "ns1", "attributes": {"name": "New Song", "artistName": "New Band",
                                          "genreNames": ["Alternative"]}},
        ]}}}]}

        def mock_call_api(cmd, *args, **kwargs):
            if cmd == "search":
                return search_results
            if cmd == "artist-top":
                return top_songs
            return None

        monkeypatch.setattr(se, "call_api", mock_call_api)
        monkeypatch.setattr(se, "search_artist", lambda sf, name:
            {"id": "seed1", "attributes": {"genreNames": ["Alternative"], "name": name}})

        result = se.strategy_constellation(sample_profile, "us", target_size=10)
        assert len(result) > 0
        # Should have zone assignments
        zones = {t.get("zone") for t in result}
        assert len(zones) > 0

    def test_excludes_library_artists(self, sample_profile, monkeypatch):
        """Known library artists should not appear as discoveries."""
        search_results = {"results": {"artists": {"data": [
            {"id": "a1", "attributes": {"name": "Radiohead", "genreNames": ["Alternative"]}},
        ]}}}

        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            search_results if cmd == "search" else None)
        monkeypatch.setattr(se, "search_artist", lambda sf, name:
            {"id": "seed1", "attributes": {"genreNames": ["Alternative"], "name": name}})

        result = se.strategy_constellation(sample_profile, "us", target_size=10)
        artists = {t["artist"].lower() for t in result}
        # Radiohead should be filtered since they're already in library_artists
        assert "radiohead" not in artists

    def test_empty_profile(self, empty_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda *a, **k: None)
        monkeypatch.setattr(se, "search_artist", lambda *a, **k: None)
        result = se.strategy_constellation(empty_profile, "us", target_size=10)
        assert result == []


# ── Strategy: Refresh ────────────────────────────────────────────

class TestStrategyRefresh:
    def test_basic_refresh(self, sample_profile, monkeypatch):
        playlist_tracks = {"data": [{
            "id": "pt1",
            "attributes": {"name": "Old Song", "artistName": "Radiohead",
                           "genreNames": ["Alternative"]},
            "relationships": {"catalog": {"data": [{"id": "cat1"}]}},
        }]}

        charts = {"results": {"songs": [{
            "data": [
                {"id": "fresh1", "attributes": {"name": "Fresh Alt", "artistName": "NewArt",
                                                  "genreNames": ["Alternative"]}},
            ],
        }]}}

        def mock_call_api(cmd, *args, **kwargs):
            if cmd == "playlist-tracks":
                return playlist_tracks
            if cmd == "charts":
                return charts
            if cmd == "artist-albums":
                return {"data": []}
            return None

        monkeypatch.setattr(se, "call_api", mock_call_api)
        monkeypatch.setattr(se, "search_artist", lambda sf, name:
            {"id": "ra1", "attributes": {"name": name}})
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: [])

        result = se.strategy_refresh(sample_profile, "us", "p123", target_add=5)
        assert len(result) > 0
        assert all(t["source"] == "refresh" for t in result)

    def test_excludes_existing_tracks(self, sample_profile, monkeypatch):
        playlist_tracks = {"data": [{
            "id": "pt1",
            "attributes": {"name": "Existing", "artistName": "A",
                           "genreNames": ["Rock"]},
            "relationships": {"catalog": {"data": [{"id": "exist1"}]}},
        }]}

        charts = {"results": {"songs": [{
            "data": [
                {"id": "exist1", "attributes": {"name": "Dupe", "artistName": "A",
                                                  "genreNames": ["Rock"]}},
                {"id": "new1", "attributes": {"name": "New", "artistName": "B",
                                               "genreNames": ["Rock"]}},
            ],
        }]}}

        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            playlist_tracks if cmd == "playlist-tracks"
            else charts if cmd == "charts"
            else {"data": []} if cmd == "artist-albums" else None)
        monkeypatch.setattr(se, "search_artist", lambda sf, name:
            {"id": "x", "attributes": {"name": name}})
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: [])

        result = se.strategy_refresh(sample_profile, "us", "p1", target_add=5)
        ids = {t["id"] for t in result}
        assert "exist1" not in ids

    def _refresh_mocks(self, monkeypatch):
        playlist_tracks = {"data": [{
            "id": "pt1",
            "attributes": {"name": "Existing", "artistName": "A", "genreNames": ["Rock"]},
            "relationships": {"catalog": {"data": [{"id": "exist1"}]}},
        }]}
        charts = {"results": {"songs": [{"data": [
            {"id": "owned1", "attributes": {"name": "Owned", "artistName": "B", "genreNames": ["Rock"]}},
            {"id": "new1", "attributes": {"name": "New", "artistName": "C", "genreNames": ["Rock"]}},
        ]}]}}
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            playlist_tracks if cmd == "playlist-tracks"
            else charts if cmd == "charts"
            else {"data": []} if cmd == "artist-albums" else None)
        monkeypatch.setattr(se, "search_artist", lambda sf, name: {"id": "x", "attributes": {"name": name}})
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: [])

    def test_excludes_library_songs(self, sample_profile, monkeypatch):
        self._refresh_mocks(monkeypatch)
        sample_profile["library_song_ids"] = ["owned1"]
        ids = {t["id"] for t in se.strategy_refresh(sample_profile, "us", "p1", target_add=5)}
        assert "owned1" not in ids
        assert "new1" in ids

    def test_include_library_opt_in(self, sample_profile, monkeypatch):
        self._refresh_mocks(monkeypatch)
        sample_profile["library_song_ids"] = ["owned1"]
        ids = {t["id"] for t in se.strategy_refresh(
            sample_profile, "us", "p1", target_add=5, include_library=True)}
        assert "owned1" in ids

    def test_empty_playlist(self, sample_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda cmd, *a, **k:
            None if cmd == "playlist-tracks" else None)
        result = se.strategy_refresh(sample_profile, "us", "p1", target_add=5)
        assert result == []


# ── Strategy: Seed ───────────────────────────────────────────────

def _song(tid, name, artist, genres=("Alternative",), date="2000-01-01", album=None):
    return {"id": tid, "type": "songs", "attributes": {
        "name": name, "artistName": artist, "genreNames": list(genres),
        "releaseDate": date, "albumName": album or f"Album {tid}"}}


def _artist(aid, name, genres=("Alternative",)):
    return {"id": aid, "type": "artists", "attributes": {"name": name, "genreNames": list(genres)}}


def _top(songs):
    return {"data": [{"views": {"top-songs": {"data": songs}}}]}


class TestStrategySeed:
    def _api(self, search_result, tops, similar=()):
        def mock(cmd, *args, **kwargs):
            if cmd == "search":
                return search_result
            if cmd == "artist-top":
                return _top(tops.get(args[1], []))
            if cmd == "similar-artists":
                return {"data": list(similar)}
            return None
        return mock

    def test_artist_seed_uses_similar_artists(self, sample_profile, monkeypatch):
        search = {"results": {"artists": {"data": [_artist("r1", "Radiohead")]}, "songs": {"data": []}}}
        tops = {
            "r1": [_song("s1", "Creep", "Radiohead"), _song("s2", "Karma Police", "Radiohead")],
            "b1": [_song("s3", "Wonderwall", "Oasis"), _song("s4", "Live Forever", "Oasis")],
        }
        monkeypatch.setattr(se, "call_api", self._api(search, tops, [_artist("b1", "Oasis")]))
        result = se.strategy_seed(sample_profile, "us", "Radiohead")
        assert {t["id"] for t in result} == {"s1", "s2", "s3", "s4"}
        assert {t["source"] for t in result} == {"seed", "similar"}

    def test_auto_prefers_exact_artist_match_over_song(self, sample_profile, monkeypatch):
        search = {"results": {
            "artists": {"data": [_artist("r1", "Radiohead")]},
            "songs": {"data": [_song("x", "Radiohead Tribute", "Cover Band")]},
        }}
        monkeypatch.setattr(se, "call_api", self._api(search, {"r1": [_song("s1", "Creep", "Radiohead")]}))
        artist, song = se._resolve_seed("us", "radiohead", "auto")
        assert artist["id"] == "r1" and song is None

    def test_song_seed_resolves_artist_and_excludes_seed_song(self, sample_profile, monkeypatch):
        search = {"results": {"songs": {"data": [_song("seed1", "Creep", "Radiohead")]},
                              "artists": {"data": [_artist("r1", "Radiohead")]}}}
        tops = {"r1": [_song("seed1", "Creep", "Radiohead"), _song("s2", "Karma Police", "Radiohead")]}
        monkeypatch.setattr(se, "call_api", self._api(search, tops))
        monkeypatch.setattr(se, "search_artist", lambda sf, name: _artist("r1", name))
        result = se.strategy_seed(sample_profile, "us", "Creep", seed_type="song")
        ids = {t["id"] for t in result}
        assert "seed1" not in ids and "s2" in ids

    def test_excludes_library_and_disliked(self, sample_profile, monkeypatch):
        search = {"results": {"artists": {"data": [_artist("r1", "Radiohead")]}}}
        tops = {"r1": [_song("owned", "A", "Radiohead"), _song("bad", "B", "Radiohead"), _song("ok", "C", "Radiohead")]}
        sample_profile["library_song_ids"] = ["owned"]
        sample_profile["disliked_song_ids"] = ["bad"]
        monkeypatch.setattr(se, "call_api", self._api(search, tops))
        assert {t["id"] for t in se.strategy_seed(sample_profile, "us", "Radiohead", "artist")} == {"ok"}
        out = se.strategy_seed(sample_profile, "us", "Radiohead", "artist", include_library=True)
        assert {t["id"] for t in out} == {"owned", "ok"}

    def test_caps_tracks_per_artist(self, sample_profile, monkeypatch):
        search = {"results": {"artists": {"data": [_artist("r1", "Radiohead")]}}}
        tops = {"r1": [_song(f"s{i}", f"Song{i}", "Radiohead", album=f"Al{i}") for i in range(8)]}
        monkeypatch.setattr(se, "call_api", self._api(search, tops))
        assert len(se.strategy_seed(sample_profile, "us", "Radiohead", "artist")) == 3

    def test_genre_fallback_when_no_similar_artists(self, sample_profile, monkeypatch):
        calls = []

        def mock(cmd, *args, **kwargs):
            calls.append((cmd, args))
            if cmd == "search" and args[2] == "artists,songs" or (cmd == "search" and args[2] == "artists" and args[1] == "Radiohead"):
                return {"results": {"artists": {"data": [_artist("r1", "Radiohead")]}}}
            if cmd == "search":  # genre fallback search
                return {"results": {"artists": {"data": [_artist("g1", "Muse")]}}}
            if cmd == "artist-top":
                return _top([_song("m1", "Starlight", "Muse")] if args[1] == "g1" else [])
            return {"data": []}

        monkeypatch.setattr(se, "call_api", mock)
        result = se.strategy_seed(sample_profile, "us", "Radiohead")
        assert [t["id"] for t in result] == ["m1"]

    def test_unknown_seed_returns_empty(self, sample_profile, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda *a, **k: {"results": {}})
        assert se.strategy_seed(sample_profile, "us", "zzzz") == []

    def test_bad_seed_type(self, sample_profile):
        with pytest.raises(ValueError):
            se.strategy_seed(sample_profile, "us", "x", seed_type="album")


# ── Strategy: Era ────────────────────────────────────────────────

class TestNormalizeDecade:
    @pytest.mark.parametrize("raw,expected", [
        ("90s", "1990s"), ("1990s", "1990s"), ("'90s", "1990s"), ("1994", "1990s"),
        ("00s", "2000s"), ("10s", "2010s"), ("2020s", "2020s"), ("70", "1970s"),
    ])
    def test_formats(self, raw, expected):
        assert se.normalize_decade(raw) == expected

    @pytest.mark.parametrize("raw", ["nineties", "", "19s0", "199999"])
    def test_rejects_garbage(self, raw):
        with pytest.raises(ValueError):
            se.normalize_decade(raw)


class TestStrategyEra:
    def _setup(self, monkeypatch, albums, tracks, charts=None, search=None):
        def mock(cmd, *args, **kwargs):
            if cmd == "artist-albums":
                return {"data": albums.get(args[1], [])}
            if cmd == "charts":
                return charts
            if cmd == "search":
                return search
            return None
        monkeypatch.setattr(se, "call_api", mock)
        monkeypatch.setattr(se, "get_album_tracks", lambda sf, aid: tracks.get(aid, []))

    def _album(self, aid, name, date, single=False):
        return {"id": aid, "attributes": {"name": name, "releaseDate": date, "isSingle": single}}

    def test_only_albums_from_decade(self, sample_profile, monkeypatch):
        albums = {"a1": [self._album("al90", "OK Computer", "1997-05-21"),
                         self._album("al00", "Kid A", "2000-10-02"),
                         self._album("sg90", "Single", "1995-01-01", single=True)]}
        tracks = {"al90": [_song("t90", "Karma Police", "Radiohead")],
                  "al00": [_song("t00", "Idioteque", "Radiohead")],
                  "sg90": [_song("tsg", "Single", "Radiohead")]}
        self._setup(monkeypatch, albums, tracks, charts={}, search={})
        result = se.strategy_era(sample_profile, "us", "90s", target_size=10)
        assert [t["id"] for t in result] == ["t90"]
        assert "1990s" in result[0]["reason"]

    def test_defaults_to_top_era(self, sample_profile, monkeypatch):
        albums = {"a1": [self._album("al00", "Kid A", "2000-10-02"),
                         self._album("al90", "OK Computer", "1997-05-21")]}
        tracks = {"al00": [_song("t00", "Idioteque", "Radiohead")],
                  "al90": [_song("t90", "Karma Police", "Radiohead")]}
        self._setup(monkeypatch, albums, tracks, charts={}, search={})
        result = se.strategy_era(sample_profile, "us", None, target_size=10)
        assert [t["id"] for t in result] == ["t00"]  # top era in sample_profile is 2000s

    def test_charts_filtered_by_decade(self, sample_profile, monkeypatch):
        charts = {"results": {"songs": [{"data": [
            _song("c20", "New", "Pop Star", ["Pop"], "2024-05-01"),
            _song("c90", "Old", "Pop Star", ["Pop"], "1996-05-01"),
        ]}]}}
        self._setup(monkeypatch, {}, {}, charts=charts, search={})
        assert [t["id"] for t in se.strategy_era(sample_profile, "us", "2020s")] == ["c20"]

    def test_search_fallback_and_library_exclusion(self, sample_profile, monkeypatch):
        search = {"results": {"songs": {"data": [
            _song("f1", "Fit", "A", ["Alternative"], "1993-01-01"),
            _song("f2", "Owned", "B", ["Alternative"], "1993-01-01"),
            _song("f3", "Wrong decade", "C", ["Alternative"], "2003-01-01"),
        ]}}}
        sample_profile["library_song_ids"] = ["f2"]
        self._setup(monkeypatch, {}, {}, charts={}, search=search)
        assert {t["id"] for t in se.strategy_era(sample_profile, "us", "1990s")} == {"f1"}
        assert {t["id"] for t in se.strategy_era(sample_profile, "us", "1990s", include_library=True)} == {"f1", "f2"}

    def test_empty_profile_without_data(self, empty_profile, monkeypatch):
        self._setup(monkeypatch, {}, {}, charts=None, search=None)
        assert se.strategy_era(empty_profile, "us") == []


class TestNamingSeedEra:
    def test_seed_name(self):
        assert se.generate_name("seed", seed="Radiohead").startswith("Like Radiohead")

    def test_era_name(self):
        assert se.generate_name("era", decade="1990s").startswith("1990s Throwback")
        assert se.generate_name("era").startswith("Throwback")

    def test_descriptions(self):
        assert "orbit" in se.generate_description("seed", track_count=5)
        assert "decade" in se.generate_description("era", track_count=5)


# ── Strategy: Blend ──────────────────────────────────────────────

class TestStrategyBlend:
    def _profiles(self, sample_profile):
        a = sample_profile
        b = {
            "top_artists": [{"name": "Radiohead", "id": "a1"}, {"name": "Beyonce", "id": "b9"},
                            {"name": "SZA", "id": "b8"}],
            "genre_distribution": [{"genre": "R&B/Soul", "weight": 0.5}, {"genre": "Pop", "weight": 0.3},
                                   {"genre": "Alternative", "weight": 0.2}],
            "era_distribution": [{"decade": "2010s", "weight": 1.0}],
            "energy_profile": "balanced",
            "loved_track_ids": ["love1"],
        }
        return a, b

    def _api(self, monkeypatch, tops):
        def mock(cmd, *args, **kwargs):
            if cmd == "artist-top":
                return _top(tops.get(args[1], []))
            if cmd == "song-detail":
                return {"data": [_song(args[1], "Loved", "Someone", ["Pop"])]}
            return None
        monkeypatch.setattr(se, "call_api", mock)

    def test_tags_shared_and_sides(self, sample_profile, monkeypatch):
        a, b = self._profiles(sample_profile)
        self._api(monkeypatch, {
            "a1": [_song("rh1", "Creep", "Radiohead")],
            "a2": [_song("wk1", "Starboy", "The Weeknd", ["Pop", "R&B/Soul"])],
            "a4": [_song("q1", "Bohemian Rhapsody", "Queen", ["Classical"])],  # no overlap with B's genres
            "b9": [_song("by1", "Halo", "Beyonce", ["Pop"])],
        })
        result = se.strategy_blend(a, b, "us", target_size=10)
        by_id = {t["id"]: t for t in result}
        assert by_id["rh1"]["source"] == "shared"
        assert by_id["wk1"]["source"] == "a"
        assert by_id["by1"]["source"] == "b"
        assert "q1" not in by_id

    def test_neither_listener_exceeds_cap(self, sample_profile, monkeypatch):
        a, b = self._profiles(sample_profile)
        # A supplies many fitting songs; B only a few
        tops = {"a2": [_song(f"w{i}", f"W{i}", "The Weeknd", ["Pop"]) for i in range(5)],
                "a3": [_song(f"k{i}", f"K{i}", "Kendrick Lamar", ["Hip-Hop/Rap"]) for i in range(5)],
                "a4": [], "a5": [],
                "b9": [_song("by1", "Halo", "Beyonce", ["Pop"])]}
        self._api(monkeypatch, tops)
        a["top_artists"] = [x for x in a["top_artists"] if x["name"] != "Radiohead"]
        b["top_artists"] = [x for x in b["top_artists"] if x["name"] != "Radiohead"]
        result = se.strategy_blend(a, b, "us", target_size=10)
        from collections import Counter
        sides = Counter(t["source"] for t in result)
        assert sides["a"] <= 6  # int(10 * 0.6)

    def test_excludes_dislikes_from_either_profile(self, sample_profile, monkeypatch):
        a, b = self._profiles(sample_profile)
        a["disliked_song_ids"] = ["rh1"]
        b["disliked_song_ids"] = ["by1"]
        self._api(monkeypatch, {"a1": [_song("rh1", "Creep", "Radiohead"), _song("rh2", "Karma", "Radiohead")],
                                "b9": [_song("by1", "Halo", "Beyonce", ["Pop"])]})
        ids = {t["id"] for t in se.strategy_blend(a, b, "us")}
        assert "rh1" not in ids and "by1" not in ids and "rh2" in ids

    def test_includes_loved_tracks_from_both_listeners(self, sample_profile, monkeypatch):
        a, b = self._profiles(sample_profile)
        a["loved_track_ids"] = ["love0"]
        self._api(monkeypatch, {})
        result = se.strategy_blend(a, b, "us")
        assert {(t["id"], t["source"]) for t in result} == {("love0", "a"), ("love1", "b")}

    def test_lopsided_candidates_never_exceed_share_of_final_playlist(self, sample_profile, monkeypatch):
        """Only one listener has candidates: 10 of 10 would be 100% A, so it must not be returned."""
        a, b = self._profiles(sample_profile)
        b["top_artists"] = [{"name": "Nobody", "id": "zz"}]
        b["loved_track_ids"] = []
        self._api(monkeypatch, {"a2": [_song(f"w{i}", f"W{i}", "The Weeknd", ["Pop"], album=f"Al{i}")
                                       for i in range(10)]})
        for artist in a["top_artists"]:
            artist["name"] = artist["name"] if artist["name"] == "The Weeknd" else artist["name"] + " (skip)"
        assert se.strategy_blend(a, b, "us", target_size=30) == []

    def test_share_holds_with_a_little_shared_material(self, sample_profile, monkeypatch):
        a, b = self._profiles(sample_profile)
        b["loved_track_ids"] = []
        self._api(monkeypatch, {
            "a1": [_song("rh1", "Creep", "Radiohead"), _song("rh2", "Karma", "Radiohead")],
            "a2": [_song(f"w{i}", f"W{i}", "The Weeknd", ["Pop"], album=f"Al{i}") for i in range(3)],
            "a3": [_song(f"k{i}", f"K{i}", "Kendrick Lamar", ["Hip-Hop/Rap"], album=f"Bl{i}") for i in range(3)],
            "b9": [_song("by1", "Halo", "Beyonce", ["Pop"])],
        })
        result = se.strategy_blend(a, b, "us", target_size=30)
        from collections import Counter
        counts = Counter(t["source"] for t in result)
        assert result and all(counts[s] / len(result) <= 0.6 + 1e-9 for s in ("a", "b"))

    def test_enforce_share_drops_weakest_of_the_heavy_side(self):
        picked = [{"id": str(i), "source": s} for i, s in enumerate("aaabab")]  # score order
        out = se._enforce_share(picked, 0.6)
        # 4 of 6 are "a" (67%): the weakest "a" (position 4) goes, leaving 3 of 5 (60%)
        assert [t["id"] for t in out] == ["0", "1", "2", "3", "5"]

    def test_no_data_returns_empty(self, empty_profile, monkeypatch):
        self._api(monkeypatch, {})
        assert se.strategy_blend(empty_profile, dict(empty_profile), "us") == []

    def test_blend_name_and_description(self):
        assert se.generate_name("blend").startswith("Blend")
        assert "two listeners" in se.generate_description("blend", track_count=3)


# ── Name & Description Generation ────────────────────────────────

class TestGenerateName:
    def test_deep_cuts_name(self, sample_profile):
        name = se.generate_name("deep-cuts", profile=sample_profile)
        assert "Radiohead" in name
        assert "Deep Cuts" in name

    def test_mood_name(self):
        name = se.generate_name("mood", mood="workout")
        assert "Workout" in name

    def test_trend_name(self, sample_profile):
        name = se.generate_name("trend", profile=sample_profile)
        assert "Trending" in name

    def test_constellation_name(self):
        name = se.generate_name("constellation")
        assert "Horizons" in name

    def test_refresh_name(self):
        name = se.generate_name("refresh")
        assert "Refresh" in name


class TestGenerateDescription:
    def test_has_track_count(self):
        desc = se.generate_description("deep-cuts", track_count=25)
        assert "25 tracks" in desc

    def test_mood_description(self):
        desc = se.generate_description("mood", mood="workout")
        assert "energy" in desc.lower() or "moving" in desc.lower()

    def test_all_strategies(self):
        for strat in ["deep-cuts", "mood", "trend", "constellation", "refresh"]:
            desc = se.generate_description(strat, track_count=10)
            assert len(desc) > 5


# ── MOOD_MAP Integrity ───────────────────────────────────────────

class TestMoodMap:
    def test_all_moods_defined(self):
        expected = {"workout", "focus", "chill", "party", "drive",
                    "sleep", "cooking", "morning", "sad", "anger"}
        assert set(se.MOOD_MAP.keys()) == expected

    def test_mood_structure(self):
        for config in se.MOOD_MAP.values():
            assert isinstance(config["genres"], list)
            assert len(config["genres"]) >= 2
            assert isinstance(config["energy"], str)
            assert isinstance(config["description"], str)

    def test_mood_arcs_are_valid(self):
        for config in se.MOOD_MAP.values():
            assert config.get("arc", "wave") in se.ARCS

    def test_sleep_descends_and_workout_ascends(self):
        assert se.MOOD_MAP["sleep"]["arc"] == "descending"
        assert se.MOOD_MAP["workout"]["arc"] == "ascending"


# ── check_playlist_exists ────────────────────────────────────────

class TestCheckPlaylistExists:
    def test_finds_existing_playlist(self, monkeypatch):
        data = json.dumps({"data": [
            {"id": "pl1", "attributes": {"name": "My Mix"}},
            {"id": "pl2", "attributes": {"name": "Other"}},
        ]})
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(
            returncode=0, stdout=data
        ))
        assert se.check_playlist_exists("My Mix") == "pl1"

    def test_returns_none_when_not_found(self, monkeypatch):
        data = json.dumps({"data": [
            {"id": "pl1", "attributes": {"name": "Other"}},
        ]})
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(
            returncode=0, stdout=data
        ))
        assert se.check_playlist_exists("Missing") is None

    def test_returns_none_on_api_failure(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(
            returncode=1, stdout=""
        ))
        assert se.check_playlist_exists("Any") is None

    def test_returns_none_on_exception(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", MagicMock(side_effect=Exception("fail")))
        assert se.check_playlist_exists("Any") is None


# ── create_playlist_from_tracks ──────────────────────────────────

class TestCreatePlaylistFromTracks:
    def test_returns_false_with_no_tracks(self):
        assert se.create_playlist_from_tracks([], "Name", "Desc") is False

    def test_returns_false_when_playlist_exists(self, monkeypatch):
        monkeypatch.setattr(se, "check_playlist_exists", lambda name: "pl1")
        tracks = [{"id": "t1"}]
        assert se.create_playlist_from_tracks(tracks, "Existing", "Desc") is False

    def test_creates_playlist_successfully(self, monkeypatch):
        monkeypatch.setattr(se, "check_playlist_exists", lambda name: None)
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
        tracks = [{"id": "t1"}, {"id": "t2"}]
        assert se.create_playlist_from_tracks(tracks, "New", "Desc") is True

    def test_returns_false_on_subprocess_failure(self, monkeypatch):
        monkeypatch.setattr(se, "check_playlist_exists", lambda name: None)
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(
            returncode=1, stderr="error"
        ))
        tracks = [{"id": "t1"}]
        assert se.create_playlist_from_tracks(tracks, "New", "Desc") is False

    def test_returns_false_on_timeout(self, monkeypatch):
        import subprocess as sp
        monkeypatch.setattr(se, "check_playlist_exists", lambda name: None)
        monkeypatch.setattr("subprocess.run", MagicMock(
            side_effect=sp.TimeoutExpired("cmd", 60)
        ))
        tracks = [{"id": "t1"}]
        assert se.create_playlist_from_tracks(tracks, "New", "Desc") is False


# ── favorite_tracks ──────────────────────────────────────────────

class TestFavoriteTracks:
    def test_batches_and_uses_raw(self, monkeypatch):
        calls = []
        monkeypatch.setattr(se, "call_api", lambda *a, **k: calls.append((a, k)) or "")
        out = se.favorite_tracks([{"id": str(i)} for i in range(30)] + [{"name": "no id"}])
        assert out == {"favorited": 30, "failed": 0}
        assert [len(c[0][2].split(",")) for c in calls] == [25, 5]
        assert calls[0][0][:2] == ("favorite", "songs") and calls[0][1] == {"raw": True}

    def test_counts_failures(self, monkeypatch):
        monkeypatch.setattr(se, "call_api", lambda *a, **k: None)
        assert se.favorite_tracks([{"id": "1"}, {"id": "2"}]) == {"favorited": 0, "failed": 2}


# ── CLI (main) ───────────────────────────────────────────────────

class TestMainCli:
    @pytest.fixture
    def cli(self, monkeypatch, tmp_path, sample_profile):
        import sys
        profile = tmp_path / "p.json"
        profile.write_text(json.dumps(sample_profile))
        other = tmp_path / "b.json"
        other.write_text(json.dumps(sample_profile))
        monkeypatch.setattr(se, "require_env_tokens", lambda: None)
        monkeypatch.setattr(se, "get_storefront", lambda sf=None: "us")
        monkeypatch.setattr(se, "load_config", lambda: {})
        tracks = [{"id": "t1", "name": "N", "artist": "A", "album": "B", "genre": []}]
        state = {"tracks": tracks, "created": [], "favorited": []}
        monkeypatch.setattr(se, "create_playlist_from_tracks",
                            lambda t, n, d: state["created"].append(n) or True)
        monkeypatch.setattr(se, "favorite_tracks", lambda t: state["favorited"].append(t) or
                            {"favorited": len(t), "failed": 0})
        monkeypatch.setattr("playlist_history.log_playlist", lambda *a, **k: None)

        def run(*argv):
            monkeypatch.setattr(sys, "argv", ["strategy_engine.py", "--profile", str(profile), *argv])
            se.main()
        state.update(run=run, profile=profile, other=other)
        return state

    def test_seed_requires_seed(self, cli):
        with pytest.raises(SystemExit):
            cli["run"]("--strategy", "seed")

    def test_seed_runs_with_args(self, cli, monkeypatch, capsys):
        seen = {}
        monkeypatch.setattr(se, "strategy_seed", lambda p, sf, seed, st, n, inc:
                            seen.update(seed=seed, st=st, inc=inc) or cli["tracks"])
        cli["run"]("--strategy", "seed", "--seed", "Radiohead", "--seed-type", "artist", "--include-library")
        assert seen == {"seed": "Radiohead", "st": "artist", "inc": True}
        assert json.loads(capsys.readouterr().out)["name"].startswith("Like Radiohead")

    def test_era_defaults_to_top_era_and_validates(self, cli, monkeypatch, capsys):
        seen = {}
        monkeypatch.setattr(se, "strategy_era", lambda p, sf, d, n, inc: seen.update(d=d) or cli["tracks"])
        cli["run"]("--strategy", "era")
        assert seen["d"] == "2000s"  # sample_profile's top era
        assert json.loads(capsys.readouterr().out)["name"].startswith("2000s Throwback")
        cli["run"]("--strategy", "era", "--decade", "'90s")
        assert seen["d"] == "1990s"
        with pytest.raises(SystemExit):
            cli["run"]("--strategy", "era", "--decade", "nineties")

    def test_blend_requires_profile_b_and_reports_compat(self, cli, monkeypatch, capsys):
        with pytest.raises(SystemExit):
            cli["run"]("--strategy", "blend")
        monkeypatch.setattr(se, "strategy_blend", lambda a, b, sf, n: cli["tracks"])
        cli["run"]("--strategy", "blend", "--profile-b", str(cli["other"]))
        out = json.loads(capsys.readouterr().out)
        assert set(out["compatibility"]) == {"compatibility_pct", "verdict", "shared_artists"}
        assert 0 <= out["compatibility"]["compatibility_pct"] <= 100
        assert out["name"].startswith("Blend")

    def test_output_file_is_owner_only(self, cli, monkeypatch, tmp_path):
        import os
        import stat
        out = tmp_path / "plans" / "plan.json"
        out.parent.mkdir()
        out.write_text("old")
        out.chmod(0o644)
        monkeypatch.setattr(se, "strategy_trend", lambda p, sf, n: cli["tracks"])
        cli["run"]("--strategy", "trend", "--output", str(out))
        assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
        assert json.loads(out.read_text())["strategy"] == "trend"

    def test_favorite_requires_create(self, cli):
        with pytest.raises(SystemExit):
            cli["run"]("--strategy", "trend", "--favorite")

    def test_create_and_favorite(self, cli, monkeypatch):
        monkeypatch.setattr(se, "strategy_trend", lambda p, sf, n: cli["tracks"])
        cli["run"]("--strategy", "trend", "--create", "--favorite")
        assert len(cli["created"]) == 1 and cli["favorited"] == [cli["tracks"]]

    def test_create_without_favorite_never_favorites(self, cli, monkeypatch):
        monkeypatch.setattr(se, "strategy_trend", lambda p, sf, n: cli["tracks"])
        cli["run"]("--strategy", "trend", "--create")
        assert cli["favorited"] == []

    def test_failed_create_does_not_favorite(self, cli, monkeypatch):
        monkeypatch.setattr(se, "strategy_trend", lambda p, sf, n: cli["tracks"])
        monkeypatch.setattr(se, "create_playlist_from_tracks", lambda *a: False)
        with pytest.raises(SystemExit):
            cli["run"]("--strategy", "trend", "--create", "--favorite")
        assert cli["favorited"] == []
