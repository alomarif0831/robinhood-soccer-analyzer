"""Venue-agnostic price snapshots and a CSV importer for venues without an API.

Robinhood's contracts clear on Kalshi (public API) or on Rothera (no public
market-data API as of September 2026). For Rothera-routed contracts, export the
prices you saw (or your order history) to a CSV and load it with
:func:`load_prices_csv`; the backtest treats both sources identically.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class PriceSnapshot:
    """One outcome contract of one match, priced at a single point in time.

    Prices are YES prices in dollars (0-1). ``price`` is the best single
    estimate (last trade or mid); ``yes_bid``/``yes_ask`` are optional and let
    the backtest use realistic fills (buy at ask).
    """

    venue: str
    league: str
    event_id: str
    team_a: str
    team_b: str
    outcome_label: str            # team name as titled, or "TIE"
    market_ticker: str
    price: float | None
    yes_bid: float | None = None
    yes_ask: float | None = None
    snapshot_time: datetime | None = None
    kickoff: datetime | None = None
    volume: float | None = None
    result: str | None = None     # "yes" / "no" / None (unsettled/unknown)
    extra: dict = field(default_factory=dict)

    @property
    def is_tie(self) -> bool:
        return self.outcome_label.strip().lower() in {"tie", "draw", "tie/draw", "draw/tie"}

    def to_row(self) -> dict:
        d = asdict(self)
        d.pop("extra", None)
        for k in ("snapshot_time", "kickoff"):
            v = getattr(self, k)
            d[k] = v.isoformat() if v else None
        return d


def parse_price(v) -> float | None:
    """Accept cents ints (55), dollar strings ("0.55"), floats (0.55) or None."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            return None
    v = float(v)
    if v > 1.0:
        v = v / 100.0
    if v < 0 or v > 1:
        return None
    return v


def parse_time(v) -> datetime | None:
    """ISO-8601 string or unix seconds -> aware UTC datetime."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v), tz=timezone.utc)
    s = str(v).strip()
    if s.isdigit():
        return datetime.fromtimestamp(int(s), tz=timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


CSV_COLUMNS = (
    "venue", "league", "event_id", "team_a", "team_b", "outcome_label", "market_ticker",
    "price", "yes_bid", "yes_ask", "snapshot_time", "kickoff", "volume", "result",
)


def load_prices_csv(path: str | Path) -> list[PriceSnapshot]:
    """Load snapshots from a CSV with the columns in :data:`CSV_COLUMNS`.

    Minimal required columns: league, team_a, team_b, outcome_label, price.
    ``outcome_label`` is a team name or "TIE"; ``price`` may be cents or dollars.
    """
    out: list[PriceSnapshot] = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            missing = [c for c in ("league", "team_a", "team_b", "outcome_label", "price") if not row.get(c)]
            if missing:
                raise ValueError(f"{path}: row {i + 2} missing {missing}")
            out.append(
                PriceSnapshot(
                    venue=row.get("venue") or "csv",
                    league=row["league"].strip().lower(),
                    event_id=row.get("event_id") or f"csv-{i}",
                    team_a=row["team_a"].strip(),
                    team_b=row["team_b"].strip(),
                    outcome_label=row["outcome_label"].strip(),
                    market_ticker=row.get("market_ticker") or f"csv-{i}-{row['outcome_label']}",
                    price=parse_price(row["price"]),
                    yes_bid=parse_price(row.get("yes_bid")),
                    yes_ask=parse_price(row.get("yes_ask")),
                    snapshot_time=parse_time(row.get("snapshot_time")),
                    kickoff=parse_time(row.get("kickoff")),
                    volume=float(row["volume"]) if row.get("volume") else None,
                    result=(row.get("result") or None),
                )
            )
    return out


def save_prices_csv(snaps: list[PriceSnapshot], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_COLUMNS))
        w.writeheader()
        for s in snaps:
            w.writerow({k: v for k, v in s.to_row().items() if k in CSV_COLUMNS})
