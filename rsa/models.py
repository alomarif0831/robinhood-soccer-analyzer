"""Reference probability models used to judge whether the market price is off.

* :class:`Elo` - Elo ratings with home advantage and a Davidson draw term.
* :class:`PoissonModel` - time-decayed attack/defence strengths with a
  Dixon-Coles low-score correction.
* :func:`blend` - mixes a model with the bookmaker consensus.

All models are fitted strictly on matches that kicked off before the match
being predicted (walk-forward), so backtest probabilities never peek at results.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .results import Match
from .teams import canonical

Probs = tuple[float, float, float]


class Elo:
    """Elo with a Davidson draw parameter.

    With strengths ``ph = 10**(rh/400)``, ``pa = 10**(ra/400)`` and draw weight
    ``nu``: P(home) = ph / (ph + pa + nu*sqrt(ph*pa)) etc. ``nu=0.7`` gives a
    26% draw rate between equal teams, in line with big-five league averages.
    """

    def __init__(self, k: float = 20.0, home_adv: float = 60.0, nu: float = 0.7, initial: float = 1500.0):
        self.k, self.home_adv, self.nu, self.initial = k, home_adv, nu, initial
        self.ratings: dict[str, float] = {}
        self.games: dict[str, int] = defaultdict(int)
        self.home_adv_by_league: dict[str, float] = {}
        self.league_of: dict[str, str] = {}
        self.last_kickoff: dict[str, datetime] = {}

    SEASON_GAP_DAYS = 60   # above any winter/World-Cup pause, below every real off-season

    def rating(self, team: str) -> float:
        return self.ratings.get(canonical(team), self.initial)

    def _home_adv(self, league: str | None) -> float:
        return self.home_adv_by_league.get(league, self.home_adv) if league else self.home_adv

    def predict(self, home: str, away: str, neutral: bool = False, league: str | None = None) -> Probs:
        rh = self.rating(home) + (0.0 if neutral else self._home_adv(league))
        ra = self.rating(away)
        ph, pa = 10 ** (rh / 400), 10 ** (ra / 400)
        d = self.nu * math.sqrt(ph * pa)
        tot = ph + pa + d
        return ph / tot, d / tot, pa / tot

    def update(self, home: str, away: str, home_goals: int, away_goals: int, neutral: bool = False,
               league: str | None = None) -> float:
        p_h, p_d, _ = self.predict(home, away, neutral, league)
        expected = p_h + 0.5 * p_d
        actual = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
        gd = abs(home_goals - away_goals)
        mult = 1.0 if gd <= 1 else 1.5 if gd == 2 else 1.75 + (gd - 3) / 8
        delta = self.k * mult * (actual - expected)
        h, a = canonical(home), canonical(away)
        self.ratings[h] = self.rating(home) + delta
        self.ratings[a] = self.rating(away) - delta
        self.games[h] += 1
        self.games[a] += 1
        if league:
            self.league_of[h] = league
            self.league_of[a] = league
        return delta

    def observe(self, m: Match) -> None:
        """Season-boundary bookkeeping for one match in kickoff order: regress the league when its last
        match was more than a season gap ago, seed unseen teams, and remember the kickoff."""
        if m.kickoff is None:
            return
        last = self.last_kickoff.get(m.league)
        if last is not None and (m.kickoff - last).days > self.SEASON_GAP_DAYS:
            self.regress_league(m.league)
        for team in (m.home, m.away):
            self.seed_team(team, m.league)
        self.last_kickoff[m.league] = max(last, m.kickoff) if last else m.kickoff

    def regress_league(self, league: str, regress: float = 0.75) -> None:
        teams = [t for t, lg in self.league_of.items() if lg == league]
        if not teams:
            return
        mean = sum(self.ratings[t] for t in teams) / len(teams)
        for t in teams:
            self.ratings[t] = mean + regress * (self.ratings[t] - mean)

    def seed_team(self, team: str, league: str, regress: float = 0.75) -> None:
        """A team unseen in a league with ratings starts at the level of the three lowest-rated teams
        (a proxy for the relegated sides), regressed like everyone else."""
        key = canonical(team)
        if key in self.ratings:
            return
        teams = [t for t, lg in self.league_of.items() if lg == league]
        if len(teams) < 3:
            return
        rs = sorted(self.ratings[t] for t in teams)
        mean = sum(rs) / len(rs)
        self.ratings[key] = mean + regress * (sum(rs[:3]) / 3 - mean)
        self.league_of[key] = league

    def fit(self, matches: Iterable[Match]) -> "Elo":
        for m in sorted((x for x in matches if x.completed), key=lambda x: x.kickoff or datetime.min.replace(tzinfo=timezone.utc)):
            self.observe(m)
            self.update(m.home, m.away, m.home_goals, m.away_goals, bool(m.extra.get("neutral")), m.league)
        return self

    def calibrate_home_advantage(self, matches: list[Match], grid: tuple[float, ...] = tuple(range(0, 125, 10))) -> dict[str, float]:
        """Per-league home advantage so the walk-forward predicted home-win share matches the observed share."""
        by_league: dict[str, list[Match]] = {}
        for m in matches:
            if m.completed and m.kickoff:
                by_league.setdefault(m.league, []).append(m)
        for lg, ms in by_league.items():
            if len(ms) < 60:
                continue
            ms.sort(key=lambda x: x.kickoff)
            observed = sum(1 for m in ms if m.home_goals > m.away_goals) / len(ms)
            best = None
            for h in grid:
                trial = Elo(self.k, h, self.nu, self.initial)
                pred = 0.0
                for m in ms:
                    pred += trial.predict(m.home, m.away, bool(m.extra.get("neutral")))[0]
                    trial.update(m.home, m.away, m.home_goals, m.away_goals, bool(m.extra.get("neutral")))
                gap = abs(pred / len(ms) - observed)
                if best is None or gap < best[0]:
                    best = (gap, h)
            self.home_adv_by_league[lg] = float(best[1])
        return self.home_adv_by_league

    def season_boundary(self, upcoming: Iterable[Match], regress: float = 0.75) -> None:
        """Apply :meth:`observe` to upcoming fixtures: regresses a league across a real season gap and
        seeds unseen (promoted) teams. Idempotent for fixtures inside the same season."""
        for m in sorted((x for x in upcoming if x.kickoff), key=lambda x: x.kickoff):
            self.observe(m)


class PoissonModel:
    """Independent Poisson goals with multiplicative attack/defence strengths.

    Strengths are fitted by iterative proportional fitting on exponentially
    time-weighted results (half-life in days). Scoreline probabilities get the
    Dixon-Coles adjustment ``rho`` for 0-0, 1-0, 0-1 and 1-1.
    """

    def __init__(self, halflife_days: float = 120.0, rho: float = -0.08, max_goals: int = 10, iters: int = 25):
        self.halflife, self.rho, self.max_goals, self.iters = halflife_days, rho, max_goals, iters
        self.attack: dict[str, float] = {}
        self.defence: dict[str, float] = {}
        self.mu = 1.35          # average goals per team per game
        self.home_adv = 1.15    # multiplicative home boost
        self.n_fit = 0

    def fit(self, matches: Iterable[Match], as_of: datetime | None = None) -> "PoissonModel":
        rows = []
        for m in matches:
            if not m.completed or m.kickoff is None:
                continue
            if as_of is not None and m.kickoff >= as_of:
                continue
            rows.append(m)
        if not rows:
            return self
        as_of = as_of or max(m.kickoff for m in rows)
        w = [0.5 ** (max(0.0, (as_of - m.kickoff).total_seconds() / 86400) / self.halflife) for m in rows]
        teams = {canonical(m.home) for m in rows} | {canonical(m.away) for m in rows}
        att = {t: 1.0 for t in teams}
        dfn = {t: 1.0 for t in teams}
        tot_w = sum(w)
        hg = sum(wi * m.home_goals for wi, m in zip(w, rows))
        ag = sum(wi * m.away_goals for wi, m in zip(w, rows))
        self.mu = (hg + ag) / (2 * tot_w)
        self.home_adv = (hg / ag) if ag > 0 else 1.15
        h = math.sqrt(self.home_adv)     # split home advantage symmetrically
        for _ in range(self.iters):
            num_a, den_a = defaultdict(float), defaultdict(float)
            num_d, den_d = defaultdict(float), defaultdict(float)
            for wi, m in zip(w, rows):
                th, ta = canonical(m.home), canonical(m.away)
                num_a[th] += wi * m.home_goals
                den_a[th] += wi * self.mu * dfn[ta] * h
                num_a[ta] += wi * m.away_goals
                den_a[ta] += wi * self.mu * dfn[th] / h
                num_d[ta] += wi * m.home_goals
                den_d[ta] += wi * self.mu * att[th] * h
                num_d[th] += wi * m.away_goals
                den_d[th] += wi * self.mu * att[ta] / h
            for t in teams:
                # shrink toward 1.0 for teams with little weighted data
                att[t] = (num_a[t] + 2 * self.mu) / (den_a[t] + 2 * self.mu) if den_a[t] > 0 else 1.0
                dfn[t] = (num_d[t] + 2 * self.mu) / (den_d[t] + 2 * self.mu) if den_d[t] > 0 else 1.0
            ma = math.exp(sum(math.log(v) for v in att.values()) / len(att))
            md = math.exp(sum(math.log(v) for v in dfn.values()) / len(dfn))
            for t in teams:
                att[t] /= ma
                dfn[t] /= md
        self.attack, self.defence, self.n_fit = att, dfn, len(rows)
        return self

    def rates(self, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
        h = 1.0 if neutral else math.sqrt(self.home_adv)
        th, ta = canonical(home), canonical(away)
        lam_h = self.mu * self.attack.get(th, 1.0) * self.defence.get(ta, 1.0) * h
        lam_a = self.mu * self.attack.get(ta, 1.0) * self.defence.get(th, 1.0) / h
        return lam_h, lam_a

    def scoreline_matrix(self, home: str, away: str, neutral: bool = False) -> list[list[float]]:
        lh, la = self.rates(home, away, neutral)
        ph = [math.exp(-lh) * lh ** i / math.factorial(i) for i in range(self.max_goals + 1)]
        pa = [math.exp(-la) * la ** j / math.factorial(j) for j in range(self.max_goals + 1)]
        mat = [[ph[i] * pa[j] for j in range(self.max_goals + 1)] for i in range(self.max_goals + 1)]
        r = self.rho
        mat[0][0] *= 1 - lh * la * r
        mat[1][0] *= 1 + la * r
        mat[0][1] *= 1 + lh * r
        mat[1][1] *= 1 - r
        s = sum(map(sum, mat))
        return [[v / s for v in row] for row in mat]

    def predict(self, home: str, away: str, neutral: bool = False) -> Probs:
        mat = self.scoreline_matrix(home, away, neutral)
        n = len(mat)
        p_home = sum(mat[i][j] for i in range(n) for j in range(n) if i > j)
        p_draw = sum(mat[i][i] for i in range(n))
        return p_home, p_draw, 1.0 - p_home - p_draw


def blend(a: Probs, b: Probs, w: float) -> Probs:
    """Linear mix ``w*a + (1-w)*b`` renormalized."""
    p = [w * x + (1 - w) * y for x, y in zip(a, b)]
    s = sum(p)
    return tuple(x / s for x in p)  # type: ignore[return-value]


class ModelSet:
    """Elo (per-league home advantage, season-boundary regression) + one Poisson model per league."""

    def __init__(self, elo: Elo | None = None):
        self.elo = elo or Elo()
        self.poisson: dict[str, PoissonModel] = {}

    SEASON_GAP_DAYS = Elo.SEASON_GAP_DAYS

    def fit(self, history: list[Match], as_of: datetime | None = None, upcoming: list[Match] | None = None) -> "ModelSet":
        hist = sorted([m for m in history if m.completed and m.kickoff], key=lambda m: m.kickoff)
        self.elo.calibrate_home_advantage(hist)
        self.elo.fit(hist)
        if upcoming:
            self.elo.season_boundary(upcoming)   # regresses only leagues whose last match is > SEASON_GAP_DAYS ago
        self.refit_poisson(hist, as_of)
        return self

    @classmethod
    def new_season_fixtures(cls, history: list[Match], upcoming: list[Match]) -> list[Match]:
        """Upcoming fixtures of leagues whose last completed match is more than a season gap ago."""
        last: dict[str, datetime] = {}
        for m in history:
            if m.completed and m.kickoff and (m.league not in last or m.kickoff > last[m.league]):
                last[m.league] = m.kickoff
        first: dict[str, datetime] = {}
        for m in upcoming:
            if m.kickoff and (m.league not in first or m.kickoff < first[m.league]):
                first[m.league] = m.kickoff
        gap = {lg: (first[lg] - last[lg]).days for lg in first if lg in last}
        return [m for m in upcoming if m.league in gap and gap[m.league] > cls.SEASON_GAP_DAYS]

    def refit_poisson(self, history: list[Match], as_of: datetime | None = None) -> None:
        by_league: dict[str, list[Match]] = {}
        for m in history:
            by_league.setdefault(m.league, []).append(m)
        for lg, ms in by_league.items():
            self.poisson[lg] = PoissonModel().fit(ms, as_of=as_of)

    def predict(self, m: Match) -> dict[str, Probs]:
        neutral = bool(m.extra.get("neutral"))
        pm = self.poisson.get(m.league) or PoissonModel()
        return {"elo": self.elo.predict(m.home, m.away, neutral, m.league), "poisson": pm.predict(m.home, m.away, neutral)}


def walk_forward(matches_window: list[Match], warmup: list[Match], elo: Elo | None = None,
                 poisson: PoissonModel | None = None) -> dict[str, dict[str, Probs]]:
    """Predict every window match using only earlier results (warm-up + earlier window matches).

    Returns ``{match_id: {"elo": (h,d,a), "poisson": (h,d,a)}}``. Elo updates after
    every match; the per-league Poisson models are refitted once per kickoff date.
    Ratings are regressed toward the league mean at the warm-up/window boundary
    (a new season) and promoted teams start at the level of the relegated ones.
    """
    models = ModelSet(elo)
    history = sorted([m for m in warmup if m.completed and m.kickoff], key=lambda m: m.kickoff)
    window = sorted([m for m in matches_window if m.kickoff], key=lambda m: m.kickoff)
    models.fit(history)   # boundaries inside the window are detected match by match below
    preds: dict[str, dict[str, Probs]] = {}
    last_fit_day = None
    pending: list[Match] = []      # completed window matches not yet old enough to count as finished
    for m in window:
        day = m.kickoff.date()
        cutoff = m.kickoff - timedelta(minutes=150)
        done = [p for p in pending if p.kickoff <= cutoff]
        if done:
            history.extend(done)
            pending = [p for p in pending if p.kickoff > cutoff]
            for p in done:
                models.elo.update(p.home, p.away, p.home_goals, p.away_goals, bool(p.extra.get("neutral")), p.league)
        if day != last_fit_day or done:
            models.refit_poisson(history, as_of=m.kickoff)
            last_fit_day = day
        models.elo.observe(m)      # season gap -> regress that league; promoted teams seeded
        preds[m.match_id] = models.predict(m)
        if m.completed:
            pending.append(m)
    return preds
