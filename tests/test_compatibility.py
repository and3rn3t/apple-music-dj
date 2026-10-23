"""Tests for compatibility.py — genre similarity and profile comparison."""

import json
import sys

import pytest

from compatibility import (
    artist_compatibility,
    genre_overlap_score,
    genre_similarity,
    get_artist_genre_profile,
    main,
    profile_compatibility,
    resolve_artist,
)


# ── genre_similarity ─────────────────────────────────────────────

class TestGenreSimilarity:
    def test_exact_match(self):
        assert genre_similarity("Rock", "Rock") == 1.0

    def test_case_insensitive(self):
        assert genre_similarity("rock", "ROCK") == 1.0

    def test_same_family(self):
        assert genre_similarity("Rock", "Alternative") == 0.5

    def test_cross_family(self):
        assert genre_similarity("Rock", "Jazz") == 0.0

    def test_unknown_genres(self):
        assert genre_similarity("Zydeco", "Throat Singing") == 0.0

    def test_same_family_electronic(self):
        assert genre_similarity("Electronic", "Dance") == 0.5

    def test_hip_hop_and_rnb(self):
        assert genre_similarity("Hip-Hop/Rap", "R&B/Soul") == 0.5

    def test_pop_family(self):
        assert genre_similarity("Pop", "K-Pop") == 0.5


# ── genre_overlap_score ──────────────────────────────────────────

class TestGenreOverlapScore:
    def test_identical_distributions(self):
        genres = [{"genre": "Rock", "weight": 0.5}, {"genre": "Pop", "weight": 0.5}]
        score = genre_overlap_score(genres, genres)
        assert score > 0.5

    def test_completely_disjoint(self):
        a = [{"genre": "Classical", "weight": 1.0}]
        b = [{"genre": "Hip-Hop/Rap", "weight": 1.0}]
        score = genre_overlap_score(a, b)
        assert score == 0.0

    def test_partial_overlap(self):
        a = [{"genre": "Rock", "weight": 0.5}, {"genre": "Jazz", "weight": 0.5}]
        b = [{"genre": "Rock", "weight": 0.5}, {"genre": "Classical", "weight": 0.5}]
        score = genre_overlap_score(a, b)
        assert 0.0 < score < 1.0

    def test_empty_a_returns_zero(self):
        assert genre_overlap_score([], [{"genre": "Rock", "weight": 1.0}]) == 0.0

    def test_empty_b_returns_zero(self):
        assert genre_overlap_score([{"genre": "Rock", "weight": 1.0}], []) == 0.0

    def test_adjacent_genres_get_partial_credit(self):
        a = [{"genre": "Rock", "weight": 1.0}]
        b = [{"genre": "Alternative", "weight": 1.0}]
        score = genre_overlap_score(a, b)
        assert score > 0.0  # adjacent, not zero
        # With equal max weights and the 2x multiplier, adjacent genres can reach 1.0
        assert score <= 1.0


# ── get_artist_genre_profile ─────────────────────────────────────

class TestGetArtistGenreProfile:
    def test_equal_weights(self):
        artist = {"attributes": {"genreNames": ["Rock", "Alternative"]}}
        profile = get_artist_genre_profile(artist)
        assert len(profile) == 2
        assert all(g["weight"] == 0.5 for g in profile)

    def test_filters_music_tag(self):
        artist = {"attributes": {"genreNames": ["Pop", "Music"]}}
        profile = get_artist_genre_profile(artist)
        assert len(profile) == 1
        assert profile[0]["genre"] == "Pop"

    def test_no_genres(self):
        artist = {"attributes": {"genreNames": []}}
        assert get_artist_genre_profile(artist) == []

    def test_missing_attributes(self):
        assert get_artist_genre_profile({}) == []


# ── profile_compatibility ────────────────────────────────────────

class TestProfileCompatibility:
    def test_identical_profiles(self, sample_profile):
        result = profile_compatibility(sample_profile, sample_profile)
        assert result["compatibility_pct"] >= 70  # identical profiles score high
        assert "verdict" in result

    def test_empty_profiles(self, empty_profile):
        result = profile_compatibility(empty_profile, empty_profile)
        assert isinstance(result["compatibility_pct"], int)
        assert 0 <= result["compatibility_pct"] <= 100

    def test_different_profiles(self):
        a = {
            "top_artists": [{"name": "Radiohead"}],
            "genre_distribution": [{"genre": "Alternative", "weight": 1.0}],
            "era_distribution": [{"decade": "2000s"}],
            "energy_profile": "balanced",
        }
        b = {
            "top_artists": [{"name": "Beyoncé"}],
            "genre_distribution": [{"genre": "Classical", "weight": 1.0}],
            "era_distribution": [{"decade": "1800s"}],
            "energy_profile": "high-energy",
        }
        result = profile_compatibility(a, b)
        assert result["compatibility_pct"] < 50

    def test_shared_artists_detected(self, sample_profile):
        other = {
            "top_artists": [{"name": "Radiohead"}, {"name": "Björk"}],
            "genre_distribution": [{"genre": "Electronic", "weight": 1.0}],
            "era_distribution": [{"decade": "2000s"}],
            "energy_profile": "balanced",
        }
        result = profile_compatibility(sample_profile, other)
        assert "radiohead" in result["shared_artists"]

    def test_energy_mismatch_penalty(self):
        base = {
            "top_artists": [{"name": "X"}],
            "genre_distribution": [{"genre": "Rock", "weight": 1.0}],
            "era_distribution": [{"decade": "2010s"}],
            "energy_profile": "high-energy",
        }
        same_energy = {**base}
        diff_energy = {**base, "energy_profile": "chill"}
        r1 = profile_compatibility(base, same_energy)
        r2 = profile_compatibility(base, diff_energy)
        assert r1["compatibility_pct"] >= r2["compatibility_pct"]
        assert r1["energy_match"] is True
        assert r2["energy_match"] is False

    def test_verdict_categories(self):
        """All verdict thresholds produce strings."""
        base = {
            "top_artists": [],
            "genre_distribution": [],
            "era_distribution": [],
            "energy_profile": "balanced",
        }
        result = profile_compatibility(base, base)
        assert isinstance(result["verdict"], str)
        assert len(result["verdict"]) > 0


# ── artist_compatibility ─────────────────────────────────────────

class TestArtistCompatibility:
    def test_existing_artist_in_library(self, monkeypatch, sample_profile):
        """An artist already in top_artists should score high."""
        mock_artist = {
            "id": "a1",
            "attributes": {"name": "Radiohead", "genreNames": ["Alternative", "Rock"]},
        }

        def mock_resolve(sf, query):
            return mock_artist

        monkeypatch.setattr("compatibility.resolve_artist", mock_resolve)
        result = artist_compatibility(sample_profile, "us", "Radiohead")
        assert result["compatibility_pct"] >= 85
        assert result["already_in_library"] is True
        assert "verdict" in result

    def test_compatible_new_artist(self, monkeypatch, sample_profile):
        mock_artist = {
            "id": "new1",
            "attributes": {"name": "Muse", "genreNames": ["Alternative", "Rock"]},
        }

        monkeypatch.setattr("compatibility.resolve_artist", lambda sf, q: mock_artist)
        result = artist_compatibility(sample_profile, "us", "Muse")
        assert result["compatibility_pct"] > 0
        assert result["already_in_library"] is False
        assert len(result["matching_genres"]) > 0

    def test_unknown_artist_returns_error(self, monkeypatch, sample_profile):
        monkeypatch.setattr("compatibility.resolve_artist", lambda sf, q: None)
        result = artist_compatibility(sample_profile, "us", "Nobody")
        assert "error" in result

    def test_distant_artist_low_score(self, monkeypatch, sample_profile):
        mock_artist = {
            "id": "far1",
            "attributes": {"name": "Polka King", "genreNames": ["Polka", "Accordion"]},
        }

        monkeypatch.setattr("compatibility.resolve_artist", lambda sf, q: mock_artist)
        result = artist_compatibility(sample_profile, "us", "Polka King")
        assert result["compatibility_pct"] < 50


# ── resolve_artist ───────────────────────────────────────────────

class TestResolveArtist:
    def test_not_found(self, monkeypatch):
        monkeypatch.setattr("_common.search_artist", lambda sf, q: None)
        assert resolve_artist("us", "Nobody") is None

    def test_prefers_full_detail(self, monkeypatch):
        monkeypatch.setattr("_common.search_artist", lambda sf, q: {"id": "a1", "attributes": {"name": "Radiohead"}})
        detail = {"id": "a1", "attributes": {"name": "Radiohead", "genreNames": ["Alternative"]}}
        calls = []

        def fake_api(cmd, *args):
            calls.append((cmd, *args))
            return {"data": [detail]}

        monkeypatch.setattr("compatibility.call_api", fake_api)
        assert resolve_artist("us", "Radiohead") == detail
        assert calls == [("artist-detail", "us", "a1")]

    def test_falls_back_to_search_hit_without_detail(self, monkeypatch):
        hit = {"id": "a1", "attributes": {"name": "Radiohead"}}
        monkeypatch.setattr("_common.search_artist", lambda sf, q: hit)
        monkeypatch.setattr("compatibility.call_api", lambda *a: None)
        assert resolve_artist("us", "Radiohead") == hit


# ── verdict bands ────────────────────────────────────────────────

NEW_ARTIST = {"id": "x1", "attributes": {"name": "Someone New", "genreNames": ["Alternative"]}}


@pytest.mark.parametrize("g_score, verdict_start", [
    (1.0, "Deeply compatible"),   # 0.8 * 1.0 + 0.1 = 90%
    (0.8, "Strong overlap"),      # 74%
    (0.5, "Moderate match"),      # 50%
    (0.3, "Stretch pick"),        # 34%
    (0.0, "Wild card"),           # 10%
])
def test_artist_verdict_bands(monkeypatch, sample_profile, g_score, verdict_start):
    monkeypatch.setattr("compatibility.resolve_artist", lambda sf, q: NEW_ARTIST)
    monkeypatch.setattr("compatibility.genre_overlap_score", lambda a, b: g_score)
    result = artist_compatibility(sample_profile, "us", "Someone New")
    assert result["verdict"].startswith(verdict_start)


@pytest.mark.parametrize("g_score, verdict_start", [
    # No shared artists or eras; energy matches (both unset), so the score is 0.4 * g + 0.15.
    (1.0, "Some common ground"),  # 55%
    (0.5, "Different worlds"),    # 35%
    (0.0, "Opposites"),           # 15%
])
def test_profile_verdict_bands(monkeypatch, g_score, verdict_start):
    monkeypatch.setattr("compatibility.genre_overlap_score", lambda a, b: g_score)
    result = profile_compatibility({}, {})
    assert result["verdict"].startswith(verdict_start)


# ── CLI ──────────────────────────────────────────────────────────

class TestMain:
    def _run(self, monkeypatch, capsys, *argv):
        monkeypatch.setattr(sys, "argv", ["compatibility.py", *argv])
        main()
        return json.loads(capsys.readouterr().out)

    def test_profile_mode(self, monkeypatch, capsys, tmp_path, sample_profile):
        a = tmp_path / "a.json"
        a.write_text(json.dumps(sample_profile))
        out = self._run(monkeypatch, capsys, "profile", str(a), str(a))
        assert out == profile_compatibility(sample_profile, sample_profile)
        assert "radiohead" in out["shared_artists"]

    def test_artist_mode_joins_multiword_names(self, monkeypatch, capsys, tmp_path, sample_profile):
        p = tmp_path / "p.json"
        p.write_text(json.dumps(sample_profile))
        seen = []

        def fake_resolve(sf, query):
            seen.append((sf, query))
            return NEW_ARTIST

        monkeypatch.setattr("compatibility.resolve_artist", fake_resolve)
        out = self._run(monkeypatch, capsys, "artist", str(p), "us", "Someone", "New")
        assert seen == [("us", "Someone New")]
        assert out["artist"] == "Someone New"

    def test_mode_is_required(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["compatibility.py"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
