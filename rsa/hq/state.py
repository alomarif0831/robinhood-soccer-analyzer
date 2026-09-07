"""Settings persistence, the app data directory and the single background job runner."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from ..config import DEFAULT_LEAGUES, LEAGUES, WINDOW_START
from ..fees import FEE_MODELS

log = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict = {
    "leagues": list(DEFAULT_LEAGUES),
    "start": WINDOW_START.isoformat(),
    "end": "",                    # blank = today
    "fees": "robinhood",
    "fill": "ask",
    "min_edge": 0.03,
    "minutes_before": 0,
    "warmup_days": 150,
    "bankroll": 1000.0,
    "kelly": 0.25,
    "max_bet": 0.02,
    "max_day": 0.10,
    "max_bets_per_day": 8,
    "min_confidence": 60.0,
    "days_ahead": 7,
    "theme": "system",            # system | light | dark
    "kalshi_key_id": "",
    "kalshi_private_key": "",
    "github_repo": "alomarif0831/robinhood-soccer-analyzer",
}


def app_dir() -> Path:
    """Per-user home for settings, fetched data and reports (override with RSA_HOME)."""
    d = Path(os.environ.get("RSA_HOME") or (Path.home() / ".robinhood-soccer-hq"))
    d.mkdir(parents=True, exist_ok=True)
    return d


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or (app_dir() / "settings.json")
        self.values = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> dict:
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                self.values.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
            except (OSError, ValueError) as e:
                log.warning("settings unreadable (%s); using defaults", e)
        return self.values

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values, indent=2), encoding="utf-8")

    def update(self, patch: dict) -> dict:
        clean = validate(patch)
        self.values.update(clean)
        self.save()
        return self.values

    @property
    def end_date(self) -> date:
        return date.fromisoformat(self.values["end"]) if self.values.get("end") else date.today()

    @property
    def start_date(self) -> date:
        return date.fromisoformat(self.values["start"])


def validate(patch: dict) -> dict:
    """Coerce and range-check a settings patch; unknown keys are ignored, bad values raise ValueError."""
    out: dict = {}
    for k, v in patch.items():
        if k not in DEFAULT_SETTINGS:
            continue
        if k == "leagues":
            if isinstance(v, str):
                v = [x.strip() for x in v.split(",") if x.strip()]
            bad = [x for x in v if x not in LEAGUES]
            if bad:
                raise ValueError(f"unknown leagues: {', '.join(bad)}")
            out[k] = list(v)
        elif k in ("start", "end"):
            if v:
                date.fromisoformat(str(v))
            out[k] = str(v or "")
        elif k == "fees":
            if v not in FEE_MODELS:
                raise ValueError(f"unknown fee model {v}")
            out[k] = v
        elif k == "fill":
            if v not in ("ask", "last"):
                raise ValueError("fill must be ask or last")
            out[k] = v
        elif k == "theme":
            if v not in ("system", "light", "dark"):
                raise ValueError("theme must be system, light or dark")
            out[k] = v
        elif k in ("min_edge", "bankroll", "kelly", "max_bet", "max_day", "min_confidence"):
            f = float(v)
            limits = {"min_edge": (-1, 1), "bankroll": (1, 1e9), "kelly": (0, 1), "max_bet": (0, 1), "max_day": (0, 1),
                      "min_confidence": (0, 100)}[k]
            if not (limits[0] <= f <= limits[1]):
                raise ValueError(f"{k} out of range")
            out[k] = f
        elif k in ("minutes_before", "warmup_days", "max_bets_per_day", "days_ahead"):
            i = int(v)
            if i < 0 or i > 100000:
                raise ValueError(f"{k} out of range")
            out[k] = i
        else:
            out[k] = str(v or "")
    return out


# ------------------------------------------------------------------ jobs
class _ListHandler(logging.Handler):
    def __init__(self, sink: list[str], limit: int = 400):
        super().__init__(level=logging.INFO)
        self.sink, self.limit = sink, limit
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.sink.append(self.format(record))
        if len(self.sink) > self.limit:
            del self.sink[: len(self.sink) - self.limit]


@dataclass
class Job:
    name: str
    status: str = "idle"          # idle | running | done | error
    started: float | None = None
    finished: float | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "started": self.started, "finished": self.finished,
                "log": self.log[-120:], "error": self.error, "result": self.result,
                "elapsed": (time.time() - self.started) if self.started and not self.finished else
                ((self.finished - self.started) if self.started and self.finished else None)}


class JobRunner:
    """Runs one job at a time in a background thread, capturing log output for the UI."""

    def __init__(self):
        self.current: Job | None = None
        self.history: list[Job] = []
        self._lock = threading.Lock()

    def busy(self) -> bool:
        return self.current is not None and self.current.status == "running"

    def start(self, name: str, fn: Callable[[Job], dict]) -> Job:
        with self._lock:
            if self.busy():
                raise RuntimeError(f"{self.current.name} is still running")
            job = Job(name=name, status="running", started=time.time())
            self.current = job
        handler = _ListHandler(job.log)

        def run() -> None:
            root = logging.getLogger()
            root.addHandler(handler)
            try:
                job.log.append(f"{time.strftime('%H:%M:%S')} INFO {name} started")
                job.result = fn(job) or {}
                job.status = "done"
                job.log.append(f"{time.strftime('%H:%M:%S')} INFO {name} finished")
            except Exception as e:  # noqa: BLE001 - surfaced to the UI
                job.status = "error"
                job.error = f"{type(e).__name__}: {e}"
                job.log.append(f"{time.strftime('%H:%M:%S')} ERROR {job.error}")
                log.debug("job %s failed:\n%s", name, traceback.format_exc())
            finally:
                job.finished = time.time()
                root.removeHandler(handler)
                with self._lock:
                    self.history.append(job)
                    self.history = self.history[-20:]

        threading.Thread(target=run, name=f"job-{name}", daemon=True).start()
        return job

    def status(self) -> dict:
        return {"current": self.current.to_dict() if self.current else None,
                "history": [j.to_dict() | {"log": []} for j in self.history[-10:]]}
