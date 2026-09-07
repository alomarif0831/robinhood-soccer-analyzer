"""Professional bet-selection logic.

What sharp bettors actually do, made explicit and testable:

1. **Fair probability by log-linear pooling.** Each available source (de-vigged
   closing/current bookmaker line, the venue's own normalized price, the Poisson
   and Elo models) contributes ``w_i * log p_i``; a per-outcome intercept fixes
   systematic draw/home bias. Weights and intercepts are fitted walk-forward
   (only on matches that finished before the one being priced) by minimizing
   log loss, shrunk toward a prior that trusts the bookmaker line most.
2. **Uncertainty.** The fit is bootstrapped, giving a standard deviation for
   every fair probability, so an edge is judged by its z-score, not its size.
3. **Fee-aware edge on the side you can actually buy** (YES at the ask, NO at
   one minus the bid), with the Robinhood fee schedule.
4. **Confidence score (0-100)** combining edge significance, edge size, agreement
   between independent sources, liquidity (spread/volume), price band (fee drag
   and favourite-longshot bias), price freshness and data support (early-season
   ratings are noisy). Tiers: A >= 75, B >= 60, C >= 45, else pass.
5. **Fractional Kelly staking** with per-bet and per-day caps, one bet per match.
6. **Closing line value (CLV)**: did the entry beat the venue's closing price and
   the sharp closing line? Positive CLV is the earliest reliable sign of a real
   edge; realized profit over a few dozen bets is not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .fees import FeeModel, NoFees

OUTCOMES = ("home", "draw", "away")
SOURCE_SETS: dict[str, tuple[str, ...]] = {
    "full": ("book", "mktn", "poisson", "elo"),
    "nobook": ("mktn", "poisson", "elo"),
}
PRIOR_WEIGHTS: dict[str, np.ndarray] = {
    "full": np.array([0.55, 0.30, 0.10, 0.05]),
    "nobook": np.array([0.65, 0.20, 0.15]),
}
MIN_TRAIN = 100         # matches needed before fitted weights replace the prior
SD_FLOOR = 0.02         # never claim a fair probability is known better than +/-2 pts (with a book line)
SD_FLOOR_NOBOOK = 0.03  # ... or +/-3 pts when no bookmaker line anchors the pool
PRIOR_SD = 0.05         # uncertainty assumed while still on prior weights
SD_INFLATE_SMALL = 1.5  # uncertainty multiplier while n_train < MIN_TRAIN (fitted on a thin sample) or on priors
SD_INFLATE_EARLY = 1.25 # ... and when the decision is more than 75 min before kickoff (lineup risk)
RECENCY_HALFLIFE_DAYS = 90.0
TIERS = (("A", 75), ("B", 60), ("C", 45))


# ------------------------------------------------------------------ pooling
def _cols(prefix: str) -> list[str]:
    return [f"{prefix}_{o}" for o in OUTCOMES]


def has_sources(df: pd.DataFrame, sources: tuple[str, ...]) -> pd.Series:
    ok = pd.Series(True, index=df.index)
    for s in sources:
        cols = _cols(s)
        if not all(c in df for c in cols):
            return pd.Series(False, index=df.index)
        ok &= df[cols].notna().all(axis=1)
    return ok


def log_probs(df: pd.DataFrame, sources: tuple[str, ...]) -> np.ndarray:
    """(n, k, 3) array of log probabilities, each source renormalized to sum to 1."""
    arr = np.stack([df[_cols(s)].to_numpy(dtype=float) for s in sources], axis=1)
    arr = np.clip(arr, 1e-6, 1.0)
    arr = arr / arr.sum(axis=2, keepdims=True)
    return np.log(arr)


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


@dataclass
class PoolFit:
    """Log-linear pooling weights: sample 0 is the point estimate, the rest are bootstrap replicates."""

    sources: tuple[str, ...]
    W: np.ndarray          # (B, k)
    b: np.ndarray          # (B, 3)
    n_train: int

    def predict_samples(self, L: np.ndarray) -> np.ndarray:
        """(B, n, 3) pooled probabilities for log-prob array L of shape (n, k, 3)."""
        z = np.einsum("bk,nko->bno", self.W, L) + self.b[:, None, :]
        return _softmax(z)

    def predict(self, L: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(fair (n,3), sd (n,3)); sd is the bootstrap spread with a reference-quality floor."""
        P = self.predict_samples(L)
        fair = P[0]
        sd = P[1:].std(axis=0) if P.shape[0] > 1 else np.full_like(fair, PRIOR_SD)
        floor = SD_FLOOR if "book" in self.sources else SD_FLOOR_NOBOOK
        sd = np.maximum(sd, floor)
        if self.n_train < MIN_TRAIN:
            sd = sd * SD_INFLATE_SMALL
        return fair, sd

    @property
    def weights(self) -> dict[str, float]:
        return {s: float(w) for s, w in zip(self.sources, self.W[0])}


def prior_fit(set_name: str) -> PoolFit:
    w0 = PRIOR_WEIGHTS[set_name]
    return PoolFit(SOURCE_SETS[set_name], w0[None, :].copy(), np.zeros((1, 3)), 0)


def _block_resample(n: int, n_boot: int, groups: np.ndarray | None, rng) -> np.ndarray:
    """(n_boot, n) row indices; with ``groups`` whole blocks (matchdays) are resampled together."""
    if groups is None:
        return rng.integers(0, n, size=(n_boot, n))
    uniq, inv = np.unique(groups, return_inverse=True)
    members = [np.flatnonzero(inv == g) for g in range(len(uniq))]
    out = np.empty((n_boot, n), dtype=int)
    for b in range(n_boot):
        picked = rng.integers(0, len(uniq), size=len(uniq))
        rows = np.concatenate([members[g] for g in picked])
        # keep the replicate the same length as the sample so gradients stay comparable
        out[b] = rows[rng.integers(0, len(rows), size=n)] if len(rows) != n else rows
    return out


def fit_pool(L: np.ndarray, y: np.ndarray, set_name: str, n_boot: int = 0, l2: float = 0.02,
             iters: int = 250, lr: float = 0.05, seed: int = 7, groups: np.ndarray | None = None,
             row_weights: np.ndarray | None = None) -> PoolFit:
    """Fit weights (>= 0) and intercepts by Adam on mean log loss + L2 shrinkage to the prior.

    ``n_boot`` extra replicates are fitted on bootstrap resamples of the rows (block
    bootstrap over ``groups`` such as matchdays when given), all vectorized in one
    pass (replicate 0 is always the full sample).
    """
    n, k, _ = L.shape
    B = 1 + n_boot
    rng = np.random.default_rng(seed)
    idx = np.vstack([np.arange(n)[None, :], _block_resample(n, n_boot, groups, rng)]) if n_boot else np.arange(n)[None, :]
    Lb = L[idx]                                    # (B, n, k, 3)
    Y = np.zeros((B, n, 3))
    yb = y[idx]
    Y[np.arange(B)[:, None], np.arange(n)[None, :], yb] = 1.0
    rw = np.ones(n) if row_weights is None else np.asarray(row_weights, dtype=float)
    rw = rw[idx] * (n / rw[idx].sum(axis=1, keepdims=True))      # (B, n), mean 1 per replicate
    w0 = PRIOR_WEIGHTS[set_name][: k]
    W = np.tile(w0, (B, 1)).astype(float)
    bias = np.zeros((B, 3))
    mW, vW, mb, vb = np.zeros_like(W), np.zeros_like(W), np.zeros_like(bias), np.zeros_like(bias)
    b1, b2, eps = 0.9, 0.999, 1e-8
    for t in range(1, iters + 1):
        z = np.einsum("bk,bnko->bno", W, Lb) + bias[:, None, :]
        P = _softmax(z)
        G = (P - Y) * rw[:, :, None] / n           # d(weighted mean NLL)/dz
        gW = np.einsum("bno,bnko->bk", G, Lb) + 2 * l2 * (W - w0)
        gb = G.sum(axis=1) + 2 * l2 * bias
        mW, vW = b1 * mW + (1 - b1) * gW, b2 * vW + (1 - b2) * gW * gW
        mb, vb = b1 * mb + (1 - b1) * gb, b2 * vb + (1 - b2) * gb * gb
        W -= lr * (mW / (1 - b1 ** t)) / (np.sqrt(vW / (1 - b2 ** t)) + eps)
        bias -= lr * (mb / (1 - b1 ** t)) / (np.sqrt(vb / (1 - b2 ** t)) + eps)
        np.maximum(W, 0.0, out=W)
    return PoolFit(SOURCE_SETS[set_name][: k], W, bias, n)


def _result_index(df: pd.DataFrame) -> np.ndarray:
    return df["result"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy(dtype=int)


def choose_set(row_has_book: bool) -> str:
    return "full" if row_has_book else "nobook"


def walk_forward_pool(df: pd.DataFrame, min_train: int = MIN_TRAIN, n_boot: int = 40, seed: int = 7) -> pd.DataFrame:
    """Add ``pro_*`` fair probabilities and ``prosd_*`` uncertainties, fitted only on earlier matches.

    Weights are refitted once per kickoff date on every settled, fully-sourced
    match that kicked off before that date. Until ``min_train`` such matches
    exist the prior weights are used (with ``PRIOR_SD`` uncertainty).
    """
    df = df.copy()
    for o in OUTCOMES:
        df[f"pro_{o}"] = np.nan
        df[f"prosd_{o}"] = np.nan
    df["pro_n_train"] = 0
    df["pro_set"] = None
    if "kickoff" not in df or df.empty:
        return df
    kick = pd.to_datetime(df["kickoff"], utc=True)
    days = kick.dt.date
    settled = df["result"].isin(OUTCOMES)
    for day in sorted(days.dropna().unique()):
        today = days == day
        # a match is "finished" for training only if it kicked off at least 150 min before the first kickoff of this day
        finished = kick <= (kick[today].min() - pd.Timedelta(minutes=150))
        for set_name, sources in SOURCE_SETS.items():
            avail = has_sources(df, sources)
            rows = today & avail
            if set_name == "nobook":
                rows &= ~has_sources(df, SOURCE_SETS["full"])   # only rows that lack a book line
            if not rows.any():
                continue
            train = settled & avail & finished
            if train.sum() >= min_train:
                age = np.array([(day - d).days for d in days[train]], dtype=float)
                fit = fit_pool(log_probs(df[train], sources), _result_index(df[train]), set_name, n_boot=n_boot, seed=seed,
                               groups=days[train].astype(str).to_numpy(), row_weights=0.5 ** (age / RECENCY_HALFLIFE_DAYS))
            else:
                fit = prior_fit(set_name)
            fair, sd = fit.predict(log_probs(df[rows], sources))
            for i, o in enumerate(OUTCOMES):
                df.loc[rows, f"pro_{o}"] = fair[:, i]
                df.loc[rows, f"prosd_{o}"] = sd[:, i]
            df.loc[rows, "pro_n_train"] = fit.n_train
            df.loc[rows, "pro_set"] = set_name
    return df


def fit_final_pools(df: pd.DataFrame, n_boot: int = 200, min_train: int = MIN_TRAIN, seed: int = 7) -> dict[str, PoolFit]:
    """Pools fitted on every settled priced match, for pricing upcoming fixtures."""
    out = {}
    settled = df["result"].isin(OUTCOMES) if "result" in df else pd.Series(False, index=df.index)
    for set_name, sources in SOURCE_SETS.items():
        rows = settled & has_sources(df, sources)
        if rows.sum() >= min_train:
            kick = pd.to_datetime(df.loc[rows, "kickoff"], utc=True)
            groups = kick.dt.date.astype(str).to_numpy()
            age = (kick.max() - kick).dt.total_seconds().to_numpy() / 86400
            out[set_name] = fit_pool(log_probs(df[rows], sources), _result_index(df[rows]), set_name, n_boot=n_boot, seed=seed,
                                     groups=groups, row_weights=0.5 ** (age / RECENCY_HALFLIFE_DAYS))
        else:
            out[set_name] = prior_fit(set_name)
    return out


def apply_pools(df: pd.DataFrame, pools: dict[str, PoolFit]) -> pd.DataFrame:
    """Price rows (typically upcoming fixtures) with already-fitted pools."""
    df = df.copy()
    for o in OUTCOMES:
        df[f"pro_{o}"] = np.nan
        df[f"prosd_{o}"] = np.nan
    df["pro_n_train"] = 0
    df["pro_set"] = None
    full = has_sources(df, SOURCE_SETS["full"])
    for set_name, sources in SOURCE_SETS.items():
        rows = has_sources(df, sources) & (full if set_name == "full" else ~full)
        if not rows.any():
            continue
        fit = pools[set_name]
        fair, sd = fit.predict(log_probs(df[rows], sources))
        for i, o in enumerate(OUTCOMES):
            df.loc[rows, f"pro_{o}"] = fair[:, i]
            df.loc[rows, f"prosd_{o}"] = sd[:, i]
        df.loc[rows, "pro_n_train"] = fit.n_train
        df.loc[rows, "pro_set"] = set_name
    return df


# ------------------------------------------------------------------ staking
def kelly_fraction(q: float, price: float, fee: float) -> float:
    """Full-Kelly fraction of bankroll for a $1 contract bought at ``price`` + ``fee`` with win probability ``q``."""
    cost = price + fee
    if cost <= 0 or cost >= 1:
        return 0.0
    b = (1.0 - cost) / cost
    return max(0.0, q - (1.0 - q) / b)


# ------------------------------------------------------------------ candidates
def _fill(row: pd.Series, o: str, side: str, fill: str) -> float | None:
    last, bid, ask = row.get(f"mkt_{o}"), row.get(f"bid_{o}"), row.get(f"ask_{o}")
    if side == "yes":
        p = ask if (fill == "ask" and pd.notna(ask)) else last
    else:
        p = (1 - bid) if (fill == "ask" and pd.notna(bid)) else (1 - last if pd.notna(last) else None)
    if p is None or pd.isna(p) or p <= 0 or p >= 1:
        return None
    return float(p)


def _hours_between(later, earlier) -> float | None:
    if later is None or earlier is None or pd.isna(later) or pd.isna(earlier):
        return None
    return float((pd.Timestamp(later) - pd.Timestamp(earlier)).total_seconds() / 3600)


def confidence_components(edge: float, edge_sd: float, agreement: float | None, spread: float | None,
                          volume: float | None, price: float, stale_hours: float | None, n_train: int,
                          team_games: float | None) -> dict[str, float]:
    """Each component in points; they sum to at most 100."""
    # z = 1.5 (about a 93% one-sided chance the edge is really positive) earns full significance points
    z = edge / edge_sd if edge_sd > 0 else 0.0
    comp = {
        "edge_significance": 35.0 * float(np.clip(z / 1.5, 0, 1)),
        "edge_size": 15.0 * float(np.clip(edge / 0.06, 0, 1)),
        "agreement": 20.0 * (agreement if agreement is not None else 0.5),
        "liquidity": 15.0 if (spread is not None and spread <= 0.02) else 10.0 if (spread is not None and spread <= 0.04)
        else 5.0 if (spread is not None and spread <= 0.06) else 5.0 if spread is None else 0.0,
        "price_band": 10.0 if 0.15 <= price <= 0.80 else 5.0 if 0.08 <= price <= 0.90 else 0.0,
        "freshness": 5.0 if (stale_hours is not None and stale_hours <= 24) else 3.0 if stale_hours is None else 0.0,
    }
    if volume is not None and volume < 50:
        comp["liquidity"] *= 0.5
    # data support: prior-only pooling or teams with few games this season make model-driven parts less trustworthy
    support = 1.0
    if n_train < MIN_TRAIN:
        support *= 0.8
    if team_games is not None and team_games < 5:
        support *= 0.8
    for k in ("edge_significance", "agreement"):
        comp[k] *= support
    comp["data_support"] = 0.0 if support == 1.0 else -round((1 - support) * 100, 1)   # informational only
    return comp


def tier_for(score: float) -> str:
    for name, cut in TIERS:
        if score >= cut:
            return name
    return "pass"


def quote_consistency(row: pd.Series) -> bool:
    """A real three-way book has ask_sum >= ~1 and bid_sum <= ~1; violations mean mis-mapped outcomes or junk quotes."""
    asks = [row.get(f"ask_{o}") for o in OUTCOMES]
    bids = [row.get(f"bid_{o}") for o in OUTCOMES]
    if any(v is None or pd.isna(v) for v in asks + bids):
        return True
    return sum(asks) >= 0.97 and sum(bids) <= 1.03


def _backed_team_rest(row: pd.Series, o: str, side: str) -> tuple[float | None, float | None]:
    """(rest days of the team whose performance the bet needs, rest days of its opponent)."""
    rh, ra = row.get("rest_home"), row.get("rest_away")
    rh = None if rh is None or pd.isna(rh) else float(rh)
    ra = None if ra is None or pd.isna(ra) else float(ra)
    if o == "draw":
        return None, None
    backing_home = (o == "home") == (side == "yes")
    return (rh, ra) if backing_home else (ra, rh)


def build_candidates(df: pd.DataFrame, fees: FeeModel = NoFees(), fill: str = "ask",
                     agreement_sources: tuple[str, ...] = ("book", "poisson", "elo"),
                     max_price: float = 0.95, min_price: float = 0.04) -> pd.DataFrame:
    """Every YES/NO contract with its fair probability, edge, uncertainty and confidence score."""
    rows = []
    base = df[has_sources(df, ("pro",))]
    for _, r in base.iterrows():
        n_train = int(r.get("pro_n_train") or 0)
        team_games = r.get("team_games")
        quotes_ok = quote_consistency(r)
        mins_before = r.get("minutes_before")
        early = 1.0 if mins_before is None or pd.isna(mins_before) or mins_before <= 75 else SD_INFLATE_EARLY
        for o in OUTCOMES:
            fair_yes, sd = float(r[f"pro_{o}"]), float(r.get(f"prosd_{o}") or PRIOR_SD) * early
            for side in ("yes", "no"):
                p = _fill(r, o, side, fill)
                if p is None or p > max_price or p < min_price:
                    continue
                fee = fees.fee_per_contract(p, 1)
                fair = fair_yes if side == "yes" else 1 - fair_yes
                edge = fair - (p + fee)
                votes, avail = 0, 0
                for s in agreement_sources:
                    v = r.get(f"{s}_{o}")
                    if v is None or pd.isna(v):
                        continue
                    avail += 1
                    s_fair = float(v) if side == "yes" else 1 - float(v)
                    votes += int(s_fair - (p + fee) > 0)
                agreement = votes / avail if avail else None
                spread = None
                if pd.notna(r.get(f"bid_{o}")) and pd.notna(r.get(f"ask_{o}")):
                    spread = max(0.0, float(r[f"ask_{o}"]) - float(r[f"bid_{o}"]))
                stale = _hours_between(r.get("snapshot_time"), r.get(f"ltt_{o}"))
                comp = confidence_components(edge, sd, agreement, spread, r.get(f"vol_{o}"), p, stale, n_train, team_games)
                rest_me, rest_opp = _backed_team_rest(r, o, side)
                comp["rest"] = -5.0 if (rest_me is not None and rest_opp is not None and rest_me < 3 <= rest_opp - 1) else 0.0
                if not quotes_ok:
                    comp["quote_sanity"] = -30.0
                score = max(0.0, sum(v for k, v in comp.items() if k != "data_support"))
                mid = None
                if pd.notna(r.get(f"bid_{o}")) and pd.notna(r.get(f"ask_{o}")):
                    mid = (float(r[f"bid_{o}"]) + float(r[f"ask_{o}"])) / 2
                    mid = mid if side == "yes" else 1 - mid
                edge_mid = (fair - mid - fee) if mid is not None else edge
                book_yes_dt = r.get(f"book_{o}")
                book_edge = np.nan
                if book_yes_dt is not None and pd.notna(book_yes_dt):
                    book_edge = (float(book_yes_dt) if side == "yes" else 1 - float(book_yes_dt)) - (p + fee)
                # CLV like-for-like: entry fill vs the closing fill on the same side (closing ask for YES, 1 - closing bid for NO),
                # falling back to the closing last trade when no closing quotes were captured
                clv_close = clv_book = np.nan
                close_fill = None
                if side == "yes" and pd.notna(r.get(f"cask_{o}")):
                    close_fill = float(r[f"cask_{o}"])
                elif side == "no" and pd.notna(r.get(f"cbid_{o}")):
                    close_fill = 1 - float(r[f"cbid_{o}"])
                elif pd.notna(r.get(f"close_{o}")):
                    close_fill = float(r[f"close_{o}"]) if side == "yes" else 1 - float(r[f"close_{o}"])
                if close_fill is not None:
                    clv_close = close_fill - p
                bookc = r.get(f"bookc_{o}")
                if bookc is not None and pd.notna(bookc):
                    clv_book = (float(bookc) - p) if side == "yes" else ((1 - float(bookc)) - p)
                won = None
                if r.get("result") in OUTCOMES:
                    won = (r["result"] == o) if side == "yes" else (r["result"] != o)
                rows.append({
                    "match_id": r["match_id"], "league": r["league"], "kickoff": r["kickoff"], "home": r["home"], "away": r["away"],
                    "outcome": o, "side": side, "price": p, "fee": fee, "fair": fair, "fair_sd": sd, "edge": edge,
                    "edge_z": edge / sd if sd > 0 else 0.0, "edge_p05": edge - 1.645 * sd, "edge_q20": edge - 0.84 * sd,
                    "edge_mid": edge_mid, "book_edge": book_edge, "quotes_ok": quotes_ok,
                    "rest_me": rest_me, "rest_opp": rest_opp,
                    "agreement": agreement, "spread": spread, "volume": r.get(f"vol_{o}"), "stale_hours": stale,
                    "confidence": round(score, 1), "tier": tier_for(score), **{f"c_{k}": round(v, 1) for k, v in comp.items()},
                    "kelly_full": kelly_fraction(fair, p, fee), "clv_close": clv_close, "clv_book": clv_book,
                    "won": won, "profit": ((1 - p - fee) if won else -(p + fee)) if won is not None else np.nan,
                    "risked": p + fee, "n_train": n_train,
                })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ portfolio
@dataclass
class StakingRules:
    bankroll: float = 1000.0
    kelly_fraction: float = 0.25      # fraction of full Kelly
    max_bet_fraction: float = 0.02    # of bankroll per bet
    max_day_fraction: float = 0.10    # of bankroll per kickoff date
    max_bets_per_day: int = 8
    min_confidence: float = 60.0
    min_edge: float = 0.02
    min_edge_q20: float = 0.0         # conservative (20th percentile) edge must still be non-negative
    min_edge_mid: float = 0.01        # edge vs the quote mid: never pay only for crossing a wide spread
    min_book_edge: float = 0.0        # the bookmaker line alone must justify the bet (when a line exists)
    require_book_line: bool = False   # True = never bet a match without a bookmaker line
    max_spread: float = 0.06
    max_stale_hours: float = 48.0
    min_price: float = 0.10
    max_price: float = 0.90
    min_contracts: int = 10           # so the per-order cent round-up of the fee is amortized
    require_edge_p05: bool = False


def select_portfolio(cands: pd.DataFrame, rules: StakingRules, fees: FeeModel = NoFees()) -> pd.DataFrame:
    """Apply the discipline rules: gates, thresholds, one bet per match, day caps, Kelly sizing at lot size."""
    if cands is None or cands.empty:
        return pd.DataFrame()
    c = cands.copy()
    ok = (c["confidence"] >= rules.min_confidence) & (c["edge"] >= rules.min_edge)
    ok &= c["edge_q20"] >= rules.min_edge_q20
    ok &= c["edge_mid"] >= rules.min_edge_mid
    ok &= c["quotes_ok"].astype(bool)
    ok &= (c["price"] >= rules.min_price) & (c["price"] <= rules.max_price)
    ok &= c["spread"].isna() | (c["spread"] <= rules.max_spread)
    ok &= c["stale_hours"].isna() | (c["stale_hours"] <= rules.max_stale_hours)
    has_book = c["book_edge"].notna()
    ok &= (~has_book) | (c["book_edge"] >= rules.min_book_edge)
    if rules.require_book_line:
        ok &= has_book
    if rules.require_edge_p05:
        ok &= c["edge_p05"] > 0
    c = c[ok]
    if c.empty:
        return c
    c = c.sort_values(["confidence", "edge_z"], ascending=False).drop_duplicates("match_id", keep="first")
    c["stake_fraction"] = (c["kelly_full"] * rules.kelly_fraction).clip(upper=rules.max_bet_fraction)
    c["day"] = pd.to_datetime(c["kickoff"], utc=True).dt.date
    out = []
    for day, grp in c.groupby("day", sort=True):
        grp = grp.sort_values("confidence", ascending=False).head(rules.max_bets_per_day).copy()
        total = grp["stake_fraction"].sum()
        if total > rules.max_day_fraction and total > 0:
            grp["stake_fraction"] *= rules.max_day_fraction / total
        out.append(grp)
    sel = pd.concat(out).sort_values(["kickoff", "confidence"], ascending=[True, False])
    sel["stake"] = (sel["stake_fraction"] * rules.bankroll).round(2)
    sel["contracts"] = np.floor(sel["stake"] / sel["risked"]).astype(int)
    # fee at the actual lot size (the per-order cent round-up is amortized over the lot)
    fee_n = [fees.fee(p, int(n)) / n if n > 0 else f for p, n, f in zip(sel["price"], sel["contracts"], sel["fee"])]
    sel["fee"] = fee_n
    sel["edge"] = sel["fair"] - sel["price"] - sel["fee"]
    sel["risked"] = sel["price"] + sel["fee"]
    sel["kelly_full"] = [kelly_fraction(q, p, f) for q, p, f in zip(sel["fair"], sel["price"], sel["fee"])]
    if "won" in sel:
        sel["profit"] = np.where(sel["won"].isna(), np.nan, np.where(sel["won"].astype(bool), 1 - sel["price"] - sel["fee"], -(sel["price"] + sel["fee"])))
    sel = sel[sel["contracts"] >= rules.min_contracts]
    sel["stake"] = (sel["contracts"] * sel["risked"]).round(2)
    return sel.drop(columns=["day"]).reset_index(drop=True)


# ------------------------------------------------------------------ evaluation
def _bootstrap_roi(profit: np.ndarray, risked: np.ndarray, n_boot: int = 2000, seed: int = 7,
                   groups: np.ndarray | None = None) -> tuple[float, float, float]:
    """ROI with a percentile bootstrap; with ``groups`` (match ids / matchdays) whole clusters are resampled,
    which is the honest interval when several contracts of one match are correlated."""
    if len(profit) == 0 or risked.sum() == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    if groups is not None:
        uniq, inv = np.unique(np.asarray(groups).astype(str), return_inverse=True)
        gp = np.bincount(inv, weights=profit, minlength=len(uniq))
        gr = np.bincount(inv, weights=risked, minlength=len(uniq))
        idx = rng.integers(0, len(uniq), size=(n_boot, len(uniq)))
        rois = gp[idx].sum(axis=1) / gr[idx].sum(axis=1)
    else:
        idx = rng.integers(0, len(profit), size=(n_boot, len(profit)))
        rois = profit[idx].sum(axis=1) / risked[idx].sum(axis=1)
    return float(profit.sum() / risked.sum()), float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5))


def summarize_pro(sel: pd.DataFrame, rules: StakingRules) -> dict:
    """Flat and Kelly-weighted ROI, CLV, drawdown for a selected bet list with known results."""
    if sel is None or sel.empty or "won" not in sel or sel["won"].isna().all():
        return {"n": 0}
    s = sel[sel["won"].notna()].copy()
    profit = s["profit"].to_numpy(dtype=float)
    risked = s["risked"].to_numpy(dtype=float)
    days = pd.to_datetime(s["kickoff"], utc=True).dt.date.astype(str).to_numpy()
    roi, lo, hi = _bootstrap_roi(profit, risked, groups=days)   # matchday clusters
    contracts = s["contracts"].to_numpy(dtype=float)
    kelly_profit = (profit * contracts).sum()
    kelly_risked = (risked * contracts).sum()
    # equity curve with the rules' bankroll, non-compounding stakes, for drawdown
    equity = rules.bankroll + np.cumsum(profit * contracts)
    peak = np.maximum.accumulate(np.concatenate([[rules.bankroll], equity]))
    dd = float(((peak[1:] - equity) / peak[1:]).max()) if len(equity) else 0.0
    out = {
        "n": int(len(s)), "flat_roi": roi, "flat_roi_ci_low": lo, "flat_roi_ci_high": hi,
        "win_rate": float(s["won"].astype(float).mean()),
        "kelly_staked": float(kelly_risked), "kelly_profit": float(kelly_profit),
        "kelly_roi": float(kelly_profit / kelly_risked) if kelly_risked else np.nan,
        "max_drawdown": dd, "avg_confidence": float(s["confidence"].mean()), "avg_edge": float(s["edge"].mean()),
        "clv_close_mean": float(s["clv_close"].mean()) if s["clv_close"].notna().any() else np.nan,
        "clv_close_positive": float((s["clv_close"] > 0).mean()) if s["clv_close"].notna().any() else np.nan,
        "clv_book_mean": float(s["clv_book"].mean()) if s["clv_book"].notna().any() else np.nan,
        "clv_book_positive": float((s["clv_book"] > 0).mean()) if s["clv_book"].notna().any() else np.nan,
    }
    return out


def tier_table(cands: pd.DataFrame) -> pd.DataFrame:
    """Realized results by confidence tier over ALL candidates (not just the portfolio) - the calibration of the score itself."""
    if cands is None or cands.empty or "won" not in cands:
        return pd.DataFrame()
    c = cands[cands["won"].notna()]
    rows = []
    for tier in ("A", "B", "C", "pass"):
        sub = c[c["tier"] == tier]
        if sub.empty:
            continue
        roi, lo, hi = _bootstrap_roi(sub["profit"].to_numpy(float), sub["risked"].to_numpy(float), n_boot=500,
                                     groups=sub["match_id"].to_numpy())
        rows.append({"tier": tier, "n": int(len(sub)), "roi": roi, "roi_ci_low": lo, "roi_ci_high": hi,
                     "win_rate": float(sub["won"].astype(float).mean()), "avg_edge": float(sub["edge"].mean()),
                     "clv_close_mean": float(sub["clv_close"].mean()) if sub["clv_close"].notna().any() else np.nan})
    return pd.DataFrame(rows)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return np.nan
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def edge_decile_table(cands: pd.DataFrame, n_bins: int = 10) -> tuple[pd.DataFrame, float]:
    """Realized ROI / CLV / hit-rate-minus-price by predicted-edge decile over all candidates.

    The proof that the edge means something: profits should rise with predicted
    edge (Spearman rho of decile rank vs realized ROI). A flat curve with one
    profitable threshold is overfitting.
    """
    if cands is None or cands.empty or "won" not in cands:
        return pd.DataFrame(), np.nan
    c = cands[cands["won"].notna()].copy()
    if len(c) < 20:
        return pd.DataFrame(), np.nan
    c["decile"] = pd.qcut(c["edge"].rank(method="first"), q=min(n_bins, max(2, len(c) // 10)), labels=False) + 1
    rows = []
    for d, sub in c.groupby("decile"):
        roi, lo, hi = _bootstrap_roi(sub["profit"].to_numpy(float), sub["risked"].to_numpy(float), n_boot=300,
                                     groups=sub["match_id"].to_numpy())
        rows.append({"decile": int(d), "n": int(len(sub)), "pred_edge": float(sub["edge"].mean()), "roi": roi,
                     "roi_ci_low": lo, "roi_ci_high": hi,
                     "hit_minus_price": float((sub["won"].astype(float) - sub["price"]).mean()),
                     "clv_close_mean": float(sub["clv_close"].mean()) if sub["clv_close"].notna().any() else np.nan})
    tab = pd.DataFrame(rows)
    return tab, _spearman(tab["decile"].to_numpy(float), tab["roi"].to_numpy(float))


def closing_line_distance(df: pd.DataFrame, sources: tuple[str, ...] = ("mktn", "book", "pro", "poisson", "elo")) -> pd.DataFrame:
    """Mean squared distance of each probability source to the de-vigged closing line (``bookc``).

    Converges far faster than ROI: a source that sits closer to the closing line
    than the venue does is the one to trust when they disagree.
    """
    rows = []
    if not has_sources(df, ("bookc",)).any():
        return pd.DataFrame()
    base = df[has_sources(df, ("bookc",))]
    target = base[_cols("bookc")].to_numpy(float)
    for s in sources:
        ok = has_sources(base, (s,))
        if not ok.any():
            continue
        est = base.loc[ok, _cols(s)].to_numpy(float)
        est = est / est.sum(axis=1, keepdims=True)
        d = ((est - target[ok.to_numpy()]) ** 2).sum(axis=1)
        rows.append({"source": s, "n": int(ok.sum()), "mse_vs_closing_line": float(d.mean()),
                     "mean_abs_diff_pts": float(np.abs(est - target[ok.to_numpy()]).mean() * 100)})
    return pd.DataFrame(rows)


def pro_backtest(df: pd.DataFrame, fees: FeeModel, rules: StakingRules, fill: str = "ask") -> dict:
    """Walk-forward professional strategy on the joined frame. Returns candidates, portfolio, summaries."""
    if "pro_home" not in df:
        df = walk_forward_pool(df)
    cands = build_candidates(df, fees, fill)
    sel = select_portfolio(cands, rules, fees)
    deciles, rho = edge_decile_table(cands)
    return {"frame": df, "candidates": cands, "portfolio": sel, "summary": summarize_pro(sel, rules),
            "tiers": tier_table(cands), "deciles": deciles, "decile_rho": rho,
            "closing_distance": closing_line_distance(df), "pool_weights": _last_weights(df)}


def _last_weights(df: pd.DataFrame) -> dict:
    return {"n_train_last": int(df["pro_n_train"].max()) if "pro_n_train" in df and len(df) else 0}


# ------------------------------------------------------------------ picks
def generate_picks(df_upcoming: pd.DataFrame, pools: dict[str, PoolFit], fees: FeeModel, rules: StakingRules,
                   fill: str = "ask") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(portfolio, all candidates, priced frame) for upcoming fixtures priced with fitted pools."""
    if df_upcoming is None or df_upcoming.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    priced = apply_pools(df_upcoming, pools)
    cands = build_candidates(priced, fees, fill)
    return select_portfolio(cands, rules, fees), cands, priced
