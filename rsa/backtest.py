"""Backtest engine: calibration, scoring rules, bias diagnostics and fee-aware strategies.

Input is the one-row-per-match frame from :mod:`rsa.matching` with market
prices ``mkt_*`` (YES price in dollars), optional ``bid_*``/``ask_*`` quotes,
the realized ``result`` and one or more reference probability sets such as
``book_*`` (de-vigged closing odds), ``elo_*`` and ``poisson_*``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .fees import FeeModel, NoFees
from .pro import StakingRules, fit_final_pools, pro_backtest, walk_forward_pool

OUTCOMES = ("home", "draw", "away")


# ------------------------------------------------------------------ helpers
def _cols(prefix: str) -> list[str]:
    return [f"{prefix}_{o}" for o in OUTCOMES]


def has_probs(df: pd.DataFrame, prefix: str) -> pd.Series:
    cols = _cols(prefix)
    if not all(c in df for c in cols):
        return pd.Series(False, index=df.index)
    return df[cols].notna().all(axis=1)


def add_normalized_market(df: pd.DataFrame, prefix: str = "mkt") -> pd.DataFrame:
    """Add ``{prefix}n_*`` (prices scaled to sum to 1) and ``{prefix}_overround``."""
    df = df.copy()
    cols = _cols(prefix)
    s = df[cols].sum(axis=1, min_count=3)
    for c, o in zip(cols, OUTCOMES):
        df[f"{prefix}n_{o}"] = df[c] / s
    df[f"{prefix}_overround"] = s - 1.0
    return df


def add_blend(df: pd.DataFrame, a: str, b: str, w: float, name: str) -> pd.DataFrame:
    df = df.copy()
    ok = has_probs(df, a) & has_probs(df, b)
    for o in OUTCOMES:
        df[f"{name}_{o}"] = np.where(ok, w * df[f"{a}_{o}"] + (1 - w) * df[f"{b}_{o}"], np.nan)
    s = df[_cols(name)].sum(axis=1)
    for o in OUTCOMES:
        df[f"{name}_{o}"] = df[f"{name}_{o}"] / s
    return df


# ------------------------------------------------------------------ scoring
def score_table(df: pd.DataFrame, prefixes: list[str]) -> pd.DataFrame:
    """Multiclass Brier score and log loss per probability source (lower is better)."""
    rows = []
    base = df[df["result"].isin(OUTCOMES)]
    for p in prefixes:
        ok = has_probs(base, p)
        sub = base[ok]
        if sub.empty:
            rows.append({"source": p, "n": 0, "brier": np.nan, "logloss": np.nan})
            continue
        probs = sub[_cols(p)].to_numpy(dtype=float)
        probs = np.clip(probs, 1e-6, 1.0)
        probs = probs / probs.sum(axis=1, keepdims=True)
        y = np.array([[1.0 if r == o else 0.0 for o in OUTCOMES] for r in sub["result"]])
        brier = float(((probs - y) ** 2).sum(axis=1).mean())
        ll = float(-(np.log(probs) * y).sum(axis=1).mean())
        rows.append({"source": p, "n": int(len(sub)), "brier": brier, "logloss": ll})
    return pd.DataFrame(rows)


def per_match_brier(df: pd.DataFrame, prefix: str) -> pd.Series:
    cols = _cols(prefix)
    probs = df[cols].to_numpy(dtype=float)
    probs = np.clip(probs, 1e-6, 1.0)
    probs = probs / probs.sum(axis=1, keepdims=True)
    y = np.array([[1.0 if r == o else 0.0 for o in OUTCOMES] for r in df["result"]])
    return pd.Series(((probs - y) ** 2).sum(axis=1), index=df.index)


def paired_score_diff(df: pd.DataFrame, a: str, b: str) -> dict:
    """Mean per-match Brier(a) - Brier(b) with its standard error and t-stat (positive = ``a`` worse)."""
    ok = df["result"].isin(OUTCOMES) & has_probs(df, a) & has_probs(df, b)
    sub = df[ok]
    if len(sub) < 2:
        return {"a": a, "b": b, "n": int(len(sub)), "mean_diff": np.nan, "se": np.nan, "t": np.nan}
    d = per_match_brier(sub, a) - per_match_brier(sub, b)
    se = d.std(ddof=1) / math.sqrt(len(d))
    return {"a": a, "b": b, "n": int(len(d)), "mean_diff": float(d.mean()), "se": float(se),
            "t": float(d.mean() / se) if se > 0 else np.nan}


def league_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per league: matches, mean overround, draw share vs draw price, market and book Brier."""
    rows = []
    base = df[df["result"].isin(OUTCOMES)]
    for lg, sub in base.groupby("league"):
        row = {"league": lg, "n": int(len(sub)),
               "overround": float(sub["mkt_overround"].mean()) if "mkt_overround" in sub else np.nan,
               "draw_price": float(sub["mkt_draw"].mean()), "draw_rate": float((sub["result"] == "draw").mean()),
               "home_price": float(sub["mkt_home"].mean()), "home_rate": float((sub["result"] == "home").mean())}
        for p in ("mktn", "book"):
            ok = has_probs(sub, p)
            row[f"brier_{p}"] = float(per_match_brier(sub[ok], p).mean()) if ok.any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def calibration_table(df: pd.DataFrame, prefix: str = "mkt", bins: tuple[float, ...] = (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)) -> pd.DataFrame:
    """Reliability table over all outcome contracts: mean price vs realized hit rate per bin."""
    base = df[df["result"].isin(OUTCOMES)]
    long = _long_outcomes(base, prefix)
    if long.empty:
        return pd.DataFrame(columns=["bin", "n", "mean_price", "hit_rate", "diff", "se"])
    long["bin"] = pd.cut(long["p"], bins=list(bins), right=False, include_lowest=True)
    g = long.groupby("bin", observed=True)
    out = g.agg(n=("hit", "size"), mean_price=("p", "mean"), hit_rate=("hit", "mean")).reset_index()
    out["diff"] = out["hit_rate"] - out["mean_price"]
    out["se"] = np.sqrt(out["mean_price"] * (1 - out["mean_price"]) / out["n"].clip(lower=1))
    out["bin"] = out["bin"].astype(str)
    return out


def _long_outcomes(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    parts = []
    for o in OUTCOMES:
        c = f"{prefix}_{o}"
        if c not in df:
            continue
        sub = df[[c, "result", "league", "match_id"]].rename(columns={c: "p"}).dropna(subset=["p"])
        sub["outcome"] = o
        sub["hit"] = (sub["result"] == o).astype(float)
        parts.append(sub)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def bias_table(df: pd.DataFrame, prefix: str = "mkt", by: str = "outcome") -> pd.DataFrame:
    """Mean price vs hit rate grouped by outcome type or league (systematic-bias check)."""
    base = df[df["result"].isin(OUTCOMES)]
    long = _long_outcomes(base, prefix)
    if long.empty:
        return pd.DataFrame()
    g = long.groupby(by, observed=True)
    out = g.agg(n=("hit", "size"), mean_price=("p", "mean"), hit_rate=("hit", "mean")).reset_index()
    out["diff"] = out["hit_rate"] - out["mean_price"]
    out["se"] = np.sqrt(out["mean_price"] * (1 - out["mean_price"]) / out["n"].clip(lower=1))
    out["z"] = out["diff"] / out["se"].replace(0, np.nan)
    return out


def market_vs_reference(df: pd.DataFrame, market: str = "mktn", ref: str = "book") -> pd.DataFrame:
    """Average (market - reference) probability per outcome, with t-stats.

    A significantly negative number means the venue prices that outcome below
    the reference (cheap to buy YES); positive means it is overpriced.
    """
    ok = has_probs(df, market) & has_probs(df, ref)
    rows = []
    for o in OUTCOMES:
        d = (df.loc[ok, f"{market}_{o}"] - df.loc[ok, f"{ref}_{o}"]).astype(float)
        n = int(d.count())
        rows.append({"outcome": o, "n": n, "mean_diff": d.mean() if n else np.nan,
                     "sd": d.std(ddof=1) if n > 1 else np.nan,
                     "t": (d.mean() / (d.std(ddof=1) / math.sqrt(n))) if n > 1 and d.std(ddof=1) > 0 else np.nan})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ betting
@dataclass
class Bet:
    match_id: str
    league: str
    kickoff: object
    home: str
    away: str
    outcome: str
    side: str            # "yes" or "no"
    price: float         # fill price in dollars for the side bought
    fee: float           # fee per contract
    fair: float          # reference probability that the bought side wins
    edge: float          # fair - (price + fee)
    won: bool
    profit: float        # per contract
    risked: float        # price + fee


def _fill_price(row: pd.Series, outcome: str, side: str, fill: str) -> float | None:
    last = row.get(f"mkt_{outcome}")
    bid, ask = row.get(f"bid_{outcome}"), row.get(f"ask_{outcome}")
    if side == "yes":
        p = ask if (fill == "ask" and pd.notna(ask)) else last
    else:
        # NO contract costs 1 - yes_bid when hitting the bid; else 1 - last
        p = (1 - bid) if (fill == "ask" and pd.notna(bid)) else (1 - last if pd.notna(last) else None)
    if p is None or pd.isna(p) or p <= 0 or p >= 1:
        return None
    return float(p)


def strategy_bets(df: pd.DataFrame, fair_prefix: str, fees: FeeModel = NoFees(), min_edge: float = 0.03,
                  sides: tuple[str, ...] = ("yes", "no"), fill: str = "ask", slippage: float = 0.0,
                  max_price: float = 0.97, min_price: float = 0.03) -> pd.DataFrame:
    """Bet every contract whose reference probability beats price + fee by ``min_edge``.

    ``fill="ask"`` buys at the ask (NO at 1 - bid) when quotes exist, else at
    the last trade; ``slippage`` is added to every fill price.
    """
    bets: list[Bet] = []
    base = df[df["result"].isin(OUTCOMES) & has_probs(df, fair_prefix)]
    for _, r in base.iterrows():
        for o in OUTCOMES:
            fair_yes = float(r[f"{fair_prefix}_{o}"])
            for side in sides:
                p = _fill_price(r, o, side, fill)
                if p is None:
                    continue
                p = min(max(p + slippage, 0.01), 0.99)
                if p > max_price or p < min_price:
                    continue
                fair = fair_yes if side == "yes" else 1 - fair_yes
                fee = fees.fee_per_contract(p, 1)
                edge = fair - (p + fee)
                if edge < min_edge:
                    continue
                won = (r["result"] == o) if side == "yes" else (r["result"] != o)
                profit = (1 - p - fee) if won else -(p + fee)
                bets.append(Bet(r["match_id"], r["league"], r["kickoff"], r["home"], r["away"], o, side, p, fee,
                                fair, edge, bool(won), profit, p + fee))
    return pd.DataFrame([b.__dict__ for b in bets])


def naive_bets(df: pd.DataFrame, rule: str, fees: FeeModel = NoFees(), fill: str = "ask") -> pd.DataFrame:
    """Fixed rules that need no model: buy every home/draw/away, favorite or underdog YES contract."""
    bets: list[Bet] = []
    base = df[df["result"].isin(OUTCOMES) & has_probs(df, "mkt")]
    for _, r in base.iterrows():
        prices = {o: float(r[f"mkt_{o}"]) for o in OUTCOMES}
        if rule in OUTCOMES:
            picks = [rule]
        elif rule == "favorite":
            picks = [max(prices, key=prices.get)]
        elif rule == "underdog":
            picks = [min(prices, key=prices.get)]
        elif rule == "no_draw":
            picks = ["draw"]
        else:
            raise ValueError(rule)
        side = "no" if rule == "no_draw" else "yes"
        for o in picks:
            p = _fill_price(r, o, side, fill)
            if p is None:
                continue
            fee = fees.fee_per_contract(p, 1)
            won = (r["result"] == o) if side == "yes" else (r["result"] != o)
            profit = (1 - p - fee) if won else -(p + fee)
            bets.append(Bet(r["match_id"], r["league"], r["kickoff"], r["home"], r["away"], o, side, p, fee,
                            float("nan"), float("nan"), bool(won), profit, p + fee))
    return pd.DataFrame([b.__dict__ for b in bets])


def summarize_bets(bets: pd.DataFrame, n_boot: int = 2000, seed: int = 7) -> dict:
    """ROI (profit / dollars risked) with a percentile-bootstrap 95% interval."""
    if bets is None or bets.empty:
        return {"n": 0, "risked": 0.0, "profit": 0.0, "roi": np.nan, "roi_ci_low": np.nan, "roi_ci_high": np.nan,
                "win_rate": np.nan, "avg_price": np.nan, "avg_edge": np.nan, "p_value_profit_le_0": np.nan}
    profit = bets["profit"].to_numpy(dtype=float)
    risked = bets["risked"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    n = len(profit)
    idx = rng.integers(0, n, size=(n_boot, n))
    rois = profit[idx].sum(axis=1) / risked[idx].sum(axis=1)
    return {
        "n": int(n),
        "risked": float(risked.sum()),
        "profit": float(profit.sum()),
        "roi": float(profit.sum() / risked.sum()),
        "roi_ci_low": float(np.percentile(rois, 2.5)),
        "roi_ci_high": float(np.percentile(rois, 97.5)),
        "win_rate": float(bets["won"].mean()),
        "avg_price": float(bets["price"].mean()),
        "avg_edge": float(bets["edge"].mean()) if bets["edge"].notna().any() else np.nan,
        "p_value_profit_le_0": float((rois <= 0).mean()),
    }


def edge_sweep(df: pd.DataFrame, fair_prefix: str, fees: FeeModel, edges=(0.0, 0.02, 0.04, 0.06, 0.08, 0.10),
               **kw) -> pd.DataFrame:
    rows = []
    for e in edges:
        s = summarize_bets(strategy_bets(df, fair_prefix, fees, min_edge=e, **kw))
        s["min_edge"] = e
        rows.append(s)
    return pd.DataFrame(rows)[["min_edge", "n", "risked", "profit", "roi", "roi_ci_low", "roi_ci_high", "win_rate", "avg_price", "avg_edge"]]


def bets_breakdown(bets: pd.DataFrame, by: str) -> pd.DataFrame:
    if bets is None or bets.empty:
        return pd.DataFrame()
    rows = []
    for key, sub in bets.groupby(by):
        s = summarize_bets(sub, n_boot=500)
        s[by] = key
        rows.append(s)
    return pd.DataFrame(rows)[[by, "n", "risked", "profit", "roi", "roi_ci_low", "roi_ci_high", "win_rate"]]


# ------------------------------------------------------------------ driver
@dataclass
class BacktestResult:
    n_matches: int
    scores: pd.DataFrame
    calibration: pd.DataFrame
    bias_by_outcome: pd.DataFrame
    bias_by_league: pd.DataFrame
    market_vs_book: pd.DataFrame
    naive: pd.DataFrame
    accuracy_vs_book: dict = field(default_factory=dict)
    strategies: dict[str, dict] = field(default_factory=dict)
    sweeps: dict[str, pd.DataFrame] = field(default_factory=dict)
    bets: dict[str, pd.DataFrame] = field(default_factory=dict)
    breakdowns: dict[str, pd.DataFrame] = field(default_factory=dict)
    frame: pd.DataFrame | None = None
    pro: dict = field(default_factory=dict)


def run_backtest(df: pd.DataFrame, fees: FeeModel, min_edge: float = 0.03,
                 fair_sources: tuple[str, ...] = ("book", "elo", "poisson", "blend", "pro"), fill: str = "ask",
                 slippage: float = 0.0, rules: StakingRules | None = None) -> BacktestResult:
    df = add_normalized_market(df)
    if has_probs(df, "book").any() and has_probs(df, "poisson").any():
        df = add_blend(df, "poisson", "book", 0.3, "blend")
    df = walk_forward_pool(df)
    sources = [s for s in fair_sources if has_probs(df, s).any()]
    res = BacktestResult(
        n_matches=int(df["result"].isin(OUTCOMES).sum()),
        scores=score_table(df, ["mktn"] + sources),
        calibration=calibration_table(df, "mkt"),
        bias_by_outcome=bias_table(df, "mkt", "outcome"),
        bias_by_league=league_summary(df),
        market_vs_book=market_vs_reference(df, "mktn", "book") if "book" in sources else pd.DataFrame(),
        accuracy_vs_book=paired_score_diff(df, "mktn", "book") if "book" in sources else {},
        naive=pd.DataFrame(),
        frame=df,
    )
    naive_rows = []
    for rule in ("home", "draw", "away", "favorite", "underdog", "no_draw"):
        s = summarize_bets(naive_bets(df, rule, fees, fill))
        s["rule"] = rule
        naive_rows.append(s)
    res.naive = pd.DataFrame(naive_rows)[["rule", "n", "risked", "profit", "roi", "roi_ci_low", "roi_ci_high", "win_rate", "avg_price"]]
    for s in sources:
        bets = strategy_bets(df, s, fees, min_edge=min_edge, fill=fill, slippage=slippage)
        res.bets[s] = bets
        res.strategies[s] = summarize_bets(bets)
        res.sweeps[s] = edge_sweep(df, s, fees, fill=fill, slippage=slippage)
        res.breakdowns[f"{s}_by_outcome"] = bets_breakdown(bets, "outcome")
        res.breakdowns[f"{s}_by_side"] = bets_breakdown(bets, "side")
        res.breakdowns[f"{s}_by_league"] = bets_breakdown(bets, "league")
    rules = rules or StakingRules(min_edge=min_edge)
    pro = pro_backtest(df, fees, rules, fill)
    pools = fit_final_pools(df, n_boot=0)
    pro["pool_weights"] = {k: {"weights": v.weights, "intercepts": [round(float(x), 3) for x in v.b[0]], "n_train": v.n_train}
                           for k, v in pools.items()}
    pro["rules"] = rules
    res.pro = pro
    res.frame = pro["frame"]
    return res
