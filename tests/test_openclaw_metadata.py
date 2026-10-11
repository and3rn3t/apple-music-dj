"""Guards that SKILL.md's frontmatter is what OpenClaw and ClawHub actually read.

Both parse the frontmatter as YAML; if that fails OpenClaw falls back to a single-line parser and
silently drops every nested key, including the whole `metadata` block. Fields neither reads (an
earlier `platforms`, `minVersion`, `permissions`) do nothing, so a gate written that way gates
nothing. ClawHub publishes every skill as MIT-0 and won't take another license. Specs:
docs.openclaw.ai/tools/skills and ClawHub's docs/skill-format.md.
"""

import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml is a dev dependency (pip install -e '.[dev]')")

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"

OS_VALUES = {"darwin", "linux", "win32"}
INSTALL_KINDS = {"brew", "node", "go", "uv", "download"}
UNREAD_KEYS = {"platforms", "minVersion", "permissions"}
# Tools beyond POSIX basics that the scripts call unconditionally; each must be in requires.bins.
REQUIRED_TOOLS = {"curl", "jq", "python3"}


def skill_parts() -> tuple[dict, str]:
    text = SKILL.read_text()
    head, body = text.removeprefix("---\n").split("\n---\n", 1)
    return yaml.safe_load(head), body


def openclaw() -> dict:
    return skill_parts()[0]["metadata"]["openclaw"]


def test_frontmatter_is_valid_yaml_with_the_required_keys():
    fm, _ = skill_parts()
    assert isinstance(fm, dict)
    for key in ("name", "description", "version"):
        assert fm.get(key), f"{key} missing from SKILL.md frontmatter"


def test_name_is_a_portable_skill_name_and_matches_the_slug():
    # The folder name varies (CI publishes from a temp copy), so compare with the manifest instead.
    name = skill_parts()[0]["name"]
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name)
    assert name == json.loads((ROOT / "clawhub.json").read_text())["name"]


def test_metadata_uses_the_openclaw_key_not_a_legacy_alias():
    meta = skill_parts()[0]["metadata"]
    assert set(meta) == {"openclaw"}, "clawdbot/clawdis are legacy; OpenClaw no longer reads them"


def test_only_fields_the_spec_reads_are_used_for_gating():
    oc = openclaw()
    assert not UNREAD_KEYS & set(oc), f"not read by OpenClaw or ClawHub: {UNREAD_KEYS & set(oc)}"
    assert oc["os"] and set(oc["os"]) <= OS_VALUES
    assert oc.get("emoji"), "OpenClaw's Skills UI reads emoji from metadata.openclaw"
    assert oc.get("homepage") == skill_parts()[0]["homepage"]


def test_install_specs_use_supported_kinds_and_cover_declared_bins():
    oc = openclaw()
    for spec in oc.get("install", []):
        assert spec["kind"] in INSTALL_KINDS
        assert set(spec.get("bins", [])) <= set(oc["requires"]["bins"])
        assert set(spec.get("os", [])) <= OS_VALUES


def test_required_bins_match_what_the_scripts_call():
    bins = set(openclaw()["requires"]["bins"])
    shell = "\n".join(p.read_text() for p in (ROOT / "scripts").glob("*.sh"))
    used = {tool for tool in REQUIRED_TOOLS if re.search(rf"\b{tool}\b", shell)}
    assert used == REQUIRED_TOOLS, "update REQUIRED_TOOLS if a script stops needing one"
    assert bins == REQUIRED_TOOLS


def test_optional_crontab_is_documented_but_not_required():
    assert "crontab" not in openclaw()["requires"]["bins"]
    assert '"crontab"' in (ROOT / "scripts" / "setup_cron.py").read_text()
    assert "`crontab` (scheduling)" in SKILL.read_text()


def test_script_invocations_use_basedir():
    # The agent's working directory isn't guaranteed to be the skill folder; OpenClaw expands
    # {baseDir}. The file-index table names files rather than running them, so it is exempt.
    _, body = skill_parts()
    bare = [
        line for line in body.splitlines()
        if not line.startswith("| `scripts/")
        and re.search(r"(?<![\w/{}.])scripts/\w+\.(py|sh)\b", line)
    ]
    assert not bare, "use {baseDir}/scripts/...:\n" + "\n".join(bare)


def test_every_license_field_says_mit_0():
    assert skill_parts()[0]["license"] == "MIT-0"
    assert json.loads((ROOT / "clawhub.json").read_text())["license"] == "MIT-0"
    assert 'license = {text = "MIT-0"}' in (ROOT / "pyproject.toml").read_text()  # no tomllib on 3.10
    assert (ROOT / "LICENSE").read_text().startswith("MIT No Attribution\n")


def test_clawhub_json_mirrors_the_skill_metadata():
    manifest = json.loads((ROOT / "clawhub.json").read_text())
    oc = openclaw()
    assert manifest["os"] == oc["os"]
    assert manifest["envVars"] == oc["envVars"]
    assert manifest["requires"] == oc["requires"]
