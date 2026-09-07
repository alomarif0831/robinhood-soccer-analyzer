"""Match results and bookmaker odds.

Two keyless sources:

* **ESPN scoreboard** (``site.api.espn.com``): results and kickoff times for
  any league, sometimes with a moneyline from ESPN's odds provider.
* **football-data.co.uk** CSVs: results plus opening/closing odds from Bet365,
  Pinnacle (``PS*``/``PSC*``) and the market average/max for the big-five
  European leagues. Pinnacle's closing line is the sharpest public benchmark
  for "fair" probabilities, which is what the edge analysis compares against.
"""

from __future__ import annotations

import io
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .config import ESPN_BASE_URL, FDCOUK_BASE_URL, League
from .prices import parse_time

log = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")


@dataclass
class Match:
    league: str
    match_id: str
    kickoff: datetime | None
    home: str
    away: str
    home_goals: int | None
    away_goals: int | None
    completed: bool
    source: str
    odds: dict[str, float] = field(default_factory=dict)   # decimal odds, keys like "psc_home"
    extra: dict = field(default_factory=dict)

    @property
    def result(self) -> str | None:
        if not self.completed or self.home_goals is None or self.away_goals is None:
            return None
        if self.home_goals > self.away_goals:
            return "home"
        if self.home_goals < self.away_goals:
            return "away"
        return "draw"

    def to_row(self) -> dict:
        row = {
            "league": self.league, "match_id": self.match_id,
            "kickoff": self.kickoff.isoformat() if self.kickoff else None,
            "home": self.home, "away": self.away,
            "home_goals": self.home_goals, "away_goals": self.away_goals,
            "completed": self.completed, "result": self.result, "source": self.source,
            "neutral": bool(self.extra.get("neutral", False)),
        }
        row.update(self.odds)
        return row

    @classmethod
    def from_row(cls, row: dict) -> "Match":
        reserved = {"league", "match_id", "kickoff", "home", "away", "home_goals", "away_goals", "completed",
                    "result", "source", "neutral"}
        skip_prefix = ("mkt", "mktn", "bid", "ask", "vol", "mres", "ticker", "elo", "poisson", "blend")
        odds = {}
        for k, v in row.items():
            if k in reserved or v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            if "_" in k and k.rsplit("_", 1)[1] in ("home", "draw", "away") and k.rsplit("_", 1)[0] not in skip_prefix:
                try:
                    odds[k] = float(v)
                except (TypeError, ValueError):
                    pass

        def _int(v):
            try:
                return int(float(v)) if v is not None and not (isinstance(v, float) and math.isnan(v)) else None
            except (TypeError, ValueError):
                return None

        completed = str(row.get("completed")).lower() in ("true", "1", "1.0")
        return cls(
            league=row["league"], match_id=row["match_id"], kickoff=parse_time(row.get("kickoff")),
            home=row["home"], away=row["away"], home_goals=_int(row.get("home_goals")),
            away_goals=_int(row.get("away_goals")), completed=completed, source=str(row.get("source") or ""),
            odds=odds, extra={"neutral": str(row.get("neutral")).lower() in ("true", "1", "1.0")},
        )


# ----------------------------------------------------------------------- HTTP
def _http_get_text(url: str, session: requests.Session | None = None, timeout: float = 30) -> str:
    s = session or requests.Session()
    r = s.get(url, timeout=timeout, headers={"User-Agent": "robinhood-soccer-hq/0.2"})
    r.raise_for_status()
    if r.encoding is None or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "latin-1"
    return r.text


def _cached_text(url: str, cache_file: Path | None, refresh: bool, fetch: Callable[[str], str]) -> str:
    if cache_file and cache_file.exists() and not refresh:
        return cache_file.read_text(encoding="utf-8")
    text = fetch(url)
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    return text


# ----------------------------------------------------------------------- ESPN
def espn_scoreboard_url(league_code: str, day: date) -> str:
    return f"{ESPN_BASE_URL}/{league_code}/scoreboard?dates={day:%Y%m%d}&limit=200"


def american_to_decimal(ml) -> float | None:
    try:
        ml = float(ml)
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return 1 + ml / 100 if ml > 0 else 1 + 100 / abs(ml)


def parse_espn_scoreboard(data: dict, league_key: str) -> list[Match]:
    out: list[Match] = []
    for ev in data.get("events", []) or []:
        comps = ev.get("competitions") or []
        if not comps:
            continue
        c = comps[0]
        home = away = None
        for t in c.get("competitors", []) or []:
            team = t.get("team") or {}
            name = team.get("displayName") or team.get("name") or team.get("shortDisplayName") or ""
            score = t.get("score")
            try:
                score_i = int(float(score)) if score not in (None, "") else None
            except (TypeError, ValueError):
                score_i = None
            rec = (name, score_i, team.get("abbreviation"))
            if t.get("homeAway") == "home":
                home = rec
            elif t.get("homeAway") == "away":
                away = rec
        if not home or not away:
            continue
        status = ((c.get("status") or ev.get("status") or {}).get("type") or {})
        completed = bool(status.get("completed"))
        kickoff = parse_time(ev.get("date") or c.get("date"))
        odds: dict[str, float] = {}
        provider = None
        for o in c.get("odds") or []:
            provider = (o.get("provider") or {}).get("name")
            for side_key, out_key in (("homeTeamOdds", "home"), ("awayTeamOdds", "away"), ("drawOdds", "draw")):
                dec = american_to_decimal((o.get(side_key) or {}).get("moneyLine"))
                if dec:
                    odds[f"espn_{out_key}"] = dec
            if odds:
                break
        out.append(
            Match(
                league=league_key,
                match_id=f"espn:{ev.get('id')}",
                kickoff=kickoff,
                home=home[0],
                away=away[0],
                home_goals=home[1] if completed else None,
                away_goals=away[1] if completed else None,
                completed=completed,
                source="espn",
                odds=odds,
                extra={"home_abbr": home[2], "away_abbr": away[2], "status": status.get("name"),
                       "odds_provider": provider, "neutral": bool(c.get("neutralSite"))},
            )
        )
    return out


def load_espn(
    league: League,
    start: date,
    end: date,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    session: requests.Session | None = None,
    fetch: Callable[[str], str] | None = None,
) -> list[Match]:
    """All ESPN matches for ``league`` with kickoff dates in [start, end] (one request per day)."""
    fetch = fetch or (lambda url: _http_get_text(url, session))
    seen: dict[str, Match] = {}
    # ESPN groups fixtures by local (US) date; late-UTC kickoffs can land a day later, so request one
    # day either side and keep only fixtures whose UTC kickoff date is inside the window.
    day = start - timedelta(days=1)
    while day <= end + timedelta(days=1):
        url = espn_scoreboard_url(league.espn, day)
        cf = Path(cache_dir) / "espn" / league.key / f"{day:%Y%m%d}.json" if cache_dir else None
        try:
            text = _cached_text(url, cf, refresh, fetch)
        except Exception as e:  # noqa: BLE001 - keep going for other days
            log.warning("ESPN %s %s failed: %s", league.key, day, e)
            day += timedelta(days=1)
            continue
        for m in parse_espn_scoreboard(json.loads(text), league.key):
            seen.setdefault(m.match_id, m)
        day += timedelta(days=1)
    matches = [m for m in seen.values() if m.kickoff is None or start <= m.kickoff.date() <= end]
    return sorted(matches, key=lambda m: (m.kickoff or datetime.max.replace(tzinfo=timezone.utc), m.match_id))


# ------------------------------------------------------------ football-data.co.uk
_FD_ODDS = {
    "B365": "b365", "B365C": "b365c", "PS": "ps", "PSC": "psc", "Avg": "avg", "AvgC": "avgc",
    "Max": "max", "MaxC": "maxc", "BW": "bw", "WH": "wh", "IW": "iw", "VC": "vc", "BF": "bf",
    "BFE": "bfe", "BFEC": "bfec", "1XB": "onexb", "1XBC": "onexbc",
}


def fdcouk_url(div: str, season: str) -> str:
    return f"{FDCOUK_BASE_URL}/{season}/{div}.csv"


def _parse_fd_date(s: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_fdcouk_csv(text: str, league_key: str, div: str = "", season: str = "") -> list[Match]:
    df = pd.read_csv(io.StringIO(text), skip_blank_lines=True)
    df = df.dropna(subset=["HomeTeam", "AwayTeam"], how="any")
    out: list[Match] = []
    for _, r in df.iterrows():
        d = _parse_fd_date(r.get("Date"))
        if d is None:
            continue
        t = str(r.get("Time") or "15:00").strip()
        try:
            hh, mm = [int(x) for x in t.split(":")[:2]]
        except ValueError:
            hh, mm = 15, 0
        kickoff = datetime(d.year, d.month, d.day, hh, mm, tzinfo=LONDON).astimezone(timezone.utc)
        hg, ag = r.get("FTHG"), r.get("FTAG")
        completed = pd.notna(hg) and pd.notna(ag)
        odds: dict[str, float] = {}
        for col, prefix in _FD_ODDS.items():
            for suffix, out_key in (("H", "home"), ("D", "draw"), ("A", "away")):
                v = r.get(f"{col}{suffix}")
                if v is not None and pd.notna(v) and float(v) > 1.0:
                    odds[f"{prefix}_{out_key}"] = float(v)
        home, away = str(r["HomeTeam"]).strip(), str(r["AwayTeam"]).strip()
        out.append(
            Match(
                league=league_key,
                match_id=f"fdcouk:{div or r.get('Div', '')}:{d:%Y%m%d}:{home}:{away}",
                kickoff=kickoff,
                home=home,
                away=away,
                home_goals=int(hg) if completed else None,
                away_goals=int(ag) if completed else None,
                completed=bool(completed),
                source="fdcouk",
                odds=odds,
                extra={"season": season},
            )
        )
    return out


FDCOUK_FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"


def load_fdcouk_fixtures(
    leagues: Iterable[League],
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    session: requests.Session | None = None,
    fetch: Callable[[str], str] | None = None,
) -> list[Match]:
    """Upcoming fixtures with current bookmaker odds (one CSV covering every division)."""
    by_div = {lg.fdcouk: lg for lg in leagues if lg.fdcouk}
    if not by_div:
        return []
    fetch = fetch or (lambda url: _http_get_text(url, session))
    cf = Path(cache_dir) / "fdcouk" / "fixtures.csv" if cache_dir else None
    text = _cached_text(FDCOUK_FIXTURES_URL, cf, refresh, fetch)
    out: list[Match] = []
    for m in parse_fdcouk_csv(text, "", "", "fixtures"):
        div = m.match_id.split(":")[1] if m.match_id.count(":") >= 1 else ""
        lg = by_div.get(div)
        if lg is None:
            continue
        m.league = lg.key
        m.match_id = f"fdfix:{div}:{m.kickoff:%Y%m%d}:{m.home}:{m.away}"
        m.completed = False
        m.home_goals = m.away_goals = None
        out.append(m)
    return out


def load_fdcouk(
    league: League,
    season: str,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    session: requests.Session | None = None,
    fetch: Callable[[str], str] | None = None,
) -> list[Match]:
    if not league.fdcouk:
        return []
    fetch = fetch or (lambda url: _http_get_text(url, session))
    url = fdcouk_url(league.fdcouk, season)
    cf = Path(cache_dir) / "fdcouk" / season / f"{league.fdcouk}.csv" if cache_dir else None
    text = _cached_text(url, cf, refresh, fetch)
    return parse_fdcouk_csv(text, league.key, league.fdcouk, season)


# ---------------------------------------------------------------- probabilities
def implied_probs(odds_home: float, odds_draw: float, odds_away: float, method: str = "shin") -> tuple[float, float, float]:
    """Remove the bookmaker margin from decimal odds.

    ``proportional`` divides by the overround; ``shin`` (Shin 1993) assumes part
    of the margin comes from insider trading and shrinks longshots more, which
    empirically fits football odds better.
    """
    raw = [1.0 / o for o in (odds_home, odds_draw, odds_away)]
    total = sum(raw)
    if method == "proportional" or total <= 1.0:
        return tuple(x / total for x in raw)  # type: ignore[return-value]
    if method != "shin":
        raise ValueError(f"unknown de-vig method {method}")

    def probs(z: float) -> list[float]:
        return [(math.sqrt(z * z + 4 * (1 - z) * pi * pi) - z) / (2 * (1 - z)) for pi in raw]

    lo, hi = 0.0, 0.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if sum(probs(mid)) > 1.0:
            lo = mid
        else:
            hi = mid
    p = probs((lo + hi) / 2)
    s = sum(p)
    return tuple(x / s for x in p)  # type: ignore[return-value]


DEFAULT_BOOK_PREFERENCE = ("psc", "ps", "avgc", "maxc", "avg", "b365c", "b365", "bfec", "espn")
# What a bettor could see well before kickoff: football-data's non-closing columns are collected
# around Friday for weekend games, so they stand in for the pre-match line. Never the closing line.
PREMATCH_BOOK_PREFERENCE = ("ps", "avg", "max", "b365", "bfe", "espn")
CLOSING_BOOK_PREFERENCE = ("psc", "avgc", "maxc", "b365c", "bfec")


def bookmaker_probs(odds: dict[str, float], prefer: Iterable[str] = DEFAULT_BOOK_PREFERENCE,
                    method: str = "shin") -> tuple[tuple[float, float, float], str] | None:
    """De-vigged 3-way probabilities from the sharpest available book in ``odds``."""
    for prefix in prefer:
        keys = [f"{prefix}_home", f"{prefix}_draw", f"{prefix}_away"]
        if all(k in odds and odds[k] and odds[k] > 1.0 for k in keys):
            return implied_probs(*(odds[k] for k in keys), method=method), prefix
    return None


def matches_to_frame(matches: Iterable[Match]) -> pd.DataFrame:
    rows = [m.to_row() for m in matches]
    df = pd.DataFrame(rows)
    if not df.empty and "kickoff" in df:
        df["kickoff"] = pd.to_datetime(df["kickoff"], utc=True)
    return df


def matches_from_frame(df: pd.DataFrame) -> list[Match]:
    out = []
    for rec in df.to_dict("records"):
        k = rec.get("kickoff")
        if isinstance(k, pd.Timestamp):
            rec["kickoff"] = k.isoformat() if pd.notna(k) else None
        out.append(Match.from_row(rec))
    return out


def merge_results(primary: list[Match], secondary: list[Match], max_hours: float = 30) -> list[Match]:
    """Attach ``secondary`` odds/scores to ``primary`` matches by league, teams and date.

    Used to overlay football-data.co.uk odds onto ESPN fixtures (ESPN has
    precise kickoff times and every league; football-data has the odds).
    """
    from .teams import canonical

    idx: dict[tuple[str, str, str], list[Match]] = {}
    for m in secondary:
        idx.setdefault((m.league, canonical(m.home), canonical(m.away)), []).append(m)
    out = []
    for m in primary:
        cands = idx.get((m.league, canonical(m.home), canonical(m.away)), [])
        best = None
        for c in cands:
            if m.kickoff and c.kickoff and abs((m.kickoff - c.kickoff).total_seconds()) > max_hours * 3600:
                continue
            best = c
            break
        if best:
            merged = dict(best.odds)
            merged.update(m.odds)
            m.odds = merged
            if not m.completed and best.completed:
                m.home_goals, m.away_goals, m.completed = best.home_goals, best.away_goals, True
            m.extra["fdcouk_id"] = best.match_id
        out.append(m)
    return out
