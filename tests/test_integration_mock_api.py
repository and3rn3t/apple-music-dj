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
        api(w, "add-to-library", "albums", "alb1,alb2", "--yes")
        api(w, "favorite", "songs", "s1,s2", "--yes")
        api(w, "rate", "s1", "-1", "--yes")
        api(w, "unrate", "s1", "--yes")
        got = [(r["method"], r["path"], r["query"], r["body"]) for r in api.mock.writes()]
        assert got == [
            ("POST", "/v1/me/library", {"ids[albums]": ["alb1,alb2"]}, None),
            ("POST", "/v1/me/favorites", {"ids[songs]": ["s1,s2"]}, None),
            ("PUT", "/v1/me/ratings/songs/s1", {}, {"type": "rating", "attributes": {"value": -1}}),
            ("DELETE", "/v1/me/ratings/songs/s1", {}, None),
        ]

    def test_write_commands_only_preview_without_yes(self, api):
        """The wrapper itself refuses to change the account unless --yes is passed."""
        w = "apple_music_api.sh"
        ids = api.tmp / "ids.json"
        ids.write_text(json.dumps({"data": [{"id": "s1", "type": "songs"}]}))
        for args in (("add-to-library", "albums", "alb1"), ("favorite", "songs", "s1"), ("rate", "s1", "-1"),
                     ("unrate", "s1"), ("create-playlist", ids), ("add-to-playlist", "p.1", ids),
                     ("remove-from-playlist", "p.1", ids)):
            res = api(w, *args, check=False)
            assert res.returncode == 3 and "WOULD" in res.stderr and "--yes" in res.stderr, args
        assert api.mock.writes() == []

    def test_build_playlist_only_previews_without_yes(self, api):
        ids = api.tmp / "ids.txt"
        ids.write_text("s1\ns2\n")
        for args in (("create", "Nope", "desc", ids), ("refresh", "p.1", ids), ("remove", "p.1", ids)):
            res = api("build_playlist.sh", *args, check=False)
            assert res.returncode == 3 and "WOULD" in res.stderr, args
        assert api.mock.writes() == []
        api("build_playlist.sh", "refresh", "p.1", ids, "--yes")
        assert [r["method"] for r in api.mock.writes()] == ["POST"]

    def test_feedback_only_previews_without_yes(self, api, profile):
        before = profile.read_text()
        out = _json(api("feedback.py", "dislike", "s2", "--profile", profile))
        assert out["applied"] is False and out["song_ids"] == ["s2"]
        assert api.mock.writes() == [] and profile.read_text() == before

    def test_playlist_track_edits_exit_cleanly(self, api):
        """Direct (non-subshell) helper calls used to trip an unbound-variable RETURN trap."""
        ids = api.tmp / "ids.json"
        ids.write_text(json.dumps({"data": [{"id": "s1", "type": "songs"}]}))
        api("apple_music_api.sh", "add-to-playlist", "p.1", ids, "--yes")
        api("apple_music_api.sh", "remove-from-playlist", "p.1", ids, "--yes")

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
        api(w, "favorite", "songs", "s1", "--yes")  # write path (runs in the main shell)
        api(w, "rate", "s1", "1", "--yes")
        api(w, "unrate", "s1", "--yes")
        api(w, "replay-summary", "2023", check=False)   # server answers 404
        assert list(api.tmpdir.glob("am_*")) == []

    @pytest.mark.parametrize("command", [["heavy-rotation"], ["favorite", "songs", "s1", "--yes"]])
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

    def test_retries_on_429_then_succeeds(self, api):
        seen = []

        class Flaky(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                body = b'{"data": [{"id": "ok"}]}' if len(seen) >= 3 else b"{}"
                self.send_response(200 if len(seen) >= 3 else 429)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Flaky)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {**api.env, "APPLE_MUSIC_API_BASE": f"http://127.0.0.1:{server.server_address[1]}"}
        try:
            r = subprocess.run(["bash", str(SCRIPTS / "apple_music_api.sh"), "heavy-rotation"],
                               capture_output=True, text=True, env=env, timeout=30)
        finally:
            server.shutdown()
            server.server_close()
        assert r.returncode == 0 and json.loads(r.stdout)["data"] == [{"id": "ok"}]
        assert len(seen) == 3 and r.stderr.count("Rate limited") == 2
        assert list(api.tmpdir.glob("am_*")) == []

    def test_connection_failure_is_reported_and_cleans_up(self, api):
        env = {**api.env, "APPLE_MUSIC_API_BASE": "http://127.0.0.1:9"}  # nothing listens on the discard port
        r = subprocess.run(["bash", str(SCRIPTS / "apple_music_api.sh"), "heavy-rotation"],
                           capture_output=True, text=True, env=env, timeout=30)
        assert r.returncode != 0 and "curl failed" in r.stderr
        assert list(api.tmpdir.glob("am_*")) == []

    def test_term_to_the_script_alone_stops_promptly_and_kills_curl(self, api):
        """bash defers traps until the foreground command ends; waiting on a background curl
        makes TERM act immediately instead of after the whole (here: 30s) request."""

        class Hang(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                time.sleep(30)

            do_POST = do_GET  # `favorite` is a POST

            def log_message(self, *args):
                pass

        socketserver.ThreadingTCPServer.daemon_threads = True
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Hang)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        env = {**api.env, "APPLE_MUSIC_API_BASE": f"http://127.0.0.1:{port}"}
        proc = subprocess.Popen(["bash", str(SCRIPTS / "apple_music_api.sh"), "favorite", "songs", "s1", "--yes"],
                                env=env, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 10
            while not list(api.tmpdir.glob("am_auth_*")) and time.time() < deadline:
                time.sleep(0.05)
            time.sleep(0.5)  # let curl start
            started = time.time()
            proc.send_signal(signal.SIGTERM)  # the script only — not its process group
            proc.wait(timeout=5)
            assert time.time() - started < 5 and proc.returncode == 143
            assert list(api.tmpdir.glob("am_*")) == []
            time.sleep(0.3)
            curl_left = subprocess.run(["pgrep", "-f", f"curl.*127.0.0.1:{port}"], capture_output=True)
            assert curl_left.returncode == 1, "curl was left running"
        finally:
            if proc.poll() is None:
                proc.kill()
            server.shutdown()
            server.server_close()

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
        plan = self._plan(api, profile, "--strategy", "similar", "--similar-to", "Radiohead", "--size", "10")
        artists = {t["artist"] for t in plan["tracks"]}
        assert "Oasis" in artists or "Muse" in artists  # came in via similar-artists
        assert plan["name"].startswith("Like Radiohead")
        assert api.mock.writes() == []

    def test_seed_excludes_library_songs(self, api, profile):
        ids = {t["id"] for t in self._plan(api, profile, "--strategy", "similar", "--similar-to", "Radiohead")["tracks"]}
        assert not ids & {"s1", "s4"}
        ids = {t["id"] for t in self._plan(api, profile, "--strategy", "similar", "--similar-to", "Radiohead",
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

    def test_blend_with_a_taste_code(self, api, profile):
        """A friend's code has artist names only; the blend looks their artists up and writes nothing."""
        code = api("share_code.py", "make", "--profile", profile).stdout.strip()
        assert code.startswith("amdj1:")
        res = api("strategy_engine.py", "--profile", profile, "--storefront", "us", "--strategy", "blend",
                  "--profile-b", code)
        plan = json.loads(res.stdout)
        assert plan["tracks"] and plan["compatibility"]["compatibility_pct"] > 50
        assert "of their top artists in the catalog" in res.stderr
        assert api.mock.writes() == []

    def test_hostile_artist_names_in_a_code_are_only_ever_data(self, api, profile):
        """Names from a stranger's code reach the catalog search, never a shell."""
        import base64
        import zlib
        names = ["$(touch PWNED_SUB)", "`touch PWNED_TICK`", "x; touch PWNED_SEMI #", "a' && touch PWNED_QUOTE && '",
                 "Radiohead"]
        payload = {"v": 1, "a": [[n, 5] for n in names], "g": [["Rock", 1]]}
        code = "amdj1:" + base64.urlsafe_b64encode(zlib.compress(json.dumps(payload).encode())).decode().rstrip("=")
        res = api("strategy_engine.py", "--profile", profile, "--storefront", "us", "--strategy", "blend",
                  "--profile-b", code, check=False)
        assert res.returncode == 0, res.stderr
        for marker in ("PWNED_SUB", "PWNED_TICK", "PWNED_SEMI", "PWNED_QUOTE"):
            assert not list(api.tmp.rglob(marker)) and not list(api.home.rglob(marker))
        searched = [r["query"] for r in api.mock.requests if "/search" in r["path"]]
        assert any("PWNED_SUB" in json.dumps(q) for q in searched)  # it was looked up as plain text
        assert "PWNED" not in res.stdout  # names the catalog doesn't know never reach the plan the agent reads
        assert api.mock.writes() == []

    def test_a_bad_code_stops_the_blend_cleanly(self, api, profile):
        res = api("strategy_engine.py", "--profile", profile, "--storefront", "us", "--strategy", "blend",
                  "--profile-b", "amdj1:definitely-not-valid", check=False)
        assert res.returncode == 1 and "ERROR" in res.stderr and not res.stdout.strip()
        assert api.mock.writes() == []

    def test_compatibility_accepts_a_taste_code(self, api, profile):
        code = api("share_code.py", "make", "--profile", profile).stdout.strip()
        result = json.loads(api("compatibility.py", "profile", profile, code).stdout)
        assert result["compatibility_pct"] > 50

    def test_share_code_commands_need_no_tokens_and_make_no_requests(self, api, profile):
        before = len(api.mock.requests)
        code = api("share_code.py", "make", "--profile", profile).stdout.strip()
        assert "Top artists:" in api("share_code.py", "show", code).stdout
        assert len(api.mock.requests) == before

    def test_mood_arc_descends_for_sleep(self, api, profile):
        plan = self._plan(api, profile, "--strategy", "mood", "--mood", "sleep", "--size", "8")
        energies = [t["energy"] for t in plan["tracks"] if "energy" in t]
        assert energies == sorted(energies, reverse=True)

    def test_create_and_favorite_write_what_was_asked(self, api, profile):
        api("strategy_engine.py", "--profile", profile, "--storefront", "us", "--strategy", "similar",
            "--similar-to", "Radiohead", "--create", "--favorite", "--name", "Live Test")
        writes = [(r["method"], r["path"]) for r in api.mock.writes()]
        assert ("POST", "/v1/me/library/playlists") in writes
        assert ("POST", "/v1/me/favorites") in writes
        created = next(r for r in api.mock.writes() if r["path"] == "/v1/me/library/playlists")
        assert created["body"]["attributes"]["name"] == "Live Test"
        history = json.loads((api.home / ".apple-music-dj" / "playlist_history.json").read_text())
        assert history[-1]["name"] == "Live Test" and history[-1]["strategy"] == "similar"

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
        out = _json(api("feedback.py", "dislike", "s2", "--profile", profile, "--yes"))
        assert out["results"] == [{"id": "s2", "ok": True}] and out["profile_updated"] is True
        put = next(r for r in api.mock.writes() if r["method"] == "PUT")
        assert put["path"] == "/v1/me/ratings/songs/s2" and put["body"]["attributes"]["value"] == -1
        assert "s2" in json.loads(profile.read_text())["disliked_song_ids"]

    def test_feedback_by_position_after_create_and_info(self, api, profile):
        api("strategy_engine.py", "--profile", profile, "--storefront", "us", "--strategy", "similar",
            "--similar-to", "Radiohead", "--create", "--name", "Pos Test")
        history = json.loads((api.home / ".apple-music-dj" / "playlist_history.json").read_text())
        first_id = history[-1]["track_ids"][0]
        info = _json(api("feedback.py", "info", "--playlist-name", "Pos Test", "--position", "1"))
        assert info[0]["id"] == first_id and info[0]["name"]
        api("feedback.py", "dislike", "--playlist-name", "Pos Test", "--position", "1", "--yes")
        assert next(r for r in api.mock.writes() if r["method"] == "PUT")["path"].endswith(first_id)

    @pytest.mark.skipif(not shutil.which("crontab"), reason="needs crontab")
    def test_setup_cron_lists_opt_in_job(self, api):
        out = api("setup_cron.py", "list", "--python", sys.executable).stdout
        assert "monthly-drift" in out and "opt-in" in out


# ── Concert prep: preview by default, write only with --create ───

class TestConcertPrep:
    def test_default_run_previews_and_writes_nothing(self, api):
        plan = _json(api("concert_prep.sh", "us", "Radiohead"))
        assert api.mock.writes() == []
        assert plan["created"] is False and plan["artist"] == "Radiohead"
        assert plan["playlist_name"].startswith("Concert Prep · Radiohead")
        assert [t["name"] for t in plan["tracks"]][:2] == ["Karma Police", "Paranoid Android"]  # top songs first
        assert {t["source"] for t in plan["tracks"]} == {"top_song", "deep_cut"}
        assert plan["track_count"] == len(plan["tracks"]) == plan["top_song_count"] + plan["deep_cut_count"]

    def test_default_run_says_how_to_create(self, api):
        assert "re-run with --create" in api("concert_prep.sh", "us", "Radiohead").stderr

    def test_deep_cuts_exclude_top_songs_and_are_unique(self, api):
        ids = [t["id"] for t in _json(api("concert_prep.sh", "us", "Radiohead"))["tracks"]]
        assert len(ids) == len(set(ids))

    def test_create_builds_exactly_the_previewed_playlist(self, api):
        preview = _json(api("concert_prep.sh", "us", "Radiohead", "Show Night"))
        assert api.mock.writes() == []
        created = _json(api("concert_prep.sh", "us", "Radiohead", "Show Night", "--create"))
        assert created["created"] is True
        posts = [r for r in api.mock.writes() if r["path"] == "/v1/me/library/playlists"]
        assert len(posts) == 1
        body = posts[0]["body"]
        assert body["attributes"]["name"] == "Show Night"
        assert [t["id"] for t in body["relationships"]["tracks"]["data"]] == [t["id"] for t in preview["tracks"]]

    def test_create_flag_works_in_any_position_and_names_may_contain_spaces(self, api):
        api("concert_prep.sh", "--create", "us", "Radiohead", "My Concert Mix")
        post = next(r for r in api.mock.writes() if r["path"] == "/v1/me/library/playlists")
        assert post["body"]["attributes"]["name"] == "My Concert Mix"

    def test_create_prints_a_single_json_document(self, api):
        out = api("concert_prep.sh", "us", "Radiohead", "--create").stdout
        assert json.loads(out)["created"] is True  # nothing else leaked onto stdout

    def test_preview_reports_whether_the_name_is_already_taken(self, api):
        assert _json(api("concert_prep.sh", "us", "Radiohead", "Show Night"))["name_exists"] is False
        api("concert_prep.sh", "us", "Radiohead", "Show Night", "--create")
        again = api("concert_prep.sh", "us", "Radiohead", "Show Night")
        assert _json(again)["name_exists"] is True
        assert "already exists" in again.stderr and "would skip it" in again.stderr

    def test_create_with_a_taken_name_does_not_claim_success(self, api):
        """build_playlist.sh skips quietly (exit 0) when the name exists; created must stay false."""
        first = _json(api("concert_prep.sh", "us", "Radiohead", "Show Night", "--create"))
        assert first["created"] is True and first["name_exists"] is False
        second = api("concert_prep.sh", "us", "Radiohead", "Show Night", "--create")
        result = _json(second)
        assert result["created"] is False and "already exists" in result["skipped_reason"]
        assert "Concert prep playlist created" not in second.stderr
        posts = [r for r in api.mock.writes() if r["path"] == "/v1/me/library/playlists"]
        assert len(posts) == 1  # the second run never even attempted a write

    def test_a_different_name_is_not_blocked(self, api):
        api("concert_prep.sh", "us", "Radiohead", "Show Night", "--create")
        other = _json(api("concert_prep.sh", "us", "Radiohead", "Another Night", "--create"))
        assert other["created"] is True and other["name_exists"] is False

    def test_unknown_artist_fails_without_writing(self, api):
        r = api("concert_prep.sh", "us", "Zzzz Nobody", "--create", check=False)
        assert r.returncode == 1 and "Could not find artist" in r.stderr
        assert api.mock.writes() == []

    def test_missing_arguments_print_usage(self, api):
        r = api("concert_prep.sh", "--create", check=False)
        assert r.returncode != 0 and "Usage: concert_prep.sh" in r.stderr and api.mock.writes() == []


# ── Nothing writes to the account unless explicitly asked ────────

class TestNothingIsWrittenByDefault:
    """The skill promises account changes are opt-in. These are the entry points that *can* write;
    run bare, none of them may. (A reviewer found concert_prep.sh creating a playlist unprompted.)"""

    CASES = [
        ("concert prep", "concert_prep.sh", ["us", "Radiohead"]),
        ("strategy: similar", "strategy_engine.py", ["--strategy", "similar", "--similar-to", "Radiohead",
                                                    "--storefront", "us"]),
        ("strategy: era", "strategy_engine.py", ["--strategy", "era", "--decade", "90s", "--storefront", "us"]),
        ("strategy: trend", "strategy_engine.py", ["--strategy", "trend", "--storefront", "us"]),
        ("gap analysis --add-missing", "catalog_explorer.py", ["gap-analysis", "{profile}", "us", "--add-missing", "2"]),
        ("playlist health fix", "playlist_health.py", ["fix", "p.1", "--profile", "{profile}"]),
    ]

    @pytest.mark.parametrize("label,script,args", CASES, ids=[c[0] for c in CASES])
    def test_bare_run_makes_no_writes(self, api, profile, label, script, args):
        args = [str(profile) if a == "{profile}" else a for a in args]
        if script == "strategy_engine.py":
            args = ["--profile", str(profile), *args]
        api(script, *args, check=False)
        assert api.mock.writes() == [], f"{label} wrote to the account without being asked"

    def test_new_releases_without_the_flag_writes_nothing(self, api, profile):
        api("new_releases.sh", str(profile), "us", check=False)
        assert api.mock.writes() == []

    def test_import_preview_writes_nothing(self, api):
        f = api.tmp / "list.txt"
        f.write_text("Radiohead - Idioteque\n")
        api("import_playlist.py", f, "--storefront", "us")
        assert api.mock.writes() == []

    def test_cron_install_without_confirm_changes_nothing(self, api):
        r = api("setup_cron.py", "install", "--log-dir", api.tmp / "logs", "--profile", api.tmp / "p.json",
                "--python", sys.executable, check=False)
        assert r.returncode == 2 and not (api.tmp / "logs").exists()


# ── The scheduled jobs actually run ──────────────────────────────

class TestScheduledJobsActuallyRun:
    """Two default cron jobs (new-releases, daily-drop) passed the wrong arguments and had failed
    silently since v3.0 — cron only writes to a log. Run every job's real command."""

    @staticmethod
    def _run(api, command):
        return subprocess.run(["sh", "-c", command], capture_output=True, text=True, env=api.env, timeout=120)

    @pytest.fixture
    def jobs(self, api, profile):
        sys.path.insert(0, str(SCRIPTS))
        import setup_cron
        return setup_cron.build_job_defs(sys.executable, str(profile), "us", str(api.tmp / "logs"))

    @pytest.mark.parametrize("name", ["weekly-mix", "new-releases", "daily-drop", "health-check"])
    def test_default_job_command_succeeds(self, api, jobs, name):
        r = self._run(api, jobs[name]["command"])
        assert r.returncode == 0, f"{name} exited {r.returncode}\nSTDERR:\n{r.stderr[-600:]}"

    def test_daily_drop_prints_one_pick(self, api, jobs):
        pick = json.loads(self._run(api, jobs["daily-drop"]["command"]).stdout)
        assert pick  # a real recommendation, not usage text

    def test_new_releases_job_only_reports(self, api, jobs):
        self._run(api, jobs["new-releases"]["command"])
        assert api.mock.writes() == []  # the job has no --create-playlist

    def test_weekly_mix_creates_its_playlist_because_the_user_installed_it(self, api, jobs):
        self._run(api, jobs["weekly-mix"]["command"])
        assert any(r["path"] == "/v1/me/library/playlists" for r in api.mock.writes())

    def test_monthly_drift_job_works_once_an_earlier_snapshot_exists(self, api, jobs):
        snaps = api.home / ".apple-music-dj" / "snapshots"
        snaps.mkdir(parents=True, exist_ok=True)
        (snaps / "2020-01-01.json").write_text(json.dumps({
            "top_artists": [{"name": "Miles Davis", "weight": 1}], "genre_distribution": [{"genre": "Jazz", "weight": 1}],
            "era_distribution": [{"decade": "1960s", "weight": 1}], "energy_profile": "chill",
            "variety_score": 0.5, "mainstream_score": 0.5, "generated_at": "2020-01-01T00:00:00+00:00"}))
        r = self._run(api, jobs["monthly-drift"]["command"])
        assert r.returncode == 0, r.stderr[-400:]
        assert "Taste drift: 2020-01-01" in r.stdout


# ── verify_setup.sh handles the tokens it writes to a temp file ──

def _hanging_server():
    """A local server that accepts requests and never answers (so we can interrupt mid-request)."""

    class Hang(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(30)

        def log_message(self, *args):
            pass

    socketserver.ThreadingTCPServer.daemon_threads = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Hang)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class TestVerifySetup:
    def test_runs_against_the_mock_and_reports_valid_tokens(self, api):
        r = api("verify_setup.sh")
        assert "Dev token — valid (HTTP 200)" in r.stdout and "User token — valid (HTTP 200)" in r.stdout
        assert api.mock.writes() == []

    def test_leaves_no_token_files_behind(self, api):
        api("verify_setup.sh")
        assert list(api.tmpdir.glob("am_verify_*")) == []

    def test_refuses_a_remote_api_base(self, api):
        env = {**api.env, "APPLE_MUSIC_API_BASE": "https://evil.example"}
        r = subprocess.run(["bash", str(SCRIPTS / "verify_setup.sh")], capture_output=True, text=True, env=env)
        assert r.returncode == 1 and "must be http://127.0.0.1" in r.stderr

    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
    def test_interrupt_mid_request_removes_the_token_file(self, api, sig):
        """The temp curl config holds both tokens; Ctrl-C while curl is waiting must not leave it."""
        server = _hanging_server()
        env = {**api.env, "APPLE_MUSIC_API_BASE": f"http://127.0.0.1:{server.server_address[1]}"}
        proc = subprocess.Popen(["bash", str(SCRIPTS / "verify_setup.sh")], env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            deadline = time.time() + 15
            while not list(api.tmpdir.glob("am_verify_*")) and time.time() < deadline:
                time.sleep(0.05)
            assert list(api.tmpdir.glob("am_verify_*")), "the token check never started"
            os.killpg(proc.pid, sig)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            server.shutdown()
            server.server_close()
        assert proc.returncode in (130, 143, -sig)
        assert list(api.tmpdir.glob("am_verify_*")) == []

    def test_term_sent_only_to_the_script_stops_it_and_cleans_up(self, api):
        """TERM to the script alone (curl is not signalled) must not wait out the request."""
        server = _hanging_server()
        env = {**api.env, "APPLE_MUSIC_API_BASE": f"http://127.0.0.1:{server.server_address[1]}"}
        proc = subprocess.Popen(["bash", str(SCRIPTS / "verify_setup.sh")], env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 15
            while not list(api.tmpdir.glob("am_verify_*")) and time.time() < deadline:
                time.sleep(0.05)
            assert list(api.tmpdir.glob("am_verify_*")), "the token check never started"
            started = time.time()
            proc.terminate()
            proc.wait(timeout=5)
            assert time.time() - started < 5
        finally:
            if proc.poll() is None:
                proc.kill()
            server.shutdown()
            server.server_close()
        assert proc.returncode in (143, -signal.SIGTERM)
        assert list(api.tmpdir.glob("am_verify_*")) == []
