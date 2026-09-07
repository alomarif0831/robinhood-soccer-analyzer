"""Command-line interface.

    rsa series                       list Kalshi soccer series (live)
    rsa fetch    --data-dir data/live   pull results, odds and venue prices
    rsa backtest --data-dir data/live   analyze what was fetched (offline)
    rsa run                          fetch + backtest
    rsa demo                         synthetic end-to-end run (no network)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .config import DEFAULT_LEAGUES, LEAGUES, WINDOW_START, leagues_from_keys
from .fees import FEE_MODELS, get_fee_model


def _date(s: str) -> date:
    return date.fromisoformat(s)


def _add_common_analysis(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fees", default="robinhood", choices=sorted(FEE_MODELS), help="fee model (default: robinhood, non-Gold)")
    p.add_argument("--min-edge", type=float, default=0.03, help="minimum (fair - price - fee) to bet, default 0.03")
    p.add_argument("--fill", default="ask", choices=("ask", "last"), help="fill YES at the ask / NO at 1-bid (default) or at last trade")
    p.add_argument("--slippage", type=float, default=0.0, help="extra cents (in dollars) added to every fill")
    p.add_argument("--out", default=None, help="report directory (default: reports/<data-dir name>)")


def _add_fetch_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--leagues", default=",".join(DEFAULT_LEAGUES), help=f"comma list from: {', '.join(LEAGUES)}")
    p.add_argument("--start", type=_date, default=WINDOW_START, help="first kickoff date (default: day after the World Cup final)")
    p.add_argument("--end", type=_date, default=date.today(), help="last kickoff date (default: today)")
    p.add_argument("--data-dir", default="data/live")
    p.add_argument("--refresh", action="store_true", help="ignore cached API responses")
    p.add_argument("--no-kalshi", action="store_true", help="skip Kalshi (results/odds only, e.g. with --prices-csv)")
    p.add_argument("--no-candles", action="store_true", help="skip candlestick requests (no bid/ask; fills use last trade)")
    p.add_argument("--minutes-before", type=int, default=0, help="snapshot this many minutes before kickoff")
    p.add_argument("--warmup-days", type=int, default=150, help="ESPN history for model warm-up in leagues without football-data.co.uk")
    p.add_argument("--prices-csv", default=None, help="extra price snapshots (e.g. Rothera/Robinhood export), see rsa/prices.py")
    p.add_argument("--kalshi-base-url", default=None)
    p.add_argument("--kalshi-key-id", default=os.environ.get("KALSHI_API_KEY_ID"))
    p.add_argument("--kalshi-private-key", default=os.environ.get("KALSHI_PRIVATE_KEY_PATH"))
    p.add_argument("--rps", type=float, default=8.0, help="max Kalshi requests per second")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rsa", description="Robinhood soccer prediction-market backtester")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("series", help="list Kalshi soccer series tickers")
    s.add_argument("--kalshi-base-url", default=None)

    f = sub.add_parser("fetch", help="download results, odds and venue prices")
    _add_fetch_args(f)

    b = sub.add_parser("backtest", help="analyze previously fetched data (offline)")
    b.add_argument("--data-dir", default="data/live")
    _add_common_analysis(b)

    r = sub.add_parser("run", help="fetch then backtest")
    _add_fetch_args(r)
    _add_common_analysis(r)

    d = sub.add_parser("demo", help="generate synthetic data and run the full pipeline offline")
    d.add_argument("--data-dir", default="data/demo")
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--leagues", default=",".join(DEFAULT_LEAGUES))
    _add_common_analysis(d)
    return p


def _client(args):
    from .kalshi import KalshiClient

    kw = {}
    if getattr(args, "kalshi_base_url", None):
        kw["base_url"] = args.kalshi_base_url
    return KalshiClient(cache_dir=Path(args.data_dir) / "cache" if hasattr(args, "data_dir") else None,
                        refresh=getattr(args, "refresh", False), requests_per_second=getattr(args, "rps", 8.0),
                        key_id=getattr(args, "kalshi_key_id", None), private_key_path=getattr(args, "kalshi_private_key", None), **kw)


def cmd_series(args) -> int:
    client = _client(args)
    rows = client.soccer_series()
    if not rows:
        print("No soccer series found (or the API was unreachable).")
        return 1
    for s in rows:
        print(f"{s.get('ticker'):<24} {s.get('title', '')}  [{s.get('frequency', '')}]")
    return 0


def cmd_fetch(args) -> int:
    from .pipeline import collect, save_bundle

    leagues = leagues_from_keys(args.leagues.split(","))
    for lg in leagues:
        if not lg.series_verified:
            logging.warning("Series ticker %s for %s is inferred, not verified; check `rsa series`.", lg.kalshi_series, lg.key)
    client = None if args.no_kalshi else _client(args)
    bundle = collect(leagues, args.start, args.end, client, cache_dir=Path(args.data_dir) / "cache", refresh=args.refresh,
                     warmup_days=args.warmup_days, prices_csv=args.prices_csv, use_candles=not args.no_candles,
                     minutes_before_kickoff=args.minutes_before)
    save_bundle(bundle, args.data_dir)
    print(f"Saved {len(bundle.matches)} fixtures, {len(bundle.warmup)} warm-up results and {len(bundle.snapshots)} price snapshots to {args.data_dir}")
    for k, v in bundle.meta.get("leagues", {}).items():
        print(f"  {k:<12} {v}")
    return 0


def _analyze_and_write(bundle, args, extra_meta: dict | None = None) -> int:
    from .pipeline import analyze, write_outputs

    fees = get_fee_model(args.fees)
    result, df, unmatched = analyze(bundle, fees, min_edge=args.min_edge, fill=args.fill, slippage=args.slippage)
    out = args.out or str(Path("reports") / Path(args.data_dir).name)
    meta = dict(bundle.meta, fee_model=args.fees, min_edge=args.min_edge, fill=args.fill, slippage=args.slippage, **(extra_meta or {}))
    path = write_outputs(result, df, unmatched, bundle, out, meta)
    print(f"Report written to {path}")
    if result is None:
        print("Nothing to backtest: no priced matches joined to results.")
        return 2
    from .report import verdicts

    for v in verdicts(result):
        print(f"- {v}")
    return 0


def cmd_backtest(args) -> int:
    from .pipeline import load_bundle

    bundle = load_bundle(args.data_dir)
    return _analyze_and_write(bundle, args, {"synthetic": bool(bundle.meta.get("synthetic"))})


def cmd_run(args) -> int:
    rc = cmd_fetch(args)
    if rc:
        return rc
    return cmd_backtest(args)


def cmd_demo(args) -> int:
    from .pipeline import collect, save_bundle
    from .synth import DemoKalshiClient, demo_fetch, generate

    root = Path(args.data_dir) / "raw"
    leagues = leagues_from_keys(args.leagues.split(","))
    generate(root, seed=args.seed, leagues=[lg.key for lg in leagues])
    fetch = demo_fetch(root)
    bundle = collect(leagues, date(2026, 7, 20), date(2026, 9, 6), DemoKalshiClient(root), cache_dir=None,
                     espn_fetch=fetch, fd_fetch=fetch, warmup_days=150)
    bundle.meta["synthetic"] = True
    save_bundle(bundle, args.data_dir)
    print(f"Synthetic data: {len(bundle.matches)} fixtures, {len(bundle.warmup)} warm-up results, {len(bundle.snapshots)} snapshots")
    return _analyze_and_write(bundle, args, {"synthetic": True})


def _utf8_stdio() -> None:
    """Windows consoles/redirects default to the legacy code page; the report uses a few Unicode glyphs."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return {"series": cmd_series, "fetch": cmd_fetch, "backtest": cmd_backtest, "run": cmd_run, "demo": cmd_demo}[args.cmd](args)


def main(argv: list[str] | None = None) -> int:
    """Entry point. With no arguments (a double-clicked .exe, or a bare `rsa`) show the menu."""
    from .interactive import is_frozen, pause_if_interactive, run_menu

    _utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return run_menu(run)
    try:
        return run(argv)
    except Exception as e:  # noqa: BLE001
        if not is_frozen():
            raise
        print(f"\nERROR: {e}", file=sys.stderr)
        pause_if_interactive()
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
