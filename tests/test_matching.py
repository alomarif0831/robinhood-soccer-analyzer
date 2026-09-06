from datetime import datetime, timedelta, timezone

from rsa.matching import check_settlement_consistency, join_snapshots, matched_frame
from rsa.prices import PriceSnapshot
from rsa.results import Match

KICK = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)


def _snap(event, a, b, label, price, result, league="epl", kickoff=KICK):
    return PriceSnapshot("kalshi", league, event, a, b, label, f"{event}-{label[:3].upper()}", price, price - 0.01, price + 0.01,
                         kickoff, kickoff, 100.0, result)


def test_join_infers_orientation_from_results_source():
    # venue lists the away team first ("Man United at Wolves" style)
    snaps = [_snap("E1", "Manchester United", "Wolves", "Manchester United", 0.40, "no"),
             _snap("E1", "Manchester United", "Wolves", "TIE", 0.27, "no"),
             _snap("E1", "Manchester United", "Wolves", "Wolves", 0.36, "yes")]
    match = Match("epl", "m1", KICK + timedelta(minutes=5), "Wolverhampton Wanderers", "Man Utd", 2, 1, True, "espn",
                  {"psc_home": 2.8, "psc_draw": 3.4, "psc_away": 2.6})
    matched, unmatched = join_snapshots(snaps, [match])
    assert not unmatched and len(matched) == 1
    mm = matched[0]
    assert mm.price == {"home": 0.36, "draw": 0.27, "away": 0.40}
    assert mm.market_result == {"home": "yes", "draw": "no", "away": "no"}
    df = matched_frame(matched)
    assert df.loc[0, "result"] == "home" and abs(df.loc[0, "book_home"] + df.loc[0, "book_draw"] + df.loc[0, "book_away"] - 1) < 1e-9
    assert check_settlement_consistency(df).empty


def test_join_respects_league_and_date_window():
    snaps = [_snap("E2", "Arsenal", "Chelsea", "Arsenal", 0.5, "yes"), _snap("E2", "Arsenal", "Chelsea", "TIE", 0.25, "no"),
             _snap("E2", "Arsenal", "Chelsea", "Chelsea", 0.3, "no")]
    far = Match("epl", "m-far", KICK + timedelta(days=10), "Arsenal", "Chelsea", 1, 0, True, "espn")
    other_league = Match("laliga", "m-other", KICK, "Arsenal", "Chelsea", 1, 0, True, "espn")
    matched, unmatched = join_snapshots(snaps, [far, other_league])
    assert not matched and len(unmatched) == 1 and unmatched[0]["event_id"] == "E2"


def test_settlement_consistency_flags_disagreement():
    snaps = [_snap("E3", "Arsenal", "Chelsea", "Arsenal", 0.5, "no"), _snap("E3", "Arsenal", "Chelsea", "TIE", 0.25, "yes"),
             _snap("E3", "Arsenal", "Chelsea", "Chelsea", 0.3, "no")]
    match = Match("epl", "m3", KICK, "Arsenal", "Chelsea", 1, 0, True, "espn")
    matched, _ = join_snapshots(snaps, [match])
    bad = check_settlement_consistency(matched_frame(matched))
    assert len(bad) == 2  # home says no but home won; draw says yes but it wasn't a draw
