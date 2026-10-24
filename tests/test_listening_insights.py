"""Tests for listening_insights.py — timeline, streaks, year-review."""

import json
import sys
from unittest.mock import Mock

import pytest

from listening_insights import cmd_streaks, cmd_timeline, cmd_year_review, year_review_caption, main
from taste_card import generate_year_review_svg, generate_year_review_text


class TestMain:
    @pytest.fixture(autouse=True)
    def isolate_commands(self, monkeypatch):
        for command in ("timeline", "streaks", "year_review"):
            monkeypatch.setattr(
                f"listening_insights.cmd_{command}", Mock(side_effect=AssertionError("Unexpected command dispatch"))
            )

    @pytest.fixture
    def profile_path(self, tmp_path, sample_profile):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps(sample_profile), encoding="utf-8")
        return str(profile)

    @pytest.fixture(autouse=True)
    def fixed_year(self, monkeypatch):
        clock = Mock()
        clock.now.return_value.year = 2026
        monkeypatch.setattr("listening_insights.datetime", clock)

    @pytest.mark.parametrize("command", ["timeline", "streaks"])
    def test_dispatches_with_the_loaded_profile_and_prints_json(
        self, monkeypatch, capsys, profile_path, sample_profile, command
    ):
        result = {"command": command, "insights": ["Example insight"]}
        handler = Mock(return_value=result)
        monkeypatch.setattr(f"listening_insights.cmd_{command}", handler)
        monkeypatch.setattr(sys, "argv", ["listening_insights.py", command, profile_path])

        main()

        handler.assert_called_once_with(sample_profile)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == result and captured.err == ""

    @pytest.mark.parametrize(("flags", "year"), [([], 2025), (["--year", "2015"], 2015), (["--year", "2026"], 2026)])
    def test_year_review_accepts_the_default_and_both_range_boundaries(
        self, monkeypatch, capsys, profile_path, sample_profile, flags, year
    ):
        result = {"year": year, "insights": []}
        handler = Mock(return_value=result)
        monkeypatch.setattr("listening_insights.cmd_year_review", handler)
        monkeypatch.setattr(sys, "argv", ["listening_insights.py", "year-review", profile_path, *flags])

        main()

        handler.assert_called_once_with(sample_profile, year)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == result and captured.err == ""

    @pytest.mark.parametrize("year", [2014, 2027])
    def test_out_of_range_year_exits_without_running_the_review(
        self, monkeypatch, capsys, profile_path, year
    ):
        handler = Mock()
        monkeypatch.setattr("listening_insights.cmd_year_review", handler)
        monkeypatch.setattr(sys, "argv", ["listening_insights.py", "year-review", profile_path, "--year", str(year)])

        with pytest.raises(SystemExit) as error:
            main()

        assert error.value.code == 1
        handler.assert_not_called()
        captured = capsys.readouterr()
        assert captured.out == "" and "Year must be between 2015 and 2026" in captured.err

    @pytest.mark.parametrize("argv", [[], ["unknown"], ["timeline"], ["year-review", "unused", "--year", "invalid"]])
    def test_invalid_arguments_exit_before_loading_a_profile(self, monkeypatch, capsys, argv):
        loader = Mock()
        monkeypatch.setattr("listening_insights.load_profile", loader)
        monkeypatch.setattr(sys, "argv", ["listening_insights.py", *argv])

        with pytest.raises(SystemExit) as error:
            main()

        assert error.value.code == 2
        loader.assert_not_called()
        captured = capsys.readouterr()
        assert captured.out == "" and "usage:" in captured.err


# ── cmd_timeline ─────────────────────────────────────────────────

class TestCmdTimeline:
    def test_returns_expected_keys(self, monkeypatch, sample_profile):
        # Mock call_api to return year-specific replay data
        def mock_api(command, *args, **kw):
            year = args[0] if args else "2024"
            return {
                "data": [{
                    "attributes": {
                        "year": int(year),
                        "topArtists": [{"name": "Radiohead"}],
                        "topGenres": [{"name": "Alternative"}],
                        "listenTimeInMinutes": 30000,
                        "topSongs": [{"name": "Everything In Its Right Place"}],
                    }
                }]
            }

        monkeypatch.setattr("listening_insights.call_api", mock_api)
        result = cmd_timeline(sample_profile)

        assert "timeline" in result
        assert "narrative" in result
        assert "current_top_genres" in result
        assert "current_top_artists" in result
        assert "replay_available" in result
        assert "years_covered" in result

    def test_timeline_entries_have_year(self, monkeypatch, sample_profile):
        def mock_api(command, *args, **kw):
            return {
                "data": [{
                    "attributes": {
                        "year": 2023,
                        "topArtists": [{"name": "Radiohead"}],
                        "topGenres": [{"name": "Rock"}],
                        "listenTimeInMinutes": 5000,
                    }
                }]
            }

        monkeypatch.setattr("listening_insights.call_api", mock_api)
        result = cmd_timeline(sample_profile)
        for entry in result["timeline"]:
            assert "year" in entry

    def test_narrative_contains_year(self, monkeypatch, sample_profile):
        def mock_api(command, *args, **kw):
            return {
                "data": [{
                    "attributes": {
                        "year": 2023,
                        "topArtists": [{"name": "Radiohead"}],
                        "topGenres": [{"name": "Rock"}],
                        "listenTimeInMinutes": 12000,
                    }
                }]
            }

        monkeypatch.setattr("listening_insights.call_api", mock_api)
        result = cmd_timeline(sample_profile)
        assert any("2023" in n for n in result["narrative"])

    def test_empty_replay(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_timeline(sample_profile)
        assert result["years_covered"] == 0
        assert result["timeline"] == []

    def test_current_profile_genres_included(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_timeline(sample_profile)
        assert "Alternative" in result["current_top_genres"]

    def test_current_profile_artists_included(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_timeline(sample_profile)
        assert "Radiohead" in result["current_top_artists"]


# ── cmd_streaks ──────────────────────────────────────────────────

class TestCmdStreaks:
    def test_returns_expected_keys(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_streaks(sample_profile)
        assert "milestones" in result
        assert "insights" in result
        assert "listening_velocity" in result
        assert "data_summary" in result

    def test_artist_loyalty_insight(self, monkeypatch):
        profile = {
            "top_artists": [{"name": "Radiohead", "count": 25}],
            "genre_distribution": [{"genre": "Alternative", "weight": 0.3}],
            "listening_velocity": "moderate",
            "data_summary": {"recent_tracks": 50, "library_songs": 200},
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_streaks(profile)
        types = [i["type"] for i in result["insights"]]
        assert "artist_loyalty" in types

    def test_genre_dominance_insight(self, monkeypatch):
        profile = {
            "top_artists": [{"name": "X", "count": 5}],
            "genre_distribution": [{"genre": "Rock", "weight": 0.6}],
            "listening_velocity": "moderate",
            "data_summary": {"recent_tracks": 50, "library_songs": 100},
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_streaks(profile)
        types = [i["type"] for i in result["insights"]]
        assert "genre_dominance" in types

    def test_no_insights_for_small_data(self, monkeypatch, empty_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_streaks(empty_profile)
        assert result["insights"] == []

    def test_milestones_from_api(self, monkeypatch, sample_profile):
        mock_milestones = {
            "data": [{
                "attributes": {
                    "kind": "listenCount",
                    "value": 10000,
                    "description": "You listened to 10,000 songs!",
                }
            }]
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: mock_milestones)
        result = cmd_streaks(sample_profile)
        assert len(result["milestones"]) == 1
        assert result["milestones"][0]["type"] == "listenCount"

    def test_library_size_insight(self, monkeypatch):
        profile = {
            "top_artists": [{"name": "X", "count": 2}],
            "genre_distribution": [{"genre": "Rock", "weight": 0.3}],
            "listening_velocity": "moderate",
            "data_summary": {"recent_tracks": 10, "library_songs": 600},
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_streaks(profile)
        types = [i["type"] for i in result["insights"]]
        assert "library_size" in types

    def test_active_rater_insight(self, monkeypatch):
        profile = {
            "top_artists": [{"name": "X", "count": 2}],
            "genre_distribution": [{"genre": "Rock", "weight": 0.3}],
            "listening_velocity": "moderate",
            "data_summary": {"recent_tracks": 10, "library_songs": 50, "loved_count": 75},
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_streaks(profile)
        types = [i["type"] for i in result["insights"]]
        assert "active_rater" in types


# ── cmd_year_review ──────────────────────────────────────────────

class TestCmdYearReview:
    def test_returns_expected_keys(self, monkeypatch, sample_profile):
        mock_summary = {
            "data": [{
                "attributes": {
                    "listenTimeInMinutes": 30000,
                    "topArtists": [{"name": "Radiohead"}, {"name": "The Weeknd"}],
                    "topSongs": [{"name": "Idioteque", "artistName": "Radiohead"}],
                    "topAlbums": [{"name": "Kid A"}],
                    "topGenres": [{"name": "Alternative"}, {"name": "Electronic"}],
                }
            }]
        }
        monkeypatch.setattr("listening_insights.call_api",
                            lambda cmd, *a, **kw: mock_summary)
        result = cmd_year_review(sample_profile, 2024)
        assert result["year"] == 2024
        assert "replay_data" in result
        assert "insights" in result
        assert "obscurity_score" in result
        assert "variety_score" in result

    def test_listen_time_insight(self, monkeypatch, sample_profile):
        mock_summary = {
            "data": [{
                "attributes": {
                    "listenTimeInMinutes": 60000,
                    "topArtists": [{"name": "Radiohead"}],
                    "topSongs": [],
                    "topAlbums": [],
                    "topGenres": [{"name": "Alternative"}],
                }
            }]
        }
        monkeypatch.setattr("listening_insights.call_api",
                            lambda cmd, *a, **kw: mock_summary)
        result = cmd_year_review(sample_profile, 2024)
        assert any("hours" in insight for insight in result["insights"])

    def test_obscurity_score_range(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_year_review(sample_profile, 2024)
        assert 0 <= result["obscurity_score"] <= 100

    def test_no_replay_data(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_year_review(sample_profile, 2024)
        assert result["replay_available"] is False
        assert result["replay_data"] == {}

    def test_milestones_extracted(self, monkeypatch, sample_profile):
        call_count = {"n": 0}

        def mock_api(cmd, *args, **kw):
            call_count["n"] += 1
            if cmd == "replay-milestones":
                return {
                    "data": [{
                        "attributes": {"description": "You hit 1000 songs!"}
                    }]
                }
            return None

        monkeypatch.setattr("listening_insights.call_api", mock_api)
        result = cmd_year_review(sample_profile, 2024)
        assert "You hit 1000 songs!" in result["milestones"]

    def test_high_variety_insight(self, monkeypatch):
        profile = {
            "genre_distribution": [],
            "top_artists": [],
            "variety_score": 0.8,
            "mainstream_score": 0.3,
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_year_review(profile, 2024)
        assert any("adventurous" in i for i in result["insights"])

    def test_low_variety_insight(self, monkeypatch):
        profile = {
            "genre_distribution": [],
            "top_artists": [],
            "variety_score": 0.2,
            "mainstream_score": 0.3,
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_year_review(profile, 2024)
        assert any("deep" in i.lower() for i in result["insights"])

    def test_mainstream_insight(self, monkeypatch):
        profile = {
            "genre_distribution": [],
            "top_artists": [],
            "variety_score": 0.5,
            "mainstream_score": 0.7,
        }
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_year_review(profile, 2024)
        assert any("mainstream" in i for i in result["insights"])


# ── year review → taste card ─────────────────────────────────────

REPLAY_2025 = {
    "replay-summary": {"data": [{"attributes": {
        "listenTimeInMinutes": 30000,
        "topArtists": [{"name": "Radiohead"}],
        "topSongs": [{"name": "Reckoner", "artistName": "Radiohead"}],
        "topGenres": [{"name": "Alternative"}],
    }}]},
    "replay-milestones": {"data": [{"attributes": {"description": "10,000 minutes"}}]},
}


class TestYearReviewCard:
    """`taste_card.py --mode year-review` reads cmd_year_review's output as-is."""

    def test_card_fields_from_replay(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda cmd, *a, **kw: REPLAY_2025.get(cmd))
        result = cmd_year_review(sample_profile, 2025)
        assert result["total_minutes"] == 30000
        assert result["top_artist"] == "Radiohead"
        assert result["top_genre"] == "Alternative"
        assert result["top_songs"] == [{"name": "Reckoner", "artist": "Radiohead"}]

    def test_round_trip_into_card(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda cmd, *a, **kw: REPLAY_2025.get(cmd))
        result = cmd_year_review(sample_profile, 2025)
        text = generate_year_review_text(result)
        assert "Hours Listened:  500" in text
        assert "#1 Artist:       Radiohead" in text
        assert "#1 Genre:        Alternative" in text
        assert "Reckoner — Radiohead" in text
        assert "(now)" not in text
        svg = generate_year_review_svg(result)
        assert ">500<" in svg and "Reckoner" in svg

    def test_without_replay_falls_back_to_profile_and_says_so(self, monkeypatch, sample_profile):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_year_review(sample_profile, 2025)
        assert result["top_artist"] == "Radiohead"
        assert result["top_genre"] == "Alternative"
        assert result["total_minutes"] is None
        # The disclosure has to survive the SVG's 50-character cut, and the card labels the stats.
        assert "Replay" in result["insights"][0] and len(result["insights"][0]) <= 50
        text = generate_year_review_text(result)
        assert "Hours Listened:  —" in text
        assert "#1 Artist (now): Radiohead" in text
        svg = generate_year_review_svg(result)
        assert "#1 Artist (now)" in svg and result["insights"][0] in svg
        # The caption is shared on its own, so it must not claim today's taste for that year.
        assert result["caption"] == "My Apple Music taste right now: #1 artist Radiohead, mostly Alternative. 🎧"
        assert "None" not in text and "None" not in generate_year_review_svg(result)

    def test_empty_profile_without_replay(self, monkeypatch):
        monkeypatch.setattr("listening_insights.call_api", lambda *a, **kw: None)
        result = cmd_year_review({}, 2025)
        assert result["top_artist"] is None and result["top_genre"] is None
        assert "Unknown" in generate_year_review_text(result)
        assert result["caption"] == "My 2025 on Apple Music: a year of music. 🎧"


class TestYearReviewCaption:
    def test_full(self):
        assert (year_review_caption(2025, 30000, "Radiohead", "Alternative")
                == "My 2025 on Apple Music: 500 hours of music, #1 artist Radiohead, mostly Alternative. 🎧")

    def test_leaves_out_unknowns(self):
        assert year_review_caption(2025, None, "Radiohead", None) == "My 2025 on Apple Music: #1 artist Radiohead. 🎧"
