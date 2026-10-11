"""Tests for setup_cron.py — cron job management for Apple Music DJ."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import setup_cron as sc


def confirm_for(defs, names):
    """The digest `install --dry-run` would print for these jobs (what --confirm must equal)."""
    return sc.install_digest([sc.format_cron_line(defs[n], n) for n in names])


# ── build_job_defs ───────────────────────────────────────────────

class TestBuildJobDefs:
    def test_returns_all_four_jobs(self):
        defs = sc.build_job_defs("/usr/bin/python3", "/path/profile.json", "us", "/tmp/logs")
        assert set(defs.keys()) == {"weekly-mix", "new-releases", "daily-drop", "health-check", "monthly-drift"}

    def test_each_job_has_required_keys(self):
        defs = sc.build_job_defs("/usr/bin/python3", "/path/profile.json", "us", "/tmp/logs")
        for job in defs.values():
            assert "description" in job
            assert "schedule" in job
            assert "command" in job
            assert "log" in job

    def test_uses_python_path(self):
        defs = sc.build_job_defs("/custom/python", "/path/profile.json", "us", "/tmp/logs")
        assert "/custom/python" in defs["weekly-mix"]["command"]

    def test_uses_storefront(self):
        defs = sc.build_job_defs("/usr/bin/python3", "/path/profile.json", "gb", "/tmp/logs")
        assert "gb" in defs["new-releases"]["command"]

    def test_uses_log_dir(self):
        defs = sc.build_job_defs("/usr/bin/python3", "/path/profile.json", "us", "/var/log/music")
        for job in defs.values():
            assert job["log"].startswith("/var/log/music/")


# ── format_cron_line ─────────────────────────────────────────────

class TestFormatCronLine:
    def test_includes_schedule_and_command(self):
        job = {"schedule": "0 7 * * 1", "command": "echo hello", "log": "/tmp/test.log"}
        line = sc.format_cron_line(job, "test-job")
        assert line.startswith("0 7 * * 1 umask 077; echo hello")

    def test_includes_marker(self):
        job = {"schedule": "0 7 * * 1", "command": "echo hello", "log": "/tmp/test.log"}
        line = sc.format_cron_line(job, "test-job")
        assert "# apple-music-dj:test-job" in line

    def test_includes_log_redirect(self):
        job = {"schedule": "0 7 * * 1", "command": "echo hello", "log": "/tmp/test.log"}
        line = sc.format_cron_line(job, "test-job")
        assert ">> /tmp/test.log 2>&1" in line


# ── get_current_crontab ─────────────────────────────────────────

class TestGetCurrentCrontab:
    def test_returns_crontab_content(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(
            returncode=0, stdout="* * * * * echo hi\n"
        ))
        assert sc.get_current_crontab() == "* * * * * echo hi\n"

    def test_returns_empty_on_failure(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(
            returncode=1, stdout=""
        ))
        assert sc.get_current_crontab() == ""

    def test_exits_on_missing_crontab(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", MagicMock(side_effect=FileNotFoundError))
        with pytest.raises(SystemExit):
            sc.get_current_crontab()


# ── set_crontab ──────────────────────────────────────────────────

class TestSetCrontab:
    def test_returns_true_on_success(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
        assert sc.set_crontab("content") is True

    def test_returns_false_on_failure(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=1))
        assert sc.set_crontab("content") is False

    def test_returns_false_on_missing_crontab(self, monkeypatch):
        monkeypatch.setattr("subprocess.run", MagicMock(side_effect=FileNotFoundError))
        assert sc.set_crontab("content") is False


# ── get_installed_jobs ───────────────────────────────────────────

class TestGetInstalledJobs:
    def test_extracts_job_names(self, monkeypatch):
        crontab = "0 7 * * 1 cmd1 # apple-music-dj:weekly-mix\n0 8 * * 3 cmd2 # apple-music-dj:new-releases\n"
        monkeypatch.setattr(sc, "get_current_crontab", lambda: crontab)
        jobs = sc.get_installed_jobs()
        assert "weekly-mix" in jobs
        assert "new-releases" in jobs

    def test_ignores_non_marker_lines(self, monkeypatch):
        crontab = "0 7 * * 1 some-other-job\n0 8 * * 3 cmd2 # apple-music-dj:daily-drop\n"
        monkeypatch.setattr(sc, "get_current_crontab", lambda: crontab)
        jobs = sc.get_installed_jobs()
        assert jobs == ["daily-drop"]

    def test_empty_crontab(self, monkeypatch):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        assert sc.get_installed_jobs() == []


# ── cmd_list ─────────────────────────────────────────────────────

class TestCmdList:
    def test_prints_job_info(self, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_installed_jobs", lambda: ["weekly-mix"])
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", "/tmp")
        sc.cmd_list(defs)
        captured = capsys.readouterr()
        assert "weekly-mix" in captured.out
        assert "✅ installed" in captured.out
        assert "⬚ not installed" in captured.out


# ── cmd_install ──────────────────────────────────────────────────

class TestCmdInstall:
    def test_installs_selected_jobs(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        set_calls = []
        monkeypatch.setattr(sc, "set_crontab", lambda c: (set_calls.append(c), True)[-1])
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", str(tmp_path))
        sc.cmd_install(defs, ["weekly-mix"], str(tmp_path), confirm=confirm_for(defs, ["weekly-mix"]))
        assert len(set_calls) == 1
        assert "weekly-mix" in set_calls[0]

    def test_replaces_existing_job(self, monkeypatch, tmp_path, capsys):
        existing = "0 7 * * 1 old-cmd # apple-music-dj:weekly-mix\n"
        monkeypatch.setattr(sc, "get_current_crontab", lambda: existing)
        set_calls = []
        monkeypatch.setattr(sc, "set_crontab", lambda c: (set_calls.append(c), True)[-1])
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", str(tmp_path))
        sc.cmd_install(defs, ["weekly-mix"], str(tmp_path), confirm=confirm_for(defs, ["weekly-mix"]))
        # Should have replaced — only one weekly-mix line
        lines = [ln for ln in set_calls[0].splitlines() if "weekly-mix" in ln]
        assert len(lines) == 1
        assert "old-cmd" not in set_calls[0]

    def test_warns_about_unknown_jobs_but_installs_the_known_ones(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        set_calls = []
        monkeypatch.setattr(sc, "set_crontab", lambda c: (set_calls.append(c), True)[-1])
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", str(tmp_path))
        sc.cmd_install(defs, ["nonexistent-job", "weekly-mix"], str(tmp_path),
                       confirm=confirm_for(defs, ["weekly-mix"]))
        assert "Unknown job 'nonexistent-job'" in capsys.readouterr().err
        assert len(set_calls) == 1 and "weekly-mix" in set_calls[0]

    def test_only_unknown_jobs_is_an_error(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", str(tmp_path))
        with pytest.raises(SystemExit) as e:
            sc.cmd_install(defs, ["nonexistent-job"], str(tmp_path), confirm="0" * 12)
        assert e.value.code == 1 and "No valid jobs selected" in capsys.readouterr().err

    def test_exits_on_set_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        monkeypatch.setattr(sc, "set_crontab", lambda c: False)
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", str(tmp_path))
        with pytest.raises(SystemExit) as e:
            sc.cmd_install(defs, ["weekly-mix"], str(tmp_path), confirm=confirm_for(defs, ["weekly-mix"]))
        assert e.value.code == 1


# ── cmd_remove ───────────────────────────────────────────────────

class TestCmdRemove:
    def test_removes_job(self, monkeypatch, capsys):
        existing = "0 7 * * 1 cmd # apple-music-dj:weekly-mix\n0 8 * * 3 cmd2 # apple-music-dj:new-releases\n"
        monkeypatch.setattr(sc, "get_current_crontab", lambda: existing)
        set_calls = []
        monkeypatch.setattr(sc, "set_crontab", lambda c: (set_calls.append(c), True)[-1])
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", "/tmp")
        sc.cmd_remove(defs, ["weekly-mix"])
        assert "weekly-mix" not in set_calls[0]
        assert "new-releases" in set_calls[0]

    def test_no_matching_jobs(self, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", "/tmp")
        sc.cmd_remove(defs, ["weekly-mix"])
        captured = capsys.readouterr()
        assert "No matching" in captured.out

    def test_exits_on_set_failure(self, monkeypatch):
        existing = "0 7 * * 1 cmd # apple-music-dj:weekly-mix\n"
        monkeypatch.setattr(sc, "get_current_crontab", lambda: existing)
        monkeypatch.setattr(sc, "set_crontab", lambda c: False)
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", "/tmp")
        with pytest.raises(SystemExit):
            sc.cmd_remove(defs, ["weekly-mix"])


# ── cmd_status ───────────────────────────────────────────────────

class TestCmdStatus:
    def test_shows_installed_jobs(self, monkeypatch, capsys):
        crontab = "0 7 * * 1 cmd # apple-music-dj:weekly-mix\n"
        monkeypatch.setattr(sc, "get_installed_jobs", lambda: ["weekly-mix"])
        monkeypatch.setattr(sc, "get_current_crontab", lambda: crontab)
        sc.cmd_status()
        captured = capsys.readouterr()
        assert "1" in captured.out
        assert "weekly-mix" in captured.out

    def test_shows_none_when_empty(self, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_installed_jobs", lambda: [])
        sc.cmd_status()
        captured = capsys.readouterr()
        assert "No apple-music-dj" in captured.out


# ── main ─────────────────────────────────────────────────────────

class TestMain:
    def test_main_status(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", "status"])
        monkeypatch.setattr("setup_cron.load_config", lambda: {})
        monkeypatch.setattr(sc, "get_installed_jobs", lambda: [])
        sc.main()
        captured = capsys.readouterr()
        assert "No apple-music-dj" in captured.out

    def test_main_list(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", "list"])
        monkeypatch.setattr("setup_cron.load_config", lambda: {})
        monkeypatch.setattr(sc, "get_installed_jobs", lambda: [])
        sc.main()
        captured = capsys.readouterr()
        assert "weekly-mix" in captured.out

    def test_main_install(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sys, "argv", [
            "setup_cron.py", "install", "--jobs", "weekly-mix",
            "--log-dir", str(tmp_path),
        ])
        monkeypatch.setattr("setup_cron.load_config", lambda: {})
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        installed = []
        monkeypatch.setattr(sc, "set_crontab", lambda c: (installed.append(c), True)[-1])
        # Review first (a dry run prints the digest), then install exactly what was reviewed
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", "install", "--jobs", "weekly-mix",
                                          "--log-dir", str(tmp_path), "--dry-run"])
        sc.main()
        digest = next(ln.split()[-1] for ln in capsys.readouterr().out.splitlines() if ln.startswith("Digest:"))
        assert installed == []
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", "install", "--jobs", "weekly-mix",
                                          "--log-dir", str(tmp_path), "--confirm", digest])
        sc.main()
        assert len(installed) == 1 and "weekly-mix" in installed[0]

    def test_main_remove(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", "remove", "--jobs", "weekly-mix"])
        monkeypatch.setattr("setup_cron.load_config", lambda: {})
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        sc.main()
        captured = capsys.readouterr()
        assert "No matching" in captured.out


class TestCommandQuoting:
    def _all(self, python="/usr/bin/python3", profile="/p/profile.json", sf="us"):
        return sc.build_job_defs(python, profile, sf, "/tmp/logs")

    def test_plain_values_are_unchanged(self):
        defs = self._all()
        assert "/usr/bin/python3" in defs["weekly-mix"]["command"]
        assert "--profile /p/profile.json " in defs["weekly-mix"]["command"]

    def test_paths_with_spaces_stay_one_argument(self):
        import shlex
        defs = self._all(python="/my python/bin/python3", profile="/Users/Jane Doe/.apple-music-dj/profile.json")
        for name, job in defs.items():
            inner = job["command"].strip("()")
            for chunk in inner.split("&&"):
                argv = shlex.split(chunk)
                assert "/Users/Jane Doe/.apple-music-dj/profile.json" in argv or name == "new-releases", name
                assert argv[0] in ("/my python/bin/python3", "bash"), (name, argv[0])

    def test_shell_metacharacters_are_not_interpreted(self):
        import shlex
        evil = "/tmp/x; touch /tmp/pwned #"
        for job in self._all(profile=evil).values():
            for chunk in job["command"].strip("()").split(" && "):
                assert "; touch /tmp/pwned #" not in [t for t in shlex.split(chunk) if t != evil]

    def test_drift_job_quotes_both_commands(self):
        job = self._all(profile="/a b/profile.json")["monthly-drift"]
        assert job["command"].count("'/a b/profile.json'") == 2


class TestMonthlyDrift:
    def test_is_optional_and_logs_both_commands(self):
        defs = sc.build_job_defs("/usr/bin/python3", "/p/profile.json", "us", "/tmp/logs")
        job = defs["monthly-drift"]
        assert job["optional"] is True
        assert "taste_profiler.py" in job["command"] and "taste_drift.py" in job["command"]
        line = sc.format_cron_line(job, "monthly-drift")
        # Subshell so the log redirect covers both commands
        assert "umask 077; (" in line and ") >> " in line

    def test_other_jobs_not_optional(self):
        defs = sc.build_job_defs("/usr/bin/python3", "/p.json", "us", "/tmp")
        assert [n for n, j in defs.items() if j.get("optional")] == ["monthly-drift"]

    def test_list_marks_opt_in(self, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_installed_jobs", lambda: [])
        sc.cmd_list(sc.build_job_defs("/usr/bin/python3", "/p.json", "us", "/tmp"))
        assert "opt-in" in capsys.readouterr().out


# ── Security audit: validation, log privacy, dry run ─────────────

import os
import stat


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class TestValidation:
    @pytest.mark.parametrize("bad", ["", "   ", "/tmp/a\nb", "/tmp/a\rb", "/tmp/a\x00b", "/tmp/50%off", "/tmp/a\tb"])
    def test_validate_path_rejects_line_breaking_input(self, bad):
        with pytest.raises(ValueError):
            sc.validate_path(bad, "--profile")

    def test_validate_path_normalizes(self, monkeypatch):
        monkeypatch.setenv("HOME", "/home/jane")
        assert sc.validate_path("~/x/../profile.json", "--profile") == "/home/jane/profile.json"
        assert sc.validate_path("/a/b c/p.json", "--profile") == "/a/b c/p.json"

    @pytest.mark.parametrize("ok", ["us", "gb", "auto"])
    def test_storefront_ok(self, ok):
        assert sc.validate_storefront(ok) == ok

    @pytest.mark.parametrize("bad", ["", "USA", "u", "us; rm -rf ~", "us\nus", "$(id)", "u1"])
    def test_storefront_rejected(self, bad):
        with pytest.raises(ValueError):
            sc.validate_storefront(bad)

    def test_python_must_be_an_executable_file(self, tmp_path):
        exe = tmp_path / "py"
        exe.write_text("#!/bin/sh\n")
        with pytest.raises(ValueError, match="not an executable file"):
            sc.validate_python(str(exe))
        exe.chmod(0o755)
        assert sc.validate_python(str(exe)) == str(exe)
        with pytest.raises(ValueError):
            sc.validate_python(str(tmp_path / "missing"))

    @pytest.mark.parametrize("bad", ["weekly mix", "Weekly", "a;b", "x$(id)", "-x", "a" * 40])
    def test_job_names_rejected(self, bad):
        with pytest.raises(ValueError):
            sc.validate_job_names(bad)

    def test_job_names_ok(self):
        assert sc.validate_job_names("weekly-mix, daily-drop,") == ["weekly-mix", "daily-drop"]


class TestCronLineSafety:
    def _job(self, **kw):
        return {"schedule": "0 7 * * 1", "command": "echo hi", "log": "/tmp/x.log", **kw}

    def test_log_path_is_quoted(self):
        line = sc.format_cron_line(self._job(log="/tmp/my logs/x.log"), "j")
        assert ">> '/tmp/my logs/x.log' 2>&1" in line

    def test_log_path_cannot_inject_commands(self):
        import shlex
        line = sc.format_cron_line(self._job(log="/tmp/x.log; touch /tmp/pwned #"), "j")
        redirect = line.split(" >> ", 1)[1]
        assert shlex.split(redirect)[0] == "/tmp/x.log; touch /tmp/pwned #"

    def test_job_runs_with_private_umask(self):
        assert " umask 077; " in sc.format_cron_line(self._job(), "j")

    @pytest.mark.parametrize("field", ["command", "log"])
    @pytest.mark.parametrize("bad", ["a\nb", "a\rb", "50%", "a\x00b"])
    def test_refuses_to_build_a_line_that_could_split_or_be_rewritten_by_cron(self, field, bad):
        with pytest.raises(ValueError, match="Refusing"):
            sc.format_cron_line(self._job(**{field: bad}), "j")

    def test_every_real_job_formats_cleanly(self):
        for name, job in sc.build_job_defs("/usr/bin/python3", "/p/profile.json", "us", "/tmp/logs").items():
            line = sc.format_cron_line(job, name)
            assert "\n" not in line and "%" not in line


class TestPrepareLogs:
    def test_creates_private_dir_and_files(self, tmp_path):
        log_dir = tmp_path / "a" / "b" / "logs"
        logs = [str(log_dir / "one.log"), str(log_dir / "two.log")]
        sc.prepare_logs(str(log_dir), logs)
        assert _mode(log_dir) == 0o700 and _mode(log_dir.parent) == 0o700
        assert all(_mode(p) == 0o600 for p in logs)

    def test_tightens_a_preexisting_world_readable_log_and_keeps_content(self, tmp_path):
        log = tmp_path / "old.log"
        log.write_text("earlier run\n")
        log.chmod(0o644)
        sc.prepare_logs(str(tmp_path), [str(log)])
        assert _mode(log) == 0o600 and log.read_text() == "earlier run\n"

    def test_rejects_symlinked_directory(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        with pytest.raises(ValueError, match="symlink"):
            sc.prepare_logs(str(link), [str(link / "x.log")])
        assert list(real.iterdir()) == []

    def test_rejects_symlinked_log_file_without_touching_target(self, tmp_path):
        target = tmp_path / "victim.txt"
        target.write_text("keep me")
        target.chmod(0o644)
        (tmp_path / "x.log").symlink_to(target)
        with pytest.raises(ValueError, match="symlink"):
            sc.prepare_logs(str(tmp_path), [str(tmp_path / "x.log")])
        assert target.read_text() == "keep me" and _mode(target) == 0o644

    def test_rejects_directory_other_users_can_write(self, tmp_path):
        d = tmp_path / "shared"
        d.mkdir()
        d.chmod(0o777)
        with pytest.raises(ValueError, match="writable by other users"):
            sc.prepare_logs(str(d), [str(d / "x.log")])

    def test_rejects_directory_owned_by_someone_else(self, tmp_path, monkeypatch):
        monkeypatch.setattr(os, "getuid", lambda: os.stat(tmp_path).st_uid + 1)
        with pytest.raises(ValueError, match="owned by another user"):
            sc.prepare_logs(str(tmp_path), [str(tmp_path / "x.log")])

    def test_rejects_log_path_that_is_a_directory(self, tmp_path):
        (tmp_path / "x.log").mkdir()
        with pytest.raises(OSError):
            sc.prepare_logs(str(tmp_path), [str(tmp_path / "x.log")])

    def test_logs_inside_the_app_dir_tighten_the_app_dir_itself(self, tmp_path, monkeypatch):
        import _common
        app = tmp_path / ".apple-music-dj"
        app.mkdir()
        app.chmod(0o755)
        monkeypatch.setattr(_common, "APP_DIR", app)
        monkeypatch.setattr(sc, "DEFAULT_LOG_DIR", app / "logs")
        sc.prepare_logs(str(app / "logs"), [str(app / "logs" / "x.log")])
        assert _mode(app) == 0o700 and _mode(app / "logs") == 0o700

    def test_default_log_dir_is_tightened_but_foreign_dirs_are_not(self, tmp_path, monkeypatch):
        mine = tmp_path / "app"
        mine.mkdir()
        mine.chmod(0o755)
        monkeypatch.setattr(sc, "DEFAULT_LOG_DIR", mine)
        sc.prepare_logs(str(mine), [str(mine / "x.log")])
        assert _mode(mine) == 0o700
        other = tmp_path / "custom"
        other.mkdir()
        other.chmod(0o755)
        sc.prepare_logs(str(other), [str(other / "x.log")])
        assert _mode(other) == 0o755  # user-chosen dir: only the files are locked down
        assert _mode(other / "x.log") == 0o600


class TestInstallSafety:
    def _defs(self, log_dir):
        return sc.build_job_defs("/usr/bin/python3", "/p/profile.json", "us", str(log_dir))

    def test_dry_run_prints_exact_lines_and_changes_nothing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        log_dir = tmp_path / "logs"
        defs = self._defs(log_dir)
        sc.cmd_install(defs, ["weekly-mix", "daily-drop"], str(log_dir), dry_run=True)
        out = capsys.readouterr().out
        assert sc.format_cron_line(defs["weekly-mix"], "weekly-mix") in out
        assert sc.format_cron_line(defs["daily-drop"], "daily-drop") in out
        assert "nothing was changed" in out
        assert not log_dir.exists()

    def test_install_creates_private_logs_before_writing_crontab(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        seen = {}

        def fake_set(content):
            seen["files"] = {p.name: _mode(p) for p in log_dir.iterdir()}
            return True

        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        monkeypatch.setattr(sc, "set_crontab", fake_set)
        defs = self._defs(log_dir)
        sc.cmd_install(defs, ["weekly-mix"], str(log_dir), confirm=confirm_for(defs, ["weekly-mix"]))
        assert seen["files"] == {"weekly-mix.log": 0o600} and _mode(log_dir) == 0o700

    def test_install_aborts_without_touching_crontab_on_unsafe_log_dir(self, tmp_path, monkeypatch, capsys):
        target = tmp_path / "real"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target)
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        defs = self._defs(link)
        with pytest.raises(SystemExit):
            sc.cmd_install(defs, ["weekly-mix"], str(link), confirm=confirm_for(defs, ["weekly-mix"]))
        assert "symlink" in capsys.readouterr().err

    def test_unknown_jobs_do_not_create_log_files(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        monkeypatch.setattr(sc, "set_crontab", lambda c: True)
        defs = self._defs(log_dir)
        sc.cmd_install(defs, ["nonexistent-job", "weekly-mix"], str(log_dir),
                       confirm=confirm_for(defs, ["weekly-mix"]))
        assert [p.name for p in log_dir.iterdir()] == ["weekly-mix.log"]


class TestMainRejectsUnsafeInput:
    def _run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", *argv])
        monkeypatch.setattr(sc, "load_config", lambda: {})
        sc.main()

    @pytest.mark.parametrize("argv", [
        ["install", "--storefront", "us; touch /tmp/pwned"],
        ["install", "--profile", "/tmp/a\nb"],
        ["install", "--log-dir", "/tmp/50%"],
        ["install", "--python", "/definitely/not/python"],
        ["install", "--jobs", "weekly-mix;reboot"],
        ["list", "--storefront", "$(id)"],
    ])
    def test_exits_before_touching_crontab(self, monkeypatch, capsys, argv):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        with pytest.raises(SystemExit) as e:
            self._run(monkeypatch, *argv)
        assert e.value.code == 1 and "ERROR:" in capsys.readouterr().err

    @pytest.mark.parametrize("jobs", ["", " ", ",", " , ,"])
    @pytest.mark.parametrize("command", ["install", "remove", "list"])
    def test_explicit_empty_jobs_is_rejected_not_treated_as_all(self, monkeypatch, capsys, command, jobs):
        """`--jobs ''` used to fall back to every default job — and `remove` removed them all."""
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        with pytest.raises(SystemExit) as e:
            self._run(monkeypatch, command, "--jobs", jobs)
        assert e.value.code == 1 and "names no jobs" in capsys.readouterr().err

    @pytest.mark.parametrize("command", ["install", "remove"])
    def test_unknown_job_names_are_rejected_up_front(self, monkeypatch, capsys, command):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        with pytest.raises(SystemExit) as e:
            self._run(monkeypatch, command, "--jobs", "weekly-mix,not-a-job")
        err = capsys.readouterr().err
        assert e.value.code == 1 and "Unknown job(s): not-a-job" in err and "weekly-mix" in err

    def test_remove_without_jobs_still_means_all(self, monkeypatch):
        removed = {}
        monkeypatch.setattr(sc, "cmd_remove", lambda defs, selected: removed.setdefault("sel", selected))
        self._run(monkeypatch, "remove")
        assert set(removed["sel"]) == set(sc.build_job_defs("/x", "/p", "us", "/l"))

    def test_dry_run_flag_via_cli(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        self._run(monkeypatch, "install", "--dry-run", "--log-dir", str(tmp_path / "l"),
                  "--profile", str(tmp_path / "p.json"))
        out = capsys.readouterr().out
        assert "weekly-mix" in out and "umask 077;" in out and not (tmp_path / "l").exists()


# ── Enforced confirmation (the code, not just the docs, requires review) ─────

class TestEnforcedConfirmation:
    def _defs(self, tmp_path, profile="/p/profile.json", sf="us"):
        return sc.build_job_defs("/usr/bin/python3", profile, sf, str(tmp_path / "logs"))

    def test_digest_is_short_hex_deterministic_and_order_insensitive(self):
        d = sc.install_digest(["a", "b"])
        assert len(d) == 12 and int(d, 16) >= 0
        assert d == sc.install_digest(["a", "b"]) == sc.install_digest(["b", "a"])

    def test_digest_changes_with_anything_that_changes_the_installed_lines(self, tmp_path):
        names = ["weekly-mix"]
        base = confirm_for(self._defs(tmp_path), names)
        assert confirm_for(self._defs(tmp_path, profile="/other/profile.json"), names) != base
        assert confirm_for(self._defs(tmp_path, sf="gb"), names) != base
        assert confirm_for(self._defs(tmp_path), ["weekly-mix", "daily-drop"]) != base
        assert confirm_for(self._defs(tmp_path / "elsewhere"), names) != base  # log path is in the line

    def test_install_without_confirm_changes_nothing_and_exits_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        defs = self._defs(tmp_path)
        with pytest.raises(SystemExit) as e:
            sc.cmd_install(defs, ["weekly-mix"], str(tmp_path / "logs"))
        cap = capsys.readouterr()
        assert e.value.code == 2
        assert sc.format_cron_line(defs["weekly-mix"], "weekly-mix") in cap.out
        assert f"--confirm {confirm_for(defs, ['weekly-mix'])}" in cap.out
        assert "Nothing was installed" in cap.err
        assert not (tmp_path / "logs").exists()

    def test_wrong_digest_is_rejected(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        defs = self._defs(tmp_path)
        with pytest.raises(SystemExit) as e:
            sc.cmd_install(defs, ["weekly-mix"], str(tmp_path / "logs"), confirm="0" * 12)
        assert e.value.code == 1 and "doesn't match" in capsys.readouterr().err
        assert not (tmp_path / "logs").exists()

    def test_digest_for_other_jobs_cannot_be_replayed(self, tmp_path, monkeypatch):
        """Approving weekly-mix must not authorize installing something else."""
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        defs = self._defs(tmp_path)
        approved = confirm_for(defs, ["weekly-mix"])
        with pytest.raises(SystemExit):
            sc.cmd_install(defs, ["daily-drop"], str(tmp_path / "logs"), confirm=approved)
        with pytest.raises(SystemExit):
            sc.cmd_install(self._defs(tmp_path, profile="/evil/profile.json"), ["weekly-mix"],
                           str(tmp_path / "logs"), confirm=approved)

    def test_correct_digest_installs_case_and_whitespace_insensitive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        installed = []
        monkeypatch.setattr(sc, "set_crontab", lambda c: (installed.append(c), True)[-1])
        defs = self._defs(tmp_path)
        digest = confirm_for(defs, ["weekly-mix"])
        sc.cmd_install(defs, ["weekly-mix"], str(tmp_path / "logs"), confirm=f"  {digest.upper()} ")
        assert len(installed) == 1

    def test_dry_run_wins_even_with_a_confirm(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        defs = self._defs(tmp_path)
        sc.cmd_install(defs, ["weekly-mix"], str(tmp_path / "logs"), dry_run=True,
                       confirm=confirm_for(defs, ["weekly-mix"]))
        assert "nothing was changed" in capsys.readouterr().out

    def test_cli_bare_install_exits_2_and_install_with_confirm_works(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sc, "load_config", lambda: {})
        installed = []
        monkeypatch.setattr(sc, "get_current_crontab", lambda: "")
        monkeypatch.setattr(sc, "set_crontab", lambda c: (installed.append(c), True)[-1])
        args = ["install", "--jobs", "weekly-mix,daily-drop", "--log-dir", str(tmp_path / "l"),
                "--profile", str(tmp_path / "p.json")]
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", *args])
        with pytest.raises(SystemExit) as e:
            sc.main()
        assert e.value.code == 2 and installed == []
        digest = next(ln.split()[-1] for ln in capsys.readouterr().out.splitlines() if ln.startswith("Digest:"))
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", *args, "--confirm", digest])
        sc.main()
        assert len(installed) == 1 and "weekly-mix" in installed[0] and "daily-drop" in installed[0]

    @pytest.mark.parametrize("bad", ["", "abc", "z" * 12, "0" * 11, "0" * 13, "$(id)"])
    def test_cli_rejects_malformed_confirm_before_touching_anything(self, tmp_path, monkeypatch, capsys, bad):
        monkeypatch.setattr(sc, "load_config", lambda: {})
        monkeypatch.setattr(sc, "get_current_crontab", lambda: pytest.fail("must not read crontab"))
        monkeypatch.setattr(sc, "set_crontab", lambda c: pytest.fail("must not write crontab"))
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", "install", "--confirm", bad,
                                          "--log-dir", str(tmp_path / "l")])
        with pytest.raises(SystemExit) as e:
            sc.main()
        assert e.value.code == 1 and "12-character digest" in capsys.readouterr().err

    def test_remove_still_needs_no_confirmation(self, monkeypatch):
        removed = {}
        monkeypatch.setattr(sc, "load_config", lambda: {})
        monkeypatch.setattr(sc, "cmd_remove", lambda defs, selected: removed.setdefault("sel", selected))
        monkeypatch.setattr(sys, "argv", ["setup_cron.py", "remove", "--jobs", "weekly-mix"])
        sc.main()
        assert removed["sel"] == ["weekly-mix"]


class TestJobArguments:
    """new-releases and daily-drop passed the wrong arguments and failed silently from v3.0 until 3.2.3."""

    def _defs(self):
        return sc.build_job_defs("/usr/bin/python3", "/p/profile.json", "gb", "/tmp/logs")

    def test_new_releases_gets_profile_then_storefront(self):
        import shlex
        argv = shlex.split(self._defs()["new-releases"]["command"])
        assert argv[0] == "bash" and argv[1].endswith("new_releases.sh")
        assert argv[2:] == ["/p/profile.json", "gb"]
        assert "--create-playlist" not in argv  # the scheduled job reports; it doesn't write

    def test_daily_drop_gets_positional_profile_then_storefront(self):
        import shlex
        argv = shlex.split(self._defs()["daily-drop"]["command"])
        assert argv[1].endswith("daily_pick.py") and argv[2] == "daily"
        assert argv[3:] == ["/p/profile.json", "gb"]
        assert "--profile" not in argv  # daily_pick.py has no such option

    def test_every_job_script_exists(self):
        import shlex
        for name, job in self._defs().items():
            scripts = [t for t in shlex.split(job["command"].strip("()").split("&&")[0]) if t.endswith((".py", ".sh"))]
            assert scripts and all(Path(t).is_file() for t in scripts), name
