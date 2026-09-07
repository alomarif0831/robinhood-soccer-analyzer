"""Join venue price snapshots to real matches and lay them out one row per match."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

from .prices import PriceSnapshot
from .results import CLOSING_BOOK_PREFERENCE, DEFAULT_BOOK_PREFERENCE, PREMATCH_BOOK_PREFERENCE, Match, bookmaker_probs
from .teams import canonical, match_team

log = logging.getLogger(__name__)

OUTCOMES = ("home", "draw", "away")


@dataclass
class MatchedMarket:
    match: Match
    venue: str
    event_id: str
    snapshot_time: datetime | None
    price: dict[str, float | None] = field(default_factory=dict)
    bid: dict[str, float | None] = field(default_factory=dict)
    ask: dict[str, float | None] = field(default_factory=dict)
    volume: dict[str, float | None] = field(default_factory=dict)
    market_result: dict[str, str | None] = field(default_factory=dict)
    tickers: dict[str, str] = field(default_factory=dict)
    close_price: dict[str, float | None] = field(default_factory=dict)
    close_bid: dict[str, float | None] = field(default_factory=dict)
    close_ask: dict[str, float | None] = field(default_factory=dict)
    open_price: dict[str, float | None] = field(default_factory=dict)
    last_trade_time: dict[str, datetime | None] = field(default_factory=dict)

    @property
    def minutes_before_kickoff(self) -> float | None:
        if self.snapshot_time is None or self.match.kickoff is None:
            return None
        return (self.match.kickoff - self.snapshot_time).total_seconds() / 60

    def to_row(self) -> dict:
        row = self.match.to_row()
        row.update({"venue": self.venue, "event_id": self.event_id,
                    "snapshot_time": self.snapshot_time.isoformat() if self.snapshot_time else None})
        for o in OUTCOMES:
            row[f"mkt_{o}"] = self.price.get(o)
            row[f"bid_{o}"] = self.bid.get(o)
            row[f"ask_{o}"] = self.ask.get(o)
            row[f"vol_{o}"] = self.volume.get(o)
            row[f"mres_{o}"] = self.market_result.get(o)
            row[f"ticker_{o}"] = self.tickers.get(o)
            row[f"close_{o}"] = self.close_price.get(o)
            row[f"cbid_{o}"] = self.close_bid.get(o)
            row[f"cask_{o}"] = self.close_ask.get(o)
            row[f"open_{o}"] = self.open_price.get(o)
            ltt = self.last_trade_time.get(o)
            row[f"ltt_{o}"] = ltt.isoformat() if ltt else None
        # decision-time line: the closing line is only admissible when the snapshot is at kickoff
        mins = self.minutes_before_kickoff
        prefer = DEFAULT_BOOK_PREFERENCE if (mins is None or mins <= 15) else PREMATCH_BOOK_PREFERENCE
        row["minutes_before"] = mins
        bp = bookmaker_probs(self.match.odds, prefer)
        if bp:
            (row["book_home"], row["book_draw"], row["book_away"]), row["book_source"] = bp
        else:
            row["book_home"] = row["book_draw"] = row["book_away"] = None
            row["book_source"] = None
        bc = bookmaker_probs(self.match.odds, CLOSING_BOOK_PREFERENCE)
        if bc:
            (row["bookc_home"], row["bookc_draw"], row["bookc_away"]), row["bookc_source"] = bc
        else:
            row["bookc_home"] = row["bookc_draw"] = row["bookc_away"] = None
            row["bookc_source"] = None
        return row


def _event_time(snaps: list[PriceSnapshot]) -> datetime | None:
    for s in snaps:
        if s.kickoff:
            return s.kickoff
    for s in snaps:
        if s.snapshot_time:
            return s.snapshot_time
    return None


def join_snapshots(snaps: list[PriceSnapshot], matches: list[Match], max_days: float = 2.0
                   ) -> tuple[list[MatchedMarket], list[dict]]:
    """Match each priced event to a real fixture by league, team names and date.

    Team names are matched with :func:`rsa.teams.match_team` (aliases + fuzzy),
    and home/away orientation is taken from the results source, so it does not
    matter which team the venue lists first. Returns (matched, unmatched_events).
    """
    by_league: dict[str, list[Match]] = {}
    for m in matches:
        by_league.setdefault(m.league, []).append(m)

    events: dict[tuple[str, str], list[PriceSnapshot]] = {}
    for s in snaps:
        events.setdefault((s.league, s.event_id), []).append(s)

    matched: list[MatchedMarket] = []
    unmatched: list[dict] = []
    used: set[str] = set()
    for (league, event_id), ss in events.items():
        t0 = _event_time(ss)
        cands = by_league.get(league, [])
        if t0 is not None:
            cands = [m for m in cands if m.kickoff is None or abs((m.kickoff - t0).total_seconds()) <= max_days * 86400]
        team_a, team_b = ss[0].team_a, ss[0].team_b
        best: tuple[float, Match, bool] | None = None
        for m in cands:
            names = [m.home, m.away]
            ra = match_team(team_a, names)
            rb = match_team(team_b, names)
            if not ra or not rb or ra == rb:
                continue
            a_is_home = ra == m.home
            dist = abs((m.kickoff - t0).total_seconds()) if (m.kickoff and t0) else 0.0
            key = dist + (1e9 if m.match_id in used else 0)
            if best is None or key < best[0]:
                best = (key, m, a_is_home)
        if best is None:
            unmatched.append({"league": league, "event_id": event_id, "team_a": team_a, "team_b": team_b,
                              "time": t0.isoformat() if t0 else None})
            continue
        _, m, a_is_home = best
        used.add(m.match_id)
        mm = MatchedMarket(match=m, venue=ss[0].venue, event_id=event_id, snapshot_time=ss[0].snapshot_time)
        for s in ss:
            if s.is_tie:
                o = "draw"
            else:
                lab = canonical(s.outcome_label)
                if lab == canonical(team_a):
                    o = "home" if a_is_home else "away"
                elif lab == canonical(team_b):
                    o = "away" if a_is_home else "home"
                else:
                    r = match_team(s.outcome_label, [m.home, m.away])
                    o = "home" if r == m.home else "away" if r == m.away else None
            if o is None:
                log.warning("Could not map outcome %r in event %s", s.outcome_label, event_id)
                continue
            mm.price[o] = s.price
            mm.bid[o] = s.yes_bid
            mm.ask[o] = s.yes_ask
            mm.volume[o] = s.volume
            mm.market_result[o] = s.result
            mm.tickers[o] = s.market_ticker
            mm.close_price[o] = s.close_price
            mm.close_bid[o] = s.close_bid
            mm.close_ask[o] = s.close_ask
            mm.open_price[o] = s.open_price
            mm.last_trade_time[o] = s.last_trade_time
        matched.append(mm)
    return matched, unmatched


def matched_frame(matched: list[MatchedMarket]) -> pd.DataFrame:
    df = pd.DataFrame([mm.to_row() for mm in matched])
    if df.empty:
        return df
    df["kickoff"] = pd.to_datetime(df["kickoff"], utc=True)
    df["snapshot_time"] = pd.to_datetime(df["snapshot_time"], utc=True, errors="coerce")
    for o in OUTCOMES:
        for pre in ("mkt", "bid", "ask", "vol", "book", "bookc", "close", "cbid", "cask", "open"):
            col = f"{pre}_{o}"
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df[f"ltt_{o}"] = pd.to_datetime(df[f"ltt_{o}"], utc=True, errors="coerce")
    return df.sort_values(["kickoff", "league"]).reset_index(drop=True)


def check_settlement_consistency(df: pd.DataFrame) -> pd.DataFrame:
    """Rows where the venue's settled result disagrees with the scoreline (data-quality check)."""
    bad = []
    for _, r in df.iterrows():
        res = r.get("result")
        if not res:
            continue
        for o in OUTCOMES:
            mr = r.get(f"mres_{o}")
            if mr in ("yes", "no") and ((mr == "yes") != (o == res)):
                bad.append({"match_id": r["match_id"], "home": r["home"], "away": r["away"],
                            "result": res, "outcome": o, "venue_result": mr})
    return pd.DataFrame(bad)
