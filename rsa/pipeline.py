"""End-to-end orchestration: collect data, join it, run models and the backtest, write outputs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .config import FDCOUK_SEASON, FDCOUK_WARMUP_SEASONS, League, window_start_ts
from .fees import FeeModel
from .kalshi import KalshiClient, build_open_snapshots, build_snapshots
from .matching import check_settlement_consistency, join_snapshots, matched_frame
from .models import ModelSet, walk_forward
from .prices import PriceSnapshot, load_prices_csv, save_prices_csv
from .pro import StakingRules, fit_final_pools, generate_picks, walk_forward_pool
from .results import (Match, load_espn, load_fdcouk, load_fdcouk_fixtures, matches_from_frame, matches_to_frame,
                      merge_results)
from .teams import canonical, match_team

log = logging.getLogger(__name__)


@dataclass
class Bundle:
    matches: list[Match]
    warmup: list[Match]
    snapshots: list[PriceSnapshot]
    meta: dict = field(default_factory=dict)


def _kickoff_lookup(matches: list[Match]) -> Callable:
    def lookup(team_a: str, team_b: str, close_time: datetime | None) -> datetime | None:
        best = None
        for m in matches:
            if m.kickoff is None:
                continue
            if close_time is not None and abs((m.kickoff - close_time).total_seconds()) > 3 * 86400:
                continue
            names = [m.home, m.away]
            ra, rb = match_team(team_a, names), match_team(team_b, names)
            if ra and rb and ra != rb:
                dist = abs((m.kickoff - close_time).total_seconds()) if close_time else 0
                if best is None or dist < best[0]:
                    best = (dist, m.kickoff)
        return best[1] if best else None

    return lookup


def collect(
    leagues: list[League],
    start: date,
    end: date,
    kalshi: KalshiClient | None,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    espn_fetch: Callable[[str], str] | None = None,
    fd_fetch: Callable[[str], str] | None = None,
    warmup_days: int = 150,
    prices_csv: str | Path | None = None,
    use_candles: bool = True,
    minutes_before_kickoff: int = 0,
    fd_season: str = FDCOUK_SEASON,
    fd_warmup_seasons: tuple[str, ...] = FDCOUK_WARMUP_SEASONS,
) -> Bundle:
    """Pull results, odds and venue prices for ``leagues`` between ``start`` and ``end``."""
    matches: list[Match] = []
    warmup: list[Match] = []
    snaps: list[PriceSnapshot] = []
    meta: dict = {"leagues": {}, "start": start.isoformat(), "end": end.isoformat()}
    since_ts = window_start_ts(start)

    for lg in leagues:
        info: dict = {}
        espn = load_espn(lg, start, end, cache_dir, refresh, fetch=espn_fetch)
        info["espn_matches"] = len(espn)
        fd_window: list[Match] = []
        fd_all: list[Match] = []
        if lg.fdcouk:
            try:
                fd_all = load_fdcouk(lg, fd_season, cache_dir, refresh, fetch=fd_fetch)
            except Exception as e:  # noqa: BLE001
                log.warning("football-data.co.uk %s/%s failed: %s", lg.key, fd_season, e)
            fd_window = [m for m in fd_all if m.kickoff and start <= m.kickoff.date() <= end]
            for season in fd_warmup_seasons:
                try:
                    warmup.extend(load_fdcouk(lg, season, cache_dir, refresh, fetch=fd_fetch))
                except Exception as e:  # noqa: BLE001
                    log.warning("football-data.co.uk %s/%s failed: %s", lg.key, season, e)
            warmup.extend(m for m in fd_all if m.kickoff and m.kickoff.date() < start)
        info["fdcouk_matches"] = len(fd_window)
        if espn:
            lg_matches = merge_results(espn, fd_window)
        else:
            log.warning("No ESPN results for %s; using football-data.co.uk fixtures", lg.key)
            lg_matches = fd_window
        if not lg.fdcouk and warmup_days > 0:
            w_start = start - timedelta(days=warmup_days)
            warmup.extend(load_espn(lg, w_start, start - timedelta(days=1), cache_dir, refresh, fetch=espn_fetch))
        matches.extend(lg_matches)

        if kalshi is not None:
            try:
                markets = kalshi.settled_markets_since(lg.kalshi_series, since_ts)
            except Exception as e:  # noqa: BLE001
                log.warning("Kalshi %s failed: %s", lg.kalshi_series, e)
                markets = []
            info["kalshi_markets"] = len(markets)
            lg_snaps = build_snapshots(kalshi, lg.key, lg.kalshi_series, markets, _kickoff_lookup(lg_matches),
                                       minutes_before_kickoff, use_candles)
            lg_snaps = [s for s in lg_snaps if s.kickoff is None or start <= s.kickoff.date() <= end]
            info["kalshi_snapshots"] = len(lg_snaps)
            snaps.extend(lg_snaps)
        meta["leagues"][lg.key] = info

    if prices_csv:
        extra = load_prices_csv(prices_csv)
        meta["csv_snapshots"] = len(extra)
        snaps.extend(extra)
    return Bundle(matches=matches, warmup=warmup, snapshots=snaps, meta=meta)


# ------------------------------------------------------------------ persistence
def save_bundle(bundle: Bundle, data_dir: str | Path) -> None:
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    matches_to_frame(bundle.matches).to_csv(d / "matches.csv", index=False)
    matches_to_frame(bundle.warmup).to_csv(d / "warmup.csv", index=False)
    save_prices_csv(bundle.snapshots, d / "snapshots.csv")
    (d / "meta.json").write_text(json.dumps(bundle.meta, indent=2, default=str), encoding="utf-8")


def load_bundle(data_dir: str | Path) -> Bundle:
    d = Path(data_dir)
    if not (d / "matches.csv").exists():
        raise FileNotFoundError(f"{d}/matches.csv not found - run `rsa fetch` (or `rsa demo`) first")
    matches = matches_from_frame(pd.read_csv(d / "matches.csv"))
    warmup = matches_from_frame(pd.read_csv(d / "warmup.csv")) if (d / "warmup.csv").exists() else []
    snaps = load_prices_csv(d / "snapshots.csv") if (d / "snapshots.csv").exists() else []
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
    return Bundle(matches, warmup, snaps, meta)


# ------------------------------------------------------------------ analysis
def team_games_feature(df: pd.DataFrame, history: list[Match], lookback_days: int = 120) -> pd.Series:
    """Min over both teams of completed games in the ``lookback_days`` before kickoff (early-season noise guard)."""
    import bisect

    played: dict[str, list[datetime]] = {}
    for m in history:
        if m.completed and m.kickoff:
            played.setdefault(canonical(m.home), []).append(m.kickoff)
            played.setdefault(canonical(m.away), []).append(m.kickoff)
    for v in played.values():
        v.sort()

    def count(team: str, kickoff) -> int:
        ts = played.get(canonical(team), [])
        if not ts or kickoff is None or pd.isna(kickoff):
            return 0
        k = pd.Timestamp(kickoff).to_pydatetime()
        lo = bisect.bisect_left(ts, k - timedelta(days=lookback_days))
        hi = bisect.bisect_left(ts, k)
        return hi - lo

    return pd.Series([min(count(r["home"], r["kickoff"]), count(r["away"], r["kickoff"])) for _, r in df.iterrows()], index=df.index)


def rest_days_feature(df: pd.DataFrame, history: list[Match], cap: float = 14.0) -> tuple[pd.Series, pd.Series]:
    """Days since each team's previous match (any fetched competition), capped; NaN when unknown."""
    import bisect

    played: dict[str, list[datetime]] = {}
    for m in history:
        if m.kickoff:
            played.setdefault(canonical(m.home), []).append(m.kickoff)
            played.setdefault(canonical(m.away), []).append(m.kickoff)
    for v in played.values():
        v.sort()

    def rest(team: str, kickoff) -> float:
        ts = played.get(canonical(team), [])
        if not ts or kickoff is None or pd.isna(kickoff):
            return float("nan")
        k = pd.Timestamp(kickoff).to_pydatetime()
        i = bisect.bisect_left(ts, k - timedelta(minutes=1))
        if i == 0:
            return float("nan")
        return min(cap, (k - ts[i - 1]).total_seconds() / 86400)

    home = pd.Series([rest(r["home"], r["kickoff"]) for _, r in df.iterrows()], index=df.index)
    away = pd.Series([rest(r["away"], r["kickoff"]) for _, r in df.iterrows()], index=df.index)
    return home, away


def build_frame(bundle: Bundle) -> tuple[pd.DataFrame, list[dict]]:
    """Join venue snapshots to matches and attach walk-forward model probabilities."""
    matched, unmatched = join_snapshots(bundle.snapshots, bundle.matches)
    df = matched_frame(matched)
    if df.empty:
        return df, unmatched
    preds = walk_forward(bundle.matches, bundle.warmup)
    for name in ("elo", "poisson"):
        for i, o in enumerate(("home", "draw", "away")):
            df[f"{name}_{o}"] = df["match_id"].map(lambda mid, name=name, i=i: preds.get(mid, {}).get(name, (None, None, None))[i])
            df[f"{name}_{o}"] = pd.to_numeric(df[f"{name}_{o}"], errors="coerce")
    df["team_games"] = team_games_feature(df, bundle.warmup + bundle.matches)
    df["rest_home"], df["rest_away"] = rest_days_feature(df, bundle.warmup + bundle.matches)
    return df, unmatched


# ------------------------------------------------------------------ upcoming / picks
@dataclass
class Upcoming:
    matches: list[Match]
    snapshots: list[PriceSnapshot]
    meta: dict = field(default_factory=dict)


def collect_upcoming(
    leagues: list[League],
    kalshi: KalshiClient | None,
    days: int = 7,
    today: date | None = None,
    cache_dir: str | Path | None = None,
    refresh: bool = True,
    espn_fetch: Callable[[str], str] | None = None,
    fd_fetch: Callable[[str], str] | None = None,
    with_last_trade: bool = True,
    now: datetime | None = None,
) -> Upcoming:
    """Fixtures in the next ``days`` days with current bookmaker odds and open venue quotes."""
    today = today or date.today()
    end = today + timedelta(days=days)
    matches: list[Match] = []
    snaps: list[PriceSnapshot] = []
    meta: dict = {"today": today.isoformat(), "days": days, "leagues": {}}
    try:
        fixtures = load_fdcouk_fixtures(leagues, cache_dir, refresh, fetch=fd_fetch)
    except Exception as e:  # noqa: BLE001
        log.warning("football-data.co.uk fixtures failed: %s", e)
        fixtures = []
    for lg in leagues:
        espn = [m for m in load_espn(lg, today, end, cache_dir, refresh, fetch=espn_fetch) if not m.completed]
        lg_fix = [m for m in fixtures if m.league == lg.key]
        lg_matches = merge_results(espn, lg_fix) if espn else lg_fix
        matches.extend(lg_matches)
        info = {"fixtures": len(lg_matches), "with_book_odds": sum(1 for m in lg_matches if any(k.endswith("_home") for k in m.odds))}
        if kalshi is not None:
            try:
                markets = kalshi.open_markets(lg.kalshi_series)
            except Exception as e:  # noqa: BLE001
                log.warning("Kalshi open markets %s failed: %s", lg.kalshi_series, e)
                markets = []
            lg_snaps = build_open_snapshots(kalshi, lg.key, lg.kalshi_series, markets, _kickoff_lookup(lg_matches), now,
                                            with_last_trade)
            lg_snaps = [s for s in lg_snaps if s.kickoff is not None and today <= s.kickoff.date() <= end]
            info["open_markets"] = len(markets)
            info["open_snapshots"] = len(lg_snaps)
            snaps.extend(lg_snaps)
        meta["leagues"][lg.key] = info
    return Upcoming(matches, snaps, meta)


def upcoming_frame(up: Upcoming, history: list[Match], now: datetime | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Joined frame for upcoming fixtures with models fitted on everything completed so far."""
    matched, unmatched = join_snapshots(up.snapshots, up.matches)
    df = matched_frame(matched)
    if df.empty:
        return df, unmatched
    completed = [m for m in history if m.completed and m.kickoff]
    models = ModelSet().fit(completed, as_of=now, upcoming=up.matches)
    preds = {m.match_id: models.predict(m) for m in up.matches}
    for name in ("elo", "poisson"):
        for i, o in enumerate(("home", "draw", "away")):
            df[f"{name}_{o}"] = df["match_id"].map(lambda mid, name=name, i=i: preds.get(mid, {}).get(name, (None, None, None))[i])
            df[f"{name}_{o}"] = pd.to_numeric(df[f"{name}_{o}"], errors="coerce")
    df["team_games"] = team_games_feature(df, history)
    df["rest_home"], df["rest_away"] = rest_days_feature(df, history + up.matches)
    from .backtest import add_normalized_market

    return add_normalized_market(df), unmatched


def run_picks(history_bundle: Bundle | None, up: Upcoming, fees: FeeModel, rules: StakingRules, fill: str = "ask",
              now: datetime | None = None) -> dict:
    """Price upcoming fixtures with pools fitted on the settled history and select a portfolio."""
    history_matches: list[Match] = []
    pools = None
    hist_df = pd.DataFrame()
    if history_bundle is not None:
        history_matches = history_bundle.warmup + history_bundle.matches
        hist_df, _ = build_frame(history_bundle)
        if not hist_df.empty:
            from .backtest import add_normalized_market

            hist_df = walk_forward_pool(add_normalized_market(hist_df))
            pools = fit_final_pools(hist_df)
    if pools is None:
        from .pro import prior_fit

        pools = {k: prior_fit(k) for k in ("full", "nobook")}
    df_up, unmatched = upcoming_frame(up, history_matches, now)
    portfolio, candidates, priced = generate_picks(df_up, pools, fees, rules, fill)
    return {"frame": priced if not priced.empty else df_up, "portfolio": portfolio, "candidates": candidates, "unmatched": unmatched, "pools": pools,
            "history_n": int(hist_df["result"].isin(("home", "draw", "away")).sum()) if not hist_df.empty else 0}


def write_picks(res: dict, up: Upcoming, out_dir: str | Path, meta: dict) -> Path:
    from .report import render_picks

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if res["portfolio"] is not None and not res["portfolio"].empty:
        res["portfolio"].to_csv(out / "picks.csv", index=False)
    if res["candidates"] is not None and not res["candidates"].empty:
        res["candidates"].to_csv(out / "picks_candidates.csv", index=False)
    if not res["frame"].empty:
        res["frame"].to_csv(out / "upcoming.csv", index=False)
    pd.DataFrame(res["unmatched"]).to_csv(out / "upcoming_unmatched.csv", index=False)
    text = render_picks(res, up, meta)
    (out / "picks.md").write_text(text, encoding="utf-8")
    return out / "picks.md"


def analyze(bundle: Bundle, fees: FeeModel, min_edge: float = 0.03, fill: str = "ask", slippage: float = 0.0,
            rules: StakingRules | None = None) -> tuple[BacktestResult | None, pd.DataFrame, list[dict]]:
    df, unmatched = build_frame(bundle)
    if df.empty:
        return None, df, unmatched
    result = run_backtest(df, fees, min_edge=min_edge, fill=fill, slippage=slippage, rules=rules)
    return result, result.frame, unmatched


def write_outputs(result: BacktestResult | None, df: pd.DataFrame, unmatched: list[dict], bundle: Bundle,
                  out_dir: str | Path, meta: dict) -> Path:
    from .report import render_markdown, summary_json

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_csv(out / "joined.csv", index=False)
    pd.DataFrame(unmatched).to_csv(out / "unmatched_events.csv", index=False)
    if result is not None:
        for name, bets in result.bets.items():
            if bets is not None and not bets.empty:
                bets.to_csv(out / f"bets_{name}.csv", index=False)
        for name in ("portfolio", "candidates"):
            frame = result.pro.get(name)
            if frame is not None and not frame.empty:
                frame.to_csv(out / f"pro_{name}.csv", index=False)
        consistency = check_settlement_consistency(df)
        meta = dict(meta, settlement_mismatches=int(len(consistency)), unmatched_events=len(unmatched),
                    n_matches_window=len(bundle.matches), n_warmup=len(bundle.warmup), n_snapshots=len(bundle.snapshots))
        (out / "summary.json").write_text(json.dumps(summary_json(result, meta), indent=2, default=str), encoding="utf-8")
    text = render_markdown(result, df, unmatched, bundle, meta)
    (out / "report.md").write_text(text, encoding="utf-8")
    return out / "report.md"
