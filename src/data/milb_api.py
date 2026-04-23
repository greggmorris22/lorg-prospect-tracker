"""
MLB Stats API helpers for fetching MiLB game logs and season stats.

Each public function returns separate season-totals and recent-games
DataFrames so the app can display them in distinct labeled sections,
along with player profile info (current level, team, age, position).
"""

import urllib.request
import urllib.parse
import json
import pandas as pd
import concurrent.futures


# FIP league constant — approximate recent MLB average. Update yearly if desired.
FIP_CONSTANT = 3.10

# FanGraphs "guts" constants for wOBA / wRC+, MLB 2024 values.
# Used as a proxy for MiLB since FanGraphs does not publish per-MiLB-league
# guts or park factors. wRC+ computed here is an approximation, not a
# FanGraphs-accurate figure.
WOBA_WEIGHTS = {
    'BB':  0.689,
    'HBP': 0.720,
    '1B':  0.882,
    '2B':  1.254,
    '3B':  1.590,
    'HR':  2.050,
}
WOBA_SCALE = 1.243
LG_WOBA    = 0.310
LG_R_PA    = 0.113


def _pct(num, den) -> str:
    """Format a ratio as a percent string, e.g. 0.123 -> '12.3%'. '—' on /0."""
    try:
        n, d = float(num), float(den)
        if d == 0:
            return '—'
        return f"{(n / d) * 100:.1f}%"
    except (TypeError, ValueError):
        return '—'


def _rate_per_9(num, ip) -> str:
    """Compute a per-9-innings rate (e.g. K/9) from raw count and IP string."""
    try:
        n, i = float(num), float(ip)
        if i == 0:
            return '0.00'
        return f"{(n * 9.0) / i:.2f}"
    except (TypeError, ValueError):
        return '0.00'


def _ratio3(num, den) -> str:
    """Format a ratio to a 3-decimal baseball-style string like '.312'."""
    try:
        n, d = float(num), float(den)
        if d == 0:
            return '.000'
        v = n / d
        # Strip leading 0 for values <1 to match AVG/OBP/SLG convention
        s = f"{v:.3f}"
        return s[1:] if s.startswith('0.') else s
    except (TypeError, ValueError):
        return '.000'


def _iso(avg_str, slg_str) -> str:
    """ISO = SLG - AVG, formatted like '.198'."""
    try:
        v = float(slg_str) - float(avg_str)
        s = f"{v:.3f}"
        return s[1:] if s.startswith('0.') else ('-' + s[2:] if s.startswith('-0.') else s)
    except (TypeError, ValueError):
        return '.000'


def _compute_wrc_plus(s: dict) -> str:
    """
    Approximate wRC+ using MLB 2024 FanGraphs guts constants and park factor = 1.
    Not FanGraphs-accurate for MiLB — league constants differ by level.
    """
    try:
        pa  = float(s.get('plateAppearances', 0) or 0)
        ab  = float(s.get('atBats', 0) or 0)
        bb  = float(s.get('baseOnBalls', 0) or 0)
        ibb = float(s.get('intentionalWalks', 0) or 0)
        hbp = float(s.get('hitByPitch', 0) or 0)
        sf  = float(s.get('sacFlies', 0) or 0)
        h   = float(s.get('hits', 0) or 0)
        d2  = float(s.get('doubles', 0) or 0)
        d3  = float(s.get('triples', 0) or 0)
        hr  = float(s.get('homeRuns', 0) or 0)

        if pa == 0:
            return '—'

        singles = h - d2 - d3 - hr
        num = (WOBA_WEIGHTS['BB']  * (bb - ibb)
             + WOBA_WEIGHTS['HBP'] * hbp
             + WOBA_WEIGHTS['1B']  * singles
             + WOBA_WEIGHTS['2B']  * d2
             + WOBA_WEIGHTS['3B']  * d3
             + WOBA_WEIGHTS['HR']  * hr)
        den = ab + bb - ibb + sf + hbp
        if den == 0:
            return '—'
        woba = num / den
        wraa = ((woba - LG_WOBA) / WOBA_SCALE) * pa
        wrc_plus = (((wraa / pa) + LG_R_PA) / LG_R_PA) * 100
        return str(int(round(wrc_plus)))
    except (TypeError, ValueError, ZeroDivisionError):
        return '—'


def _compute_pitcher_babip(s: dict) -> str:
    """BABIP = (H - HR) / (BF - K - HR - BB - HBP - SF)."""
    try:
        h   = float(s.get('hits', 0) or 0)
        hr  = float(s.get('homeRuns', 0) or 0)
        bf  = float(s.get('battersFaced', 0) or 0)
        k   = float(s.get('strikeOuts', 0) or 0)
        bb  = float(s.get('baseOnBalls', 0) or 0)
        hbp = float(s.get('hitBatsmen', 0) or 0)
        sf  = float(s.get('sacFlies', 0) or 0)
        den = bf - k - hr - bb - hbp - sf
        if den <= 0:
            return '.000'
        return _ratio3(h - hr, den)
    except (TypeError, ValueError):
        return '.000'


def _compute_lob_pct(s: dict) -> str:
    """LOB% = (H + BB + HBP - R) / (H + BB + HBP - 1.4*HR)."""
    try:
        h   = float(s.get('hits', 0) or 0)
        bb  = float(s.get('baseOnBalls', 0) or 0)
        hbp = float(s.get('hitBatsmen', 0) or 0)
        r   = float(s.get('runs', 0) or 0)
        hr  = float(s.get('homeRuns', 0) or 0)
        den = h + bb + hbp - (1.4 * hr)
        num = h + bb + hbp - r
        if den == 0:
            return '—'
        return f"{(num / den) * 100:.1f}%"
    except (TypeError, ValueError):
        return '—'


def _compute_fip(s: dict) -> str:
    """FIP = ((13*HR + 3*(BB+HBP) - 2*K) / IP) + FIP_CONSTANT."""
    try:
        hr  = float(s.get('homeRuns', 0) or 0)
        bb  = float(s.get('baseOnBalls', 0) or 0)
        hbp = float(s.get('hitBatsmen', 0) or 0)
        k   = float(s.get('strikeOuts', 0) or 0)
        ip  = float(s.get('inningsPitched', 0) or 0)
        if ip == 0:
            return '0.00'
        fip = ((13 * hr + 3 * (bb + hbp) - 2 * k) / ip) + FIP_CONSTANT
        return f"{fip:.2f}"
    except (TypeError, ValueError):
        return '0.00'


def search_player(player_name: str) -> dict:
    """
    Search the MLB Stats API by name and return basic player info.

    Returns a dict with keys:
        id         -- MLB Stats API player ID (string)
        is_pitcher -- True if the player's primary position is pitcher
        team       -- current team full name (or 'UNK')
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
                'team':       p.get('currentTeam', {}).get('name', 'UNK'),
                'age':        p.get('currentAge', 'UNK'),
                'position':   normalize_position(p.get('primaryPosition', {}).get('abbreviation', 'UNK')),
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


def normalize_position(pos: str) -> str:
    """
    Collapse all outfield sub-positions into a single 'OF' label.
    LF, CF, and RF are all returned as 'OF'; all other positions are unchanged.
    """
    return 'OF' if pos in {'LF', 'CF', 'RF'} else pos


def fetch_parent_org(team_id: int) -> str:
    """
    Look up the MLB parent organization name for a minor league team.

    Minor league teams in the Stats API carry a parentOrgName field that
    holds the MLB affiliate name (e.g., "Milwaukee Brewers" for Biloxi
    Shuckers). For an MLB team itself, this field is absent and the team's
    own name is returned instead.

    Returns the parent org name string, or 'UNK' on any error.
    """
    if not team_id:
        return 'UNK'
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}"
    data = fetch_stats(url)
    if data and data.get('teams'):
        t = data['teams'][0]
        return t.get('parentOrgName') or t.get('name', 'UNK')
    return 'UNK'


def fetch_game_scores(pk_home_map: dict) -> dict:
    """
    Batch-fetch final scores for a set of gamePks in a single API call.

    pk_home_map: dict mapping gamePk (int) -> is_home (bool), indicating
    whether the player's team was the home team in each game.

    Returns a dict mapping gamePk -> score string, e.g.:
        {717949: "W 4-2", 717950: "L 3-5", 717951: "2-2"}

    Games that are in progress or postponed get a score without a W/L prefix.
    Games whose data is unavailable get an empty string.
    """
    if not pk_home_map:
        return {}

    pks_str = ",".join(str(pk) for pk in pk_home_map)
    url = f"https://statsapi.mlb.com/api/v1/schedule?gamePks={pks_str}"
    data = fetch_stats(url)

    scores = {}
    if not data:
        return scores

    for date_entry in data.get('dates', []):
        for game in date_entry.get('games', []):
            pk = game.get('gamePk')
            if pk not in pk_home_map:
                continue

            home = game.get('teams', {}).get('home', {})
            away = game.get('teams', {}).get('away', {})
            home_score = home.get('score')
            away_score = away.get('score')

            if home_score is None or away_score is None:
                scores[pk] = ""
                continue

            is_home = pk_home_map[pk]
            team_score = home_score if is_home else away_score
            opp_score  = away_score if is_home else home_score

            game_state = game.get('status', {}).get('abstractGameState', '')
            if game_state == 'Final':
                is_winner = home.get('isWinner', False) if is_home else away.get('isWinner', False)
                prefix = "W " if is_winner else "L "
            else:
                prefix = ""  # In-progress or not yet final — no W/L

            scores[pk] = f"{prefix}{team_score}-{opp_score}"

    return scores


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


def format_hitting_stats(splits: list, season_stat: dict, scores: dict = None) -> tuple:
    """
    Format hitting data into two separate DataFrames.

    scores: optional dict of {gamePk: score_string} from fetch_game_scores().
    If provided, a Score column is included in games_df.

    Returns:
        season_df  -- one-row DataFrame of 2026 season totals
                      (PA, H, 2B, 3B, HR, R, RBI, SB, CS, BB%, K%, ISO,
                       BABIP, AVG, OBP, SLG, OPS, wRC+)
        games_df   -- DataFrame of the 7 most recent games in chronological
                      order (Date linked to Savant, Team, Opp, Score, and
                      per-game slash-line stats)
    """
    splits.sort(key=lambda x: x['date'], reverse=True)
    recent_7 = splits[:7]  # newest first — most recent game at the top

    rows = []
    for game in recent_7:
        s = game.get('stat', {})
        t = _team_abbrev(game.get('team', {}))
        o = _team_abbrev(game.get('opponent', {}))
        date_short = game.get('date', '')[5:]  # "YYYY-MM-DD" -> "MM-DD"
        game_pk = game.get('game', {}).get('gamePk')
        lvl = game.get('minorLeagueLevel', '')

        home_away = "vs" if game.get('isHome') else "@"
        date_value = _savant_url(game_pk, date_short) if game_pk else date_short

        # Look up the final score from the pre-fetched scores dict
        score_str = (scores.get(game_pk, "") if scores and game_pk else "")

        rows.append({
            "Date":  date_value,
            "Lvl":   lvl,
            "Team":  t,
            "Opp":   f"{home_away} {o}",
            "Score": score_str,
            "AB":    s.get('atBats', 0),
            "R":     s.get('runs', 0),
            "H":     s.get('hits', 0),
            "2B":    s.get('doubles', 0),
            "3B":    s.get('triples', 0),
            "HR":    s.get('homeRuns', 0),
            "RBI":   s.get('rbi', 0),
            "BB":    s.get('baseOnBalls', 0),
            "SO":    s.get('strikeOuts', 0),
            "SB":    s.get('stolenBases', 0),
            "CS":    s.get('caughtStealing', 0),
            "AVG":   s.get('avg', '.000'),
            "OBP":   s.get('obp', '.000'),
            "SLG":   s.get('slg', '.000'),
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

    avg_str = s.get('avg', '.000')
    pa = s.get('plateAppearances', 0)
    bb = s.get('baseOnBalls', 0)
    so = s.get('strikeOuts', 0)

    season_df = pd.DataFrame([{
        "PA":    pa,
        "H":     s.get('hits', 0),
        "2B":    s.get('doubles', 0),
        "3B":    s.get('triples', 0),
        "HR":    s.get('homeRuns', 0),
        "R":     s.get('runs', 0),
        "RBI":   s.get('rbi', 0),
        "SB":    s.get('stolenBases', 0),
        "CS":    s.get('caughtStealing', 0),
        "BB%":   _pct(bb, pa),
        "K%":    _pct(so, pa),
        "ISO":   _iso(avg_str, slg_str),
        "BABIP": s.get('babip', '.000'),
        "AVG":   avg_str,
        "OBP":   obp_str,
        "SLG":   slg_str,
        "OPS":   ops_val,
        "wRC+":  _compute_wrc_plus(s),
    }])

    return season_df, games_df


def format_pitching_stats(splits: list, season_stat: dict, scores: dict = None) -> tuple:
    """
    Format pitching data into two separate DataFrames.

    scores: optional dict of {gamePk: score_string} from fetch_game_scores().

    Returns:
        season_df  -- one-row DataFrame of 2026 season totals
                      (GP-GS, W-L, SV-BS, IP, QS, R, ER, BAA, K/9, BB/9,
                       HR/9, K%-BB%, BABIP, LOB%, GB%, HR/FB, ERA, FIP)
        games_df   -- DataFrame of the 7 most recent appearances in
                      chronological order
                      (Date, Team, Opp, Score, GS, W, L, SV, BS, HLD,
                       IP, H, R, ER, HR, BB, K, PIT, BAA, ERA)
    """
    splits.sort(key=lambda x: x['date'], reverse=True)
    recent_7 = splits[:7]  # newest first — most recent game at the top

    rows = []
    for game in recent_7:
        s = game.get('stat', {})
        t = _team_abbrev(game.get('team', {}))
        o = _team_abbrev(game.get('opponent', {}))
        date_short = game.get('date', '')[5:]
        game_pk = game.get('game', {}).get('gamePk')
        lvl = game.get('minorLeagueLevel', '')

        home_away = "vs" if game.get('isHome') else "@"
        date_value = _savant_url(game_pk, date_short) if game_pk else date_short
        score_str  = (scores.get(game_pk, "") if scores and game_pk else "")

        rows.append({
            "Date":  date_value,
            "Lvl":   lvl,
            "Team":  t,
            "Opp":   f"{home_away} {o}",
            "Score": score_str,
            "GS":    s.get('gamesStarted', 0),
            "W":     s.get('wins', 0),
            "L":     s.get('losses', 0),
            "SV":    s.get('saves', 0),
            "BS":    s.get('blownSaves', 0),
            "HLD":   s.get('holds', 0),
            "IP":    s.get('inningsPitched', '0.0'),
            "H":     s.get('hits', 0),
            "R":     s.get('runs', 0),
            "ER":    s.get('earnedRuns', 0),
            "HR":    s.get('homeRuns', 0),
            "BB":    s.get('baseOnBalls', 0),
            "K":     s.get('strikeOuts', 0),
            "NP-S":  f"{s.get('numberOfPitches', 0)}-{s.get('strikes', 0)}",
            "BAA":   s.get('avg', '.000'),
            "ERA":   s.get('era', '0.00'),
        })

    games_df = pd.DataFrame(rows)

    s = season_stat if season_stat else {}

    ip = s.get('inningsPitched', '0.0')
    bf = s.get('battersFaced', 0)
    k  = s.get('strikeOuts', 0)
    bb = s.get('baseOnBalls', 0)
    hr = s.get('homeRuns', 0)
    go = s.get('groundOuts', 0) or 0
    ao = s.get('airOuts', 0) or 0

    # K/9, BB/9, HR/9 — API provides directly, but fall back to computed
    # values if a field is missing so the column never shows "0.00" by accident.
    k9  = s.get('strikeoutsPer9Inn') or _rate_per_9(k, ip)
    bb9 = s.get('walksPer9Inn')      or _rate_per_9(bb, ip)
    hr9 = s.get('homeRunsPer9')      or _rate_per_9(hr, ip)

    # K%-BB% — single percent-point gap, e.g. "18.4%"
    try:
        bf_f = float(bf)
        k_bb_pct = f"{((float(k) - float(bb)) / bf_f) * 100:.1f}%" if bf_f > 0 else '—'
    except (TypeError, ValueError):
        k_bb_pct = '—'

    # GB% and HR/FB are approximations. MLB Stats API exposes groundOuts and
    # airOuts (i.e. batted-ball *outs*), not full batted-ball types, so these
    # will drift from FanGraphs' GB/(GB+FB+LD) and HR/FB computed from true
    # batted-ball data.
    gb_pct = _pct(go, go + ao)
    hr_fb  = _pct(hr, ao)

    season_df = pd.DataFrame([{
        "GP-GS":  f"{s.get('gamesPlayed', 0)}-{s.get('gamesStarted', 0)}",
        "W-L":    f"{s.get('wins', 0)}-{s.get('losses', 0)}",
        "SV-BS":  f"{s.get('saves', 0)}-{s.get('blownSaves', 0)}",
        "IP":     ip,
        "QS":     s.get('qualityStarts', 0),
        "R":      s.get('runs', 0),
        "ER":     s.get('earnedRuns', 0),
        "BAA":    s.get('avg', '.000'),
        "K/9":    k9,
        "BB/9":   bb9,
        "HR/9":   hr9,
        "K%-BB%": k_bb_pct,
        "BABIP":  _compute_pitcher_babip(s),
        "LOB%":   _compute_lob_pct(s),
        "GB%":    gb_pct,
        "HR/FB":  hr_fb,
        "ERA":    s.get('era', '0.00'),
        "FIP":    _compute_fip(s),
    }])

    return season_df, games_df


def get_milb_stats(player_name: str, player_id: str = None) -> tuple:
    """
    Fetch MiLB game logs and season stats for a player.

    player_id: optional MLB Stats API player ID. If provided, skips the name
    search entirely — useful when two players share a name and the wrong one
    is returned by the search endpoint.

    Returns a 6-tuple:
        (season_df, games_df, current_level, team, age, position)

    Where:
        season_df     -- one-row season-totals DataFrame
        games_df      -- recent-games DataFrame
        current_level -- sport abbreviation of the player's most recent game
                         (e.g., "AAA", "AA", "A+", "A", "Rk")
        team          -- player's current team full name
        age           -- player's current age
        position      -- player's primary position abbreviation

    Returns None if the player cannot be found or has no 2026 stats.
    """
    if player_id:
        # Fetch full profile to determine position and collect team/age info
        try:
            url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req).read())
            person = data['people'][0]
            pos_code = person.get('primaryPosition', {}).get('code', '')
            p_info = {
                'id':         player_id,
                'is_pitcher': pos_code == '1',
                'team':       person.get('currentTeam', {}).get('name', 'UNK'),
                'age':        person.get('currentAge', 'UNK'),
                'position':   normalize_position(person.get('primaryPosition', {}).get('abbreviation', 'UNK')),
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
    SPORT_ID_TO_LEVEL = {
        11: "AAA",
        12: "AA",
        13: "A+",
        14: "A",
        15: "ROOKIE_BALL",
        16: "DSL",
        17: "VSL",
    }

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
            sid = futures[future]
            level = SPORT_ID_TO_LEVEL.get(sid, "UNK")
            res = future.result()
            if res and res.get('stats'):
                for stat_block in res['stats']:
                    if stat_block['type']['displayName'] == 'gameLog' and stat_block.get('splits'):
                        # Attach level to each game split so we know which minor league level it's from
                        for split in stat_block['splits']:
                            split['minorLeagueLevel'] = level
                        all_splits.extend(stat_block['splits'])
                    elif stat_block['type']['displayName'] == 'season' and stat_block.get('splits'):
                        new_stat = stat_block['splits'][0].get('stat', {})
                        if (new_stat.get('atBats', 0) > best_season_stat.get('atBats', 0)
                                or new_stat.get('inningsPitched', '0.0')
                                    > best_season_stat.get('inningsPitched', '0.0')):
                            best_season_stat = new_stat

    if not all_splits:
        return None

    # Determine the player's current level and team from their most recent game.
    # Do this before the format functions sort the list.
    all_splits.sort(key=lambda x: x['date'], reverse=True)
    current_level = all_splits[0].get('sport', {}).get('abbreviation', 'UNK')
    current_team_id = all_splits[0].get('team', {}).get('id')

    # Build a gamePk -> isHome map for all unique games.
    pk_home_map = {}
    for split in all_splits:
        pk = split.get('game', {}).get('gamePk')
        if pk:
            pk_home_map[pk] = split.get('isHome', False)

    # Fetch game scores and MLB parent org in parallel — two API calls,
    # run concurrently so neither has to wait on the other.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        scores_future  = executor.submit(fetch_game_scores, pk_home_map)
        org_future     = executor.submit(fetch_parent_org, current_team_id)
        scores = scores_future.result()
        team   = org_future.result()  # replaces whatever the profile returned

    if p_info['is_pitcher']:
        season_df, games_df = format_pitching_stats(all_splits, best_season_stat, scores)
    else:
        season_df, games_df = format_hitting_stats(all_splits, best_season_stat, scores)

    return season_df, games_df, current_level, team, age, position
