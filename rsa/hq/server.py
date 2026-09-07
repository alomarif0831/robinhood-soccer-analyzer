"""Local HTTP server: JSON API for the HQ UI plus the static files, and the app window launcher."""

from __future__ import annotations

import json
import logging
import math
import os
import platform
import secrets
import socket
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from .. import __version__
from . import APP_NAME
from .jobs import job_backtest, job_demo, job_fetch, job_picks, paths
from .state import JobRunner, Settings, app_dir

log = logging.getLogger(__name__)
UI_DIR = Path(__file__).resolve().parent / "ui"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json; charset=utf-8"}
MATCH_COLUMNS = ["league", "kickoff", "home", "away", "home_goals", "away_goals", "result", "mkt_home", "mkt_draw", "mkt_away",
                 "bid_home", "bid_draw", "bid_away", "ask_home", "ask_draw", "ask_away", "vol_home", "vol_draw", "vol_away",
                 "book_home", "book_draw", "book_away", "book_source", "bookc_home", "bookc_draw", "bookc_away",
                 "pro_home", "pro_draw", "pro_away", "prosd_home", "prosd_draw", "prosd_away", "pro_n_train",
                 "poisson_home", "poisson_draw", "poisson_away", "elo_home", "elo_draw", "elo_away",
                 "close_home", "close_draw", "close_away", "mkt_overround", "team_games", "rest_home", "rest_away", "match_id", "event_id"]


def records(df: pd.DataFrame | None, columns: list[str] | None = None, limit: int | None = None) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts (NaN -> null, timestamps -> ISO)."""
    if df is None or df.empty:
        return []
    if columns:
        df = df[[c for c in columns if c in df]]
    if limit:
        df = df.head(limit)
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return None


IDLE_SECONDS = 300      # browsers throttle timers in hidden windows to once a minute; give plenty of slack
BYE_GRACE_SECONDS = 12  # after the page says goodbye, wait this long for a reload before quitting


def _sanitize(obj):
    """Replace NaN/Infinity (not valid JSON) with null, recursively."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


class HQState:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.runner = JobRunner()
        self.started = time.time()
        self.last_heartbeat: float | None = None
        self.bye_at: float | None = None
        self.window_opened = False
        self.window_proc: subprocess.Popen | None = None
        self.shutdown_requested = False
        self.token = secrets.token_urlsafe(24)   # required on every POST: blocks cross-site requests from other pages

    def touch(self) -> None:
        self.last_heartbeat = time.time()
        self.bye_at = None

    # ---------------------------------------------------------------- data access
    def _reports(self, source: str) -> Path:
        return paths(self.settings, demo=(source == "demo"))["reports"]

    def _data(self, source: str) -> Path:
        return paths(self.settings, demo=(source == "demo"))["data"]

    def info(self) -> dict:
        out = {"app": APP_NAME, "version": __version__, "app_dir": str(app_dir()), "frozen": bool(getattr(sys, "frozen", False)),
               "idle_seconds": IDLE_SECONDS,
               "settings": self.settings.values, "job": self.runner.status()["current"], "sources": {}}
        for src in ("live", "demo"):
            d, r = self._data(src), self._reports(src)
            meta = {}
            mp = d / "meta.json"
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8"))
                except ValueError:
                    meta = {}
            out["sources"][src] = {
                "has_data": (d / "matches.csv").exists(),
                "fetched_at": (d / "matches.csv").stat().st_mtime if (d / "matches.csv").exists() else None,
                "meta": {k: meta.get(k) for k in ("start", "end", "leagues", "synthetic")},
                "backtest_at": (r / "summary.json").stat().st_mtime if (r / "summary.json").exists() else None,
                "picks_at": (r / "picks.md").stat().st_mtime if (r / "picks.md").exists() else None,
            }
        return out

    def report(self, source: str) -> dict:
        r = self._reports(source)
        summary = {}
        if (r / "summary.json").exists():
            summary = json.loads((r / "summary.json").read_text(encoding="utf-8"), parse_constant=lambda _c: None)
        port = _read_csv(r / "pro_portfolio.csv")
        return {"summary": summary, "markdown": (r / "report.md").read_text(encoding="utf-8") if (r / "report.md").exists() else "",
                "generated": (r / "summary.json").stat().st_mtime if (r / "summary.json").exists() else None,
                "pro_portfolio": records(port), "unmatched": records(_read_csv(r / "unmatched_events.csv"), limit=200)}

    def picks(self, source: str) -> dict:
        r = self._reports(source)
        cands = _read_csv(r / "picks_candidates.csv")
        if cands is not None and not cands.empty:
            cands = cands.sort_values("confidence", ascending=False)
        return {"picks": records(_read_csv(r / "picks.csv")), "candidates": records(cands, limit=150),
                "markdown": (r / "picks.md").read_text(encoding="utf-8") if (r / "picks.md").exists() else "",
                "generated": (r / "picks.md").stat().st_mtime if (r / "picks.md").exists() else None,
                "upcoming": records(_read_csv(r / "upcoming.csv"), MATCH_COLUMNS)}

    def matches(self, source: str) -> dict:
        r = self._reports(source)
        df = _read_csv(r / "joined.csv")
        if df is not None and "kickoff" in df:
            df = df.sort_values("kickoff", ascending=False)
        return {"matches": records(df, MATCH_COLUMNS)}

    def check_updates(self) -> dict:
        repo = self.settings.values.get("github_repo") or "alomarif0831/robinhood-soccer-analyzer"
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                         headers={"User-Agent": f"{APP_NAME}/{__version__}", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = str(data.get("tag_name", "")).lstrip("v")
            return {"current": __version__, "latest": latest, "url": data.get("html_url"), "newer": _newer(latest, __version__),
                    "assets": [a.get("name") for a in data.get("assets", [])]}
        except Exception as e:  # noqa: BLE001
            return {"current": __version__, "error": f"{type(e).__name__}: {e}"}

    # ---------------------------------------------------------------- jobs
    def start_job(self, name: str, body: dict) -> dict:
        source = body.get("source", "live")
        demo = source == "demo"
        if name == "fetch":
            fn = job_fetch(self.settings, refresh=bool(body.get("refresh")))
        elif name == "backtest":
            fn = job_backtest(self.settings, demo=demo)
        elif name == "picks":
            fn = job_picks(self.settings, demo=demo)
        elif name == "demo":
            fn = job_demo(self.settings)
        elif name == "run":
            fetch, back = job_fetch(self.settings, refresh=bool(body.get("refresh"))), job_backtest(self.settings)

            def fn(job):
                out = fetch(job)
                out.update(back(job))
                return out
        else:
            raise KeyError(name)
        return self.runner.start(name, fn).to_dict()


def _newer(latest: str, current: str) -> bool:
    def parts(v: str) -> tuple:
        out = []
        for x in v.split("."):
            num = "".join(ch for ch in x if ch.isdigit())
            out.append(int(num) if num else 0)
        return tuple(out)

    try:
        return parts(latest) > parts(current)
    except ValueError:
        return False


# ------------------------------------------------------------------ HTTP handler
def make_handler(state: HQState):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"{APP_NAME.replace(' ', '')}/{__version__}"

        def log_message(self, fmt, *args):  # quiet by default; API errors are logged explicitly
            log.debug("%s " + fmt, self.address_string(), *args)

        # -------- helpers
        def _json(self, payload, status: int = 200) -> None:
            body = json.dumps(_sanitize(payload), default=str, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _static(self, name: str) -> None:
            path = (UI_DIR / name).resolve()
            if not str(path).startswith(str(UI_DIR.resolve())) or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = path.read_bytes()
            if name == "index.html":
                data = data.replace(b"<head>", f'<head><meta name="hq-token" content="{state.token}">'.encode("utf-8"), 1)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                parsed = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except ValueError:
                return {}
            return parsed if isinstance(parsed, dict) else {}

        def _same_origin(self) -> bool:
            """Only this page may call the API: exact Host (defeats DNS rebinding), same-origin Origin if sent,
            and the per-process token plus JSON content type on writes."""
            port = self.server.server_address[1]
            if (self.headers.get("Host") or "") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return False
            origin = self.headers.get("Origin")
            if origin and not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
                return False
            return True

        # -------- routes
        def do_GET(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            source = q.get("source", "live")
            if not self._same_origin():
                return self._json({"error": "forbidden"}, 403)
            if u.path.startswith("/api/"):
                state.touch()   # any API traffic proves the window is alive
            try:
                if u.path in ("/", "/index.html"):
                    return self._static("index.html")
                if u.path.startswith("/static/"):
                    return self._static(u.path[len("/static/"):])
                if u.path == "/api/info":
                    return self._json(state.info())
                if u.path == "/api/settings":
                    return self._json(state.settings.values)
                if u.path == "/api/jobs":
                    return self._json(state.runner.status())
                if u.path == "/api/report":
                    return self._json(state.report(source))
                if u.path == "/api/picks":
                    return self._json(state.picks(source))
                if u.path == "/api/matches":
                    return self._json(state.matches(source))
                if u.path == "/api/updates":
                    return self._json(state.check_updates())
                if u.path == "/api/heartbeat":
                    return self._json({"ok": True, "busy": state.runner.busy()})
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as e:  # noqa: BLE001
                log.exception("GET %s failed", u.path)
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def do_POST(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            if not self._same_origin():
                return self._json({"error": "forbidden"}, 403)
            if u.path == "/api/bye":
                # sent by the page on unload (sendBeacon, no custom headers); a reload cancels it via the next heartbeat
                state.bye_at = time.time()
                return self._json({"ok": True})
            if self.headers.get("X-HQ-Token") != state.token or not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json({"error": "forbidden"}, 403)
            state.touch()
            body = self._body()
            try:
                if u.path == "/api/settings":
                    try:
                        return self._json(state.settings.update(body))
                    except (ValueError, TypeError) as e:
                        return self._json({"error": str(e)}, 400)
                if u.path.startswith("/api/jobs/"):
                    name = u.path.rsplit("/", 1)[1]
                    try:
                        return self._json(state.start_job(name, body))
                    except KeyError:
                        return self._json({"error": f"unknown job {name}"}, 404)
                    except (RuntimeError, ValueError, TypeError) as e:
                        return self._json({"error": str(e)}, 409)
                if u.path == "/api/quit":
                    if state.runner.busy() and not body.get("force"):
                        return self._json({"ok": False, "busy": True, "error": f"{state.runner.current.name} is still running"}, 409)
                    state.shutdown_requested = True
                    return self._json({"ok": True})
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as e:  # noqa: BLE001
                log.exception("POST %s failed", u.path)
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    return Handler


# ------------------------------------------------------------------ window
def _browser_candidates() -> list[str]:
    sysname = platform.system()
    cands: list[str] = []
    if sysname == "Windows":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LocalAppData")):
            if base:
                cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif sysname == "Darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"):
            w = shutil.which(name)
            if w:
                cands.append(w)
    return [c for c in cands if os.path.exists(c)]


def open_window(url: str) -> tuple[str, subprocess.Popen | None]:
    """Open the HQ as an app-style window (Chrome/Edge --app) or fall back to the default browser.

    Returns (description, process). With its own profile directory the launched browser process is
    the window's real process, so its exit is a reliable "window closed" signal."""
    profile = app_dir() / "browser-profile"
    for exe in _browser_candidates():
        try:
            proc = subprocess.Popen([exe, f"--app={url}", "--window-size=1320,900", f"--user-data-dir={profile}", "--no-first-run",
                                     "--no-default-browser-check", "--disable-background-timer-throttling"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"app window ({Path(exe).name})", proc
        except OSError:
            continue
    webbrowser.open(url)
    return "default browser", None


# ------------------------------------------------------------------ entry
class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second instance bind a port that is already listening; refuse that instead.
    allow_reuse_address = platform.system() != "Windows"

    def server_bind(self) -> None:
        if platform.system() == "Windows" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _say(msg: str) -> None:
    if sys.stdout is not None:
        print(msg)


def serve(port: int = 0, open_ui: bool = True, exit_on_idle: bool = True, smoke: bool = False, settings: Settings | None = None) -> int:
    root = logging.getLogger()
    fh = logging.FileHandler(app_dir() / "hq.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    state = HQState(settings)
    try:
        httpd = _Server(("127.0.0.1", port), make_handler(state))
    except OSError as e:
        log.exception("cannot listen on 127.0.0.1:%s", port)
        _say(f"Cannot listen on port {port}: {e}")
        return 1
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    _say(f"{APP_NAME} v{__version__} running at {url}  (data in {app_dir()})")
    log.info("serving at %s", url)

    def watchdog() -> None:
        while not state.shutdown_requested:
            time.sleep(2)
            if not exit_on_idle or not state.window_opened or state.runner.busy():
                continue
            now = time.time()
            last = state.last_heartbeat or state.started
            proc = state.window_proc
            if proc is not None and proc.poll() is not None and now - state.started > 20:
                log.info("app window process exited; shutting down")
                state.shutdown_requested = True
            elif state.bye_at and now - state.bye_at > BYE_GRACE_SECONDS and state.last_heartbeat and state.last_heartbeat <= state.bye_at:
                log.info("window closed; shutting down")
                state.shutdown_requested = True
            elif now - last > IDLE_SECONDS:
                log.info("no UI heartbeat for %ss; shutting down", IDLE_SECONDS)
                state.shutdown_requested = True
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    if smoke:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        with urllib.request.urlopen(url + "api/info", timeout=10) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        with urllib.request.urlopen(url, timeout=10) as resp:
            page = resp.read().decode("utf-8")
        with urllib.request.urlopen(url + "static/app.js", timeout=10) as resp:
            js = resp.read().decode("utf-8")
        httpd.shutdown()
        if APP_NAME not in page or "viewDashboard" not in js:
            log.error("smoke FAILED: UI files are not being served from %s", UI_DIR)
            _say("smoke FAILED: UI files are not being served")
            return 1
        _say(f"smoke ok: {info['app']} {info['version']} (UI served from {UI_DIR})")
        return 0

    threading.Thread(target=watchdog, daemon=True).start()
    if open_ui:
        how, state.window_proc = open_window(url)
        state.window_opened = True
        state.touch()
        log.info("opened the HQ in %s", how)
        _say(f"Opened the HQ in your {how}. Close the window (or use Quit in the app) to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
