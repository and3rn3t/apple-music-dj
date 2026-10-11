import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("self_audit", ROOT / ".github" / "scripts" / "self_audit.py")
sa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sa)


def test_the_review_prompt_covers_each_reviewer_concern():
    prompt = sa.review_prompt("v1.0.0", "SKILL.md | 2 +-")
    for concern in ("Undisclosed writes", "Unattended actions", "Credentials", "Network", "Injection",
                    "Prompt injection", "Scope", "Mismatch"):
        assert concern in prompt
    assert "since v1.0.0" in prompt and "SKILL.md | 2 +-" in prompt


def test_the_prompt_says_so_when_nothing_changed():
    assert "(none)" in sa.review_prompt("v1.0.0", "")


def test_shipped_files_match_the_package_and_exclude_dev_files():
    files = sa.shipped_files()
    assert "SKILL.md" in files and "scripts/apple_music_api.sh" in files
    assert not any(f.startswith(("tests/", ".github/")) or f in {"CHANGELOG.md", "ROADMAP.md"} for f in files)


def test_the_checks_it_runs_exist():
    assert all((ROOT / c).is_file() for c in sa.CHECKS)
