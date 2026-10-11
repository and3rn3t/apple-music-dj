#!/usr/bin/env python3
"""Render `demo.py tour` as an animated terminal replay (assets/demo-tour.svg).

The README embeds the SVG, so people see the skill working without installing anything. The text is
the tour's real output (run fresh unless --input is given); only the request lines are added. GitHub
plays CSS animations in SVG images; with reduced motion the replay shows one scene as a still.

Usage:
  python3 .github/scripts/make_demo_svg.py                  # writes assets/demo-tour.svg
  python3 .github/scripts/make_demo_svg.py --freeze 2       # a still of scene 2, for checking the layout
"""

import argparse
import re
import subprocess
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "assets" / "demo-tour.svg"

LINE_H, FONT, PAD_X, CHAR_W = 20, 13, 24, 7.9
BAR_H, TOP, FOOT_H = 38, 26, 34
MAX_LINES = 16          # output lines shown per scene; longer ones end in an ellipsis
STILL_SCENE = 2         # shown when the viewer prefers reduced motion
REQUESTS = {"Your Taste DNA card": "Show me my taste card"}
CAPTION = "demo mode · fictional listener · nothing touches an Apple Music account"


def parse_scenes(text: str) -> list[tuple[str, list[str]]]:
    """[(request, output lines)] from the tour's `── title ──` sections."""
    scenes, title, body = [], None, []
    for line in text.splitlines():
        match = re.fullmatch(r"── (.+) ──", line.rstrip())  # column 0 only: the card has indented ones
        if match:
            if title is not None:
                scenes.append((title, body))
            title, body = match.group(1), []
        elif title is not None:
            body.append(line.rstrip())
    if title is not None:
        scenes.append((title, body))
    out = []
    for title, body in scenes:
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        collapsed = []
        for line in body:
            if line.strip() or (collapsed and collapsed[-1].strip()):
                collapsed.append(line)
        if not collapsed or title.startswith("That's the demo"):
            continue
        quoted = re.search(r'"([^"]+)"', title)
        request = quoted.group(1) if quoted else REQUESTS.get(title, title)
        if len(collapsed) > MAX_LINES:
            collapsed = collapsed[:MAX_LINES - 1] + ["  …"]
        out.append((request, collapsed))
    return out


def line_class(line: str) -> str:
    if line.lstrip().startswith("──") or set(line.strip()) <= set("╔╗╚╝═║╠╣ "):
        return "dim"
    return "out"


def render(scenes: list[tuple[str, list[str]]], freeze: int | None = None) -> str:
    longest = max(len(line) for _, body in scenes for line in body + ["› " + scenes[0][0]])
    width = round(max(longest, len(CAPTION)) * CHAR_W + 2 * PAD_X)
    rows = max(len(body) for _, body in scenes) + 2
    height = BAR_H + TOP + rows * LINE_H + FOOT_H

    # Timeline: per scene — request, then output lines, then a hold, then a short gap.
    timings, t = [], 0.4
    for _, body in scenes:
        shown = [t]                      # when the request line appears
        t += 0.9
        for _ in body:
            shown.append(t)
            t += 0.09
        t += 3.2                             # hold on the finished scene
        timings.append((t, shown))
        t += 0.5
    total = t

    css, texts = [], []
    for si, ((request, body), (end, shown)) in enumerate(zip(scenes, timings, strict=True), 1):
        lines = [("req", f"› {request}")] + [(line_class(x), x) for x in body]
        for li, ((cls, text), at) in enumerate(zip(lines, shown, strict=True)):
            y = BAR_H + TOP + li * LINE_H
            name = f"s{si}l{li}"
            a, b = at / total * 100, end / total * 100
            css.append(f"@keyframes {name}{{0%,{a:.3f}%{{opacity:0}}{a + 0.001:.3f}%,{b:.3f}%{{opacity:1}}"
                       f"{b + 0.001:.3f}%,100%{{opacity:0}}}}"
                       f".{name}{{animation:{name} {total:.2f}s linear infinite}}")
            visible = freeze == si
            style = ' style="opacity:1"' if visible else ""
            klass = f"l {cls} {name}" if freeze is None else f"l {cls}"
            if freeze is not None and not visible:
                continue
            still = " still" if freeze is None and si == STILL_SCENE else ""
            texts.append(f'<text class="{klass}{still}" x="{PAD_X}" y="{y}" xml:space="preserve"{style}>'
                         f"{escape(text)}</text>")
    animation = "" if freeze is not None else "\n".join(css)
    reduced = ("@media (prefers-reduced-motion: reduce){.l{animation:none!important;opacity:0}"
               ".l.still{opacity:1}}") if freeze is None else ""
    names = ", ".join(f"“{r}”" for r, _ in scenes)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="t d">
<title id="t">Apple Music DJ demo</title>
<desc id="d">A terminal replay of the no-account demo: {escape(names)}.</desc>
<style>
text{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono",monospace;font-size:{FONT}px;white-space:pre}}
.l{{opacity:0;fill:#e6edf3}}.req{{fill:#79c0ff;font-weight:600}}.dim{{fill:#8b949e}}.cap{{fill:#8b949e;font-size:12px}}
{animation}
{reduced}
</style>
<rect width="{width}" height="{height}" rx="10" fill="#0d1117"/>
<rect width="{width}" height="{BAR_H}" rx="10" fill="#161b22"/><rect y="{BAR_H - 10}" width="{width}" height="10" fill="#161b22"/>
<circle cx="22" cy="19" r="6" fill="#ff5f56"/><circle cx="42" cy="19" r="6" fill="#ffbd2e"/><circle cx="62" cy="19" r="6" fill="#27c93f"/>
<text x="{width // 2}" y="23" text-anchor="middle" class="cap" xml:space="preserve">🎧 Apple Music DJ</text>
{chr(10).join(texts)}
<text x="{PAD_X}" y="{height - 12}" class="cap" xml:space="preserve">{escape(CAPTION)}</text>
</svg>
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", help="a saved `demo.py tour` output (default: run it now)")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--freeze", type=int, help="write a static still of this scene (1-based)")
    args = parser.parse_args(argv)
    if args.input:
        text = Path(args.input).read_text()
    else:
        text = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo.py"), "tour"],
                              capture_output=True, text=True, check=True, timeout=120).stdout
    scenes = parse_scenes(text)
    if len(scenes) < 4:
        sys.exit(f"expected at least 4 scenes in the tour output, found {len(scenes)}")
    Path(args.out).write_text(render(scenes, args.freeze))
    print(f"wrote {args.out} ({len(scenes)} scenes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
