import numpy as np
import pandas as pd
import pytest

from rsa.fees import NoFees, RobinhoodFees
from rsa.pro import (MIN_TRAIN, StakingRules, apply_pools, build_candidates, confidence_components, fit_final_pools, fit_pool,
                     kelly_fraction, log_probs, prior_fit, select_portfolio, summarize_pro, tier_for, tier_table,
                     walk_forward_pool)

OUT = ("home", "draw", "away")


def _synthetic_frame(n=400, seed=1, with_book=True, true_w=(0.9, 0.0, 0.3, 0.0)):
    """Rows whose results are drawn from a log-linear pool of the sources with known weights."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        base = rng.dirichlet([4, 3, 3])
        srcs = {}
        for name, noise in (("book", 0.1), ("mktn", 0.3), ("poisson", 0.25), ("elo", 0.4)):
            z = np.log(base) + rng.normal(0, noise, 3)
            p = np.exp(z) / np.exp(z).sum()
            srcs[name] = p
        logits = sum(w * np.log(srcs[s]) for w, s in zip(true_w, ("book", "mktn", "poisson", "elo")))
        truth = np.exp(logits) / np.exp(logits).sum()
        res = rng.choice(OUT, p=truth)
        row = {"match_id": f"m{i}", "league": "epl", "home": f"H{i}", "away": f"A{i}", "result": res,
               "kickoff": pd.Timestamp("2026-08-01", tz="UTC") + pd.Timedelta(days=i // 10),
               "snapshot_time": pd.Timestamp("2026-08-01", tz="UTC") + pd.Timedelta(days=i // 10)}
        for name, p in srcs.items():
            if name == "book" and not with_book:
                continue
            for o, v in zip(OUT, p):
                row[f"{name}_{o}"] = v
        for o, v in zip(OUT, srcs["mktn"]):
            row[f"mkt_{o}"] = v * 1.02
            row[f"bid_{o}"] = v * 1.02 - 0.01
            row[f"ask_{o}"] = v * 1.02 + 0.01
            row[f"vol_{o}"] = 500
            row[f"close_{o}"] = v * 1.02
            row[f"ltt_{o}"] = row["snapshot_time"]
        rows.append(row)
    return pd.DataFrame(rows)


def test_fit_pool_recovers_weights_and_beats_prior():
    df = _synthetic_frame(n=600)
    L = log_probs(df, ("book", "mktn", "poisson", "elo"))
    y = df["result"].map({o: i for i, o in enumerate(OUT)}).to_numpy()
    fit = fit_pool(L, y, "full", n_boot=20)
    w = fit.weights
    assert w["book"] > w["elo"] and w["book"] > w["mktn"]
    assert fit.W.shape == (21, 4) and (fit.W >= 0).all()
    fair, sd = fit.predict(L)
    assert np.allclose(fair.sum(axis=1), 1.0) and (sd >= 0.02).all()
    # fitted pool has lower log loss on its training data than the prior
    prior = prior_fit("full")
    ll = lambda P: -np.log(P[np.arange(len(y)), y]).mean()
    assert ll(fit.predict(L)[0]) < ll(prior.predict(L)[0])


def test_walk_forward_uses_only_earlier_matches():
    df = _synthetic_frame(n=300)
    out = walk_forward_pool(df, n_boot=5)
    assert out["pro_home"].notna().all()
    first_day = out["kickoff"].dt.date.min()
    assert (out.loc[out["kickoff"].dt.date == first_day, "pro_n_train"] == 0).all()   # prior weights on day 1
    assert out["pro_n_train"].max() >= MIN_TRAIN
    # changing the LAST day's results must not change any earlier prediction
    df2 = df.copy()
    last = df2["kickoff"] == df2["kickoff"].max()
    df2.loc[last, "result"] = "draw"
    out2 = walk_forward_pool(df2, n_boot=5)
    earlier = out["kickoff"] < out["kickoff"].max()
    assert np.allclose(out.loc[earlier, "pro_home"].to_numpy(), out2.loc[earlier, "pro_home"].to_numpy())


def test_pool_without_book_uses_nobook_set():
    df = _synthetic_frame(n=120, with_book=False)
    out = walk_forward_pool(df, n_boot=3)
    assert out["pro_home"].notna().all() and set(out["pro_set"]) == {"nobook"}
    pools = fit_final_pools(_synthetic_frame(n=200))
    priced = apply_pools(df, pools)
    assert priced["pro_home"].notna().all() and set(priced["pro_set"]) == {"nobook"}


def test_kelly_fraction():
    assert kelly_fraction(0.5, 0.5, 0.0) == 0.0            # fair price, no bet
    assert kelly_fraction(0.6, 0.5, 0.0) == pytest.approx(0.2)   # b=1 -> 2q-1
    assert kelly_fraction(0.6, 0.5, 0.05) < 0.2            # fees reduce it
    assert kelly_fraction(0.3, 0.5, 0.0) == 0.0            # negative edge -> zero
    assert kelly_fraction(0.9, 0.99, 0.02) == 0.0          # cost >= 1


def test_confidence_components_and_tiers():
    strong = confidence_components(edge=0.10, edge_sd=0.02, agreement=1.0, spread=0.01, volume=1000, price=0.4, stale_hours=2, n_train=100, team_games=10)
    weak = confidence_components(edge=0.01, edge_sd=0.05, agreement=0.0, spread=0.08, volume=10, price=0.05, stale_hours=100, n_train=0, team_games=2)
    total = lambda c: sum(v for k, v in c.items() if k != "data_support")
    assert total(strong) >= 90 and total(weak) < 20
    assert tier_for(total(strong)) == "A" and tier_for(total(weak)) == "pass"
    assert tier_for(60) == "B" and tier_for(45) == "C" and tier_for(44.9) == "pass"
    assert strong["data_support"] == 0.0 and weak["data_support"] < 0


def test_candidates_edges_and_clv_math():
    df = _synthetic_frame(n=60)
    df = walk_forward_pool(df, n_boot=3)
    fees = RobinhoodFees()
    c = build_candidates(df, fees, fill="ask")
    assert set(c["side"]) == {"yes", "no"} and (c["fair_sd"] >= 0.02).all()
    row = c.iloc[0]
    m = df[df["match_id"] == row["match_id"]].iloc[0]
    o = row["outcome"]
    if row["side"] == "yes":
        assert row["price"] == pytest.approx(m[f"ask_{o}"]) and row["fair"] == pytest.approx(m[f"pro_{o}"])
        assert row["clv_close"] == pytest.approx(m[f"close_{o}"] - m[f"ask_{o}"])
    else:
        assert row["price"] == pytest.approx(1 - m[f"bid_{o}"]) and row["fair"] == pytest.approx(1 - m[f"pro_{o}"])
    assert row["edge"] == pytest.approx(row["fair"] - row["price"] - fees.fee_per_contract(row["price"]))
    assert row["profit"] == pytest.approx((1 - row["price"] - row["fee"]) if row["won"] else -(row["price"] + row["fee"]))


def test_portfolio_rules_one_bet_per_match_and_caps():
    df = _synthetic_frame(n=80)
    df = walk_forward_pool(df, n_boot=3)
    c = build_candidates(df, NoFees(), fill="last")
    rules = StakingRules(bankroll=1000, kelly_fraction=0.5, max_bet_fraction=0.02, max_day_fraction=0.05, max_bets_per_day=3,
                         min_confidence=0, min_edge=0.0, min_edge_q20=-1, min_edge_mid=-1, min_book_edge=-1, min_contracts=1,
                         min_price=0.02, max_price=0.98)
    sel = select_portfolio(c, rules)
    assert not sel.empty
    assert sel["match_id"].is_unique
    per_day = sel.groupby(pd.to_datetime(sel["kickoff"]).dt.date)
    assert (per_day.size() <= 3).all()
    assert (per_day["stake_fraction"].sum() <= 0.05 + 1e-9).all()
    assert (sel["stake_fraction"] <= 0.02 + 1e-9).all()
    assert (sel["stake"] == (sel["contracts"] * sel["risked"]).round(2)).all()
    s = summarize_pro(sel, rules)
    assert s["n"] == len(sel) and "flat_roi" in s and 0 <= s["max_drawdown"] <= 1
    tt = tier_table(c)
    assert tt["n"].sum() == c["won"].notna().sum()
    strict = select_portfolio(c, StakingRules(min_confidence=101, min_edge=0.0))
    assert strict.empty
    # gates: a wide spread or an inconsistent three-way book removes the contract
    wide = c.copy()
    wide["spread"] = 0.2
    assert select_portfolio(wide, rules).empty
    bad = c.copy()
    bad["quotes_ok"] = False
    assert select_portfolio(bad, rules).empty


def test_picks_flow_on_synthetic_upcoming(tmp_path):
    from datetime import date, datetime, timezone

    from rsa.config import leagues_from_keys
    from rsa.pipeline import collect, collect_upcoming, run_picks, write_picks
    from rsa.synth import DemoKalshiClient, demo_fetch, generate

    root = tmp_path / "raw"
    generate(root, seed=5, leagues=["epl", "mls"])
    fetch = demo_fetch(root)
    client = DemoKalshiClient(root)
    leagues = leagues_from_keys(["epl", "mls"])
    bundle = collect(leagues, date(2026, 7, 20), date(2026, 9, 6), client, espn_fetch=fetch, fd_fetch=fetch, minutes_before_kickoff=360)
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    up = collect_upcoming(leagues, client, days=10, today=date(2026, 9, 7), espn_fetch=fetch, fd_fetch=fetch, now=now)
    assert up.matches and up.snapshots and all(not m.completed for m in up.matches)
    assert any("ps_home" in m.odds for m in up.matches if m.league == "epl")   # fixtures.csv odds merged
    res = run_picks(bundle, up, RobinhoodFees(), StakingRules(min_confidence=0, min_edge=-1, min_edge_q20=-1, min_edge_mid=-1,
                                                             min_book_edge=-1, min_contracts=1), "ask", now=now)
    assert not res["frame"].empty and res["history_n"] > 0
    assert res["frame"]["pro_home"].notna().all()
    assert not res["candidates"].empty and res["candidates"]["won"].isna().all()
    assert res["portfolio"]["match_id"].is_unique
    path = write_picks(res, up, tmp_path / "out", {"synthetic": True, "fee_model": "robinhood", "fill": "ask", "rules": StakingRules()})
    text = path.read_text(encoding="utf-8")
    assert "# Upcoming picks" in text and "SYNTHETIC" in text
    # entry snapshots 6h before kickoff give a measurable closing-line value in the backtest
    from rsa.backtest import run_backtest
    from rsa.pipeline import build_frame

    df, _ = build_frame(bundle)
    r = run_backtest(df, RobinhoodFees(), rules=StakingRules(min_confidence=0, min_edge=0.0, min_edge_q20=-1, min_edge_mid=-1,
                                                             min_book_edge=-1, min_contracts=1))
    assert r.pro["summary"]["n"] > 0 and not np.isnan(r.pro["summary"]["clv_close_mean"])
    assert not r.pro["deciles"].empty and not r.pro["closing_distance"].empty
    # with a 6h-early entry the decision-time line is the pre-match one, never the closing line
    assert set(df["book_source"].dropna()) <= {"ps", "avg", "max", "b365", "bfe", "espn"}
    assert set(df["bookc_source"].dropna()) <= {"psc", "avgc", "maxc", "b365c", "bfec"}
    assert (df["snapshot_time"] < df["kickoff"]).all()
