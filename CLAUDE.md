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

**Workout-date parsing is window-bounded.** `extract_workout_dates` only emits dates in `2026-04-01..2026-07-13` (the pre-draft window). Multi-format aware: `June 11 - Atlanta`, `May 18th Columbia, SC 9am`, `Location: Pirate City complex`, comma-separated lists, etc. Returns `{team_abbrev: [{date, time, location, tentative}]}`. `_wd_first_team` decides which team the parsed events belong to when the message has multiple team headers.

**Team-detection guards.** `find_teams_in_line` skips `ATL` when the line contains "Metro Atl" or "Atl." (location, not team), and skips 2-letter abbrevs preceded by `, ` (state codes — `Tampa, FL` is not MIA). Per memory, downstream consumers should trust the MLB API's `currentTeam` over sheet/affiliate data.

**Players have alias maps.** `PLAYER_ALIASES` lets short forms ("cam", "trev", "bo", "taj", "phinn") resolve back to canonical names. `_build_alias_lookup` is the lower-cased version used to match the game-schedule CSV's "Client" column to roster names.

**`data/front_office_2026.csv`** is loaded once per build to map mentioned names → tiers (e.g. naming a team's GM in a TeamIntel line bumps that record to T1). `_ORG_ROLE_TIER` maps CSV columns to tier numbers. `data/team_draft_2026.csv` is bonus-pool/picks data shown in the calendar's team-info popover.

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

## Roster updates

A new client requires updates in three places in `fetch_and_build.py`:
1. `PLAYERS_2026` (last-name → full name)
2. `CHANNEL_TO_PLAYER` and `CHANNELS` (Slack channel name → player + channel ID)
3. `PLAYER_ALIASES` if the player goes by a non-obvious nickname

Forgetting any of these will cause silent data loss (records dropped, single-player-channel scoping broken, or workout-targeted patterns failing to match).
