"""Tests for demo.py: the no-tokens tour and the `run` sandbox around the real scripts."""

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import demo

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "demo.py"

needs_tools = pytest.mark.skipif(not (shutil.which("curl") and shutil.which("jq") and shutil.which("bash")),
                                 reason="needs curl, jq and bash")


class TestMain:
    @pytest.fixture(autouse=True)
    def sandbox(self, monkeypatch, tmp_path):
        home = tmp_path / "home"
        real_data = home / ".apple-music-dj"
        real_data.mkdir(parents=True)
        (real_data / "sentinel.json").write_text('{"synthetic": true}', encoding="utf-8")
        monkeypatch.setattr(demo, "DEMO_HOME", home / ".apple-music-dj-demo")
        monkeypatch.setattr(demo, "REAL_APP_DIR", real_data)

    @pytest.mark.parametrize(("argv", "handler_name", "args"), [
        (["tour"], "cmd_tour", ()),
        (["serve"], "cmd_serve", (8765,)),
        (["serve", "--port", "1234"], "cmd_serve", (1234,)),
    ])
    def test_dispatches_tour_and_serve_and_returns_the_handler_status(
        self, monkeypatch, argv, handler_name, args
    ):
        handler = Mock(return_value=7)
        monkeypatch.setattr(demo, handler_name, handler)
        monkeypatch.setattr(sys, "argv", ["demo.py", *argv])

        assert demo.main() == 7
        handler.assert_called_once_with(*args)

    @pytest.mark.parametrize("use_profile", [False, True])
    def test_run_forwards_arguments_substitutes_the_profile_and_stops_the_server(
        self, monkeypatch, use_profile
    ):
        server = SimpleNamespace(url="http://127.0.0.1:1", stop=Mock())
        monkeypatch.setattr(demo, "start_server", Mock(return_value=server))
        ensure_profile = Mock()
        monkeypatch.setattr(demo, "ensure_profile", ensure_profile)
        runner = Mock(return_value=subprocess.CompletedProcess([], 4))
        monkeypatch.setattr(demo, "_run", runner)
        arguments = ["now", "DEMO_PROFILE", "gb"] if use_profile else ["--help"]
        monkeypatch.setattr(sys, "argv", ["demo.py", "run", "daily_pick.py", *arguments])

        assert demo.main() == 4

        command, env = runner.call_args.args
        expected_args = ["now", str(demo.demo_profile_path()), "gb"] if use_profile else ["--help"]
        assert command == [sys.executable, str(demo.SCRIPT_DIR / "daily_pick.py"), *expected_args]
        assert env["HOME"] == str(demo.DEMO_HOME)
        assert env["APPLE_MUSIC_API_BASE"] == server.url and env["APPLE_MUSIC_DJ_DEMO"] == "1"
        assert runner.call_count == 1
        if use_profile:
            ensure_profile.assert_called_once_with(env)
        else:
            ensure_profile.assert_not_called()
        server.stop.assert_called_once_with()

    @pytest.mark.parametrize("script", ["setup_cron.py", "setup_auth.py"])
    def test_run_refuses_cron_and_auth_before_starting_a_server_or_child(self, monkeypatch, script):
        server = Mock()
        runner = Mock()
        monkeypatch.setattr(demo, "start_server", server)
        monkeypatch.setattr(demo, "_run", runner)
        monkeypatch.setattr(sys, "argv", ["demo.py", "run", script])

        with pytest.raises(SystemExit, match="can't run in demo mode"):
            demo.main()

        server.assert_not_called()
        runner.assert_not_called()
        assert not demo.DEMO_HOME.exists()
        assert (demo.REAL_APP_DIR / "sentinel.json").read_text(encoding="utf-8") == '{"synthetic": true}'

    @pytest.mark.parametrize("form", ["positional", "separate", "equals"])
    def test_run_refuses_account_paths_before_starting_a_server_or_child(self, monkeypatch, form):
        path = str(demo.REAL_APP_DIR / "sentinel.json")
        args = {"positional": [path], "separate": ["--output", path], "equals": [f"--output={path}"]}[form]
        server = Mock()
        runner = Mock()
        monkeypatch.setattr(demo, "start_server", server)
        monkeypatch.setattr(demo, "_run", runner)
        monkeypatch.setattr(sys, "argv", ["demo.py", "run", "taste_card.py", *args])

        with pytest.raises(SystemExit, match="real data"):
            demo.main()

        server.assert_not_called()
        runner.assert_not_called()
        assert not demo.DEMO_HOME.exists()
        assert (demo.REAL_APP_DIR / "sentinel.json").read_text(encoding="utf-8") == '{"synthetic": true}'

    def test_reset_removes_only_the_synthetic_demo_folder(self, monkeypatch, capsys):
        demo.DEMO_HOME.mkdir()
        (demo.DEMO_HOME / "demo.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["demo.py", "reset"])

        assert demo.main() == 0
        assert f"Removed {demo.DEMO_HOME}" in capsys.readouterr().out
        assert not demo.DEMO_HOME.exists()
        assert (demo.REAL_APP_DIR / "sentinel.json").read_text(encoding="utf-8") == '{"synthetic": true}'
        assert demo.main() == 0
        assert "No demo data to remove" in capsys.readouterr().out


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def run_demo(home, *args, env_extra=None):
    import os
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1", **(env_extra or {})}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=120)


def test_mock_server_skips_the_reverse_dns_lookup(monkeypatch):
    """HTTPServer.server_bind calls socket.getfqdn(), which hangs ~35 s on some macOS setups."""
    def no_lookup(*_args):
        raise AssertionError("socket.getfqdn() called")
    monkeypatch.setattr(demo.socketserver.socket, "getfqdn", no_lookup)
    demo.MockAppleMusic().start().stop()


class TestSandbox:
    def test_env_drops_real_apple_credentials(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "REAL")
        monkeypatch.setenv("APPLE_PRIVATE_KEY_PATH", "/secret.p8")
        env = demo.demo_env("http://127.0.0.1:1")
        assert env["APPLE_MUSIC_USER_TOKEN"] == "demo-user-token" and "APPLE_PRIVATE_KEY_PATH" not in env
        assert env["HOME"] == str(demo.DEMO_HOME) and env["APPLE_MUSIC_DJ_DEMO"] == "1"

    @pytest.mark.parametrize("name", ["setup_cron.py", "setup_auth.py", "../x.py", "/bin/sh", "nope.py", "demo.py"])
    def test_only_plain_skill_scripts_run(self, name):
        with pytest.raises(SystemExit, match="can't run in demo mode"):
            demo.script_command(name)

    def test_real_data_paths_are_refused(self):
        with pytest.raises(SystemExit, match="real data"):
            demo.check_args([f"--output={demo.REAL_APP_DIR}/taste_profile.json"])
        assert demo.check_args([str(demo.DEMO_HOME)]) == [str(demo.DEMO_HOME)]  # the sibling demo dir is fine

    def test_dotdot_and_symlink_aliases_into_real_data_are_refused(self, tmp_path, monkeypatch):
        real = tmp_path / "home" / ".apple-music-dj"
        real.mkdir(parents=True)
        demo_home = tmp_path / "home" / ".apple-music-dj-demo"
        monkeypatch.setattr(demo, "REAL_APP_DIR", real)
        monkeypatch.setattr(demo, "DEMO_HOME", demo_home)
        alias = tmp_path / "alias"
        alias.symlink_to(real)
        for arg in (f"{demo_home}/../.apple-music-dj/taste_profile.json",
                    f"--output={demo_home}/../.apple-music-dj/x.json", str(alias / "x.json")):
            with pytest.raises(SystemExit, match="real data"):
                demo.check_args([arg])
        assert demo.check_args(["--size", "8", "Radiohead"]) == ["--size", "8", "Radiohead"]

    @pytest.mark.parametrize("which", ["home", "inner"])
    def test_symlinked_sandbox_is_refused(self, tmp_path, monkeypatch, which):
        real = tmp_path / "real"
        real.mkdir()
        demo_home = tmp_path / "demo-home"
        if which == "home":
            demo_home.symlink_to(real)
        else:
            demo_home.mkdir()
            (demo_home / ".apple-music-dj").symlink_to(real)
        monkeypatch.setattr(demo, "DEMO_HOME", demo_home)
        with pytest.raises(SystemExit, match="symlink"):
            demo.prepare_demo_home()

    def test_tour_reports_failed_steps(self, monkeypatch, capsys):
        class Srv:
            url = "http://127.0.0.1:1"

            def stop(self):
                pass

        monkeypatch.setattr(demo, "start_server", Srv)
        monkeypatch.setattr(demo, "ensure_profile", lambda env: None)
        monkeypatch.setattr(demo, "_run", lambda *a, **k: demo.subprocess.CompletedProcess(a, 2, "", "boom"))
        assert demo.cmd_tour() == 1
        captured = capsys.readouterr()
        assert "failed" in captured.err and "That's the demo" not in captured.out

    def test_profile_placeholder_is_substituted(self):
        assert demo.check_args(["--profile", "DEMO_PROFILE"]) == ["--profile", str(demo.demo_profile_path())]


class TestPretty:
    def test_playlist(self):
        out = demo.pretty('{"name": "Mix", "tracks": [{"name": "A", "artist": "B", "reason": "why"}]}')
        assert out.splitlines() == ["Mix", " 1. A — B   why"]

    def test_message_and_passthrough(self):
        assert demo.pretty('{"message": "hi"}') == "hi"
        assert demo.pretty("plain text\n") == "plain text"


@needs_tools
class TestEndToEnd:
    def test_tour_runs_without_tokens_and_stays_in_the_demo_folder(self, home):
        r = run_demo(home, "tour", env_extra={"APPLE_MUSIC_DEV_TOKEN": "", "APPLE_MUSIC_USER_TOKEN": ""})
        assert r.returncode == 0, r.stderr
        assert "TASTE DNA CARD" in r.stdout and "Like Radiohead" in r.stdout and "Today's pick" in r.stdout
        assert "setup_auth.py" in r.stdout
        assert (home / ".apple-music-dj-demo" / ".apple-music-dj" / "taste_profile.json").is_file()
        assert not (home / ".apple-music-dj").exists()

    def test_run_passes_through_exit_codes_and_writes_go_to_the_mock(self, home):
        r = run_demo(home, "run", "strategy_engine.py", "--strategy", "similar", "--similar-to", "Radiohead",
                     "--profile", "DEMO_PROFILE", "--create")
        assert r.returncode == 0, r.stderr
        assert "Nothing here touches your Apple Music account" in r.stderr
        assert run_demo(home, "run", "taste_card.py", "/does/not/exist.json").returncode != 0

    def test_reset_removes_only_the_demo_folder(self, home):
        (home / ".apple-music-dj-demo").mkdir()
        (home / ".apple-music-dj").mkdir()
        assert "Removed" in run_demo(home, "reset").stdout
        assert not (home / ".apple-music-dj-demo").exists() and (home / ".apple-music-dj").exists()
