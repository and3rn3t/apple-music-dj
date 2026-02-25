#!/usr/bin/env python3
"""
taste_card.py — Generate a shareable Taste DNA Card (SVG).

Reads a taste profile JSON and produces a visual summary card with:
  - Listener archetype label
  - Top genres with bar chart
  - Top artists
  - Era breakdown
  - Stats: variety, mainstream, energy, velocity

Usage:
  python3 taste_card.py <profile.json> [--output card.svg]
  python3 taste_card.py <profile.json> --format text

Requires: A taste profile JSON (from taste_profiler.py).
"""

import argparse
import json
import sys
from pathlib import Path

# ── Archetype Detection ──────────────────────────────────────────

ARCHETYPES = [
    # (label, condition_fn, description)
    ("Deep Catalog Digger", lambda p: p["variety_score"] > 0.7 and p["mainstream_score"] < 0.3,
     "You live in the deep end — album tracks, B-sides, and artists most people haven't heard of."),
    ("Genre Drifter", lambda p: p["variety_score"] > 0.6 and len(p["genre_distribution"]) >= 6,
     "Your taste refuses to stay in one lane. Every genre is fair game."),
    ("Comfort Zone Commander", lambda p: p["variety_score"] < 0.3 and len(p["genre_distribution"]) <= 3,
     "You know what you like and you stick to it. Deep loyalty to a tight rotation."),
    ("Nostalgia Keeper", lambda p: _top_era(p).startswith(("19", "200")) and _top_era_weight(p) > 0.5,
     "Your heart lives in a different decade. The classics never get old."),
    ("Trend Surfer", lambda p: p["mainstream_score"] > 0.6,
     "You ride the wave — if it's on the charts, you've heard it."),
    ("Indie Purist", lambda p: p["mainstream_score"] < 0.2 and p["energy_profile"] != "high-energy",
     "Mainstream? Never heard of it. Your taste is curated, intentional, and defiantly independent."),
    ("Energy Chaser", lambda p: p["energy_profile"] == "high-energy" and p["mainstream_score"] > 0.3,
     "Volume up, tempo high. You need music that matches your intensity."),
    ("Chill Architect", lambda p: p["energy_profile"] == "chill",
     "Low tempo, warm tones, ambient vibes. You build soundscapes, not playlists."),
    ("Balanced Explorer", lambda p: True,
     "A well-rounded listener who keeps one foot in the familiar and one in the unknown."),
]


def _top_era(profile: dict) -> str:
    eras = profile.get("era_distribution", [])
    return eras[0]["decade"] if eras else "2020s"


def _top_era_weight(profile: dict) -> float:
    eras = profile.get("era_distribution", [])
    return eras[0]["weight"] if eras else 0.0


def detect_archetype(profile: dict) -> tuple[str, str]:
    """Return (archetype_label, description)."""
    for label, condition, desc in ARCHETYPES:
        try:
            if condition(profile):
                return label, desc
        except (KeyError, IndexError, TypeError):
            continue
    return "Balanced Explorer", "A well-rounded listener."


# ── SVG Card Generator ──────────────────────────────────────────

def _bar(value: float, max_width: int = 180) -> int:
    return max(4, int(value * max_width))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _stat_label(key: str) -> str:
    labels = {
        "variety_score": "Variety",
        "mainstream_score": "Mainstream",
    }
    return labels.get(key, key.replace("_", " ").title())


def generate_svg(profile: dict) -> str:
    archetype, arch_desc = detect_archetype(profile)
    top_genres = profile.get("genre_distribution", [])[:6]
    top_artists = profile.get("top_artists", [])[:8]
    eras = profile.get("era_distribution", [])[:5]
    energy = profile.get("energy_profile", "balanced")
    variety = profile.get("variety_score", 0.5)
    mainstream = profile.get("mainstream_score", 0.5)
    velocity = profile.get("listening_velocity", "moderate")
    summary = profile.get("data_summary", {})

    # Colors
    bg = "#1a1a2e"
    card_bg = "#16213e"
    accent = "#e94560"
    text = "#eaeaea"
    muted = "#a0a0b0"
    bar_color = "#e94560"
    bar_bg = "#2a2a4a"

    w, h = 480, 720
    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">')
    lines.append(f'<rect width="{w}" height="{h}" rx="16" fill="{bg}"/>')
    lines.append(f'<rect x="16" y="16" width="{w-32}" height="{h-32}" rx="12" fill="{card_bg}"/>')

    # Header
    lines.append(f'<text x="240" y="52" text-anchor="middle" font-family="system-ui,sans-serif" '
                 f'font-size="13" fill="{muted}" letter-spacing="3">TASTE DNA</text>')
    lines.append(f'<text x="240" y="84" text-anchor="middle" font-family="system-ui,sans-serif" '
                 f'font-size="22" font-weight="700" fill="{accent}">{_escape(archetype)}</text>')
    lines.append(f'<text x="240" y="106" text-anchor="middle" font-family="system-ui,sans-serif" '
                 f'font-size="11" fill="{muted}">{_escape(arch_desc[:70])}</text>')

    # Divider
    lines.append(f'<line x1="40" y1="122" x2="440" y2="122" stroke="{bar_bg}" stroke-width="1"/>')

    # Top Genres
    y = 148
    lines.append(f'<text x="40" y="{y}" font-family="system-ui,sans-serif" '
                 f'font-size="11" fill="{muted}" letter-spacing="2">TOP GENRES</text>')
    y += 6
    for g in top_genres:
        y += 22
        bw = _bar(g["weight"])
        lines.append(f'<rect x="140" y="{y-10}" width="180" height="12" rx="3" fill="{bar_bg}"/>')
        lines.append(f'<rect x="140" y="{y-10}" width="{bw}" height="12" rx="3" fill="{bar_color}"/>')
        lines.append(f'<text x="136" y="{y}" text-anchor="end" font-family="system-ui,sans-serif" '
                     f'font-size="11" fill="{text}">{_escape(g["genre"])}</text>')
        pct = int(g["weight"] * 100)
        lines.append(f'<text x="326" y="{y}" font-family="system-ui,sans-serif" '
                     f'font-size="10" fill="{muted}">{pct}%</text>')

    # Divider
    y += 18
    lines.append(f'<line x1="40" y1="{y}" x2="440" y2="{y}" stroke="{bar_bg}" stroke-width="1"/>')

    # Top Artists
    y += 22
    lines.append(f'<text x="40" y="{y}" font-family="system-ui,sans-serif" '
                 f'font-size="11" fill="{muted}" letter-spacing="2">TOP ARTISTS</text>')
    y += 4
    for i, a in enumerate(top_artists):
        y += 20
        rank = f"{i+1}."
        lines.append(f'<text x="50" y="{y}" font-family="system-ui,sans-serif" '
                     f'font-size="11" fill="{muted}">{rank}</text>')
        lines.append(f'<text x="68" y="{y}" font-family="system-ui,sans-serif" '
                     f'font-size="12" fill="{text}">{_escape(a["name"])}</text>')

    # Divider
    y += 18
    lines.append(f'<line x1="40" y1="{y}" x2="440" y2="{y}" stroke="{bar_bg}" stroke-width="1"/>')

    # Stats row
    y += 26
    stats = [
        ("Energy", energy.replace("-", " ").title()),
        ("Variety", f"{int(variety * 100)}%"),
        ("Mainstream", f"{int(mainstream * 100)}%"),
        ("Velocity", velocity.title()),
    ]
    col_w = 100
    for i, (label, val) in enumerate(stats):
        cx = 40 + i * col_w + col_w // 2
        lines.append(f'<text x="{cx}" y="{y}" text-anchor="middle" font-family="system-ui,sans-serif" '
                     f'font-size="10" fill="{muted}">{label}</text>')
        lines.append(f'<text x="{cx}" y="{y+18}" text-anchor="middle" font-family="system-ui,sans-serif" '
                     f'font-size="14" font-weight="600" fill="{text}">{val}</text>')

    # Era badges
    y += 42
    lines.append(f'<text x="40" y="{y}" font-family="system-ui,sans-serif" '
                 f'font-size="11" fill="{muted}" letter-spacing="2">ERA MIX</text>')
    y += 8
    ex = 40
    for era in eras:
        label = era["decade"]
        tw = len(label) * 8 + 16
        lines.append(f'<rect x="{ex}" y="{y}" width="{tw}" height="22" rx="11" '
                     f'fill="{bar_bg}" stroke="{accent}" stroke-width="1"/>')
        lines.append(f'<text x="{ex + tw//2}" y="{y+15}" text-anchor="middle" '
                     f'font-family="system-ui,sans-serif" font-size="10" fill="{text}">{label}</text>')
        ex += tw + 8

    # Footer
    lines.append(f'<text x="240" y="{h-28}" text-anchor="middle" font-family="system-ui,sans-serif" '
                 f'font-size="9" fill="{muted}">Generated by Apple Music DJ · openclaw</text>')

    lines.append('</svg>')
    return '\n'.join(lines)


# ── Text Card (terminal-friendly) ───────────────────────────────

def generate_text(profile: dict) -> str:
    archetype, arch_desc = detect_archetype(profile)
    top_genres = profile.get("genre_distribution", [])[:6]
    top_artists = profile.get("top_artists", [])[:8]
    eras = profile.get("era_distribution", [])[:5]
    energy = profile.get("energy_profile", "balanced")
    variety = profile.get("variety_score", 0.5)
    mainstream = profile.get("mainstream_score", 0.5)
    velocity = profile.get("listening_velocity", "moderate")
    summary = profile.get("data_summary", {})

    bar_full = "█"
    bar_empty = "░"

    lines = []
    lines.append("╔══════════════════════════════════════╗")
    lines.append("║          🎧  TASTE DNA CARD          ║")
    lines.append("╠══════════════════════════════════════╣")
    lines.append(f"  Archetype: {archetype}")
    lines.append(f"  {arch_desc}")
    lines.append("")
    lines.append("  ── TOP GENRES ──")
    for g in top_genres:
        pct = int(g["weight"] * 100)
        filled = int(g["weight"] * 20)
        bar = bar_full * filled + bar_empty * (20 - filled)
        lines.append(f"  {g['genre']:.<20s} {bar} {pct}%")
    lines.append("")
    lines.append("  ── TOP ARTISTS ──")
    for i, a in enumerate(top_artists):
        lines.append(f"  {i+1:>2}. {a['name']}")
    lines.append("")
    lines.append("  ── STATS ──")
    lines.append(f"  Energy:     {energy.replace('-', ' ').title()}")
    lines.append(f"  Variety:    {int(variety * 100)}%")
    lines.append(f"  Mainstream: {int(mainstream * 100)}%")
    lines.append(f"  Velocity:   {velocity.title()}")
    lines.append("")
    lines.append("  ── ERA MIX ──")
    era_str = "  " + " · ".join(e["decade"] for e in eras) if eras else "  N/A"
    lines.append(era_str)
    lines.append("")
    lines.append("╚══════════════════════════════════════╝")
    lines.append("  Generated by Apple Music DJ · openclaw")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Taste DNA Card")
    parser.add_argument("profile", help="Path to taste profile JSON")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout)")
    parser.add_argument("--format", choices=["svg", "text"], default="svg",
                        help="Output format (default: svg)")
    args = parser.parse_args()

    try:
        with open(args.profile) as f:
            profile = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "svg":
        result = generate_svg(profile)
    else:
        result = generate_text(profile)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(result)
        print(f"✅ Taste DNA Card written to {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
