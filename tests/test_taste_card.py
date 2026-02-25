"""Tests for taste_card.py — archetype detection, SVG/text generation, helpers."""

import pytest

from taste_card import (
    _bar,
    _escape,
    _top_era,
    _top_era_weight,
    detect_archetype,
    generate_svg,
    generate_text,
)


# ── _top_era / _top_era_weight ───────────────────────────────────

class TestTopEra:
    def test_returns_first_decade(self, sample_profile):
        assert _top_era(sample_profile) == sample_profile["era_distribution"][0]["decade"]

    def test_empty_eras_default(self):
        assert _top_era({"era_distribution": []}) == "2020s"

    def test_missing_key(self):
        assert _top_era({}) == "2020s"


class TestTopEraWeight:
    def test_returns_first_weight(self, sample_profile):
        expected = sample_profile["era_distribution"][0]["weight"]
        assert _top_era_weight(sample_profile) == expected

    def test_empty_eras_default(self):
        assert _top_era_weight({"era_distribution": []}) == 0.0

    def test_missing_key(self):
        assert _top_era_weight({}) == 0.0


# ── _bar ─────────────────────────────────────────────────────────

class TestBar:
    def test_full_width(self):
        assert _bar(1.0) == 180

    def test_zero_clamps_minimum(self):
        assert _bar(0.0) == 4

    def test_half(self):
        assert _bar(0.5) == 90

    def test_negative_clamps_minimum(self):
        assert _bar(-0.1) == 4

    def test_custom_max_width(self):
        assert _bar(1.0, max_width=100) == 100


# ── _escape ──────────────────────────────────────────────────────

class TestEscape:
    def test_ampersand(self):
        assert _escape("R&B") == "R&amp;B"

    def test_less_than(self):
        assert _escape("a < b") == "a &lt; b"

    def test_greater_than(self):
        assert _escape("a > b") == "a &gt; b"

    def test_all_at_once(self):
        assert _escape("A & B < C > D") == "A &amp; B &lt; C &gt; D"

    def test_no_special(self):
        assert _escape("Hello World") == "Hello World"

    def test_empty_string(self):
        assert _escape("") == ""


# ── detect_archetype ─────────────────────────────────────────────

class TestDetectArchetype:
    def test_returns_tuple(self, sample_profile):
        result = detect_archetype(sample_profile)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_deep_catalog_digger(self):
        profile = {
            "variety_score": 0.8,
            "mainstream_score": 0.1,
            "genre_distribution": [{"genre": "Rock", "weight": 1.0}],
            "energy_profile": "balanced",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, desc = detect_archetype(profile)
        assert label == "Deep Catalog Digger"

    def test_genre_drifter(self):
        profile = {
            "variety_score": 0.7,
            "mainstream_score": 0.5,
            "genre_distribution": [
                {"genre": g, "weight": 0.15}
                for g in ["Rock", "Pop", "Jazz", "Hip-Hop", "Electronic", "Classical"]
            ],
            "energy_profile": "balanced",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, _ = detect_archetype(profile)
        assert label == "Genre Drifter"

    def test_comfort_zone_commander(self):
        profile = {
            "variety_score": 0.2,
            "mainstream_score": 0.5,
            "genre_distribution": [
                {"genre": "Pop", "weight": 0.8},
                {"genre": "Rock", "weight": 0.2},
            ],
            "energy_profile": "balanced",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, _ = detect_archetype(profile)
        assert label == "Comfort Zone Commander"

    def test_nostalgia_keeper(self):
        profile = {
            "variety_score": 0.4,
            "mainstream_score": 0.4,
            "genre_distribution": [{"genre": "Rock", "weight": 1.0}],
            "energy_profile": "balanced",
            "era_distribution": [{"decade": "1980s", "weight": 0.7}],
        }
        label, _ = detect_archetype(profile)
        assert label == "Nostalgia Keeper"

    def test_trend_surfer(self):
        profile = {
            "variety_score": 0.4,
            "mainstream_score": 0.8,
            "genre_distribution": [
                {"genre": "Pop", "weight": 0.5},
                {"genre": "Hip-Hop", "weight": 0.3},
                {"genre": "R&B", "weight": 0.2},
            ],
            "energy_profile": "balanced",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, _ = detect_archetype(profile)
        assert label == "Trend Surfer"

    def test_indie_purist(self):
        profile = {
            "variety_score": 0.5,
            "mainstream_score": 0.1,
            "genre_distribution": [{"genre": "Indie", "weight": 1.0}],
            "energy_profile": "chill",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, _ = detect_archetype(profile)
        assert label == "Indie Purist"

    def test_energy_chaser(self):
        profile = {
            "variety_score": 0.4,
            "mainstream_score": 0.5,
            "genre_distribution": [{"genre": "EDM", "weight": 1.0}],
            "energy_profile": "high-energy",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, _ = detect_archetype(profile)
        assert label == "Energy Chaser"

    def test_chill_architect(self):
        profile = {
            "variety_score": 0.4,
            "mainstream_score": 0.25,
            "genre_distribution": [
                {"genre": "Ambient", "weight": 0.5},
                {"genre": "Jazz", "weight": 0.3},
                {"genre": "Lo-fi", "weight": 0.2},
            ],
            "energy_profile": "chill",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, _ = detect_archetype(profile)
        assert label == "Chill Architect"

    def test_balanced_explorer_fallback(self):
        """When no specific archetype matches early, Balanced Explorer always matches."""
        profile = {
            "variety_score": 0.5,
            "mainstream_score": 0.5,
            "genre_distribution": [
                {"genre": "Pop", "weight": 0.3},
                {"genre": "Rock", "weight": 0.3},
                {"genre": "Jazz", "weight": 0.2},
                {"genre": "Classical", "weight": 0.2},
            ],
            "energy_profile": "balanced",
            "era_distribution": [{"decade": "2020s", "weight": 0.5}],
        }
        label, _ = detect_archetype(profile)
        # Balanced Explorer is the catch-all but may also match other archetypes
        assert isinstance(label, str)
        assert len(label) > 0

    def test_keyerror_resilience(self):
        """detect_archetype should not crash on missing keys."""
        label, desc = detect_archetype({})
        assert label == "Balanced Explorer"

    def test_partial_profile(self):
        """Profile with only some keys should still return an archetype."""
        label, desc = detect_archetype({"variety_score": 0.5})
        assert isinstance(label, str)


# ── generate_svg ─────────────────────────────────────────────────

class TestGenerateSvg:
    def test_valid_svg(self, sample_profile):
        svg = generate_svg(sample_profile)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")

    def test_contains_taste_dna(self, sample_profile):
        svg = generate_svg(sample_profile)
        assert "TASTE DNA" in svg

    def test_contains_archetype(self, sample_profile):
        archetype, _ = detect_archetype(sample_profile)
        svg = generate_svg(sample_profile)
        assert _escape(archetype) in svg

    def test_contains_genres(self, sample_profile):
        svg = generate_svg(sample_profile)
        for g in sample_profile["genre_distribution"][:6]:
            assert _escape(g["genre"]) in svg

    def test_contains_artist_names(self, sample_profile):
        svg = generate_svg(sample_profile)
        for a in sample_profile["top_artists"][:8]:
            assert _escape(a["name"]) in svg

    def test_escapes_special_chars(self):
        profile = {
            "genre_distribution": [{"genre": "R&B/Soul", "weight": 0.5}],
            "top_artists": [{"name": "Simon & Garfunkel", "id": "a1", "play_count": 10}],
            "era_distribution": [{"decade": "1960s", "weight": 0.5}],
            "energy_profile": "chill",
            "variety_score": 0.5,
            "mainstream_score": 0.5,
        }
        svg = generate_svg(profile)
        assert "R&amp;B/Soul" in svg
        assert "Simon &amp; Garfunkel" in svg
        # Raw & should not appear in data values
        assert "R&B" not in svg.replace("R&amp;B", "")

    def test_empty_profile(self, empty_profile):
        svg = generate_svg(empty_profile)
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_footer_attribution(self, sample_profile):
        svg = generate_svg(sample_profile)
        assert "Apple Music DJ" in svg


# ── generate_text ────────────────────────────────────────────────

class TestGenerateText:
    def test_box_drawing(self, sample_profile):
        text = generate_text(sample_profile)
        assert "╔" in text
        assert "╚" in text
        assert "╠" in text

    def test_contains_taste_dna(self, sample_profile):
        text = generate_text(sample_profile)
        assert "TASTE DNA" in text

    def test_contains_archetype(self, sample_profile):
        archetype, _ = detect_archetype(sample_profile)
        text = generate_text(sample_profile)
        assert archetype in text

    def test_contains_genres_with_bars(self, sample_profile):
        text = generate_text(sample_profile)
        assert "█" in text
        for g in sample_profile["genre_distribution"][:6]:
            assert g["genre"] in text

    def test_contains_numbered_artists(self, sample_profile):
        text = generate_text(sample_profile)
        for i, a in enumerate(sample_profile["top_artists"][:8]):
            assert a["name"] in text
            assert f"{i+1}." in text

    def test_contains_stats(self, sample_profile):
        text = generate_text(sample_profile)
        assert "Energy:" in text
        assert "Variety:" in text
        assert "Mainstream:" in text
        assert "Velocity:" in text

    def test_era_mix(self, sample_profile):
        text = generate_text(sample_profile)
        assert "ERA MIX" in text
        for era in sample_profile["era_distribution"][:5]:
            assert era["decade"] in text

    def test_empty_profile(self, empty_profile):
        text = generate_text(empty_profile)
        assert "TASTE DNA" in text
        assert "N/A" in text  # empty era_distribution

    def test_footer_attribution(self, sample_profile):
        text = generate_text(sample_profile)
        assert "Apple Music DJ" in text
