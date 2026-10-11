import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

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


def _repo(tmp_path):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                       cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / ".clawhubignore").write_text("tests/\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("SKILL.md", "scripts/gone.sh", "scripts/kept.sh", "tests/test_x.py"):
        (tmp_path / name).write_text("v1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    git("tag", "v1")
    return git


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_a_shipped_file_deleted_since_the_tag_still_shows_up(tmp_path):
    git = _repo(tmp_path)
    (tmp_path / "scripts/gone.sh").unlink()
    (tmp_path / "tests/test_x.py").unlink()          # a dev file: not part of the package
    (tmp_path / "scripts/kept.sh").write_text("v2\n")
    git("add", "-A")
    git("commit", "-q", "-m", "two")

    paths = sa.shipped_paths("v1", tmp_path)
    assert "scripts/gone.sh" in paths and "scripts/kept.sh" in paths
    assert "tests/test_x.py" not in paths
    stat = sa.shipped_changes("v1", root=tmp_path)
    assert "scripts/gone.sh" in stat and "scripts/kept.sh" in stat and "test_x" not in stat


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_a_renamed_shipped_file_shows_the_old_name_too(tmp_path):
    git = _repo(tmp_path)
    (tmp_path / "scripts/kept.sh").rename(tmp_path / "scripts/renamed.sh")
    git("add", "-A")
    git("commit", "-q", "-m", "rename")
    assert {"scripts/kept.sh", "scripts/renamed.sh"} <= set(sa.shipped_paths("v1", tmp_path))
