import urllib.request
import json

def fetch_league_teams(league_id: str) -> dict:
    """
    Fetches all teams and their prospect rosters from HarryKnowsBall proxy API.
    Returns a dictionary mapping Team Name -> List of Prospect Player Names.
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
                # Filter for players marked as prospects
                is_prospect = player.get('prospect', False)
                if is_prospect:
                    # Clean the name (remove extra flags if any)
                    name = player.get('name', 'Unknown')
                    prospects.append(name)
            
            teams_dict[team_name] = prospects
            
        return teams_dict
    except Exception as e:
        raise RuntimeError(f"Failed to fetch league data: {e}")
