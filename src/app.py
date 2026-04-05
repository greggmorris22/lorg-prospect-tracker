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
st.markdown("Select a team to view the last 7 minor league game logs and 2026 Season stats YTD for all their prospects.")

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

# Column config shared by all stat tables. Renders the Date column as a
# clickable link to the Baseball Savant gamefeed. The URL has the short date
# embedded as &d=MM-DD so the regex can extract it for display. The Season
# aggregate row has an empty URL and renders as a blank cell.
STAT_COLUMN_CONFIG = {
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
                if "|" in entry:
                    player_name, player_id = entry.split("|", 1)
                else:
                    player_name = entry
                    player_id = PLAYER_ID_OVERRIDES.get(player_name)
                stats_df = get_milb_stats(player_name, player_id=player_id)
                return player_name, stats_df

            with st.spinner("Fetching watch list stats..."):
                with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [executor.submit(fetch_watchlist_player, e) for e in watchlist]
                    wl_results = [f.result() for f in concurrent.futures.as_completed(futures)]

            # Preserve original watchlist order
            wl_map = {name: df for name, df in wl_results}
            found_watchlist = False
            for entry in watchlist:
                player_name = entry.split("|")[0] if "|" in entry else entry
                stats_df = wl_map.get(player_name)
                if stats_df is not None and not stats_df.empty:
                    found_watchlist = True
                    st.subheader(player_name)
                    st.dataframe(stats_df, use_container_width=True, hide_index=True, column_config=STAT_COLUMN_CONFIG)

            st.success(f"Found {len(watchlist)} players on your watch list.")
            if not found_watchlist:
                st.info("No active MiLB game logs found for your watch list players.")

# --- Regular team view ---
else:
    prospects = teams_data[selected_team]

    if not prospects:
        st.warning(f"No players with 'prospect' status found on {selected_team}.")
        st.stop()

    def fetch_prospect(player_name):
        override_id = PLAYER_ID_OVERRIDES.get(player_name)
        stats_df = get_milb_stats(player_name, player_id=override_id)
        return player_name, stats_df

    with st.spinner(f"Fetching MiLB stats for {selected_team}..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(fetch_prospect, name) for name in prospects]
            team_results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Preserve original sorted order from fantrax_api
    results_map = {name: df for name, df in team_results}
    found_minors = False

    st.success(f"Found {len(prospects)} prospects on {selected_team}.")

    for player_name in prospects:
        stats_df = results_map.get(player_name)
        if stats_df is not None and not stats_df.empty:
            found_minors = True
            st.subheader(player_name)
            st.dataframe(stats_df, use_container_width=True, hide_index=True, column_config=STAT_COLUMN_CONFIG)

    if not found_minors:
        st.info("No active MiLB game logs found for the prospects on this team.")
