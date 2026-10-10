"""End-to-end tests: real scripts, real curl/jq, against the local mock API (tests/mock_api.py).

These catch what mocked unit tests can't — URL quoting, empty 202 bodies, shell traps,
subprocess plumbing. They do NOT prove Apple's real response shapes match the mock.
"""

import http.server
import json
import os
import shutil
import signal
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.mock_api import MockAppleMusic

pytestmark = pytest.mark.skipif(
    not (shutil.which("curl") and shutil.which("jq") and shutil.which("bash")),
    reason="needs curl, jq and bash",
)

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def api(tmp_path):
    mock = MockAppleMusic().start()
    home = tmp_path / "home"
    home.mkdir()
    tmpdir = tmp_path / "tmpdir"  # isolated so tests can see whether scripts leave temp files behind
    tmpdir.mkdir()
    env = {**os.environ, "HOME": str(home), "TMPDIR": str(tmpdir), "APPLE_MUSIC_API_BASE": mock.url,
           "APPLE_MUSIC_DEV_TOKEN": "dev", "APPLE_MUSIC_USER_TOKEN": "user", "PYTHONDONTWRITEBYTECODE": "1"}
    for k in ("APPLE_MUSIC_STOREFRONT",):
        env.pop(k, None)

    def run(script, *args, check=True, input=None):
        cmd = ["bash", str(SCRIPTS / script)] if script.endswith(".sh") else [sys.executable, str(SCRIPTS / script)]
        r = subprocess.run(cmd + [str(a) for a in args], capture_output=True, text=True, env=env,
                           timeout=60, input=input)
        if check and r.returncode != 0:
            raise AssertionError(f"{script} {args} exited {r.returncode}\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}")
        return r

    run.mock, run.home, run.tmp, run.tmpdir, run.env = mock, home, tmp_path, tmpdir, env
    yield run
    mock.stop()


def _json(r):
    return json.loads(r.stdout)


# ── Shell wrapper ────────────────────────────────────────────────

class TestWrapper:
    def test_base_override_rejects_remote_hosts(self, api):
        env = {**os.environ, "APPLE_MUSIC_API_BASE": "https://evil.example"}
        r = subprocess.run(["bash", str(SCRIPTS / "apple_music_api.sh"), "help"],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 1 and "must be http://127.0.0.1" in r.stderr

    def test_verify(self, api):
        assert "Both tokens verified" in api("apple_music_api.sh", "verify").stderr

    def test_bracket_urls_are_not_globbed(self, api):
        data = _json(api("apple_music_api.sh", "songs-by-isrc", "us", "GBAYE9700001,GBAYE0600009"))
        assert [s["attributes"]["name"] for s in data["data"]] == ["Karma Police", "Starlight"]
        assert api.mock.requests[-1]["query"]["filter[isrc]"] == ["GBAYE9700001,GBAYE0600009"]

    def test_replay_summary_year_filter_reaches_server(self, api):
        api("apple_music_api.sh", "replay-summary", "2023", check=False)  # mock 404s Replay on purpose
        assert api.mock.requests[-1]["query"]["filter[year]"] == ["2023"]

    def test_unknown_song_is_a_real_404(self, api):
        assert api("apple_music_api.sh", "song-detail", "us", "s1").returncode == 0
        r = api("apple_music_api.sh", "song-detail", "us", "nope", check=False)
        assert r.returncode != 0
        assert api.mock.requests[-1]["path"] == "/v1/catalog/us/songs/nope"

    def test_new_read_commands(self, api):
        assert [i["id"] for i in _json(api("apple_music_api.sh", "recently-added", "5"))["data"]] == ["l.alb4", "p.1"]
        assert len(_json(api("apple_music_api.sh", "recent-stations"))["data"]) == 2
        names = [a["attributes"]["name"] for a in _json(api("apple_music_api.sh", "similar-artists", "us", "a1"))["data"]]
        assert names == ["Oasis", "Muse"]

    def test_write_commands_send_the_right_requests(self, api):
        w = "apple_music_api.sh"
        api(w, "add-to-library", "albums", "alb1,alb2")
        api(w, "favorite", "songs", "s1,s2")
        api(w, "rate", "s1", "-1")
        api(w, "unrate", "s1")
        got = [(r["method"], r["path"], r["query"], r["body"]) for r in api.mock.writes()]
        assert got == [
            ("POST", "/v1/me/library", {"ids[albums]": ["alb1,alb2"]}, None),
            ("POST", "/v1/me/favorites", {"ids[songs]": ["s1,s2"]}, None),
            ("PUT", "/v1/me/ratings/songs/s1", {}, {"type": "rating", "attributes": {"value": -1}}),
            ("DELETE", "/v1/me/ratings/songs/s1", {}, None),
        ]

    def test_playlist_track_edits_exit_cleanly(self, api):
        """Direct (non-subshell) helper calls used to trip an unbound-variable RETURN trap."""
        ids = api.tmp / "ids.json"
        ids.write_text(json.dumps({"data": [{"id": "s1", "type": "songs"}]}))
        api("apple_music_api.sh", "add-to-playlist", "p.1", ids)
        api("apple_music_api.sh", "remove-from-playlist", "p.1", ids)

    def test_input_validation_blocks_before_any_request(self, api):
        for args in (("favorite", "foo", "1"), ("add-to-library", "songs", "a;b"),
                     ("songs-by-isrc", "us", "BADISRC"), ("rate", "s1", "5"), ("unrate", "x/y")):
            assert api("apple_music_api.sh", *args, check=False).returncode != 0
        assert api.mock.writes() == []

    def test_no_token_files_left_behind(self, api):
        """The curl auth config holds both tokens — it must be gone after every call."""
        w = "apple_music_api.sh"
        api(w, "verify")
        api(w, "heavy-rotation")                    # read path (runs in a pipeline subshell)
        api(w, "favorite", "songs", "s1")           # write path (runs in the main shell)
        api(w, "rate", "s1", "1")
        api(w, "unrate", "s1")
        api(w, "replay-summary", "2023", check=False)   # server answers 404
        assert list(api.tmpdir.glob("am_*")) == []

    @pytest.mark.parametrize("command", [["heavy-rotation"], ["favorite", "songs", "s1"]])
    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
    def test_interrupt_cleans_up_token_files(self, api, command, sig):
        """Ctrl-C (signal to the whole process group) mid-request must not leave tokens in $TMPDIR."""

        class Hang(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                time.sleep(30)

            do_POST = do_GET

            def log_message(self, *args):
                pass

        socketserver.ThreadingTCPServer.daemon_threads = True  # don't wait for the hung handler on shutdown
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Hang)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {**api.env, "APPLE_MUSIC_API_BASE": f"http://127.0.0.1:{server.server_address[1]}"}
        proc = subprocess.Popen(["bash", str(SCRIPTS / "apple_music_api.sh"), *command], env=env,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            deadline = time.time() + 10
            while not list(api.tmpdir.glob("am_auth_*")) and time.time() < deadline:
                time.sleep(0.05)
            assert list(api.tmpdir.glob("am_auth_*")), "request never started"
            os.killpg(proc.pid, sig)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            server.shutdown()
            server.server_close()
        assert list(api.tmpdir.glob("am_*")) == []

    def test_missing_auth_is_rejected_by_server(self, api):
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            f"{api.mock.url}/v1/storefronts/us"], capture_output=True, text=True)
        assert r.stdout == "401"


# ── Profile ──────────────────────────────────────────────────────

@pytest.fixture
def profile(api):
    path = api.tmp / "profile.json"
    api("taste_profiler.py", "--output", path)
    return path


class TestProfiler:
    def test_builds_profile_with_new_signals(self, api, profile):
        p = json.loads(profile.read_text())
        assert p["recently_added_artists"] == ["Muse"]
        assert p["station_genres"] == ["Alternative"]
        assert p["data_summary"]["recently_added_items"] == 1 and p["data_summary"]["recent_stations"] == 2
        assert {a["name"] for a in p["top_artists"]} >= {"Radiohead", "Oasis", "Muse"}
        assert p["loved_track_ids"] == ["s5"] and p["disliked_song_ids"] == ["s11"]
        assert set(p["library_song_ids"]) == {"s1", "s4"}  # catalog IDs, not i.* library IDs

    def test_saves_private_snapshot_without_ids(self, api, profile):
        snaps = list((api.home / ".apple-music-dj" / "snapshots").glob("*.json"))
        assert len(snaps) == 1
        assert oct(snaps[0].stat().st_mode & 0o777) == "0o600"
        text = snaps[0].read_text()
        assert "s5" not in text and "Radiohead" in text

    def test_no_snapshot_flag(self, api):
        api("taste_profiler.py", "--no-snapshot", "--output", api.tmp / "p.json")
        assert not (api.home / ".apple-music-dj" / "snapshots").exists()

    def test_drift_needs_two_days(self, api, profile):
        r = api("taste_drift.py", check=False)
        assert r.returncode == 1 and "at least two snapshots" in r.stderr

    def test_drift_between_two_snapshots(self, api, profile):
        snap_dir = api.home / ".apple-music-dj" / "snapshots"
        newest = next(snap_dir.glob("*.json"))
        old = json.loads(newest.read_text())
        old["genre_distribution"] = [{"genre": "Jazz", "weight": 1.0}]
        old["top_artists"] = [{"name": "Miles Davis", "weight": 1.0}]
        (snap_dir / "2020-01-01.json").write_text(json.dumps(old))
        report = _json(api("taste_drift.py", "--since", "5y"))
        assert report["period"]["from"] == "2020-01-01"
        assert "Radiohead" in report["artists"]["new"] and report["artists"]["dropped"] == ["Miles Davis"]
        text = api("taste_drift.py", "--since", "5y", "--format", "text").stdout
        assert "Taste drift: 2020-01-01" in text
        # …and the card renders from that report
        data = api.tmp / "drift.json"
        data.write_text(json.dumps(report))
        card = api("taste_card.py", profile, "--mode", "drift", "--data", data, "--format", "text").stdout
        assert "TASTE DRIFT" in card


# ── Strategies (preview only unless noted) ───────────────────────

class TestStrategies:
    def _plan(self, api, profile, *args):
        return _json(api("strategy_engine.py", "--profile", profile, "--storefront", "us", *args))

    def test_seed_artist(self, api, profile):
        plan = self._plan(api, profile, "--strategy", "seed", "--seed", "Radiohead", "--size", "10")
        artists = {t["artist"] for t in plan["tracks"]}
        assert "Oasis" in artists or "Muse" in artists  # came in via similar-artists
        assert plan["name"].startswith("Like Radiohead")
        assert api.mock.writes() == []

    def test_seed_excludes_library_songs(self, api, profile):
        ids = {t["id"] for t in self._plan(api, profile, "--strategy", "seed", "--seed", "Radiohead")["tracks"]}
        assert not ids & {"s1", "s4"}
        ids = {t["id"] for t in self._plan(api, profile, "--strategy", "seed", "--seed", "Radiohead",
                                           "--include-library")["tracks"]}
        assert ids & {"s1", "s4"}

    def test_era(self, api, profile):
        plan = self._plan(api, profile, "--strategy", "era", "--decade", "90s")
        assert plan["tracks"] and all(t["id"] in {"s2", "s3", "s6", "s7", "s8", "s11", "s12"} for t in plan["tracks"])
        assert plan["name"].startswith("1990s Throwback")

    def test_blend_with_itself_is_all_shared(self, api, profile):
        plan = self._plan(api, profile, "--strategy", "blend", "--profile-b", profile)
        assert plan["tracks"] and plan["compatibility"]["compatibility_pct"] > 50
        assert {t["source"] for t in plan["tracks"]} <= {"shared", "a", "b"}

    def test_mood_arc_descends_for_sleep(self, api, profile):
        plan = self._plan(api, profile, "--strategy", "mood", "--mood", "sleep", "--size", "8")
        energies = [t["energy"] for t in plan["tracks"] if "energy" in t]
        assert energies == sorted(energies, reverse=True)

    def test_create_and_favorite_write_what_was_asked(self, api, profile):
        api("strategy_engine.py", "--profile", profile, "--storefront", "us", "--strategy", "seed",
            "--seed", "Radiohead", "--create", "--favorite", "--name", "Live Test")
        writes = [(r["method"], r["path"]) for r in api.mock.writes()]
        assert ("POST", "/v1/me/library/playlists") in writes
        assert ("POST", "/v1/me/favorites") in writes
        created = next(r for r in api.mock.writes() if r["path"] == "/v1/me/library/playlists")
        assert created["body"]["attributes"]["name"] == "Live Test"
        history = json.loads((api.home / ".apple-music-dj" / "playlist_history.json").read_text())
        assert history[-1]["name"] == "Live Test" and history[-1]["strategy"] == "seed"

    def test_favorite_without_create_is_refused(self, api, profile):
        r = api("strategy_engine.py", "--profile", profile, "--strategy", "trend", "--favorite", check=False)
        assert r.returncode == 2 and "--favorite only applies" in r.stderr


# ── Gap analysis, import, feedback ───────────────────────────────

class TestOtherScripts:
    def test_add_missing_preview_then_confirm(self, api, profile):
        preview = _json(api("catalog_explorer.py", "gap-analysis", profile, "us", "--add-missing", "2"))
        assert preview["add_missing"]["dry_run"] is True and len(preview["add_missing"]["albums"]) == 2
        assert [r for r in api.mock.writes() if r["path"] == "/v1/me/library"] == []

        done = _json(api("catalog_explorer.py", "gap-analysis", profile, "us", "--add-missing", "2", "--yes"))
        assert len(done["add_missing"]["added"]) == 2 and done["add_missing"]["failed"] == []
        post = next(r for r in api.mock.writes() if r["path"] == "/v1/me/library")
        assert set(post["query"]["ids[albums]"][0].split(",")) == {a["id"] for a in done["add_missing"]["albums"]}

    def test_import_csv_preview_and_create(self, api):
        csv_file = api.tmp / "export.csv"
        csv_file.write_text(
            "Track Name,Artist Name(s),ISRC\n"
            "Karma Police,Radiohead,GBAYE9700001\n"           # exact via ISRC
            "Wonderwall (Remastered),Oasis,\n"               # fuzzy via search
            "Nonexistent Song,Nobody,ZZZZZ0000000\n")        # unmatched
        preview = _json(api("import_playlist.py", csv_file, "--storefront", "us"))
        assert preview["counts"] == {"total": 3, "exact": 1, "fuzzy": 1, "unmatched": 1, "duplicates": 0}
        assert [t["id"] for t in preview["tracks"]] == ["s1", "s6"]
        assert api.mock.writes() == []

        api("import_playlist.py", csv_file, "--storefront", "us", "--create", "--name", "Imported")
        created = next(r for r in api.mock.writes() if r["path"] == "/v1/me/library/playlists")
        assert [t["id"] for t in created["body"]["relationships"]["tracks"]["data"]] == ["s1", "s6"]

    def test_import_text_file(self, api):
        f = api.tmp / "list.txt"
        f.write_text("Radiohead - Idioteque\n")
        assert [t["id"] for t in _json(api("import_playlist.py", f, "--storefront", "us"))["tracks"]] == ["s4"]

    def test_feedback_dislike_updates_api_and_profile(self, api, profile):
        out = _json(api("feedback.py", "dislike", "s2", "--profile", profile))
        assert out["results"] == [{"id": "s2", "ok": True}] and out["profile_updated"] is True
        put = next(r for r in api.mock.writes() if r["method"] == "PUT")
        assert put["path"] == "/v1/me/ratings/songs/s2" and put["body"]["attributes"]["value"] == -1
        assert "s2" in json.loads(profile.read_text())["disliked_song_ids"]

    def test_feedback_by_position_after_create_and_info(self, api, profile):
        api("strategy_engine.py", "--profile", profile, "--storefront", "us", "--strategy", "seed",
            "--seed", "Radiohead", "--create", "--name", "Pos Test")
        history = json.loads((api.home / ".apple-music-dj" / "playlist_history.json").read_text())
        first_id = history[-1]["track_ids"][0]
        info = _json(api("feedback.py", "info", "--playlist-name", "Pos Test", "--position", "1"))
        assert info[0]["id"] == first_id and info[0]["name"]
        api("feedback.py", "dislike", "--playlist-name", "Pos Test", "--position", "1")
        assert next(r for r in api.mock.writes() if r["method"] == "PUT")["path"].endswith(first_id)

    def test_setup_cron_lists_opt_in_job(self, api):
        out = api("setup_cron.py", "list", "--python", sys.executable).stdout
        assert "monthly-drift" in out and "opt-in" in out
