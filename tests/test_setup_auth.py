"""Tests for setup_auth.py (guided token setup) and the user-token age tracking in _common."""

import base64
import http.client
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

import _common
import setup_auth
from generate_dev_token import TokenError


def fake_jwt(days: float) -> str:
    """An unsigned JWT-shaped token whose exp is `days` from now (only the payload is read)."""
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{seg({'alg': 'ES256'})}.{seg({'exp': int(time.time() + days * 86400)})}.sig"


def request(catcher, method, path, body=None, headers=None):
    host, port = catcher.url.split("/")[2].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=5)
    hdrs = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    payload = json.dumps(body).encode() if isinstance(body, dict) else body
    conn.request(method, path, body=payload, headers=hdrs)
    resp = conn.getresponse()
    return resp.status, resp.read()


@pytest.fixture
def catcher():
    c = setup_auth.TokenCatcher("dev.tok.en").start()
    yield c
    c.stop()


def origin(c):
    return c.url.rsplit("/", 2)[0]


class TestPage:
    def test_dev_token_is_a_safe_js_string(self):
        page = setup_auth.render_page('a"b</script><x>').decode()
        assert '</script><x>' not in page and "\\u003c/script>" in page
        assert setup_auth.MUSICKIT_JS in page

    def test_page_served_only_on_the_one_time_path(self, catcher):
        status, body = request(catcher, "GET", f"/{catcher.nonce}/")
        assert status == 200 and b"Connect Apple Music" in body and b"dev.tok.en" in body
        assert request(catcher, "GET", "/")[0] == 404
        assert request(catcher, "GET", "/wrong/")[0] == 404

    def test_foreign_host_header_is_refused(self, catcher):
        """A DNS-rebinding page would arrive with its own Host name."""
        assert request(catcher, "GET", f"/{catcher.nonce}/", headers={"Host": "evil.example"})[0] == 404


class TestTokenPost:
    def path(self, c):
        return f"/{c.nonce}/token"

    def test_same_origin_post_delivers_the_token(self, catcher):
        status, _ = request(catcher, "POST", self.path(catcher), {"token": "user-123"},
                            {"Origin": origin(catcher), "Content-Type": "application/json"})
        assert status == 200 and catcher.wait(1) == "user-123"

    def test_cross_origin_post_is_refused(self, catcher):
        status, _ = request(catcher, "POST", self.path(catcher), {"token": "x"}, {"Origin": "https://evil.example"})
        assert status == 403 and catcher.wait(0.1) is None

    def test_missing_origin_is_refused(self, catcher):
        assert request(catcher, "POST", self.path(catcher), {"token": "x"})[0] == 403

    @pytest.mark.parametrize("body", [{"token": ""}, {"token": "has space"}, {"token": 5}, {}, b"not json"])
    def test_bad_bodies_are_rejected(self, catcher, body):
        assert request(catcher, "POST", self.path(catcher), body, {"Origin": origin(catcher)})[0] == 400
        assert catcher.wait(0.05) is None

    def test_simultaneous_posts_keep_exactly_one_token(self, catcher):
        tokens = [f"tok-{i}" for i in range(12)]
        threads = [threading.Thread(target=request, args=(catcher, "POST", self.path(catcher), {"token": t},
                                                          {"Origin": origin(catcher)})) for t in tokens]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        first = catcher.wait(1)
        assert first in tokens
        time.sleep(0.05)
        assert catcher.token == first  # no later POST overwrote it

    def test_oversized_body_is_rejected(self, catcher):
        big = {"token": "x" * (setup_auth.MAX_TOKEN_BYTES + 10)}
        assert request(catcher, "POST", self.path(catcher), big, {"Origin": origin(catcher)})[0] == 400

    def test_first_token_wins(self, catcher):
        for tok in ("first", "second"):
            request(catcher, "POST", self.path(catcher), {"token": tok}, {"Origin": origin(catcher)})
        assert catcher.wait(1) == "first"


class TestDevToken:
    def args(self, **kw):
        base = {"new_dev_token": False, "key_id": None, "team_id": None, "key_path": None}
        return type("A", (), {**base, **kw})()

    def test_reuses_a_healthy_token(self, monkeypatch):
        tok = fake_jwt(90)
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", tok)
        assert setup_auth.get_dev_token(self.args()) == tok

    def test_signs_a_new_one_when_close_to_expiry(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", fake_jwt(3))
        seen = {}
        monkeypatch.setattr(setup_auth, "make_dev_token",
                            lambda k, t, p: seen.update(k=k, t=t, p=p) or "new")
        out = setup_auth.get_dev_token(self.args(key_id="K", team_id="T", key_path="/k.p8"))
        assert out == "new" and seen == {"k": "K", "t": "T", "p": "/k.p8"}

    def test_missing_key_details_is_a_clear_error(self, monkeypatch):
        for var in ("APPLE_MUSIC_DEV_TOKEN", "APPLE_KEY_ID", "APPLE_TEAM_ID", "APPLE_PRIVATE_KEY_PATH"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(setup_auth.sys.stdin, "isatty", lambda: False)
        with pytest.raises(TokenError, match="--key-id"):
            setup_auth.get_dev_token(self.args())


class TestSetupFlow:
    def run_with_signin(self, monkeypatch, argv, token="user-tok"):
        """Run main() and play the browser: post a token as soon as the page link is known."""
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", fake_jwt(90))
        real = setup_auth.TokenCatcher

        class Catcher(real):
            def start(self):
                super().start()
                if token:
                    threading.Thread(target=lambda: request(self, "POST", f"/{self.nonce}/token",
                                                            {"token": token}, {"Origin": origin(self)})).start()
                return self

        monkeypatch.setattr(setup_auth, "TokenCatcher", Catcher)
        return setup_auth.main(argv)

    def test_prints_quoted_export_lines(self, monkeypatch, capsys):
        assert self.run_with_signin(monkeypatch, ["--no-browser", "--timeout", "5"]) == 0
        out = capsys.readouterr().out
        assert "export APPLE_MUSIC_USER_TOKEN=user-tok" in out and "export APPLE_MUSIC_DEV_TOKEN=" in out
        assert _common.USER_TOKEN_SEEN.is_file()  # reminder record, by fingerprint only
        assert "user-tok" not in _common.USER_TOKEN_SEEN.read_text()

    def test_env_file_is_private_and_tokens_stay_off_stdout(self, monkeypatch, capsys, tmp_path):
        env_file = tmp_path / "tokens.env"
        assert self.run_with_signin(monkeypatch, ["--no-browser", "--timeout", "5", "--env-file", str(env_file)]) == 0
        assert "user-tok" not in capsys.readouterr().out
        assert env_file.stat().st_mode & 0o777 == 0o600
        assert "export APPLE_MUSIC_USER_TOKEN=user-tok" in env_file.read_text()

    def test_timeout_without_signin_fails_cleanly(self, monkeypatch, capsys):
        assert self.run_with_signin(monkeypatch, ["--no-browser", "--timeout", "0"], token=None) == 1
        assert "no sign-in arrived" in capsys.readouterr().err

    def test_bad_key_path_fails_before_opening_anything(self, monkeypatch, capsys, tmp_path):
        monkeypatch.delenv("APPLE_MUSIC_DEV_TOKEN", raising=False)
        opened = []
        monkeypatch.setattr(setup_auth.webbrowser, "open", opened.append)
        rc = setup_auth.main(["--key-id", "K", "--team-id", "T", "--key-path", str(tmp_path / "nope.p8")])
        assert rc == 1 and not opened


class TestStatus:
    def test_healthy(self, monkeypatch, capsys):
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", fake_jwt(90))
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "u")
        assert setup_auth.main(["status"]) == 0
        assert "Renew" not in capsys.readouterr().out

    def test_unreadable_age_record_is_explained(self, monkeypatch, capsys):
        monkeypatch.setenv("APPLE_MUSIC_DEV_TOKEN", fake_jwt(90))
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "u")
        monkeypatch.setattr(setup_auth, "check_user_token_age", lambda: None)
        assert setup_auth.main(["status"]) == 1
        assert "age couldn't be read" in capsys.readouterr().out

    def test_missing_tokens(self, monkeypatch, capsys):
        monkeypatch.delenv("APPLE_MUSIC_DEV_TOKEN", raising=False)
        monkeypatch.delenv("APPLE_MUSIC_USER_TOKEN", raising=False)
        assert setup_auth.main(["status"]) == 1
        assert "not set" in capsys.readouterr().out


class TestKeyFile:
    def test_unreadable_key_is_a_token_error(self, tmp_path, monkeypatch):
        pytest.importorskip("jwt")
        key = tmp_path / "AuthKey.p8"
        key.write_text("x")

        def deny(*a, **k):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr("builtins.open", deny)
        from generate_dev_token import make_dev_token
        with pytest.raises(TokenError, match="Can't read the key file"):
            make_dev_token("K", "T", str(key))


class TestUserTokenAge:
    def test_new_token_is_recorded_today(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "abc")
        status = _common.check_user_token_age()
        assert status["age_days"] == 0 and not status["warning"]
        assert json.loads(_common.USER_TOKEN_SEEN.read_text())["fingerprint"] == _common.user_token_fingerprint("abc")

    def test_old_token_warns(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "abc")
        _common.record_user_token("abc", when=datetime.now(timezone.utc) - timedelta(days=170))
        status = _common.check_user_token_age()
        assert status["age_days"] == 170 and status["warning"] and "setup_auth.py" in status["message"]

    def test_a_different_token_resets_the_clock(self, monkeypatch):
        _common.record_user_token("old", when=datetime.now(timezone.utc) - timedelta(days=170))
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "new")
        assert _common.check_user_token_age()["age_days"] == 0

    def test_demo_mode_and_no_token_skip(self, monkeypatch):
        monkeypatch.delenv("APPLE_MUSIC_USER_TOKEN", raising=False)
        assert _common.check_user_token_age() is None
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "abc")
        monkeypatch.setenv("APPLE_MUSIC_DJ_DEMO", "1")
        assert _common.check_user_token_age() is None

    def test_corrupt_record_is_tolerated(self, monkeypatch):
        monkeypatch.setenv("APPLE_MUSIC_USER_TOKEN", "abc")
        _common.USER_TOKEN_SEEN.write_text(json.dumps({"fingerprint": _common.user_token_fingerprint("abc"),
                                                       "first_seen": "garbage"}))
        assert _common.check_user_token_age() is None
