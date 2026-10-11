"""Tests for .github/scripts/release_checks.py (the publish-to-ClawHub workflow's helper)."""

import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release_checks", ROOT / ".github" / "scripts" / "release_checks.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def make_repo(tmp_path, skill="3.4.5", pyproject="3.4.5", clawhub="3.4.5", changelog=None):
    (tmp_path / "SKILL.md").write_text(f"---\nname: x\nversion: {skill}\nemoji: 🎧\n---\n# X\nversion: 9.9.9 in the body\n")
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{pyproject}"\n')
    (tmp_path / "clawhub.json").write_text(json.dumps({"name": "x", "version": clawhub}))
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog)
    return tmp_path


class FakeCLI:
    """Stands in for subprocess.run: pops one scripted response per call and records the commands."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        out = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(out, subprocess.CompletedProcess):
            return out
        stdout, code = out if isinstance(out, tuple) else (out, 0)
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="")


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


# ── versions ─────────────────────────────────────────────────────

class TestVersions:
    def test_agreeing_files(self, tmp_path):
        assert rc.agreed_version(make_repo(tmp_path)) == "3.4.5"

    def test_only_frontmatter_version_counts(self, tmp_path):
        assert rc.read_versions(make_repo(tmp_path))["SKILL.md"] == "3.4.5"  # not the 9.9.9 in the body

    @pytest.mark.parametrize("kw", [{"skill": "3.4.6"}, {"pyproject": "3.4.6"}, {"clawhub": "3.4.6"}])
    def test_any_disagreement_is_reported_with_all_three(self, tmp_path, kw):
        with pytest.raises(rc.CheckError, match=r"disagree.*SKILL.md=.*pyproject.toml=.*clawhub.json="):
            rc.agreed_version(make_repo(tmp_path, **kw))

    @pytest.mark.parametrize("version", ["3.4", "3.4.5-rc1", "v3.4.5", "3.4.5.1"])
    def test_non_semver_is_rejected(self, tmp_path, version):
        with pytest.raises(rc.CheckError, match="not plain semver"):
            rc.agreed_version(make_repo(tmp_path, skill=version, pyproject=version, clawhub=version))

    def test_missing_version_is_named(self, tmp_path):
        repo = make_repo(tmp_path)
        (repo / "clawhub.json").write_text("{}")
        with pytest.raises(rc.CheckError, match="clawhub.json"):
            rc.read_versions(repo)

    def test_real_repo_versions_agree(self):
        assert rc.agreed_version(ROOT)


class TestCheckTag:
    def test_matching_tag(self, tmp_path):
        assert rc.check_tag("v3.4.5", make_repo(tmp_path)) == "3.4.5"

    @pytest.mark.parametrize("tag", ["3.4.5", "v3.4.4", "v3.4.5-rc1", "release-3.4.5", ""])
    def test_mismatched_tag(self, tmp_path, tag):
        with pytest.raises(rc.CheckError, match="doesn't match"):
            rc.check_tag(tag, make_repo(tmp_path))


# ── changelog ────────────────────────────────────────────────────

CHANGELOG = """# Changelog

## [Unreleased]

## [3.4.5] — 2026-01-02

### Fixed

- one thing

## [3.4.4] — 2026-01-01

- older

## [3.4.10]

- a different version that shares a prefix
"""


class TestChangelog:
    def test_extracts_just_that_section(self):
        section = rc.changelog_section(CHANGELOG, "3.4.5")
        assert "one thing" in section and "older" not in section and "3.4.4" not in section

    def test_last_section_runs_to_end_of_file(self):
        assert "shares a prefix" in rc.changelog_section(CHANGELOG, "3.4.10")

    def test_prefix_versions_do_not_collide(self):
        assert "shares a prefix" not in rc.changelog_section(CHANGELOG, "3.4.5")
        with pytest.raises(rc.CheckError):
            rc.changelog_section(CHANGELOG, "3.4")  # [3.4.x] must not match "3.4"

    @pytest.mark.parametrize("text", ["# Changelog\n", "## [3.4.5]\n\n## [3.4.4]\n- x\n", "## [3.4.5]\n   \n"])
    def test_missing_or_empty_section_fails(self, text):
        with pytest.raises(rc.CheckError, match=r"no \(non-empty\) section"):
            rc.changelog_section(text, "3.4.5")

    def test_notes_are_headed_and_truncated(self, tmp_path):
        repo = make_repo(tmp_path, changelog="## [3.4.5]\n\n" + "- line\n" * 500)
        notes = rc.release_notes("3.4.5", max_chars=300, root=repo)
        assert notes.startswith("v3.4.5\n\n") and len(notes) <= 300 and notes.endswith("CHANGELOG.md)")

    def test_short_notes_are_not_truncated(self, tmp_path):
        repo = make_repo(tmp_path, changelog="## [3.4.5]\n\n- x\n")
        assert rc.release_notes("3.4.5", max_chars=300, root=repo) == "v3.4.5\n\n- x"


# ── config / auth ────────────────────────────────────────────────

class TestWriteConfig:
    def test_writes_owner_only_json(self, tmp_path):
        path = tmp_path / "cfg.json"
        rc.write_config(str(path), " secret-token \n")
        assert json.loads(path.read_text()) == {"registry": "https://clawhub.ai", "token": "secret-token"}
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_tightens_an_existing_world_readable_file(self, tmp_path):
        path = tmp_path / "cfg.json"
        path.write_text("{}")
        path.chmod(0o644)
        rc.write_config(str(path), "t")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    @pytest.mark.parametrize("token", ["", "   ", "\n"])
    def test_empty_token_is_a_clear_error(self, tmp_path, token):
        with pytest.raises(rc.CheckError, match="CLAWHUB_TOKEN is empty"):
            rc.write_config(str(tmp_path / "cfg.json"), token)
        assert not (tmp_path / "cfg.json").exists()


class TestWhoami:
    def test_expected_handle(self):
        assert rc.check_whoami("and3rn3t", run=FakeCLI("- Checking token\n✔ and3rn3t\n")) == "and3rn3t"

    def test_handle_with_at_sign(self):
        assert rc.check_whoami("and3rn3t", run=FakeCLI("@and3rn3t")) == "@and3rn3t"

    def test_wrong_account_is_refused(self):
        with pytest.raises(rc.CheckError, match="expected 'and3rn3t'"):
            rc.check_whoami("and3rn3t", run=FakeCLI("✔ someone-else"))

    def test_failed_login_is_refused_even_if_output_looks_right(self):
        with pytest.raises(rc.CheckError):
            rc.check_whoami("and3rn3t", run=FakeCLI(("✔ and3rn3t", 1)))

    def test_cli_is_called_non_interactively(self):
        cli = FakeCLI("✔ and3rn3t")
        rc.check_whoami("and3rn3t", run=cli)
        assert cli.calls == [["clawhub", "whoami", "--no-input"]]


# ── waiting for the registry ─────────────────────────────────────

def inspect_json(version):
    return json.dumps({"skill": {"slug": "x"}, "latestVersion": {"version": version}})


class TestWaitForVersion:
    def test_immediately_latest(self):
        clock = Clock()
        rc.wait_for_version("x", "3.4.5", run=FakeCLI(inspect_json("3.4.5")), sleep=clock.sleep, clock=clock.now)
        assert clock.t == 0

    def test_polls_until_the_new_version_lands(self):
        clock = Clock()
        cli = FakeCLI(inspect_json("3.4.4"), inspect_json("3.4.4"), inspect_json("3.4.5"))
        rc.wait_for_version("x", "3.4.5", interval=20, run=cli, sleep=clock.sleep, clock=clock.now)
        assert len(cli.calls) == 3 and clock.t == 40

    def test_tolerates_transient_failures_and_bad_json(self):
        clock = Clock()
        cli = FakeCLI(("", 1), ("not json", 0), inspect_json("3.4.5"))
        rc.wait_for_version("x", "3.4.5", run=cli, sleep=clock.sleep, clock=clock.now)
        assert len(cli.calls) == 3

    def test_times_out_with_a_useful_message(self):
        clock = Clock()
        with pytest.raises(rc.CheckError, match=r"didn't become ClawHub's latest within 100s"):
            rc.wait_for_version("x", "3.4.5", timeout=100, interval=20, run=FakeCLI(inspect_json("3.4.4")),
                                sleep=clock.sleep, clock=clock.now)
        assert clock.t >= 100

    def test_asks_for_the_right_slug(self):
        cli = FakeCLI(inspect_json("3.4.5"))
        rc.wait_for_version("apple-music-dj", "3.4.5", run=cli, sleep=lambda s: None)
        assert cli.calls[0][:3] == ["clawhub", "inspect", "apple-music-dj"]


# ── verdict ──────────────────────────────────────────────────────

def verdict(status="clean", passed=True, decision="pass", reasons=()):
    return json.dumps({"decision": decision, "reasons": list(reasons),
                       "security": {"status": status, "passed": passed, "summary": "the summary"}})


class TestCheckVerdict:
    def test_clean_and_passing(self):
        result = rc.check_verdict("x", "3.4.5", run=FakeCLI(verdict()), sleep=lambda s: None)
        assert result["decision"] == "pass"

    def test_waits_out_a_lagging_skill_card(self):
        slept = []
        cli = FakeCLI(verdict(decision="fail", reasons=["card.missing"]),
                      verdict(decision="fail", reasons=["card.missing"]), verdict())
        rc.check_verdict("x", "3.4.5", interval=30, run=cli, sleep=slept.append)
        assert len(cli.calls) == 3 and slept == [30, 30]

    def test_a_card_that_never_appears_eventually_fails(self):
        with pytest.raises(rc.CheckError, match="card was still not generated after 3 checks"):
            rc.check_verdict("x", "3.4.5", attempts=3, run=FakeCLI(verdict(decision="fail", reasons=["card.missing"])),
                             sleep=lambda s: None)

    @pytest.mark.parametrize("status", ["suspicious", "malicious", "pending", None])
    def test_a_non_clean_verdict_fails_immediately_without_retrying(self, status):
        cli = FakeCLI(verdict(status=status, passed=False, decision="fail", reasons=["security.status_not_clean"]))
        with pytest.raises(rc.CheckError, match="Security verdict"):
            rc.check_verdict("x", "3.4.5", run=cli, sleep=lambda s: pytest.fail("must not wait on a bad verdict"))
        assert len(cli.calls) == 1

    def test_clean_status_but_not_passed_fails(self):
        with pytest.raises(rc.CheckError, match="Security verdict"):
            rc.check_verdict("x", "3.4.5", run=FakeCLI(verdict(passed=False)), sleep=lambda s: None)

    def test_other_reasons_fail_even_alongside_card_missing(self):
        with pytest.raises(rc.CheckError, match="signature.invalid"):
            rc.check_verdict("x", "3.4.5", run=FakeCLI(verdict(decision="fail", reasons=["card.missing", "signature.invalid"])),
                             sleep=lambda s: None)

    def test_unreadable_output_is_a_clear_error(self):
        with pytest.raises(rc.CheckError, match="Couldn't read"):
            rc.check_verdict("x", "3.4.5", run=FakeCLI("<html>502</html>"), sleep=lambda s: None)


# ── command line ─────────────────────────────────────────────────

class TestMain:
    def test_versions(self, capsys):
        assert rc.main(["versions"]) == 0
        assert capsys.readouterr().out.strip() == rc.agreed_version()

    def test_check_tag_passes_and_fails(self, capsys):
        assert rc.main(["check-tag", f"v{rc.agreed_version()}"]) == 0
        assert rc.main(["check-tag", "v0.0.0"]) == 1
        assert "::error::" in capsys.readouterr().err

    def test_notes_for_a_real_version(self, capsys):
        assert rc.main(["notes", "--version", rc.agreed_version(), "--max-chars", "500"]) == 0
        assert capsys.readouterr().out.startswith(f"v{rc.agreed_version()}")

    def test_notes_for_an_unknown_version_fail(self):
        assert rc.main(["notes", "--version", "0.0.0"]) == 1

    def test_write_config_reads_the_token_from_the_environment(self, tmp_path, monkeypatch):
        cfg = tmp_path / "clawhub.json"
        monkeypatch.setenv("CLAWHUB_CONFIG_PATH", str(cfg))
        monkeypatch.setenv("CLAWHUB_TOKEN", "from-env")
        assert rc.main(["write-config"]) == 0
        assert json.loads(cfg.read_text())["token"] == "from-env"

    def test_write_config_without_a_token_variable_fails_cleanly(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CLAWHUB_CONFIG_PATH", str(tmp_path / "c.json"))
        monkeypatch.delenv("CLAWHUB_TOKEN", raising=False)
        assert rc.main(["write-config"]) == 1
        assert "CLAWHUB_TOKEN is empty" in capsys.readouterr().err

    def test_write_config_without_a_path_variable_fails_cleanly(self, monkeypatch, capsys):
        monkeypatch.delenv("CLAWHUB_CONFIG_PATH", raising=False)
        assert rc.main(["write-config"]) == 1
        assert "Missing environment variable" in capsys.readouterr().err

    def test_token_is_never_printed(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CLAWHUB_CONFIG_PATH", str(tmp_path / "c.json"))
        monkeypatch.setenv("CLAWHUB_TOKEN", "super-secret-value")
        rc.main(["write-config"])
        out = capsys.readouterr()
        assert "super-secret-value" not in out.out + out.err

    def test_subcommands_wired_to_the_cli_helpers(self, monkeypatch, capsys):
        monkeypatch.setattr(rc, "check_whoami", lambda expect: expect)
        monkeypatch.setattr(rc, "wait_for_version", lambda slug, version, timeout: None)
        monkeypatch.setattr(rc, "check_verdict", lambda slug, version: {"security": {"summary": "fine"}})
        assert rc.main(["check-whoami", "--expect", "me"]) == 0
        assert rc.main(["wait-for-version", "--slug", "s", "--version", "1.0.0"]) == 0
        assert rc.main(["check-verdict", "--slug", "s", "--version", "1.0.0"]) == 0
        out = capsys.readouterr().out
        assert "Authenticated as me" in out and "latest version on ClawHub" in out and "fine" in out
