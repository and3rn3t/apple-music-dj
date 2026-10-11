"""Guards for the claims SKILL.md makes about network, environment, files and risky constructs.

ClawHub's reviewers see only the shipped package (not these tests), so the claims must be true and
stay true: a new host, env var or stored file has to be documented before this passes.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "scripts").glob("*.sh"))
SKILL = (ROOT / "SKILL.md").read_text()

ALLOWED_URLS = {
    "https://api.music.apple.com",
    "http://127.0.0.1",  # test hook, loopback only
    "http://localhost",  # test hook, loopback only
    "http://www.w3.org/2000/svg",  # SVG XML namespace, not a request
    "https://js-cdn.music.apple.com",  # MusicKit JS, loaded by setup_auth.py's local sign-in page
}

RISKY = {
    "eval": re.compile(r"(?<![\w.])eval\b"),
    "piped installer": re.compile(r"curl[^|\n]*\|\s*(ba)?sh"),
    "sudo": re.compile(r"\bsudo\b"),
    "shell=True": re.compile(r"shell\s*=\s*True"),
    "os.system": re.compile(r"os\.system"),
    "rm -rf": re.compile(r"rm\s+-rf"),
}


def code_lines(path: Path):
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.lstrip().startswith("#"):
            yield number, line


def test_scripts_only_contact_documented_hosts():
    for path in SCRIPTS:
        for number, line in code_lines(path):
            for url in re.findall(r"https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9./_\-]*)?", line):
                if "github.com" in url:
                    continue
                host = re.match(r"https?://[^/:]+", url).group(0)
                assert any(url.startswith(a) or host == a for a in ALLOWED_URLS), f"{path.name}:{number} {url}"
    assert "https://api.music.apple.com" in SKILL
    assert "Apple's CDN" in SKILL  # the one extra host must stay disclosed


def test_no_risky_constructs_in_shipped_scripts():
    for path in SCRIPTS:
        for number, line in code_lines(path):
            for name, pattern in RISKY.items():
                assert not pattern.search(line), f"{path.name}:{number} uses {name}"


def test_every_env_var_the_scripts_read_is_documented():
    names = set()
    for path in SCRIPTS:
        names |= set(re.findall(r"\bAPPLE_[A-Z_]+\b", path.read_text()))
    assert names, "expected the scripts to reference APPLE_* variables"
    missing = sorted(n for n in names if n not in SKILL)
    assert not missing, f"undocumented in SKILL.md: {missing}"


def test_every_stored_file_is_documented():
    paths = set()
    for path in SCRIPTS:
        paths |= set(re.findall(r"\.apple-music-dj/([A-Za-z0-9_.\-]+)", path.read_text()))
    # Filenames can appear with trailing punctuation from prose
    names = {p.rstrip(".") for p in paths}
    missing = sorted(n for n in names if n and n not in SKILL)
    assert not missing, f"stored under ~/.apple-music-dj but undocumented in SKILL.md: {missing}"


def test_token_handoff_is_disclosed():
    assert "temporary" in SKILL and "0600" in SKILL


def test_every_account_writing_command_asks_for_confirmation():
    """Enumerated from the script, so a new write command can't skip the --yes check."""
    text = (ROOT / "scripts" / "apple_music_api.sh").read_text()
    writers = re.compile(r"\b_(post|post_file|post_empty|put_file|delete|delete_no_body)\b")
    bodies = re.findall(r"^(cmd_\w+)\(\) \{\n(.*?)^\}", text, re.S | re.M)
    assert len(bodies) > 20, "failed to parse the command functions"
    writing = [name for name, body in bodies if writers.search(body)]
    assert len(writing) >= 7, writing  # create/add/remove playlist, add-to-library, favorite, rate, unrate
    unconfirmed = [name for name, body in bodies if name in writing and "_confirm" not in body]
    assert not unconfirmed, f"write commands without _confirm: {unconfirmed}"
