import numpy as np
import pandas as pd
import pytest

from rsa.backtest import (add_normalized_market, bias_table, calibration_table, market_vs_reference, naive_bets, run_backtest,
                          score_table, strategy_bets, summarize_bets)
from rsa.fees import NoFees, RobinhoodFees


def _frame():
    rows = []
    rng = np.random.default_rng(0)
    for i in range(60):
        ph, pd_, pa = 0.5, 0.25, 0.25
        res = rng.choice(["home", "draw", "away"], p=[ph, pd_, pa])
        rows.append({"match_id": f"m{i}", "league": "epl" if i % 2 else "laliga", "kickoff": pd.Timestamp("2026-08-22", tz="UTC"),
                     "home": "H", "away": "A", "result": res,
                     "mkt_home": 0.52, "mkt_draw": 0.20, "mkt_away": 0.30,
                     "bid_home": 0.51, "ask_home": 0.53, "bid_draw": 0.19, "ask_draw": 0.21, "bid_away": 0.29, "ask_away": 0.31,
                     "book_home": ph, "book_draw": pd_, "book_away": pa})
    return pd.DataFrame(rows)


def test_normalized_market_and_scores():
    df = add_normalized_market(_frame())
    assert df["mkt_overround"].iloc[0] == pytest.approx(0.02)
    assert (df[["mktn_home", "mktn_draw", "mktn_away"]].sum(axis=1) - 1).abs().max() < 1e-9
    sc = score_table(df, ["mktn", "book", "missing"]).set_index("source")
    assert sc.loc["missing", "n"] == 0 and sc.loc["book", "n"] == 60
    assert sc.loc["book", "brier"] > 0


def test_strategy_bets_math_with_fees():
    df = _frame()
    fees = RobinhoodFees()
    bets = strategy_bets(df, "book", fees, min_edge=0.005, fill="ask")
    # draw: ask 0.21, fee 0.03 -> edge 0.25 - 0.24 = 0.01 qualifies.
    # NO on away: 1 - bid = 0.71, fee 0.04 -> edge 0.75 - 0.75 = 0.00 < 0.005 excluded.
    # NO on home: 1 - bid = 0.49, fee 0.04 -> edge 0.50 - 0.53 < 0 excluded.
    assert set(bets["outcome"]) == {"draw"} and set(bets["side"]) == {"yes"}
    assert len(strategy_bets(df, "book", fees, min_edge=0.0, fill="ask")["outcome"].unique()) == 2
    b = bets.iloc[0]
    assert b["price"] == pytest.approx(0.21) and b["fee"] == pytest.approx(fees.fee(0.21, 1))
    assert b["risked"] == pytest.approx(0.21 + b["fee"])
    won = bets[bets["won"]]
    lost = bets[~bets["won"]]
    if len(won):
        assert won["profit"].iloc[0] == pytest.approx(1 - 0.21 - b["fee"])
    if len(lost):
        assert lost["profit"].iloc[0] == pytest.approx(-(0.21 + b["fee"]))
    # 'last' fills use the last price instead of the ask
    bets_last = strategy_bets(df, "book", NoFees(), min_edge=0.0, fill="last")
    assert bets_last["price"].min() == pytest.approx(0.20)


def test_summarize_bets_bootstrap_and_empty():
    empty = summarize_bets(pd.DataFrame())
    assert empty["n"] == 0 and np.isnan(empty["roi"])
    bets = pd.DataFrame({"profit": [0.5, -0.5, 0.5, 0.5], "risked": [0.5] * 4, "won": [True, False, True, True],
                         "price": [0.5] * 4, "edge": [0.1] * 4})
    s = summarize_bets(bets, n_boot=200)
    assert s["roi"] == pytest.approx(0.5) and s["roi_ci_low"] <= s["roi"] <= s["roi_ci_high"] and s["win_rate"] == 0.75


def test_calibration_bias_and_market_vs_reference():
    df = add_normalized_market(_frame())
    cal = calibration_table(df, "mkt")
    assert cal["n"].sum() == 180
    bias = bias_table(df, "mkt", "outcome").set_index("outcome")
    assert bias.loc["draw", "mean_price"] == pytest.approx(0.20)
    mv = market_vs_reference(df, "mktn", "book").set_index("outcome")
    assert mv.loc["draw", "mean_diff"] < 0 and mv.loc["home", "mean_diff"] > 0


def test_naive_rules_and_run_backtest():
    df = _frame()
    fav = naive_bets(df, "favorite", NoFees())
    assert set(fav["outcome"]) == {"home"} and len(fav) == 60
    nd = naive_bets(df, "no_draw", NoFees())
    assert set(nd["side"]) == {"no"} and nd["price"].iloc[0] == pytest.approx(1 - 0.19)
    res = run_backtest(df, RobinhoodFees(), min_edge=0.0, fair_sources=("book", "elo"))
    assert res.n_matches == 60 and "book" in res.strategies and "elo" not in res.strategies
    assert not res.naive.empty and not res.sweeps["book"].empty
