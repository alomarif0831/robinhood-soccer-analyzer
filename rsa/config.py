"""Static configuration: leagues, venue identifiers, and the analysis window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

# The 2026 FIFA World Cup final was played on 19 July 2026 (MetLife Stadium).
# "After the World Cup" therefore means kickoff on or after 20 July 2026.
WORLD_CUP_FINAL = date(2026, 7, 19)
WINDOW_START = date(2026, 7, 20)

KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
FDCOUK_BASE_URL = "https://www.football-data.co.uk/mmz4281"

# football-data.co.uk season code for 2026/27 and the prior season used to
# warm up Elo ratings before the analysis window.
FDCOUK_SEASON = "2627"
FDCOUK_WARMUP_SEASONS = ("2526",)


@dataclass(frozen=True)
class League:
    key: str
    name: str
    kalshi_series: str          # Kalshi "game" (match winner, 3-way) series ticker
    espn: str                   # ESPN scoreboard league code
    fdcouk: str | None = None   # football-data.co.uk division code (None = not covered)
    series_verified: bool = True  # False = ticker inferred from Kalshi's naming; confirm with `rsa series`


# Kalshi's soccer match-winner series follow the pattern KX<LEAGUE>GAME and each
# event holds three markets: home team, away team and TIE. The five European
# leagues plus MLS/UCL are confirmed public series; the rest follow the same
# naming convention but should be confirmed with `rsa series` before use.
LEAGUES: dict[str, League] = {
    "epl": League("epl", "Premier League", "KXEPLGAME", "eng.1", "E0"),
    "laliga": League("laliga", "La Liga", "KXLALIGAGAME", "esp.1", "SP1"),
    "bundesliga": League("bundesliga", "Bundesliga", "KXBUNDESLIGAGAME", "ger.1", "D1"),
    "seriea": League("seriea", "Serie A", "KXSERIEAGAME", "ita.1", "I1"),
    "ligue1": League("ligue1", "Ligue 1", "KXLIGUE1GAME", "fra.1", "F1"),
    "mls": League("mls", "MLS", "KXMLSGAME", "usa.1", None),
    "ucl": League("ucl", "Champions League", "KXUCLGAME", "uefa.champions", None),
    "uel": League("uel", "Europa League", "KXUELGAME", "uefa.europa", None, series_verified=False),
    "uecl": League("uecl", "Conference League", "KXUECLGAME", "uefa.europa.conf", None, series_verified=False),
    "leaguescup": League("leaguescup", "Leagues Cup", "KXLEAGUESCUPGAME", "concacaf.leagues.cup", None, series_verified=False),
    "ligamx": League("ligamx", "Liga MX", "KXLIGAMXGAME", "mex.1", None, series_verified=False),
}

DEFAULT_LEAGUES = ("epl", "laliga", "bundesliga", "seriea", "ligue1", "mls")

OUTCOMES = ("home", "draw", "away")


def window_start_ts(start: date = WINDOW_START) -> int:
    """Unix timestamp (UTC midnight) for the first day of the analysis window."""
    return int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())


def leagues_from_keys(keys) -> list[League]:
    out = []
    for k in keys:
        if k not in LEAGUES:
            raise KeyError(f"Unknown league '{k}'. Known: {', '.join(LEAGUES)}")
        out.append(LEAGUES[k])
    return out
