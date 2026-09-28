"""Where fetch_and_build.py gets its draft-client ROSTER from.

ROSTER_SOURCE=hardcoded  (default) the roster dicts written in fetch_and_build.py
                         (PLAYERS_2026 / CHANNEL_TO_PLAYER / CHANNELS). `sheet`
                         is accepted as an alias, so the org-wide rollback value
                         from sv-registry's roster cutover kit works here too.
ROSTER_SOURCE=registry   sv-registry's authenticated roster projection door,
                         GET https://sv-registry.vercel.app/api/roster-projection

Same pattern as the kitted readers (sv-scouting-data ingest/roster_source.py):

* The registry path FAILS CLOSED. A missing token, a 401/403, a non-JSON body,
  a body that does not assert contains_no_contact_data, a row without a slug,
  duplicate slugs, fewer rows than ROSTER_MIN_ROWS, an empty draft class, or
  two draft-class players sharing a last-name key all raise. There is never a
  silent fallback to the hard-coded roster: rollback is a config change
  (ROSTER_SOURCE=hardcoded, or delete the variable).
* Membership comes from canon only. The draft cycle's roster is every row whose
  `draft_class` equals DRAFT_YEAR, minus `is_client: false` and coaches. Former
  clients are already excluded by the door. Names and Slack channels (id +
  name) come from the same rows, so a new client needs a registry dossier, not
  an edit here. Nicknames are NOT used: fetch_and_build.py embeds
  its alias map in the committed public/index.html of this public repo, so only
  names and Slack channels (already in this repo today) are taken.
* Dual run: with ROSTER_SOURCE=hardcoded and SV_REGISTRY_ROSTER_TOKEN set,
  fetch_and_build.py prints one `[dual-run]` line comparing the two rosters.
  It never changes the build and never fails it.

This repo is PUBLIC. The token is a platform secret only (a GitHub Actions
encrypted secret), never committed and never baked into public/index.html.

Env:
  ROSTER_SOURCE              hardcoded | registry   (default hardcoded; `sheet` = hardcoded)
  SV_REGISTRY_ROSTER_TOKEN   svt_ service token scoped read:roster-projection
  ROSTER_PROJECTION_URL      override the door URL (default: production)
  ROSTER_MIN_ROWS            fail-closed floor for the whole projection (default 50; ~100 today)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_PROJECTION_URL = "https://sv-registry.vercel.app/api/roster-projection"
DEFAULT_MIN_ROWS = 50
SOURCES = ("hardcoded", "registry")
_ALIASES = {"sheet": "hardcoded", "": "hardcoded"}
# Name suffixes skipped when deriving the last-name key PLAYERS_2026 is keyed by.
_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


class RosterProjectionError(RuntimeError):
    """The registry roster could not be trusted. Never caught to fall back."""


def roster_source() -> str:
    raw = (os.environ.get("ROSTER_SOURCE") or "").strip().lower()
    src = _ALIASES.get(raw, raw)
    if src not in SOURCES:
        raise RosterProjectionError(
            f"ROSTER_SOURCE must be one of {SOURCES} (or 'sheet'), got {raw!r}")
    return src


def fetch_projection(url: str | None = None, token: str | None = None,
                     min_rows: int | None = None, opener=None,
                     log: bool = True) -> tuple[dict, list[dict]]:
    """GET the projection. Returns (_meta, rows). Raises RosterProjectionError."""
    url = url or os.environ.get("ROSTER_PROJECTION_URL") or DEFAULT_PROJECTION_URL
    token = token if token is not None else os.environ.get("SV_REGISTRY_ROSTER_TOKEN", "")
    if min_rows is None:
        min_rows = int(os.environ.get("ROSTER_MIN_ROWS") or DEFAULT_MIN_ROWS)
    if not token.strip():
        raise RosterProjectionError(
            "ROSTER_SOURCE=registry but SV_REGISTRY_ROSTER_TOKEN is not set. Refusing to "
            "build on a guessed roster (set the secret, or set ROSTER_SOURCE=hardcoded to roll back).")

    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token.strip()}", "Accept": "application/json"})
    try:
        with opener(req, timeout=30) as resp:
            body = resp.read()
            generated_hdr = resp.headers.get("X-Roster-Generated-At") if resp.headers else None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RosterProjectionError("Registry rejected the roster token (401). The token is "
                                        "missing, mistyped or revoked, so re-mint it.") from e
        if e.code == 403:
            raise RosterProjectionError("Registry token is valid but not scoped for "
                                        "read:roster-projection (403). This needs a mint, not a retry.") from e
        raise RosterProjectionError(f"Roster projection request failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RosterProjectionError(f"Roster projection unreachable: {e.reason}") from e

    try:
        data = json.loads(body)
    except ValueError as e:
        raise RosterProjectionError(f"Roster projection body is not JSON: {e}") from e
    meta, rows = (data or {}).get("_meta"), (data or {}).get("rows")
    if not isinstance(meta, dict) or not isinstance(rows, list):
        raise RosterProjectionError("Roster projection is missing _meta or rows.")
    if meta.get("contains_no_contact_data") is not True:
        raise RosterProjectionError("Roster projection does not assert contains_no_contact_data. "
                                    "Refusing to use it.")
    if len(rows) < min_rows:
        raise RosterProjectionError(f"Roster projection has {len(rows)} rows, below the "
                                    f"fail-closed floor of {min_rows}. Refusing to proceed.")
    slugs = [str(p.get("slug") or "").strip() for p in rows if isinstance(p, dict)]
    if len(slugs) != len(rows) or not all(slugs):
        raise RosterProjectionError("Roster projection has a row without a slug.")
    if len(set(slugs)) != len(slugs):
        raise RosterProjectionError("Roster projection has duplicate slugs.")

    generated = meta.get("generated_at") or generated_hdr or "unknown"
    meta.setdefault("generated_at", generated)
    if log:
        print(f"[roster] source=registry rows={len(rows)} generated_at={generated}")
    return meta, rows


def _last_name_key(name: str) -> str:
    parts = [p for p in name.lower().split() if p]
    while len(parts) > 1 and parts[-1] in _SUFFIXES:
        parts.pop()
    return parts[-1] if parts else ""


def _draft_class(p: dict):
    v = p.get("draft_class")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def draft_class_rows(rows: list[dict], draft_year: int) -> list[dict]:
    """The draft cycle's clients: draft_class == draft_year, not former, not coaches."""
    out = []
    for p in rows:
        if p.get("is_client") is False or p.get("is_coach") is True:
            continue
        if _draft_class(p) == int(draft_year):
            out.append(p)
    return sorted(out, key=lambda p: p["slug"])


def build_roster(rows: list[dict], draft_year: int) -> dict:
    """Projection rows -> the shapes fetch_and_build.py uses.

    Returns {"players": {last_lc: full_name}, "channel_to_player": {channel_name: full_name},
             "channels": [(channel_name, channel_id)],
             "slugs": [...], "members": [(slug, name), ...]}.
    """
    members = draft_class_rows(rows, draft_year)
    if not members:
        raise RosterProjectionError(
            f"Roster projection has no clients with draft_class={draft_year}. Refusing to "
            "build an empty dashboard (check DRAFT_YEAR, or roll back with ROSTER_SOURCE=hardcoded).")
    players: dict[str, str] = {}
    channel_to_player: dict[str, str] = {}
    channels: list[tuple[str, str]] = []
    for p in members:
        name = str(p.get("name") or "").strip()
        if not name:
            raise RosterProjectionError(f"Roster projection row {p['slug']} has no name.")
        key = _last_name_key(name)
        if key in players and players[key] != name:
            raise RosterProjectionError(
                f"Two draft-class {draft_year} clients share the last-name key {key!r} "
                f"({players[key]} / {name}). PLAYERS_2026 is keyed by last name, so this "
                "roster cannot be represented; fix the matcher before flipping.")
        players[key] = name
        ch_name = str(p.get("slack_channel_name") or "").strip().lstrip("#").lower()
        ch_id = str(p.get("slack_channel_id") or "").strip()
        if ch_name and ch_id:
            channel_to_player[ch_name] = name
            channels.append((ch_name, ch_id))
    return {"players": players, "channel_to_player": channel_to_player,
            "channels": channels,
            "slugs": [p["slug"] for p in members],
            "members": [(p["slug"], str(p.get("name") or "").strip()) for p in members]}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def dual_run_line(hardcoded_players: dict, hardcoded_c2p: dict, registry: dict) -> str:
    """One log line comparing the in-file roster with the registry's draft class.
    Names only (no contact data exists on this door). Keys are slug-shaped."""
    hard = {_slugify(n) for n in hardcoded_players.values()}
    reg_keys = {slug for slug, _ in registry["members"]} | {
        _slugify(name) for _, name in registry["members"]}
    only_hard = sorted(hard - reg_keys)
    only_reg = sorted(slug for slug, name in registry["members"]
                      if slug not in hard and _slugify(name) not in hard)
    hard_ch = {(c, _slugify(n)) for c, n in hardcoded_c2p.items()}
    reg_ch = {(c, _slugify(n)) for c, n in registry["channel_to_player"].items()}
    ch_diff = sorted({c for c, _ in hard_ch ^ reg_ch} & {c for c, _ in hard_ch})
    return (f"[dual-run] roster hardcoded={len(hard)} registry={len(registry['members'])} "
            f"only_hardcoded={only_hard} only_registry={only_reg} channel_mismatch={ch_diff}")
