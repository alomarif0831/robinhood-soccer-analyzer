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


def summary_json(result: BacktestResult, meta: dict) -> dict:
    return {
        "meta": meta,
        "n_matches": result.n_matches,
        "scores": result.scores.to_dict("records"),
        "bias_by_outcome": result.bias_by_outcome.to_dict("records"),
        "market_vs_book": result.market_vs_book.to_dict("records") if not result.market_vs_book.empty else [],
        "naive": result.naive.to_dict("records"),
        "strategies": result.strategies,
        "verdicts": verdicts(result),
    }
