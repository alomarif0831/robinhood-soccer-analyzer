"""Menu shown when the executable is started without arguments (e.g. double-clicked)."""

from __future__ import annotations

import sys
from datetime import date
from typing import Callable

from .config import DEFAULT_LEAGUES, LEAGUES, WINDOW_START
from .fees import FEE_MODELS

BANNER = """
Robinhood Soccer HQ (text menu; `rsa hq` opens the app window)
================================================================
Backtests Robinhood/Kalshi soccer match-winner contracts against real results
for matches played after the 2026 World Cup, net of fees.

  1) Demo             synthetic data, no internet, ~15 s  -> reports/demo/report.md
  2) Fetch + backtest live data (Kalshi, ESPN, football-data.co.uk)
  3) Backtest data fetched earlier (offline)
  4) List Kalshi soccer series tickers
  5) Picks: rank upcoming contracts by confidence and size stakes
  6) Open the HQ app window
  h) Show all command-line options
  q) Quit
"""


class MenuQuit(Exception):
    """Raised when stdin ends (EOF) in the middle of a prompt: treat it as quit."""


def _read(input_fn: Callable[[str], str], prompt: str) -> str | None:
    try:
        return input_fn(prompt)
    except EOFError:
        return None


def _ask(input_fn: Callable[[str], str], prompt: str, default: str) -> str:
    raw = _read(input_fn, f"{prompt} [{default}]: ")
    if raw is None:
        raise MenuQuit
    return raw.strip() or default


def pause_if_interactive(prompt: str = "Press Enter to close...") -> None:
    """Keep a double-clicked console window open, but never block scripts, CI or hidden consoles."""
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input(prompt)
    except (EOFError, OSError, RuntimeError, ValueError):
        pass


def _choose(input_fn, prompt: str, default: str, options) -> str:
    while True:
        v = _ask(input_fn, f"{prompt} ({'/'.join(options)})", default)
        if v in options:
            return v
        print(f"  choose one of: {', '.join(options)}")


def _analysis_args(input_fn) -> list[str]:
    fees = _choose(input_fn, "Fee model", "robinhood", sorted(FEE_MODELS))
    edge = _ask(input_fn, "Minimum edge to bet (fair - price - fee)", "0.03")
    fill = _choose(input_fn, "Fill at", "ask", ("ask", "last"))
    return ["--fees", fees, "--min-edge", edge, "--fill", fill]


def build_argv(choice: str, input_fn: Callable[[str], str] = input, today: date | None = None) -> list[str] | None:
    """Turn a menu choice into CLI arguments (None = nothing to run)."""
    today = today or date.today()
    if choice == "1":
        return ["demo"]
    if choice == "2":
        leagues = _ask(input_fn, f"Leagues (comma list from {', '.join(LEAGUES)})", ",".join(DEFAULT_LEAGUES))
        start = _ask(input_fn, "First kickoff date", WINDOW_START.isoformat())
        end = _ask(input_fn, "Last kickoff date", today.isoformat())
        data_dir = _ask(input_fn, "Data directory", "data/live")
        return ["run", "--leagues", leagues, "--start", start, "--end", end, "--data-dir", data_dir] + _analysis_args(input_fn)
    if choice == "3":
        data_dir = _ask(input_fn, "Data directory", "data/live")
        return ["backtest", "--data-dir", data_dir] + _analysis_args(input_fn)
    if choice == "4":
        return ["series"]
    if choice == "6":
        return ["hq"]
    if choice == "5":
        leagues = _ask(input_fn, f"Leagues (comma list from {', '.join(LEAGUES)})", ",".join(DEFAULT_LEAGUES))
        days = _ask(input_fn, "Days ahead", "7")
        data_dir = _ask(input_fn, "Data directory with fetched history", "data/live")
        bankroll = _ask(input_fn, "Bankroll in dollars", "1000")
        conf = _ask(input_fn, "Minimum confidence (0-100)", "60")
        return ["picks", "--leagues", leagues, "--days", days, "--data-dir", data_dir, "--bankroll", bankroll, "--min-confidence", conf]
    if choice == "h":
        return ["--help"]
    return None


def run_menu(runner: Callable[[list[str]], int], input_fn: Callable[[str], str] = input, once: bool = False) -> int:
    """Loop the menu until quit; ``runner`` is the CLI entry point."""
    rc = 0
    while True:
        print(BANNER)
        raw = _read(input_fn, "Choice: ")
        if raw is None:
            return rc
        choice = raw.strip().lower()
        if choice == "":
            continue
        if choice in ("q", "quit", "exit"):
            return rc
        try:
            argv = build_argv(choice, input_fn)
        except MenuQuit:
            return rc
        if argv is None:
            print("  unknown choice")
            continue
        print(f"\n> rsa {' '.join(argv)}\n")
        try:
            rc = runner(argv)
        except SystemExit as e:  # argparse --help exits
            rc = int(e.code or 0)
        except KeyboardInterrupt:
            print("\nCancelled.")
            rc = 130
        except Exception as e:  # noqa: BLE001 - keep the window open, show the error
            print(f"\nERROR: {e}")
            rc = 1
        if once:
            return rc
        if _read(input_fn, "\nPress Enter to return to the menu...") is None:
            return rc


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
