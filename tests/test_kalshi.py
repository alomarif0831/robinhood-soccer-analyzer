from datetime import datetime, timedelta, timezone

from rsa.kalshi import (KalshiClient, build_snapshots, event_teams, group_by_event, market_close_time, market_price,
                        outcome_label, snapshot_from_candles, snapshot_from_trades)

KICK = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)


def _mk(ticker, sub, result):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0], "title": "Arsenal vs Wolves Winner?",
            "yes_sub_title": sub, "status": "settled", "result": result, "close_time": (KICK + timedelta(hours=2)).isoformat(),
            "open_time": (KICK - timedelta(days=5)).isoformat(), "yes_bid": 55, "yes_ask_dollars": "0.57", "last_price": 56}


MARKETS = [_mk("KXEPLGAME-26AUG22ARSWOL-ARS", "Arsenal", "yes"), _mk("KXEPLGAME-26AUG22ARSWOL-TIE", "Tie", "no"),
           _mk("KXEPLGAME-26AUG22ARSWOL-WOL", "Wolves", "no")]


def test_market_field_parsing():
    m = MARKETS[0]
    assert market_price(m, "yes_bid") == 0.55
    assert market_price(m, "yes_ask") == 0.57   # dollars variant wins
    assert market_price(m, "last_price") == 0.56
    assert market_close_time(m) == KICK + timedelta(hours=2)
    assert outcome_label(MARKETS[1]) == "TIE" and outcome_label(MARKETS[2]) == "Wolves"
    assert event_teams(MARKETS) == ("Arsenal", "Wolves")
    assert list(group_by_event(MARKETS)) == ["KXEPLGAME-26AUG22ARSWOL"]


def test_event_teams_falls_back_to_title():
    ms = [{"ticker": "X-TIE", "yes_sub_title": "Tie", "title": "Real Madrid vs Mallorca Winner?"}]
    assert event_teams(ms) == ("Real Madrid", "Mallorca")


def test_snapshot_from_trades_ignores_in_play_trades():
    trades = [
        {"created_time": (KICK - timedelta(hours=5)).isoformat(), "yes_price": 50, "count": 10},
        {"created_time": (KICK - timedelta(minutes=30)).isoformat(), "yes_price_dollars": "0.60", "count": 5},
        {"created_time": (KICK + timedelta(minutes=30)).isoformat(), "yes_price": 90, "count": 100},
    ]
    s = snapshot_from_trades(trades, KICK)
    assert s["last"] == 0.60 and s["volume"] == 15
    assert s["vwap"] == 0.60  # only the -30min trade is inside the 3h window


def test_snapshot_from_candles_takes_last_pre_kickoff_bar():
    candles = [
        {"end_period_ts": int((KICK - timedelta(hours=2)).timestamp()), "yes_bid": {"close": 50}, "yes_ask": {"close": 53}, "price": {"close": 51}},
        {"end_period_ts": int((KICK - timedelta(hours=1)).timestamp()), "yes_bid": {"close_dollars": "0.54"}, "yes_ask": {"close": 57}, "price": {"close": 55}},
        {"end_period_ts": int((KICK + timedelta(hours=1)).timestamp()), "yes_bid": {"close": 90}, "yes_ask": {"close": 95}, "price": {"close": 92}},
    ]
    s = snapshot_from_candles(candles, KICK)
    assert (s["yes_bid"], s["yes_ask"], s["price"]) == (0.54, 0.57, 0.55)


class FakeClient(KalshiClient):
    def __init__(self):
        super().__init__(requests_per_second=0)
        self.calls = []

    def trades(self, ticker, min_ts=None, max_ts=None):
        self.calls.append(("trades", ticker, min_ts, max_ts))
        p = {"ARS": 56, "TIE": 24, "WOL": 22}[ticker.rsplit("-", 1)[1]]
        return [{"created_time": (KICK - timedelta(minutes=10)).isoformat(), "yes_price": p, "count": 3},
                {"created_time": (KICK + timedelta(minutes=10)).isoformat(), "yes_price": 99, "count": 3}]

    def candlesticks(self, series, ticker, start_ts, end_ts, period_interval=60):
        return []


def test_build_snapshots_uses_kickoff_lookup_and_pre_kickoff_trades():
    client = FakeClient()
    snaps = build_snapshots(client, "epl", "KXEPLGAME", MARKETS, kickoff_lookup=lambda a, b, close: KICK)
    assert len(snaps) == 3
    by = {s.outcome_label: s for s in snaps}
    assert by["Arsenal"].price == 0.56 and by["TIE"].price == 0.24 and by["Wolves"].price == 0.22
    assert by["Arsenal"].result == "yes" and by["TIE"].is_tie
    assert all(s.kickoff == KICK and s.snapshot_time == KICK for s in snaps)
    # trades were requested only up to kickoff
    assert all(c[3] == int(KICK.timestamp()) + 1 for c in client.calls)


def test_build_snapshots_without_lookup_uses_close_minus_two_hours():
    client = FakeClient()
    snaps = build_snapshots(client, "epl", "KXEPLGAME", MARKETS)
    assert snaps[0].kickoff == KICK  # close_time is kickoff + 2h in the fixture
