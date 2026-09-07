"""Markdown report rendering for backtest results."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

from .backtest import BacktestResult


def _fmt(v, pct=False, digits=3, signed=False):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return f"{v:,}"
    if isinstance(v, float):
        if pct:
            return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"
        return f"{v:.{digits}f}"
    return str(v)


def md_table(df: pd.DataFrame, pct_cols: tuple[str, ...] = (), digits: int = 3, max_rows: int = 60) -> str:
    if df is None or df.empty:
        return "_no data_\n"
    df = df.head(max_rows)
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (pd.Timestamp, datetime)):
                cells.append(v.strftime("%Y-%m-%d %H:%M"))
            elif isinstance(v, float) and float(v).is_integer() and c in ("n",):
                cells.append(str(int(v)))
            else:
                cells.append(_fmt(v, pct=c in pct_cols, digits=digits, signed=str(c).startswith("roi")))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _strategy_table(strategies: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for name, s in strategies.items():
        rows.append({"reference": name, **{k: s.get(k) for k in ("n", "risked", "profit", "roi", "roi_ci_low", "roi_ci_high", "win_rate", "avg_price", "avg_edge", "p_value_profit_le_0")}})
    return pd.DataFrame(rows)


def verdicts(result: BacktestResult) -> list[str]:
    """Plain-language conclusions that the numbers actually support."""
    out = []
    n = result.n_matches
    if n < 100:
        out.append(f"Only {n} priced, settled matches are in the sample. Confidence intervals below are wide; "
                   "treat everything as a hypothesis to keep testing, not a proven edge.")
    acc = result.accuracy_vs_book
    if acc and acc.get("n", 0) >= 2 and not math.isnan(acc.get("t", float("nan"))):
        d, t, n = acc["mean_diff"], acc["t"], acc["n"]
        if t >= 2:
            out.append(f"The venue's prices are less accurate than the sharp closing line (mean Brier gap {d:+.3f}, t={t:.1f}, n={n}). "
                       "That gap is where an edge would come from.")
        elif t <= -2:
            out.append(f"The venue's prices are *more* accurate than the closing line (mean Brier gap {d:+.3f}, t={t:.1f}, n={n}); "
                       "do not expect to beat them with public odds.")
        else:
            out.append(f"Venue prices and the closing line are statistically indistinguishable in accuracy "
                       f"(mean Brier gap {d:+.3f}, t={t:.1f}, n={n}).")
    for _, r in result.bias_by_outcome.iterrows():
        if abs(r.get("z", 0)) >= 2 and r["n"] >= 30:
            direction = "under" if r["diff"] > 0 else "over"
            out.append(f"{str(r['outcome']).capitalize()} contracts look {direction}priced: paid {r['mean_price']:.3f} on average, "
                       f"won {r['hit_rate']:.3f} of the time (n={int(r['n'])}, z={r['z']:.1f}).")
    if not result.market_vs_book.empty:
        for _, r in result.market_vs_book.iterrows():
            if abs(r.get("t", 0)) >= 2.5:
                cheap = r["mean_diff"] < 0
                out.append(f"Versus the closing line the venue prices the {r['outcome']} {'below' if cheap else 'above'} fair on average "
                           f"({r['mean_diff'] * 100:+.1f} pts, t={r['t']:.1f}, n={int(r['n'])}).")
    ps = (result.pro or {}).get("summary") or {}
    if ps.get("n", 0) >= 10:
        clv = ps.get("clv_close_mean")
        clv_txt = f", mean CLV vs venue close {clv * 100:+.1f} pts" if clv is not None and not math.isnan(clv) else ""
        out.append(f"Professional rules would have placed {ps['n']} bets: flat ROI {ps['flat_roi'] * 100:+.1f}% "
                   f"(95% CI {ps['flat_roi_ci_low'] * 100:+.1f}% to {ps['flat_roi_ci_high'] * 100:+.1f}%), Kelly ROI {ps['kelly_roi'] * 100:+.1f}%, "
                   f"max drawdown {ps['max_drawdown'] * 100:.1f}%{clv_txt}.")
    for name, s in result.strategies.items():
        if s["n"] >= 20 and not math.isnan(s["roi"]):
            if s["roi_ci_low"] > 0:
                out.append(f"Betting where the **{name}** reference beats price+fees was profitable after fees: ROI {s['roi'] * 100:+.1f}% "
                           f"(95% CI {s['roi_ci_low'] * 100:+.1f}% to {s['roi_ci_high'] * 100:+.1f}%, n={s['n']}). The interval excludes zero.")
            elif s["roi_ci_high"] < 0:
                out.append(f"Betting on the **{name}** reference lost money after fees: ROI {s['roi'] * 100:+.1f}% "
                           f"(95% CI {s['roi_ci_low'] * 100:+.1f}% to {s['roi_ci_high'] * 100:+.1f}%, n={s['n']}).")
            else:
                out.append(f"The **{name}**-based strategy's ROI of {s['roi'] * 100:+.1f}% (n={s['n']}) is not distinguishable from zero "
                           f"(95% CI {s['roi_ci_low'] * 100:+.1f}% to {s['roi_ci_high'] * 100:+.1f}%).")
    if not out:
        out.append("No statistically meaningful pattern found.")
    return out


def render_markdown(result: BacktestResult | None, df: pd.DataFrame, unmatched: list[dict], bundle, meta: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# Robinhood soccer prediction-market backtest", ""]
    if meta.get("synthetic"):
        lines += ["> **SYNTHETIC DEMO DATA.** Every price and score in this report was simulated by `rsa demo` "
                  "with planted biases so you can see what the analysis looks like. Nothing here is a real finding.", ""]
    lines += [f"Generated {now}. Window **{meta.get('start')} → {meta.get('end')}** (post-World-Cup). "
              f"Fee model: **{meta.get('fee_model', 'none')}**; fills at **{meta.get('fill', 'ask')}**"
              + (f" + {meta.get('slippage'):.2f} slippage" if meta.get("slippage") else "") + ".", ""]
    lines += [f"- Fixtures in window: {len(bundle.matches)} ({sum(1 for m in bundle.matches if m.completed)} completed); "
              f"warm-up results for models: {len(bundle.warmup)}",
              f"- Venue price snapshots: {len(bundle.snapshots)}; priced events matched to a fixture: "
              f"{0 if df.empty else df['match_id'].nunique()}; unmatched events: {len(unmatched)}", ""]
    if result is None or df.empty:
        lines += ["**No priced matches could be joined to results, so there is nothing to backtest.**", "",
                  "Check `unmatched_events.csv`, the league list, and that the venue series tickers are right (`rsa series`).", ""]
        return "\n".join(lines)

    lines += ["## Verdict", ""] + [f"- {v}" for v in verdicts(result)] + [""]

    lines += ["## Accuracy: venue vs reference probabilities", "",
              "Multiclass Brier score and log loss over the three outcomes (lower is better). `mktn` = venue prices "
              "normalized to sum to 1; `book` = de-vigged closing odds (Pinnacle when available); `elo`/`poisson` = "
              "walk-forward models; `blend` = 30% Poisson / 70% book.", "",
              md_table(result.scores), ""]

    lines += ["## Calibration of venue prices", "",
              "Each outcome contract bucketed by its pre-kickoff YES price. `diff` = hit rate − mean price; a positive "
              "diff means contracts in that bucket paid out more often than their price implied (cheap).", "",
              md_table(result.calibration), ""]

    lines += ["## Systematic bias by outcome", "", md_table(result.bias_by_outcome), "",
              "## By league", "",
              "`overround` = sum of the three YES prices − 1 (the venue's built-in margin); `brier_*` lower is better.", "",
              md_table(result.bias_by_league), ""]

    if not result.market_vs_book.empty:
        lines += ["## Venue price minus closing line", "",
                  "Mean of (normalized venue probability − de-vigged closing probability) per outcome. Negative = venue "
                  "cheaper than the sharp line.", "", md_table(result.market_vs_book, digits=4), ""]

    lines += ["## Naive rules (no model), after fees", "",
              "Buy one YES contract on every match under a fixed rule (`no_draw` buys NO on the draw). ROI = profit / dollars risked, "
              "with a bootstrap 95% interval.", "",
              md_table(result.naive, pct_cols=("roi", "roi_ci_low", "roi_ci_high", "win_rate")), ""]

    lines += ["## Reference-driven strategies, after fees", "",
              f"Buy any YES or NO contract whose reference probability exceeds fill price + fee by at least "
              f"{meta.get('min_edge', 0.03):.2f}.", "",
              md_table(_strategy_table(result.strategies), pct_cols=("roi", "roi_ci_low", "roi_ci_high", "win_rate")), ""]
    for name, sweep in result.sweeps.items():
        lines += [f"### Edge threshold sweep — {name}", "",
                  md_table(sweep, pct_cols=("roi", "roi_ci_low", "roi_ci_high", "win_rate")), ""]
    for name, bd in result.breakdowns.items():
        if bd is not None and not bd.empty:
            lines += [f"### Breakdown — {name}", "", md_table(bd, pct_cols=("roi", "roi_ci_low", "roi_ci_high", "win_rate")), ""]

    lines += render_pro_section(result)

    best = max(result.strategies.items(), key=lambda kv: (kv[1]["n"] > 0, kv[1].get("roi", float("-inf")) if not math.isnan(kv[1].get("roi", float("nan"))) else float("-inf")), default=None)
    if best and best[0] in result.bets and not result.bets[best[0]].empty:
        sample = result.bets[best[0]].sort_values("edge", ascending=False).head(15)
        sample = sample[["kickoff", "league", "home", "away", "outcome", "side", "price", "fee", "fair", "edge", "won", "profit"]]
        lines += [f"## Largest-edge bets — {best[0]} reference", "", md_table(sample), ""]

    lines += ["## How to read this", "",
              "- A real, exploitable edge needs three things at once: a bias that is stable across leagues/weeks, "
              "ROI whose confidence interval excludes zero **after fees**, and fills at the ask (not the last trade).",
              "- Brier/log-loss differences of < 0.005 are noise at this sample size.",
              "- Model-based strategies (Elo, Poisson) are weak references; `book` (the closing line) is the strongest "
              "public benchmark. If a strategy only wins against Elo, that is not evidence of an edge.",
              "- Rothera-routed Robinhood contracts have no public API; import them with `--prices-csv` to include them.", ""]
    if meta.get("settlement_mismatches"):
        lines += [f"**Warning:** {meta['settlement_mismatches']} venue settlements disagree with the scoreline; see `joined.csv`.", ""]
    return "\n".join(lines)


def _rules_line(rules) -> str:
    return (f"bankroll ${rules.bankroll:,.0f}, {rules.kelly_fraction:.2f}× Kelly, max {rules.max_bet_fraction * 100:.0f}% per bet, "
            f"{rules.max_day_fraction * 100:.0f}% per day, {rules.max_bets_per_day} bets/day, confidence ≥ {rules.min_confidence:.0f}, "
            f"edge ≥ {rules.min_edge:.2f}")


def render_pro_section(result: BacktestResult) -> list[str]:
    pro = result.pro or {}
    if not pro:
        return []
    s = pro.get("summary", {}) or {}
    rules = pro.get("rules")
    lines = ["## Professional strategy: pooled fair value, confidence tiers, fractional Kelly", "",
             "Fair probabilities pool the bookmaker line, the venue's own price and the two models with weights fitted "
             "walk-forward (only on earlier matches) and bootstrapped for uncertainty. A bet needs a confident, fee-adjusted "
             "edge, agreement between independent sources, a tight and fresh market, and a sane price band. One bet per "
             "match, fractional Kelly stakes, daily caps.", ""]
    if rules is not None:
        lines += [f"Rules: {_rules_line(rules)}. Gates: quote consistency, spread ≤ {rules.max_spread:.2f}, price "
                  f"{rules.min_price:.2f}–{rules.max_price:.2f}, last trade ≤ {rules.max_stale_hours:.0f}h old, conservative edge "
                  f"(20th pct) ≥ {rules.min_edge_q20:.2f}, edge vs mid ≥ {rules.min_edge_mid:.2f}, bookmaker line alone ≥ "
                  f"{rules.min_book_edge:.2f} after fees, lot ≥ {rules.min_contracts} contracts.", ""]
    pw = pro.get("pool_weights") or {}
    if pw:
        rows = [{"source_set": k, **{f"w_{src}": w for src, w in v["weights"].items()},
                 "intercepts(h,d,a)": ", ".join(f"{x:+.2f}" for x in v["intercepts"]), "n_train": v["n_train"]} for k, v in pw.items()]
        lines += ["Pooling weights fitted on the whole sample (the walk-forward fits use only earlier matches):", "",
                  md_table(pd.DataFrame(rows), digits=2), ""]
    if s.get("n", 0) == 0:
        lines += ["No bet passed the rules in this sample.", ""]
        return lines
    summ = pd.DataFrame([{k: s.get(k) for k in ("n", "flat_roi", "flat_roi_ci_low", "flat_roi_ci_high", "win_rate", "kelly_staked",
                                                "kelly_profit", "kelly_roi", "max_drawdown", "avg_confidence", "avg_edge")}])
    lines += [md_table(summ, pct_cols=("flat_roi", "flat_roi_ci_low", "flat_roi_ci_high", "win_rate", "kelly_roi", "max_drawdown")), ""]
    clv = pd.DataFrame([{"clv_vs_venue_close_mean": s.get("clv_close_mean"), "clv_vs_venue_close_positive": s.get("clv_close_positive"),
                         "clv_vs_book_mean": s.get("clv_book_mean"), "clv_vs_book_positive": s.get("clv_book_positive")}])
    lines += ["Closing line value (CLV): entry price vs the venue's price at kickoff and vs the de-vigged closing line. "
              "Consistently positive CLV is the earliest reliable evidence of an edge; it needs the entry snapshot to be "
              "taken before kickoff (`--minutes-before`).", "",
              md_table(clv, pct_cols=("clv_vs_venue_close_positive", "clv_vs_book_positive"), digits=4), ""]
    tiers = pro.get("tiers")
    if tiers is not None and not tiers.empty:
        lines += ["Realized results of **all** candidate contracts by confidence tier (does the score rank bets correctly?):", "",
                  md_table(tiers, pct_cols=("roi", "roi_ci_low", "roi_ci_high", "win_rate"), digits=4), ""]
    dec = pro.get("deciles")
    if dec is not None and not dec.empty:
        rho = pro.get("decile_rho")
        lines += [f"Edge-decile monotonicity over all candidates (Spearman rho of decile vs realized ROI = "
                  f"{'n/a' if rho is None or math.isnan(rho) else f'{rho:+.2f}'}; a real edge shows profits rising with predicted edge):", "",
                  md_table(dec, pct_cols=("roi", "roi_ci_low", "roi_ci_high"), digits=4), ""]
    cd = pro.get("closing_distance")
    if cd is not None and not cd.empty:
        lines += ["Distance of each probability source to the de-vigged **closing** line (lower = closer to the sharpest price; "
                  "this converges much faster than ROI):", "", md_table(cd, digits=4), ""]
    port = pro.get("portfolio")
    if port is not None and not port.empty:
        cols = ["kickoff", "league", "home", "away", "outcome", "side", "price", "fee", "fair", "fair_sd", "edge", "edge_z",
                "agreement", "confidence", "tier", "contracts", "clv_close", "won", "profit"]
        lines += ["Bets the rules would have placed (first 20):", "", md_table(port[[c for c in cols if c in port]].head(20)), ""]
    return lines


def _why(row) -> str:
    parts = []
    if row.get("agreement") is not None and not (isinstance(row.get("agreement"), float) and math.isnan(row["agreement"])):
        parts.append(f"sources agree {row['agreement'] * 100:.0f}%")
    if row.get("spread") is not None and not (isinstance(row.get("spread"), float) and math.isnan(row["spread"])):
        parts.append(f"spread {row['spread']:.2f}")
    if row.get("stale_hours") is not None and not (isinstance(row.get("stale_hours"), float) and math.isnan(row["stale_hours"])):
        parts.append(f"last trade {row['stale_hours']:.0f}h ago")
    parts.append(f"z={row['edge_z']:.1f}")
    return "; ".join(parts)


def render_picks(res: dict, up, meta: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rules = meta.get("rules")
    lines = ["# Upcoming picks", ""]
    if meta.get("synthetic"):
        lines += ["> **SYNTHETIC DEMO DATA.** These fixtures, quotes and odds are simulated. Nothing here is a real recommendation.", ""]
    lines += [f"Generated {now}. Fixtures in the next {up.meta.get('days', '?')} days from {up.meta.get('today', '?')}: {len(up.matches)}; "
              f"open venue markets matched: {0 if res['frame'].empty else res['frame']['match_id'].nunique()}; unmatched events: {len(res['unmatched'])}. "
              f"Pools fitted on {res.get('history_n', 0)} settled priced matches" + (" (prior weights: not enough history yet)." if res.get("history_n", 0) < 40 else "."), ""]
    if rules is not None:
        lines += [f"Rules: {_rules_line(rules)}; fees **{meta.get('fee_model', 'none')}**; fills at {meta.get('fill', 'ask')}.", ""]
    port = res.get("portfolio")
    if port is None or port.empty:
        lines += ["**No pick meets the confidence and edge thresholds right now.** That is the normal outcome most days; "
                  "lower `--min-confidence` only if you accept a weaker filter.", ""]
    else:
        rows = []
        for _, r in port.iterrows():
            rows.append({"kickoff": r["kickoff"], "league": r["league"], "match": f"{r['home']} v {r['away']}",
                         "bet": f"{r['side'].upper()} {r['outcome']}", "price": r["price"], "fee": r["fee"], "fair": r["fair"],
                         "edge": r["edge"], "conf": r["confidence"], "tier": r["tier"], "stake_$": r["stake"], "contracts": int(r["contracts"]),
                         "why": _why(r)})
        lines += [f"## {len(port)} pick(s)", "", md_table(pd.DataFrame(rows)), ""]
    cands = res.get("candidates")
    if cands is not None and not cands.empty:
        near = cands[(cands["edge"] > 0)].sort_values("confidence", ascending=False)
        if port is not None and not port.empty:
            near = near[~near.set_index(["match_id", "outcome", "side"]).index.isin(port.set_index(["match_id", "outcome", "side"]).index)]
        near = near.head(12)
        if not near.empty:
            cols = ["kickoff", "league", "home", "away", "outcome", "side", "price", "fair", "fair_sd", "edge", "edge_z", "agreement", "spread", "confidence", "tier"]
            lines += ["## Positive-edge contracts that did not qualify", "", md_table(near[cols]), ""]
    lines += ["## Read before betting", "",
              "- Confidence = edge significance (35, full at z = 1.5) + edge size (15, full at 6 pts) + source agreement (20) + liquidity (15) + price band (10) + freshness (5), "
              "scaled down when the pools are still on prior weights or a team has played fewer than 5 games.",
              "- Fair probabilities lean on the bookmaker line; where none exists (e.g. MLS without a line) the venue price and the models carry it, "
              "so those picks deserve extra skepticism.",
              "- Prices move: re-run right before placing, and buy at or below the quoted price. Never buy two outcomes of one match.",
              "- Track every bet and its closing price. If your bets do not beat the closing line on average after 50+ bets, stop.", ""]
    return "\n".join(lines)


def summary_json(result: BacktestResult, meta: dict) -> dict:
    return {
        "meta": meta,
        "n_matches": result.n_matches,
        "scores": result.scores.to_dict("records"),
        "bias_by_outcome": result.bias_by_outcome.to_dict("records"),
        "market_vs_book": result.market_vs_book.to_dict("records") if not result.market_vs_book.empty else [],
        "naive": result.naive.to_dict("records"),
        "strategies": result.strategies,
        "pro": {k: v for k, v in (result.pro or {}).items() if k in ("summary", "pool_weights", "decile_rho")},
        "pro_tiers": _recs(result.pro.get("tiers")) if result.pro else [],
        "pro_deciles": _recs(result.pro.get("deciles")) if result.pro else [],
        "closing_distance": _recs(result.pro.get("closing_distance")) if result.pro else [],
        "calibration": _recs(result.calibration),
        "bias_by_league": _recs(result.bias_by_league),
        "accuracy_vs_book": result.accuracy_vs_book,
        "sweeps": {k: _recs(v) for k, v in result.sweeps.items()},
        "breakdowns": {k: _recs(v) for k, v in result.breakdowns.items()},
        "verdicts": verdicts(result),
    }


def _recs(df) -> list:
    if df is None or (hasattr(df, "empty") and df.empty):
        return []
    import json as _json

    return _json.loads(df.to_json(orient="records", date_format="iso"))
