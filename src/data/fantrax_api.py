import urllib.request
import json

# Only these levels count as "in the minors". Excludes MLB-level players who
# are still rookie-eligible by service time, draft picks (assetType=PICK),
# and any players without a current assignment (level=None / IL / unassigned).
MINOR_LEAGUE_LEVELS = {"AAA", "AA", "HIGH_A", "LOW_A", "ROOKIE_BALL"}

def fetch_league_teams(league_id: str) -> dict:
    """
    Fetches all teams and their prospect rosters from HarryKnowsBall proxy API.
    Returns a dictionary mapping Team Name -> List of Prospect Player Names.

    A player is included only if the API marks them as a prospect AND their
    current level is one of the recognized minor league levels. This excludes:
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
                    prospects.append(player.get('name', 'Unknown'))

            teams_dict[team_name] = prospects

        return teams_dict
    except Exception as e:
        raise RuntimeError(f"Failed to fetch league data: {e}")
