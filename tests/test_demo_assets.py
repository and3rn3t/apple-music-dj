"""The README's animated demo and the Spotify sample are generated from / run by the real scripts."""

import importlib.util
import re
import xml.dom.minidom
from pathlib import Path

import import_playlist

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("make_demo_svg", ROOT / ".github" / "scripts" / "make_demo_svg.py")
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)

TOUR = """🎧 Demo mode: a fictional listener.

── Building a taste profile ──


── Your Taste DNA card ──

╔════╗
  Archetype: Nostalgia Keeper

  ── TOP GENRES ──
  Rock... 75%
╚════╝

── "Songs like Radiohead" (a preview) ──

Like Radiohead
 1. Starlight — Muse

── "Make me a 90s throwback" ──

1990s Throwback
 1. Let Down — Radiohead

── "Give me one song" ──

Today's pick: X

── That's the demo ──
Ready for your own music?
"""


def test_scenes_split_on_column_zero_titles_only():
    scenes = mk.parse_scenes(TOUR)
    assert [request for request, _ in scenes] == [
        "Show me my taste card", "Songs like Radiohead", "Make me a 90s throwback", "Give me one song"]
    card = scenes[0][1]
    assert any("TOP GENRES" in line for line in card), "indented sub-headings stay inside the card scene"


def test_long_scenes_are_cut_with_an_ellipsis():
    scenes = mk.parse_scenes("── A ──\n" + "\n".join(f"line {i}" for i in range(40)) + "\n── B ──\nx\n")
    body = scenes[0][1]
    assert len(body) == mk.MAX_LINES and body[-1].strip() == "…"


def test_rendered_svg_is_valid_and_animated():
    svg = mk.render(mk.parse_scenes(TOUR))
    xml.dom.minidom.parseString(svg)
    assert "@keyframes" in svg and "prefers-reduced-motion" in svg and "<title" in svg
    assert "Songs like Radiohead" in svg


def test_freeze_makes_a_static_still():
    svg = mk.render(mk.parse_scenes(TOUR), freeze=2)
    assert "@keyframes" not in svg and "Starlight" in svg and "Let Down" not in svg


def test_committed_demo_svg_is_valid_and_has_the_real_scenes():
    text = (ROOT / "assets" / "demo-tour.svg").read_text()
    xml.dom.minidom.parseString(text)
    for phrase in ("Songs like Radiohead", "90s throwback", "TASTE DNA CARD", "nothing touches an Apple Music account"):
        assert phrase in text
    assert len(text) < 60_000


def test_sample_spotify_export_parses_without_isrc():
    rows = import_playlist.parse_file(str(ROOT / "assets" / "sample-spotify-export.csv"))
    assert len(rows) == 4
    assert all(r["title"] and r["artist"] and r["isrc"] is None for r in rows)


def test_a_long_later_request_is_not_clipped_by_the_viewbox():
    long_request = "Make me a playlist for a very long rainy Sunday afternoon of reading by the window"
    svg = mk.render([("Short", ["a", "b"]), (long_request, ["x"])])
    width = int(re.search(r'viewBox="0 0 (\d+) ', svg).group(1))
    assert width >= (len(long_request) + 2) * mk.CHAR_W
