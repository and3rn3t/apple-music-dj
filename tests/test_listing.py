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


def test_description_fits_the_agent_skills_limit():
    """The Agent Skills spec caps `description` at 1024 characters; Claude-side validators and the
    community skill lists reject anything longer. The `>` scalar keeps one trailing newline that
    `description()` drops, so count it."""
    assert len(description()) + 1 <= 1024


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


def test_shipped_docs_never_suggest_rm_rf_on_the_data_folder():
    """A reviewer flagged `rm -rf ~/.apple-music-dj/` (user data, no confirmation) in three docs."""
    shipped = [ROOT / "SKILL.md", ROOT / "README.md", ROOT / "SECURITY.md", *sorted((ROOT / "references").glob("*.md"))]
    offenders = [p.name for p in shipped if re.search(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+~/?\.apple-music-dj", p.read_text())]
    assert not offenders, f"destructive cache-clearing advice in: {offenders}"


def test_skill_md_discloses_that_editing_a_playlist_can_remove_tracks():
    body = (ROOT / "SKILL.md").read_text()
    glance = body.split("## At a glance", 1)[1].split("## Architecture", 1)[0]
    assert "remove tracks" in glance and "playlist_health.py fix --apply" in glance and "get a yes first" in glance
    written = body.split("Data written to the user's account", 1)[1].split("**Data stored locally", 1)[0]
    assert "playlist_health.py fix --apply" in written and "/tracks" in written


def test_docs_name_apply_not_auto_for_the_health_fix():
    for path in (ROOT / "SKILL.md", ROOT / "README.md", *sorted((ROOT / "references").glob("*.md"))):
        assert "playlist_health.py fix" not in path.read_text() or "--auto" not in path.read_text(), path.name


def _openclaw_block(key: str) -> str:
    """The indented block under `metadata.openclaw.<key>:` (plain text; no YAML dependency in CI)."""
    fm = frontmatter()
    match = re.search(rf"^    {key}:\n((?:      .*\n)+)", fm + "\n", re.M)
    assert match, f"metadata.openclaw.{key} missing"
    return match.group(1)


def _env_vars() -> dict[str, str]:
    """envVars entries as {name: required-value}."""
    block = _openclaw_block("envVars")
    return dict(re.findall(r"- name: (\S+)\n\s+required: (\S+)", block))


def test_tokens_are_optional_so_the_skill_loads_for_the_demo():
    """OpenClaw hides a skill whose requires.env vars are unset, which would hide the no-token demo."""
    assert not re.search(r"^\s+env:", _openclaw_block("requires"), re.M)
    declared = _env_vars()
    for token in ("APPLE_MUSIC_DEV_TOKEN", "APPLE_MUSIC_USER_TOKEN"):
        assert declared[token] == "false"
    assert frontmatter_value("    primaryEnv") == "APPLE_MUSIC_DEV_TOKEN"
    clawhub = json.loads((ROOT / "clawhub.json").read_text())
    assert "env" not in clawhub["requires"]
    assert {"APPLE_MUSIC_DEV_TOKEN", "APPLE_MUSIC_USER_TOKEN"} <= {v["name"] for v in clawhub["envVars"]}
    assert all(v["required"] is False for v in clawhub["envVars"])


def test_every_apple_env_var_the_scripts_read_is_declared():
    """ClawHub's review flags env vars the code reads but the frontmatter doesn't declare."""
    declared = set(_env_vars())
    used = set()
    for path in sorted((ROOT / "scripts").glob("*.[ps][yh]")):
        used |= set(re.findall(r"\b(APPLE_[A-Z0-9_]+)\b", path.read_text()))
    assert used - declared == set(), f"undeclared env vars: {sorted(used - declared)}"


def test_only_the_newest_changelog_section_may_be_unreleased():
    """A published version must carry a date; "Unreleased" is for the section being written."""
    headings = re.findall(r"^## \[([^\]]+)\]([^\n]*)$", (ROOT / "CHANGELOG.md").read_text(), re.M)
    assert len(headings) > 3
    stale = [version for version, rest in headings[1:] if not re.search(r"\d{4}-\d{2}-\d{2}", rest)]
    assert not stale, f"released versions without a date in CHANGELOG.md: {stale}"
