# Project Review: Fantasy Baseball Prospect Tracker

## What went wrong with Version 1:
1. **Aesthetics Failed:** I built a basic Streamlit app with raw HTML tables. It felt like a "dusty internal enterprise tool" rather than the "Premium Flat Design" modern SaaS feel required by the global rules.
2. **Poor UX for Authentication:** Asking a user to dig into Dev Tools to find a session cookie is terrible UX. 
3. **Data Overload:** Stacking 20+ tables vertically for a watchlist of prospects is visually overwhelming. 
4. **Ignored Core Rules:** I used `task.md` instead of `tasks/todo.md`, didn't follow the step-by-step verification, and settled for a hacky workaround (manual cookie entry) instead of a robust automated solution.

## Suggested Architectural Pivot
**Frontend:** Drop Streamlit. Build a **Next.js (React)** application using **Tailwind CSS**, **Lucide React** icons, and **Shadcn/UI**. This guarantees the premium, modern SaaS look with FedEx colors and native dark mode.
**Data Visualization:** Use a "Player Card" grid layout. Each card shows the player's headshot (via MLB API), their 2026 Season AVG/OPS, and expands into a beautifully styled table for their last 9 games when clicked.
**Backend/Fantrax Auth:** Create a Python API (FastAPI) that runs in the background. It uses **Playwright** to headlessly log into Fantrax once, grab the required cookies automatically, and sync the rosters behind the scenes. Zero manual copy-pasting required from the user.

## Review Steps Completed
- Evaluated UI/UX mismatch against User Global Rules.
- Researched MLB API headshot endpoints for better visual design.
- Formulated an automated Playwright strategy for the Fantrax roadblock.
