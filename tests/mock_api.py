"""A tiny local stand-in for the Apple Music API.

Serves Apple-shaped responses for every endpoint the skill uses, from a small
fixed catalog, and records each request so tests can assert on what was sent
(especially writes). Used by test_integration_mock_api.py and handy for manual
runs:

    python3 tests/mock_api.py            # serves on http://127.0.0.1:8765
    export APPLE_MUSIC_API_BASE=http://127.0.0.1:8765
    export APPLE_MUSIC_DEV_TOKEN=x APPLE_MUSIC_USER_TOKEN=y
    scripts/apple_music_api.sh recently-added 5

Response shapes follow Apple's documentation but are NOT verified against the
real service — that needs a live developer account.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# ── Fixed catalog ────────────────────────────────────────────────

ARTISTS = {
    "a1": {"name": "Radiohead", "genres": ["Alternative", "Music"]},
    "a2": {"name": "Oasis", "genres": ["Rock", "Alternative", "Music"]},
    "a3": {"name": "Björk", "genres": ["Electronic", "Music"]},
    "a4": {"name": "Muse", "genres": ["Alternative", "Music"]},
}

# id, name, artist id, genres, release date, album id, isrc
_SONGS = [
    ("s1", "Karma Police", "a1", ["Alternative"], "1997-05-21", "alb1", "GBAYE9700001"),
    ("s2", "Paranoid Android", "a1", ["Alternative"], "1997-05-21", "alb1", "GBAYE9700002"),
    ("s3", "Let Down", "a1", ["Alternative"], "1997-05-21", "alb1", "GBAYE9700003"),
    ("s4", "Idioteque", "a1", ["Alternative", "Electronic"], "2000-10-02", "alb2", "GBAYE0000004"),
    ("s5", "Everything In Its Right Place", "a1", ["Alternative"], "2000-10-02", "alb2", "GBAYE0000005"),
    ("s6", "Wonderwall", "a2", ["Rock"], "1995-10-02", "alb3", "GBAYE9500006"),
    ("s7", "Champagne Supernova", "a2", ["Rock"], "1995-10-02", "alb3", "GBAYE9500007"),
    ("s8", "Don't Look Back in Anger", "a2", ["Rock"], "1995-10-02", "alb3", "GBAYE9500008"),
    ("s9", "Starlight", "a4", ["Alternative"], "2006-06-19", "alb4", "GBAYE0600009"),
    ("s10", "Supermassive Black Hole", "a4", ["Alternative", "Rock"], "2006-06-19", "alb4", "GBAYE0600010"),
    ("s11", "Jóga", "a3", ["Electronic"], "1997-09-22", "alb5", "GBAYE9700011"),
    ("s12", "Bachelorette", "a3", ["Electronic"], "1997-09-22", "alb5", "GBAYE9700012"),
]
ALBUMS = {
    "alb1": ("OK Computer", "a1", "1997-05-21"),
    "alb2": ("Kid A", "a1", "2000-10-02"),
    "alb3": ("(What's the Story) Morning Glory?", "a2", "1995-10-02"),
    "alb4": ("Black Holes and Revelations", "a4", "2006-06-19"),
    "alb5": ("Homogenic", "a3", "1997-09-22"),
}
SIMILAR = {"a1": ["a2", "a4"], "a2": ["a1"], "a3": ["a1"], "a4": ["a1", "a2"]}
LIBRARY_SONGS = ["s1", "s4"]
RATINGS = {"s5": 1, "s11": -1}
RECENT_TRACKS = ["s1", "s2", "s6"]


def song(sid: str) -> dict:
    row = next(r for r in _SONGS if r[0] == sid)
    _, name, aid, genres, date, alb, isrc = row
    return {
        "id": sid, "type": "songs",
        "attributes": {
            "name": name, "artistName": ARTISTS[aid]["name"], "genreNames": genres + ["Music"],
            "releaseDate": date, "albumName": ALBUMS[alb][0], "isrc": isrc, "trackNumber": 1,
        },
        "relationships": {"artists": {"data": [{"id": aid, "type": "artists"}]},
                          "albums": {"data": [{"id": alb, "type": "albums"}]}},
    }


def artist(aid: str) -> dict:
    a = ARTISTS[aid]
    return {"id": aid, "type": "artists", "attributes": {"name": a["name"], "genreNames": a["genres"]}}


def album(alb_id: str) -> dict:
    name, aid, date = ALBUMS[alb_id]
    return {"id": alb_id, "type": "albums",
            "attributes": {"name": name, "artistName": ARTISTS[aid]["name"], "releaseDate": date,
                           "isSingle": False, "trackCount": sum(1 for r in _SONGS if r[5] == alb_id),
                           "genreNames": ARTISTS[aid]["genres"]}}


# ── Server ───────────────────────────────────────────────────────

class MockAppleMusic:
    """Start with .start(); read .url; inspect .requests; stop with .stop()."""

    def __init__(self, port: int = 0):
        self.requests: list[dict] = []
        self.playlists: list[dict] = []
        self._port = port
        self._server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> "MockAppleMusic":
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _send(self, status: int, body: dict | None = None):
                payload = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _handle(self, method: str):
                url = urlparse(self.path)
                query = parse_qs(url.query)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode() if length else ""
                try:
                    body = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    body = raw
                auth = self.headers.get("Authorization", "").startswith("Bearer ")
                user = bool(self.headers.get("Music-User-Token"))
                mock.requests.append({"method": method, "path": unquote(url.path), "query": query,
                                      "body": body, "auth": auth, "user_token": user})
                if not auth:
                    status, payload = 401, {"errors": [{"status": "401"}]}
                elif "/me/" in url.path + "/" and not user:
                    status, payload = 403, {"errors": [{"status": "403"}]}
                else:
                    status, payload = mock.route(method, unquote(url.path), query, body)
                self._send(status, payload)

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_PUT(self):
                self._handle("PUT")

            def do_DELETE(self):
                self._handle("DELETE")

        self._server = ThreadingHTTPServer(("127.0.0.1", self._port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def writes(self) -> list[dict]:
        return [r for r in self.requests if r["method"] != "GET"]

    # ── Routing ──────────────────────────────────────────────────

    def route(self, method: str, path: str, q: dict, body) -> tuple[int, dict | None]:
        parts = [p for p in path.split("/") if p]  # v1, ...
        if parts[:1] != ["v1"]:
            return 404, {"errors": [{"status": "404"}]}
        rest = parts[1:]

        if method == "GET":
            if rest == ["storefronts", "us"] or rest == ["me", "storefront"]:
                return 200, {"data": [{"id": "us", "type": "storefronts"}]}
            if rest == ["me", "recent", "played", "tracks"]:
                offset = int(q.get("offset", ["0"])[0])
                return 200, {"data": [song(s) for s in RECENT_TRACKS] if offset == 0 else []}
            if rest == ["me", "history", "heavy-rotation"] or rest == ["me", "recommendations"]:
                return 200, {"data": []}
            if rest == ["me", "recent", "played"]:
                return 200, {"data": []}
            if rest == ["me", "ratings", "songs"]:
                return 200, {"data": [{"id": sid, "type": "ratings", "attributes": {"value": v}}
                                      for sid, v in RATINGS.items()]}
            if rest == ["me", "music-summaries"] or rest == ["me", "music-summaries", "milestones"]:
                return 404, {"errors": [{"status": "404", "title": "Replay not available"}]}
            if rest == ["me", "library", "artists"]:
                offset = int(q.get("offset", ["0"])[0])
                return 200, {"data": [{"id": f"r.{a}", "type": "library-artists",
                                       "attributes": {"name": ARTISTS[a]["name"]}}
                                      for a in ("a1", "a2")] if offset == 0 else []}
            if rest == ["me", "library", "songs"]:
                offset = int(q.get("offset", ["0"])[0])
                out = []
                for sid in LIBRARY_SONGS if offset == 0 else []:
                    s = song(sid)
                    s["id"] = f"i.{sid}"
                    s["type"] = "library-songs"
                    s["relationships"]["catalog"] = {"data": [{"id": sid, "type": "songs"}]}
                    out.append(s)
                return 200, {"data": out}
            if rest == ["me", "library", "recently-added"]:
                return 200, {"data": [
                    {"id": "l.alb4", "type": "library-albums",
                     "attributes": {"name": ALBUMS["alb4"][0], "artistName": "Muse",
                                    "genreNames": ["Alternative"], "releaseDate": "2006-06-19"}},
                    {"id": "p.1", "type": "library-playlists", "attributes": {"name": "Road Trip"}},
                ]}
            if rest == ["me", "recent", "radio-stations"]:
                return 200, {"data": [
                    {"id": "ra.1", "type": "stations", "attributes": {"name": "Alternative Radio"}},
                    {"id": "ra.2", "type": "stations", "attributes": {"name": "Radiohead Station"}},
                ]}
            if rest == ["me", "library", "playlists"]:
                return 200, {"data": self.playlists}
            if rest[:3] == ["me", "library", "playlists"] and rest[-1] == "tracks":
                return 200, {"data": []}
            if rest[:1] == ["catalog"]:
                return self._catalog(rest[2:], q)
            return 404, {"errors": [{"status": "404", "detail": f"no mock for GET {path}"}]}

        if method == "POST":
            if rest == ["me", "library", "playlists"]:
                attrs = (body or {}).get("attributes", {})
                pl = {"id": f"p.{len(self.playlists) + 1}", "type": "library-playlists",
                      "attributes": {"name": attrs.get("name", "")}}
                self.playlists.append(pl)
                return 201, {"data": [pl]}
            if rest == ["me", "library"] or rest == ["me", "favorites"]:
                return 202, None
            if rest[:3] == ["me", "library", "playlists"] and rest[-1] == "tracks":
                return 204, None
        if method == "PUT" and rest[:3] == ["me", "ratings", "songs"] and len(rest) == 4:
            value = ((body or {}).get("attributes") or {}).get("value")
            return 200, {"data": [{"id": rest[3], "type": "ratings", "attributes": {"value": value}}]}
        if method == "DELETE" and rest[:3] == ["me", "ratings", "songs"] and len(rest) == 4:
            return 204, None
        if method == "DELETE" and rest[:3] == ["me", "library", "playlists"] and rest[-1] == "tracks":
            return 204, None
        return 404, {"errors": [{"status": "404", "detail": f"no mock for {method} {path}"}]}

    def _catalog(self, rest: list[str], q: dict) -> tuple[int, dict]:
        if rest == ["charts"]:
            return 200, {"results": {"songs": [{"name": "Top Songs", "data": [song("s9"), song("s12")]}]}}
        if rest == ["search"]:
            term = (q.get("term", [""])[0]).lower()
            types = (q.get("types", ["songs"])[0]).split(",")
            results: dict = {}
            if "artists" in types:
                results["artists"] = {"data": [artist(a) for a, v in ARTISTS.items() if v["name"].lower() in term
                                               or term in v["name"].lower()]}
            if "songs" in types:
                results["songs"] = {"data": [song(r[0]) for r in _SONGS
                                             if r[1].lower() in term or term in r[1].lower()
                                             or ARTISTS[r[2]]["name"].lower() in term]}
            if "albums" in types:
                results["albums"] = {"data": [album(a) for a, v in ALBUMS.items() if term in v[0].lower()]}
            return 200, {"results": results}
        if rest == ["songs"]:
            wanted = set((q.get("filter[isrc]", [""])[0]).split(","))
            return 200, {"data": [song(r[0]) for r in _SONGS if r[6] in wanted]}
        if len(rest) == 2 and rest[0] == "songs":
            if not any(r[0] == rest[1] for r in _SONGS):
                return 404, {"errors": [{"status": "404", "detail": f"no song {rest[1]}"}]}
            return 200, {"data": [song(rest[1])]}
        if rest[:1] == ["artists"] and len(rest) >= 2 and rest[1] in ARTISTS:
            aid = rest[1]
            if rest[2:] == ["view", "similar-artists"]:
                return 200, {"data": [artist(a) for a in SIMILAR.get(aid, [])]}
            if rest[2:] == ["albums"]:
                return 200, {"data": [album(a) for a, v in ALBUMS.items() if v[1] == aid]}
            if len(rest) == 2 and "top-songs" in (q.get("views", [""])[0]):
                tops = [song(r[0]) for r in _SONGS if r[2] == aid][:2]
                a = artist(aid)
                a["views"] = {"top-songs": {"data": tops}}
                return 200, {"data": [a]}
            if len(rest) == 2:
                return 200, {"data": [artist(aid)]}
        if len(rest) == 2 and rest[0] == "albums" and rest[1] in ALBUMS:
            a = album(rest[1])
            a["relationships"] = {"tracks": {"data": [song(r[0]) for r in _SONGS if r[5] == rest[1]]}}
            return 200, {"data": [a]}
        return 404, {"errors": [{"status": "404", "detail": f"no mock for catalog/{'/'.join(rest)}"}]}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = MockAppleMusic(port).start()
    print(f"Mock Apple Music API on {srv.url}  (Ctrl-C to stop)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.stop()
