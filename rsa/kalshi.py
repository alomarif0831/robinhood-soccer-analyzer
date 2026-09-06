"""Kalshi public market-data client and pre-kickoff price snapshots.

Robinhood's Kalshi-routed soccer contracts are the same order books as on
Kalshi itself, so Kalshi's public REST API is the price history for them.

Endpoints used (all GET, no auth needed for market data; optional RSA auth is
supported for higher rate limits):

* ``/series?category=Sports``                 discover soccer series
* ``/markets?series_ticker=&status=settled``  recent settled markets
* ``/historical/cutoff`` + ``/historical/markets``   markets settled before the cutoff
* ``/markets/trades?ticker=`` and ``/historical/trades?ticker=``   trade tape
* ``/series/{series}/markets/{ticker}/candlesticks``   hourly bid/ask/price bars

Prices come back either as cents integers (``yes_bid: 55``) or dollar strings
(``yes_bid_dollars: "0.55"``) depending on API version; both are handled.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

import requests

from .config import KALSHI_BASE_URL
from .prices import PriceSnapshot, parse_price, parse_time

log = logging.getLogger(__name__)

SOCCER_KEYWORDS = (
    "soccer", "premier league", "epl", "la liga", "laliga", "bundesliga", "serie a", "ligue 1",
    "mls", "champions league", "europa", "conference league", "world cup", "fifa", "uefa",
    "liga mx", "leagues cup", "copa", "eredivisie", "primeira",
)


class KalshiError(RuntimeError):
    pass


class KalshiClient:
    """Thin, cached, rate-limited wrapper over Kalshi's REST API."""

    def __init__(
        self,
        base_url: str = KALSHI_BASE_URL,
        cache_dir: str | Path | None = None,
        refresh: bool = False,
        requests_per_second: float = 8.0,
        timeout: float = 30.0,
        key_id: str | None = None,
        private_key_path: str | None = None,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.refresh = refresh
        self.min_interval = 1.0 / requests_per_second if requests_per_second else 0.0
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "robinhood-soccer-analyzer/0.1")
        self._last_call = 0.0
        self._private_key = None
        self.key_id = key_id
        if key_id and private_key_path:
            self._private_key = _load_private_key(private_key_path)
        self._cutoff: dict | None = None

    # ------------------------------------------------------------------ HTTP
    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        if not (self.key_id and self._private_key):
            return {}
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        ts = str(int(time.time() * 1000))
        full_path = "/trade-api/v2" + path if not path.startswith("/trade-api") else path
        msg = (ts + method.upper() + full_path.split("?")[0]).encode()
        sig = self._private_key.sign(
            msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        }

    def _cache_path(self, path: str, params: dict | None) -> Path | None:
        if not self.cache_dir:
            return None
        key = json.dumps([path, sorted((params or {}).items())], sort_keys=True)
        h = hashlib.sha1(key.encode()).hexdigest()[:20]
        safe = re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")
        return self.cache_dir / f"{safe}_{h}.json"

    def get(self, path: str, params: dict | None = None, *, cacheable: bool = True) -> dict:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        cp = self._cache_path(path, params) if cacheable else None
        if cp and cp.exists() and not self.refresh:
            with open(cp) as f:
                return json.load(f)

        url = self.base_url + path
        backoff = 1.0
        for attempt in range(6):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            resp = self.session.get(url, params=params, headers=self._auth_headers("GET", path), timeout=self.timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("Kalshi %s -> %s, retrying in %.1fs", path, resp.status_code, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            if resp.status_code >= 400:
                raise KalshiError(f"GET {path} params={params} -> {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if cp:
                cp.parent.mkdir(parents=True, exist_ok=True)
                with open(cp, "w") as f:
                    json.dump(data, f)
            return data
        raise KalshiError(f"GET {path}: gave up after retries")

    def paged(self, path: str, params: dict | None, key: str, max_pages: int = 500) -> Iterator[dict]:
        params = dict(params or {})
        params.setdefault("limit", 1000)
        for _ in range(max_pages):
            data = self.get(path, params)
            for item in data.get(key, []) or []:
                yield item
            cursor = data.get("cursor")
            if not cursor:
                return
            params["cursor"] = cursor

    # ---------------------------------------------------------------- series
    def list_series(self, category: str | None = "Sports") -> list[dict]:
        data = self.get("/series", {"category": category, "limit": 1000})
        return data.get("series", []) or []

    def soccer_series(self) -> list[dict]:
        out = []
        for s in self.list_series("Sports"):
            blob = " ".join(str(s.get(k, "")) for k in ("ticker", "title", "tags", "frequency")).lower()
            if any(k in blob for k in SOCCER_KEYWORDS):
                out.append(s)
        return sorted(out, key=lambda s: s.get("ticker", ""))

    # --------------------------------------------------------------- markets
    def historical_cutoff(self) -> dict:
        if self._cutoff is None:
            try:
                self._cutoff = self.get("/historical/cutoff", cacheable=False)
            except KalshiError as e:
                log.info("No historical cutoff endpoint (%s); using live endpoints only", e)
                self._cutoff = {}
        return self._cutoff

    def list_markets(self, series_ticker: str, status: str | None = None,
                     min_close_ts: int | None = None, max_close_ts: int | None = None) -> list[dict]:
        params = {"series_ticker": series_ticker, "status": status,
                  "min_close_ts": min_close_ts, "max_close_ts": max_close_ts}
        return list(self.paged("/markets", params, "markets"))

    def list_historical_markets(self, series_ticker: str) -> list[dict]:
        """Markets archived past the historical cutoff. Filters on this endpoint are
        mutually exclusive, so only ``series_ticker`` is sent; callers filter by time."""
        try:
            return list(self.paged("/historical/markets", {"series_ticker": series_ticker}, "markets"))
        except KalshiError as e:
            log.warning("historical/markets unavailable for %s: %s", series_ticker, e)
            return []

    def settled_markets_since(self, series_ticker: str, since_ts: int) -> list[dict]:
        """All settled markets in a series whose close time is >= ``since_ts``.

        Merges the live ``/markets`` listing with ``/historical/markets`` (where
        Kalshi parks markets settled before its rolling cutoff) and de-duplicates.
        """
        found: dict[str, dict] = {}
        for m in self.list_markets(series_ticker, status="settled", min_close_ts=since_ts):
            found[m["ticker"]] = m
        cutoff = self.historical_cutoff()
        if cutoff:
            for m in self.list_historical_markets(series_ticker):
                found.setdefault(m["ticker"], m)
        out = []
        for m in found.values():
            t = market_close_time(m)
            if t is None or t.timestamp() >= since_ts:
                out.append(m)
        return sorted(out, key=lambda m: (market_close_time(m) or datetime.max.replace(tzinfo=timezone.utc), m["ticker"]))

    # ---------------------------------------------------------------- prices
    def trades(self, ticker: str, min_ts: int | None = None, max_ts: int | None = None) -> list[dict]:
        params = {"ticker": ticker, "min_ts": min_ts, "max_ts": max_ts}
        trades = list(self.paged("/markets/trades", params, "trades"))
        cutoff = self.historical_cutoff()
        cutoff_ts = _as_ts(cutoff.get("trades_created_ts")) if cutoff else None
        if cutoff_ts and (min_ts is None or min_ts < cutoff_ts):
            try:
                hist = list(self.paged("/historical/trades", params, "trades"))
            except KalshiError as e:
                log.info("historical/trades unavailable for %s: %s", ticker, e)
                hist = []
            seen = {t.get("trade_id") for t in trades}
            trades.extend(t for t in hist if t.get("trade_id") not in seen)
        trades.sort(key=lambda t: parse_time(t.get("created_time")) or datetime.min.replace(tzinfo=timezone.utc))
        return trades

    def candlesticks(self, series_ticker: str, ticker: str, start_ts: int, end_ts: int,
                     period_interval: int = 60) -> list[dict]:
        params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval}
        paths = [
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            # archived markets: Kalshi serves candles from the historical tier
            f"/historical/series/{series_ticker}/markets/{ticker}/candlesticks",
            f"/historical/markets/{ticker}/candlesticks",
        ]
        for path in paths:
            try:
                data = self.get(path, params)
            except KalshiError as e:
                log.info("candlesticks %s unavailable (%s)", path, e)
                continue
            candles = data.get("candlesticks", []) or []
            if candles:
                return candles
        return []


# ---------------------------------------------------------------- parsing helpers
def _as_ts(v) -> int | None:
    dt = parse_time(v)
    return int(dt.timestamp()) if dt else None


def market_close_time(m: dict) -> datetime | None:
    for k in ("close_time", "expected_expiration_time", "expiration_time", "latest_expiration_time"):
        dt = parse_time(m.get(k))
        if dt:
            return dt
    return None


def market_settled_time(m: dict) -> datetime | None:
    for k in ("settlement_ts", "settled_time", "settlement_time"):
        dt = parse_time(m.get(k))
        if dt:
            return dt
    return None


def market_price(m: dict, field: str) -> float | None:
    """Read ``field`` ("yes_bid", "yes_ask", "last_price"...) in dollars from either encoding."""
    if m.get(f"{field}_dollars") not in (None, ""):
        return parse_price(m[f"{field}_dollars"])
    return parse_price(m.get(field))


def trade_yes_price(t: dict) -> float | None:
    return market_price(t, "yes_price")


def market_result(m: dict) -> str | None:
    r = (m.get("result") or "").lower()
    return r if r in ("yes", "no") else None


def outcome_label(m: dict) -> str:
    """Team name (or TIE) that a market's YES side refers to."""
    suffix = m.get("ticker", "").rsplit("-", 1)[-1].upper()
    if suffix in ("TIE", "DRAW"):
        return "TIE"
    for k in ("yes_sub_title", "subtitle"):
        v = (m.get(k) or "").strip()
        if v and v.lower() not in ("yes", "no"):
            if v.lower() in ("tie", "draw"):
                return "TIE"
            return v
    return suffix


def event_teams(markets: list[dict]) -> tuple[str, str] | None:
    """The two team names in an event from its non-TIE markets' labels."""
    names = []
    for m in markets:
        lab = outcome_label(m)
        if lab != "TIE" and lab not in names:
            names.append(lab)
    if len(names) >= 2:
        return names[0], names[1]
    # fall back to parsing the title "Arsenal vs Wolves Winner?"
    from .teams import parse_matchup

    for m in markets:
        title = re.sub(r"[?]+$", "", (m.get("title") or "").strip())
        parsed = parse_matchup(title)
        if parsed:
            a, b = (re.sub(r"\s+(match\s+)?(winner|result|moneyline|game|outcome)\s*$", "", x, flags=re.IGNORECASE).strip()
                    for x in parsed[:2])
            if a and b:
                return a, b
    return None


def group_by_event(markets: Iterable[dict]) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    for m in markets:
        ev = m.get("event_ticker") or m["ticker"].rsplit("-", 1)[0]
        events.setdefault(ev, []).append(m)
    return events


# ------------------------------------------------------------------ snapshots
def snapshot_from_trades(trades: list[dict], at: datetime, window_minutes: int = 180) -> dict:
    """Pre-``at`` price summary from a trade tape: last trade, VWAP over a window, volume."""
    last = None
    last_t = None
    vol = 0.0
    wsum = 0.0
    wvol = 0.0
    for t in trades:
        ts = parse_time(t.get("created_time"))
        p = trade_yes_price(t)
        if ts is None or p is None or ts > at:
            continue
        n = float(t.get("count_fp") or t.get("count") or 1)
        last, last_t = p, ts
        vol += n
        if (at - ts).total_seconds() <= window_minutes * 60:
            wsum += p * n
            wvol += n
    return {"last": last, "last_time": last_t, "vwap": (wsum / wvol) if wvol else None, "volume": vol}


def snapshot_from_candles(candles: list[dict], at: datetime) -> dict:
    """Bid/ask/price close of the last candle ending at or before ``at``."""
    best = None
    for c in candles:
        end = parse_time(c.get("end_period_ts"))
        if end is None or end > at:
            continue
        if best is None or end > best[0]:
            best = (end, c)
    if not best:
        return {}
    c = best[1]

    def close_of(key):
        sub = c.get(key) or {}
        v = sub.get("close_dollars", sub.get("close"))
        return parse_price(v)

    return {"yes_bid": close_of("yes_bid"), "yes_ask": close_of("yes_ask"), "price": close_of("price"),
            "candle_end": best[0], "open_interest": c.get("open_interest")}


def build_snapshots(
    client: KalshiClient,
    league_key: str,
    series_ticker: str,
    markets: list[dict],
    kickoff_lookup=None,
    minutes_before_kickoff: int = 0,
    use_candles: bool = True,
) -> list[PriceSnapshot]:
    """Turn settled Kalshi markets into pre-kickoff :class:`PriceSnapshot` rows.

    ``kickoff_lookup(team_a, team_b, close_time) -> datetime | None`` supplies the
    true kickoff from the results source; without it the snapshot is taken at
    the market's close time minus ~2h (Kalshi keeps game markets open in-play,
    so close time is not kickoff). Snapshots use the last trade at or before
    ``kickoff - minutes_before_kickoff``.
    """
    snaps: list[PriceSnapshot] = []
    for event_ticker, ms in group_by_event(markets).items():
        teams = event_teams(ms)
        if not teams:
            log.warning("Could not identify teams for event %s", event_ticker)
            continue
        team_a, team_b = teams
        close = market_close_time(ms[0])
        kickoff = kickoff_lookup(team_a, team_b, close) if kickoff_lookup else None
        if kickoff is None and close is not None:
            kickoff = close - timedelta(minutes=120)
        for m in ms:
            if kickoff is None:
                continue
            at = kickoff - timedelta(minutes=minutes_before_kickoff)
            open_ts = _as_ts(m.get("open_time")) or int(at.timestamp()) - 14 * 86400
            trades = client.trades(m["ticker"], min_ts=open_ts, max_ts=int(at.timestamp()) + 1)
            ts = snapshot_from_trades(trades, at)
            cs = {}
            if use_candles:
                candles = client.candlesticks(series_ticker, m["ticker"], open_ts, int(at.timestamp()) + 3600)
                cs = snapshot_from_candles(candles, at)
            price = ts["last"] if ts["last"] is not None else cs.get("price")
            snaps.append(
                PriceSnapshot(
                    venue="kalshi",
                    league=league_key,
                    event_id=event_ticker,
                    team_a=team_a,
                    team_b=team_b,
                    outcome_label=outcome_label(m),
                    market_ticker=m["ticker"],
                    price=price,
                    yes_bid=cs.get("yes_bid"),
                    yes_ask=cs.get("yes_ask"),
                    snapshot_time=at,
                    kickoff=kickoff,
                    volume=ts["volume"],
                    result=market_result(m),
                    extra={"vwap_3h": ts["vwap"], "last_trade_time": ts["last_time"].isoformat() if ts["last_time"] else None,
                           "market_volume": m.get("volume"), "close_time": close.isoformat() if close else None},
                )
            )
    return snaps


def _load_private_key(path: str):
    from cryptography.hazmat.primitives import serialization

    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)
