"""Guards for how the skill shows up on ClawHub.

The listing page uses the frontmatter `description` as its summary (cut off after a few sentences
with "Read more") and renders SKILL.md as the page body, while the same `description` is what an
agent reads to decide when to use the skill. So it has to open crisply for people AND keep every
trigger phrase for agents.
"""

import json
import re
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def frontmatter() -> str:
    text = (ROOT / "SKILL.md").read_text()
    assert text.startswith("---\n")
    return text.split("\n---\n", 1)[0].removeprefix("---\n")


def description() -> str:
    """The folded (`>`) description block, joined into one line."""
    lines = frontmatter().splitlines()
    start = lines.index("description: >") + 1
    block = []
    for line in lines[start:]:
        if line and not line.startswith(" "):
            break
        block.append(line.strip())
    return " ".join(part for part in block if part)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def frontmatter_value(key: str) -> str:
    match = re.search(rf"^{key}:\s*(.+)$", frontmatter(), re.M)
    assert match, f"{key} missing from SKILL.md frontmatter"
    return match.group(1).strip()


def test_versions_agree_across_the_three_files():
    pyproject = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    clawhub = json.loads((ROOT / "clawhub.json").read_text())["version"]
    assert frontmatter_value("version") == pyproject == clawhub


def test_description_opens_crisply_before_the_read_more_cut():
    desc = description()
    first = sentences(desc)
    assert len(first[0]) <= 80, f"opening sentence is too long: {first[0]!r}"
    # What a visitor sees before "Read more": a few sentences, so they must carry the pitch
    assert len(" ".join(first[:3])) <= 420
    assert "Apple Music" in " ".join(first[:2])
    assert not desc.startswith("Ultimate")  # the old run-on opening


def test_description_keeps_every_trigger_phrase_agents_rely_on():
    desc = description().lower().replace("\n", " ")
    normalized = re.sub(r"\s+", " ", desc)
    for phrase in ("apple music", "playlists", "music recommendations", "what should i listen to",
                   "surprise me", "deep cuts", "songs like", "similar to", "more like", "taste dna",
                   "taste card", "compatibility", "year in review", "listening stats",
                   "what have i missed", "album deep dive", "rabbit hole", "concert prep", "daily song",
                   "blend", "throwback", "taste drift", "import my playlist", "i didn't like track",
                   "add the missing albums", "new release", "cron", "dj"):
        assert phrase in normalized, f"trigger phrase dropped from the description: {phrase!r}"


def test_tags_cover_the_main_topics():
    tags = set(re.findall(r"^\s+-\s+(\S+)$", frontmatter().split("tags:", 1)[1].split("category:", 1)[0], re.M))
    assert {"music", "apple-music", "playlists", "musickit", "discovery", "taste-profile"} <= tags


def test_readme_local_images_exist_and_the_sample_card_is_valid_svg():
    readme = (ROOT / "README.md").read_text()
    images = re.findall(r"!\[[^\]]*\]\((?!https?://)([^)\s]+)\)", readme)
    assert "assets/sample-taste-card.svg" in images
    for rel in images:
        assert (ROOT / rel).is_file(), f"README references a missing image: {rel}"
    xml.dom.minidom.parse(str(ROOT / "assets" / "sample-taste-card.svg"))  # raises if malformed


def test_readme_has_no_coming_soon_placeholders():
    assert "coming soon" not in (ROOT / "README.md").read_text().lower()


def test_shipped_docs_avoid_the_pattern_a_scanner_misread_as_a_seed_phrase():
    """An earlier example put `--seed "<value>"` in SKILL.md and a static scanner flagged it as a
    crypto seed phrase passed on the command line (critical)."""
    pattern = re.compile(r"--seed[ =]+[\"'<$]")
    shipped = [ROOT / "SKILL.md", ROOT / "README.md", *sorted((ROOT / "references").glob("*.md"))]
    offenders = [p.name for p in shipped if pattern.search(p.read_text())]
    assert not offenders, f"flagged pattern found in: {offenders}"


def test_skill_md_documents_the_safety_posture_near_the_top():
    body = (ROOT / "SKILL.md").read_text()
    glance = body.split("## At a glance", 1)[1].split("## Architecture", 1)[0]
    assert "Try saying" in glance and "Safety" in glance and "confirmed first" in glance


def test_concert_prep_docs_match_the_script_which_previews_by_default():
    body = (ROOT / "SKILL.md").read_text()
    section = body.split("### Concert Prep Playlist", 1)[1].split("### ", 1)[0]
    assert "Preview first" in section and "--create" in section and "only after they" in section
    assert "Creates directly" not in body  # the old wording that promised an unconfirmed write
    script = (ROOT / "scripts" / "concert_prep.sh").read_text()
    assert "--create" in script and "Preview only" in script


def test_skill_md_says_scheduled_jobs_run_unattended():
    body = (ROOT / "SKILL.md").read_text()
    assert "runs unattended and writes on its own" in body
    assert "unattended once installed" in body.split("## At a glance", 1)[1].split("## Architecture", 1)[0]
