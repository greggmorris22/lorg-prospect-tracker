library(baseballr)
library(dplyr)

# Step 1: Find Mississippi State's NCAA team_id
schools <- ncaa_school_id_lu()

msu <- schools |>
  filter(grepl("Mississippi St", school, ignore.case = TRUE))

print(msu)  # Inspect to confirm the right row / division

msu_team_id <- msu$school_id[1]

# Step 2: Pull the 2026 schedule
msu_schedule_raw <- ncaa_schedule_info(
  team_id = msu_team_id,
  year    = 2026
)

# Inspect available columns in case names differ across package versions
glimpse(msu_schedule_raw)

# Step 3: Build a clean tibble
msu_schedule_tbl <- msu_schedule_raw |>
  as_tibble() |>
  mutate(
    home_away = case_when(
      home_team == "Mississippi St." ~ "Home",
      away_team == "Mississippi St." ~ "Away",
      TRUE                           ~ "Neutral"
    )
  ) |>
  select(
    date,
    home_away,
    opponent  = away_team,   # away_team when MSU is home; adjust as needed
    home_team,
    score,
    outcome,
    location
  ) |>
  arrange(date)

print(msu_schedule_tbl, n = Inf)
