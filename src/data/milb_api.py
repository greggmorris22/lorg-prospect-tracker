"""
MLB Stats API helpers for fetching MiLB game logs and season stats.

Each public function returns separate season-totals and recent-games
DataFrames so the app can display them in distinct labeled sections,
along with player profile info (team, age, position).
"""

import urllib.request
import urllib.parse
import json
import pandas as pd
import concurrent.futures


def search_player(player_name: str) -> dict:
    """
    Search the MLB Stats API by name and return basic player info.

    Returns a dict with keys:
        id         -- MLB Stats API player ID (string)
        is_pitcher -- True if the player's primary position is pitcher
        team       -- current team abbreviation (or 'UNK')
        age        -- current age (int or 'UNK')
        position   -- primary position abbreviation (C, 1B, SS, P, etc.)

    Returns None if the search finds no results or the request fails.
    """
    encoded_name = urllib.parse.quote(player_name)
    url = f"https://statsapi.mlb.com/api/v1/people/search?names={encoded_name}"

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        people = data.get('people', [])
        if people:
            p = people[0]
            return {
                'id':         str(p['id']),
                'is_pitcher': p.get('primaryPosition', {}).get('code') == '1',
                'team':       p.get('currentTeam', {}).get('abbreviation', 'UNK'),
                'age':        p.get('currentAge', 'UNK'),
                'position':   p.get('primaryPosition', {}).get('abbreviation', 'UNK'),
            }
    except Exception as e:
        print(f"Error searching for {player_name}: {e}")
    return None


def fetch_stats(url: str):
    """Fetch JSON from a URL, returning None on any error."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except Exception:
        return None


def _savant_url(game_pk: int, date_short: str) -> str:
    """
    Build a Baseball Savant gamefeed URL with the short date (MM-DD) embedded
    as a query param. The extra param is ignored by Savant but lets Streamlit's
    LinkColumn regex extract "MM-DD" for display instead of showing the full URL.
    """
    return f"https://baseballsavant.mlb.com/gamefeed?gamePk={game_pk}&d={date_short}"


def _team_abbrev(team_obj: dict) -> str:
    """
    Extract a short team label from a team object in a game log split.
    Tries the abbreviation field first; falls back to the full name.
    Applies manual overrides for long MiLB team names that have no abbreviation.
    """
    abbrev = team_obj.get('abbreviation') or team_obj.get('name', 'UNK')
    overrides = {
        'Sacramento River Cats': 'SAC',
        'El Paso Chihuahuas':    'ELP',
    }
    return overrides.get(abbrev, abbrev)


def format_hitting_stats(splits: list, season_stat: dict) -> tuple:
    """
    Format hitting data into two separate DataFrames.

    Returns:
        season_df  -- one-row DataFrame of 2026 season totals
                      (GP, AB, R, H, 2B, 3B, HR, RBI, BB, SO, SB, CS,
                       AVG, OBP, SLG, OPS)
        games_df   -- DataFrame of the 7 most recent games in chronological
                      order (Date linked to Savant, Team, Opp, Result, and
                      per-game slash-line stats)
    """
    splits.sort(key=lambda x: x['date'], reverse=True)
    recent_7 = splits[:7]
    recent_7.reverse()  # chronological for display

    rows = []
    for game in recent_7:
        s = game.get('stat', {})
        t = _team_abbrev(game.get('team', {}))
        o = _team_abbrev(game.get('opponent', {}))
        date_short = game.get('date', '')[5:]  # "YYYY-MM-DD" -> "MM-DD"
        game_pk = game.get('game', {}).get('gamePk')

        # isWin reflects whether the player's team won that game
        is_win = game.get('isWin')
        result = "W" if is_win is True else ("L" if is_win is False else "")

        home_away = "vs" if game.get('isHome') else "@"
        date_value = _savant_url(game_pk, date_short) if game_pk else date_short

        rows.append({
            "Date":   date_value,
            "Team":   t,
            "Opp":    f"{home_away} {o}",
            "Result": result,
            "AB":     s.get('atBats', 0),
            "R":      s.get('runs', 0),
            "H":      s.get('hits', 0),
            "2B":     s.get('doubles', 0),
            "3B":     s.get('triples', 0),
            "HR":     s.get('homeRuns', 0),
            "RBI":    s.get('rbi', 0),
            "BB":     s.get('baseOnBalls', 0),
            "SO":     s.get('strikeOuts', 0),
            "SB":     s.get('stolenBases', 0),
            "CS":     s.get('caughtStealing', 0),
            "AVG":    s.get('avg', '.000'),
            "OBP":    s.get('obp', '.000'),
            "SLG":    s.get('slg', '.000'),
        })

    games_df = pd.DataFrame(rows)

    # Season totals — use API ops field if present, else derive from OBP + SLG
    s = season_stat if season_stat else {}
    obp_str = s.get('obp', '.000')
    slg_str = s.get('slg', '.000')
    ops_val = s.get('ops')
    if ops_val is None:
        try:
            ops_val = f"{float(obp_str) + float(slg_str):.3f}"
        except (ValueError, TypeError):
            ops_val = '.000'

    season_df = pd.DataFrame([{
        "GP":  s.get('gamesPlayed', 0),
        "AB":  s.get('atBats', 0),
        "R":   s.get('runs', 0),
        "H":   s.get('hits', 0),
        "2B":  s.get('doubles', 0),
        "3B":  s.get('triples', 0),
        "HR":  s.get('homeRuns', 0),
        "RBI": s.get('rbi', 0),
        "BB":  s.get('baseOnBalls', 0),
        "SO":  s.get('strikeOuts', 0),
        "SB":  s.get('stolenBases', 0),
        "CS":  s.get('caughtStealing', 0),
        "AVG": s.get('avg', '.000'),
        "OBP": obp_str,
        "SLG": slg_str,
        "OPS": ops_val,
    }])

    return season_df, games_df


def format_pitching_stats(splits: list, season_stat: dict) -> tuple:
    """
    Format pitching data into two separate DataFrames.

    Returns:
        season_df  -- one-row DataFrame of 2026 season totals
        games_df   -- DataFrame of the 7 most recent appearances in
                      chronological order
    """
    splits.sort(key=lambda x: x['date'], reverse=True)
    recent_7 = splits[:7]
    recent_7.reverse()

    rows = []
    for game in recent_7:
        s = game.get('stat', {})
        t = _team_abbrev(game.get('team', {}))
        o = _team_abbrev(game.get('opponent', {}))
        date_short = game.get('date', '')[5:]
        game_pk = game.get('game', {}).get('gamePk')

        is_win = game.get('isWin')
        result = "W" if is_win is True else ("L" if is_win is False else "")

        home_away = "vs" if game.get('isHome') else "@"
        date_value = _savant_url(game_pk, date_short) if game_pk else date_short

        rows.append({
            "Date":   date_value,
            "Team":   t,
            "Opp":    f"{home_away} {o}",
            "Result": result,
            "W":      s.get('wins', 0),
            "L":      s.get('losses', 0),
            "IP":     s.get('inningsPitched', '0.0'),
            "H":      s.get('hits', 0),
            "R":      s.get('runs', 0),
            "ER":     s.get('earnedRuns', 0),
            "HR":     s.get('homeRuns', 0),
            "BB":     s.get('baseOnBalls', 0),
            "SO":     s.get('strikeOuts', 0),
            "NP-S":   f"{s.get('numberOfPitches', 0)}-{s.get('strikes', 0)}",
            "ERA":    s.get('era', '0.00'),
            "WHIP":   s.get('whip', '0.00'),
        })

    games_df = pd.DataFrame(rows)

    s = season_stat if season_stat else {}
    season_df = pd.DataFrame([{
        "G":    s.get('gamesPlayed', 0),
        "GS":   s.get('gamesStarted', 0),
        "W":    s.get('wins', 0),
        "L":    s.get('losses', 0),
        "SV":   s.get('saves', 0),
        "ERA":  s.get('era', '0.00'),
        "IP":   s.get('inningsPitched', '0.0'),
        "H":    s.get('hits', 0),
        "R":    s.get('runs', 0),
        "ER":   s.get('earnedRuns', 0),
        "HR":   s.get('homeRuns', 0),
        "BB":   s.get('baseOnBalls', 0),
        "SO":   s.get('strikeOuts', 0),
        "WHIP": s.get('whip', '0.00'),
    }])

    return season_df, games_df


def get_milb_stats(player_name: str, player_id: str = None) -> tuple:
    """
    Fetch MiLB game logs and season stats for a player.

    player_id: optional MLB Stats API player ID. If provided, skips the name
    search entirely — useful when two players share a name and the wrong one
    is returned by the search endpoint.

    Returns a 5-tuple:
        (season_df, games_df, team_abbrev, age, position)

    Where:
        season_df   -- one-row season-totals DataFrame
        games_df    -- recent-games DataFrame
        team_abbrev -- player's current team abbreviation
        age         -- player's current age
        position    -- player's primary position abbreviation

    Returns None if the player cannot be found or has no 2026 stats.
    """
    if player_id:
        # Fetch full profile to determine position and get team/age info
        try:
            url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req).read())
            person = data['people'][0]
            pos_code = person.get('primaryPosition', {}).get('code', '')
            p_info = {
                'id':         player_id,
                'is_pitcher': pos_code == '1',
                'team':       person.get('currentTeam', {}).get('abbreviation', 'UNK'),
                'age':        person.get('currentAge', 'UNK'),
                'position':   person.get('primaryPosition', {}).get('abbreviation', 'UNK'),
            }
        except Exception as e:
            print(f"Error fetching player {player_id}: {e}")
            return None
    else:
        p_info = search_player(player_name)

    if not p_info:
        return None

    player_id  = p_info['id']
    team       = p_info.get('team', 'UNK')
    age        = p_info.get('age', 'UNK')
    position   = p_info.get('position', 'UNK')
    group      = "pitching" if p_info['is_pitcher'] else "hitting"
    year       = 2026

    # MiLB sport IDs — prospects are minor leaguers only in this tracker
    # 11: AAA, 12: AA, 13: A+, 14: A, 15: Rk(Complex), 16: DSL, 17: VSL
    sport_ids = [11, 12, 13, 14, 15, 16, 17]

    def fetch_level(sid):
        """Fetch game log and season stats for one sport level."""
        url = (
            f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
            f"?stats=gameLog,season&group={group}&season={year}"
            f"&gameType=R&sportId={sid}"
        )
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
                        if (new_stat.get('atBats', 0) > best_season_stat.get('atBats', 0)
                                or new_stat.get('inningsPitched', '0.0')
                                    > best_season_stat.get('inningsPitched', '0.0')):
                            best_season_stat = new_stat

    if not all_splits:
        return None

    if p_info['is_pitcher']:
        season_df, games_df = format_pitching_stats(all_splits, best_season_stat)
    else:
        season_df, games_df = format_hitting_stats(all_splits, best_season_stat)

    return season_df, games_df, team, age, position
