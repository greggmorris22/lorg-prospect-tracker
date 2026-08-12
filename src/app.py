import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import concurrent.futures
import pandas as pd
from data.fantrax_api import fetch_league_teams
from data.milb_api import get_milb_stats

st.set_page_config(page_title="LORG Prospect Tracker", layout="wide")

st.title("LORG Prospect Tracker")
st.markdown("Select a team to view the last 7 minor league game logs and 2026 season stats YTD for all their prospects.")

@st.cache_data(ttl=3600)  # Cache for an hour to avoid spamming the endpoint
def load_teams(league_id):
    return fetch_league_teams(league_id)

league_id = "eofqrg7umiyswern"

# Player ID overrides: maps a player's display name to a specific MLB Stats API
# player ID. Used when the name search returns the wrong player (e.g. two active
# players share the same name). Set in Streamlit secrets as:
#   [player_id_overrides]
#   "Esteban Mejia" = "821757"
PLAYER_ID_OVERRIDES = st.secrets.get("player_id_overrides", {})

# Prospect Savant player pages are keyed by MLBAM ID — the same ID the MLB
# Stats API uses — so the link needs no extra lookup.
SAVANT_URL_TEMPLATE = "https://prospectsavant.com/player/{mlbam_id}"

# Material Symbols icon rendered next to each player name as the link target.
# Streamlit expands ":material/<name>:" in markdown into an inline icon.
SAVANT_ICON = ":material/open_in_new:"

# Column config applied only to Recent Games tables. Renders the Date column
# as a clickable link to the Baseball Savant gamefeed. The URL has the short
# date embedded as &d=MM-DD so the regex can extract it for display.
GAMES_COLUMN_CONFIG = {
    "Date": st.column_config.LinkColumn(
        "Date",
        display_text=r"d=(\d{2}-\d{2})"
    )
}

with st.spinner("Loading league teams..."):
    try:
        teams_data = load_teams(league_id)
    except Exception as e:
        st.error(f"Error loading league data: {e}")
        st.stop()

if not teams_data:
    st.error("No teams were found in the league.")
    st.stop()

# Team selector — uses st.radio instead of st.selectbox so that no text
# input is rendered. st.selectbox puts a focusable <input> on screen which
# triggers the iOS soft keyboard; radio buttons are pure tap targets with
# no keyboard involvement on any device.
#
# "Gregg's Watch List" is injected at the end as a first-class team option.
# It prompts for a password before revealing any player names.
WATCHLIST_LABEL = "Gregg's Watch List"
team_names = sorted(list(teams_data.keys())) + [WATCHLIST_LABEL]

# Default to "Uncle Ben's Rice" if it exists in the league, otherwise first team.
default_idx = 0
for i, name in enumerate(team_names):
    if 'uncle' in name.lower() and 'ben' in name.lower():
        default_idx = i
        break

selected_team = st.radio("Select Team:", options=team_names, index=default_idx)


def render_player(player_name: str, result: tuple):
    """
    Render one player's stat block: header line, 2026 Stats table,
    Recent Games table, and a divider.

    result is the 7-tuple returned by get_milb_stats:
        (season_df, games_df, current_level, team, age, position, mlbam_id)

    The header carries a link icon to the player's Prospect Savant page, which
    is keyed by the same MLBAM ID the stats come from.
    """
    season_df, games_df, current_level, team, age, position, mlbam_id = result

    header = f"{player_name} | {position} | {current_level}"
    if mlbam_id:
        header += f" [{SAVANT_ICON}]({SAVANT_URL_TEMPLATE.format(mlbam_id=mlbam_id)})"
    st.subheader(header)
    st.caption(f"{team} | Age {age}")

    st.markdown("**2026 Stats**")
    st.dataframe(season_df, use_container_width=True, hide_index=True)

    if games_df is not None and not games_df.empty:
        st.markdown("**Recent Games**")
        st.dataframe(
            games_df,
            use_container_width=True,
            hide_index=True,
            column_config=GAMES_COLUMN_CONFIG,
        )

    st.divider()


# --- Gregg's Watch List (password-protected) ---
if selected_team == WATCHLIST_LABEL:
    if not st.session_state.get("watchlist_unlocked"):
        pwd = st.text_input("Enter password to view watch list:", type="password", key="watchlist_pwd")
        if pwd:
            if pwd == st.secrets.get("watchlist_password", ""):
                st.session_state["watchlist_unlocked"] = True
                st.rerun()
            else:
                st.error("Nice try lol")
    else:
        watchlist = st.secrets.get("watchlist_players", [])
        if not watchlist:
            st.info("No players on your watch list yet.")
        else:
            def fetch_watchlist_player(entry):
                """Fetch stats for one watch list entry (name or name|id)."""
                if "|" in entry:
                    player_name, player_id = entry.split("|", 1)
                else:
                    player_name = entry
                    player_id = PLAYER_ID_OVERRIDES.get(player_name)
                result = get_milb_stats(player_name, player_id=player_id)
                return player_name, result

            with st.spinner("Fetching watch list stats..."):
                with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [executor.submit(fetch_watchlist_player, e) for e in watchlist]
                    wl_results = [f.result() for f in concurrent.futures.as_completed(futures)]

            # Preserve original watchlist order
            wl_map = {name: result for name, result in wl_results}
            wl_names = [
                entry.split("|")[0] if "|" in entry else entry
                for entry in watchlist
            ]
            wl_rendered = [n for n in wl_names if wl_map.get(n) is not None]
            found_watchlist = bool(wl_rendered)

            for player_name in wl_rendered:
                render_player(player_name, wl_map[player_name])

            st.success(f"Found {len(wl_rendered)} players on your watch list.")
            if not found_watchlist:
                st.info("No active MiLB game logs found for your watch list players.")

# --- Regular team view ---
else:
    prospects = teams_data[selected_team]

    if not prospects:
        st.warning(f"No players with 'prospect' status found on {selected_team}.")
        st.stop()

    def fetch_prospect(prospect: dict):
        """
        Fetch stats for one prospect record from fantrax_api.

        A manual ID override wins if one is configured; otherwise the player's
        org and level are passed as hints so the name search picks the right
        person when several share a name.
        """
        player_name = prospect['name']
        override_id = PLAYER_ID_OVERRIDES.get(player_name)
        result = get_milb_stats(
            player_name,
            player_id=override_id,
            org=prospect.get('org'),
            level=prospect.get('level'),
        )
        return player_name, result

    with st.spinner(f"Fetching MiLB stats for {selected_team}..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(fetch_prospect, p) for p in prospects]
            team_results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Preserve the original sorted order from fantrax_api (pos then level)
    results_map = {name: result for name, result in team_results}
    rendered = [p for p in prospects if results_map.get(p['name']) is not None]

    st.success(f"Found {len(rendered)} prospects on {selected_team}.")

    for prospect in rendered:
        render_player(prospect['name'], results_map[prospect['name']])

    found_minors = bool(rendered)

    if not found_minors:
        st.info("No active MiLB game logs found for the prospects on this team.")
