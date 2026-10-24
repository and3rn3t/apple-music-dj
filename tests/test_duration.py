"""strategies/duration.py: trimming an ordered playlist to a running time."""

import pytest

from strategies.duration import (
    AVERAGE_TRACK_MS,
    TOLERANCE_MS,
    fit_to_duration,
    pool_size_for,
    total_ms,
)

MIN = 60_000


def tracks(*minutes: float) -> list[dict]:
    return [{"id": f"t{i}", "duration_ms": round(m * MIN)} for i, m in enumerate(minutes)]


def ids(items: list[dict]) -> list[str]:
    return [t["id"] for t in items]


def test_a_playlist_already_on_target_is_untouched():
    items = tracks(3, 4, 3, 4)
    assert fit_to_duration(items, 14 * MIN) == items


def test_a_short_playlist_is_returned_as_is():
    items = tracks(3, 3)
    assert fit_to_duration(items, 60 * MIN) == items


def test_trims_down_to_within_the_tolerance():
    items = tracks(*[3 + (i % 5) * 0.4 for i in range(14)])  # varied lengths, about 48 min
    out = fit_to_duration(items, 30 * MIN)
    assert abs(total_ms(out) - 30 * MIN) <= TOLERANCE_MS


def test_lands_when_one_removal_at_a_time_gets_stuck():
    items = tracks(3.2, 3.0, 3.0, 3.0, 4.4, 3.0, 3.0, 3.2)  # 25.8 min -> 22: needs 3.8 off
    out = fit_to_duration(items, 22 * MIN)
    assert abs(total_ms(out) - 22 * MIN) <= TOLERANCE_MS
    assert ids(out) == [i for i in ids(items) if i in set(ids(out))]


def test_never_reorders():
    items = tracks(*[3 + (i % 4) * 0.5 for i in range(20)])
    out = fit_to_duration(items, 45 * MIN)
    assert ids(out) == [i for i in ids(items) if i in set(ids(out))]


def test_keeps_the_opener_and_closer():
    items = tracks(*[3.5] * 12)
    out = fit_to_duration(items, 21 * MIN)
    assert out[0] is items[0] and out[-1] is items[-1]


def test_drops_are_spread_out_not_clumped():
    items = tracks(*[3] * 20)  # 60 min, drop 4 tracks to reach 48
    out = fit_to_duration(items, 48 * MIN)
    dropped = sorted(int(i[1:]) for i in set(ids(items)) - set(ids(out)))
    assert len(dropped) == 4 and all(b - a >= 3 for a, b in zip(dropped, dropped[1:], strict=False))


def test_picks_the_track_that_lands_closest():
    # drop exactly the 5-minute track to reach 12 min, not a 3
    items = tracks(3, 5, 3, 3, 3)
    assert ids(fit_to_duration(items, 12 * MIN, tolerance_ms=0)) == ["t0", "t2", "t3", "t4"]


def test_stops_rather_than_overshoot_further():
    items = tracks(10, 10, 10)
    out = fit_to_duration(items, 5 * MIN)  # nothing fits; keep what is closest rather than empty
    assert out and len(out) >= 1


def test_a_missing_duration_counts_as_an_average_track():
    items = [{"id": "a"}, {"id": "b", "duration_ms": None}, {"id": "c", "duration_ms": 0}]
    assert total_ms(items) == 3 * AVERAGE_TRACK_MS


@pytest.mark.parametrize("minutes", [10, 45, 120])
def test_the_pool_has_room_to_trim(minutes):
    assert pool_size_for(minutes) * AVERAGE_TRACK_MS >= minutes * MIN * 1.25
