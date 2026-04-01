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

# Team Dropdown
team_names = sorted(list(teams_data.keys()))

# Default index logic if 'uncle ben's rice' exists
default_idx = 0
for i, name in enumerate(team_names):
    if 'uncle' in name.lower() and 'ben' in name.lower():
        default_idx = i
        break

selected_team = st.selectbox("Select Team:", options=team_names, index=default_idx)

# Auto-fetch on selection
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
