"""Tests for demo.py: the no-tokens tour and the `run` sandbox around the real scripts."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import demo

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "demo.py"

needs_tools = pytest.mark.skipif(not (shutil.which("curl") and shutil.which("jq") and shutil.which("bash")),
                                 reason="needs curl, jq and bash")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def run_demo(home, *args, env_extra=None):
    import os
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1", **(env_extra or {})}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=120)


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
