# Fantasy Baseball Prospect Tracker Plan

## Phase 1: Planning & Architecture (Current)
- [x] Review V1 failures and document in `project_review.md`.
- [ ] Interview user regarding UI preferences, Fantrax login automation, and app framework.
- [ ] Finalize tech stack based on user feedback.

## Phase 2: Backend & Automation
- [ ] Implement Playwright auto-login script for Fantrax.
- [ ] Create FastAPI or lightweight backend to serve MiLB stats (with player headshots) and Fantrax rosters.

## Phase 3: Premium Frontend
- [ ] Scaffold Next.js (or designated framework) app with Tailwind CSS and Shadcn/UI.
- [ ] Implement FedEx color theme (`#4D148C`, `#FF6600`) and modern typography.
- [ ] Build interactive Player Cards (Season overview).
- [ ] Build expanding detail view (Last 9 games data table).

## Phase 4: Review & Deploy
- [ ] Write `run.bat` for one-click startup (starts backend + frontend).
- [ ] Final user testing and UI polish.
