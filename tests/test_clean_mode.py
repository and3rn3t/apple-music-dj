"""Clean mode: keep explicit songs out, using the clean version of the same song when there is one."""

import pytest

import _common


def song(sid: str, name: str, artist: str, rating: str | None) -> dict:
    attrs = {"name": name, "artistName": artist, "albumName": f"{artist} LP", "durationInMillis": 200_000}
    if rating:
        attrs["contentRating"] = rating
    return {"id": sid, "type": "songs", "attributes": attrs}


def candidate(sid: str, name: str, artist: str = "A", explicit: bool = False) -> dict:
    return {"id": sid, "name": name, "artist": artist, "album": "x", "genre": ["Rock"], "explicit": explicit,
            "reason": "r", "_score": 0.5, "duration_ms": 1}


@pytest.fixture
def searches(monkeypatch):
    """Record catalog searches; the catalog holds a clean twin of 'Loud' and nothing for 'Filthy'."""
    calls: list[tuple] = []

    def fake(cmd, *args, **kwargs):
        calls.append((cmd, *args))
        term = args[1].lower()
        songs = [song("loud-x", "Loud", "A", "explicit"), song("loud-c", "Loud", "A", "clean"),
                 song("other", "Loud (Live)", "A", None), song("filthy-x", "Filthy", "A", "explicit")]
        return {"results": {"songs": {"data": [s for s in songs if s["attributes"]["name"].lower() in term]}}}

    monkeypatch.setattr(_common, "call_api", fake)
    return calls


def filters(**kw):
    return _common.user_filters({"clean_only": True}, storefront="us", **kw)


class TestSwitch:
    def test_off_by_default(self):
        assert _common.user_filters({})["clean_only"] is False

    def test_config_turns_it_on(self):
        assert _common.user_filters({"clean_only": True})["clean_only"] is True

    @pytest.mark.parametrize("value", ["yes", 1, None])
    def test_only_a_real_true_counts(self, value):
        assert _common.user_filters({"clean_only": value})["clean_only"] is False

    def test_the_flag_overrides_the_config(self):
        assert _common.user_filters({}, clean_only=True)["clean_only"] is True
        assert _common.user_filters({"clean_only": True}, clean_only=False)["clean_only"] is False


class TestPasses:
    def test_explicit_is_refused_in_clean_mode_only(self):
        assert not _common.passes_user_filters(candidate("1", "x", explicit=True), filters())
        assert _common.passes_user_filters(candidate("1", "x", explicit=True), _common.user_filters({}))
        assert _common.passes_user_filters(candidate("1", "x"), filters())

    def test_a_candidate_without_the_field_is_not_explicit(self):
        assert _common.passes_user_filters({"id": "1", "artist": "A"}, filters())


class TestSwap:
    def test_uses_the_clean_version(self, searches):
        out = _common.swap_explicit_for_clean(candidate("loud-x", "Loud", explicit=True), filters())
        assert out["id"] == "loud-c" and out["explicit"] is False and out["reason"] == "r (clean version)"
        assert out["_score"] == 0.5 and out["genre"] == ["Rock"]  # the rest is unchanged

    def test_a_live_take_is_not_the_clean_version(self, searches):
        out = _common.swap_explicit_for_clean(candidate("loud-x", "Loud", explicit=True), filters())
        assert out["id"] != "other"

    def test_no_clean_version_leaves_it_to_be_dropped(self, searches):
        c = candidate("filthy-x", "Filthy", explicit=True)
        assert _common.swap_explicit_for_clean(c, filters()) is c

    def test_clean_songs_cost_no_lookup(self, searches):
        _common.swap_explicit_for_clean(candidate("1", "Loud"), filters())
        assert searches == []

    def test_each_song_is_looked_up_once(self, searches):
        f = filters()
        for _ in range(3):
            _common.swap_explicit_for_clean(candidate("loud-x", "Loud", explicit=True), f)
        assert len(searches) == 1

    def test_lookups_are_capped_per_run(self, searches):
        f = filters()
        for i in range(_common.CLEAN_LOOKUP_LIMIT + 5):
            _common.swap_explicit_for_clean(candidate(f"x{i}", f"Song {i}", explicit=True), f)
        assert len(searches) == _common.CLEAN_LOOKUP_LIMIT

    def test_needs_a_storefront(self, searches):
        c = candidate("loud-x", "Loud", explicit=True)
        assert _common.swap_explicit_for_clean(c, _common.user_filters({"clean_only": True})) is c and searches == []

    def test_does_nothing_outside_clean_mode(self, searches):
        c = candidate("loud-x", "Loud", explicit=True)
        assert _common.swap_explicit_for_clean(c, _common.user_filters({}, storefront="us")) is c and searches == []

    def test_a_failed_search_keeps_the_song_explicit(self, monkeypatch):
        monkeypatch.setattr(_common, "call_api", lambda *a, **k: None)
        c = candidate("loud-x", "Loud", explicit=True)
        assert _common.swap_explicit_for_clean(c, filters()) is c


class TestApply:
    def test_swaps_what_it_can_and_drops_the_rest(self, searches):
        cands = [candidate("a", "Fine"), candidate("loud-x", "Loud", explicit=True),
                 candidate("filthy-x", "Filthy", explicit=True)]
        out = _common.apply_user_filters(cands, filters())
        assert [c["id"] for c in out] == ["a", "loud-c"]


class TestDailyPick:
    def test_the_daily_pick_honours_clean_only(self, monkeypatch, searches):
        import daily_pick

        pool = [candidate("filthy-x", "Filthy", explicit=True), candidate("ok", "Fine")]
        monkeypatch.setattr(daily_pick, "get_candidates", lambda profile, sf, context=None: [dict(c) for c in pool])
        monkeypatch.setattr(daily_pick, "score_candidate", lambda *a, **k: 0.5)
        monkeypatch.setattr(daily_pick, "load_config", lambda: {"clean_only": True})
        monkeypatch.setattr(daily_pick, "get_token_renewal_reminder", lambda: "")
        for _ in range(5):  # the pick is random among the top tier
            assert daily_pick.cmd_daily({}, "us")["track"]["id"] == "ok"


class TestReplacementsRespectExclusions:
    """A clean twin must not bring back a song the strategy or listener already ruled out."""

    def swap(self, searches, **kw):
        f = _common.user_filters({"clean_only": True}, storefront="us", **kw)
        return _common.swap_explicit_for_clean(candidate("loud-x", "Loud", explicit=True), f), f

    def test_a_disliked_clean_twin_is_not_used(self, searches):
        out, _ = self.swap(searches, profile={"disliked_song_ids": ["loud-c"]})
        assert out["id"] == "loud-x"  # stays explicit, so it is then dropped

    def test_the_other_listeners_dislikes_count_in_a_blend(self, searches):
        out, _ = self.swap(searches, profile={}, profile_b={"disliked_song_ids": ["loud-c"]})
        assert out["id"] == "loud-x"

    def test_a_library_song_is_blocked_unless_the_run_allows_the_library(self, searches):
        profile = {"library_song_ids": ["loud-c"]}
        assert self.swap(searches, profile=profile)[0]["id"] == "loud-x"
        assert self.swap(searches, profile=profile, include_library=True)[0]["id"] == "loud-c"

    def test_a_recently_used_twin_is_not_used(self, searches):
        out, _ = self.swap(searches, recent_track_ids={"loud-c"})
        assert out["id"] == "loud-x"

    def test_a_strategy_can_block_its_own_ids(self, searches):
        f = _common.user_filters({"clean_only": True}, storefront="us")
        f["blocked_ids"].add("loud-c")  # e.g. the seed song, or a track already in the playlist
        assert _common.swap_explicit_for_clean(candidate("loud-x", "Loud", explicit=True), f)["id"] == "loud-x"


class TestTwinsBecomeOneEntry:
    def test_an_explicit_song_and_its_clean_twin_do_not_fill_two_slots(self, searches):
        cands = [candidate("loud-x", "Loud", explicit=True), candidate("loud-c", "Loud")]
        out = _common.apply_user_filters(cands, filters())
        assert [c["id"] for c in out] == ["loud-c"]

    def test_two_explicit_entries_for_one_song_become_one(self, searches):
        cands = [candidate("loud-x", "Loud", explicit=True), candidate("loud-x2", "Loud", explicit=True)]
        assert [c["id"] for c in _common.apply_user_filters(cands, filters())] == ["loud-c"]

    def test_outside_clean_mode_nothing_is_deduplicated(self):
        cands = [candidate("a", "X"), candidate("a", "X")]
        assert len(_common.apply_user_filters(cands, _common.user_filters({}))) == 2
