import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
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
# "Gregg's Watch List" is injected at the top as a first-class team option.
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
            st.success(f"Found {len(watchlist)} players on your watch list. Fetching MiLB logs...")
            found_watchlist = False
            for entry in watchlist:
                # Entries can be plain "Player Name" or "Player Name|mlb_id"
                # to pin a specific player when name search returns the wrong one.
                if "|" in entry:
                    player_name, player_id = entry.split("|", 1)
                else:
                    player_name, player_id = entry, None
                with st.spinner(f"Pulling MiLB stats for {player_name}..."):
                    stats_df = get_milb_stats(player_name, player_id=player_id)
                if stats_df is not None and not stats_df.empty:
                    found_watchlist = True
                    st.subheader(player_name)
                    st.dataframe(stats_df, use_container_width=True, hide_index=True)
            if not found_watchlist:
                st.info("No active MiLB game logs found for your watch list players.")

# --- Regular team view ---
else:
    prospects = teams_data[selected_team]

    if not prospects:
        st.warning(f"No players with 'prospect' status found on {selected_team}.")
        st.stop()

    st.success(f"Found {len(prospects)} prospects on {selected_team}. Fetching MiLB Logs...")

    found_minors = False

    for player_name in prospects:
        with st.spinner(f"Pulling MiLB stats for {player_name}..."):
            stats_df = get_milb_stats(player_name)

        if stats_df is not None and not stats_df.empty:
            found_minors = True
            st.subheader(player_name)
            st.dataframe(stats_df, use_container_width=True, hide_index=True)

    if not found_minors:
        st.info("No active MiLB game logs found for the prospects on this team.")
