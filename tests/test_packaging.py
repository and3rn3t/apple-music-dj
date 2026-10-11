"""The skill is packaged by two tools that read two differently named ignore files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rules(name):
    lines = (ROOT / name).read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def test_clawignore_and_clawhubignore_have_the_same_rules():
    """`clawhub publish` ignores .clawignore entirely (it reads .clawhubignore); without this
    check the two drift and dev files — tests, pyproject — get uploaded to the registry."""
    assert rules(".clawhubignore") == rules(".clawignore")


def test_dev_files_and_secrets_are_excluded():
    ignored = set(rules(".clawhubignore"))
    for must_exclude in ("tests/", ".env", ".env.*", "*.p8", "*.pem", ".venv/", "__pycache__/",
                         "CHANGELOG.md", "CONTRIBUTING.md", "pyproject.toml"):
        assert must_exclude in ignored, f"{must_exclude} would be published"


def test_runtime_files_are_not_excluded():
    ignored = set(rules(".clawhubignore"))
    for needed in ("SKILL.md", "README.md", "LICENSE", "scripts/", "references/", "assets/", "clawhub.json"):
        assert needed not in ignored, f"{needed} is needed by the published skill"
    assert not any(r.startswith(("scripts", "references", "SKILL")) for r in ignored)
