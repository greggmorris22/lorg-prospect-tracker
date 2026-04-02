import urllib.request
import urllib.parse
import json
import pandas as pd
import concurrent.futures

def search_player(player_name: str) -> dict:
    encoded_name = urllib.parse.quote(player_name)
    url = f"https://statsapi.mlb.com/api/v1/people/search?names={encoded_name}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        people = data.get('people', [])
        if people:
            p = people[0]
            is_pitcher = p.get('primaryPosition', {}).get('code') == '1'
            return {'id': str(p['id']), 'is_pitcher': is_pitcher}
    except Exception as e:
        print(f"Error searching for {player_name}: {e}")
    return None

def fetch_stats(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except:
        return None

def format_hitting_stats(splits, season_stat):
    splits.sort(key=lambda x: x['date'], reverse=True)
    recent_7 = splits[:7]
    recent_7.reverse() # chronological
    
    rows = []
    for game in recent_7:
        s = game.get('stat', {})
        t = game.get('team', {}).get('name', 'UNK')
        o = game.get('opponent', {}).get('name', 'UNK')
        lvl = game.get('sport', {}).get('abbreviation', 'UNK')
        
        if "River Cats" in t: t = "SAC"
        elif "Chihuahuas" in o: o = "ELP"
        elif "Chihuahuas" in t: t = "ELP"
        elif "River Cats" in o: o = "SAC"
        
        row = {
            "Date": game.get('date', '')[5:],
            "Lvl": lvl,
            "Team": t,
            "OPP": f"vs {o}" if game.get('isHome') else f"@ {o}",
            "AB": s.get('atBats', 0),
            "R": s.get('runs', 0),
            "H": s.get('hits', 0),
            "TB": s.get('totalBases', 0),
            "2B": s.get('doubles', 0),
            "3B": s.get('triples', 0),
            "HR": s.get('homeRuns', 0),
            "RBI": s.get('rbi', 0),
            "BB": s.get('baseOnBalls', 0),
            "IBB": s.get('intentionalWalks', 0),
            "SO": s.get('strikeOuts', 0),
            "SB": s.get('stolenBases', 0),
            "CS": s.get('caughtStealing', 0),
            "AVG": s.get('avg', '.000'),
            "OBP": s.get('obp', '.000'),
            "SLG": s.get('slg', '.000'),
            "HBP": s.get('hitByPitch', 0),
            "SAC": s.get('sacBunts', 0),
            "SF": s.get('sacFlies', 0)
        }
        rows.append(row)
        
    s = season_stat if season_stat else {}
    rows.append({
        "Date": "Season", "Lvl": "-", "Team": "-", "OPP": "-",
        "AB": s.get('atBats', 0), "R": s.get('runs', 0), "H": s.get('hits', 0), "TB": s.get('totalBases', 0),
        "2B": s.get('doubles', 0), "3B": s.get('triples', 0), "HR": s.get('homeRuns', 0), "RBI": s.get('rbi', 0),
        "BB": s.get('baseOnBalls', 0), "IBB": s.get('intentionalWalks', 0), "SO": s.get('strikeOuts', 0),
        "SB": s.get('stolenBases', 0), "CS": s.get('caughtStealing', 0), "AVG": s.get('avg', '.000'),
        "OBP": s.get('obp', '.000'), "SLG": s.get('slg', '.000'), "HBP": s.get('hitByPitch', 0),
        "SAC": s.get('sacBunts', 0), "SF": s.get('sacFlies', 0)
    })
    return pd.DataFrame(rows)

def format_pitching_stats(splits, season_stat):
    splits.sort(key=lambda x: x['date'], reverse=True)
    recent_7 = splits[:7]
    recent_7.reverse() # chronological
    
    rows = []
    for game in recent_7:
        s = game.get('stat', {})
        t = game.get('team', {}).get('name', 'UNK')
        o = game.get('opponent', {}).get('name', 'UNK')
        lvl = game.get('sport', {}).get('abbreviation', 'UNK')
        
        row = {
            "Date": game.get('date', '')[5:],
            "Lvl": lvl,
            "Team": t,
            "OPP": f"vs {o}" if game.get('isHome') else f"@ {o}",
            "W": s.get('wins', 0),
            "L": s.get('losses', 0),
            "ERA": s.get('era', '0.00'),
            "G": s.get('gamesPlayed', 0),
            "GS": s.get('gamesStarted', 0),
            "CG": s.get('completeGames', 0),
            "SHO": s.get('shutouts', 0),
            "SV": s.get('saves', 0),
            "SVO": s.get('saveOpportunities', 0),
            "IP": s.get('inningsPitched', '0.0'),
            "H": s.get('hits', 0),
            "R": s.get('runs', 0),
            "ER": s.get('earnedRuns', 0),
            "HR": s.get('homeRuns', 0),
            "HB": s.get('hitBatsmen', 0),
            "BB": s.get('baseOnBalls', 0),
            "IBB": s.get('intentionalWalks', 0),
            "SO": s.get('strikeOuts', 0),
            "NP-S": f"{s.get('numberOfPitches', 0)}-{s.get('strikes', 0)}",
            "AVG": s.get('avg', '.000'),
            "WHIP": s.get('whip', '0.00')
        }
        rows.append(row)
        
    s = season_stat if season_stat else {}
    rows.append({
        "Date": "Season", "Lvl": "-", "Team": "-", "OPP": "-",
        "W": s.get('wins', 0), "L": s.get('losses', 0), "ERA": s.get('era', '0.00'),
        "G": s.get('gamesPlayed', 0), "GS": s.get('gamesStarted', 0), "CG": s.get('completeGames', 0),
        "SHO": s.get('shutouts', 0), "SV": s.get('saves', 0), "SVO": s.get('saveOpportunities', 0),
        "IP": s.get('inningsPitched', '0.0'), "H": s.get('hits', 0), "R": s.get('runs', 0),
        "ER": s.get('earnedRuns', 0), "HR": s.get('homeRuns', 0), "HB": s.get('hitBatsmen', 0),
        "BB": s.get('baseOnBalls', 0), "IBB": s.get('intentionalWalks', 0), "SO": s.get('strikeOuts', 0),
        "NP-S": f"{s.get('numberOfPitches', 0)}-{s.get('strikes', 0)}", "AVG": s.get('avg', '.000'),
        "WHIP": s.get('whip', '0.00')
    })
    return pd.DataFrame(rows)

def get_milb_stats(player_name: str, player_id: str = None) -> pd.DataFrame:
    """
    Fetch MiLB game logs and season stats for a player.

    player_id: optional MLB Stats API player ID. If provided, skips the name
    search entirely — useful when two players share a name and the wrong one
    is returned by the search endpoint.
    """
    if player_id:
        # Fetch position directly to determine hitter vs pitcher
        try:
            url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req).read())
            pos_code = data['people'][0].get('primaryPosition', {}).get('code', '')
            p_info = {'id': player_id, 'is_pitcher': pos_code == '1'}
        except Exception as e:
            print(f"Error fetching player {player_id}: {e}")
            return None
    else:
        p_info = search_player(player_name)
    if not p_info:
        return None
        
    player_id = p_info['id']
    group = "pitching" if p_info['is_pitcher'] else "hitting"
    year = 2026
    
    # Comprehensive MiLB levels
    # 11: AAA, 12: AA, 13: A+, 14: A, 15: Rk(Complex), 16: Rk(DSL), 17: Rk(VSL)
    sport_ids = [11, 12, 13, 14, 15, 16, 17]
    
    def fetch_level(sid):
        # We exclusively fetch Regular Season (gameType=R)
        url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog,season&group={group}&season={year}&gameType=R&sportId={sid}"
        return fetch_stats(url)

    all_splits = []
    best_season_stat = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = {executor.submit(fetch_level, sid): sid for sid in sport_ids}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res and res.get('stats'):
                for stat_block in res['stats']:
                    if stat_block['type']['displayName'] == 'gameLog' and stat_block.get('splits'):
                        all_splits.extend(stat_block['splits'])
                    elif stat_block['type']['displayName'] == 'season' and stat_block.get('splits'):
                        new_stat = stat_block['splits'][0].get('stat', {})
                        if new_stat.get('atBats', 0) > best_season_stat.get('atBats', 0) or new_stat.get('inningsPitched', '0.0') > best_season_stat.get('inningsPitched', '0.0'):
                             best_season_stat = new_stat
                             
    # Note: Spring Training fallback (gameType=S) was intentionally removed per user request
    if not all_splits:
        return None
        
    if group == "pitching":
        return format_pitching_stats(all_splits, best_season_stat)
    else:
        return format_hitting_stats(all_splits, best_season_stat)
