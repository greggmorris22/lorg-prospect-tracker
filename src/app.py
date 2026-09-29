import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import base64
import html
from pathlib import Path

import streamlit as st
import concurrent.futures
import pandas as pd
from data.fantrax_api import fetch_league_teams
from data.milb_api import get_milb_stats

st.set_page_config(page_title="LORG Prospect Tracker", layout="wide")

# Hide the chain-link icon Streamlit adds to every heading on hover (a link to
# that heading's own anchor). It duplicates nothing useful here and crowds the
# MiLB.com / Prospect Savant logo links next to each player name.
st.markdown(
    "<style>[data-testid='stHeaderActionElements'] {display: none;}</style>",
    unsafe_allow_html=True,
)

st.title("LORG Prospect Tracker")
st.markdown(
    "Select a team to view the last 7 minor league game logs and 2026 season stats YTD for all their prospects. "
    "Game logs include Arizona Fall League games (AFL) and postseason games, marked (PS); "
    "season stats are regular season only."
)

@st.cache_data(ttl=3600)  # Cache for an hour to avoid spamming the endpoint
def load_teams(league_id):
    return fetch_league_teams(league_id)

@st.cache_data(ttl=900, show_spinner=False)  # 15 min: games only finish a few times a day
def load_player_stats(player_name, player_id, org, level):
    """
    Cached get_milb_stats. Without this every rerun (any dropdown change)
    re-downloads ~10 API responses per player; with it, revisiting a team is
    instant. Arguments are the cache key, so they must be plain values.
    """
    return get_milb_stats(player_name, player_id=player_id, org=org, level=level)

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

# MiLB.com player pages also resolve from the bare MLBAM ID
# (e.g. https://www.milb.com/player/823787), so no name slug is needed.
MILB_URL_TEMPLATE = "https://www.milb.com/player/{mlbam_id}"

def _logo_data_uri(filename: str) -> str:
    """
    Read a logo from src/assets and return it as an inline data URI, so the
    header can show it as a plain <img> without depending on another site
    hosting the image.
    """
    data = (Path(__file__).parent / "assets" / filename).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")

# Logos shown next to each player name as link targets. The Savant logo is
# transparent with a black outline, so it gets a white circular backing to
# stay visible on dark themes.
MILB_LOGO = _logo_data_uri("milb.png")
SAVANT_LOGO = _logo_data_uri("prospect_savant.png")
LOGO_STYLE = "height:22px;vertical-align:middle;margin-left:10px;"
SAVANT_LOGO_STYLE = LOGO_STYLE + "background:#fff;border-radius:50%;"

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

# Team selector — a dropdown so the 13 options don't stack down the page.
# (This was a st.radio to avoid st.selectbox's focusable <input>, which can
# raise the iOS soft keyboard; if that comes back on iPhone, switch to
# st.pills or st.radio(horizontal=True).)
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

selected_team = st.selectbox("Select Team:", options=team_names, index=default_idx)


def render_player(player_name: str, result: tuple):
    """
    Render one player's stat block: header line, 2026 Stats table,
    Recent Games table, and a divider.

    result is the 7-tuple returned by get_milb_stats:
        (season_df, games_df, current_level, team, age, position, mlbam_id)

    The header carries two separate logo links: the player's MiLB.com page and
    their Prospect Savant page, both keyed by the MLBAM ID the stats come from.
    """
    season_df, games_df, current_level, team, age, position, mlbam_id = result

    # Escaped because the header is rendered as HTML and the name comes from
    # an outside feed.
    header = html.escape(f"{player_name} | {position} | {current_level}")
    if mlbam_id:
        milb_url = MILB_URL_TEMPLATE.format(mlbam_id=mlbam_id)
        savant_url = SAVANT_URL_TEMPLATE.format(mlbam_id=mlbam_id)
        header += (
            f'<a href="{milb_url}" target="_blank" rel="noopener noreferrer" title="MiLB.com player page">'
            f'<img src="{MILB_LOGO}" alt="MiLB.com" style="{LOGO_STYLE}"></a>'
            f'<a href="{savant_url}" target="_blank" rel="noopener noreferrer" title="Prospect Savant player page">'
            f'<img src="{SAVANT_LOGO}" alt="Prospect Savant" style="{SAVANT_LOGO_STYLE}"></a>'
        )
    # A markdown h3 (same look as st.subheader) so the logos can be inline HTML.
    st.markdown(f"### {header}", unsafe_allow_html=True)
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
                result = load_player_stats(player_name, player_id, None, None)
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
        result = load_player_stats(
            player_name,
            override_id,
            prospect.get('org'),
            prospect.get('level'),
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
