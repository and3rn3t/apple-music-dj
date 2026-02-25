"""Tests for daily_pick.py — scoring, seeding, and time context."""

import random
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from daily_pick import daily_seed, get_time_context, score_candidate


# ── daily_seed ───────────────────────────────────────────────────

class TestDailySeed:
    def test_returns_int(self):
        assert isinstance(daily_seed(), int)

    def test_deterministic_same_day(self):
        assert daily_seed() == daily_seed()

    def test_different_days_differ(self):
        with patch("daily_pick.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            seed_a = daily_seed()

        with patch("daily_pick.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 2, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            seed_b = daily_seed()

        assert seed_a != seed_b


# ── get_time_context ─────────────────────────────────────────────

class TestGetTimeContext:
    @pytest.mark.parametrize("hour,expected_period", [
        (5, "morning"),
        (8, "morning"),
        (9, "mid-morning"),
        (11, "mid-morning"),
        (12, "midday"),
        (13, "midday"),
        (14, "afternoon"),
        (16, "afternoon"),
        (17, "evening"),
        (19, "evening"),
        (20, "night"),
        (22, "night"),
        (23, "late-night"),
        (0, "late-night"),
        (3, "late-night"),
        (4, "late-night"),
    ])
    def test_period_boundaries(self, hour, expected_period):
        with patch("daily_pick.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, hour, 0, 0)
            ctx = get_time_context()
            assert ctx["period"] == expected_period

    def test_context_has_required_keys(self):
        ctx = get_time_context()
        assert "period" in ctx
        assert "energy" in ctx
        assert "mood" in ctx
        assert "genres_boost" in ctx
        assert isinstance(ctx["genres_boost"], list)


# ── score_candidate ──────────────────────────────────────────────

class TestScoreCandidate:
    """These tests would have caught the rng keyword argument bug."""

    @pytest.fixture
    def base_candidate(self):
        return {
            "id": "t1",
            "name": "Test Song",
            "artist": "Test Artist",
            "genre": ["Rock"],
            "source": "charts",
        }

    @pytest.fixture
    def deep_cut(self):
        return {
            "id": "t2",
            "name": "Deep Cut",
            "artist": "Test Artist",
            "genre": ["Rock"],
            "source": "deep_cut",
        }

    def test_base_score(self, base_candidate, sample_profile):
        rng = random.Random(42)
        score = score_candidate(base_candidate, sample_profile, rng=rng)
        assert 0.5 <= score <= 0.8  # base 0.5 + random(0, 0.3)

    def test_deep_cut_bonus(self, deep_cut, sample_profile):
        rng = random.Random(42)
        score = score_candidate(deep_cut, sample_profile, rng=rng)
        assert score >= 0.7  # base 0.5 + 0.2 deep_cut + random

    def test_deep_cut_scores_higher(self, base_candidate, deep_cut, sample_profile):
        """Deep cuts should consistently score higher (same RNG seed)."""
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        normal = score_candidate(base_candidate, sample_profile, rng=rng1)
        deep = score_candidate(deep_cut, sample_profile, rng=rng2)
        assert deep > normal

    def test_genre_context_boost(self, base_candidate, sample_profile):
        context = {"genres_boost": ["Rock"]}
        rng = random.Random(42)
        score_with = score_candidate(base_candidate, sample_profile, context, rng=rng)

        rng = random.Random(42)  # reset
        score_without = score_candidate(base_candidate, sample_profile, rng=rng)

        assert score_with > score_without

    def test_genre_boost_case_insensitive(self, sample_profile):
        candidate = {"genre": ["rock"], "source": "charts"}
        context = {"genres_boost": ["Rock"]}
        rng = random.Random(42)
        score = score_candidate(candidate, sample_profile, context, rng=rng)
        assert score > 0.5 + 0.3  # base + genre boost (at minimum)

    def test_deterministic_with_seeded_rng(self, base_candidate, sample_profile):
        rng1 = random.Random(99)
        rng2 = random.Random(99)
        s1 = score_candidate(base_candidate, sample_profile, rng=rng1)
        s2 = score_candidate(base_candidate, sample_profile, rng=rng2)
        assert s1 == s2

    def test_no_context(self, base_candidate, sample_profile):
        """Passing context=None should work without error."""
        score = score_candidate(base_candidate, sample_profile, None)
        assert isinstance(score, float)

    def test_rng_keyword_argument(self, base_candidate, sample_profile):
        """Regression: score_candidate must accept rng as keyword arg."""
        rng = random.Random(42)
        # This call would have crashed before the fix
        score = score_candidate(base_candidate, sample_profile, context=None, rng=rng)
        assert isinstance(score, float)
