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
from datetime import datetime, timezone
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

    def rating(self, team: str) -> float:
        return self.ratings.get(canonical(team), self.initial)

    def predict(self, home: str, away: str, neutral: bool = False) -> Probs:
        rh = self.rating(home) + (0.0 if neutral else self.home_adv)
        ra = self.rating(away)
        ph, pa = 10 ** (rh / 400), 10 ** (ra / 400)
        d = self.nu * math.sqrt(ph * pa)
        tot = ph + pa + d
        return ph / tot, d / tot, pa / tot

    def update(self, home: str, away: str, home_goals: int, away_goals: int, neutral: bool = False) -> float:
        p_h, p_d, _ = self.predict(home, away, neutral)
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
        return delta

    def fit(self, matches: Iterable[Match]) -> "Elo":
        for m in sorted((x for x in matches if x.completed), key=lambda x: x.kickoff or datetime.min.replace(tzinfo=timezone.utc)):
            self.update(m.home, m.away, m.home_goals, m.away_goals, bool(m.extra.get("neutral")))
        return self


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


def walk_forward(matches_window: list[Match], warmup: list[Match], elo: Elo | None = None,
                 poisson: PoissonModel | None = None) -> dict[str, dict[str, Probs]]:
    """Predict every window match using only earlier results (warm-up + earlier window matches).

    Returns ``{match_id: {"elo": (h,d,a), "poisson": (h,d,a)}}``. The Poisson
    model is refitted once per distinct kickoff date.
    """
    elo = elo or Elo()
    poisson = poisson or PoissonModel()
    history = sorted([m for m in warmup if m.completed and m.kickoff], key=lambda m: m.kickoff)
    elo.fit(history)
    window = sorted([m for m in matches_window if m.kickoff], key=lambda m: m.kickoff)
    preds: dict[str, dict[str, Probs]] = {}
    last_fit_day = None
    pending: list[Match] = []
    for m in window:
        day = m.kickoff.date()
        if day != last_fit_day:
            history.extend(pending)
            pending = []
            poisson.fit(history, as_of=m.kickoff.replace(hour=0, minute=0, second=0, microsecond=0))
            last_fit_day = day
        preds[m.match_id] = {
            "elo": elo.predict(m.home, m.away, bool(m.extra.get("neutral"))),
            "poisson": poisson.predict(m.home, m.away, bool(m.extra.get("neutral"))),
        }
        if m.completed:
            # Elo updates per match; Poisson refits per day from the growing history
            elo.update(m.home, m.away, m.home_goals, m.away_goals, bool(m.extra.get("neutral")))
            pending.append(m)
    return preds
