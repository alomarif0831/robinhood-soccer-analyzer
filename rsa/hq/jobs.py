"""The four things the HQ can do, each as a job function: fetch, backtest, picks, demo."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from ..config import leagues_from_keys
from ..fees import get_fee_model
from ..pro import StakingRules
from .state import Job, Settings, app_dir

log = logging.getLogger(__name__)


def paths(settings: Settings, demo: bool = False) -> dict[str, Path]:
    root = app_dir()
    name = "demo" if demo else "live"
    return {"data": root / "data" / name, "reports": root / "reports" / name, "cache": root / "data" / name / "cache"}


def rules_from(settings: Settings) -> StakingRules:
    v = settings.values
    return StakingRules(bankroll=float(v["bankroll"]), kelly_fraction=float(v["kelly"]), max_bet_fraction=float(v["max_bet"]),
                        max_day_fraction=float(v["max_day"]), max_bets_per_day=int(v["max_bets_per_day"]),
                        min_confidence=float(v["min_confidence"]), min_edge=float(v["min_edge"]))


def _client(settings: Settings, cache: Path, refresh: bool):
    from ..kalshi import KalshiClient

    v = settings.values
    return KalshiClient(cache_dir=cache, refresh=refresh, key_id=v.get("kalshi_key_id") or None,
                        private_key_path=v.get("kalshi_private_key") or None)


def job_fetch(settings: Settings, refresh: bool = False):
    def run(job: Job) -> dict:
        from ..pipeline import collect, save_bundle

        p = paths(settings)
        v = settings.values
        leagues = leagues_from_keys(v["leagues"])
        log.info("Fetching %s from %s to %s", ", ".join(v["leagues"]), settings.start_date, settings.end_date)
        bundle = collect(leagues, settings.start_date, settings.end_date, _client(settings, p["cache"], refresh),
                         cache_dir=p["cache"], refresh=refresh, warmup_days=int(v["warmup_days"]),
                         minutes_before_kickoff=int(v["minutes_before"]))
        save_bundle(bundle, p["data"])
        log.info("Saved %d fixtures, %d warm-up results, %d price snapshots", len(bundle.matches), len(bundle.warmup), len(bundle.snapshots))
        return {"fixtures": len(bundle.matches), "warmup": len(bundle.warmup), "snapshots": len(bundle.snapshots),
                "leagues": bundle.meta.get("leagues", {})}

    return run


def job_backtest(settings: Settings, demo: bool = False):
    def run(job: Job) -> dict:
        from ..pipeline import analyze, load_bundle, write_outputs

        p = paths(settings, demo)
        v = settings.values
        bundle = load_bundle(p["data"])
        log.info("Backtesting %d fixtures with %d snapshots (fees=%s)", len(bundle.matches), len(bundle.snapshots), v["fees"])
        result, df, unmatched = analyze(bundle, get_fee_model(v["fees"]), min_edge=float(v["min_edge"]), fill=v["fill"],
                                        rules=rules_from(settings))
        meta = dict(bundle.meta, fee_model=v["fees"], min_edge=float(v["min_edge"]), fill=v["fill"], slippage=0.0,
                    synthetic=bool(bundle.meta.get("synthetic")))
        path = write_outputs(result, df, unmatched, bundle, p["reports"], meta)
        log.info("Report written to %s", path)
        if result is None:
            return {"matches": 0, "report": str(path)}
        from ..report import verdicts

        for line in verdicts(result):
            log.info("verdict: %s", line)
        return {"matches": result.n_matches, "report": str(path), "pro_bets": result.pro.get("summary", {}).get("n", 0)}

    return run


def job_picks(settings: Settings, demo: bool = False):
    def run(job: Job) -> dict:
        from ..pipeline import collect_upcoming, load_bundle, run_picks, write_picks

        p = paths(settings, demo)
        v = settings.values
        leagues = leagues_from_keys(v["leagues"])
        try:
            bundle = load_bundle(p["data"])
        except FileNotFoundError:
            log.warning("No fetched history yet; pools use prior weights. Run Fetch first for fitted weights.")
            bundle = None
        if demo:
            from ..synth import DemoKalshiClient, demo_fetch

            raw = p["data"] / "raw"
            fetch = demo_fetch(raw)
            now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
            up = collect_upcoming(leagues, DemoKalshiClient(raw), days=10, today=date(2026, 9, 7), espn_fetch=fetch, fd_fetch=fetch, now=now)
        else:
            now = None
            up = collect_upcoming(leagues, _client(settings, p["cache"], True), days=int(v["days_ahead"]), cache_dir=p["cache"], refresh=True)
        log.info("%d upcoming fixtures, %d open contracts", len(up.matches), len(up.snapshots))
        res = run_picks(bundle, up, get_fee_model(v["fees"]), rules_from(settings), v["fill"], now=now)
        path = write_picks(res, up, p["reports"], {"synthetic": demo, "fee_model": v["fees"], "fill": v["fill"], "rules": rules_from(settings)})
        n = 0 if res["portfolio"] is None else len(res["portfolio"])
        log.info("%d pick(s) written to %s", n, path)
        return {"fixtures": len(up.matches), "contracts": len(up.snapshots), "picks": n, "report": str(path)}

    return run


def job_demo(settings: Settings):
    def run(job: Job) -> dict:
        from ..pipeline import collect, save_bundle
        from ..synth import DemoKalshiClient, demo_fetch, generate

        p = paths(settings, demo=True)
        raw = p["data"] / "raw"
        leagues = leagues_from_keys(settings.values["leagues"])
        log.info("Generating synthetic data for %s", ", ".join(lg.key for lg in leagues))
        generate(raw, seed=42, leagues=[lg.key for lg in leagues])
        fetch = demo_fetch(raw)
        bundle = collect(leagues, date(2026, 7, 20), date(2026, 9, 6), DemoKalshiClient(raw), cache_dir=None,
                         espn_fetch=fetch, fd_fetch=fetch, warmup_days=150, minutes_before_kickoff=360)
        bundle.meta["synthetic"] = True
        save_bundle(bundle, p["data"])
        out = job_backtest(settings, demo=True)(job)
        out.update({f"picks_{k}": v for k, v in job_picks(settings, demo=True)(job).items()})
        return out

    return run
