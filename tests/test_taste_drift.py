"""Tests for taste_drift — snapshot comparison and reporting."""

import json
from argparse import Namespace
from datetime import date

import pytest

import taste_drift as td
from _common import list_snapshots, save_snapshot


def _profile(genres, artists, eras=None, variety=0.5, mainstream=0.5, energy="balanced", day="2026-01-01"):
    return {
        "top_artists": [{"name": n, "play_weight": 0.1} for n in artists],
        "genre_distribution": [{"genre": g, "weight": w} for g, w in genres],
        "era_distribution": [{"decade": d, "weight": w} for d, w in (eras or [("2000s", 1.0)])],
        "variety_score": variety,
        "mainstream_score": mainstream,
        "energy_profile": energy,
        "generated_at": f"{day}T12:00:00+00:00",
    }


def _args(**kw):
    base = dict(profile=None, since="90d", from_date=None)
    base.update(kw)
    return Namespace(**base)


class TestParsing:
    @pytest.mark.parametrize("raw,days", [("90d", 90), ("12w", 84), ("6m", 180), ("1y", 365), ("45", 45)])
    def test_parse_since(self, raw, days):
        assert td.parse_since(raw) == days

    @pytest.mark.parametrize("raw", ["", "soon", "-3d", "3x"])
    def test_parse_since_rejects(self, raw):
        with pytest.raises(ValueError):
            td.parse_since(raw)

    def test_parse_date(self):
        assert td.parse_date("2026-03-02") == date(2026, 3, 2)
        with pytest.raises(ValueError):
            td.parse_date("03/02/2026")


class TestComputeDrift:
    def test_genre_risers_and_fallers(self):
        old = _profile([("Rock", 0.5), ("Pop", 0.3), ("Jazz", 0.2)], ["A"])
        new = _profile([("Electronic", 0.4), ("Rock", 0.3), ("Pop", 0.3)], ["A"])
        d = td.compute_drift(old, new)
        assert d["genres"]["risers"][0] == {"genre": "Electronic", "delta": 0.4}
        assert {f["genre"] for f in d["genres"]["fallers"]} == {"Rock", "Jazz"}

    def test_tiny_moves_ignored(self):
        old = _profile([("Rock", 0.50)], ["A"])
        new = _profile([("Rock", 0.505)], ["A"])
        d = td.compute_drift(old, new)
        assert d["genres"]["risers"] == [] and d["genres"]["fallers"] == []

    def test_artists_new_and_dropped_case_insensitive(self):
        old = _profile([("Rock", 1)], ["Radiohead", "Queen"])
        new = _profile([("Rock", 1)], ["radiohead", "Muse"])
        d = td.compute_drift(old, new)
        assert d["artists"] == {"new": ["Muse"], "dropped": ["Queen"]}

    def test_era_shift_and_scores(self):
        old = _profile([("Rock", 1)], ["A"], eras=[("1990s", 0.7), ("2000s", 0.3)], variety=0.4)
        new = _profile([("Rock", 1)], ["A"], eras=[("1990s", 0.2), ("2010s", 0.8)], variety=0.7)
        d = td.compute_drift(old, new)
        assert d["eras"]["top_from"] == "1990s" and d["eras"]["top_to"] == "2010s"
        assert d["eras"]["biggest_move"]["decade"] == "2010s"
        assert d["scores"]["variety"] == {"from": 0.4, "to": 0.7, "delta": 0.3}

    def test_archetype_change_detected(self):
        old = _profile([("Rock", 1)], ["A"], variety=0.2, mainstream=0.5)
        new = _profile([(g, 0.1) for g in "ABCDEFG"], ["A"], variety=0.9, mainstream=0.1)
        d = td.compute_drift(old, new)
        assert d["archetype"]["changed"] is True
        assert d["archetype"]["to"] == "Deep Catalog Digger"
        assert "Deep Catalog Digger" in d["narrative"]

    def test_steady_taste_narrative(self):
        p = _profile([("Rock", 1)], ["A"])
        d = td.compute_drift(p, dict(p))
        assert d["narrative"] == "Your taste has been steady — no big moves."

    def test_narrative_mentions_movers(self):
        old = _profile([("Rock", 0.6), ("Pop", 0.4)], ["A"])
        new = _profile([("Rock", 0.3), ("Pop", 0.7)], ["A", "B", "C"])
        text = td.compute_drift(old, new)["narrative"]
        assert "toward Pop (+30%)" in text and "away from Rock (−30%)" in text
        assert "B and 1 more entered your top 20" in text


class TestPickBaseline:
    def _snaps(self, tmp_path, days):
        for d in days:
            (tmp_path / f"{d}.json").write_text("{}")
        return td.list_snapshots(tmp_path)

    def test_closest_to_target(self, tmp_path):
        snaps = self._snaps(tmp_path, ["2026-01-01", "2026-02-15", "2026-03-20"])
        pick = td.pick_baseline(snaps, date(2026, 4, 1), date(2026, 2, 1))
        assert pick[0] == "2026-02-15"

    def test_excludes_current_and_newer(self, tmp_path):
        snaps = self._snaps(tmp_path, ["2026-03-01", "2026-04-01"])
        assert td.pick_baseline(snaps, date(2026, 4, 1), date(2026, 4, 1))[0] == "2026-03-01"

    def test_none_when_no_older(self, tmp_path):
        snaps = self._snaps(tmp_path, ["2026-04-01"])
        assert td.pick_baseline(snaps, date(2026, 4, 1), date(2026, 1, 1)) is None


class TestSnapshotErrors:
    def test_corrupt_snapshot_is_a_clean_error(self, tmp_path):
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-04-01"), tmp_path)
        (tmp_path / "2026-01-01.json").write_text("{not json")
        with pytest.raises(ValueError, match="Can't read snapshot 2026-01-01.json"):
            td.run(_args(), tmp_path)

    def test_non_object_snapshot_rejected(self, tmp_path):
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-04-01"), tmp_path)
        (tmp_path / "2026-01-01.json").write_text("[1, 2]")
        with pytest.raises(ValueError, match="isn't a valid snapshot"):
            td.run(_args(), tmp_path)

    def test_unreadable_snapshot_is_a_clean_error(self, tmp_path):
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-04-01"), tmp_path)
        bad = tmp_path / "2026-01-01.json"
        bad.write_text("{}")
        bad.chmod(0)
        try:
            with pytest.raises(ValueError, match="Can't read snapshot"):
                td.run(_args(), tmp_path)
        finally:
            bad.chmod(0o600)

    def test_cli_reports_instead_of_tracebacks(self, tmp_path, monkeypatch, capsys):
        import sys
        monkeypatch.setattr("_common.SNAPSHOT_DIR", tmp_path)
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-04-01"), tmp_path)
        (tmp_path / "2026-01-01.json").write_text("{not json")
        monkeypatch.setattr(sys, "argv", ["taste_drift.py"])
        with pytest.raises(SystemExit) as e:
            td.main()
        assert e.value.code == 1 and "Can't read snapshot" in capsys.readouterr().err

    def test_stray_files_are_ignored(self, tmp_path):
        (tmp_path / "abcd-ef-gh.json").write_text("{}")
        assert list_snapshots(tmp_path) == []


class TestRun:
    def test_no_snapshots(self, tmp_path):
        with pytest.raises(ValueError, match="No snapshots yet"):
            td.run(_args(), tmp_path)

    def test_single_snapshot(self, tmp_path):
        save_snapshot(_profile([("Rock", 1)], ["A"], day="2026-04-01"), tmp_path)
        with pytest.raises(ValueError, match="at least two"):
            td.run(_args(), tmp_path)

    def test_newest_vs_baseline(self, tmp_path):
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-01-01"), tmp_path)
        save_snapshot(_profile([("Rock", 0.5), ("Jazz", 0.5)], ["A"], day="2026-04-01"), tmp_path)
        report = td.run(_args(), tmp_path)
        assert report["period"] == {"from": "2026-01-01", "to": "2026-04-01", "days": 90}
        assert report["genres"]["risers"][0]["genre"] == "Jazz"

    def test_profile_as_now_and_from_date(self, tmp_path):
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-01-01"), tmp_path)
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-03-01"), tmp_path)
        profile_file = tmp_path / "profile.json"
        profile_file.write_text(json.dumps(_profile([("Pop", 1.0)], ["B"], day="2026-04-01")))
        report = td.run(_args(profile=str(profile_file), from_date="2026-01-05"), tmp_path)
        assert report["period"]["from"] == "2026-01-01"
        assert report["artists"]["new"] == ["B"]

    def test_text_format(self, tmp_path):
        save_snapshot(_profile([("Rock", 1.0)], ["A"], day="2026-01-01"), tmp_path)
        save_snapshot(_profile([("Pop", 1.0)], ["B"], day="2026-04-01"), tmp_path)
        text = td.format_text(td.run(_args(), tmp_path))
        assert "2026-01-01 → 2026-04-01" in text
        assert "Rising:" in text and "Pop" in text
        assert "New top artists:" in text
