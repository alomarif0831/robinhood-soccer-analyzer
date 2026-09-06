from datetime import datetime, timedelta, timezone

import pytest

from rsa.models import Elo, PoissonModel, blend, walk_forward
from rsa.results import Match

T0 = datetime(2026, 1, 3, 15, 0, tzinfo=timezone.utc)


def _m(i, home, away, hg, ag, league="epl"):
    return Match(league, f"m{i}", T0 + timedelta(days=i), home, away, hg, ag, True, "t")


def test_elo_probabilities_sum_and_favor_stronger_team():
    e = Elo()
    p = e.predict("A", "B")
    assert sum(p) == pytest.approx(1.0)
    assert p[0] > p[2]  # home advantage
    e.ratings["a"] = 1700
    q = e.predict("A", "B")
    assert q[0] > p[0] and q[1] < p[1]


def test_elo_update_moves_ratings_and_uses_margin():
    e = Elo()
    d1 = e.update("A", "B", 1, 0)
    e2 = Elo()
    d2 = e2.update("A", "B", 4, 0)
    assert d1 > 0 and d2 > d1
    assert e.rating("A") == pytest.approx(1500 + d1) and e.rating("B") == pytest.approx(1500 - d1)


def test_poisson_fit_and_predict():
    ms = []
    i = 0
    for _ in range(12):
        ms += [_m(i, "Strong", "Weak", 3, 0), _m(i + 1, "Weak", "Strong", 0, 2), _m(i + 2, "Mid", "Weak", 1, 1),
               _m(i + 3, "Strong", "Mid", 2, 1)]
        i += 4
    pm = PoissonModel().fit(ms)
    p = pm.predict("Strong", "Weak")
    assert sum(p) == pytest.approx(1.0) and p[0] > 0.6
    q = pm.predict("Weak", "Strong")
    assert q[2] > q[0]
    assert pm.attack["strong"] > pm.attack["weak"]
    assert pm.predict("Unknown", "Alsounknown")[0] > 0.3  # unseen teams get average strength


def test_blend_and_walk_forward_only_use_past():
    assert sum(blend((0.5, 0.3, 0.2), (0.2, 0.3, 0.5), 0.5)) == pytest.approx(1.0)
    warm = [_m(i, "A", "B", 2, 0) for i in range(0, 10, 2)] + [_m(i, "B", "A", 0, 1) for i in range(1, 10, 2)]
    window = [Match("epl", "w1", T0 + timedelta(days=30), "B", "A", 5, 0, True, "t"),
              Match("epl", "w2", T0 + timedelta(days=37), "A", "B", 0, 0, True, "t")]
    preds = walk_forward(window, warm)
    assert set(preds) == {"w1", "w2"}
    # A dominated the warm-up so w1 (B at home) still favors A before B's 5-0 is seen
    assert preds["w1"]["elo"][2] > preds["w1"]["elo"][0]
    # after B's 5-0, A at home is rated lower than an Elo that never saw that result
    assert preds["w2"]["elo"][0] < Elo().fit(warm).predict("A", "B")[0]
