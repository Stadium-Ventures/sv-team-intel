# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`sv-teamintel` is a single-page dashboard that aggregates "TeamIntel" Slack messages about Stadium Ventures' 2026 MLB draft clients into a player × team interest matrix. It runs as a scheduled GitHub Actions job that produces a static `public/index.html` deployed via Vercel; user edits made in the dashboard write to a Redis (Upstash) KV store via Vercel serverless functions and are merged back in on the next build.

## Pipeline

```
GitHub Actions (hourly cron)
  └── python fetch_and_build.py
       ├── fetch_messages()         # Slack: configured channels + threads, filtered by "teamintel" keyword
       │                            #        (2026-draft-general is unfiltered — keyword often omitted there)
       ├── parse_messages()         # extract (player, team, date, score, color, attendee_tier, workout, workout_dates)
       ├── load_manual_records()    # Redis key `manual_records` — matrix "+ Add Entry" rows (same shape as Slack)
       ├── fetch_game_schedule()    # read-only Google Sheet CSV → games filtered to roster
       ├── build_html()             # all matrix/calendar/detail UI — single 4900-line render
       ├── load_kv_overrides()      # Redis key `score_overrides` — score/PDW/tier/color/team-reassign edits
       └── apply_overrides()        # merged ONLY into teamintel.json, not the HTML
                                    #   (HTML applies overrides client-side via /api/overrides)

Outputs:  public/index.html  (dashboard, password-gated)
          public/teamintel.json  (downstream consumer: sv-draft-fit-workout)
```

The workflow commits both files back to `main` each run (commit message `Auto-update TeamIntel dashboard …`).

## Commands

```bash
# Full local build (writes public/index.html and public/teamintel.json)
SLACK_BOT_TOKEN=xoxb-… REDIS_URL=redis://… python fetch_and_build.py
# .env is also read for SLACK_BOT_TOKEN; REDIS_URL is optional locally (overrides + manual_records skipped)

# Dry-run validate workout-date parser against the latest teamintel.json
python parse_workout_dates.py

# One-off: backfill workout_dates onto every record in public/teamintel.json
# (use when you change extract_workout_dates and want immediate UI without a full rebuild)
python backfill_workout_dates.py

# Trigger the scheduled job manually
gh workflow run update-dashboard.yml
```

There is no test suite, linter, or build step — `vercel.json` sets `outputDirectory: public` with an empty `buildCommand`. `package.json` only declares `ioredis` for the serverless functions.

## Architecture notes that aren't obvious from the code

**`fetch_and_build.py` is the entire backend.** ~4900 lines, four phases marked by `# --- STEP N` banners. `build_html` is one giant function that emits HTML + inline CSS + inline JS as a single string; the dashboard is fully client-rendered from a `RECORDS` JSON blob embedded in the page. There is no separate JS source — search inside the f-strings of `build_html` for client-side logic.

**`parse_and_build.py` is legacy** (gitignored, references an absolute path to a different repo). Don't touch it. `dashboard.html` is also legacy/gitignored — the live artifact is `public/index.html`.

**Two parallel data sources, merged at build time:**
- Slack messages → Slack-parsed records (`channel != None`)
- Redis `manual_records` → manual records (`is_manual: True`, `channel: None`) — these are shaped identically so matrix/detail/calendar rendering needs no special-casing.

**Score model is layered.** `score_line_for_team` derives sentiment from explicit color words and keywords. `_attach_tier` then enforces a "tier floor": when an attendee tier is detected (T1 GM / T2 Dir / T3 NXC / T4 X / T5 Area), the record's score is bumped up to the tier's `TIER_MULTIPLIERS` value — unless sentiment was already negative (negative always wins). Default tier when nothing detected is **T5** (the team being on file at all implies an area scout was watching). Original sentiment is preserved as `raw_score`.

**Matrix cell color ≠ score.** Cell color comes from `detect_color_word` (literal "red"/"orange"/"yellow"/"light green"/"green" in the message). Most-recent record per (player, team) wins. Score drives ranking and sorting, not cell color.

**Workout flag has two regex tiers.** `_WORKOUT_BROAD_PATTERNS` (PDW, "private workout", etc.) fire workspace-wide. `_WORKOUT_TARGETED_PATTERNS` ("wants Bo to workout", team-name-near-"workout") only fire when a player alias appears in the same sentence. In single-player Slack channels (`CHANNEL_TO_PLAYER`), targeted patterns auto-match because the channel itself scopes the player. This avoids blanket-flagging every player named in a "BAL ... Workout" group post.

**Workout-date parsing is window-bounded.** `extract_workout_dates` only emits dates between `WORKOUT_WINDOW_START` and `WORKOUT_WINDOW_END` (the `# --- DRAFT CYCLE CONFIG ---` block near the top of `fetch_and_build.py`; currently `2026-04-01..2026-07-13`). Multi-format aware: `June 11 - Atlanta`, `May 18th Columbia, SC 9am`, `Location: Pirate City complex`, comma-separated lists, etc. Returns `{team_abbrev: [{date, time, location, tentative}]}`. `_wd_first_team` decides which team the parsed events belong to when the message has multiple team headers.

**Team-detection guards.** `find_teams_in_line` skips `ATL` when the line contains "Metro Atl" or "Atl." (location, not team), and skips 2-letter abbrevs preceded by `, ` (state codes — `Tampa, FL` is not MIA). Per memory, downstream consumers should trust the MLB API's `currentTeam` over sheet/affiliate data.

**Players have alias maps.** `PLAYER_ALIASES` lets short forms ("cam", "trev", "bo", "taj", "phinn") resolve back to canonical names. `_build_alias_lookup` is the lower-cased version used to match the game-schedule CSV's "Client" column to roster names.

**`data/front_office_2026.csv`** (path built from the `FRONT_OFFICE_CSV` config constant) is loaded once per build to map mentioned names → tiers (e.g. naming a team's GM in a TeamIntel line bumps that record to T1). `_ORG_ROLE_TIER` maps CSV columns to tier numbers. `data/team_draft_2026.csv` (`TEAM_DRAFT_CSV`) is bonus-pool/picks data shown in the calendar's team-info popover.

## Vercel API (`api/*.js`)

Three Node serverless handlers, all CORS-open, all backed by Upstash Redis (`REDIS_URL`):

- `api/overrides.js` — `score_overrides` blob, multi-namespace keys:
  - `player|team|date` → score (`-2..2` or `"NA"` for exclusion)
  - `w|player|team` → bool (PDW flag toggle)
  - `t|player|team|date` → int 0..5 (manual tier override)
  - `c|player|team` → color word (manual cell-color override)
  - `mt|player|orig_team|date` → 'NEW' (team reassignment)
  - `?meta=1` returns per-key `updated_at` timestamps for the Edits view.
- `api/manual-records.js` — `manual_records` blob: matrix `+ Add Entry` rows with optional `workout_dates`.
- `api/calendar-events.js` — `calendar_events` blob: ad-hoc workout/playoff/travel/other events the user adds in the calendar UI.

The dashboard reads/writes these directly from the browser. The next `fetch_and_build.py` run reads them from Redis and merges them into the static outputs.

## Draft-cycle activation (reactivate / shutter)

This repo tracks one draft cycle at a time. Between cycles it should sit **shuttered** — no scheduled builds, no Vercel redeploys — until the next draft's live window opens.

**Shuttered is the resting state.** `.github/workflows/update-dashboard.yml`'s "Cadence gate" step has an `ACTIVE` flag. `ACTIVE=false` skips every scheduled tick — manual `workflow_dispatch` still always builds, for one-off checks. Set it back to `false` as soon as a cycle's draft ends.

**To reactivate for a new draft cycle (e.g. 2027):**
1. In `.github/workflows/update-dashboard.yml`, flip `ACTIVE=true` and update `PUSH_END` to that cycle's push-window end date (fast 24/7 builds run until then; it then auto-reverts to hourly-daytime).
2. In `fetch_and_build.py`, update the `# --- DRAFT CYCLE CONFIG ---` block near the top: `DRAFT_YEAR`, `DRAFT_DATES`, `COMBINE_WINDOW_START`/`END`, `WORKOUT_WINDOW_START`/`END`, `CALENDAR_PICKER_MIN`/`MAX`. The `*_CSV`/`*_JSON` filename constants (`FRONT_OFFICE_CSV`, `TEAM_DRAFT_CSV`, `FARM_SYSTEM_CSV`, `RECOMMENDED_SCHEDULE_JSON`) derive from `DRAFT_YEAR` automatically — just make sure matching files exist under `data/` (`front_office_<year>.csv`, `team_draft_<year>.csv`, `farm_system_<year>.csv`, `recommended_schedule_<year>.json`).
3. Replace the roster: `PLAYERS_2026`, `CHANNEL_TO_PLAYER`, `CHANNELS`, `PLAYER_ALIASES` (see "Roster updates" below). These keep their `_2026`-suffixed names by design — renaming them is a large mechanical ripple through the file for no functional gain; just replace their *contents* each cycle.
4. Replace the special-pick-tags / draft-board data block (search for "MLB draft): overall pick # -> label" — the full slotted-pick table) with the new year's draft order. This is wholesale year-specific data the config block doesn't (and shouldn't try to) parameterize.
5. Rotate the `DASHBOARD_PASSWORD` GitHub secret if it should change for the new cycle.
6. Run `gh workflow run update-dashboard.yml` once to confirm a manual build still produces sane output before relying on the schedule.

**To pull it back down (shutter) once that cycle's draft ends:** flip `ACTIVE` back to `false` in the workflow. That's the only required change — the yearly config values can stay in place untouched until the next reactivation.

## Roster updates

A new client requires updates in three places in `fetch_and_build.py`:
1. `PLAYERS_2026` (last-name → full name)
2. `CHANNEL_TO_PLAYER` and `CHANNELS` (Slack channel name → player + channel ID)
3. `PLAYER_ALIASES` if the player goes by a non-obvious nickname

Forgetting any of these will cause silent data loss (records dropped, single-player-channel scoping broken, or workout-targeted patterns failing to match).

## Health check + #sv-automation ops alerts

**Where it lives:** `.github/workflows/health-check.yml` runs `scripts/health_check.py` daily at 11:23 UTC (~7:23am ET). Manual run: `gh workflow run health-check.yml` (add `-f test=true` to send a clearly-labeled test post instead of running checks).

**What it monitors:** dashboard page up (`sv-teamintel.vercel.app`), overrides API end-to-end (Vercel function → Upstash), Redis reachable from CI (`REDIS_URL` secret), Slack bot token valid (`auth.test`), and — only when the build cadence is live (`ACTIVE=true` in `update-dashboard.yml`) — that a successful build ran in the last 26h, plus an ACTIVE-flag/disabled-workflow mismatch check. **Cycle-aware:** while shuttered between drafts, "no recent builds" is expected and never alerts.

**#sv-automation scope + message contract** (channel `C0BE0ELP92Q`, webhook secret `SV_AUTOMATION_WEBHOOK_URL` — value from Tom Trudeau, never hardcode/commit it):
- #sv-automation is for bugs, failures, and health findings ONLY. Feature output (the dashboard itself, intel digests) stays on product surfaces — never move it there, and never leave ops noise on product channels.
- Every post must lead with the product label `SV TeamIntel (sv-team-intel) — …`, tag each finding `🛠️ Code change` vs `👤 Manual`, and read as three plain-English lines: **What broke / How we know / What to do**. No internal thresholds or dev jargon.
- Health checks are **silent when healthy** — no "all good" posts.
- ALL posts go through `scripts/sv_automation_notify.py` (`post_findings`) so the label + contract live in one place. Never add a second webhook path.

## SV Internal Hub registry

This app is registered at https://sv-internal-hub.vercel.app/apps/sv-teamintel.
Whenever a change in this session adds, removes, or alters any of the following, update `sv-app.json` at the repo root **in the same session** — don't leave it for later:
- scheduled jobs / crons (including flipping the `ACTIVE` cadence flag for a new draft cycle)
- data sources in or destinations out (Slack channels, sheets, Redis keys, downstream consumers)
- hosting, deployment, or access/auth
- monitoring or known issues
- ownership or who uses it

Also update the `runbook` steps if the local-dev or deploy process changed. The hub reads `sv-app.json` hourly and merges it over `registry/sv-teamintel.json` in `Stadium-Ventures/sv-internal-hub`.

## 🧭 The SV Way — North Star doctrine (read this first, every session)

THE-SV-WAY.md in Stadium-Ventures/sv-registry (served live at
https://sv-internal-hub.vercel.app/sv-way.md) is the North Star every Stadium
Ventures tool and every chat working on one routes through — read it at
session start, before anything else. Non-negotiables even before you read it:
every player fact resolves to the player's file in sv-registry and every
surface is a projection of it; nothing unvalidated projects (flag it, file a
candidate, never overwrite a stable field); one write door (write-registry
chokepoint / governed writers); one write-home per dataset; firm work is
first-class but becomes a player fact only when it actualizes through that one
door; systems doing work about a player resolve them against canon first (read
duty); automation is silent when healthy and posts actionable-only to
#sv-automation; collaborative tools live in Stadium-Ventures org repos; locked
client-facing artifacts (Report Packets) are never moved or regenerated. This
tool's hub registration + #sv-automation hookup are canonical requirements of
being "promoted." When your work decides something reusable, capture it
(status slice → SOP → canon) before you finish.
