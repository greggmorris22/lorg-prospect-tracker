import urllib.request
import json

# Only these levels count as "in the minors". Excludes MLB-level players who
# are still rookie-eligible by service time, draft picks (assetType=PICK),
# and any players without a current assignment (level=None / IL / unassigned).
MINOR_LEAGUE_LEVELS = {"AAA", "AA", "HIGH_A", "LOW_A", "ROOKIE_BALL"}

# Sort order for display: C first, then infield, outfield, then pitchers.
# Any position not in this map (e.g. UT, DH) sorts to the end.
POSITION_ORDER = {"C": 0, "1B": 1, "2B": 2, "3B": 3, "SS": 4, "OF": 5, "SP": 6, "RP": 7}

# Sort order for minor league levels: closest to majors first.
LEVEL_ORDER = {"AAA": 0, "AA": 1, "HIGH_A": 2, "LOW_A": 3, "ROOKIE_BALL": 4}


def _primary_position(positions: list) -> str:
    """
    Returns the first position from the player's position list that appears
    in POSITION_ORDER. Falls back to the raw first position if none match
    (e.g. a player listed only as UT).
    """
    for pos in positions:
        if pos in POSITION_ORDER:
            return pos
    return positions[0] if positions else "UT"


def fetch_league_teams(league_id: str) -> dict:
    """
    Fetches all teams and their prospect rosters from HarryKnowsBall proxy API.
    Returns a dictionary mapping Team Name -> List of Prospect Player Names.

    Players are filtered to active minor leaguers only (AAA/AA/HIGH_A/LOW_A/
    ROOKIE_BALL) and sorted by position (C > 1B > 2B > 3B > SS > OF > SP > RP)
    then by level within each position (AAA first, ROOKIE_BALL last).

    Excluded:
      - MLB-level players who retain rookie eligibility by service time
      - Future draft picks (assetType=PICK, level=None)
      - Players on IL or without a current assignment (level=None)
    """
    url = "https://harryknowsball.com/hkb/fantraxLeague"
    payload = {"leagueId": league_id, "hardRefresh": False}

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        }
    )

    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())

        teams_dict = {}
        for t in data.get('teams', []):
            team_name = t.get('teamName', 'Unknown Team')

            prospects = []
            for player in t.get('players', []):
                is_prospect = player.get('prospect', False)
                is_in_minors = player.get('level') in MINOR_LEAGUE_LEVELS
                if is_prospect and is_in_minors:
                    primary_pos = _primary_position(player.get('positions', []))
                    level = player.get('level')
                    prospects.append({
                        'name': player.get('name', 'Unknown'),
                        'pos': primary_pos,
                        'level': level,
                    })

            # Sort by position order first, then by level order within position
            prospects.sort(key=lambda p: (
                POSITION_ORDER.get(p['pos'], 99),
                LEVEL_ORDER.get(p['level'], 99),
            ))

            teams_dict[team_name] = [p['name'] for p in prospects]

        return teams_dict
    except Exception as e:
        raise RuntimeError(f"Failed to fetch league data: {e}")
