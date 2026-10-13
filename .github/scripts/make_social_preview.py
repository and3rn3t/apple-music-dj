#!/usr/bin/env python3
"""Render the GitHub social preview card (assets/social-preview.svg and .png, 1280×640).

GitHub shows this image when the repo is linked on Reddit, X, Discord, Slack and so on. It reuses
the icon and the taste card's palette. GitHub's API can't set it, so after rendering upload the PNG
by hand: repo Settings → General → Social preview → Edit → Upload an image.

The PNG is rendered with headless Chrome (set CHROME to override the path).

Usage:
  python3 .github/scripts/make_social_preview.py            # writes the SVG and the PNG
  python3 .github/scripts/make_social_preview.py --svg-only
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_SVG = ROOT / "assets" / "social-preview.svg"
OUT_PNG = ROOT / "assets" / "social-preview.png"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

W, H = 1280, 640
FONT = "-apple-system,BlinkMacSystemFont,'SF Pro Display',system-ui,sans-serif"
BG, PANEL, TRACK, ACCENT, TEXT, MUTED = "#1a1a2e", "#16213e", "#2a2a4a", "#e94560", "#eaeaea", "#a0a0b0"

FEATURES = ["8 playlist strategies", "Taste DNA", "Songs like X", "Spotify import", "Blend with a friend"]
GENRES = [("Alternative", 27), ("Indie", 19), ("Electronic", 16), ("Hip-Hop/Rap", 10), ("Jazz", 8)]


def icon(x: int, y: int, size: int) -> str:
    """assets/icon.svg's artwork, placed at (x, y) and scaled to size."""
    art = (ROOT / "assets" / "icon.svg").read_text()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", art, re.S).group(1)
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.S).replace('id="bg"', 'id="icon-bg"').replace("url(#bg)", "url(#icon-bg)")
    return f'<g transform="translate({x},{y}) scale({size / 512})">{inner}</g>'


def text(x, y, s, size, fill=TEXT, weight=400, anchor="start", spacing=0) -> str:
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" letter-spacing="{spacing}">{escape(s)}</text>')


def chips(x: int, y: int) -> str:
    out, cx, cy = [], x, y
    for label in FEATURES:
        w = int(len(label) * 10.4) + 36
        if cx + w > 760:
            cx, cy = x, cy + 52
        out.append(f'<rect x="{cx}" y="{cy}" width="{w}" height="38" rx="19" fill="{PANEL}" stroke="{TRACK}"/>')
        out.append(text(cx + w / 2, cy + 25, label, 18, TEXT, 500, "middle"))
        cx += w + 12
    return "\n".join(out)


def card(x: int, y: int) -> str:
    """A miniature taste card, like the one taste_card.py draws."""
    w, h = 380, 460
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="{PANEL}" stroke="{TRACK}" stroke-width="2"/>',
           text(x + w / 2, y + 50, "TASTE DNA", 15, MUTED, 500, "middle", 4),
           text(x + w / 2, y + 90, "Deep Catalog Digger", 28, ACCENT, 700, "middle"),
           f'<line x1="{x + 30}" y1="{y + 116}" x2="{x + w - 30}" y2="{y + 116}" stroke="{TRACK}"/>',
           text(x + 30, y + 150, "TOP GENRES", 13, MUTED, 500, spacing=3)]
    top = GENRES[0][1]
    for i, (genre, pct) in enumerate(GENRES):
        gy = y + 178 + i * 44
        out.append(text(x + 30, gy + 15, genre, 17, TEXT))
        out.append(f'<rect x="{x + 160}" y="{gy}" width="150" height="16" rx="5" fill="{TRACK}"/>')
        out.append(f'<rect x="{x + 160}" y="{gy}" width="{150 * pct / top:.0f}" height="16" rx="5" fill="{ACCENT}"/>')
        out.append(text(x + w - 30, gy + 14, f"{pct}%", 15, MUTED, anchor="end"))
    out.append(f'<line x1="{x + 30}" y1="{y + 410}" x2="{x + w - 30}" y2="{y + 410}" stroke="{TRACK}"/>')
    out.append(text(x + w / 2, y + 440, "Variety 78% · Mainstream 27% · Velocity High", 14, MUTED, anchor="middle"))
    return "\n".join(out)


def render_svg() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="glow" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="{ACCENT}" stop-opacity="0.22"/>
    <stop offset="60%" stop-color="{BG}" stop-opacity="0"/>
  </linearGradient>
</defs>
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect width="{W}" height="{H}" fill="url(#glow)"/>
{icon(80, 80, 112)}
{text(80, 268, "Apple Music DJ", 72, TEXT, 800)}
{text(80, 322, "Playlists from your real listening history.", 30, MUTED, 400)}
{chips(80, 368)}
{text(80, 540, "Agent Skill for Claude Code & OpenClaw", 22, TEXT, 600)}
{text(80, 574, "Read-only by default · Try the demo with no account", 20, MUTED)}
{card(820, 90)}
</svg>
"""


def render_png(svg: Path, png: Path) -> None:
    if not Path(CHROME).exists():
        sys.exit(f"Chrome not found at {CHROME}; set CHROME or use --svg-only.")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "card.html"
        page.write_text(f'<html><body style="margin:0;background:{BG}">{svg.read_text()}</body></html>')
        png.unlink(missing_ok=True)
        # Chrome sometimes keeps running after it has written the screenshot, so wait for the file
        # rather than for the process.
        proc = subprocess.Popen([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                                 f"--window-size={W},{H}", f"--user-data-dir={tmp}/profile",
                                 f"--screenshot={png}", page.as_uri()],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while not (png.exists() and png.stat().st_size) and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        time.sleep(0.5)
        proc.terminate()
        proc.wait(timeout=10)
        if not (png.exists() and png.stat().st_size):
            sys.exit("Chrome didn't write the screenshot.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svg-only", action="store_true", help="write the SVG but don't render the PNG")
    args = parser.parse_args()
    OUT_SVG.write_text(render_svg())
    print(f"wrote {OUT_SVG.relative_to(ROOT)}")
    if not args.svg_only:
        render_png(OUT_SVG, OUT_PNG)
        print(f"wrote {OUT_PNG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
