import json
from datetime import timezone

import pytest

from rsa.config import LEAGUES
from rsa.results import (Match, american_to_decimal, bookmaker_probs, implied_probs, load_espn, matches_from_frame,
                         matches_to_frame, merge_results, parse_espn_scoreboard, parse_fdcouk_csv)

ESPN = {
    "events": [{
        "id": "1", "date": "2026-08-22T14:00Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": "2", "winner": True, "team": {"displayName": "Wolverhampton Wanderers", "abbreviation": "WOL"}},
                {"homeAway": "away", "score": "1", "winner": False, "team": {"displayName": "Manchester United", "abbreviation": "MAN"}},
            ],
            "status": {"type": {"name": "STATUS_FULL_TIME", "completed": True}},
            "odds": [{"provider": {"name": "x"}, "homeTeamOdds": {"moneyLine": 250}, "awayTeamOdds": {"moneyLine": -110}, "drawOdds": {"moneyLine": 240}}],
        }],
    }, {
        "id": "2", "date": "2026-08-22T16:30Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": "0", "team": {"displayName": "Arsenal"}},
                {"homeAway": "away", "score": "0", "team": {"displayName": "Chelsea"}},
            ],
            "status": {"type": {"name": "STATUS_SCHEDULED", "completed": False}},
        }],
    }],
}

FD_CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A,PSH,PSD,PSA,PSCH,PSCD,PSCA
E0,22/08/2026,15:00,Wolves,Man United,2,1,H,3.4,3.5,2.1,3.55,3.6,2.15,3.6,3.55,2.12
E0,23/08/2026,14:00,Arsenal,Chelsea,,,,1.8,3.8,4.5,1.85,3.9,4.6,,,
"""


def test_parse_espn_scoreboard():
    ms = parse_espn_scoreboard(ESPN, "epl")
    assert len(ms) == 2
    m = ms[0]
    assert (m.home, m.away, m.home_goals, m.away_goals, m.result) == ("Wolverhampton Wanderers", "Manchester United", 2, 1, "home")
    assert m.kickoff.tzinfo is not None and m.kickoff.hour == 14
    assert m.odds["espn_home"] == pytest.approx(3.5)
    assert m.odds["espn_away"] == pytest.approx(1 + 100 / 110)
    assert ms[1].completed is False and ms[1].result is None and ms[1].home_goals is None


def test_parse_fdcouk_csv_converts_london_time_and_odds():
    ms = parse_fdcouk_csv(FD_CSV, "epl", "E0", "2627")
    assert len(ms) == 2
    m = ms[0]
    assert m.kickoff.astimezone(timezone.utc).hour == 14  # 15:00 BST == 14:00 UTC
    assert m.result == "home" and m.odds["psc_home"] == 3.6 and m.odds["b365_draw"] == 3.5
    assert ms[1].completed is False and "psc_home" not in ms[1].odds


def test_implied_probs_removes_margin():
    p = implied_probs(2.0, 3.5, 4.0, method="proportional")
    assert sum(p) == pytest.approx(1.0)
    s = implied_probs(2.0, 3.5, 4.0, method="shin")
    assert sum(s) == pytest.approx(1.0)
    # Shin shrinks longshots more than proportional
    assert s[2] < p[2] and s[0] > p[0]


def test_bookmaker_probs_prefers_pinnacle_closing():
    odds = {"b365_home": 2.0, "b365_draw": 3.5, "b365_away": 4.0, "psc_home": 2.1, "psc_draw": 3.4, "psc_away": 3.9}
    probs, src = bookmaker_probs(odds)
    assert src == "psc" and sum(probs) == pytest.approx(1.0)
    assert bookmaker_probs({"psc_home": 2.0}) is None


def test_merge_results_overlays_odds_by_canonical_names():
    espn = parse_espn_scoreboard(ESPN, "epl")
    fd = parse_fdcouk_csv(FD_CSV, "epl", "E0", "2627")
    merged = merge_results(espn, fd)
    assert merged[0].odds["psc_home"] == 3.6 and merged[0].odds["espn_home"] == pytest.approx(3.5)
    assert merged[1].odds["b365_home"] == 1.8


def test_frame_round_trip():
    ms = parse_espn_scoreboard(ESPN, "epl")
    df = matches_to_frame(ms)
    back = matches_from_frame(df)
    assert back[0].home == "Wolverhampton Wanderers" and back[0].result == "home"
    assert back[0].odds["espn_home"] == pytest.approx(3.5)
    assert back[1].completed is False


def test_load_espn_dedupes_and_uses_fetch(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return json.dumps(ESPN)

    from datetime import date

    ms = load_espn(LEAGUES["epl"], date(2026, 8, 22), date(2026, 8, 23), cache_dir=tmp_path, fetch=fetch)
    assert len(ms) == 2 and len(calls) == 4  # window plus one day either side, deduped by event id
    ms2 = load_espn(LEAGUES["epl"], date(2026, 8, 22), date(2026, 8, 23), cache_dir=tmp_path, fetch=fetch)
    assert len(calls) == 4  # served from cache
    assert len(ms2) == 2
    # fixtures whose UTC kickoff date is outside the window are dropped even if ESPN lists them
    assert load_espn(LEAGUES["epl"], date(2026, 8, 23), date(2026, 8, 23), cache_dir=tmp_path, fetch=fetch) == []


def test_american_to_decimal():
    assert american_to_decimal(100) == 2.0
    assert american_to_decimal(-200) == 1.5
    assert american_to_decimal("x") is None
