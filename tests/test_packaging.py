"""The skill is packaged by two tools that read two differently named ignore files.

`clawhub publish` ignores .clawignore entirely: it skips every dot-entry, applies .gitignore plus
.clawhubignore, then uploads the text files that are left. These tests reproduce that selection
with git's own ignore engine (`git check-ignore --no-index`, with .clawhubignore as the extra
excludes file) and assert on the files that would actually ship — not on the rule strings, so a
broad rule like `*.md`, or a rule added only to .gitignore, is caught too.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

# What the published skill is allowed to contain at its top level. A new root file must be added
# here (or ignored) on purpose, so dev files can't slip into the package unnoticed.
ALLOWED_ROOT = {"README.md", "SKILL.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "LICENSE", "clawhub.json",
                "requirements.txt"}
ALLOWED_DIRS = {"scripts", "references", "assets"}
MUST_NOT_SHIP = ("pyproject.toml", "CHANGELOG.md", "CONTRIBUTING.md", "renovate.json", "Makefile", "ROADMAP.md",
                "assets/social-preview.svg", "assets/social-preview.png")


def _git(args, cwd, input_=None):
    return subprocess.run(["git", *args], cwd=cwd, input=input_, capture_output=True, text=True)


def shipped_files(root: Path) -> list[str]:
    """Files `clawhub publish <root>` would pick up (tracked files, mirroring the CLI's rules)."""
    tracked = _git(["ls-files", "-z"], root).stdout.split("\0")
    # The CLI's walk skips any entry whose name starts with "." (files and directories)
    candidates = [p for p in tracked if p and not any(part.startswith(".") for part in Path(p).parts)]
    excludes = root / ".clawhubignore"
    result = _git(["-c", f"core.excludesFile={excludes}", "check-ignore", "--no-index", "-z", "--stdin"],
                  root, input_="\0".join(candidates) + "\0")
    ignored = {p for p in result.stdout.split("\0") if p}
    return sorted(set(candidates) - ignored)


def rules(name):
    lines = (ROOT / name).read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def test_clawignore_and_clawhubignore_have_the_same_rules():
    """`clawhub publish` ignores .clawignore entirely (it reads .clawhubignore); without this
    check the two drift and OpenClaw and ClawHub package different things."""
    assert rules(".clawhubignore") == rules(".clawignore")


@pytest.fixture(scope="module")
def shipped():
    if shutil.which("git") is None or _git(["rev-parse", "--is-inside-work-tree"], ROOT).returncode != 0:
        pytest.skip("needs a git checkout")
    return shipped_files(ROOT)


@needs_git
class TestRealPackage:
    def test_runtime_files_ship(self, shipped):
        tracked = _git(["ls-files", "-z"], ROOT).stdout.split("\0")
        required = {"SKILL.md", "README.md", "clawhub.json", "assets/icon.svg"}
        required |= {p for p in tracked if p.startswith(("scripts/", "references/"))}
        missing = sorted(required - set(shipped))
        assert not missing, f"runtime files that would NOT be published: {missing}"

    def test_dev_files_and_tests_do_not_ship(self, shipped):
        leaked = [p for p in shipped if p.startswith("tests/") or p in MUST_NOT_SHIP]
        assert not leaked, f"dev files that would be published: {leaked}"

    def test_nothing_unexpected_ships(self, shipped):
        root_files = {p for p in shipped if "/" not in p}
        dirs = {p.split("/")[0] for p in shipped if "/" in p}
        assert root_files <= ALLOWED_ROOT, f"unexpected root files: {sorted(root_files - ALLOWED_ROOT)}"
        assert dirs <= ALLOWED_DIRS, f"unexpected directories: {sorted(dirs - ALLOWED_DIRS)}"

    def test_secrets_and_caches_never_ship(self, shipped):
        bad = [p for p in shipped if p.endswith((".pem", ".p8", ".pyc")) or ".env" in Path(p).name
               or "__pycache__" in p]
        assert not bad


@needs_git
class TestSelectionLogic:
    """The checks above are only as good as shipped_files(); prove it reacts to bad rules."""

    def _repo(self, tmp_path, clawhubignore="", gitignore=""):
        for rel in ("SKILL.md", "README.md", "scripts/run.py", "tests/test_x.py", ".hidden/x.md", ".env"):
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x")
        (tmp_path / ".clawhubignore").write_text(clawhubignore)
        (tmp_path / ".gitignore").write_text(gitignore)
        _git(["init", "-q"], tmp_path)
        _git(["add", "-A", "-f"], tmp_path)
        return tmp_path

    def test_baseline(self, tmp_path):
        repo = self._repo(tmp_path, clawhubignore="tests/\n")
        assert shipped_files(repo) == ["README.md", "SKILL.md", "scripts/run.py"]  # dot entries are skipped

    def test_broad_rule_that_hides_runtime_files_is_visible(self, tmp_path):
        repo = self._repo(tmp_path, clawhubignore="tests/\n*.md\n")
        assert "SKILL.md" not in shipped_files(repo) and "README.md" not in shipped_files(repo)

    def test_star_rule_ships_nothing(self, tmp_path):
        assert shipped_files(self._repo(tmp_path, clawhubignore="*\n")) == []

    def test_gitignore_rules_also_apply(self, tmp_path):
        """ClawHub feeds .gitignore to its matcher too, so a rule added only there hides files."""
        repo = self._repo(tmp_path, clawhubignore="tests/\n", gitignore="scripts/\n")
        assert "scripts/run.py" not in shipped_files(repo)

    def test_a_removed_exclusion_makes_dev_files_ship(self, tmp_path):
        repo = self._repo(tmp_path, clawhubignore="")
        assert "tests/test_x.py" in shipped_files(repo)
