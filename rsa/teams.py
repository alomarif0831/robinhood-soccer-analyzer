"""Team-name normalization so market titles, ESPN and football-data.co.uk agree.

Every source spells clubs differently ("Man United", "Manchester United",
"Manchester Utd", "Man Utd"). We reduce a name to a canonical slug via
accent-stripping, dropping club-form tokens (FC, CF, SC...), an alias table,
and finally fuzzy matching against the candidate set for the league.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

# Tokens that carry no identity (club-form words and numbers-as-years).
_DROP_TOKENS = {
    "fc", "cf", "sc", "ac", "afc", "ss", "ssc", "us", "as", "ud", "sd", "rcd", "rc", "cd", "ca", "sv",
    "vfb", "vfl", "tsg", "fsv", "bsc", "sk", "fk", "bk", "if", "club", "calcio", "cfc", "the",
    "1", "04", "05", "09", "1846", "1899", "1893", "1900", "1904", "1909", "1913", "1919", "1927",
}

# Canonical slug -> list of alternative spellings (lowercase, pre-normalized loosely).
_ALIASES: dict[str, list[str]] = {
    # ---- Premier League
    "arsenal": ["arsenal"],
    "aston_villa": ["aston villa", "villa"],
    "bournemouth": ["bournemouth", "afc bournemouth"],
    "brentford": ["brentford"],
    "brighton": ["brighton", "brighton and hove albion", "brighton hove albion"],
    "burnley": ["burnley"],
    "chelsea": ["chelsea"],
    "crystal_palace": ["crystal palace", "palace"],
    "everton": ["everton"],
    "fulham": ["fulham"],
    "leeds": ["leeds", "leeds united", "leeds utd"],
    "liverpool": ["liverpool"],
    "man_city": ["man city", "manchester city", "mancity"],
    "man_united": ["man united", "manchester united", "man utd", "manchester utd", "manutd"],
    "newcastle": ["newcastle", "newcastle united", "newcastle utd"],
    "nottm_forest": ["nott'm forest", "nottm forest", "nottingham forest", "forest", "nottingham"],
    "sunderland": ["sunderland"],
    "tottenham": ["tottenham", "tottenham hotspur", "spurs"],
    "west_ham": ["west ham", "west ham united", "west ham utd"],
    "wolves": ["wolves", "wolverhampton", "wolverhampton wanderers"],
    "ipswich": ["ipswich", "ipswich town"],
    "leicester": ["leicester", "leicester city"],
    "southampton": ["southampton"],
    # ---- La Liga
    "alaves": ["alaves", "deportivo alaves"],
    "athletic_bilbao": ["ath bilbao", "athletic bilbao", "athletic club", "athletic", "bilbao"],
    "atletico_madrid": ["ath madrid", "atletico madrid", "atletico de madrid", "atletico", "atl madrid"],
    "barcelona": ["barcelona", "barca"],
    "real_betis": ["betis", "real betis"],
    "celta_vigo": ["celta", "celta vigo", "celta de vigo"],
    "elche": ["elche"],
    "espanyol": ["espanol", "espanyol", "rcd espanyol"],
    "getafe": ["getafe"],
    "girona": ["girona"],
    "levante": ["levante"],
    "mallorca": ["mallorca", "rcd mallorca"],
    "osasuna": ["osasuna", "ca osasuna"],
    "real_oviedo": ["oviedo", "real oviedo"],
    "rayo_vallecano": ["vallecano", "rayo vallecano", "rayo"],
    "real_madrid": ["real madrid", "madrid"],
    "real_sociedad": ["sociedad", "real sociedad"],
    "sevilla": ["sevilla"],
    "valencia": ["valencia"],
    "villarreal": ["villarreal"],
    "las_palmas": ["las palmas", "ud las palmas"],
    "leganes": ["leganes"],
    "valladolid": ["valladolid", "real valladolid"],
    # ---- Bundesliga
    "augsburg": ["augsburg", "fc augsburg"],
    "bayern_munich": ["bayern munich", "bayern", "bayern munchen", "fc bayern munchen", "fc bayern"],
    "dortmund": ["dortmund", "borussia dortmund", "bvb"],
    "frankfurt": ["ein frankfurt", "eintracht frankfurt", "frankfurt"],
    "freiburg": ["freiburg", "sc freiburg"],
    "hamburg": ["hamburg", "hamburger sv", "hsv"],
    "heidenheim": ["heidenheim", "1 fc heidenheim"],
    "hoffenheim": ["hoffenheim", "tsg hoffenheim", "1899 hoffenheim"],
    "koln": ["fc koln", "koln", "cologne", "1 fc koln"],
    "leverkusen": ["leverkusen", "bayer leverkusen", "bayer 04 leverkusen"],
    "mainz": ["mainz", "mainz 05", "1 fsv mainz 05"],
    "mgladbach": ["m'gladbach", "mgladbach", "monchengladbach", "borussia monchengladbach", "gladbach"],
    "rb_leipzig": ["rb leipzig", "leipzig"],
    "st_pauli": ["st pauli", "st. pauli", "fc st pauli"],
    "stuttgart": ["stuttgart", "vfb stuttgart"],
    "union_berlin": ["union berlin", "1 fc union berlin"],
    "werder_bremen": ["werder bremen", "bremen", "werder"],
    "wolfsburg": ["wolfsburg", "vfl wolfsburg"],
    "bochum": ["bochum", "vfl bochum"],
    "holstein_kiel": ["holstein kiel", "kiel"],
    # ---- Serie A
    "atalanta": ["atalanta"],
    "bologna": ["bologna"],
    "cagliari": ["cagliari"],
    "como": ["como"],
    "cremonese": ["cremonese"],
    "fiorentina": ["fiorentina"],
    "genoa": ["genoa"],
    "inter": ["inter", "inter milan", "internazionale"],
    "juventus": ["juventus", "juve"],
    "lazio": ["lazio"],
    "lecce": ["lecce"],
    "milan": ["milan", "ac milan"],
    "napoli": ["napoli"],
    "parma": ["parma"],
    "pisa": ["pisa"],
    "roma": ["roma", "as roma"],
    "sassuolo": ["sassuolo"],
    "torino": ["torino"],
    "udinese": ["udinese"],
    "verona": ["verona", "hellas verona"],
    "empoli": ["empoli"],
    "monza": ["monza"],
    "venezia": ["venezia"],
    # ---- Ligue 1
    "angers": ["angers", "angers sco"],
    "auxerre": ["auxerre", "aj auxerre"],
    "brest": ["brest", "stade brestois"],
    "le_havre": ["le havre", "le havre ac"],
    "lens": ["lens", "rc lens"],
    "lille": ["lille", "losc", "losc lille"],
    "lorient": ["lorient", "fc lorient"],
    "lyon": ["lyon", "olympique lyonnais", "ol"],
    "marseille": ["marseille", "olympique marseille", "olympique de marseille", "om"],
    "metz": ["metz", "fc metz"],
    "monaco": ["monaco", "as monaco"],
    "nantes": ["nantes", "fc nantes"],
    "nice": ["nice", "ogc nice"],
    "paris_fc": ["paris fc"],
    "psg": ["paris sg", "paris saint-germain", "paris saint germain", "psg", "paris"],
    "rennes": ["rennes", "stade rennais"],
    "strasbourg": ["strasbourg", "rc strasbourg"],
    "toulouse": ["toulouse", "toulouse fc"],
    "montpellier": ["montpellier"],
    "reims": ["reims", "stade de reims"],
    "st_etienne": ["st etienne", "saint-etienne", "saint etienne", "as saint-etienne"],
    # ---- MLS
    "atlanta_united": ["atlanta united", "atlanta"],
    "austin": ["austin", "austin fc"],
    "charlotte": ["charlotte", "charlotte fc"],
    "chicago_fire": ["chicago fire", "chicago"],
    "cincinnati": ["cincinnati", "fc cincinnati"],
    "colorado_rapids": ["colorado rapids", "colorado"],
    "columbus_crew": ["columbus crew", "columbus"],
    "dc_united": ["dc united", "d.c. united", "washington"],
    "dallas": ["dallas", "fc dallas"],
    "houston_dynamo": ["houston dynamo", "houston"],
    "inter_miami": ["inter miami", "miami"],
    "la_galaxy": ["la galaxy", "galaxy", "los angeles galaxy"],
    "lafc": ["lafc", "los angeles fc", "los angeles"],
    "minnesota_united": ["minnesota united", "minnesota"],
    "montreal": ["montreal", "cf montreal", "montréal"],
    "nashville": ["nashville", "nashville sc"],
    "new_england": ["new england", "new england revolution", "revolution"],
    "nycfc": ["nycfc", "new york city", "new york city fc"],
    "ny_red_bulls": ["new york red bulls", "ny red bulls", "red bulls", "rbny"],
    "orlando_city": ["orlando city", "orlando"],
    "philadelphia_union": ["philadelphia union", "philadelphia", "union"],
    "portland_timbers": ["portland timbers", "portland"],
    "real_salt_lake": ["real salt lake", "salt lake", "rsl"],
    "san_diego": ["san diego", "san diego fc"],
    "san_jose": ["san jose", "san jose earthquakes", "earthquakes"],
    "seattle_sounders": ["seattle sounders", "seattle"],
    "sporting_kc": ["sporting kc", "sporting kansas city", "kansas city"],
    "st_louis_city": ["st louis city", "st. louis city", "st louis", "saint louis"],
    "toronto": ["toronto", "toronto fc"],
    "vancouver_whitecaps": ["vancouver whitecaps", "vancouver"],
}

_ALIAS_LOOKUP: dict[str, str] = {}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _basic(s: str) -> str:
    s = _strip_accents(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize(name: str) -> str:
    """Loose normalized form: accents/punctuation removed, club-form tokens dropped."""
    tokens = [t for t in _basic(name).split() if t not in _DROP_TOKENS]
    return " ".join(tokens) or _basic(name)


def _build_lookup() -> None:
    if _ALIAS_LOOKUP:
        return
    for slug, names in _ALIASES.items():
        for n in names:
            _ALIAS_LOOKUP[normalize(n)] = slug
            _ALIAS_LOOKUP[_basic(n)] = slug


def canonical(name: str) -> str:
    """Canonical slug for a team name (falls back to the normalized string)."""
    _build_lookup()
    if not name:
        return ""
    for key in (normalize(name), _basic(name)):
        if key in _ALIAS_LOOKUP:
            return _ALIAS_LOOKUP[key]
    return normalize(name).replace(" ", "_")


def match_team(name: str, candidates: list[str], cutoff: float = 0.8) -> str | None:
    """Find which of ``candidates`` (raw names from another source) ``name`` refers to.

    Exact canonical match first, then fuzzy matching on normalized strings.
    Returns the matching *candidate string* (not the slug), or None.
    """
    target = canonical(name)
    by_slug = {canonical(c): c for c in candidates}
    if target in by_slug:
        return by_slug[target]
    norm_target = normalize(name)
    norm_candidates = {normalize(c): c for c in candidates}
    # token containment ("wolverhampton" in "wolverhampton wanderers")
    for nc, raw in norm_candidates.items():
        a, b = set(norm_target.split()), set(nc.split())
        if a and b and (a <= b or b <= a) and len(a & b) >= 1 and max(len(a), len(b)) <= 3:
            if len(a & b) == min(len(a), len(b)):
                return raw
    close = difflib.get_close_matches(norm_target, list(norm_candidates), n=1, cutoff=cutoff)
    return norm_candidates[close[0]] if close else None


_VS_SPLIT = re.compile(r"\s+(?:vs\.?|v\.?|versus|@|at|-)\s+", re.IGNORECASE)


def split_matchup(title: str) -> tuple[str, str] | None:
    """Split "Arsenal vs Wolves" / "Arsenal at Wolves" style titles into (first, second).

    "A at B" means A is away; the caller decides ordering using the ``at`` hint
    returned by :func:`parse_matchup`.
    """
    parsed = parse_matchup(title)
    return (parsed[0], parsed[1]) if parsed else None


def parse_matchup(title: str) -> tuple[str, str, bool] | None:
    """Return (home, away, used_at_form) parsed from a matchup title.

    Handles "Home vs Away", "Home v Away", "Away at Home" and "Away @ Home".
    Trailing decorations like ": Winner" or "(Match Winner)" are stripped.
    """
    if not title:
        return None
    t = re.split(r"\s*[:(\[]\s*", title, maxsplit=1)[0].strip()
    m = re.search(r"\s+(vs\.?|v\.?|versus|@|at|-)\s+", t, re.IGNORECASE)
    if not m:
        return None
    left, right = t[: m.start()].strip(), t[m.end():].strip()
    if not left or not right:
        return None
    sep = m.group(1).lower().rstrip(".")
    if sep in ("at", "@"):
        return right, left, True
    return left, right, False
