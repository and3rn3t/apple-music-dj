"""Guards that the docs keep up with the code.

An audit (#69, #70) found SKILL.md's Scripts table missing the core script, README's tree missing a
reference, and SKILL.md documenting cron schedules the code didn't use. Each check here fails with
the file to fix, so the next drift is caught in CI instead of by a reader.
"""

import functools
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml is a dev dependency (pip install -e '.[dev]')")

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "SKILL.md").read_text()
README = (ROOT / "README.md").read_text()
SCRIPTS = sorted(p.name for p in (ROOT / "scripts").iterdir() if p.suffix in (".py", ".sh"))
REFERENCES = sorted(p.name for p in (ROOT / "references").glob("*.md"))
DOCS = [*sorted(ROOT.glob("*.md")), *sorted((ROOT / "references").glob("*.md"))]
SKILL_BODY_LIMIT = 500


def section(text: str, heading: str) -> str:
    """From `heading` up to the next heading of the same or a higher level."""
    level = heading.split(" ", 1)[0]
    start = text.index(heading + "\n")
    rest = text[start + len(heading) + 1:]
    nxt = re.search(rf"^#{{1,{len(level)}}} ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def readme_tree() -> str:
    block = section(README, "## 📁 Project Structure")
    return block.split("```", 2)[1]


# ── Inventories ──────────────────────────────────────────────────

@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_is_in_skill_md_scripts_table(script):
    assert f"| `scripts/{script}` |" in section(SKILL, "## Scripts"), \
        f"add a row for scripts/{script} to the Scripts table in SKILL.md"


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_is_in_readme_tree(script):
    assert re.search(rf"\b{re.escape(script)}\b", readme_tree()), \
        f"add scripts/{script} to the Project Structure tree in README.md"


@pytest.mark.parametrize("ref", REFERENCES)
def test_every_reference_is_in_skill_md_reference_table(ref):
    assert f"| `references/{ref}` |" in section(SKILL, "## Reference Files"), \
        f"add references/{ref} to the Reference Files table in SKILL.md (with when to read it)"


@pytest.mark.parametrize("ref", REFERENCES)
def test_every_reference_is_in_readme_tree(ref):
    assert re.search(rf"\b{re.escape(ref)}\b", readme_tree()), \
        f"add references/{ref} to the Project Structure tree in README.md"


# ── Links and paths ──────────────────────────────────────────────

@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_and_paths_exist(doc):
    text = doc.read_text()
    broken = []
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
        if not target.startswith(("http://", "https://", "mailto:")) and not (doc.parent / target).exists():
            broken.append(target)
    for path in re.findall(r"(?:(?<![\w/.{])|(?<=\{baseDir\}/))((?:scripts|references)/[\w.-]+\.(?:py|sh|md))", text):
        if not (ROOT / path).exists():
            broken.append(path)
    assert not broken, f"{doc.relative_to(ROOT)} points at missing files: {sorted(set(broken))}"


# ── Documented commands ─────────────────────────────────────────

@functools.cache
def help_text(script: str, sub: str | None = None) -> str:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *([sub] if sub else []), "-h"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=ROOT)
    return r.stdout if r.returncode == 0 else ""


def command_texts(text: str) -> list[str]:
    """Commands as written: fenced-block lines (with `\\` continuations joined, `# comments` dropped)
    and inline code spans. Pipes inside a span (`svg|text`, `[--since 90d | --from …]`) stay part of the
    command; a Markdown table's `|` separators fall outside the spans."""
    out = []
    fences = re.findall(r"^```[^\n]*\n(.*?)^```", text, re.M | re.S)
    for block in fences:
        for line in re.sub(r"\\\n\s*", " ", block).splitlines():
            out.append(re.split(r"\s#\s", line, maxsplit=1)[0])
    prose = re.sub(r"^```[^\n]*\n.*?^```", "", text, flags=re.M | re.S)
    out += re.findall(r"`([^`\n]+)`", prose)
    return out


def flags_by_command(text: str) -> list[tuple[str, str | None, str]]:
    """(script, subcommand, flag) for every `--flag` after a `scripts/x.py` in a command."""
    found = []
    for cmd in command_texts(text):
        hits = list(re.finditer(r"scripts/([a-z_]+\.py)", cmd))
        for i, m in enumerate(hits):
            rest = cmd[m.end(): hits[i + 1].start() if i + 1 < len(hits) else len(cmd)]
            toks = rest.split()
            sub = toks[0] if toks and re.fullmatch(r"[a-z][a-z-]+", toks[0]) else None
            if m.group(1) == "demo.py" and sub == "run":
                continue  # flags after `demo.py run <script>` belong to that script
            found += [(m.group(1), sub, f) for f in re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", rest)]
    return found


def test_flag_extraction_handles_continuations_and_inline_pipes():
    fenced = "```bash\npython3 scripts/strategy_engine.py --strategy blend \\\n        --profile-b x --storefront us\n```\n"
    inline = "| x | `python3 {baseDir}/scripts/taste_drift.py [--since 90d | --from 2026-01-01] --format text` |"
    alt = "Run: `python3 {baseDir}/scripts/taste_card.py <p> [--format svg|text] [--output card.svg]`"
    assert {f for _, _, f in flags_by_command(fenced)} == {"--strategy", "--profile-b", "--storefront"}
    assert {f for _, _, f in flags_by_command(inline)} == {"--since", "--from", "--format"}
    assert {f for _, _, f in flags_by_command(alt)} == {"--format", "--output"}


def documented_commands() -> list[tuple[str, str, str | None, str]]:
    """(doc, script, subcommand, flag) for every `--flag` in a documented `scripts/x.py …` command."""
    return sorted({(doc.relative_to(ROOT).as_posix(), *hit) for doc in DOCS for hit in flags_by_command(doc.read_text())})


@pytest.mark.parametrize("doc,script,sub,flag", documented_commands())
def test_documented_flags_exist(doc, script, sub, flag):
    known = help_text(script) + (help_text(script, sub) if sub else "")
    assert re.search(rf"{re.escape(flag)}(?![\w-])", known), f"{doc} documents `{script}{' ' + sub if sub else ''} {flag}`, which `-h` doesn't list"


def api_commands() -> list[str]:
    text = (ROOT / "scripts" / "apple_music_api.sh").read_text()
    dispatch = text.split('case "$cmd" in', 1)[1].split("\nesac", 1)[0]
    return re.findall(r"^\s+([a-z][a-z-]+)\)", dispatch, re.M)


def test_api_dispatch_parsed():
    assert len(api_commands()) > 20


@pytest.mark.parametrize("command", api_commands())
def test_every_api_command_is_in_the_api_reference(command):
    ref = (ROOT / "references" / "api-reference.md").read_text()
    assert re.search(rf"apple_music_api\.sh {re.escape(command)}\b", ref), \
        f"name `apple_music_api.sh {command}` under its endpoint in references/api-reference.md"


# ── Versions, size, schedules ────────────────────────────────────

def test_readme_python_badge_matches_ci():
    badge = re.search(r"img\.shields\.io/badge/python-([^)]*?)-blue", README)
    assert badge, "README.md has no Python badge"
    shown = re.findall(r"\d+\.\d+", unquote(badge.group(1)))
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "test.yml").read_text())
    tested = [str(v) for v in workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]]
    assert shown == tested, f"README.md's Python badge says {shown}; CI tests {tested}"


def test_skill_md_body_stays_small():
    body = SKILL.removeprefix("---\n").split("\n---\n", 1)[1]
    lines = len(body.splitlines())
    assert lines < SKILL_BODY_LIMIT, (
        f"SKILL.md's body is {lines} lines (limit {SKILL_BODY_LIMIT}, the Agent Skills guideline): "
        "move detail into references/ and list it in the Reference Files table instead of raising the limit")


def cron_time(schedule: str) -> str:
    minute, hour = schedule.split()[:2]
    return f"{int(hour)}:{int(minute):02d}"


def test_cron_time_formatting():
    assert cron_time("0 7 * * 1") == "7:00" and cron_time("30 8 * * *") == "8:30"


def scheduled_jobs() -> dict[str, dict]:
    import setup_cron
    return setup_cron.build_job_defs("python3", "profile.json", "us", "/tmp/logs")


@pytest.mark.parametrize("name,job", sorted(scheduled_jobs().items()))
def test_automation_reference_matches_setup_cron(name, job):
    doc = (ROOT / "references" / "automation.md").read_text()
    rows = [line for line in doc.splitlines() if line.startswith("|") and f"`{name}`" in line]
    assert rows, f"references/automation.md has no table row for the `{name}` job"
    when = cron_time(job["schedule"])
    assert any(re.search(rf"(?<![\d:]){re.escape(when)}(?!\d)", row) for row in rows), \
        f"references/automation.md's `{name}` row should say {when} (setup_cron.py schedules `{job['schedule']}`)"
