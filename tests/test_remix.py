"""strategies/remix.py: keep what fits, swap the rest."""

import random

import pytest

import strategy_engine as se
from strategies.remix import LAST_REMIX, parse_playlist_ref, strategy_remix
from tests.strategy_helpers import patch_everywhere

PLAYLIST_ID = "pl.abc123"


def song(sid: str, name: str, artist: str, genres: list[str]) -> dict:
    return {"id": sid, "type": "songs", "attributes": {
        "name": name, "artistName": artist, "genreNames": [*genres, "Music"], "albumName": f"{artist} LP",
        "durationInMillis": 200_000}}


ORIGINAL = [
    song("k1", "Guitar One", "Rockers", ["Rock"]),
    song("k2", "Guitar Two", "Indie Kids", ["Indie Rock"]),
    song("x1", "Club Banger", "DJ Loud", ["Dance"]),       # not this listener's sound
    song("x2", "Smooth Hour", "Sax Man", ["Jazz"]),         # not this listener's sound
    song("own", "Already Mine", "Rockers", ["Rock"]),       # in their library
    song("bad", "Thumbs Down", "Rockers", ["Rock"]),        # they disliked it
]

ARTIST_IDS = {"Rockers": "ar1", "Indie Kids": "ar2", "DJ Loud": "ar3", "Sax Man": "ar4"}
TOP = {"ar1": [song("r-new", "Rockers Hit", "Rockers", ["Rock"])],
       "ar2": [song("i-new", "Indie Hit", "Indie Kids", ["Indie Rock"])],
       "ar3": [song("d-new", "More Club", "DJ Loud", ["Dance"])],
       "ar4": [song("s-new", "More Sax", "Sax Man", ["Jazz"])]}
SIMILAR = {"ar3": [{"id": "ar2", "attributes": {"name": "Indie Kids"}}], "ar4": []}

PROFILE = {
    "top_artists": [{"name": "Rockers", "id": "ar1"}],
    "genre_distribution": [{"genre": "Rock", "weight": 0.6}, {"genre": "Indie Rock", "weight": 0.4}],
    "library_song_ids": ["own"], "disliked_song_ids": ["bad"],
}


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    def fake_api(cmd, *args, **kwargs):
        if cmd == "catalog-playlist":
            if args[1] != PLAYLIST_ID:
                return None
            return {"data": [{"id": PLAYLIST_ID, "attributes": {"name": "Party Starters"},
                              "relationships": {"tracks": {"data": ORIGINAL}}}]}
        if cmd == "artist-top":
            return {"data": [{"views": {"top-songs": {"data": TOP.get(args[1], [])}}}]}
        if cmd == "similar-artists":
            return {"data": SIMILAR.get(args[1], [])}
        return None

    patch_everywhere(monkeypatch, "call_api", fake_api)
    patch_everywhere(monkeypatch, "search_artist", lambda sf, name: (
        {"id": ARTIST_IDS[name], "attributes": {"name": name}} if name in ARTIST_IDS else None))
    se.USER_FILTERS.clear()


def remix(**kwargs) -> list[dict]:
    return strategy_remix(PROFILE, "us", kwargs.pop("playlist", PLAYLIST_ID), 20, rng=random.Random(1), **kwargs)


class TestParsePlaylistRef:
    @pytest.mark.parametrize("value, expected", [
        ("pl.f4d106fed2bd41149aaacabb233eb5eb", (None, "pl.f4d106fed2bd41149aaacabb233eb5eb")),
        ("  pl.abc  ", (None, "pl.abc")),
        ("https://music.apple.com/us/playlist/todays-hits/pl.f4d1", ("us", "pl.f4d1")),
        ("https://music.apple.com/gb/playlist/chill/pl.abc?l=en", ("gb", "pl.abc")),
    ])
    def test_accepts_urls_and_ids(self, value, expected):
        assert parse_playlist_ref(value) == expected

    @pytest.mark.parametrize("value", [
        "", "todays-hits", "pl.", "pl.a b", "https://evil.example/us/playlist/x/pl.abc",
        "https://music.apple.com/us/album/x/123", "https://music.apple.com.evil.example/us/playlist/x/pl.abc",
        "ftp://music.apple.com/us/playlist/x/pl.abc", "pl.abc/../../me",
    ])
    def test_refuses_everything_else(self, value):
        with pytest.raises(ValueError):
            parse_playlist_ref(value)


class TestRemix:
    def test_keeps_what_fits_and_says_so(self):
        tracks = remix()
        kept = {t["id"]: t for t in tracks if t["source"] == "remix_keep"}
        assert set(kept) == {"k1", "k2"} and "fits your taste" in kept["k1"]["reason"]

    def test_swaps_the_rest_and_says_why(self):
        swapped = {t["id"]: t for t in remix() if t["source"] == "remix_swap"}
        assert "r-new" in swapped or "i-new" in swapped  # DJ Loud / Sax Man got taste-matched stand-ins
        reasons = " ".join(t["reason"] for t in swapped.values())
        assert "Club Banger" in reasons and "Smooth Hour" in reasons

    def test_a_dropped_artists_own_song_only_swaps_in_if_it_suits_you(self):
        ids = {t["id"] for t in remix()}
        assert "d-new" not in ids and "s-new" not in ids

    def test_never_returns_library_or_disliked_tracks(self):
        assert {"own", "bad"}.isdisjoint(t["id"] for t in remix())

    def test_include_library_keeps_an_owned_song_that_fits(self):
        assert "own" in {t["id"] for t in remix(include_library=True)}

    def test_never_duplicates_the_original_in_a_swap(self):
        ids = [t["id"] for t in remix()]
        assert len(ids) == len(set(ids))

    def test_records_how_much_was_kept(self):
        tracks = remix()
        assert LAST_REMIX["name"] == "Party Starters" and LAST_REMIX["original"] == len(ORIGINAL)
        assert LAST_REMIX["kept"] + LAST_REMIX["swapped"] == len(tracks)
        assert LAST_REMIX["kept"] == 2

    def test_each_run_starts_clean(self):
        remix()
        assert remix(playlist="pl.missing") == [] and "kept" not in LAST_REMIX

    @pytest.mark.parametrize("playlist", ["pl.missing", "not a playlist"])
    def test_an_unknown_or_malformed_playlist_is_reported_not_raised(self, playlist, capsys):
        assert remix(playlist=playlist) == []
        assert "ERROR" in capsys.readouterr().err

    def test_every_track_has_a_duration_for_minutes_mode(self):
        assert all(isinstance(t["duration_ms"], int) for t in remix())

    def test_the_user_filters_still_apply(self):
        se.USER_FILTERS.update(se.user_filters({"excluded_artists": ["Indie Kids"]}, set()))
        assert "Indie Kids" not in {t["artist"] for t in remix()}
