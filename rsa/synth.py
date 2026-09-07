"""Synthetic fixture generator for offline runs and tests.

Writes files in the *exact raw shapes* the live loaders parse (Kalshi market,
trade and candlestick JSON; ESPN scoreboard JSON per day; football-data.co.uk
CSVs), generated from a hidden "true" Poisson model with deliberately planted
market biases (draws underpriced, longshots overpriced) so the demo report
shows what a real finding would look like. Club lists are illustrative only.
Nothing here is real market data.
"""

from __future__ import annotations

import json
import math
import random
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import LEAGUES, League
from .kalshi import KalshiClient

# (espn_display_name, football_data_name, venue_name)
TEAMS: dict[str, list[tuple[str, str, str]]] = {
    "epl": [
        ("Arsenal", "Arsenal", "Arsenal"), ("Aston Villa", "Aston Villa", "Aston Villa"),
        ("AFC Bournemouth", "Bournemouth", "Bournemouth"), ("Brentford", "Brentford", "Brentford"),
        ("Brighton & Hove Albion", "Brighton", "Brighton"), ("Burnley", "Burnley", "Burnley"),
        ("Chelsea", "Chelsea", "Chelsea"), ("Crystal Palace", "Crystal Palace", "Crystal Palace"),
        ("Everton", "Everton", "Everton"), ("Fulham", "Fulham", "Fulham"),
        ("Leeds United", "Leeds", "Leeds"), ("Liverpool", "Liverpool", "Liverpool"),
        ("Manchester City", "Man City", "Manchester City"), ("Manchester United", "Man United", "Manchester United"),
        ("Newcastle United", "Newcastle", "Newcastle"), ("Nottingham Forest", "Nott'm Forest", "Nottingham Forest"),
        ("Sunderland", "Sunderland", "Sunderland"), ("Tottenham Hotspur", "Tottenham", "Tottenham"),
        ("West Ham United", "West Ham", "West Ham"), ("Wolverhampton Wanderers", "Wolves", "Wolves"),
    ],
    "laliga": [
        ("Deportivo Alavés", "Alaves", "Alaves"), ("Athletic Club", "Ath Bilbao", "Athletic Bilbao"),
        ("Atlético Madrid", "Ath Madrid", "Atletico Madrid"), ("Barcelona", "Barcelona", "Barcelona"),
        ("Real Betis", "Betis", "Real Betis"), ("Celta Vigo", "Celta", "Celta Vigo"),
        ("Elche", "Elche", "Elche"), ("Espanyol", "Espanol", "Espanyol"),
        ("Getafe", "Getafe", "Getafe"), ("Girona", "Girona", "Girona"),
        ("Levante", "Levante", "Levante"), ("Mallorca", "Mallorca", "Mallorca"),
        ("Osasuna", "Osasuna", "Osasuna"), ("Real Oviedo", "Oviedo", "Real Oviedo"),
        ("Rayo Vallecano", "Vallecano", "Rayo Vallecano"), ("Real Madrid", "Real Madrid", "Real Madrid"),
        ("Real Sociedad", "Sociedad", "Real Sociedad"), ("Sevilla", "Sevilla", "Sevilla"),
        ("Valencia", "Valencia", "Valencia"), ("Villarreal", "Villarreal", "Villarreal"),
    ],
    "bundesliga": [
        ("FC Augsburg", "Augsburg", "Augsburg"), ("Bayern Munich", "Bayern Munich", "Bayern Munich"),
        ("Borussia Dortmund", "Dortmund", "Borussia Dortmund"), ("Eintracht Frankfurt", "Ein Frankfurt", "Eintracht Frankfurt"),
        ("SC Freiburg", "Freiburg", "Freiburg"), ("Hamburg SV", "Hamburg", "Hamburg"),
        ("1. FC Heidenheim", "Heidenheim", "Heidenheim"), ("TSG Hoffenheim", "Hoffenheim", "Hoffenheim"),
        ("1. FC Köln", "FC Koln", "Koln"), ("Bayer Leverkusen", "Leverkusen", "Bayer Leverkusen"),
        ("Mainz", "Mainz", "Mainz"), ("Borussia Mönchengladbach", "M'gladbach", "Monchengladbach"),
        ("RB Leipzig", "RB Leipzig", "RB Leipzig"), ("FC St. Pauli", "St Pauli", "St. Pauli"),
        ("VfB Stuttgart", "Stuttgart", "Stuttgart"), ("Union Berlin", "Union Berlin", "Union Berlin"),
        ("Werder Bremen", "Werder Bremen", "Werder Bremen"), ("VfL Wolfsburg", "Wolfsburg", "Wolfsburg"),
    ],
    "seriea": [
        ("Atalanta", "Atalanta", "Atalanta"), ("Bologna", "Bologna", "Bologna"), ("Cagliari", "Cagliari", "Cagliari"),
        ("Como", "Como", "Como"), ("Cremonese", "Cremonese", "Cremonese"), ("Fiorentina", "Fiorentina", "Fiorentina"),
        ("Genoa", "Genoa", "Genoa"), ("Internazionale", "Inter", "Inter Milan"), ("Juventus", "Juventus", "Juventus"),
        ("Lazio", "Lazio", "Lazio"), ("Lecce", "Lecce", "Lecce"), ("AC Milan", "Milan", "AC Milan"),
        ("Napoli", "Napoli", "Napoli"), ("Parma", "Parma", "Parma"), ("Pisa", "Pisa", "Pisa"),
        ("AS Roma", "Roma", "Roma"), ("Sassuolo", "Sassuolo", "Sassuolo"), ("Torino", "Torino", "Torino"),
        ("Udinese", "Udinese", "Udinese"), ("Hellas Verona", "Verona", "Verona"),
    ],
    "ligue1": [
        ("Angers", "Angers", "Angers"), ("Auxerre", "Auxerre", "Auxerre"), ("Brest", "Brest", "Brest"),
        ("Le Havre", "Le Havre", "Le Havre"), ("Lens", "Lens", "Lens"), ("Lille", "Lille", "Lille"),
        ("Lorient", "Lorient", "Lorient"), ("Lyon", "Lyon", "Lyon"), ("Marseille", "Marseille", "Marseille"),
        ("Metz", "Metz", "Metz"), ("Monaco", "Monaco", "Monaco"), ("Nantes", "Nantes", "Nantes"),
        ("Nice", "Nice", "Nice"), ("Paris FC", "Paris FC", "Paris FC"), ("Paris Saint-Germain", "Paris SG", "PSG"),
        ("Rennes", "Rennes", "Rennes"), ("Strasbourg", "Strasbourg", "Strasbourg"), ("Toulouse", "Toulouse", "Toulouse"),
    ],
    "mls": [
        ("Atlanta United FC", "", "Atlanta United"), ("Austin FC", "", "Austin FC"), ("Charlotte FC", "", "Charlotte FC"),
        ("Chicago Fire FC", "", "Chicago Fire"), ("FC Cincinnati", "", "FC Cincinnati"), ("Colorado Rapids", "", "Colorado Rapids"),
        ("Columbus Crew", "", "Columbus Crew"), ("D.C. United", "", "DC United"), ("FC Dallas", "", "FC Dallas"),
        ("Houston Dynamo FC", "", "Houston Dynamo"), ("Inter Miami CF", "", "Inter Miami"), ("LA Galaxy", "", "LA Galaxy"),
        ("Los Angeles FC", "", "LAFC"), ("Minnesota United FC", "", "Minnesota United"), ("CF Montréal", "", "Montreal"),
        ("Nashville SC", "", "Nashville SC"), ("New England Revolution", "", "New England"), ("New York City FC", "", "NYCFC"),
        ("New York Red Bulls", "", "NY Red Bulls"), ("Orlando City SC", "", "Orlando City"), ("Philadelphia Union", "", "Philadelphia Union"),
        ("Portland Timbers", "", "Portland Timbers"), ("Real Salt Lake", "", "Real Salt Lake"), ("San Diego FC", "", "San Diego FC"),
        ("San Jose Earthquakes", "", "San Jose Earthquakes"), ("Seattle Sounders FC", "", "Seattle Sounders"),
        ("Sporting Kansas City", "", "Sporting KC"), ("St. Louis City SC", "", "St. Louis City"), ("Toronto FC", "", "Toronto FC"),
        ("Vancouver Whitecaps", "", "Vancouver Whitecaps"),
    ],
}

# First matchday of the (synthetic) season inside the window, and kickoff slots (UTC hour).
SEASON_START = {"epl": date(2026, 8, 15), "laliga": date(2026, 8, 14), "bundesliga": date(2026, 8, 21),
                "seriea": date(2026, 8, 22), "ligue1": date(2026, 8, 14), "mls": date(2026, 7, 25)}
WARMUP_START = {"epl": date(2025, 8, 16), "laliga": date(2025, 8, 15), "bundesliga": date(2025, 8, 22),
                "seriea": date(2025, 8, 23), "ligue1": date(2025, 8, 15), "mls": date(2026, 2, 21)}
KICKOFF_HOURS = {"epl": (11, 14, 16), "laliga": (14, 16, 19), "bundesliga": (13, 16), "seriea": (16, 18), "ligue1": (15, 19), "mls": (23, 0, 2)}
MARGINS = {"psc": 0.025, "ps": 0.03, "b365c": 0.05, "b365": 0.055, "avgc": 0.055, "avg": 0.06, "maxc": 0.01, "max": 0.015}


def _poisson_grid(lh: float, la: float, rho: float = -0.08, n: int = 10) -> list[list[float]]:
    ph = [math.exp(-lh) * lh ** i / math.factorial(i) for i in range(n + 1)]
    pa = [math.exp(-la) * la ** j / math.factorial(j) for j in range(n + 1)]
    mat = [[ph[i] * pa[j] for j in range(n + 1)] for i in range(n + 1)]
    mat[0][0] *= 1 - lh * la * rho
    mat[1][0] *= 1 + la * rho
    mat[0][1] *= 1 + lh * rho
    mat[1][1] *= 1 - rho
    s = sum(map(sum, mat))
    return [[v / s for v in r] for r in mat]


def _three_way(mat):
    n = len(mat)
    ph = sum(mat[i][j] for i in range(n) for j in range(n) if i > j)
    pd_ = sum(mat[i][i] for i in range(n))
    return ph, pd_, 1 - ph - pd_


def _sample_score(rng: random.Random, mat) -> tuple[int, int]:
    u = rng.random()
    acc = 0.0
    n = len(mat)
    for i in range(n):
        for j in range(n):
            acc += mat[i][j]
            if u <= acc:
                return i, j
    return n - 1, n - 1


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


def _odds_with_margin(probs, margin, rng, noise=0.0):
    ps = [_sigmoid(_logit(p) + rng.gauss(0, noise)) for p in probs]
    s = sum(ps)
    ps = [p / s for p in ps]
    return [round(max(1.01, 1 / (p * (1 + margin))), 2) for p in ps]


_CODES: dict[str, str] = {}


def _code(name: str) -> str:
    """Deterministic 3-letter ticker code, unique across names seen so far (Real Madrid / Real Betis must differ)."""
    if name in _CODES:
        return _CODES[name]
    letters = "".join(c for c in name.upper() if c.isalpha())
    words = [w for w in re.split(r"[^A-Za-z]+", name.upper()) if w]
    cands = []
    if len(words) > 1:
        cands.append(words[0][0] + words[-1][:2])
        cands.append("".join(w[0] for w in words[:3]).ljust(3, "X")[:3])
    cands.append(letters[:3])
    for i in range(0, max(1, len(letters) - 2)):
        cands.append(letters[i:i + 3])
    used = set(_CODES.values())
    for c in cands:
        if len(c) == 3 and c not in used:
            _CODES[name] = c
            return c
    c = f"{len(_CODES):03d}"
    _CODES[name] = c
    return c


class SyntheticWorld:
    def __init__(self, seed: int = 42, leagues: tuple[str, ...] = ("epl", "laliga", "bundesliga", "seriea", "ligue1", "mls"),
                 window_start: date = date(2026, 7, 20), window_end: date = date(2026, 9, 6)):
        self.rng = random.Random(seed)
        self.leagues = leagues
        self.window_start, self.window_end = window_start, window_end
        self.strength: dict[tuple[str, str], tuple[float, float]] = {}
        for lg in leagues:
            for t in TEAMS[lg]:
                self.strength[(lg, t[0])] = (self.rng.gauss(0, 0.32), self.rng.gauss(0, 0.25))
        self.matches: list[dict] = []   # dicts with league, kickoff, home/away tuples, goals, true probs, odds, venue prices

    # ---------------------------------------------------------------- schedule
    def _round_robin(self, teams: list) -> list[list[tuple]]:
        t = list(teams)
        if len(t) % 2:
            t.append(None)
        n = len(t)
        rounds = []
        for r in range(n - 1):
            pairs = []
            for i in range(n // 2):
                a, b = t[i], t[n - 1 - i]
                if a is None or b is None:
                    continue
                pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
            rounds.append(pairs)
            t = [t[0]] + [t[-1]] + t[1:-1]
        return rounds + [[(b, a) for a, b in rd] for rd in rounds]

    def build(self) -> "SyntheticWorld":
        for lg in self.leagues:
            teams = TEAMS[lg]
            rounds = self._round_robin(teams)
            # warm-up season (previous season / earlier in MLS season) every 7 days
            d = WARMUP_START[lg]
            stop = date(2026, 5, 24) if lg != "mls" else self.window_start - timedelta(days=1)
            i = 0
            while d <= stop and i < len(rounds):
                if not (date(2025, 12, 24) <= d <= date(2026, 1, 3)) and not (date(2026, 6, 8) <= d <= date(2026, 7, 19)):
                    self._make_round(lg, rounds[i], d, priced=False)
                    i += 1
                d += timedelta(days=7)
            # window matchdays
            d = SEASON_START[lg]
            i = 0
            order = self._round_robin(list(reversed(teams)))  # reshuffled pairings for the new season
            while d <= self.window_end and i < len(order):
                if not (lg != "mls" and date(2026, 8, 31) <= d <= date(2026, 9, 8)):  # international break
                    self._make_round(lg, order[i], d, priced=True)
                    i += 1
                d += timedelta(days=7)
            # one upcoming matchday (unplayed, open markets) for the picks demo
            d = self.window_end + timedelta(days=(5 - self.window_end.weekday()) % 7 or 7)
            if i < len(order):
                self._make_round(lg, order[i], d, priced=True, upcoming=True)
        self.matches.sort(key=lambda m: m["kickoff"])
        return self

    def _make_round(self, lg: str, pairs, d: date, priced: bool, upcoming: bool = False) -> None:
        rng = self.rng
        hours = KICKOFF_HOURS[lg]
        for k, (home, away) in enumerate(pairs):
            hour = hours[k % len(hours)]
            day_shift = 1 if lg == "mls" and hour < 5 else 0
            kickoff = datetime(d.year, d.month, d.day, hour, 0, tzinfo=timezone.utc) + timedelta(days=day_shift)
            if k % 4 == 3:
                kickoff += timedelta(days=1)  # some Sunday games
            ah, dh = self.strength[(lg, home[0])]
            aa, da = self.strength[(lg, away[0])]
            mu, hadv = 1.38, 1.12
            lh = mu * math.exp(ah - da) * hadv
            la = mu * math.exp(aa - dh) / hadv
            mat = _poisson_grid(lh, la)
            true = _three_way(mat)
            hg, ag = _sample_score(rng, mat)
            m = {"league": lg, "kickoff": kickoff, "home": home, "away": away, "hg": hg, "ag": ag, "true": true,
                 "odds": {}, "venue": None, "espn_id": f"{700000 + len(self.matches)}", "upcoming": upcoming}
            for key, margin in MARGINS.items():
                noise = 0.06 if key.endswith("c") or key in ("psc",) else 0.10
                m["odds"][key] = _odds_with_margin(true, margin, rng, noise)
            if priced:
                m["venue"] = self._venue_prices(true, rng)
            self.matches.append(m)

    def _venue_prices(self, true, rng: random.Random) -> dict:
        """Kalshi-style YES prices with planted biases: draws ~4pt cheap, longshots ~2.5pt rich, favourites ~2.5pt cheap."""
        out = {}
        for o, p in zip(("home", "draw", "away"), true):
            x = _sigmoid(_logit(p) + rng.gauss(0, 0.22)) + 0.012   # venue overround ~ +2-4 pts across 3 legs
            if o == "draw":
                x -= 0.04
            if p < 0.20:
                x += 0.025
            elif p > 0.60:
                x -= 0.025
            x = min(max(x, 0.02), 0.97)
            spread = rng.choice([0.01, 0.02, 0.02, 0.03])
            last = round(x, 2)
            out[o] = {"last": last, "bid": max(0.01, round(last - spread / 2 - 0.005, 2)), "ask": min(0.99, round(last + spread / 2 + 0.005, 2)),
                      "volume": int(rng.lognormvariate(6.5, 0.8))}
        return out


# ---------------------------------------------------------------- writers
def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_espn(world: SyntheticWorld, root: Path) -> None:
    by_day: dict[tuple[str, date], list[dict]] = {}
    for m in world.matches:
        lg = LEAGUES[m["league"]]
        by_day.setdefault((lg.espn, m["kickoff"].date()), []).append(m)
    for (code, d), ms in by_day.items():
        events = []
        for m in ms:
            up = m.get("upcoming", False)
            events.append({
                "id": m["espn_id"], "date": _iso(m["kickoff"]), "name": f"{m['home'][0]} at {m['away'][0]}",
                "competitions": [{
                    "id": m["espn_id"], "date": _iso(m["kickoff"]), "neutralSite": False,
                    "competitors": [
                        {"homeAway": "home", "winner": (m["hg"] > m["ag"]) if not up else False, "score": "" if up else str(m["hg"]),
                         "team": {"displayName": m["home"][0], "shortDisplayName": m["home"][0], "abbreviation": _code(m["home"][0])}},
                        {"homeAway": "away", "winner": (m["ag"] > m["hg"]) if not up else False, "score": "" if up else str(m["ag"]),
                         "team": {"displayName": m["away"][0], "shortDisplayName": m["away"][0], "abbreviation": _code(m["away"][0])}},
                    ],
                    "status": {"type": {"name": "STATUS_SCHEDULED" if up else "STATUS_FULL_TIME", "completed": not up,
                                        "state": "pre" if up else "post"}},
                    "odds": [{"provider": {"name": "synthetic"}, "details": "", "overUnder": 2.5,
                              "homeTeamOdds": {"moneyLine": _decimal_to_american(m["odds"]["b365"][0])},
                              "awayTeamOdds": {"moneyLine": _decimal_to_american(m["odds"]["b365"][2])},
                              "drawOdds": {"moneyLine": _decimal_to_american(m["odds"]["b365"][1])}}],
                }],
            })
        p = root / "espn" / code / f"{d:%Y%m%d}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"events": events}), encoding="utf-8")


def _decimal_to_american(dec: float) -> int:
    dec = max(dec, 1.01)
    return int(round((dec - 1) * 100)) if dec >= 2 else int(round(-100 / (dec - 1)))


def write_fdcouk(world: SyntheticWorld, root: Path) -> None:
    from zoneinfo import ZoneInfo

    london = ZoneInfo("Europe/London")
    cols = ["Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "HTR"]
    odds_cols = []
    for key in ("B365", "PS", "Max", "Avg", "B365C", "PSC", "MaxC", "AvgC"):
        odds_cols += [f"{key}H", f"{key}D", f"{key}A"]
    key_map = {"B365": "b365", "PS": "ps", "Max": "max", "Avg": "avg", "B365C": "b365c", "PSC": "psc", "MaxC": "maxc", "AvgC": "avgc"}
    for lg_key in world.leagues:
        lg = LEAGUES[lg_key]
        if not lg.fdcouk:
            continue
        seasons: dict[str, list[str]] = {}
        for m in world.matches:
            if m["league"] != lg_key:
                continue
            season = "fixtures" if m.get("upcoming") else "2627" if m["kickoff"].date() >= date(2026, 7, 1) else "2526"
            local = m["kickoff"].astimezone(london)
            ftr = "H" if m["hg"] > m["ag"] else "A" if m["hg"] < m["ag"] else "D"
            if m.get("upcoming"):
                row = [lg.fdcouk, local.strftime("%d/%m/%Y"), local.strftime("%H:%M"), m["home"][1], m["away"][1], "", "", "", "", "", ""]
            else:
                row = [lg.fdcouk, local.strftime("%d/%m/%Y"), local.strftime("%H:%M"), m["home"][1], m["away"][1],
                       str(m["hg"]), str(m["ag"]), ftr, "", "", ""]
            for key in ("B365", "PS", "Max", "Avg", "B365C", "PSC", "MaxC", "AvgC"):
                row += [f"{v:.2f}" for v in m["odds"][key_map[key]]]
            seasons.setdefault(season, []).append(",".join(row))
        for season, lines in seasons.items():
            if season == "fixtures":
                p = root / "fdcouk" / "fixtures.csv"
                p.parent.mkdir(parents=True, exist_ok=True)
                existing = p.read_text(encoding="utf-8") if p.exists() else ",".join(cols + odds_cols) + "\n"
                p.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")
                continue
            p = root / "fdcouk" / season / f"{lg.fdcouk}.csv"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(",".join(cols + odds_cols) + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def write_kalshi(world: SyntheticWorld, root: Path) -> None:
    rng = random.Random(99)
    markets_by_series: dict[str, list[dict]] = {}
    open_by_series: dict[str, list[dict]] = {}
    for m in world.matches:
        if not m["venue"]:
            continue
        if m.get("upcoming"):
            _write_open_market(world, m, open_by_series, rng)
            continue
        lg = LEAGUES[m["league"]]
        series = lg.kalshi_series
        kick = m["kickoff"]
        date_code = kick.strftime("%y%b%d").upper()
        # Kalshi lists many US-sport events as "Away at Home"; flip order for some to prove orientation is inferred
        first, second = (m["home"], m["away"]) if rng.random() < 0.7 else (m["away"], m["home"])
        event = f"{series}-{date_code}{_code(first[2])}{_code(second[2])}"
        title = f"{first[2]} vs {second[2]}" if first is m["home"] else f"{first[2]} at {second[2]}"
        open_time, close_time = kick - timedelta(days=6), kick + timedelta(hours=2, minutes=15)
        result = "home" if m["hg"] > m["ag"] else "away" if m["hg"] < m["ag"] else "draw"
        for o, label, suffix in (("home", m["home"][2], _code(m["home"][2])), ("draw", "Tie", "TIE"), ("away", m["away"][2], _code(m["away"][2]))):
            v = m["venue"][o]
            ticker = f"{event}-{suffix}"
            settled_yes = result == o
            mk = {
                "ticker": ticker, "event_ticker": event, "market_type": "binary", "title": f"{title} Winner?",
                "subtitle": label, "yes_sub_title": label, "no_sub_title": "", "status": "settled",
                "result": "yes" if settled_yes else "no", "open_time": _iso(open_time), "close_time": _iso(close_time),
                "expiration_time": _iso(close_time + timedelta(hours=1)), "settlement_ts": _iso(close_time + timedelta(minutes=30)),
                "yes_bid": 99 if settled_yes else 0, "yes_ask": 100 if settled_yes else 1, "last_price": 100 if settled_yes else 0,
                "yes_bid_dollars": "0.99" if settled_yes else "0.00", "volume": v["volume"], "open_interest": 0,
            }
            markets_by_series.setdefault(series, []).append(mk)
            _write_trades_and_candles(root, ticker, v, open_time, kick, close_time, settled_yes, rng)
    for series, ms in markets_by_series.items():
        p = root / "kalshi" / "markets" / f"{series}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"markets": ms, "cursor": ""}), encoding="utf-8")
    for series, ms in open_by_series.items():
        p = root / "kalshi" / "open" / f"{series}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"markets": ms, "cursor": ""}), encoding="utf-8")


def _write_open_market(world: SyntheticWorld, m: dict, open_by_series: dict, rng: random.Random) -> None:
    lg = LEAGUES[m["league"]]
    series = lg.kalshi_series
    kick = m["kickoff"]
    date_code = kick.strftime("%y%b%d").upper()
    event = f"{series}-{date_code}{_code(m['home'][2])}{_code(m['away'][2])}"
    title = f"{m['home'][2]} vs {m['away'][2]}"
    for o, label, suffix in (("home", m["home"][2], _code(m["home"][2])), ("draw", "Tie", "TIE"), ("away", m["away"][2], _code(m["away"][2]))):
        v = m["venue"][o]
        bid, ask, last = int(round(v["bid"] * 100)), int(round(v["ask"] * 100)), int(round(v["last"] * 100))
        open_by_series.setdefault(series, []).append({
            "ticker": f"{event}-{suffix}", "event_ticker": event, "market_type": "binary", "title": f"{title} Winner?",
            "subtitle": label, "yes_sub_title": label, "status": "open", "result": "",
            "open_time": _iso(kick - timedelta(days=6)), "close_time": _iso(kick + timedelta(hours=2, minutes=15)),
            "yes_bid": bid, "yes_ask": ask, "last_price": last, "yes_bid_dollars": f"{v['bid']:.2f}",
            "yes_ask_dollars": f"{v['ask']:.2f}", "last_price_dollars": f"{v['last']:.2f}",
            "volume": v["volume"], "open_interest": rng.randint(50, 2000),
        })


def _write_trades_and_candles(root: Path, ticker: str, v: dict, open_time: datetime, kick: datetime,
                              close_time: datetime, settled_yes: bool, rng: random.Random) -> None:
    trades = []
    n = max(8, int(v["volume"] / 40))
    # random walk that ends at the pre-kickoff last price
    price = min(max(v["last"] + rng.gauss(0, 0.05), 0.03), 0.97)
    span = (kick - open_time).total_seconds()
    times = sorted(open_time + timedelta(seconds=rng.random() * span * 0.995) for _ in range(n))
    for i, t in enumerate(times):
        frac = (i + 1) / n
        price = price + (v["last"] - price) * frac * 0.6 + rng.gauss(0, 0.012)
        p = min(max(round(price, 2), 0.01), 0.99)
        if i == n - 1:
            p = v["last"]
        cents = int(round(p * 100))
        trades.append({"trade_id": f"{ticker}-{i}", "ticker": ticker, "count": rng.randint(1, 60), "yes_price": cents,
                       "no_price": 100 - cents, "yes_price_dollars": f"{p:.2f}", "no_price_dollars": f"{1 - p:.2f}",
                       "taker_side": rng.choice(["yes", "no"]), "created_time": _iso(t)})
    # in-play trades after kickoff drift toward settlement; the snapshot logic must ignore these
    for j in range(5):
        t = kick + timedelta(minutes=10 + j * 18)
        p = min(max((0.95 if settled_yes else 0.05) * (j + 1) / 5 + v["last"] * (4 - j) / 5, 0.01), 0.99)
        cents = int(round(p * 100))
        trades.append({"trade_id": f"{ticker}-live{j}", "ticker": ticker, "count": rng.randint(1, 30), "yes_price": cents,
                       "no_price": 100 - cents, "yes_price_dollars": f"{p:.2f}", "no_price_dollars": f"{1 - p:.2f}",
                       "taker_side": "yes", "created_time": _iso(t)})
    p = root / "kalshi" / "trades" / f"{ticker}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"trades": trades, "cursor": ""}), encoding="utf-8")

    candles = []
    spread = v["ask"] - v["bid"]
    pre_trades = [(datetime.fromisoformat(t["created_time"].replace("Z", "+00:00")), t["yes_price"] / 100) for t in trades
                  if not t["trade_id"].endswith(tuple(f"live{j}" for j in range(5)))]
    t = kick - timedelta(hours=48)
    while t <= close_time:
        pre = t <= kick
        if pre:
            # quotes track the tape: mid = last trade before this hour, so entry and closing quotes differ
            before = [px for ts, px in pre_trades if ts <= t]
            mid = before[-1] if before else v["last"]
            bid = max(0.01, round(mid - spread / 2, 2))
            ask = min(0.99, round(mid + spread / 2, 2))
            last = mid
        else:
            bid = 0.9 if settled_yes else 0.02
            ask = 0.95 if settled_yes else 0.05
            last = (bid + ask) / 2
        candles.append({
            "end_period_ts": int(t.timestamp()),
            "yes_bid": {"open": int(bid * 100), "low": int(bid * 100) - 1, "high": int(bid * 100), "close": int(round(bid * 100)),
                        "close_dollars": f"{bid:.2f}"},
            "yes_ask": {"open": int(ask * 100), "low": int(ask * 100), "high": int(ask * 100) + 1, "close": int(round(ask * 100)),
                        "close_dollars": f"{ask:.2f}"},
            "price": {"open": int(last * 100), "low": int(last * 100) - 1, "high": int(last * 100) + 1, "close": int(round(last * 100)),
                      "mean": int(last * 100), "previous": int(last * 100)},
            "volume": rng.randint(0, 40), "open_interest": rng.randint(100, 3000),
        })
        t += timedelta(hours=1)
    p = root / "kalshi" / "candles" / f"{ticker}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ticker": ticker, "candlesticks": candles}), encoding="utf-8")


def generate(root: str | Path, seed: int = 42, leagues=("epl", "laliga", "bundesliga", "seriea", "ligue1", "mls")) -> SyntheticWorld:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    world = SyntheticWorld(seed=seed, leagues=tuple(leagues)).build()
    write_espn(world, root)
    write_fdcouk(world, root)
    write_kalshi(world, root)
    (root / "README.txt").write_text(
        "SYNTHETIC DEMO DATA generated by `rsa demo`. Shapes mirror the live Kalshi / ESPN / "
        "football-data.co.uk responses, but every price and score is simulated. Do not trade on it.\n", encoding="utf-8")
    return world


# ---------------------------------------------------------------- offline client
class DemoKalshiClient(KalshiClient):
    """Serves the synthetic Kalshi files instead of hitting the network."""

    def __init__(self, root: str | Path):
        super().__init__(cache_dir=None, requests_per_second=0)
        self.root = Path(root) / "kalshi"

    def soccer_series(self) -> list[dict]:
        return [{"ticker": p.stem, "title": f"{p.stem} (demo)"} for p in sorted((self.root / "markets").glob("*.json"))]

    def historical_cutoff(self) -> dict:
        return {}

    def settled_markets_since(self, series_ticker: str, since_ts: int) -> list[dict]:
        p = self.root / "markets" / f"{series_ticker}.json"
        if not p.exists():
            return []
        ms = json.loads(p.read_text(encoding="utf-8"))["markets"]
        return [m for m in ms if datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp() >= since_ts]

    def open_markets(self, series_ticker: str) -> list[dict]:
        p = self.root / "open" / f"{series_ticker}.json"
        return json.loads(p.read_text(encoding="utf-8"))["markets"] if p.exists() else []

    def get(self, path, params=None, *, cacheable=True):
        # the only live GET the picks flow makes is the recent-trades peek; serve nothing (no tape for open markets)
        if path == "/markets/trades":
            return {"trades": [], "cursor": ""}
        raise RuntimeError(f"DemoKalshiClient is offline; attempted GET {path}")

    def trades(self, ticker: str, min_ts=None, max_ts=None) -> list[dict]:
        p = self.root / "trades" / f"{ticker}.json"
        if not p.exists():
            return []
        out = []
        for t in json.loads(p.read_text(encoding="utf-8"))["trades"]:
            ts = datetime.fromisoformat(t["created_time"].replace("Z", "+00:00")).timestamp()
            if (min_ts is None or ts >= min_ts) and (max_ts is None or ts <= max_ts):
                out.append(t)
        return out

    def candlesticks(self, series_ticker: str, ticker: str, start_ts: int, end_ts: int, period_interval: int = 60) -> list[dict]:
        p = self.root / "candles" / f"{ticker}.json"
        if not p.exists():
            return []
        return [c for c in json.loads(p.read_text(encoding="utf-8"))["candlesticks"] if start_ts <= c["end_period_ts"] <= end_ts]


def demo_fetch(root: str | Path):
    """A ``fetch(url) -> text`` function that maps ESPN / football-data URLs onto the demo files."""
    import re

    root = Path(root)

    def fetch(url: str) -> str:
        m = re.search(r"/soccer/([^/]+)/scoreboard\?dates=(\d{8})", url)
        if m:
            p = root / "espn" / m.group(1) / f"{m.group(2)}.json"
            return p.read_text(encoding="utf-8") if p.exists() else '{"events": []}'
        if url.endswith("/fixtures.csv"):
            p = root / "fdcouk" / "fixtures.csv"
            return p.read_text(encoding="utf-8") if p.exists() else "Div,Date,Time,HomeTeam,AwayTeam\n"
        m = re.search(r"/mmz4281/(\d{4})/([A-Z0-9]+)\.csv", url)
        if m:
            p = root / "fdcouk" / m.group(1) / f"{m.group(2)}.csv"
            if not p.exists():
                raise FileNotFoundError(url)
            return p.read_text(encoding="utf-8")
        raise ValueError(f"demo fetch cannot serve {url}")

    return fetch
