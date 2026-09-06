import pytest

from rsa.teams import canonical, match_team, normalize, parse_matchup


@pytest.mark.parametrize("name,slug", [
    ("Manchester United", "man_united"), ("Man Utd", "man_united"), ("Nott'm Forest", "nottm_forest"),
    ("Nottingham Forest", "nottm_forest"), ("Wolverhampton Wanderers", "wolves"), ("Spurs", "tottenham"),
    ("Atlético de Madrid", "atletico_madrid"), ("Ath Madrid", "atletico_madrid"), ("FC Bayern München", "bayern_munich"),
    ("Borussia Mönchengladbach", "mgladbach"), ("M'gladbach", "mgladbach"), ("Paris Saint-Germain", "psg"),
    ("Paris SG", "psg"), ("Internazionale", "inter"), ("AC Milan", "milan"), ("Inter Miami CF", "inter_miami"),
    ("Los Angeles FC", "lafc"), ("St. Louis City SC", "st_louis_city"), ("1. FC Köln", "koln"),
    ("Brighton & Hove Albion", "brighton"), ("Real Sociedad", "real_sociedad"), ("Real Madrid", "real_madrid"),
])
def test_canonical_aliases(name, slug):
    assert canonical(name) == slug


def test_unknown_team_falls_back_to_normalized_slug():
    assert canonical("FC Nowhere Town") == "nowhere_town"
    assert normalize("Nowhere Town FC") == "nowhere town"


def test_match_team_picks_right_candidate():
    cands = ["Man United", "Wolves", "Nott'm Forest", "Tottenham", "Brighton"]
    assert match_team("Manchester United", cands) == "Man United"
    assert match_team("Wolverhampton Wanderers", cands) == "Wolves"
    assert match_team("Brighton and Hove Albion", cands) == "Brighton"
    assert match_team("Arsenal", cands) is None


def test_parse_matchup_orientation():
    assert parse_matchup("Arsenal vs Wolves") == ("Arsenal", "Wolves", False)
    assert parse_matchup("Liverpool at PSG: Spreads") == ("PSG", "Liverpool", True)
    assert parse_matchup("Inter Miami @ LA Galaxy") == ("LA Galaxy", "Inter Miami", True)
    assert parse_matchup("nonsense title") is None
