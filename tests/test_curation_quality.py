"""Curation quality: every strategy against one synthetic catalog, with a fixed RNG.

The demo catalog is too small to fill a playlist, so tuning a weight shows no difference
there. This catalog is big enough that each strategy reaches its target length, and the
checks below say what a good playlist looks like: full length, spread across artists and
albums, nothing the listener owns, disliked, excluded or heard last week, and each
strategy's own promise (sleep descends, constellation fans out, blend stays balanced).
Change a weight and these say whether the playlists got worse.
"""

import random
from collections import Counter
from itertools import pairwise

import pytest

import strategy_engine as se
from _common import taste_affinity, track_energy, user_filters

# ── Synthetic catalog ────────────────────────────────────────────

# name, genres, first release year
ARTISTS = [
    ("Static Bloom", ["Alternative"], 1994), ("Glass Harbour", ["Alternative"], 1999),
    ("Paper Lanterns", ["Indie Rock"], 2004), ("Iron Meadow", ["Rock"], 1988),
    ("Northbound", ["Garage Rock"], 2001), ("Velvet Engine", ["Hard Rock"], 1985),
    ("Low Orbit", ["Electronic"], 2008), ("Night Shift", ["Dance"], 2012),
    ("Still Water", ["Ambient"], 1996), ("Slow Tide", ["New Age"], 1990),
    ("Blue Room", ["Jazz"], 1979), ("Late Set", ["Smooth Jazz"], 1992),
    ("Sugar Kites", ["Pop"], 2010), ("Neon Choir", ["Synth Pop"], 1983),
    ("Corner Talk", ["Hip-Hop/Rap"], 2005), ("Quiet Strings", ["Classical"], 1970),
    ("Ember Folk", ["Folk"], 2009), ("Red Clay", ["Country"], 2003),
]
ALBUMS_PER_ARTIST, TRACKS_PER_ALBUM = 4, 10


def _aid(i: int) -> str:
    return f"ar{i}"


def _song(artist_i: int, album_j: int, track_k: int) -> dict:
    name, genres, year = ARTISTS[artist_i]
    title = f"{name} {album_j}-{track_k}"
    if track_k == TRACKS_PER_ALBUM:  # every album ends on a live take, which deep cuts must skip
        title = f"{name} {album_j}-1 (Live)"
    return {"id": f"s{artist_i}-{album_j}-{track_k}", "type": "songs", "attributes": {
        "name": title, "artistName": name, "genreNames": [*genres, "Music"], "trackNumber": track_k,
        "releaseDate": f"{year + 4 * album_j}-06-01", "albumName": f"{name} LP{album_j}"}}


def _album(artist_i: int, album_j: int) -> dict:
    name, _, year = ARTISTS[artist_i]
    return {"id": f"al{artist_i}-{album_j}", "attributes": {
        "name": f"{name} LP{album_j}", "releaseDate": f"{year + 4 * album_j}-06-01", "isSingle": False}}


def _artist(i: int) -> dict:
    name, genres, _ = ARTISTS[i]
    return {"id": _aid(i), "type": "artists", "attributes": {"name": name, "genreNames": genres}}


def _index(artist_id: str) -> int:
    return int(artist_id.removeprefix("ar"))


def _similar(i: int) -> list[int]:
    """Neighbours: the next artists in the list, so similar artists cross genre lines."""
    return [(i + step) % len(ARTISTS) for step in (1, 2, 3, 4, 5, 7, 9, 11)]


CHARTS = {"results": {"songs": [{"data": [
    _song(i, j, k) for k in (2, 3) for j in range(ALBUMS_PER_ARTIST) for i in range(len(ARTISTS))]}]}}


def fake_api(cmd: str, *args, **kwargs):
    if cmd == "charts":
        return CHARTS
    if cmd == "artist-albums":
        i = _index(args[1])
        return {"data": [_album(i, j) for j in range(ALBUMS_PER_ARTIST)]}
    if cmd == "artist-top":
        i = _index(args[1])
        return {"data": [{"views": {"top-songs": {"data": [_song(i, j, 1) for j in range(ALBUMS_PER_ARTIST)]}}}]}
    if cmd == "similar-artists":
        return {"data": [_artist(n) for n in _similar(_index(args[1]))]}
    if cmd == "search":
        query = args[1].lower()
        hits = [i for i, (name, genres, _) in enumerate(ARTISTS)
                if name.lower() in query or any(g.lower() in query for g in genres)]
        return {"results": {"artists": {"data": [_artist(i) for i in hits]},
                            "songs": {"data": [_song(i, j, 3) for i in hits for j in range(ALBUMS_PER_ARTIST)]}}}
    if cmd == "song-detail":
        i, j, k = (int(x) for x in args[1].removeprefix("s").split("-"))
        return {"data": [_song(i, j, k)]}
    if cmd == "playlist-tracks":
        return {"data": [_song(0, 0, k) | {"id": f"pl{k}"} for k in range(1, 6)]
                + [_song(1, 0, k) | {"id": f"pl1-{k}"} for k in range(1, 4)]}
    return None


def fake_album_tracks(sf: str, album_id: str) -> list[dict]:
    i, j = (int(x) for x in album_id.removeprefix("al").split("-"))
    return [_song(i, j, k) for k in range(1, TRACKS_PER_ALBUM + 1)]


def fake_search_artist(sf: str, name: str) -> dict | None:
    return next((_artist(i) for i, (n, _, _) in enumerate(ARTISTS) if n.lower() == name.lower()), None)


# ── Listener ─────────────────────────────────────────────────────

OWNED = {"s0-0-3", "s3-1-4", "s6-2-5"}
DISLIKED = {"s1-0-4", "s2-1-5", "s0-1-2"}
HEARD_LAST_WEEK = {"s4-0-6", "s5-1-3", "s0-2-2"}
EXCLUDED_ARTIST = "Velvet Engine"


def listener(top: list[int], genres: dict[str, float]) -> dict:
    return {
        "top_artists": [{"name": ARTISTS[i][0], "id": _aid(i), "play_weight": round(0.3 / (n + 1), 3)}
                        for n, i in enumerate(top)],
        "genre_distribution": [{"genre": g, "weight": w} for g, w in genres.items()],
        "era_distribution": [{"decade": "1990s", "weight": 0.5}, {"decade": "2000s", "weight": 0.3}],
        "library_song_ids": sorted(OWNED), "disliked_song_ids": sorted(DISLIKED),
        "loved_track_ids": ["s2-0-7", "s1-1-8"], "recently_added_artists": [],
    }


ROCK_FAN = listener([0, 1, 2, 3, 4, 5, 6, 13],
                    {"Alternative": 0.35, "Rock": 0.25, "Indie Rock": 0.15, "Electronic": 0.1, "Synth Pop": 0.05})
JAZZ_FAN = listener([10, 11, 9, 8, 15, 16, 0],
                    {"Jazz": 0.4, "New Age": 0.2, "Ambient": 0.15, "Classical": 0.1, "Alternative": 0.05})
ELECTRO_FAN = listener([6, 7, 13, 12, 0, 2, 8],
                       {"Electronic": 0.3, "Dance": 0.2, "Synth Pop": 0.15, "Alternative": 0.15, "Pop": 0.1})


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    monkeypatch.setattr(se, "call_api", fake_api)
    monkeypatch.setattr(se, "get_album_tracks", fake_album_tracks)
    monkeypatch.setattr(se, "search_artist", fake_search_artist)
    se.USER_FILTERS.clear()
    se.USER_FILTERS.update(user_filters({"excluded_artists": [EXCLUDED_ARTIST]}, HEARD_LAST_WEEK))
    yield
    se.USER_FILTERS.clear()


SIZE = 20
STRATEGIES = {
    "deep-cuts": lambda rng: se.strategy_deep_cuts(ROCK_FAN, "us", SIZE, rng=rng),
    "mood-workout": lambda rng: se.strategy_mood(ROCK_FAN, "us", "workout", SIZE, rng=rng),
    "mood-sleep": lambda rng: se.strategy_mood(JAZZ_FAN, "us", "sleep", SIZE, rng=rng),
    "trend": lambda rng: se.strategy_trend(ROCK_FAN, "us", SIZE, rng=rng),
    "constellation": lambda rng: se.strategy_constellation(ROCK_FAN, "us", SIZE, rng=rng),
    "similar": lambda rng: se.strategy_seed(ROCK_FAN, "us", "Static Bloom", "artist", SIZE, rng=rng),
    "era": lambda rng: se.strategy_era(ROCK_FAN, "us", "1990s", SIZE, rng=rng),
    "blend": lambda rng: se.strategy_blend(ROCK_FAN, ELECTRO_FAN, "us", SIZE, rng=rng),
}


def run(name: str, seed: int = 1) -> list[dict]:
    return STRATEGIES[name](random.Random(seed))


# ── Every strategy ───────────────────────────────────────────────

@pytest.mark.parametrize("name", STRATEGIES)
class TestEveryStrategy:
    def test_reaches_target_length(self, name):
        assert len(run(name)) == SIZE

    def test_spread_across_artists_and_albums(self, name):
        tracks = run(name)
        artists = Counter(t["artist"] for t in tracks)
        albums = Counter(t["album"] for t in tracks if t.get("album"))
        assert max(artists.values()) <= se.ARTIST_CAP
        assert not albums or max(albums.values()) <= se.ALBUM_CAP
        assert len(artists) >= 0.35 * len(tracks)

    def test_never_owned_disliked_excluded_or_recent(self, name):
        tracks = run(name)
        ids = [t["id"] for t in tracks]
        assert len(ids) == len(set(ids))
        assert not set(ids) & (OWNED | DISLIKED | HEARD_LAST_WEEK)
        assert EXCLUDED_ARTIST not in {t["artist"] for t in tracks}

    def test_repeatable_with_a_seed(self, name):
        assert [t["id"] for t in run(name, 3)] == [t["id"] for t in run(name, 3)]


# ── Each strategy's own promise ──────────────────────────────────

def test_deep_cuts_skip_hits_and_live_takes():
    tracks = run("deep-cuts")
    assert not any("(Live)" in t["name"] for t in tracks)
    assert not any(t["name"].endswith("-1") for t in tracks)  # track 1 of each album is a top song
    assert {t["artist"] for t in tracks} <= {ARTISTS[i][0] for i in (0, 1, 2, 3, 4, 6, 13)}


def _mostly_ordered(values: list[float], descending: bool = False) -> bool:
    """The arc's direction holds for most steps and from the first third to the last.

    Not strictly: sequence_tracks spaces out artists after ordering by energy, which can
    swap neighbours.
    """
    sign = -1 if descending else 1
    steps = [sign * (b - a) >= 0 for a, b in pairwise(values)]
    third = max(len(values) // 3, 1)
    first, last = sum(values[:third]) / third, sum(values[-third:]) / third
    return sum(steps) >= 0.75 * len(steps) and sign * (last - first) > 0


def test_sleep_is_quiet_and_descends():
    tracks = run("mood-sleep")
    target = se.MOOD_ENERGY[se.MOOD_MAP["sleep"]["energy"]]
    fits = [1 - abs(track_energy(t["genre"]) - target) for t in tracks]
    assert min(fits) >= se.MIN_ENERGY_FIT
    assert sum(fits) / len(fits) >= 0.75
    assert _mostly_ordered([t["energy"] for t in tracks], descending=True)


def test_sleep_draws_on_your_own_quiet_genres():
    """Jazz isn't a sleep genre, but it is this listener's top genre and it's quiet."""
    assert {"Jazz", "Smooth Jazz"} & {g for t in run("mood-sleep") for g in t["genre"]}


def test_workout_is_loud_and_ascends():
    tracks = run("mood-workout")
    energies = [t["energy"] for t in tracks]
    assert sum(energies) / len(energies) >= 0.65
    assert _mostly_ordered(energies)


def test_trend_is_mostly_your_taste_plus_a_few_wildcards():
    tracks = run("trend")
    off_taste = [t for t in tracks if taste_affinity(t["genre"], ROCK_FAN["genre_distribution"]) == 0]
    assert 1 <= len(off_taste) <= se.TREND_WILDCARDS


def test_constellation_fans_out_from_familiar_to_frontier():
    zones = [t["zone"] for t in run("constellation")]
    order = {"familiar": 0, "expansion": 1, "frontier": 2}
    assert [order[z] for z in zones] == sorted(order[z] for z in zones)
    assert zones[0] == "familiar" and len(set(zones)) >= 2


def test_similar_leans_on_the_seed_sound():
    tracks = run("similar")
    close = [t for t in tracks if se.best_genre_match(t["genre"], ["Alternative"]) >= 0.5]
    assert len(close) >= 0.6 * len(tracks)


def test_era_stays_in_its_decade():
    years = [_song(*map(int, t["id"].removeprefix("s").split("-"))) for t in run("era")]
    assert {se._release_decade(s["attributes"]["releaseDate"]) for s in years} == {"1990s"}


def test_blend_stays_balanced():
    tracks = run("blend")
    sources = Counter(t["source"] for t in tracks)
    assert max(sources["a"], sources["b"]) <= se.BLEND_MAX_SHARE * len(tracks)
    assert sources["shared"] >= 1


def test_distant_tastes_blend_shorter_but_never_lopsided():
    """Rock vs jazz share one artist: the blend shrinks rather than letting one listener take over."""
    tracks = se.strategy_blend(ROCK_FAN, JAZZ_FAN, "us", SIZE, rng=random.Random(1))
    sources = Counter(t["source"] for t in tracks)
    assert SIZE // 2 <= len(tracks) <= SIZE
    assert max(sources["a"], sources["b"]) <= se.BLEND_MAX_SHARE * len(tracks)


# ── Likes and dislikes steer (#64) ───────────────────────────────

@pytest.mark.parametrize("name,disliked", [("deep-cuts", "Neon Choir"), ("trend", "Neon Choir"), ("era", "Neon Choir"),
                                           ("similar", "Night Shift"), ("mood-workout", "Sugar Kites")])
def test_an_artist_you_disliked_twice_drops_out(name, disliked):
    """The issue's acceptance test. These artists are lightly played or not in the top list at all;
    for an artist you play a lot the penalty is halved on purpose (see TestRatingSignals)."""
    assert disliked in {t["artist"] for t in run(name)}  # there to begin with
    signals = _signals([(-1, {"artistName": disliked, "genreNames": []})] * 2)
    se.USER_FILTERS.update(user_filters({"excluded_artists": [EXCLUDED_ARTIST]}, HEARD_LAST_WEEK,
                                        {**ROCK_FAN, "rating_signals": signals}))
    assert disliked not in {t["artist"] for t in run(name)}


def test_a_liked_artist_gets_more_room():
    liked = "Corner Talk"  # 2 tracks in the workout mix before
    before = Counter(t["artist"] for t in run("mood-workout"))[liked]
    signals = _signals([(1, {"artistName": liked, "genreNames": []})] * 3)
    se.USER_FILTERS.update(user_filters({"excluded_artists": [EXCLUDED_ARTIST]}, HEARD_LAST_WEEK,
                                        {**ROCK_FAN, "rating_signals": signals}))
    tracks = [t for t in run("mood-workout") if t["artist"] == liked]
    assert len(tracks) > before
    assert all("boosted: you liked 3 songs by Corner Talk" in t["reason"] for t in tracks)


def _signals(pairs):
    """rating_signals_from with a distinct song ID per (value, attrs) pair."""
    from _common import rating_signals_from
    return rating_signals_from([(f"song{i}", value, attrs) for i, (value, attrs) in enumerate(pairs)])
