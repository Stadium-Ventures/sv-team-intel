#!/usr/bin/env python3
"""
Fetch TeamIntel messages from Slack, parse, and build dashboard.html
Runs locally or via GitHub Actions.
"""

import json, re, os, time, csv, io, urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from slack_sdk import WebClient

# --- CONFIG ---
OLDEST = str(int(datetime(2025, 8, 1).timestamp()))

PLAYERS_2026 = {
    'robbins': 'Aiden Robbins', 'flukey': 'Cameron Flukey', 'jones': 'Kyle Jones',
    'bailey': 'Myles Bailey', 'condon': 'Trevor Condon', 'lowrance': 'Bo Lowrance',
    'marchand': 'Taj Marchand', 'tiroly': 'Joe Tiroly', 'kranzler': 'Alex Kranzler',
    'torres': 'Boston Torres', 'neal': 'Brady Neal', 'wright': 'Brooks Wright',
    'cleveland': 'Cole Cleveland', 'diaz': 'Devin Diaz', 'lawrence': 'Lucas Lawrence',
    'loy': 'Griffin Loy', 'beaird': 'Phinn Beaird', 'eckelman': 'Mason Eckelman',
    'steele': 'Lucas Steele', 'gillen': 'Michael Gillen', 'fowler': 'Bryce Fowler',
    'myhand': 'Will Myhand', 'mccarron': 'Duke McCarron', 'viveros': 'Easton Viveros',
    'woodward': 'Dominic Woodward', 'ellis': 'Lee Ellis', 'tryon': 'Ben Tryon',
}

ALL_2026_PLAYERS = sorted(set(PLAYERS_2026.values()))

CHANNEL_TO_PLAYER = {
    'aiden-robbins': 'Aiden Robbins', 'cameron-flukey': 'Cameron Flukey',
    'kyle-jones': 'Kyle Jones', 'myles-bailey': 'Myles Bailey',
    'trevor-condon': 'Trevor Condon', 'bo-lowrance': 'Bo Lowrance',
    'taj-marchand': 'Taj Marchand', 'joe-tiroly': 'Joe Tiroly',
    'alex-kranzler': 'Alex Kranzler', 'boston-torres': 'Boston Torres',
    'brady-neal': 'Brady Neal', 'brooks-wright': 'Brooks Wright',
    'cole-cleveland': 'Cole Cleveland', 'devin-diaz': 'Devin Diaz',
    'lucas-lawrence': 'Lucas Lawrence', 'griffin-loy': 'Griffin Loy',
    'phinn-beaird': 'Phinn Beaird', 'mason-eckelman': 'Mason Eckelman',
    'lucas-steele': 'Lucas Steele', 'michael-gillen': 'Michael Gillen',
    'bryce-fowler': 'Bryce Fowler', 'will-myhand': 'Will Myhand',
    'ben-tryon': 'Ben Tryon', 'duke-mccarron': 'Duke McCarron',
    'easton-viveros': 'Easton Viveros', 'lee-ellis': 'Lee Ellis',
    'dominic-woodward': 'Dominic Woodward',
}

TEAM_ABBR = {
    'ARI': 'ARI', 'ARZ': 'ARI', 'AZ': 'ARI', 'DBACKS': 'ARI', 'DIAMONDBACKS': 'ARI', 'ARIZONA': 'ARI',
    'ATL': 'ATL', 'ATLANTA': 'ATL', 'BRAVES': 'ATL',
    'BAL': 'BAL', 'BALTIMORE': 'BAL', 'ORIOLES': 'BAL',
    'BOS': 'BOS', 'BOSTON': 'BOS', 'RED SOX': 'BOS',
    'CHC': 'CHC', 'CUBS': 'CHC',
    'CHW': 'CHW', 'CWS': 'CHW', 'WHITE SOX': 'CHW',
    'CIN': 'CIN', 'REDS': 'CIN', 'CINCINNATI': 'CIN',
    'CLE': 'CLE', 'CLEVELAND': 'CLE', 'GUARDIANS': 'CLE',
    'COL': 'COL', 'COLORADO': 'COL', 'ROCKIES': 'COL',
    'DET': 'DET', 'DETROIT': 'DET', 'TIGERS': 'DET',
    'HOU': 'HOU', 'HOUSTON': 'HOU', 'ASTROS': 'HOU',
    'KC': 'KC', 'KANSAS CITY': 'KC', 'ROYALS': 'KC',
    'LAA': 'LAA', 'ANGELS': 'LAA',
    'LAD': 'LAD', 'DODGERS': 'LAD',
    'MIA': 'MIA', 'MIAMI': 'MIA', 'MARLINS': 'MIA', 'FL': 'MIA', 'FLA': 'MIA',
    'MIL': 'MIL', 'MILWAUKEE': 'MIL', 'BREWERS': 'MIL',
    'MIN': 'MIN', 'MINNESOTA': 'MIN', 'TWINS': 'MIN', 'MINN': 'MIN',
    'NYM': 'NYM', 'METS': 'NYM',
    'NYY': 'NYY', 'YANKEES': 'NYY',
    'ATH': 'ATH', 'OAK': 'ATH', 'ATHLETICS': 'ATH', "A'S": 'ATH',
    'PHI': 'PHI', 'PHIL': 'PHI', 'PHILLIES': 'PHI', 'PHILADELPHIA': 'PHI',
    'PIT': 'PIT', 'PIRATES': 'PIT', 'PITT': 'PIT', 'PITTSBURGH': 'PIT',
    'SD': 'SD', 'SDP': 'SD', 'PADRES': 'SD', 'SAN DIEGO': 'SD',
    'SF': 'SF', 'SFG': 'SF', 'GIANTS': 'SF', 'SAN FRANCISCO': 'SF',
    'SEA': 'SEA', 'SEATTLE': 'SEA', 'MARINERS': 'SEA',
    'STL': 'STL', 'CARDINALS': 'STL', 'ST LOUIS': 'STL',
    'TB': 'TB', 'TAMPA BAY': 'TB', 'RAYS': 'TB',
    'TEX': 'TEX', 'TEXAS': 'TEX', 'RANGERS': 'TEX',
    'TOR': 'TOR', 'TORONTO': 'TOR', 'BLUE JAYS': 'TOR', 'JAYS': 'TOR',
    'WSH': 'WSH', 'WAS': 'WSH', 'WASHINGTON': 'WSH', 'NATIONALS': 'WSH', 'NATS': 'WSH',
}

ALL_TEAMS = sorted(set(TEAM_ABBR.values()))

# Channels to search
CHANNELS = [
    ("2026-draft-general", "C09BB2NE1D4"),
    ("winter-meetings-2026", "C0A1XFUMQFM"),
    ("aiden-robbins", "C08DQTL4TGE"), ("cameron-flukey", "C08FL69S1S6"),
    ("kyle-jones", "C08CMC78D9Q"), ("myles-bailey", "C08CEPHABRC"),
    ("trevor-condon", "C08CJHA0C4D"), ("bo-lowrance", "C08CJHP13V3"),
    ("taj-marchand", "C08CZQFEGCR"), ("joe-tiroly", "C08LWQUEBQE"),
    ("alex-kranzler", "C08F4HDD9TR"), ("boston-torres", "C08M293RD19"),
    ("brady-neal", "C08FDPYARRP"), ("brooks-wright", "C08CMDB8FMY"),
    ("cole-cleveland", "C08D03F4797"), ("devin-diaz", "C08CMD0V802"),
    ("lucas-lawrence", "C08CMA913BL"), ("griffin-loy", "C09LQL4ENAX"),
    ("phinn-beaird", "C09344354UA"), ("mason-eckelman", "C09A0TL8KNY"),
    ("lucas-steele", "C08C6RFJKSB"), ("michael-gillen", "C08DA6DJ01W"),
    ("bryce-fowler", "C08C6RT634P"), ("will-myhand", "C08DA7A0P6C"),
    ("ben-tryon", "C0A3EKND2P4"), ("duke-mccarron", "C0A605KCVJ7"),
    ("easton-viveros", "C0ACP8YSA00"), ("lee-ellis", "C0A844F4SUF"),
    ("dominic-woodward", "C0ADA5H22C8"),
]


# --- STEP 1: FETCH FROM SLACK ---
def fetch_messages(token):
    client = WebClient(token=token)
    all_messages = []

    for name, cid in CHANNELS:
        try:
            client.conversations_join(channel=cid)
        except:
            pass

        cursor = None
        while True:
            kwargs = dict(channel=cid, oldest=OLDEST, limit=200)
            if cursor:
                kwargs['cursor'] = cursor
            try:
                resp = client.conversations_history(**kwargs)
            except Exception as e:
                print(f"  Error #{name}: {e}")
                break

            for msg in resp['messages']:
                text = msg.get('text', '')
                tl = text.lower()
                # Include ALL messages from 2026-draft-general (keyword often omitted)
                # For other channels, require "teamintel" / "team intel" keyword
                is_teamintel = (
                    name == '2026-draft-general'
                    or 'teamintel' in tl
                    or 'team intel' in tl
                )
                if is_teamintel:
                    all_messages.append({
                        'channel': name, 'channel_id': cid,
                        'ts': msg['ts'],
                        'date': datetime.fromtimestamp(float(msg['ts'])).strftime('%Y-%m-%d'),
                        'text': text, 'user': msg.get('user', ''),
                    })

                # Fetch thread replies when the parent is a team-intel post.
                # Replies get their own records and inherit the parent's first line
                # (usually the team header) so "Bo and Taj workout" in a reply
                # under "HOU - Cam Pendino" gets attributed to HOU.
                if is_teamintel and msg.get('reply_count', 0) > 0 and msg.get('thread_ts') == msg['ts']:
                    try:
                        rep_resp = client.conversations_replies(channel=cid, ts=msg['ts'])
                    except Exception as e:
                        print(f"  Error fetching replies in #{name}: {e}")
                        rep_resp = None
                    if rep_resp:
                        parent_header = text.split('\n')[0] if text else ''
                        for reply in rep_resp.get('messages', []):
                            if reply.get('ts') == msg['ts']:
                                continue  # skip the parent itself
                            r_text = reply.get('text', '')
                            combined = (parent_header + '\n\n' + r_text) if parent_header else r_text
                            all_messages.append({
                                'channel': name, 'channel_id': cid,
                                'ts': reply['ts'],
                                'date': datetime.fromtimestamp(float(reply['ts'])).strftime('%Y-%m-%d'),
                                'text': combined, 'user': reply.get('user', ''),
                                'is_reply': True, 'parent_ts': msg['ts'],
                            })
                    time.sleep(0.3)

            if not resp.get('has_more'):
                break
            cursor = resp['response_metadata']['next_cursor']
            time.sleep(0.3)

    # Deduplicate by timestamp
    seen = set()
    unique = []
    for m in all_messages:
        if m['ts'] not in seen:
            seen.add(m['ts'])
            unique.append(m)

    print(f"Fetched {len(unique)} TeamIntel messages from {len(CHANNELS)} channels")
    return unique


# --- STEP 2: PARSE ---
def normalize_team(s):
    return TEAM_ABBR.get(s.upper().strip())

def find_teams_in_line(line):
    found = set()
    lu = line.upper().strip()
    for key in sorted(TEAM_ABBR.keys(), key=len, reverse=True):
        if len(key) >= 2 and re.search(r'\b' + re.escape(key) + r'\b', lu):
            # Skip location references like "Metro Atl.", "Atl. area"
            if key == 'ATL' and re.search(r'METRO\s+ATL|ATL\.', lu):
                continue
            found.add(TEAM_ABBR[key])
    if lu in TEAM_ABBR:
        found.add(TEAM_ABBR[lu])
    return found

def find_players_in_text(text):
    found = set()
    tl = text.lower()
    for last, full in PLAYERS_2026.items():
        if last in tl:
            found.add(full)
    if re.search(r'\bcam\b', tl) and 'Cameron Flukey' not in found:
        found.add('Cameron Flukey')
    if re.search(r'\btrev\b', tl) and 'Trevor Condon' not in found:
        found.add('Trevor Condon')
    if re.search(r'\bbo\b', tl) and 'Bo Lowrance' not in found:
        found.add('Bo Lowrance')
    if re.search(r'\btaj\b', tl) and 'Taj Marchand' not in found:
        found.add('Taj Marchand')
    if re.search(r'\bphinn\b', tl) and 'Phinn Beaird' not in found:
        found.add('Phinn Beaird')
    return found

# Single-player Slack channels — every message in these is already scoped to one player,
# so a workout phrase anywhere in the text applies to that player.
_SINGLE_PLAYER_CHANNELS = set(CHANNEL_TO_PLAYER.keys())

# Player alias map: full name -> set of lowercase aliases (first name, last name, nicknames).
PLAYER_ALIASES = {}
for _last_lc, _full in PLAYERS_2026.items():
    _first = _full.split()[0].lower()
    PLAYER_ALIASES[_full] = {_last_lc, _first}
PLAYER_ALIASES['Cameron Flukey'].update({'cam'})
PLAYER_ALIASES['Trevor Condon'].update({'trev'})
# 'bo', 'taj', 'phinn' already first names

# Broad patterns — team-level workout facts that apply to every player named in the message.
_WORKOUT_BROAD_PATTERNS = [
    r'pre[- ]?draft\s+\w*\s*workout',
    r'\bpdw\b',
    r'invite\w*\s.*?workout',
    r'workout\s+invite\w*',
    r'\bprivate\s+workout',
    r'\bcome\s+(?:in|out)\s+for\s+(?:a\s+)?workout',
    r'\bworkout\s+(?:scheduled|set\s+for|planned)',
    r'\bscheduled\s+(?:for\s+)?.*?workout',
    r'offered\s+.*?\b(?:jan|feb|mar|apr|may|june|july|aug|sep|oct|nov|dec)\b',
    r'tentative\s+.*?workout',
]

# Targeted patterns — phrase must appear in the same sentence/line as a player name.
_WORKOUT_TARGETED_PATTERNS = [
    r'\bwants?\s+\w+(?:\s+(?:and|,)\s+\w+)?\s+(?:to|at)\s+workout\b',       # "wants Bo to workout" / "want Taj and Condon at workout"
    r'\bbring(?:ing)?\s+\w+\s+in\s+.*?workout',                              # "bringing him in for a workout"
    r'\bworkout\s+(?:on\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d',  # "workout June 5"
    # "Workout in Sarasota May 24-29" — allow a few intermediate words before the month
    r'\bworkout\s+(?:in|at|on|for|during)\s+(?:\w+\s+){0,4}(?:jan|feb|mar|apr|may|june|july|aug|sep|oct|nov|dec)\w*\s+\d',
    r'\bworkout\s+\w*\s*@\s+\w',                                             # "workout @ Port St Lucie"
    r'\bworkout\s+important\b',                                              # "Condon — workout important"
    r'\bworkouts?\s+for\s+\w',                                               # "workouts for Bo and Taj"
    r'\breach(?:ed|ing)?\s+out\s+(?:on|about|for)\s+.*?workouts?',           # "reached out on workouts"
    # Team-name + workout proximity: only flag players co-mentioned in the same line.
    # Keeps single-player channels covered (all targeted fire there), but group-intel
    # messages won't blanket-flag everyone just because "BAL ... Workout" appears.
    r'\b(?:jays|astros|cubs|tigers|rays|dodgers|yankees|mets|braves|reds|padres|pirates|phillies|nationals|marlins|brewers|cardinals|rockies|diamondbacks|giants|mariners|angels|twins|royals|guardians|orioles|rangers|white sox|red sox|blue jays)[\s\S]{0,40}?workout',
    r'\b(?:ari|atl|bal|bos|chc|chw|cin|cle|col|det|hou|kc|laa|lad|mia|mil|min|nym|nyy|oak|phi|pit|sd|sdp|sea|sf|sfg|stl|tb|tbr|tex|tor|wsh|was)[\s\S]{0,40}?workout',
]

def _spans_for(text_lc, patterns):
    spans = []
    for pat in patterns:
        for m in re.finditer(pat, text_lc):
            spans.append(m.span())
    return spans

_ALL_ALIASES = set()
for _aliases in PLAYER_ALIASES.values():
    _ALL_ALIASES.update(_aliases)

_SENTENCE_BOUNDARY = re.compile(r'[.!?\n]')

def _sentence_around(text, span):
    """Return the sentence/line containing `span` — bounded by [.!?\\n] or the text edges."""
    s, e = span
    left_boundary = 0
    for m in _SENTENCE_BOUNDARY.finditer(text, 0, s):
        left_boundary = m.end()
    right_match = _SENTENCE_BOUNDARY.search(text, e)
    right_boundary = right_match.start() if right_match else len(text)
    return text[left_boundary:right_boundary]

def has_workout_invite(text, player=None, channel=None):
    """Bool wrapper over workout_match_details."""
    return len(workout_match_details(text, player, channel)) > 0

def workout_match_details(text, player=None, channel=None):
    """
    Return list of {'start','end','text','kind'} for the specific regex spans that
    triggered a workout flag. UI uses these to highlight the phrase in the message.
    """
    tl = text.lower()
    broad_spans = _spans_for(tl, _WORKOUT_BROAD_PATTERNS)
    targeted_spans = _spans_for(tl, _WORKOUT_TARGETED_PATTERNS)
    if not broad_spans and not targeted_spans:
        return []
    matches = []
    if channel in _SINGLE_PLAYER_CHANNELS:
        for s, e in broad_spans:
            matches.append({'start': s, 'end': e, 'text': text[s:e], 'kind': 'broad'})
        for s, e in targeted_spans:
            matches.append({'start': s, 'end': e, 'text': text[s:e], 'kind': 'targeted'})
        return matches
    for s, e in broad_spans:
        matches.append({'start': s, 'end': e, 'text': text[s:e], 'kind': 'broad'})
    aliases = PLAYER_ALIASES.get(player) if player else None
    if aliases:
        for s, e in targeted_spans:
            sentence = _sentence_around(tl, (s, e))
            for alias in aliases:
                if re.search(r'\b' + re.escape(alias) + r'\b', sentence):
                    matches.append({'start': s, 'end': e, 'text': text[s:e], 'kind': 'targeted'})
                    break
    elif targeted_spans and not broad_spans:
        for s, e in targeted_spans:
            matches.append({'start': s, 'end': e, 'text': text[s:e], 'kind': 'targeted'})
    return matches

# --- Workout-date parser (pre-draft window: April 1 – July 13, 2026) ---
_WD_MONTH_NUM = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_WD_MONTH_RE = r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
_WD_MIN = datetime(2026, 4, 1)
_WD_MAX = datetime(2026, 7, 13)
_WD_TENTATIVE_RE = re.compile(r'\b(tentative|likely|maybe|possibly|tbd|possible|hopefully|might)\b', re.I)
_WD_TIME_RE = re.compile(r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\b')
_WD_LOC_RE = re.compile(
    r'(?:\bin|\bat|@)\s+([A-Z][\w\.\- ]+?)(?=[\.,\n]|\s+or\s+|\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b|\s+\d|\Z)',
    re.I,
)
_WD_DATE_LIST_LINE_RE = re.compile(
    r'^\s*(?:' + _WD_MONTH_RE + r'\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}/\d{1,2})\s*[-–:]\s*\S',
    re.I,
)


def _wd_safe(year, month, day):
    try:
        return datetime(year, month, day)
    except (ValueError, TypeError):
        return None


def _wd_extract_dates(line):
    found = []
    for m in re.finditer(_WD_MONTH_RE + r'\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?', line, re.I):
        month = _WD_MONTH_NUM.get(m.group(1).upper()[:3])
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else 2026
        d = _wd_safe(year, month, day)
        if d and _WD_MIN <= d <= _WD_MAX:
            found.append(d)
    for m in re.finditer(_WD_MONTH_RE + r'\s+(\d{1,2})(?:st|nd|rd|th)?\s+or\s+(\d{1,2})(?:st|nd|rd|th)?', line, re.I):
        month = _WD_MONTH_NUM.get(m.group(1).upper()[:3])
        day = int(m.group(3))
        d = _wd_safe(2026, month, day)
        if d and _WD_MIN <= d <= _WD_MAX:
            found.append(d)
    for m in re.finditer(_WD_MONTH_RE + r'\s+(\d{1,2})-(\d{1,2})\b', line, re.I):
        month = _WD_MONTH_NUM.get(m.group(1).upper()[:3])
        day = int(m.group(3))
        d = _wd_safe(2026, month, day)
        if d and _WD_MIN <= d <= _WD_MAX:
            found.append(d)
    for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b', line):
        month = int(m.group(1))
        day = int(m.group(2))
        year = m.group(3)
        if year:
            year = int(year)
            if year < 100: year += 2000
        else:
            year = 2026
        d = _wd_safe(year, month, day)
        if d and _WD_MIN <= d <= _WD_MAX:
            found.append(d)
    seen = set(); out = []
    for d in found:
        s = d.strftime('%Y-%m-%d')
        if s not in seen:
            seen.add(s); out.append(s)
    return out


def _wd_first_team(line):
    lu = line.upper()
    best_pos = None; best_team = None
    for key, team in TEAM_ABBR.items():
        if len(key) < 2: continue
        if team == 'ATL' and re.search(r'METRO\s+ATL|ATL\.', lu): continue
        m = re.search(r'\b' + re.escape(key) + r'\b', lu)
        if not m: continue
        if best_pos is None or m.start() < best_pos:
            best_pos = m.start(); best_team = team
    return best_team


def extract_workout_dates(full_text):
    """
    Parse message text for pre-draft workout dates attributed to teams.
    Returns { team_abbr: [ {date, tentative, time, location}, ... ] }.
    """
    merged = defaultdict(dict)
    current_team = None
    for raw_line in full_text.split('\n'):
        line = raw_line.strip()
        if not line: continue
        is_date_list = bool(_WD_DATE_LIST_LINE_RE.match(line))
        teams_in_line = find_teams_in_line(line)
        if teams_in_line and not is_date_list:
            current_team = _wd_first_team(line) or sorted(teams_in_line)[0]
        dates = _wd_extract_dates(line)
        if not dates: continue
        tentative = bool(_WD_TENTATIVE_RE.search(line))
        tm = _WD_TIME_RE.search(line)
        time_str = tm.group(1).strip() if tm else None
        lm = _WD_LOC_RE.search(line)
        location = lm.group(1).strip() if lm else None
        targets = sorted(teams_in_line) if (teams_in_line and not is_date_list) else [current_team]
        for team in targets:
            for d in dates:
                ev = merged[team].get(d)
                if ev is None:
                    merged[team][d] = {'date': d, 'tentative': tentative, 'time': time_str, 'location': location}
                else:
                    if tentative: ev['tentative'] = True
                    if time_str and not ev['time']: ev['time'] = time_str
                    if location and (not ev['location'] or len(location) > len(ev['location'])):
                        ev['location'] = location
    return {t: list(d.values()) for t, d in merged.items() if t}


def score_line_for_team(line, full_text=""):
    ll = line.lower()
    if re.search(r'\bred\b', ll) and 'green' not in ll and 'orange' not in ll:
        return -2
    if 'orange' in ll:
        return -1
    if 'yellow' in ll:
        return 0
    if 'light green' in ll:
        return 1
    if re.search(r'\bgreen\b', ll):
        return 2
    if any(w in ll for w in ['love', 'loves', 'absolutely', 'favorites', 'elite', 'really like', 'really likes', 'high on', 'heavy on']):
        return 2
    if 'no communication' in ll or "didn't like" in ll:
        return -1
    return 1


# Matrix-cell color = literal color word from the message line. No sentiment
# weighting, no aggregation. Most-recent record's color wins per (player, team).
# Check 'light green' before 'green' — order matters.
def detect_color_word(text):
    if not text:
        return None
    ll = text.lower()
    if re.search(r'\blight\s+green\b', ll):
        return 'light green'
    if re.search(r'\bgreen\b', ll):
        return 'green'
    if re.search(r'\byellow\b', ll):
        return 'yellow'
    if re.search(r'\borange\b', ll):
        return 'orange'
    if re.search(r'\bred\b', ll):
        return 'red'
    return None

# ======================== ATTENDEE TIER DETECTION ========================
# Weight each TeamIntel record by the seniority of the attendee mentioned in
# the message line. Tier 1 (SD / GM / VP / Special Asst) weighs 2×; T2 (National
# X'er) 1.5×; T3 (plain X'er / regional) 1.25×; T4 (area scout) is baseline.

# TIER_MULTIPLIERS doubles as the score floor for a record: when an attendee
# at a given tier is detected, the record's sentiment score is bumped up to
# this value (unless sentiment was already higher or explicitly negative).
# Tier 0 = no tier detected (no floor applied, sentiment drives everything).
TIER_MULTIPLIERS = {0: 0, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1}
TIER_LABELS = {0: '', 1: 'GM', 2: 'Dir', 3: 'NXC', 4: 'X', 5: 'Area'}

# Role → tier map for the org-review CSV columns. The very top (GM /
# President of Baseball Ops) is T1; other director-level roles are T2.
_ORG_ROLE_TIER = {
    'president': 1,           # corporate president (if at a game, huge)
    'pres_baseball_ops': 1,   # baseball ops head — top-of-org signal
    'gm': 1,
    'asst_gm': 2,
    'scouting_dir': 2,
    'asst_scouting_dir': 2,
    'pd_dir': 2,
    'asst_pd_dir': 2,
    'pitching_coord': 2,
    'hitting_coord': 2,
}

def load_front_office():
    """Return {team_abbrev: [(name_lower, tier, role_label), ...]}.
    Multi-person cells ("Name One / Name Two") split on ' / '. Silent fallback
    to {} if the CSV isn't present (e.g. during local dry runs).
    """
    path = os.path.join(os.path.dirname(__file__), 'data', 'front_office_2026.csv')
    if not os.path.exists(path):
        print(f"INFO: {path} not found — tier detection will rely on keywords only.")
        return {}
    directory = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            abbrev = (row.get('abbrev') or '').strip().upper()
            if not abbrev:
                continue
            entries = []
            for col, tier in _ORG_ROLE_TIER.items():
                raw = (row.get(col) or '').strip()
                if not raw:
                    continue
                for name in re.split(r'\s*/\s*', raw):
                    n = name.strip()
                    if not n:
                        continue
                    entries.append((n.lower(), tier, col))
            if entries:
                directory[abbrev] = entries
    print(f"Loaded front-office directory for {len(directory)} teams.")
    return directory


# Regex patterns for keyword-based tier detection.
# Checked in priority order: T1 > T2 > T3 > T4 > T5. Highest tier detected wins.
# T1 — GM / President of Baseball Ops (the absolute top).
# `\bgm\b` uses negative lookbehinds so "Asst GM" / "Assistant GM" do NOT
# match here (they fall through to T2 instead).
_TIER1_PATTERNS = [
    r'(?<!asst )(?<!asst\. )(?<!assistant )\bgm\b',
    r'\bpres(?:ident)?\s+of\s+baseball\s+ops\b',
    r'\bpres(?:ident)?\s+baseball\s+ops\b',
    r'\bpobo\b',
]
# T2 — Director-level: SD / AGM / Special Asst / VP / Dir of Pro Scouting / PD Dir / Coords
_TIER2_PATTERNS = [
    r'\bagm\b', r'\basst\.?\s+gm\b', r'\bassistant\s+gm\b',
    r'\bsd\b', r'\basst\.?\s+sd\b',
    r'\bscouting\s+dir(?:ector)?\b', r'\basst\.?\s+scouting\s+dir(?:ector)?\b',
    r'\bvp\b', r'\bv\.p\.\b',
    r'\bdirector\s+of\s+pro\s+scouting\b', r'\bpro\s+scouting\s+dir(?:ector)?\b',
    r'\bhead\s+of\s+draft\s+ops\b',
    r'\bspecial\s+ass?t\b', r'\bspecial\s+assistant\b',
    r'\bdirector\s+of\s+player\s+development\b', r'\bdirector\s+player\s+dev\b',
    r'\bpitching\s+coord(?:inator)?\b', r'\bhitting\s+coord(?:inator)?\b',
]
# T3 — National Cross-Checker
_TIER3_PATTERN = r'\bnational\s+x(?:er|\'er|-er)?\b|\bnxc\b|\bnational\s+cross[- ]?check(?:ers?)?\b'
# T4 — Regional Cross-Checker (bare X'er / Crosschecker, or explicit "Regional X")
_TIER4_PATTERN = r'\bx(?:er|\'er|-er)\b|\bcross[- ]?check(?:ers?)?\b|\bregional\s+x(?:er|\'er|-er)?\b'
# T5 — Area Scout
_TIER5_PATTERN = r'\barea\s+(?:guy|scout)?\b|\bout\s+of\s+area\b'


def detect_attendee_tier(line, team, directory):
    """Returns (tier:int 0-5, points:int, label:str).
    Tier 0 = nothing detected (no floor applied). 1-5 descending seniority.
    1. Name match against `directory[team]` → that role's tier.
    2. Keyword regex. Multiple hits → highest tier wins (lowest numeric).
    3. Default T0 (no boost).
    """
    if not line:
        return 0, 0, ''
    tiers_seen = set()
    lower = line.lower()

    # Name match against the team directory (roles assigned tier 1 or 2 per _ORG_ROLE_TIER).
    for name_lower, tier, role_col in directory.get(team, []):
        if re.search(r'\b' + re.escape(name_lower) + r'\b', lower):
            tiers_seen.add(tier)

    # T1 — GM / President of Baseball Ops
    for pat in _TIER1_PATTERNS:
        if re.search(pat, lower):
            tiers_seen.add(1)
            break
    # T2 — Director-level
    for pat in _TIER2_PATTERNS:
        if re.search(pat, lower):
            tiers_seen.add(2)
            break
    # T3 — National X'er / Crosschecker
    if re.search(_TIER3_PATTERN, lower):
        tiers_seen.add(3)
    # T4 — bare X'er / Crosschecker (must not be preceded by "national")
    t4_hit = False
    for m in re.finditer(r'\bx(?:er|\'er|-er)\b', lower):
        pre = lower[max(0, m.start()-15):m.start()]
        if 'national' not in pre:
            t4_hit = True
            break
    if t4_hit or re.search(r'\bcross[- ]?check(?:ers?)?\b', lower) or re.search(r'\bregional\s+x', lower):
        tiers_seen.add(4)
    # T5 — Area
    if re.search(_TIER5_PATTERN, lower):
        tiers_seen.add(5)

    if not tiers_seen:
        return 0, 0, ''
    tier = min(tiers_seen)
    return tier, TIER_MULTIPLIERS[tier], TIER_LABELS.get(tier, '')


def parse_messages(messages):
    records = []
    # Load front-office directory once per build (tiny CSV, ~30 teams).
    _front_office = load_front_office()

    def _attach_tier(rec, line_text):
        """Write attendee_tier / tier_multiplier / tier_label / raw_score / color
        onto a record in place, and bump rec['score'] to the tier floor when a
        senior attendee was detected.
        - Sentiment score stays visible as rec['raw_score'] (for audit / revert).
        - Negative sentiment (-1, -2) always wins — an SD being there doesn't
          override "didn't like".
        - Otherwise: rec['score'] = max(sentiment, tier_floor).
        - rec['color'] = literal color word (red/orange/yellow/light green/green)
          extracted from the line, or None. Drives matrix cell color directly
          (no aggregation / sentiment translation).
        - **T0 → T5 floor**: if no tier keyword is detected, default to T5 (Area
          scout, +1 pt). The team being named in the message is itself evidence
          that at least an area scout was tracking this player. Manual point
          overrides (popup) can dial this down to 0 if needed.
        """
        t, mult, label = detect_attendee_tier(line_text, rec.get('team'), _front_office)
        if t == 0:
            t, mult, label = 5, TIER_MULTIPLIERS[5], TIER_LABELS[5]
        rec['attendee_tier'] = t
        rec['tier_multiplier'] = mult
        rec['tier_label'] = label
        rec['color'] = detect_color_word(line_text)
        sentiment = rec.get('score', 1)
        rec['raw_score'] = sentiment
        if sentiment < 0 or t == 0:
            # Explicit negative wins; T0 (no tier identified) keeps sentiment as-is.
            return
        tier_floor = mult
        if tier_floor > sentiment:
            rec['score'] = tier_floor

    for msg in sorted(messages, key=lambda m: m['ts']):
        text = msg['text']
        date = msg['date']
        channel = msg['channel']

        if channel == 'winter-meetings-2026':
            header_match = re.search(r'[Tt]eam\s*[Ii]ntel\s*[-:]\s*(\w+)', text)
            if not header_match:
                continue
            team = normalize_team(header_match.group(1))
            if not team:
                continue
            for line in text.split('\n'):
                ls = line.strip()
                if not ls or re.match(r'^[Tt]eam\s*[Ii]ntel', ls):
                    continue
                players = find_players_in_text(ls)
                if not players:
                    continue
                score = score_line_for_team(ls, text)
                for player in players:
                    records.append({
                        'player': player, 'team': team, 'date': date,
                        'score': score, 'note': ls[:200],
                        'channel': channel, 'full_text': text[:3000],
                    })
                    _attach_tier(records[-1], ls)

        elif channel in CHANNEL_TO_PLAYER:
            player = CHANNEL_TO_PLAYER[channel]
            all_teams = set()
            for line in text.split('\n'):
                all_teams.update(find_teams_in_line(line))
            if not all_teams:
                continue
            for team in all_teams:
                best_score = 1
                # Highest tier across all lines mentioning this team — gives the
                # senior-most attendee credit for the team's score in this message.
                best_tier_line = ''
                best_tier = 5
                for line in text.split('\n'):
                    line_teams = find_teams_in_line(line)
                    if team in line_teams:
                        s = score_line_for_team(line, text)
                        if s != 1:
                            best_score = s
                        t, _, _ = detect_attendee_tier(line, team, _front_office)
                        if t < best_tier:
                            best_tier = t
                            best_tier_line = line
                tl = text.lower()
                if any(w in tl for w in ['love', 'loves', 'absolutely', 'elite', 'high on']):
                    for line in text.split('\n'):
                        if team in find_teams_in_line(line):
                            ll = line.lower()
                            if any(w in ll for w in ['love', 'loves', 'absolutely', 'elite', 'high on']):
                                best_score = 2
                if 'no communication' in tl:
                    for line in text.split('\n'):
                        if 'no communication' in line.lower() and team in find_teams_in_line(line):
                            best_score = -1
                records.append({
                    'player': player, 'team': team, 'date': date,
                    'score': best_score, 'note': text.strip()[:200],
                    'channel': channel, 'full_text': text[:3000],
                })
                _attach_tier(records[-1], best_tier_line or text)

        else:
            players = find_players_in_text(text)
            header_match = re.search(r'[Tt]eam\s*[Ii]ntel\s*[-:]?\s*\n?\s*(\w+)', text)
            header_team = None
            if header_match:
                ht = normalize_team(header_match.group(1))
                if ht:
                    header_team = ht
            all_teams = set()
            for line in text.split('\n'):
                all_teams.update(find_teams_in_line(line))

            if header_team and players:
                for line in text.split('\n'):
                    ls = line.strip()
                    if not ls:
                        continue
                    lp = find_players_in_text(ls)
                    if lp:
                        score = score_line_for_team(ls, text)
                        for p in lp:
                            records.append({
                                'player': p, 'team': header_team, 'date': date,
                                'score': score, 'note': ls[:200],
                                'channel': channel, 'full_text': text[:3000],
                            })
                            _attach_tier(records[-1], ls)
            elif players and all_teams:
                for line in text.split('\n'):
                    ls = line.strip()
                    lp = find_players_in_text(ls)
                    lt = find_teams_in_line(ls)
                    if lp and lt:
                        score = score_line_for_team(ls, text)
                        for p in lp:
                            for t in lt:
                                records.append({
                                    'player': p, 'team': t, 'date': date,
                                    'score': score, 'note': ls[:200],
                                    'channel': channel, 'full_text': text[:3000],
                                })
                                _attach_tier(records[-1], ls)
                    elif lp and not lt and all_teams:
                        score = score_line_for_team(ls, text)
                        for p in lp:
                            for t in all_teams:
                                records.append({
                                    'player': p, 'team': t, 'date': date,
                                    'score': score, 'note': text.strip()[:200],
                                    'channel': channel, 'full_text': text[:3000],
                                })
                                _attach_tier(records[-1], ls)

    # Add workout flag + match details based on note/full_text
    # Also attach parsed workout_dates (pre-draft window, May–Jul 2026),
    # filtered to the record's team so cross-team mentions don't bleed in.
    _wd_cache = {}
    for r in records:
        text = r.get('full_text', '') + '\n' + r.get('note', '')
        matches = workout_match_details(text, r.get('player'), r.get('channel'))
        r['workout'] = len(matches) > 0
        r['workout_matches'] = [m['text'] for m in matches]

        if r['workout']:
            ft = r.get('full_text', '')
            if ft not in _wd_cache:
                _wd_cache[ft] = extract_workout_dates(ft)
            r['workout_dates'] = _wd_cache[ft].get(r['team'], [])
        else:
            r['workout_dates'] = []

    # Deduplicate
    seen = set()
    unique = []
    for r in records:
        key = (r['player'], r['team'], r['date'], r['score'])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"Parsed {len(unique)} unique intel records")
    return unique


# --- STEP 3: BUILD HTML ---
def load_team_draft_info():
    """Read 2026 bonus pool + first picks per team from data/team_draft_2026.csv.
    Returns { abbrev: { 'pool': str, 'picks': [int] } }. Empty dict if missing.
    Source: `~/Desktop/claude/sv-org-review/Org.Review.2026.xlsx` "Review" sheet
    rows 3 ("Pool Amount") + 4 ("Pick #"). Re-extract when org-review updates.
    """
    path = os.path.join(os.path.dirname(__file__), 'data', 'team_draft_2026.csv')
    if not os.path.exists(path):
        print(f"INFO: {path} not found — team draft info won't render.")
        return {}
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            abbr = (row.get('abbrev') or '').strip().upper()
            if not abbr:
                continue
            picks = [p.strip() for p in (row.get('picks') or '').split(',') if p.strip()]
            out[abbr] = {
                'pool': (row.get('pool_amount') or '').strip(),
                'picks': picks,
            }
    return out


def build_html(records, password="SVintel2026", games=None):
    records_js = json.dumps(records)
    games_js = json.dumps(games or [])
    eastern = timezone(timedelta(hours=-4))
    now_str = datetime.now(eastern).strftime('%B %d, %Y %I:%M %p') + ' ET'
    all_2026_js = json.dumps(ALL_2026_PLAYERS)
    # Serialize alias map (sets aren't JSON-safe — convert to lists)
    player_aliases_js = json.dumps({name: sorted(aliases) for name, aliases in PLAYER_ALIASES.items()})
    team_draft_js = json.dumps(load_team_draft_info())

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, shrink-to-fit=no">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>SV TeamIntel</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/favicon.svg">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f5; color: #333; }}

/* --- PASSWORD GATE --- */
#loginGate {{
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: linear-gradient(135deg, #4a0a0a 0%, #8b1a1a 50%, #a52222 100%);
    display: flex; align-items: center; justify-content: center; z-index: 9999;
}}
#loginGate.hidden {{ display: none; }}
.login-box {{
    background: white; border-radius: 12px; padding: 40px; text-align: center;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3); min-width: 340px;
}}
.login-box .logo-img {{ height: 64px; width: auto; margin: 0 auto 8px; display: block; }}
.login-box .brand-name {{ font-size: 20px; font-weight: 800; color: #000000; letter-spacing: 0.5px; margin-top: 4px; }}
.login-box .brand-name .accent {{ color: #ff2a22; }}
.login-box .tagline {{ font-size: 12px; color: #888; margin-bottom: 24px; margin-top: 4px; }}
.login-box input {{
    width: 100%; padding: 12px 16px; font-size: 14px; border: 2px solid #ddd;
    border-radius: 8px; outline: none; margin-bottom: 12px; transition: border-color 0.2s;
}}
.login-box input:focus {{ border-color: #000000; }}
.login-box button {{
    width: 100%; padding: 12px; font-size: 14px; font-weight: 600;
    background: #000000; color: white; border: none; border-radius: 8px;
    cursor: pointer; transition: background 0.2s;
}}
.login-box button:hover {{ background: #222222; }}
.login-error {{
    color: #c0392b; font-size: 13px; margin-top: 12px; display: none;
    background: #fce4ec; padding: 10px 14px; border-radius: 6px;
    font-weight: 600; border: 1px solid #f5c6cb;
}}
@keyframes shake {{
    0%, 100% {{ transform: translateX(0); }}
    20%, 60% {{ transform: translateX(-8px); }}
    40%, 80% {{ transform: translateX(8px); }}
}}
.shake {{ animation: shake 0.4s ease; }}

#appContent {{ display: none; visibility: hidden; }}
#appContent.visible {{ display: block; visibility: visible; }}

/* --- DASHBOARD --- */
.header {{
    background: #000000;
    color: white; padding: 18px 30px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3); position: relative; z-index: 100;
    border-bottom: 3px solid #ff2a22;
}}
.header-left {{ display: flex; align-items: center; gap: 16px; }}
.header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
.header .subtitle {{ font-size: 13px; opacity: 0.8; font-weight: 400; }}
.logo-icon {{
    height: 38px; width: auto; display: flex; align-items: center; justify-content: center;
}}
.logo-icon img {{ height: 38px; width: auto; display: block; }}
.nav-tabs {{ display: flex; gap: 4px; }}
.nav-tab {{
    padding: 8px 20px; border-radius: 6px; cursor: pointer;
    font-size: 13px; font-weight: 600; transition: all 0.2s;
    border: 1px solid rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.8);
}}
.nav-tab:hover {{ background: rgba(255,255,255,0.15); color: white; }}
.nav-tab.active {{ background: rgba(255,255,255,0.25); color: white; border-color: rgba(255,255,255,0.4); }}

.stats-bar {{
    background: white; padding: 12px 30px; display: flex; gap: 30px;
    border-bottom: 1px solid #e0e0e0; font-size: 13px;
}}
.stat-item {{ display: flex; gap: 6px; align-items: center; }}
.stat-label {{ color: #888; font-weight: 500; }}
.stat-value {{ font-weight: 700; color: #000000; }}

.legend {{
    display: flex; gap: 16px; padding: 10px 30px; font-size: 12px;
    align-items: center; background: white; border-bottom: 1px solid #e0e0e0;
}}
.legend-title {{ font-weight: 600; color: #666; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.legend-swatch {{ width: 18px; height: 18px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1); }}

.matrix-container {{ padding: 20px 30px; }}
.matrix-scroll {{
    /* Fill the page below the sticky header + slim legend + statsBar so the
       matrix doesn't feel cut off. ~70px header + ~32px legend + ~52px stats
       + ~60px paddings. */
    max-height: calc(100vh - 215px); overflow: auto;
    -webkit-overflow-scrolling: touch; overscroll-behavior: contain;
    border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); background: white;
}}
.matrix-table {{
    border-collapse: separate; border-spacing: 0; font-size: 12px;
    width: auto; min-width: 100%; background: white;
}}
.matrix-table th, .matrix-table td {{
    padding: 8px 6px; text-align: center;
    border-right: 1px solid #e8e8e8; border-bottom: 1px solid #e8e8e8;
    white-space: nowrap; height: 32px; background: white;
}}
.matrix-table thead th {{
    background: #000000; color: white; font-weight: 600; font-size: 11px;
    letter-spacing: 0.3px; border-right: 1px solid #2a2a2a; border-bottom: 1px solid #2a2a2a;
    position: sticky; top: 0; z-index: 3;
}}
.matrix-table thead tr:first-child th {{ height: 26px; }}
/* Sub-header row: 2026 bonus pool + first 5 picks per team. Top-aligned so the
   pool $ stays in the same place across all columns regardless of how many
   picks land in the cell below. */
.matrix-table thead th.team-info {{
    background: #1a1a1a; color: #d8d8d8; font-weight: 500;
    padding: 5px 5px 6px; white-space: normal; vertical-align: top;
    border-bottom: 2px solid #000000; min-width: 64px;
    position: sticky; top: 26px; z-index: 3;
}}
.matrix-table thead th.team-info .ti-pool {{
    color: #fff; font-weight: 700; font-size: 11px; line-height: 1.1;
    letter-spacing: 0.2px; margin-bottom: 3px;
}}
.matrix-table thead th.team-info .ti-picks {{
    color: #c8c8c8; font-size: 9px; line-height: 1.25;
    font-weight: 500; letter-spacing: 0.1px;
}}
.matrix-table thead th.team-info .ti-picks-label {{
    color: #888; font-size: 8px; font-weight: 600;
    letter-spacing: 0.4px; text-transform: uppercase; margin-right: 3px;
}}
/* Sticky first column (Client name) — scoped to the first header row + body
   so the team-info sub-header's first cell isn't also stuck to the left edge. */
.matrix-table thead tr:first-child th:nth-child(1), .matrix-table tbody td:nth-child(1) {{
    position: sticky; left: 0; z-index: 2;
    min-width: 140px; max-width: 140px;
}}
.matrix-table tbody td:nth-child(1) {{
    background: white; text-align: left; padding-left: 10px; font-size: 12px; font-weight: 600;
    color: #000000;
    box-shadow: 2px 0 3px -1px rgba(0,0,0,0.1);
}}
.matrix-table thead tr:first-child th:nth-child(1) {{
    z-index: 4; box-shadow: 2px 0 3px -1px rgba(0,0,0,0.1);
}}
/* Row hover: drop !important so the inline cell-color (literal color word) wins.
   Empty cells still get a subtle pink wash; colored cells keep their color. */
.matrix-table tbody tr:hover td {{ background-color: #fff5f5; }}

.score-2 {{ background-color: #c6efce !important; color: #1a5e1a; font-weight: 700; }}
.score-1 {{ background-color: #e2efda !important; color: #3a6b30; font-weight: 600; }}
.score-0 {{ background-color: #fff2cc !important; color: #7a6b00; font-weight: 600; }}
.score-n1 {{ background-color: #ffd9b3 !important; color: #8a4500; font-weight: 600; }}
.score-na {{ background-color: #e0e0e0 !important; color: #666; font-weight: 600; font-style: italic; }}
.score-n2 {{ background-color: #f4c7c3 !important; color: #8b1a1a; font-weight: 700; }}
td.score-cell {{ position: relative; }}
td.score-cell.clickable:hover {{ outline: 2px solid #000000; outline-offset: -2px; }}
td.workout {{ outline: 3px solid #d4a017; outline-offset: -3px; }}
.workout-badge {{ display: inline-block; background: #d4a017; color: white; font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px; margin-left: 6px; vertical-align: middle; letter-spacing: 0.3px; }}
td.overridden {{ position: relative; }}
td.overridden::after {{ content: '*'; position: absolute; top: 1px; right: 3px; font-size: 9px; color: rgba(0,0,0,0.4); }}

#scorePopup {{
    display: none; position: fixed; z-index: 9000;
    background: white; border-radius: 10px; padding: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25); min-width: 220px;
}}
#scorePopup .popup-title {{ font-size: 13px; font-weight: 600; color: #333; margin-bottom: 10px; }}
#scorePopup .popup-scores {{ display: flex; gap: 6px; margin-bottom: 10px; }}
#scorePopup .popup-scores button {{
    flex: 1; padding: 8px 0; font-size: 14px; font-weight: 700; border: 2px solid #ddd;
    border-radius: 6px; cursor: pointer; transition: all 0.15s;
}}
#scorePopup .popup-scores button:hover {{ transform: scale(1.1); }}
#scorePopup .popup-scores button.ps2 {{ background: #c6efce; color: #1a5e1a; border-color: #a3d9a5; }}
#scorePopup .popup-scores button.ps1 {{ background: #e2efda; color: #3a6b30; border-color: #c5deb8; }}
#scorePopup .popup-scores button.ps0 {{ background: #fff2cc; color: #7a6b00; border-color: #e6d98a; }}
#scorePopup .popup-scores button.psn1 {{ background: #ffd9b3; color: #8a4500; border-color: #f5b97a; }}
#scorePopup .popup-scores button.psn2 {{ background: #f4c7c3; color: #8b1a1a; border-color: #e8a8a3; }}
#scorePopup .popup-scores button.psna {{ background: #e0e0e0; color: #666; border-color: #bbb; font-style: italic; font-size: 12px; }}
#scorePopup .popup-team-info {{
    background: #f7f7f7; border: 1px solid #e0e0e0; border-radius: 5px;
    padding: 6px 9px; margin: 0 0 10px; font-size: 11px; line-height: 1.45;
}}
#scorePopup .popup-team-info .pti-row {{ display: flex; gap: 6px; }}
#scorePopup .popup-team-info .pti-label {{ color: #888; font-weight: 600; min-width: 52px; }}
#scorePopup .popup-team-info .pti-pool {{ color: #1a5e1a; font-weight: 700; }}
#scorePopup .popup-team-info .pti-picks {{ color: #c0392b; font-weight: 600; }}
#scorePopup .popup-points-label {{ font-size: 11px; color: #888; font-weight: 600; letter-spacing: 0.3px; margin-bottom: 5px; text-transform: uppercase; }}
#scorePopup .popup-points {{ display: flex; gap: 5px; margin-bottom: 10px; }}
#scorePopup .popup-points button {{
    flex: 1; padding: 6px 0; font-size: 13px; font-weight: 700; cursor: pointer;
    border-radius: 5px; border: 1px solid #ccc; background: #f5f5f5; color: #333;
    transition: transform 0.1s;
}}
#scorePopup .popup-points button:hover {{ transform: scale(1.08); }}
#scorePopup .popup-points button.pp5 {{ background: #c6efce; color: #1a5e1a; border-color: #a3d9a5; }}
#scorePopup .popup-points button.pp4 {{ background: #d8f0d4; color: #2a6e2a; border-color: #b8dfb0; }}
#scorePopup .popup-points button.pp3 {{ background: #e2efda; color: #3a6b30; border-color: #c5deb8; }}
#scorePopup .popup-points button.pp2 {{ background: #f1f6e6; color: #4a6b1f; border-color: #d4e0b5; }}
#scorePopup .popup-points button.pp1 {{ background: #fafafa; color: #555; border-color: #ddd; }}
#scorePopup .popup-points button.pp0 {{ background: #f0f0f0; color: #888; border-color: #ccc; }}
#scorePopup .popup-reset {{
    font-size: 11px; color: #888; cursor: pointer; text-decoration: underline;
    text-align: center; display: block;
}}
#scorePopup .popup-pdw {{
    display: flex; align-items: center; justify-content: center; gap: 6px;
    margin-bottom: 8px; padding: 6px 0; border: 2px solid #ff2a22; border-radius: 6px;
    cursor: pointer; font-size: 12px; font-weight: 600; color: #ff2a22; background: white;
    transition: all 0.15s;
}}
#scorePopup .popup-pdw:hover {{ background: #fdf6e3; }}
#scorePopup .popup-pdw.active {{ background: #ff2a22; color: white; }}
#scorePopup .popup-reset:hover {{ color: #c0392b; }}
#scoreOverlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 8999; }}

#toast {{
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(120%);
    background: #c0392b; color: white; padding: 10px 18px; border-radius: 6px;
    font-size: 13px; font-weight: 500; box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    z-index: 10000; transition: transform 0.25s ease; max-width: 90%; text-align: center;
}}
#toast.ok {{ background: #2d7a2d; }}
#toast.visible {{ transform: translateX(-50%) translateY(0); }}

#messageOverlay {{
    display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.5); z-index: 9100;
}}
#messageOverlay.visible {{ display: flex; align-items: center; justify-content: center; }}
#messageModal {{
    background: white; border-radius: 10px; padding: 20px 24px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.3);
    max-width: 680px; width: 92%; max-height: 80vh; overflow: auto;
    font-size: 13px; color: #222;
}}
#messageModal .mm-close {{
    float: right; cursor: pointer; color: #888; font-size: 20px; line-height: 1;
    padding: 0 4px; border: none; background: none;
}}
#messageModal .mm-close:hover {{ color: #c0392b; }}
#messageModal .mm-back {{
    float: left; cursor: pointer; padding: 4px 10px; margin-right: 10px;
    background: #ff2a22; color: white; border: none; border-radius: 5px;
    font-size: 12px; font-weight: 600;
}}
#messageModal .mm-back:hover {{ background: #d4221a; }}
#messageModal .mm-header {{
    font-size: 12px; color: #666; font-weight: 600; letter-spacing: 0.3px; margin-bottom: 4px;
    text-transform: uppercase;
}}
#messageModal .mm-title {{
    font-size: 16px; font-weight: 700; color: #000000; margin-bottom: 2px;
}}
#messageModal .mm-meta {{
    font-size: 11px; color: #888; margin-bottom: 14px;
}}
#messageModal .mm-body {{
    background: #fafafa; border-left: 3px solid #000000; padding: 12px 14px;
    white-space: pre-wrap; line-height: 1.5; font-size: 13px;
    border-radius: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}
#messageModal mark.mm-hl {{
    background: #fdf6c7; border-bottom: 2px solid #ff2a22;
    padding: 1px 2px; border-radius: 2px; color: #6a4c00; font-weight: 600;
}}
#messageModal mark.mm-hl-player {{
    background: #d6e7f7; border-bottom: 2px solid #1f6bb8;
    padding: 1px 2px; border-radius: 2px; color: #0d3b6a; font-weight: 700;
}}
#messageModal .mm-legend {{
    font-size: 11px; color: #888; margin-top: 10px;
}}
#messageModal .mm-legend .pill {{
    display: inline-block; background: #fdf6c7; border-bottom: 2px solid #ff2a22;
    padding: 1px 6px; border-radius: 2px; margin-right: 4px; color: #6a4c00; font-weight: 600;
}}
#messageModal .mm-legend .pill-player {{
    background: #d6e7f7; border-bottom-color: #1f6bb8; color: #0d3b6a;
}}
.detail-table td.note-cell {{ cursor: pointer; }}
.detail-table tr:hover td.note-cell {{ background: #fff5f5; }}

.detail-container {{ padding: 20px 30px; display: none; }}
.player-select-wrapper {{ display: flex; align-items: center; gap: 14px; margin-bottom: 20px; }}
.player-select-wrapper label {{ font-weight: 600; font-size: 14px; color: #555; }}
.player-select {{
    padding: 10px 14px; font-size: 14px; border: 2px solid #ccc;
    border-radius: 6px; background: white; min-width: 250px; cursor: pointer;
}}
.player-select:focus {{ outline: none; border-color: #000000; }}

.player-summary {{
    display: flex; gap: 24px; margin-bottom: 20px; background: white;
    padding: 16px 24px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}}
.summary-item {{ display: flex; flex-direction: column; gap: 2px; }}
.summary-label {{ font-size: 11px; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
.summary-value {{ font-size: 20px; font-weight: 700; color: #000000; }}

.detail-table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    background: white; border-radius: 8px; overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1); font-size: 13px;
}}
.detail-table th {{
    background: #000000; color: white; font-weight: 600; padding: 12px 14px;
    text-align: left; font-size: 12px; letter-spacing: 0.3px;
}}
.detail-table td {{ padding: 10px 14px; border-bottom: 1px solid #eee; vertical-align: top; }}
.detail-table td:first-child {{ white-space: nowrap; font-weight: 500; width: 100px; }}
.detail-table td:nth-child(2) {{ white-space: nowrap; font-weight: 600; width: 60px; }}
.detail-table td:nth-child(3) {{ line-height: 1.5; color: #555; max-width: 600px; }}
.detail-table td:last-child {{ text-align: center; width: 70px; font-weight: 700; }}
.detail-table tbody tr:hover {{ background: #fafafa; }}

.score-badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; }}
.score-badge.s2 {{ background: #c6efce; color: #1a5e1a; }}
.score-badge.s1 {{ background: #e2efda; color: #3a6b30; }}
.score-badge.s0 {{ background: #fff2cc; color: #7a6b00; }}
.score-badge.sn1 {{ background: #fce4ec; color: #9a2020; }}
.score-badge.sn2 {{ background: #f4c7c3; color: #8b1a1a; }}

.clickable {{ cursor: pointer; }}
.clickable:hover {{ outline: 2px solid #000000; outline-offset: -2px; }}
.last-updated {{ font-size: 11px; opacity: 0.7; margin-top: 2px; }}

/* --- TABLET --- */
@media (max-width: 1024px) and (min-width: 769px) {{
    .header {{ padding: 14px 20px; }}
    .header h1 {{ font-size: 20px; }}
    .matrix-container {{ padding: 15px 10px; }}
    .matrix-table {{ font-size: 11px; }}
    .matrix-table th, .matrix-table td {{ padding: 7px 5px; }}
    .legend {{ padding: 8px 20px; font-size: 11px; }}
    .stats-bar {{ padding: 10px 20px; font-size: 12px; }}
}}

/* --- MOBILE --- */
@media (max-width: 768px) {{
    html, body {{ width: 100%; }}
    .header {{
        flex-direction: column; align-items: flex-start; gap: 10px; padding: 14px 16px;
    }}
    .header h1 {{ font-size: 18px; }}
    .header .subtitle {{ font-size: 11px; }}
    .nav-tabs {{ align-self: stretch; }}
    .nav-tab {{ flex: 1; text-align: center; padding: 6px 12px; font-size: 12px; }}

    .legend {{
        flex-wrap: wrap; gap: 6px 14px; padding: 8px 16px; font-size: 11px;
    }}
    .legend-title {{ width: 100%; margin-bottom: 2px; }}
    .legend-swatch {{ width: 14px; height: 14px; }}

    .stats-bar {{
        flex-wrap: wrap; gap: 8px 20px; padding: 8px 16px; font-size: 12px;
    }}

    .matrix-container {{ padding: 10px 4px; }}
    .matrix-scroll {{ max-height: 72vh; }}
    .matrix-table {{ font-size: 10px; }}
    .matrix-table th, .matrix-table td {{ padding: 5px 3px; height: 26px; }}
    .matrix-table thead tr:first-child th:nth-child(1), .matrix-table tbody td:nth-child(1) {{
        min-width: 100px; max-width: 100px; font-size: 10px; padding-left: 4px;
    }}

    .detail-container {{ padding: 12px 16px; }}
    .player-select {{ min-width: 200px; font-size: 13px; }}
    .player-summary {{ flex-wrap: wrap; gap: 12px; padding: 12px 16px; }}
    .summary-value {{ font-size: 16px; }}
    .detail-table td {{ padding: 8px 10px; font-size: 12px; }}
    .detail-table td:nth-child(3) {{ max-width: 250px; }}

    .login-box {{ min-width: 280px; padding: 30px 24px; }}
}}

/* --- Calendar view --- */
#calendarView {{ padding: 12px 16px; display: none; }}
.cal-toolbar {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }}
.cal-nav {{ display: flex; align-items: center; gap: 6px; }}
.cal-nav button {{
    padding: 6px 12px; font-size: 13px; font-weight: 600;
    background: #000000; color: white; border: none; border-radius: 6px; cursor: pointer;
}}
.cal-nav button:hover {{ background: #222222; }}
.cal-month-label {{ font-size: 16px; font-weight: 700; min-width: 150px; text-align: center; color: #000000; }}
.cal-addbtn {{
    padding: 6px 14px; font-size: 13px; font-weight: 600;
    background: #ff2a22; color: white; border: none; border-radius: 6px; cursor: pointer;
}}
.cal-addbtn:hover {{ background: #d4221a; }}
.cal-pdfbtn {{
    padding: 6px 14px; font-size: 13px; font-weight: 600;
    background: #000000; color: white; border: none; border-radius: 6px; cursor: pointer;
}}
.cal-pdfbtn:hover {{ background: #222222; }}
.cal-pdfbtn:disabled {{ background: #888; cursor: wait; }}
.cal-filter {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: #555; }}
.cal-filter select, .cal-filter input {{ padding: 4px 8px; font-size: 12px; border: 1px solid #ccc; border-radius: 4px; }}
.cal-multi {{ position: relative; display: inline-block; }}
.cal-multi-btn {{
    padding: 5px 10px; font-size: 12px; font-weight: 600;
    border: 1px solid #ccc; border-radius: 4px; background: white; color: #333;
    cursor: pointer; min-width: 140px; text-align: left;
    display: inline-flex; align-items: center; justify-content: space-between; gap: 6px;
}}
.cal-multi-btn:hover {{ border-color: #000000; }}
.cal-multi-btn .caret {{ font-size: 10px; color: #888; }}
.cal-multi-panel {{
    display: none; position: absolute; top: 100%; left: 0; z-index: 20; margin-top: 4px;
    background: white; border: 1px solid #ccc; border-radius: 6px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.12); min-width: 220px; max-height: 320px; overflow-y: auto;
    padding: 6px 0;
}}
.cal-multi.open .cal-multi-panel {{ display: block; }}
.cal-multi-header {{
    display: flex; gap: 6px; padding: 6px 10px; border-bottom: 1px solid #eee; margin-bottom: 4px;
}}
.cal-multi-ctl {{
    padding: 3px 10px; font-size: 11px; font-weight: 700; border-radius: 12px;
    border: 1.5px solid #ff2a22; background: white; color: #ff2a22; cursor: pointer; user-select: none;
}}
.cal-multi-ctl:hover {{ background: #fff7e0; }}
.cal-multi-item {{
    display: flex; align-items: center; gap: 8px; padding: 5px 12px; cursor: pointer;
    font-size: 12px; color: #333; user-select: none;
}}
.cal-multi-item:hover {{ background: #fff5f5; }}
.cal-multi-item input[type="checkbox"] {{ margin: 0; cursor: pointer; accent-color: #000000; }}
.cal-multi-empty {{ padding: 10px 12px; font-size: 12px; color: #888; font-style: italic; }}
.cal-grid {{
    display: grid; grid-template-columns: repeat(7, 1fr);
    border: 1px solid #d6d6d6; border-radius: 6px; overflow: hidden; background: #eee; gap: 1px;
}}
.cal-dow {{
    background: #000000; color: white; padding: 6px 8px; font-size: 11px; font-weight: 600;
    text-align: center; letter-spacing: 0.5px;
}}
.cal-cell {{
    background: white; min-height: 92px; padding: 4px 5px; position: relative;
    cursor: pointer; transition: background 0.12s;
}}
.cal-cell:hover {{ background: #fff5f5; }}
.cal-cell.other-month {{ background: #fafafa; color: #aaa; }}
.cal-cell.today {{ background: #fff0ed; }}
.cal-cell.today::before {{
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #ff2a22;
}}
.cal-daynum {{ font-size: 11px; color: #888; font-weight: 600; margin-bottom: 2px; }}
.cal-cell.today .cal-daynum {{ color: #ff2a22; }}
.cal-chip {{
    display: block; font-size: 10px; padding: 2px 5px; margin-bottom: 2px;
    border-radius: 3px; color: white; white-space: normal; overflow-wrap: anywhere;
    word-break: break-word; line-height: 1.25; cursor: pointer; font-weight: 600;
}}
/* Workout invites (default): lighter, hollow look */
.cal-chip.workout-invite {{
    background-color: transparent !important;
    color: inherit;
    border: 1.5px dashed var(--chip-color, #888);
    font-weight: 500;
}}
.cal-chip.workout-invite .chip-text {{ color: var(--chip-color, #333); }}
/* Confirmed workout: solid, bold, with check */
.cal-chip.workout-confirmed {{ font-weight: 800; box-shadow: 0 0 0 2px rgba(0,0,0,0.15) inset; }}
.cal-chip.tentative {{ opacity: 0.75; font-style: italic; }}
.cal-chip.manual::after {{ content: ' *'; opacity: 0.8; }}
.cal-legend {{ display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 10px; font-size: 10px; color: #666; }}
.cal-legend-item {{ display: flex; align-items: center; gap: 4px; }}
.cal-legend-swatch, .cal-legend-sw {{ width: 12px; height: 12px; border-radius: 3px; }}
.cal-pad {{ background: #fafafa !important; cursor: default !important; }}
.cal-pad:hover {{ background: #fafafa !important; }}
.cal-cell.cal-draft {{ background: #fff5e0; }}
.cal-cell.cal-today {{ background: #fff0ed; }}
.cal-cell.cal-today::before {{
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #ff2a22;
}}
.cal-drafttag {{
    display: inline-block; font-size: 8px; padding: 1px 4px; background: #ff2a22; color: white;
    border-radius: 2px; vertical-align: middle; font-weight: 700; letter-spacing: 0.5px;
}}

/* --- Event modal --- */
#evOverlay, #mrOverlay, #gameDetailsOverlay {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000;
    display: none; align-items: center; justify-content: center;
}}
#evOverlay.open, #mrOverlay.open, #gameDetailsOverlay.open {{ display: flex; }}
#evModal, #mrModal, #gameDetailsModal {{
    background: white; border-radius: 8px; padding: 20px 22px; width: 420px; max-width: 92vw;
    max-height: 90vh; overflow-y: auto; box-shadow: 0 6px 32px rgba(0,0,0,0.3);
}}
.gd-title {{ font-size: 16px; font-weight: 700; color: #12284b; margin-bottom: 4px; }}
.gd-sub {{ font-size: 11px; color: #888; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
.gd-row {{ display: flex; padding: 5px 0; border-bottom: 1px solid #f0f0f0; font-size: 12px; color: #333; }}
.gd-row:last-child {{ border-bottom: none; }}
.gd-label {{ width: 95px; flex-shrink: 0; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; font-size: 10px; padding-top: 1px; }}
.gd-close {{ margin-top: 14px; width: 100%; padding: 9px 14px; background: #000000; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; }}
.gd-close:hover {{ background: #222222; }}
.mr-addentry-btn {{
    padding: 5px 12px; font-size: 12px; font-weight: 700;
    background: #000000; color: white; border: none; border-radius: 4px; cursor: pointer;
    margin-left: auto;
}}
.mr-addentry-btn:hover {{ background: #222222; }}
.weight-toggle {{
    padding: 5px 10px; font-size: 11px; font-weight: 700; letter-spacing: 0.4px;
    background: white; color: #555; border: 1.5px solid #ccc; border-radius: 12px;
    cursor: pointer; user-select: none;
}}
.weight-toggle:hover {{ border-color: #000000; color: #000000; }}
.weight-toggle.on {{ background: #ff2a22; color: white; border-color: #ff2a22; }}
.weight-toggle.on:hover {{ background: #d4221a; border-color: #d4221a; }}
/* Attendee tier badge (detail-view rows) */
.tier-badge {{
    display: inline-block; font-size: 9px; font-weight: 800; letter-spacing: 0.5px;
    padding: 2px 6px; border-radius: 3px; text-transform: uppercase;
    margin-left: 6px; vertical-align: middle;
}}
.tier-badge.t1 {{ background: #000000; color: white; }}              /* GM / Pres Baseball Ops */
.tier-badge.t2 {{ background: #ff2a22; color: white; }}              /* SD / AGM / Special Asst / VP */
.tier-badge.t3 {{ background: #f59e0b; color: white; }}              /* National X'er */
.tier-badge.t4 {{ background: #6b7280; color: white; }}              /* Regional X'er */
.tier-badge.t5 {{ background: #9ca3af; color: white; }}              /* Area scout */
.mr-wd-row {{ display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }}
.mr-wd-row input[type="date"] {{ flex: 1; padding: 5px 8px; font-size: 12px; border: 1px solid #ccc; border-radius: 4px; }}
.mr-wd-del {{
    padding: 4px 9px; font-size: 12px; background: #eee; color: #666;
    border: 1px solid #ccc; border-radius: 4px; cursor: pointer;
}}
.mr-wd-del:hover {{ background: #f5d5d5; color: #a83030; border-color: #c94040; }}
.mr-wd-add {{
    padding: 5px 10px; font-size: 11px; font-weight: 600;
    background: #fff5f5; color: #000000; border: 1px dashed #000000; border-radius: 4px; cursor: pointer;
}}
.mr-wd-add:hover {{ background: #e0efd6; }}
.mm-edit-btn {{
    padding: 4px 10px; font-size: 11px; font-weight: 600; background: #ff2a22; color: white;
    border: none; border-radius: 4px; cursor: pointer; margin-left: 8px;
}}
.mm-edit-btn:hover {{ background: #d4221a; }}
.ev-title {{ font-size: 16px; font-weight: 700; color: #000000; margin-bottom: 14px; }}
.ev-row {{ display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }}
.ev-row label {{ font-size: 11px; font-weight: 600; color: #555; text-transform: uppercase; letter-spacing: 0.3px; }}
.ev-row input[type="text"], .ev-row input[type="date"], .ev-row input[type="time"],
.ev-row select, .ev-row textarea {{
    width: 100%; padding: 7px 10px; font-size: 13px; border: 1px solid #ccc; border-radius: 4px;
    font-family: inherit; box-sizing: border-box;
}}
.ev-row textarea {{ resize: vertical; min-height: 60px; }}
.ev-row.cb {{ flex-direction: row; align-items: center; gap: 6px; }}
.ev-row.cb label {{ text-transform: none; letter-spacing: 0; margin: 0; }}
.ev-btns {{ display: flex; gap: 8px; margin-top: 16px; }}
.ev-save {{ flex: 1; padding: 9px 14px; background: #000000; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; }}
.ev-save:hover {{ background: #222222; }}
.ev-cancel {{ padding: 9px 14px; background: #eee; color: #333; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; }}
.ev-delete {{ padding: 9px 14px; background: #c94040; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; margin-right: auto; }}
.ev-delete:hover {{ background: #a83030; }}
.ev-slack {{ padding: 9px 14px; background: #4a154b; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; margin-right: auto; }}
.ev-slack:hover {{ background: #611f62; }}
.ev-clear {{ padding: 9px 14px; background: #ff2a22; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; margin-right: auto; }}
.ev-clear:hover {{ background: #d4221a; }}
.ev-note {{ font-size: 11px; color: #888; margin-top: 6px; }}

/* --- Mobile agenda view (calendar) --- */
.cal-agenda {{ display: none; }}
.agenda-day {{
    display: flex; align-items: flex-start; gap: 10px;
    padding: 10px 12px; border-bottom: 1px solid #e8e8e8; background: white;
}}
.agenda-day:first-child {{ border-top: 1px solid #e8e8e8; }}
.agenda-day.agenda-draft {{ background: #fff5e0; }}
.agenda-date {{
    flex-shrink: 0; width: 52px; text-align: center; padding: 4px 0;
    background: #fafafa; border-radius: 6px;
}}
.agenda-dow {{ font-size: 10px; font-weight: 700; color: #888; letter-spacing: 0.5px; }}
.agenda-dnum {{ font-size: 22px; font-weight: 800; color: #000000; line-height: 1; }}
.agenda-drafttag {{
    display: inline-block; font-size: 8px; padding: 1px 4px; background: #ff2a22; color: white;
    border-radius: 2px; font-weight: 700; letter-spacing: 0.5px; margin-top: 2px;
}}
.agenda-chips {{ flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 0; }}
.agenda-chips .cal-chip {{ font-size: 12px; padding: 6px 10px; white-space: normal; }}
.agenda-empty {{ padding: 30px 20px; text-align: center; color: #888; font-size: 13px; }}
.agenda-none {{ font-size: 11px; color: #888; font-style: italic; padding: 4px 0; }}

@media (max-width: 640px) {{
    #calendarView {{ padding: 8px 0; }}
    .cal-toolbar {{ gap: 8px; padding: 0 12px; }}
    .cal-month-label {{ font-size: 14px; min-width: 110px; }}
    .cal-nav button {{ padding: 8px 10px; }}
    .cal-addbtn {{ padding: 8px 12px; }}
    .cal-filter {{ flex: 1 1 100%; }}
    .cal-filter select {{ flex: 1; min-width: 0; }}
    .cal-filter.cal-multi {{ display: flex; align-items: center; gap: 6px; }}
    .cal-multi {{ width: 100%; }}
    .cal-multi-btn {{ flex: 1; min-width: 0; padding: 9px 12px; font-size: 13px; }}
    .cal-multi-panel {{ left: 0; right: 0; min-width: 0; max-height: 60vh; }}
    .cal-multi-item {{ padding: 10px 14px; font-size: 14px; }}
    .cal-multi-item input[type="checkbox"] {{ width: 18px; height: 18px; }}
    .cal-multi-ctl {{ padding: 6px 12px; font-size: 12px; }}
    .cal-grid {{ display: none; }}
    .cal-agenda {{ display: block; }}
    .cal-legend {{ padding: 0 12px; }}
}}
</style>
<script src="https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.1/dist/html2pdf.bundle.min.js"></script>
</head>
<body>

<!-- PASSWORD GATE -->
<div id="loginGate">
    <div class="login-box">
        <img src="/sv-logo.svg" alt="Stadium Ventures" class="logo-img">
        <div class="brand-name">Team<span class="accent">Intel</span></div>
        <div class="tagline">2026 MLB Draft Intelligence</div>
        <input type="password" id="pwInput" placeholder="Enter password" onkeydown="if(event.key==='Enter')checkPw()">
        <button onclick="checkPw()">Access Dashboard</button>
        <div class="login-error" id="loginError">Incorrect password. Try again.</div>
    </div>
</div>
<script>
var attempts = 0;
function checkPw() {{
    var val = document.getElementById('pwInput').value;
    var errEl = document.getElementById('loginError');
    if (val === '{password}') {{
        document.getElementById('loginGate').classList.add('hidden');
        document.getElementById('appContent').classList.add('visible');
        sessionStorage.setItem('sv_auth', '1');
    }} else {{
        attempts++;
        if (attempts >= 5) {{
            errEl.textContent = 'Too many failed attempts. Please contact your administrator.';
            document.getElementById('pwInput').disabled = true;
            document.querySelector('.login-box button').disabled = true;
            document.querySelector('.login-box button').style.opacity = '0.5';
        }} else {{
            errEl.textContent = 'Incorrect password. Please try again. (' + (5 - attempts) + ' attempts remaining)';
        }}
        errEl.style.display = 'block';
        document.getElementById('pwInput').value = '';
        var box = document.querySelector('.login-box');
        box.classList.remove('shake');
        void box.offsetWidth;
        box.classList.add('shake');
    }}
}}
// Auto-login from session is handled after full page load
</script>

<!-- DASHBOARD (hidden until auth) -->
<div id="appContent">

<div class="header">
    <div class="header-left">
        <div class="logo-icon"><img src="/sv-logo-white.svg" alt="Stadium Ventures"></div>
        <div>
            <h1>TeamIntel Dashboard</h1>
            <div class="subtitle">Player Intelligence Score By Team &mdash; 2026 MLB Draft</div>
            <div class="last-updated">Last updated: {now_str}</div>
        </div>
    </div>
    <div class="nav-tabs">
        <div class="nav-tab active" onclick="showView('matrix')">Matrix View</div>
        <div class="nav-tab" onclick="showView('detail')">Detail View</div>
        <div class="nav-tab" onclick="goToCalendar()">Calendar</div>
    </div>
</div>

<div class="legend">
    <div class="legend-item"><div class="legend-swatch" style="background:#fff;box-shadow:inset 0 0 0 3px #d4a017"></div>Pre-Draft Workout</div>
    <span class="legend-title" style="margin-left:18px;">Points:</span>
    <span style="font-size:11px;color:#666;">GM 5 &middot; Dir 4 &middot; NXC 3 &middot; X 2 &middot; Area 1</span>
</div>

<div id="statsBar" class="stats-bar"></div>

<div id="matrixView" class="matrix-container">
    <div class="matrix-scroll" id="matrixScroll">
        <table class="matrix-table" id="matrixTable"></table>
    </div>
</div>

<div id="detailView" class="detail-container">
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px;">
        <button onclick="showView('matrix')" style="padding:6px 14px;font-size:13px;font-weight:600;background:#000000;color:white;border:none;border-radius:6px;cursor:pointer;">&#8592; Back</button>
        <button onclick="jumpToCalendarForCurrentPlayer()" style="padding:6px 14px;font-size:13px;font-weight:600;background:#ff2a22;color:white;border:none;border-radius:6px;cursor:pointer;" title="Show this player's workouts on the calendar">&#x1F4C5; View Calendar</button>
        <button onclick="openManualEntryForCurrentPlayer()" style="padding:6px 14px;font-size:13px;font-weight:600;background:#000000;color:white;border:none;border-radius:6px;cursor:pointer;" title="Add a manual entry for this player">&#x2B; Add Entry</button>
        <div class="player-select-wrapper" style="margin-bottom:0;">
            <label>Select Player:</label>
            <select class="player-select" id="playerSelect" onchange="_filterTeam=null; renderDetail()">
                <option value="">-- Choose a player --</option>
            </select>
        </div>
    </div>
    <div id="playerSummary" class="player-summary"></div>
    <div id="hiddenBar"></div>
    <table class="detail-table" id="detailTable"></table>
</div>

<div id="calendarView">
    <div class="cal-toolbar">
        <div class="cal-nav">
            <button onclick="calShiftMonth(-1)" title="Previous month">&#8592;</button>
            <div class="cal-month-label" id="calMonthLabel"></div>
            <button onclick="calShiftMonth(1)" title="Next month">&#8594;</button>
            <button onclick="calJumpTo('today')" title="Jump to today" style="margin-left:6px;">Today</button>
        </div>
        <button class="cal-addbtn" onclick="openEventModal(null, null)">+ Add Event</button>
        <button class="cal-pdfbtn" onclick="exportCalendarPDF()" title="Download this month as PDF">&#x2B07; PDF</button>
        <div class="cal-filter cal-multi" id="calPlayerDropdown">
            <label>Players:</label>
            <button type="button" class="cal-multi-btn" onclick="event.stopPropagation(); toggleCalPlayerPanel()">
                <span id="calPlayerBtnLabel">All</span><span class="caret">&#9662;</span>
            </button>
            <div class="cal-multi-panel" id="calPlayerPanel" onclick="event.stopPropagation()">
                <div class="cal-multi-header">
                    <span class="cal-multi-ctl" onclick="calSelectAllPlayers()">All</span>
                    <span class="cal-multi-ctl" onclick="calSelectNoPlayers()">None</span>
                </div>
                <div id="calPlayerChips"></div>
            </div>
        </div>
        <div class="cal-filter">
            <label for="calTypeFilter">Type:</label>
            <select id="calTypeFilter" onchange="renderCalendar()">
                <option value="">All</option>
                <option value="workout">Workouts</option>
                <option value="game">Games</option>
                <option value="other">Other</option>
            </select>
        </div>
    </div>
    <div class="cal-grid" id="calGrid"></div>
    <div class="cal-agenda" id="calAgenda"></div>
    <div class="cal-legend" id="calLegend"></div>
    <div style="margin-top:10px;font-size:11px;color:#888;">
        Workouts are auto-parsed from Slack messages. Click a chip to view/edit; use <b>+ Add Event</b> for new entries.
        <span style="opacity:0.8;display:inline-block;margin-left:10px;">
            <span style="display:inline-block;padding:1px 6px;border:1.5px dashed #000000;color:#000000;border-radius:3px;font-size:10px;font-weight:500;">DASHED</span> = invite &nbsp;·&nbsp;
            <span style="display:inline-block;padding:1px 6px;background:#000000;color:white;border-radius:3px;font-size:10px;font-weight:800;">&#10003; SOLID</span> = confirmed going &nbsp;·&nbsp;
            <span>"*" = manually edited</span>
        </span>
    </div>
</div>

</div><!-- /appContent -->

<div id="evOverlay" onclick="if(event.target===this) closeEventModal()">
    <div id="evModal">
        <div class="ev-title" id="evTitle">Add Event</div>
        <div class="ev-row">
            <label>Date</label>
            <input type="date" id="evDate" min="2026-04-01" max="2026-08-31">
        </div>
        <div class="ev-row">
            <label>Type</label>
            <select id="evType" onchange="evSyncType()">
                <option value="workout">Pre-Draft Workout</option>
                <option value="other">Other</option>
            </select>
        </div>
        <div class="ev-row">
            <label>Player</label>
            <select id="evPlayer"></select>
        </div>
        <div class="ev-row" id="evTeamRow">
            <label>Team</label>
            <select id="evTeam"><option value="">—</option></select>
        </div>
        <div class="ev-row" id="evTitleRow" style="display:none;">
            <label>Title</label>
            <input type="text" id="evTitleInput" placeholder="e.g. ACC Championship">
        </div>
        <div class="ev-row">
            <label>Time (optional)</label>
            <input type="text" id="evTime" placeholder="e.g. 11am, 9:30 AM">
        </div>
        <div class="ev-row">
            <label>Location (optional)</label>
            <input type="text" id="evLocation" placeholder="e.g. Port St Lucie">
        </div>
        <div class="ev-row cb" id="evConfirmedRow">
            <input type="checkbox" id="evConfirmed">
            <label for="evConfirmed"><strong>Confirmed — player is going</strong> (unchecked = invite only)</label>
        </div>
        <div class="ev-row cb">
            <input type="checkbox" id="evTentative">
            <label for="evTentative">Tentative date (from Slack)</label>
        </div>
        <div class="ev-row">
            <label>Notes (optional)</label>
            <textarea id="evNotes"></textarea>
        </div>
        <div class="ev-btns">
            <button class="ev-delete" id="evDeleteBtn" onclick="deleteEvent()" style="display:none;">Delete</button>
            <button class="ev-clear" id="evClearBtn" onclick="clearEventChanges()" style="display:none;" title="Remove manual override; restore auto-parsed version">Clear Changes</button>
            <button class="ev-slack" id="evSlackBtn" onclick="openSlackFromEvent()" style="display:none;" title="Open the originating Slack message">&#x1F4AC; View Slack Message</button>
            <button class="ev-cancel" onclick="closeEventModal()">Cancel</button>
            <button class="ev-save" onclick="saveEvent()">Save</button>
        </div>
        <div class="ev-note" id="evNote"></div>
    </div>
</div>

<script>
const RECORDS = {records_js};
const GAMES_SCHEDULE = {games_js};
const ALL_TEAMS = {json.dumps(ALL_TEAMS)};
const ALL_2026_PLAYERS = {all_2026_js};
const PLAYER_ALIASES = {player_aliases_js};
const TEAM_DRAFT = {team_draft_js};

// --- Override system (Vercel KV) — per-record overrides ---
var scoreOverrides = {{}};
var _popupPlayer = '', _popupTeam = '', _popupDate = '';
var _showHidden = false;
var _filterTeam = null;

var _toastTimer = null;
function showToast(msg, ok) {{
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.className = (ok ? 'ok ' : '') + 'visible';
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function() {{ el.className = ok ? 'ok' : ''; }}, ok ? 2000 : 5000);
}}

async function loadOverrides() {{
    try {{
        const res = await fetch('/api/overrides');
        if (!res.ok) {{
            const body = await res.text();
            showToast('Could not load overrides (' + res.status + '). Manual edits may not persist. ' + body.slice(0, 120));
            return;
        }}
        scoreOverrides = await res.json();
    }} catch(e) {{
        showToast('Could not reach overrides API. Manual edits may not persist.');
    }}
}}

function getScore(r) {{
    const ok = r.player + '|' + r.team + '|' + r.date;
    return scoreOverrides.hasOwnProperty(ok) ? scoreOverrides[ok] : r.score;
}}

// Manual tier-points override key: 't|player|team|date' → integer 0-5.
// Falls back to the parser's auto-detected r.tier_multiplier.
function getPoints(r) {{
    const tk = 't|' + r.player + '|' + r.team + '|' + r.date;
    if (scoreOverrides.hasOwnProperty(tk)) {{
        const v = scoreOverrides[tk];
        if (typeof v === 'number') return v;
    }}
    return (typeof r.tier_multiplier === 'number') ? r.tier_multiplier : 0;
}}

function isPointsOverridden(r) {{
    return scoreOverrides.hasOwnProperty('t|' + r.player + '|' + r.team + '|' + r.date);
}}

function isExcluded(r) {{
    return getScore(r) === 'NA';
}}

// --- Message modal (click a row's note to see full message + highlighted PDW trigger) ---
var _modalIndex = {{}};

function _escapeHtml(s) {{
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}}

function _highlightMatches(text, phraseGroups) {{
    // phraseGroups: list of groups — each has phrases[], cls, wholeWord
    if (!phraseGroups || !phraseGroups.length) return _escapeHtml(text);
    const lc = text.toLowerCase();
    const ranges = [];
    phraseGroups.forEach(function(g) {{
        (g.phrases || []).slice().sort((a,b) => b.length - a.length).forEach(function(p) {{
            if (!p) return;
            var needle = p.toLowerCase();
            var idx = 0;
            while ((idx = lc.indexOf(needle, idx)) !== -1) {{
                if (g.wholeWord) {{
                    var before = idx === 0 ? '' : lc[idx-1];
                    var after = (idx + needle.length) >= lc.length ? '' : lc[idx + needle.length];
                    var isBoundary = function(c) {{ return !c || !/[a-z0-9]/.test(c); }};
                    if (!isBoundary(before) || !isBoundary(after)) {{ idx += 1; continue; }}
                }}
                ranges.push({{start: idx, end: idx + needle.length, cls: g.cls}});
                idx += needle.length;
            }}
        }});
    }});
    if (!ranges.length) return _escapeHtml(text);
    // Sort by start; for overlaps, keep PDW highlight (mm-hl) over player (mm-hl-player) when tied.
    ranges.sort(function(a,b){{
        if (a.start !== b.start) return a.start - b.start;
        return (b.end - b.start) - (a.end - a.start);
    }});
    // Drop ranges overlapped by earlier kept range.
    const kept = [];
    ranges.forEach(function(r) {{
        if (kept.length && r.start < kept[kept.length-1].end) return;
        kept.push(r);
    }});
    var out = '', cursor = 0;
    kept.forEach(function(r) {{
        out += _escapeHtml(text.slice(cursor, r.start));
        out += '<mark class="' + r.cls + '">' + _escapeHtml(text.slice(r.start, r.end)) + '</mark>';
        cursor = r.end;
    }});
    out += _escapeHtml(text.slice(cursor));
    return out;
}}

function openMessageModal(rowKey) {{
    const r = _modalIndex[rowKey];
    if (!r) return;
    _mmCurrentRecord = r;
    // Default: no back button. openSlackFromEvent sets it after this call.
    _mmReturnToEvent = null;
    const bb = document.getElementById('mmBackBtn');
    if (bb) bb.style.display = 'none';
    const body = (r.full_text && r.full_text.length > (r.note || '').length) ? r.full_text : r.note;
    const isPDWrow = !!r.workout;
    const playerAliases = (PLAYER_ALIASES[r.player] || []).concat([r.player]);
    document.getElementById('mmTitle').textContent = r.player + ' · ' + r.team;
    // Header: "Manual Entry" for manually-added records (with Edit button); otherwise the default Slack label.
    const header = document.getElementById('mmHeader');
    const editBtn = document.getElementById('mmEditBtn');
    if (r.is_manual) {{
        header.childNodes[0].nodeValue = 'Manual Entry ';
        if (editBtn) editBtn.style.display = 'inline-block';
        document.getElementById('mmMeta').textContent = r.date +
            (isPDWrow ? ' · PDW flagged' : '');
    }} else {{
        header.childNodes[0].nodeValue = 'Full Slack Message ';
        if (editBtn) editBtn.style.display = 'none';
        document.getElementById('mmMeta').textContent = r.date + ' · #' + (r.channel || 'unknown') +
            (isPDWrow ? ' · PDW flagged' : '');
    }}
    const groups = [
        // Draw PDW highlight first (it takes priority on overlap).
        {{ phrases: r.workout_matches || [], cls: 'mm-hl', wholeWord: false }},
        {{ phrases: playerAliases, cls: 'mm-hl-player', wholeWord: true }},
    ];
    document.getElementById('mmBody').innerHTML = _highlightMatches(body || '', groups);
    document.getElementById('mmLegend').innerHTML =
        '<span class="pill pill-player">' + r.player.split(' ')[0] + '</span> = player mentions' +
        (isPDWrow && (r.workout_matches || []).length
            ? ' &nbsp;·&nbsp; <span class="pill">highlighted</span> = text that triggered the PDW flag'
            : '');
    document.getElementById('mmLegend').style.display = 'block';
    document.getElementById('messageOverlay').classList.add('visible');
}}

function closeMessageModal() {{
    document.getElementById('messageOverlay').classList.remove('visible');
    _mmReturnToEvent = null;
    const bb = document.getElementById('mmBackBtn');
    if (bb) bb.style.display = 'none';
}}

document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') closeMessageModal();
}});

async function saveScore(score) {{
    const player = _popupPlayer, team = _popupTeam, date = _popupDate;
    const key = player + '|' + team + '|' + date;
    const tKey = 't|' + key;
    const isReset = (score === null);
    closeScorePopup();
    try {{
        const res = await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ player, team, date, score }})
        }});
        if (!res.ok) {{
            const body = await res.text();
            showToast('Save failed (' + res.status + '). ' + body.slice(0, 120));
            return;
        }}
        if (isReset) {{
            delete scoreOverrides[key];
        }} else {{
            scoreOverrides[key] = score;
        }}
        // "Reset to original" should also clear any manual points override.
        if (isReset && scoreOverrides.hasOwnProperty(tKey)) {{
            await fetch('/api/overrides', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ key: tKey, score: null }})
            }});
            delete scoreOverrides[tKey];
        }}
        showToast('Saved', true);
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    renderMatrix();
    renderDetail();
}}

// Manual tier-points override (popup buttons 5/4/3/2/1/0).
async function savePoints(points) {{
    const player = _popupPlayer, team = _popupTeam, date = _popupDate;
    const tKey = 't|' + player + '|' + team + '|' + date;
    closeScorePopup();
    try {{
        const res = await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ key: tKey, score: points }})
        }});
        if (!res.ok) {{
            const body = await res.text();
            showToast('Save failed (' + res.status + '). ' + body.slice(0, 120));
            return;
        }}
        scoreOverrides[tKey] = points;
        showToast('Saved', true);
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    renderMatrix();
    renderDetail();
}}

function isPDW(player, team) {{
    var wk = 'w|' + player + '|' + team;
    if (scoreOverrides.hasOwnProperty(wk)) return scoreOverrides[wk];
    var hasAuto = false;
    RECORDS.forEach(function(r) {{ if (r.player === player && r.team === team && r.workout) hasAuto = true; }});
    return hasAuto;
}}

async function togglePDW() {{
    var wk = 'w|' + _popupPlayer + '|' + _popupTeam;
    var hasAuto = false;
    RECORDS.forEach(function(r) {{ if (r.player === _popupPlayer && r.team === _popupTeam && r.workout) hasAuto = true; }});
    var current = isPDW(_popupPlayer, _popupTeam);
    var newVal = !current;
    // If the new value matches the auto-detected state, clear the override.
    // Otherwise persist the explicit true/false so an auto-true flag can be turned off.
    var toStore = (newVal === hasAuto) ? null : newVal;
    try {{
        const res = await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ key: wk, score: toStore }})
        }});
        if (!res.ok) {{
            const body = await res.text();
            showToast('Save failed (' + res.status + '). ' + body.slice(0, 120));
            return;
        }}
        if (toStore === null) {{
            delete scoreOverrides[wk];
        }} else {{
            scoreOverrides[wk] = toStore;
        }}
        showToast('Saved', true);
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    updatePDWButton();
    renderMatrix();
    renderDetail();
    // Reflect the PDW flip on the calendar immediately (no rebuild / refresh needed).
    if (window._calInitialized) {{ buildAutoEvents(); renderCalendar(); }}
}}

function updatePDWButton() {{
    var btn = document.getElementById('pdwToggle');
    if (isPDW(_popupPlayer, _popupTeam)) {{
        btn.classList.add('active');
        btn.textContent = '\\u2713 Pre-Draft Workout';
    }} else {{
        btn.classList.remove('active');
        btn.textContent = 'Pre-Draft Workout';
    }}
}}

function openScorePopup(player, team, date, event) {{
    _popupPlayer = player;
    _popupTeam = team;
    _popupDate = date;
    document.getElementById('popupTitle').textContent = player + ' \\u2014 ' + team + ' (' + date + ')';
    // Render the team's 2026 bonus pool + first 5 picks (if available).
    const tInfo = TEAM_DRAFT[team];
    const tBox = document.getElementById('popupTeamInfo');
    if (tInfo && (tInfo.pool || (tInfo.picks && tInfo.picks.length))) {{
        const picks = (tInfo.picks || []).slice(0, 5).join(', ') || '—';
        tBox.innerHTML =
            '<div class="pti-row"><span class="pti-label">Pool:</span><span class="pti-pool">' + (tInfo.pool ? fmtPool(tInfo.pool) : '—') + '</span></div>' +
            '<div class="pti-row"><span class="pti-label">Picks:</span><span class="pti-picks">' + picks + '</span></div>';
        tBox.style.display = 'block';
    }} else {{
        tBox.style.display = 'none';
    }}
    updatePDWButton();
    var popup = document.getElementById('scorePopup');
    var overlay = document.getElementById('scoreOverlay');
    popup.style.display = 'block';
    overlay.style.display = 'block';
    var rect = event.target.getBoundingClientRect();
    var x = rect.left + rect.width / 2 - 110;
    var y = rect.bottom + 6;
    if (x < 8) x = 8;
    if (x + 220 > window.innerWidth) x = window.innerWidth - 228;
    if (y + 280 > window.innerHeight) y = Math.max(8, rect.top - 280);
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';
}}

function closeScorePopup() {{
    document.getElementById('scorePopup').style.display = 'none';
    document.getElementById('scoreOverlay').style.display = 'none';
}}

// Matrix-cell color comes from the literal color word in the most recent
// message for that (player, team). No sentiment aggregation. No gradient.
const COLOR_BG = {{
    'green':       'rgb(130, 200, 140)',
    'light green': 'rgb(200, 230, 180)',
    'yellow':      'rgb(252, 232, 130)',
    'orange':      'rgb(245, 160, 95)',
    'red':         'rgb(225, 110, 105)'
}};

// Pool amounts come from the org-review xlsx as "$13.60m" etc. — trim to one
// decimal for display ("$13.6m"). Color math still uses the raw value.
function fmtPool(s) {{
    if (!s) return '';
    const m = String(s).match(/^\\$?([\\d.]+)\\s*([a-z]*)$/i);
    if (!m) return s;
    return '$' + parseFloat(m[1]).toFixed(1) + (m[2] ? m[2].toUpperCase() : 'M');
}}

// Bonus-pool color scale: brighter green = more $ to spend, muted red = less.
// 2026 MLB pool range is ~$3.95m (LAD) to ~$19.13m (PIT). Anchored to that
// span so the gradient hugs the actual data; values outside clamp.
function poolTextColor(poolStr) {{
    if (!poolStr) return '#fff';
    const m = String(poolStr).match(/([\\d.]+)/);
    if (!m) return '#fff';
    const v = parseFloat(m[1]);
    const lo = 4, hi = 19;
    const t = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    if (t >= 0.5) {{
        // mid → high: white → bright green
        const u = (t - 0.5) * 2;
        const r = Math.round(255 - 165 * u);
        const g = 255;
        const b = Math.round(255 - 145 * u);
        return 'rgb(' + r + ',' + g + ',' + b + ')';
    }} else {{
        // mid → low: white → muted red
        const u = (0.5 - t) * 2;
        const r = 255;
        const g = Math.round(255 - 130 * u);
        const b = Math.round(255 - 130 * u);
        return 'rgb(' + r + ',' + g + ',' + b + ')';
    }}
}}

function buildMatrix() {{
    // Number = sum of attendee-tier points across all touches for that
    // (player, team) cell (GM=+5, Dir=+4, NXC=+3, X=+2, Area=+1, T0=0).
    // Color = literal color word from the most recent record with one set.
    // Total column = sum of points across teams; ranks players by who has been
    // seen the most by the most senior people.
    const activeRecords = RECORDS.filter(r => !isExcluded(r));
    const cellPoints = {{}};       // key -> sum of tier points
    const cellLatestColor = {{}};  // key -> {{date, color}} of most-recent colored record
    const workoutMap = {{}};

    activeRecords.forEach(r => {{
        const key = r.player + '|' + r.team;
        cellPoints[key] = (cellPoints[key] || 0) + getPoints(r);
        if (r.color) {{
            const cur = cellLatestColor[key];
            if (!cur || (r.date || '') > (cur.date || '')) {{
                cellLatestColor[key] = {{ date: r.date || '', color: r.color }};
            }}
        }}
        if (r.workout) workoutMap[key] = true;
    }});
    // Manual PDW overrides (matrix popup) still apply to the workout map.
    Object.keys(scoreOverrides).forEach(k => {{
        if (k.startsWith('w|')) {{
            const parts = k.substring(2);
            if (scoreOverrides[k]) workoutMap[parts] = true;
            else delete workoutMap[parts];
        }}
    }});

    const playerTeams = {{}}, playerTeamColors = {{}}, playerTotals = {{}};
    Object.keys(cellPoints).forEach(key => {{
        const [player, team] = key.split('|');
        if (!playerTeams[player]) playerTeams[player] = {{}};
        if (!playerTeamColors[player]) playerTeamColors[player] = {{}};
        playerTeams[player][team] = cellPoints[key];
        if (cellLatestColor[key]) playerTeamColors[player][team] = cellLatestColor[key].color;
        playerTotals[player] = (playerTotals[player] || 0) + cellPoints[key];
    }});
    // Ensure every roster player has an entry even if no records yet.
    ALL_2026_PLAYERS.forEach(p => {{
        if (!playerTeams[p]) playerTeams[p] = {{}};
        if (!playerTeamColors[p]) playerTeamColors[p] = {{}};
        if (playerTotals[p] === undefined) playerTotals[p] = 0;
    }});
    // Sort primarily by # of teams the player has a color from (more colored
    // cells = more concrete signal). Tiebreak by total points, then alpha.
    const coloredTeamCount = {{}};
    Object.keys(playerTeamColors).forEach(p => {{
        coloredTeamCount[p] = Object.keys(playerTeamColors[p] || {{}}).length;
    }});
    const sortedPlayers = Object.keys(playerTotals).sort((a,b) => {{
        const ca = coloredTeamCount[a] || 0, cb = coloredTeamCount[b] || 0;
        if (cb !== ca) return cb - ca;
        const ta = playerTotals[a] || 0, tb = playerTotals[b] || 0;
        if (tb !== ta) return tb - ta;
        return a.localeCompare(b);
    }});
    return {{ playerTeams, playerTeamColors, playerTotals, sortedPlayers, workoutMap, coloredTeamCount }};
}}

function scoreClass(s) {{
    if (typeof s !== 'number') return '';
    // Range-based buckets so fractional scores (e.g. tier floor 0.5 / 1.5) land right.
    if (s >= 1.5) return 'score-2';
    if (s >= 0.5) return 'score-1';
    if (s >= -0.5) return 'score-0';
    if (s >= -1.5) return 'score-n1';
    return 'score-n2';
}}
function fmtScore(s) {{
    if (s === 'NA') return 'NA';
    if (typeof s !== 'number') return String(s);
    // Drop trailing .0 so integers still render cleanly (1 not 1.0).
    return (s % 1 === 0) ? String(s) : s.toFixed(1);
}}

function renderMatrix() {{
    const {{ playerTeams, playerTeamColors, playerTotals, sortedPlayers, workoutMap }} = buildMatrix();

    var html = '<thead><tr><th rowspan="2">Client</th>';
    ALL_TEAMS.forEach(t => html += '<th>' + t + '</th>');
    html += '</tr><tr>';
    ALL_TEAMS.forEach(t => {{
        const info = TEAM_DRAFT[t];
        if (info) {{
            const pool = info.pool || '';
            const picks = (info.picks || []).slice(0, 5).join(', ');
            const poolStyle = pool ? ' style="color:' + poolTextColor(pool) + ';"' : '';
            const picksHtml = picks
                ? '<div class="ti-picks"><span class="ti-picks-label">PICKS</span>' + picks + '</div>'
                : '';
            html += '<th class="team-info"><div class="ti-pool"' + poolStyle + '>' + fmtPool(pool) + '</div>' + picksHtml + '</th>';
        }} else {{
            html += '<th class="team-info"></th>';
        }}
    }});
    html += '</tr></thead><tbody>';

    sortedPlayers.forEach(player => {{
        const total = playerTotals[player] || 0;
        const rowTitle = ' title="' + total + ' total point' + (total === 1 ? '' : 's') + ' (GM=5, Dir=4, NXC=3, X=2, Area=1)"';
        const esc = player.replace(/'/g, "\\\\'");
        html += '<tr' + rowTitle + '>';
        html += '<td class="clickable" onclick="jumpToDetail(\\'' + esc + '\\')">' + player + '</td>';
        ALL_TEAMS.forEach(team => {{
            const pts = playerTeams[player] && playerTeams[player][team];
            const colorWord = playerTeamColors[player] && playerTeamColors[player][team];
            const wk = workoutMap[player + '|' + team];
            const hasData = (typeof pts === 'number' && pts > 0);
            if (hasData || colorWord || wk) {{
                const bg = colorWord ? COLOR_BG[colorWord] : '';
                const cellStyle = bg ? 'background:' + bg + ';' : '';
                const display = (typeof pts === 'number' && pts > 0) ? String(pts) : '';
                const title = (pts || 0) + ' point' + (pts === 1 ? '' : 's') + (colorWord ? ' \\u2022 latest: ' + colorWord : '');
                html += '<td class="score-cell clickable' + (wk ? ' workout' : '') + '" style="' + cellStyle + '" onclick="jumpToDetail(\\'' + esc + '\\', \\'' + team + '\\')" title="' + title + '">' + display + '</td>';
            }} else {{
                html += '<td></td>';
            }}
        }});
        html += '</tr>';
    }});
    html += '</tbody>';
    document.getElementById('matrixTable').innerHTML = html;

    let uniquePairs = 0;
    Object.keys(playerTeams).forEach(p => uniquePairs += Object.keys(playerTeams[p]).length);
    document.getElementById('statsBar').innerHTML =
        '<div class="stat-item"><span class="stat-label">Players:</span><span class="stat-value">' + sortedPlayers.length + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Intel Reports:</span><span class="stat-value">' + RECORDS.length + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Player-Team Connections:</span><span class="stat-value">' + uniquePairs + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Date Range:</span><span class="stat-value">Aug 2025 - Present</span></div>' +
        '<button class="mr-addentry-btn" onclick="openManualEntryModal(null, null, null)" title="Add a manual player-team connection">&#x2B;&nbsp;Add Entry</button>';
}}

function toggleHidden() {{
    _showHidden = !_showHidden;
    renderDetail();
}}

function renderDetail() {{
    const player = document.getElementById('playerSelect').value;
    if (!player) return;
    let allPr = RECORDS.filter(r => r.player === player).sort((a,b) => b.date.localeCompare(a.date));
    if (_filterTeam) allPr = allPr.filter(r => r.team === _filterTeam);
    const hiddenCount = allPr.filter(r => isExcluded(r)).length;
    const pr = _showHidden ? allPr : allPr.filter(r => !isExcluded(r));
    const visible = pr.filter(r => !isExcluded(r));
    const teams = new Set(visible.map(r => r.team));
    // Each touch contributes its tier-point value (GM=5, Dir=4, NXC=3, X=2, Area=1, T0=0).
    // Honors any manual point overrides (set via the score popup).
    const totalPoints = visible.reduce((a, r) => a + getPoints(r), 0);
    document.getElementById('playerSummary').innerHTML =
        '<div class="summary-item"><span class="summary-label">Player</span><span class="summary-value">' + player + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Intel Reports</span><span class="summary-value">' + visible.length + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Teams Connected</span><span class="summary-value">' + teams.size + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Total Points</span><span class="summary-value">' + (visible.length > 0 ? totalPoints : '-') + '</span></div>';

    let hiddenBar = '';
    if (_filterTeam) {{
        const tInfo = TEAM_DRAFT[_filterTeam];
        if (tInfo && (tInfo.pool || (tInfo.picks && tInfo.picks.length))) {{
            const picks = (tInfo.picks || []).slice(0, 5).join(', ');
            hiddenBar += '<div style="background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;padding:9px 13px;margin-bottom:8px;display:flex;flex-wrap:wrap;gap:18px;align-items:center;font-size:12px;">' +
                '<span style="color:#888;font-weight:700;font-size:10px;letter-spacing:0.5px;text-transform:uppercase;">' + _filterTeam + ' \\u2014 2026 Draft</span>' +
                (tInfo.pool ? '<div><span style="color:#888;font-weight:600;margin-right:6px;">Pool:</span><span style="font-weight:700;color:#1a5e1a;font-size:13px;">' + fmtPool(tInfo.pool) + '</span></div>' : '') +
                (picks ? '<div><span style="color:#888;font-weight:600;margin-right:6px;">Picks:</span><span style="font-weight:600;color:#222;letter-spacing:0.3px;">' + picks + '</span></div>' : '') +
                '</div>';
        }}
        hiddenBar += '<div style="padding:6px 10px;font-size:12px;color:#555;margin-bottom:6px;">' +
            'Filtered to <strong>' + _filterTeam + '</strong> \\u00b7 ' +
            '<span style="text-decoration:underline;cursor:pointer;color:#000000;" onclick="clearTeamFilter()">show all teams</span></div>';
    }}
    if (hiddenCount > 0) {{
        const label = _showHidden ? 'hide' : 'show';
        hiddenBar += '<div style="padding:6px 10px;font-size:12px;color:#888;margin-bottom:6px;">' +
            hiddenCount + ' record' + (hiddenCount===1?'':'s') + ' hidden (marked NA) \\u00b7 ' +
            '<span style="text-decoration:underline;cursor:pointer;color:#000000;" onclick="toggleHidden()">' + label + '</span></div>';
    }}

    let html = '<thead><tr><th>Date</th><th>Team</th><th>Intel Note</th><th>Score</th></tr></thead><tbody>';
    if (pr.length === 0) {{
        html += '<tr><td colspan="4" style="text-align:center;color:#999;padding:20px;">No intel reports yet</td></tr>';
    }}
    pr.forEach((r, i) => {{
        const note = r.note.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>').replace(/&amp;/g,'&');
        const esc = r.player.replace(/'/g, "\\\\'");
        const isOverridden = scoreOverrides.hasOwnProperty(r.player + '|' + r.team + '|' + r.date);
        const excluded = isExcluded(r);
        const wBadge = !excluded && isPDW(r.player, r.team) ? '<span class="workout-badge">PDW</span>' : '';
        const rowKey = r.player + '|' + r.team + '|' + r.date + '|' + i;
        const rowStyle = excluded ? ' style="opacity:0.45;"' : '';
        // Score column = tier points for THIS touch (5/4/3/2/1/0). Plain badge
        // — color is decoupled from the matrix grid (which keys off color words).
        const tierPts = getPoints(r);
        const ptsOverridden = isPointsOverridden(r);
        const scoreDisp = excluded ? 'NA' : (String(tierPts) + (ptsOverridden ? ' *' : ''));
        const badgeCls = excluded ? 'score-na' : '';
        // Tier badge — shows when we detected a senior attendee (T1-T4). No badge for T5.
        const tier = r.attendee_tier;
        const tierLabel = r.tier_label || '';
        const tierBadge = (tier && tier >= 1 && tier <= 5 && tierLabel)
            ? '<span class="tier-badge t' + tier + '" title="Attendee tier: ' + tier + ' (×' + (r.tier_multiplier || 1) + ')">' + tierLabel + '</span>'
            : '';
        html += '<tr' + rowStyle + '><td>' + r.date + '</td><td>' + r.team + wBadge + tierBadge + '</td>' +
            '<td class="note-cell" onclick="openMessageModal(\\'' + rowKey + '\\')">' + note + '</td>' +
            '<td><span class="score-badge ' + badgeCls + '" style="cursor:pointer;" onclick="openScorePopup(\\'' + esc + '\\', \\'' + r.team + '\\', \\'' + r.date + '\\', event)">' + scoreDisp + '</span></td></tr>';
        _modalIndex[rowKey] = r;
    }});
    html += '</tbody>';
    document.getElementById('hiddenBar').innerHTML = hiddenBar;
    document.getElementById('detailTable').innerHTML = html;
}}

function jumpToDetail(player, team) {{
    document.getElementById('playerSelect').value = player;
    _filterTeam = team || null;
    renderDetail();
    showView('detail');
}}

function clearTeamFilter() {{
    _filterTeam = null;
    renderDetail();
}}

// Calendar tab click — always snap to the current month so a fresh look at
// the calendar starts "today", not wherever a prior detail-jump landed it.
function goToCalendar() {{
    const now = new Date();
    _calMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    showView('calendar');
    if (window._calInitialized) renderCalendar();
}}

function showView(view) {{
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    const mx = document.getElementById('matrixView');
    const dt = document.getElementById('detailView');
    const cl = document.getElementById('calendarView');
    mx.style.display = 'none'; dt.style.display = 'none'; cl.style.display = 'none';
    if (view === 'matrix') {{
        mx.style.display = 'block';
        document.querySelectorAll('.nav-tab')[0].classList.add('active');
    }} else if (view === 'detail') {{
        dt.style.display = 'block';
        document.querySelectorAll('.nav-tab')[1].classList.add('active');
    }} else if (view === 'calendar') {{
        cl.style.display = 'block';
        document.querySelectorAll('.nav-tab')[2].classList.add('active');
        if (!window._calInitialized) {{ initCalendar(); }}
    }}
}}

// ================= Calendar =================
const TEAM_COLORS = {{
    'ARI':'#A71930','ATL':'#CE1141','BAL':'#DF4601','BOS':'#BD3039','CHC':'#0E3386',
    'CWS':'#27251F','CIN':'#C6011F','CLE':'#00385D','COL':'#333366','DET':'#0C2340',
    'HOU':'#EB6E1F','KC':'#004687','LAA':'#BA0021','LAD':'#005A9C','MIA':'#00A3E0',
    'MIL':'#12284B','MIN':'#002B5C','NYM':'#FF5910','NYY':'#003087','ATH':'#003831',
    'PHI':'#E81828','PIT':'#FDB827','SD':'#2F241D','SF':'#FD5A1E','SEA':'#0C2C56',
    'STL':'#C41E3A','TB':'#092C5C','TEX':'#003278','TOR':'#134A8E','WSH':'#AB0003'
}};
const TYPE_COLORS = {{ workout:null, playoff:'#6a3a9a', travel:'#555', other:'#999', game:'#12284b' }};
const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

// Default to the current month so the calendar tracks forward as time moves.
// Calendar navigation works for any month regardless of this start value.
var _calMonth = (function() {{
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
}})();
var _calEvents = {{}};       // manual events from API
var _calAutoEvents = [];     // events derived from RECORDS.workout_dates
var _calRecordsByPlayerTeam = {{}};  // 'player|team' -> [records] for Slack link lookup
var _calChipIndex = {{}};    // 'c5' -> ev, rebuilt each render (dispatch table for chip clicks)
var _calChipCounter = 0;
var _calInitialized = false;
var _calSelectedPlayers = null;   // Set<player> currently toggled on. null = uninitialized.
var _calAllPlayersCache = null;   // sorted list of every player that could appear
var _calSelectedPlayersEverSeen = new Set();  // tracks which players we've shown a chip for

const _CAL_PLAYERS_LS_KEY = 'ti_cal_selected_players_v1';

function _calComputeAllPlayers() {{
    // Players who have a PDW invite — honoring the matrix override:
    //   w|player|team === false -> force-off (hide regardless of r.workout)
    //   w|player|team === true  -> force-on (include even if r.workout is falsy)
    // This matches buildAutoEvents' eligibility logic so the chip row and grid agree.
    const s = new Set();
    RECORDS.forEach(r => {{
        const ov = (typeof scoreOverrides !== 'undefined') ? scoreOverrides['w|' + r.player + '|' + r.team] : undefined;
        const isPDW = (ov === false) ? false : (ov === true ? true : !!r.workout);
        if (isPDW) s.add(r.player);
    }});
    // Surface manual workout events tied to an existing PDW player,
    // so confirmed/edited entries don't vanish if the underlying r.workout is toggled later.
    Object.values(_calEvents || {{}}).forEach(ev => {{
        if (ev && ev.type === 'workout' && ev.player && s.has(ev.player)) s.add(ev.player);
    }});
    // Also include any player who has a game on the schedule — otherwise the per-player
    // toggle filter would hide their games from the grid.
    (GAMES_SCHEDULE || []).forEach(g => {{ if (g && g.player) s.add(g.player); }});
    return [...s].sort();
}}

function _calLoadSelection(allPlayers) {{
    try {{
        const raw = localStorage.getItem(_CAL_PLAYERS_LS_KEY);
        if (raw) {{
            const saved = JSON.parse(raw);
            if (Array.isArray(saved)) {{
                const known = new Set(allPlayers);
                const restored = new Set(saved.filter(p => known.has(p)));
                if (restored.size > 0) return restored;
            }}
        }}
    }} catch(e) {{ /* ignore */ }}
    return new Set(allPlayers);
}}

function _calSaveSelection() {{
    try {{
        localStorage.setItem(_CAL_PLAYERS_LS_KEY, JSON.stringify([..._calSelectedPlayers]));
    }} catch(e) {{ /* ignore */ }}
}}

function _calEnsureSelection() {{
    _calAllPlayersCache = _calComputeAllPlayers();
    if (_calSelectedPlayers === null) {{
        _calSelectedPlayers = _calLoadSelection(_calAllPlayersCache);
    }} else {{
        // Auto-include any newly-appearing players so fresh Slack logs aren't silently hidden.
        const prev = new Set(_calSelectedPlayers);
        _calAllPlayersCache.forEach(p => {{ if (!prev.has(p) && !_calSelectedPlayersEverSeen.has(p)) _calSelectedPlayers.add(p); }});
    }}
    _calAllPlayersCache.forEach(p => _calSelectedPlayersEverSeen.add(p));
}}

function _calRenderPlayerChips() {{
    const host = document.getElementById('calPlayerChips');
    if (!host) return;
    let html = '';
    if (!_calAllPlayersCache.length) {{
        html = '<div class="cal-multi-empty">No PDW invites yet.</div>';
    }} else {{
        _calAllPlayersCache.forEach(p => {{
            const on = _calSelectedPlayers.has(p);
            const safeAttr = p.replace(/'/g, "\\\\'").replace(/"/g, '&quot;');
            const safeText = p.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            html += '<label class="cal-multi-item" onclick="event.stopPropagation()">'
                +  '<input type="checkbox" ' + (on ? 'checked' : '') + ' onchange="calTogglePlayer(\\'' + safeAttr + '\\')">'
                +  '<span>' + safeText + '</span>'
                +  '</label>';
        }});
    }}
    host.innerHTML = html;
    _calUpdatePlayerBtnLabel();
}}

function _calUpdatePlayerBtnLabel() {{
    const el = document.getElementById('calPlayerBtnLabel');
    if (!el) return;
    const total = _calAllPlayersCache.length;
    const sel = _calSelectedPlayers ? _calSelectedPlayers.size : 0;
    let label;
    if (total === 0) label = 'No players';
    else if (sel === 0) label = 'None';
    else if (sel === total) label = 'All (' + total + ')';
    else if (sel === 1) label = [..._calSelectedPlayers][0];
    else label = sel + ' selected';
    el.textContent = label;
}}

function toggleCalPlayerPanel() {{
    const el = document.getElementById('calPlayerDropdown');
    if (!el) return;
    el.classList.toggle('open');
}}

function _calClosePlayerPanel() {{
    const el = document.getElementById('calPlayerDropdown');
    if (el) el.classList.remove('open');
}}

document.addEventListener('click', function(e) {{
    const dd = document.getElementById('calPlayerDropdown');
    if (!dd || !dd.classList.contains('open')) return;
    if (!dd.contains(e.target)) _calClosePlayerPanel();
}});

function calTogglePlayer(p) {{
    if (_calSelectedPlayers.has(p)) _calSelectedPlayers.delete(p);
    else _calSelectedPlayers.add(p);
    _calSaveSelection();
    _calRenderPlayerChips();
    renderCalendar();
}}

function calSelectAllPlayers() {{
    _calSelectedPlayers = new Set(_calAllPlayersCache);
    _calSaveSelection();
    _calRenderPlayerChips();
    renderCalendar();
}}

function calSelectNoPlayers() {{
    _calSelectedPlayers = new Set();
    _calSaveSelection();
    _calRenderPlayerChips();
    renderCalendar();
}}

function _escHtml(s) {{
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function _buildPdfGridHtml(year, month, eventsByDate) {{
    const first = new Date(year, month, 1);
    const startDow = first.getDay();
    const daysInMonth = new Date(year, month+1, 0).getDate();
    const cells = Math.ceil((startDow + daysInMonth) / 7) * 7;
    let html = '<div style="display:grid;grid-template-columns:repeat(7,1fr);border:1px solid #bbb;background:#ddd;gap:1px;border-radius:4px;overflow:hidden;">';
    ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d => {{
        html += '<div style="background:#000000;color:white;padding:6px 0;font-size:11px;font-weight:700;text-align:center;letter-spacing:0.5px;">' + d + '</div>';
    }});
    for (let i = 0; i < cells; i++) {{
        const dayNum = i - startDow + 1;
        if (dayNum < 1 || dayNum > daysInMonth) {{
            html += '<div style="background:#fafafa;min-height:90px;"></div>';
            continue;
        }}
        const iso = year + '-' + String(month+1).padStart(2,'0') + '-' + String(dayNum).padStart(2,'0');
        const isDraft = (iso === '2026-07-11' || iso === '2026-07-12' || iso === '2026-07-13');
        const bg = isDraft ? '#fff5e0' : 'white';
        html += '<div style="background:' + bg + ';min-height:90px;padding:4px 5px;vertical-align:top;">';
        html += '<div style="font-size:10px;color:#888;font-weight:700;margin-bottom:3px;">' + dayNum
            + (isDraft ? ' <span style="font-size:8px;padding:1px 4px;background:#ff2a22;color:white;border-radius:2px;font-weight:700;">DRAFT</span>' : '')
            + '</div>';
        (eventsByDate[iso] || []).forEach(ev => {{
            const color = _chipColor(ev);
            const isWorkout = ev.type === 'workout';
            const isConfirmed = isWorkout && !!ev.confirmed;
            const label = _escHtml(_chipLabel(ev));
            let style;
            if (isWorkout && !isConfirmed) {{
                style = 'display:block;font-size:9px;padding:2px 5px;margin-bottom:2px;border-radius:3px;'
                    + 'border:1.5px dashed ' + color + ';color:' + color + ';font-weight:500;'
                    + 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;line-height:1.25;'
                    + (ev.tentative ? 'opacity:0.75;font-style:italic;' : '');
                html += '<div style="' + style + '">' + label + '</div>';
            }} else {{
                const prefix = isConfirmed ? '&#10003; ' : '';
                style = 'display:block;font-size:9px;padding:2px 5px;margin-bottom:2px;border-radius:3px;'
                    + 'background:' + color + ';color:white;font-weight:' + (isConfirmed ? '800' : '600') + ';'
                    + 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;line-height:1.25;';
                html += '<div style="' + style + '">' + prefix + label + '</div>';
            }}
        }});
        html += '</div>';
    }}
    html += '</div>';
    return html;
}}

function _buildPdfAgendaHtml(players, eventsByDate, year, month) {{
    const MONTH_KEY = year + '-' + String(month+1).padStart(2,'0');
    const byPlayer = {{}};
    Object.keys(eventsByDate).forEach(iso => {{
        if (iso.slice(0,7) !== MONTH_KEY) return;
        eventsByDate[iso].forEach(ev => {{
            (byPlayer[ev.player] = byPlayer[ev.player] || []).push(ev);
        }});
    }});
    let html = '<div style="margin-top:18px;display:grid;grid-template-columns:repeat(2,1fr);gap:14px;">';
    players.forEach(p => {{
        const evs = (byPlayer[p] || []).slice().sort((a,b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
        html += '<div style="border:1px solid #ddd;border-radius:4px;padding:8px 10px;break-inside:avoid;">';
        html += '<div style="font-size:12px;font-weight:700;color:#000000;margin-bottom:6px;border-bottom:1px solid #eee;padding-bottom:4px;">' + _escHtml(p) + '</div>';
        if (!evs.length) {{
            html += '<div style="font-size:10px;color:#999;font-style:italic;">No events this month.</div>';
        }} else {{
            evs.forEach(ev => {{
                const d = new Date(ev.date + 'T00:00:00');
                const dateStr = (d.getMonth()+1) + '/' + d.getDate();
                const isWorkout = ev.type === 'workout';
                const isGame = ev.type === 'game';
                let line = '';
                if (isWorkout) {{
                    line = _escHtml(ev.team || '?') + (ev.confirmed ? ' (confirmed)' : ' invite') + (ev.tentative ? ' · T' : '');
                }} else if (isGame) {{
                    line = 'vs ' + _escHtml(ev.opponent || '?');
                    if (ev.ballpark) line += ' @ ' + _escHtml(ev.ballpark);
                }} else {{
                    line = _escHtml(ev.title || ev.type || 'Event');
                }}
                if (ev.time) line += ' · ' + _escHtml(ev.time);
                if (ev.location && !isGame) line += ' · ' + _escHtml(ev.location);
                html += '<div style="font-size:10px;color:#333;padding:2px 0;">'
                     + '<span style="display:inline-block;width:34px;color:#888;font-weight:600;">' + dateStr + '</span>'
                     + line + '</div>';
            }});
        }}
        html += '</div>';
    }});
    html += '</div>';
    return html;
}}

function exportCalendarPDF() {{
    // Switched from html2canvas/html2pdf to the browser's native print-to-PDF
    // pipeline. html2canvas kept producing blank canvases regardless of positioning
    // tricks; the browser's own print engine handles layout + print-safe rendering
    // reliably. UX cost: the user clicks "Save as PDF" in the print dialog (1 extra step).
    _calEnsureSelection();
    const players = [..._calSelectedPlayers].sort();
    if (!players.length) {{
        showToast('Select at least one player first.', false);
        return;
    }}

    const fType = document.getElementById('calTypeFilter').value;
    const merged = _getMergedEvents().filter(ev => {{
        if (!_calSelectedPlayers.has(ev.player)) return false;
        if (fType) {{
            // "other" buckets anything that isn't a workout or a game
            // (keeps legacy playoff/travel events visible).
            if (fType === 'other') {{
                if (ev.type === 'workout' || ev.type === 'game') return false;
            }} else if (ev.type !== fType) return false;
        }}
        return true;
    }});
    const byDate = {{}};
    merged.forEach(ev => {{ (byDate[ev.date] = byDate[ev.date] || []).push(ev); }});

    const year = _calMonth.getFullYear();
    const month = _calMonth.getMonth();
    const monthName = MONTH_NAMES[month];
    const nowIso = _fmtIso(new Date());
    const filename = 'SV-TeamIntel-' + monthName + '-' + year
        + (players.length <= 3 ? '-' + players.map(p => p.split(' ').pop()).join('-') : '');

    const bodyHtml =
        '<div class="pdf-header">'
      +   '<div>'
      +     '<div class="pdf-title">Stadium Ventures &middot; ' + monthName + ' ' + year + '</div>'
      +     '<div class="pdf-sub">Players: ' + _escHtml(players.join(', ')) + '</div>'
      +   '</div>'
      +   '<div class="pdf-gen">SV TeamIntel<br>Generated ' + nowIso + '</div>'
      + '</div>'
      + _buildPdfGridHtml(year, month, byDate)
      + _buildPdfAgendaHtml(players, byDate, year, month);

    const doc = '<!DOCTYPE html>\\n<html><head><meta charset="utf-8"><title>' + filename + '</title>'
      + '<style>'
      +   '@page {{ size: letter landscape; margin: 10mm; }}'
      +   '@media print {{ body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}'
      +   'body {{ margin: 0; padding: 12px; font-family: Arial, sans-serif; color: #222; font-size: 10px; }}'
      +   '.pdf-header {{ display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 3px solid #ff2a22; padding-bottom: 8px; margin-bottom: 12px; }}'
      +   '.pdf-title {{ font-size: 20px; font-weight: 800; color: #000000; letter-spacing: 0.3px; }}'
      +   '.pdf-sub {{ font-size: 10px; color: #555; margin-top: 3px; }}'
      +   '.pdf-gen {{ font-size: 9px; color: #888; text-align: right; }}'
      + '</style></head><body>' + bodyHtml + '</body></html>';

    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;';
    document.body.appendChild(iframe);

    const btn = document.querySelector('.cal-pdfbtn');
    if (btn) {{ btn.disabled = true; btn.textContent = 'Opening...'; }}

    const restore = () => {{
        if (btn) {{ btn.disabled = false; btn.innerHTML = '&#x2B07; PDF'; }}
        // Defer iframe removal: Safari/Chrome need the iframe alive through the print dialog.
        setTimeout(() => {{ if (iframe.parentNode) iframe.parentNode.removeChild(iframe); }}, 2000);
    }};

    // Write into the iframe and trigger print once it's ready. The user picks
    // "Save as PDF" in the browser's print dialog — works on every browser.
    const iwin = iframe.contentWindow;
    const idoc = iwin.document;
    idoc.open();
    idoc.write(doc);
    idoc.close();

    const triggerPrint = () => {{
        try {{
            iwin.focus();
            iwin.print();
            showToast('Print dialog opened — choose "Save as PDF".', true);
        }} catch(e) {{
            console.error(e);
            showToast('PDF failed: ' + e.message, false);
        }} finally {{
            restore();
        }}
    }};

    // Give the iframe one paint cycle to layout before printing.
    if (idoc.readyState === 'complete') {{
        setTimeout(triggerPrint, 100);
    }} else {{
        iwin.addEventListener('load', () => setTimeout(triggerPrint, 100), {{ once: true }});
    }}
}}

async function _calApi(method, body) {{
    const opts = {{ method: method, headers: {{'Content-Type':'application/json'}} }};
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch('/api/calendar-events', opts);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
}}

async function loadCalendarEvents() {{
    try {{ _calEvents = await _calApi('GET', null) || {{}}; }}
    catch(e) {{ _calEvents = {{}}; console.warn('calendar load failed', e); }}
}}

function buildAutoEvents() {{
    const byKey = {{}};          // 'player|team|date' -> best event (dedup)
    const byPT = {{}};
    RECORDS.forEach(r => {{
        // Respect manual PDW override from the matrix popup:
        //   w|player|team === false -> force-off (hide auto chips even if r.workout)
        //   w|player|team === true  -> force-on (but we still need workout_dates to place chips)
        const _ov = scoreOverrides['w|' + r.player + '|' + r.team];
        const _isPDW = (_ov === false) ? false : (_ov === true ? true : !!r.workout);
        if (!_isPDW) return;
        const ptKey = r.player + '|' + r.team;
        (byPT[ptKey] = byPT[ptKey] || []).push(r);
        if (!r.workout_dates || !r.workout_dates.length) return;
        r.workout_dates.forEach(wd => {{
            const key = r.player + '|' + r.team + '|' + wd.date;
            const candidate = {{
                auto: true,
                type: 'workout',
                date: wd.date,
                player: r.player,
                team: r.team,
                time: wd.time || null,
                location: wd.location || null,
                tentative: !!wd.tentative,
                confirmed: false,
                notes: null,
                title: null,
                _postDate: r.date,
            }};
            const existing = byKey[key];
            if (!existing) {{ byKey[key] = candidate; return; }}
            // Merge: keep richer metadata (location > time > tentative-flag > most recent post).
            if (!existing.location && candidate.location) existing.location = candidate.location;
            if (!existing.time && candidate.time) existing.time = candidate.time;
            if (!existing.tentative && candidate.tentative) existing.tentative = true;
            if ((candidate._postDate || '') > (existing._postDate || '')) existing._postDate = candidate._postDate;
        }});
    }});
    // Game schedule events — read-only, straight from the shared Google Sheet.
    // Not deduped against workouts (games and workouts are distinct types).
    (GAMES_SCHEDULE || []).forEach(g => {{
        if (!g.player || !g.date) return;
        byKey['GAME|' + g.player + '|' + g.date + '|' + (g.opponent || '')] = {{
            auto: true,
            readonly: true,
            type: 'game',
            date: g.date,
            player: g.player,
            team: g.team || null,
            opponent: g.opponent || null,
            ballpark: g.ballpark || null,
            location: g.location || null,
            time: g.time || null,
            level: g.level || null,
            title: null,
            notes: null,
            tentative: false,
            confirmed: false,
        }};
    }});
    _calAutoEvents = Object.values(byKey);
    _calRecordsByPlayerTeam = byPT;
}}

function _getMergedEvents() {{
    // Manual overrides match auto events by (player|team|date|type). Manual wins.
    const manualKeys = new Set();
    const manual = Object.values(_calEvents || {{}});
    manual.forEach(ev => {{
        manualKeys.add([ev.player, ev.team || '', ev.date, ev.type].join('|'));
    }});
    const autos = _calAutoEvents.filter(ev => {{
        const k = [ev.player, ev.team || '', ev.date, ev.type].join('|');
        return !manualKeys.has(k);
    }});
    return autos.concat(manual.map(ev => Object.assign({{ auto:false }}, ev)));
}}

function _fmtMonth(d) {{ return MONTH_NAMES[d.getMonth()] + ' ' + d.getFullYear(); }}
function _fmtIso(d) {{
    const m = String(d.getMonth()+1).padStart(2,'0');
    const day = String(d.getDate()).padStart(2,'0');
    return d.getFullYear() + '-' + m + '-' + day;
}}

function calShiftMonth(delta) {{
    _calMonth = new Date(_calMonth.getFullYear(), _calMonth.getMonth()+delta, 1);
    renderCalendar();
}}

function calJumpTo(which) {{
    if (which === 'today') {{
        const now = new Date();
        _calMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    }}
    renderCalendar();
}}

function _chipColor(ev) {{
    if (ev.type === 'workout') {{ return TEAM_COLORS[ev.team] || '#888'; }}
    if (ev.type === 'game') {{
        // HS games get a teal chip; NCAA/JUCO (college) use the default navy.
        const lvl = (ev.level || '').toUpperCase();
        if (lvl === 'HS' || lvl.startsWith('HIGH')) return '#0d9488';
        return TYPE_COLORS.game;
    }}
    return TYPE_COLORS[ev.type] || '#888';
}}

function _chipLabel(ev) {{
    if (ev.type === 'workout') {{
        return (ev.team || '?') + ' · ' + (ev.player || '?') + (ev.tentative ? ' (T)' : '');
    }}
    if (ev.type === 'game') {{
        const opp = ev.opponent || '?';
        return (ev.player || '?') + ' vs ' + opp;
    }}
    const t = ev.title || ({{playoff:'Playoff', travel:'Travel', other:'Event'}}[ev.type] || 'Event');
    return (ev.player || '?') + ' · ' + t;
}}

function renderCalendar() {{
    document.getElementById('calMonthLabel').textContent = _fmtMonth(_calMonth);

    _calEnsureSelection();
    _calRenderPlayerChips();
    const fType = document.getElementById('calTypeFilter').value;

    const year = _calMonth.getFullYear(), month = _calMonth.getMonth();
    const first = new Date(year, month, 1);
    const startDow = first.getDay();
    const daysInMonth = new Date(year, month+1, 0).getDate();

    let html = '';
    ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d => {{
        html += '<div class="cal-dow">' + d + '</div>';
    }});

    const merged = _getMergedEvents().filter(ev => {{
        if (!_calSelectedPlayers.has(ev.player)) return false;
        if (fType) {{
            // "other" buckets anything that isn't a workout or a game
            // (keeps legacy playoff/travel events visible).
            if (fType === 'other') {{
                if (ev.type === 'workout' || ev.type === 'game') return false;
            }} else if (ev.type !== fType) return false;
        }}
        return true;
    }});
    // Reset chip dispatch table for this render.
    _calChipIndex = {{}};
    _calChipCounter = 0;
    const byDate = {{}};
    merged.forEach(ev => {{ (byDate[ev.date] = byDate[ev.date] || []).push(ev); }});

    const todayIso = _fmtIso(new Date());
    const cells = Math.ceil((startDow + daysInMonth) / 7) * 7;
    for (let i = 0; i < cells; i++) {{
        const dayNum = i - startDow + 1;
        if (dayNum < 1 || dayNum > daysInMonth) {{
            html += '<div class="cal-cell cal-pad"></div>';
            continue;
        }}
        const d = new Date(year, month, dayNum);
        const iso = _fmtIso(d);
        const isDraft = (iso === '2026-07-11' || iso === '2026-07-12' || iso === '2026-07-13');
        const isToday = (iso === todayIso);
        let cls = 'cal-cell';
        if (isDraft) cls += ' cal-draft';
        if (isToday) cls += ' cal-today';
        html += '<div class="' + cls + '" data-iso="' + iso + '">';
        html += '<div class="cal-daynum">' + dayNum + (isDraft ? ' <span class="cal-drafttag">DRAFT</span>' : '') + '</div>';
        const evs = byDate[iso] || [];
        evs.forEach(ev => {{
            const color = _chipColor(ev);
            const marker = ev.auto ? '' : '*';
            const cid = 'c' + (_calChipCounter++);
            _calChipIndex[cid] = ev;
            const safeTitle = (ev.notes || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
            const isWorkout = ev.type === 'workout';
            const isConfirmed = isWorkout && !!ev.confirmed;
            let cls = 'cal-chip';
            let style = '';
            let prefix = '';
            if (isWorkout && !isConfirmed) {{
                cls += ' workout-invite';
                style = 'border-color:' + color + ';color:' + color + ';--chip-color:' + color + ';';
            }} else {{
                if (isConfirmed) cls += ' workout-confirmed';
                style = 'background:' + color + ';';
                if (isConfirmed) prefix = '&#10003; ';
            }}
            if (ev.tentative) cls += ' tentative';
            html += '<div class="' + cls + '" style="' + style + '" ' +
                'onclick="openEventChip(\\'' + cid + '\\')" ' +
                'title="' + safeTitle + '">' +
                prefix + _chipLabel(ev) + marker + '</div>';
        }});
        html += '</div>';
    }}
    document.getElementById('calGrid').innerHTML = html;

    // Mobile agenda view: same events, grouped chronologically by date.
    const monthKey = year + '-' + String(month+1).padStart(2,'0');
    const agendaDates = Object.keys(byDate).filter(d => d.slice(0,7) === monthKey).sort();
    // Always surface draft days even if empty.
    ['2026-07-11','2026-07-12','2026-07-13'].forEach(d => {{
        if (d.slice(0,7) === monthKey && agendaDates.indexOf(d) === -1) agendaDates.push(d);
    }});
    agendaDates.sort();
    let agendaHtml = '';
    if (!agendaDates.length) {{
        agendaHtml = '<div class="agenda-empty">No events this month.</div>';
    }} else {{
        const dowNames = ['SUN','MON','TUE','WED','THU','FRI','SAT'];
        agendaDates.forEach(iso => {{
            const parts = iso.split('-');
            const d = new Date(parseInt(parts[0]), parseInt(parts[1])-1, parseInt(parts[2]));
            const isDraft = (iso === '2026-07-11' || iso === '2026-07-12' || iso === '2026-07-13');
            let dayCls = 'agenda-day';
            if (isDraft) dayCls += ' agenda-draft';
            agendaHtml += '<div class="' + dayCls + '">';
            agendaHtml += '<div class="agenda-date">';
            agendaHtml += '<div class="agenda-dow">' + dowNames[d.getDay()] + '</div>';
            agendaHtml += '<div class="agenda-dnum">' + d.getDate() + '</div>';
            if (isDraft) agendaHtml += '<div class="agenda-drafttag">DRAFT</div>';
            agendaHtml += '</div>';
            agendaHtml += '<div class="agenda-chips">';
            const evs = byDate[iso] || [];
            if (!evs.length) {{
                agendaHtml += '<div class="agenda-none">' + (isDraft ? 'MLB Draft Day — no workouts' : 'No events') + '</div>';
            }} else {{
                evs.forEach(ev => {{
                    const color = _chipColor(ev);
                    const marker = ev.auto ? '' : '*';
                    const cid = 'a' + (_calChipCounter++);
                    _calChipIndex[cid] = ev;
                    const safeTitle = (ev.notes || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
                    const isWorkout = ev.type === 'workout';
                    const isConfirmed = isWorkout && !!ev.confirmed;
                    let cls = 'cal-chip';
                    let style = '';
                    let prefix = '';
                    if (isWorkout && !isConfirmed) {{
                        cls += ' workout-invite';
                        style = 'border-color:' + color + ';color:' + color + ';--chip-color:' + color + ';';
                    }} else {{
                        if (isConfirmed) cls += ' workout-confirmed';
                        style = 'background:' + color + ';';
                        if (isConfirmed) prefix = '&#10003; ';
                    }}
                    if (ev.tentative) cls += ' tentative';
                    agendaHtml += '<div class="' + cls + '" style="' + style + '" ' +
                        'onclick="openEventChip(\\'' + cid + '\\')" ' +
                        'title="' + safeTitle + '">' +
                        prefix + _chipLabel(ev) + marker + '</div>';
                }});
            }}
            agendaHtml += '</div></div>';
        }});
    }}
    document.getElementById('calAgenda').innerHTML = agendaHtml;

    // Legend: show unique teams active in the merged set this month
    const activeTeams = new Set();
    merged.forEach(ev => {{
        if (ev.date.slice(0,7) === year + '-' + String(month+1).padStart(2,'0')) {{
            if (ev.type === 'workout' && ev.team) activeTeams.add(ev.team);
        }}
    }});
    let legend = '';
    [...activeTeams].sort().forEach(t => {{
        legend += '<span class="cal-legend-item"><span class="cal-legend-sw" style="background:' + (TEAM_COLORS[t]||'#888') + '"></span>' + t + '</span>';
    }});
    document.getElementById('calLegend').innerHTML = legend;
}}

var _lastEventModalCtx = null;     // last args to openEventModal: id, isoDate, ev
var _mmReturnToEvent = null;       // if set, message modal shows "Back to Event" button

function openEventChip(cid) {{
    const ev = _calChipIndex[cid];
    if (!ev) return;
    // Games are read-only (source is the shared Google Sheet). Show a minimal
    // details popup instead of the editable event modal.
    if (ev.type === 'game') {{ openGameDetails(ev); return; }}
    openEventModal(ev.id || null, ev.date, ev);
}}

function openGameDetails(ev) {{
    const fmt = v => (v == null || v === '') ? '—' : v;
    const body = document.getElementById('gameDetailsBody');
    if (!body) return;
    body.innerHTML =
        '<div class="gd-row"><span class="gd-label">Player</span><span>' + fmt(ev.player) + '</span></div>'
      + '<div class="gd-row"><span class="gd-label">Date</span><span>' + fmt(ev.date) + '</span></div>'
      + '<div class="gd-row"><span class="gd-label">Team</span><span>' + fmt(ev.team) + (ev.level ? ' · ' + fmt(ev.level) : '') + '</span></div>'
      + '<div class="gd-row"><span class="gd-label">Opponent</span><span>vs ' + fmt(ev.opponent) + '</span></div>'
      + '<div class="gd-row"><span class="gd-label">Time</span><span>' + fmt(ev.time) + '</span></div>'
      + '<div class="gd-row"><span class="gd-label">Ballpark</span><span>' + fmt(ev.ballpark) + '</span></div>'
      + '<div class="gd-row"><span class="gd-label">Location</span><span>' + fmt(ev.location) + '</span></div>';
    document.getElementById('gameDetailsOverlay').classList.add('open');
}}

function closeGameDetails() {{
    document.getElementById('gameDetailsOverlay').classList.remove('open');
}}

function openEventModal(id, isoDate, ev) {{
    const overlay = document.getElementById('evOverlay');
    ev = ev || null;
    _lastEventModalCtx = {{ id: id, isoDate: isoDate, ev: ev }};
    document.getElementById('evTitle').textContent = (id && ev && !ev.auto) ? 'Edit Event' : (ev && ev.auto ? 'Edit Auto-Workout' : 'Add Event');
    document.getElementById('evDate').value = (ev && ev.date) || isoDate || _fmtIso(new Date());
    document.getElementById('evType').value = (ev && ev.type) || 'workout';
    const playerSel = document.getElementById('evPlayer');
    if (playerSel.options.length === 0) {{
        const players = [...new Set([...RECORDS.map(r => r.player), ...ALL_2026_PLAYERS])].sort();
        players.forEach(p => {{ const o = document.createElement('option'); o.value = p; o.textContent = p; playerSel.appendChild(o); }});
    }}
    // Default to a currently-selected player when adding a new event.
    let calFilterPlayer = '';
    if (_calSelectedPlayers && _calSelectedPlayers.size >= 1) {{
        const sel = [..._calSelectedPlayers].sort();
        calFilterPlayer = sel[0];
    }}
    playerSel.value = (ev && ev.player) || calFilterPlayer || playerSel.options[0].value;
    const teamSel = document.getElementById('evTeam');
    if (teamSel.options.length <= 1) {{
        ALL_TEAMS.forEach(t => {{ const o = document.createElement('option'); o.value = t; o.textContent = t; teamSel.appendChild(o); }});
    }}
    teamSel.value = (ev && ev.team) || '';
    document.getElementById('evTitleInput').value = (ev && ev.title) || '';
    document.getElementById('evTime').value = (ev && ev.time) || '';
    document.getElementById('evLocation').value = (ev && ev.location) || '';
    document.getElementById('evTentative').checked = !!(ev && ev.tentative);
    document.getElementById('evConfirmed').checked = !!(ev && ev.confirmed);
    document.getElementById('evNotes').value = (ev && ev.notes) || '';
    // If this is a manual override of an auto-parsed workout, offer "Clear Changes"
    // (restores the auto-parsed version) instead of Delete.
    const hasAutoCounterpart = !!(ev && !ev.auto && ev.type === 'workout' && _calAutoEvents.some(a =>
        a.player === ev.player && a.team === ev.team && a.date === ev.date && a.type === 'workout'));
    const isManualEdit = !!(id && ev && !ev.auto);
    document.getElementById('evDeleteBtn').style.display = (isManualEdit && !hasAutoCounterpart) ? 'inline-block' : 'none';
    document.getElementById('evClearBtn').style.display = (isManualEdit && hasAutoCounterpart) ? 'inline-block' : 'none';
    document.getElementById('evNote').textContent = (ev && ev.auto) ? 'This event was auto-parsed from a Slack message. Saving creates a manual override.' : '';
    // Slack button: only meaningful for workout events with a backing record.
    const slackBtn = document.getElementById('evSlackBtn');
    const type = (ev && ev.type) || 'workout';
    const pt = playerSel.value + '|' + (teamSel.value || '');
    const hasSlackRecord = (type === 'workout') && !!(_calRecordsByPlayerTeam[pt] && _calRecordsByPlayerTeam[pt].length);
    slackBtn.style.display = hasSlackRecord ? 'inline-block' : 'none';
    overlay.dataset.editId = (id && ev && !ev.auto) ? id : '';
    overlay.dataset.player = playerSel.value;
    overlay.dataset.team = teamSel.value || '';
    overlay.dataset.date = document.getElementById('evDate').value;
    evSyncType();
    overlay.style.display = 'flex';
}}

function openSlackFromEvent() {{
    const overlay = document.getElementById('evOverlay');
    const player = overlay.dataset.player;
    const team = overlay.dataset.team;
    const evDate = overlay.dataset.date;
    const pool = _calRecordsByPlayerTeam[player + '|' + team] || [];
    if (!pool.length) {{ showToast('No Slack message found for this player/team', false); return; }}
    // Prefer the record whose workout_dates contains this event's date.
    let picked = pool.find(r => (r.workout_dates || []).some(wd => wd.date === evDate));
    if (!picked) {{
        // Fallback: most recent record by post-date.
        picked = pool.slice().sort((a,b) => (b.date || '').localeCompare(a.date || ''))[0];
    }}
    const rowKey = picked.player + '|' + picked.team + '|' + picked.date + '|cal';
    _modalIndex[rowKey] = picked;
    // Capture the event context so the message modal can offer "Back to Event".
    const returnCtx = _lastEventModalCtx ? {{ id: _lastEventModalCtx.id, isoDate: _lastEventModalCtx.isoDate, ev: _lastEventModalCtx.ev }} : null;
    closeEventModal();
    openMessageModal(rowKey);
    if (returnCtx) {{
        _mmReturnToEvent = returnCtx;
        document.getElementById('mmBackBtn').style.display = 'inline-block';
    }}
}}

function returnToEvent() {{
    const ctx = _mmReturnToEvent;
    _mmReturnToEvent = null;
    document.getElementById('mmBackBtn').style.display = 'none';
    closeMessageModal();
    if (ctx) openEventModal(ctx.id, ctx.isoDate, ctx.ev);
}}

function jumpToCalendarForCurrentPlayer() {{
    const player = document.getElementById('playerSelect').value;
    if (!player) {{ showView('calendar'); return; }}
    (async () => {{
        if (!_calInitialized) {{ await initCalendar(); }}
        // Solo-focus this player on the master calendar.
        _calEnsureSelection();
        _calSelectedPlayers = new Set([player]);
        _calSelectedPlayersEverSeen.add(player);
        _calSaveSelection();
        // Jump to a month where this player has events if possible, else stay.
        const autoDates = _calAutoEvents.filter(e => e.player === player).map(e => e.date).sort();
        if (autoDates.length) {{
            const d = new Date(autoDates[0] + 'T00:00:00');
            _calMonth = new Date(d.getFullYear(), d.getMonth(), 1);
        }}
        showView('calendar');
        renderCalendar();
    }})();
}}

function closeEventModal() {{
    document.getElementById('evOverlay').style.display = 'none';
}}

function evSyncType() {{
    const t = document.getElementById('evType').value;
    document.getElementById('evTeamRow').style.display = (t === 'workout') ? 'flex' : 'none';
    document.getElementById('evTitleRow').style.display = (t === 'workout') ? 'none' : 'flex';
    document.getElementById('evConfirmedRow').style.display = (t === 'workout') ? 'flex' : 'none';
    // Hide Slack button for non-workout events.
    const slackBtn = document.getElementById('evSlackBtn');
    if (slackBtn && t !== 'workout') slackBtn.style.display = 'none';
}}

async function saveEvent() {{
    const body = {{
        date: document.getElementById('evDate').value,
        type: document.getElementById('evType').value,
        player: document.getElementById('evPlayer').value,
        team: document.getElementById('evTeam').value || null,
        title: document.getElementById('evTitleInput').value || null,
        time: document.getElementById('evTime').value || null,
        location: document.getElementById('evLocation').value || null,
        tentative: document.getElementById('evTentative').checked,
        confirmed: document.getElementById('evConfirmed').checked,
        notes: document.getElementById('evNotes').value || null,
    }};
    const editId = document.getElementById('evOverlay').dataset.editId;
    if (editId) body.id = editId;
    try {{
        const r = await _calApi('POST', body);
        if (r && r.event) {{ _calEvents[r.id] = r.event; }}
        closeEventModal();
        renderCalendar();
        showToast('Event saved', true);
    }} catch(e) {{ showToast('Save failed: ' + e.message, false); }}
}}

async function deleteEvent() {{
    const id = document.getElementById('evOverlay').dataset.editId;
    if (!id) return;
    if (!confirm('Delete this event?')) return;
    try {{
        await _calApi('DELETE', {{ id: id }});
        delete _calEvents[id];
        closeEventModal();
        renderCalendar();
        showToast('Event deleted', true);
    }} catch(e) {{ showToast('Delete failed: ' + e.message, false); }}
}}

async function clearEventChanges() {{
    const id = document.getElementById('evOverlay').dataset.editId;
    if (!id) return;
    if (!confirm('Clear manual changes and restore the auto-parsed version?')) return;
    try {{
        await _calApi('DELETE', {{ id: id }});
        delete _calEvents[id];
        closeEventModal();
        renderCalendar();
        showToast('Changes cleared — restored to auto-parsed version', true);
    }} catch(e) {{ showToast('Clear failed: ' + e.message, false); }}
}}

async function initCalendar() {{
    _calInitialized = true;
    buildAutoEvents();
    await loadCalendarEvents();
    renderCalendar();
}}

// ================= Manual Entries =================
// Manual player-team records (not from Slack). Backed by Redis key `manual_records`
// via /api/manual-records. Server-side merges them into the embedded RECORDS on
// build; client-side reloads the latest on init so adds/edits propagate without
// waiting for a full rebuild.

async function _mrApi(method, body) {{
    const opts = {{ method: method, headers: {{'Content-Type':'application/json'}} }};
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch('/api/manual-records', opts);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
}}

async function loadManualRecords() {{
    // Fetch the latest manual records from Redis and replace any manual entries in RECORDS.
    // (Server-side build may have embedded a slightly older snapshot; client fetch catches up.)
    let blob;
    try {{ blob = await _mrApi('GET', null); }}
    catch(e) {{ console.warn('manual records load failed', e); return; }}
    if (!blob || typeof blob !== 'object') return;
    // Drop any existing manual records (server-side-embedded snapshot) in place,
    // then push the fresh set. RECORDS is `const`, so mutate — do not reassign.
    for (let i = RECORDS.length - 1; i >= 0; i--) {{
        if (RECORDS[i].is_manual) RECORDS.splice(i, 1);
    }}
    Object.values(blob).forEach(val => {{
        if (!val || !val.player || !val.team || !val.date) return;
        const full = val.full_text || '';
        RECORDS.push({{
            id: val.id,
            player: val.player,
            team: val.team,
            date: val.date,
            score: Number(val.score),
            note: full.slice(0, 200),
            full_text: full,
            channel: null,
            workout: !!val.workout,
            workout_dates: val.workout_dates || [],
            is_manual: true,
        }});
    }});
}}

function _mrPopulatePlayerOptions(selectedPlayer) {{
    const sel = document.getElementById('mrPlayer');
    sel.innerHTML = '';
    const players = [...new Set([...RECORDS.map(r => r.player), ...ALL_2026_PLAYERS])].sort();
    players.forEach(p => {{
        const o = document.createElement('option'); o.value = p; o.textContent = p;
        sel.appendChild(o);
    }});
    if (selectedPlayer) sel.value = selectedPlayer;
}}

function _mrPopulateTeamOptions(selectedTeam) {{
    const sel = document.getElementById('mrTeam');
    sel.innerHTML = '';
    ALL_TEAMS.forEach(t => {{
        const o = document.createElement('option'); o.value = t; o.textContent = t;
        sel.appendChild(o);
    }});
    if (selectedTeam) sel.value = selectedTeam;
}}

function _toggleWorkoutDatesVisibility() {{
    const on = document.getElementById('mrWorkout').checked;
    document.getElementById('mrWorkoutDatesWrap').style.display = on ? 'block' : 'none';
    if (on && document.getElementById('mrWorkoutDates').children.length === 0) {{
        addWorkoutDateRow();
    }}
}}

function addWorkoutDateRow(preset) {{
    const host = document.getElementById('mrWorkoutDates');
    const row = document.createElement('div');
    row.className = 'mr-wd-row';
    const dateInput = document.createElement('input');
    dateInput.type = 'date';
    if (preset && preset.date) dateInput.value = preset.date;
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'mr-wd-del';
    del.innerHTML = '&times;';
    del.title = 'Remove this date';
    del.onclick = () => row.remove();
    row.appendChild(dateInput);
    row.appendChild(del);
    host.appendChild(row);
}}

function _collectWorkoutDates() {{
    const host = document.getElementById('mrWorkoutDates');
    const out = [];
    host.querySelectorAll('input[type="date"]').forEach(inp => {{
        const v = (inp.value || '').trim();
        if (v && /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(v)) out.push({{ date: v, tentative: false }});
    }});
    return out;
}}

function openManualEntryModal(existingId, preselectPlayer, preselectTeam) {{
    // Find existing manual record if editing.
    let existing = null;
    if (existingId) existing = RECORDS.find(r => r.is_manual && r.id === existingId);

    _mrPopulatePlayerOptions((existing && existing.player) || preselectPlayer || null);
    _mrPopulateTeamOptions((existing && existing.team) || preselectTeam || null);

    const today = new Date();
    const pad = n => String(n).padStart(2,'0');
    const todayIso = today.getFullYear() + '-' + pad(today.getMonth()+1) + '-' + pad(today.getDate());
    document.getElementById('mrDate').value = (existing && existing.date) || todayIso;
    document.getElementById('mrScore').value = String((existing && typeof existing.score === 'number') ? existing.score : 1);
    document.getElementById('mrNotes').value = (existing && existing.full_text) || '';
    document.getElementById('mrWorkout').checked = !!(existing && existing.workout);

    // Seed workout-date rows
    const host = document.getElementById('mrWorkoutDates');
    host.innerHTML = '';
    if (existing && existing.workout_dates && existing.workout_dates.length) {{
        existing.workout_dates.forEach(wd => addWorkoutDateRow(wd));
    }}
    _toggleWorkoutDatesVisibility();

    document.getElementById('mrTitle').textContent = existing ? 'Edit Manual Entry' : 'Add Manual Entry';
    document.getElementById('mrDeleteBtn').style.display = existing ? 'inline-block' : 'none';
    document.getElementById('mrOverlay').dataset.editId = existing ? existing.id : '';
    document.getElementById('mrOverlay').classList.add('open');
}}

function openManualEntryForCurrentPlayer() {{
    const p = document.getElementById('playerSelect').value;
    // If the detail view is filtered to a specific team (user clicked that team's row),
    // pre-select it too so "+ Add Entry" lands on the exact Player×Team the user is viewing.
    openManualEntryModal(null, p || null, _filterTeam || null);
}}

function closeManualEntryModal() {{
    document.getElementById('mrOverlay').classList.remove('open');
}}

async function saveManualEntry() {{
    const body = {{
        player: document.getElementById('mrPlayer').value,
        team: document.getElementById('mrTeam').value,
        date: document.getElementById('mrDate').value,
        score: Number(document.getElementById('mrScore').value),
        full_text: document.getElementById('mrNotes').value || '',
        workout: document.getElementById('mrWorkout').checked,
        workout_dates: document.getElementById('mrWorkout').checked ? _collectWorkoutDates() : [],
    }};
    if (!body.player || !body.team || !body.date) {{
        showToast('Player, team, and date are required.', false);
        return;
    }}
    const editId = document.getElementById('mrOverlay').dataset.editId;
    if (editId) body.id = editId;
    try {{
        await _mrApi('POST', body);
        await loadManualRecords();
        closeManualEntryModal();
        renderMatrix();
        if (document.getElementById('detailView').style.display !== 'none' && document.getElementById('playerSelect').value) {{
            renderDetail();
        }}
        showToast('Manual entry saved', true);
    }} catch(e) {{
        showToast('Save failed: ' + e.message, false);
    }}
}}

async function deleteManualEntry() {{
    const id = document.getElementById('mrOverlay').dataset.editId;
    if (!id) return;
    if (!confirm('Delete this manual entry?')) return;
    try {{
        await _mrApi('DELETE', {{ id: id }});
        await loadManualRecords();
        closeManualEntryModal();
        renderMatrix();
        if (document.getElementById('detailView').style.display !== 'none' && document.getElementById('playerSelect').value) {{
            renderDetail();
        }}
        showToast('Manual entry deleted', true);
    }} catch(e) {{
        showToast('Delete failed: ' + e.message, false);
    }}
}}

// Track the record currently open in the message modal so "Edit" can route to the manual modal.
var _mmCurrentRecord = null;

function editManualFromMessage() {{
    const r = _mmCurrentRecord;
    if (!r || !r.is_manual || !r.id) return;
    closeMessageModal();
    openManualEntryModal(r.id, r.player, r.team);
}}

async function init() {{
    await loadOverrides();
    await loadManualRecords();
    renderMatrix();
    const players = [...new Set([...RECORDS.map(r => r.player), ...ALL_2026_PLAYERS])].sort();
    const sel = document.getElementById('playerSelect');
    players.forEach(p => {{
        const o = document.createElement('option');
        o.value = p; o.textContent = p; sel.appendChild(o);
    }});
    if (players.length > 0) {{ sel.value = players[0]; renderDetail(); }}
}}
init();

// After everything is loaded, auto-login if session exists
if (sessionStorage.getItem('sv_auth') === '1') {{
    document.getElementById('loginGate').classList.add('hidden');
    document.getElementById('appContent').classList.add('visible');
}}
</script>
<div id="scoreOverlay" onclick="closeScorePopup()"></div>
<div id="scorePopup">
    <div class="popup-title" id="popupTitle"></div>
    <div class="popup-team-info" id="popupTeamInfo" style="display:none;"></div>
    <div class="popup-points-label">Set points</div>
    <div class="popup-points">
        <button class="pp5" onclick="savePoints(5)" title="GM / POBO / President">5</button>
        <button class="pp4" onclick="savePoints(4)" title="Director / SD / AGM / VP">4</button>
        <button class="pp3" onclick="savePoints(3)" title="National Cross-Checker">3</button>
        <button class="pp2" onclick="savePoints(2)" title="Cross-Checker / Regional X">2</button>
        <button class="pp1" onclick="savePoints(1)" title="Area Scout">1</button>
        <button class="pp0" onclick="savePoints(0)" title="No tier credit">0</button>
    </div>
    <div class="popup-scores">
        <button class="psna" onclick="saveScore('NA')" title="Not a real connection — hide this record">NA</button>
    </div>
    <div class="popup-pdw" id="pdwToggle" onclick="togglePDW()">Pre-Draft Workout</div>
    <span class="popup-reset" onclick="saveScore(null)">Reset to original</span>
</div>
<div id="messageOverlay" onclick="if(event.target===this) closeMessageModal()">
    <div id="messageModal">
        <button class="mm-close" onclick="closeMessageModal()">&times;</button>
        <button class="mm-back" id="mmBackBtn" onclick="returnToEvent()" style="display:none;">&#8592; Back to Event</button>
        <div class="mm-header" id="mmHeader">Full Slack Message
            <button class="mm-edit-btn" id="mmEditBtn" onclick="editManualFromMessage()" style="display:none;">Edit</button>
        </div>
        <div class="mm-title" id="mmTitle"></div>
        <div class="mm-meta" id="mmMeta"></div>
        <div class="mm-body" id="mmBody"></div>
        <div class="mm-legend" id="mmLegend" style="display:none;">
            <span class="pill">highlighted</span> = text that triggered the PDW flag
        </div>
    </div>
</div>

<!-- Manual Entry modal (matrix "+ Add Entry" / detail view "+ Add Entry") -->
<div id="mrOverlay" onclick="if(event.target===this) closeManualEntryModal()">
    <div id="mrModal">
        <div class="ev-title" id="mrTitle">Add Manual Entry</div>
        <div class="ev-row">
            <label for="mrPlayer">Player</label>
            <select id="mrPlayer"></select>
        </div>
        <div class="ev-row">
            <label for="mrTeam">Team</label>
            <select id="mrTeam"></select>
        </div>
        <div class="ev-row">
            <label for="mrDate">Date</label>
            <input type="date" id="mrDate">
        </div>
        <div class="ev-row">
            <label for="mrScore">Score</label>
            <select id="mrScore">
                <option value="2">+2 (Green / Strong Interest)</option>
                <option value="1" selected>+1 (Light Green / Interest)</option>
                <option value="0">0 (Yellow / Neutral)</option>
                <option value="-1">-1 (Red / Cool / No Contact)</option>
                <option value="-2">-2 (Dark Red / Negative)</option>
            </select>
        </div>
        <div class="ev-row">
            <label for="mrNotes">Notes (full message)</label>
            <textarea id="mrNotes" rows="5" placeholder="Paste / type the intel context here..."></textarea>
        </div>
        <div class="ev-row cb">
            <input type="checkbox" id="mrWorkout" onchange="_toggleWorkoutDatesVisibility()">
            <label for="mrWorkout">Pre-Draft Workout (invite or confirmed)</label>
        </div>
        <div id="mrWorkoutDatesWrap" style="display:none;margin-bottom:10px;">
            <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:0.3px;display:block;margin-bottom:6px;">Workout Dates</label>
            <div id="mrWorkoutDates"></div>
            <button type="button" class="mr-wd-add" onclick="addWorkoutDateRow()">+ Add Date</button>
        </div>
        <div class="ev-btns">
            <button class="ev-delete" id="mrDeleteBtn" onclick="deleteManualEntry()" style="display:none;">Delete</button>
            <button class="ev-cancel" onclick="closeManualEntryModal()">Cancel</button>
            <button class="ev-save" onclick="saveManualEntry()">Save</button>
        </div>
    </div>
</div>
<!-- Game Details (read-only, sourced from the shared Google Sheet) -->
<div id="gameDetailsOverlay" onclick="if(event.target===this) closeGameDetails()">
    <div id="gameDetailsModal">
        <div class="gd-title">Game Details</div>
        <div class="gd-sub">Read-only &middot; sourced from schedule sheet</div>
        <div id="gameDetailsBody"></div>
        <button class="gd-close" onclick="closeGameDetails()">Close</button>
    </div>
</div>
<div id="toast"></div>
</body>
</html>'''
    return html


# --- KV OVERRIDES (merged into teamintel.json for downstream consumers) ---
# The dashboard applies these client-side; downstream consumers (sv-draft-fit-workout)
# read the static JSON and never see the overrides unless we merge them here.
#
# KV blob shape (key = 'score_overrides'):
#   "player|team|date" -> int (-2..2) or "NA"         (score edit / exclusion)
#   "w|player|team"    -> true | false                 (PDW flag toggle)
GAME_SCHEDULE_CSV_URL = (
    'https://docs.google.com/spreadsheets/d/1PvPw1SKki7ZsSWwk2QIWrTp31yrgKvDvH8lbcHJCI24'
    '/export?format=csv&gid=446091585'
)


def _parse_sheet_date(raw):
    """Tolerant date parser — accepts 2026-04-23, 4/23/2026, 4/23/26, 04/23/2026.
    Returns 'YYYY-MM-DD' string or None on failure.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%-m/%-d/%Y', '%-m/%-d/%y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except Exception:
            continue
    return None


def _build_alias_lookup():
    """Map any known alias (lowercased) to its canonical roster name."""
    lookup = {}
    # Every canonical name maps to itself
    for p in ALL_2026_PLAYERS:
        lookup[p.lower()] = p
    # All aliases map to their canonical
    for canonical, aliases in PLAYER_ALIASES.items():
        lookup[canonical.lower()] = canonical
        for a in aliases:
            lookup[a.lower()] = canonical
    return lookup


def fetch_game_schedule():
    """Pull the game schedule Google Sheet (shared link-viewable) and return a list
    of game dicts restricted to players on the current roster. Silently tolerant —
    a fetch failure returns []. Dropped rows (name mismatch, missing date) are
    logged but not fatal.
    """
    try:
        req = urllib.request.Request(
            GAME_SCHEDULE_CSV_URL,
            headers={'User-Agent': 'sv-teamintel-build/1.0'},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"WARN: Failed to fetch game schedule CSV: {e}")
        return []

    alias_lookup = _build_alias_lookup()
    reader = csv.DictReader(io.StringIO(text))
    games = []
    dropped_names = set()
    kept_rows = 0
    total_rows = 0
    for row in reader:
        total_rows += 1
        client_raw = (row.get('Client') or '').strip()
        if not client_raw:
            continue
        canonical = alias_lookup.get(client_raw.lower())
        if not canonical:
            dropped_names.add(client_raw)
            continue
        iso_date = _parse_sheet_date(row.get('Date'))
        if not iso_date:
            continue
        games.append({
            'player': canonical,
            'team': (row.get('Team') or '').strip() or None,
            'level': (row.get('Level') or '').strip() or None,
            'date': iso_date,
            'location': (row.get('Location') or '').strip() or None,
            'time': (row.get('Time (Local time)') or row.get('Time') or '').strip() or None,
            'opponent': (row.get('Opponent') or '').strip() or None,
            'ballpark': (row.get('Ballpark') or '').strip() or None,
        })
        kept_rows += 1

    print(f"Game schedule: kept {kept_rows}/{total_rows} rows.")
    if dropped_names:
        print(f"Game schedule: dropped names not on roster: {sorted(dropped_names)}")
    return games


def load_kv_overrides():
    url = os.environ.get('REDIS_URL')
    if not url:
        print("INFO: REDIS_URL not set — skipping manual overrides.")
        return {}
    try:
        import redis as _redis
    except ImportError:
        print("WARN: 'redis' package not installed — skipping manual overrides.")
        return {}
    try:
        client = _redis.from_url(url, socket_connect_timeout=10, socket_timeout=8)
        raw = client.get('score_overrides')
        try:
            client.close()
        except Exception:
            pass
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return json.loads(raw)
    except Exception as e:
        print(f"WARN: Failed to load overrides from Redis: {e}")
        return {}


def load_manual_records():
    """Read the `manual_records` Redis blob and return records in the same shape as
    Slack-parsed records so they can be concatenated into the RECORDS list.
    Each blob value becomes one record with {player, team, date, score, full_text,
    workout, workout_dates, channel: None, is_manual: True, id}.
    """
    url = os.environ.get('REDIS_URL')
    if not url:
        return []
    try:
        import redis as _redis
    except ImportError:
        return []
    try:
        client = _redis.from_url(url, socket_connect_timeout=10, socket_timeout=8)
        raw = client.get('manual_records')
        try:
            client.close()
        except Exception:
            pass
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        blob = json.loads(raw)
        out = []
        for rid, val in blob.items():
            if not isinstance(val, dict):
                continue
            player = val.get('player')
            team = val.get('team')
            date = val.get('date')
            if not (player and team and date):
                continue
            full = val.get('full_text') or ''
            score_val = int(val.get('score', 0))
            # Color: prefer literal word in note text; fall back to mapping the
            # legacy numeric score so existing manual entries keep their cell color.
            color = detect_color_word(full)
            if not color:
                color = {2: 'green', 1: 'light green', 0: 'yellow',
                         -1: 'orange', -2: 'red'}.get(score_val)
            out.append({
                'id': rid,
                'player': player,
                'team': team,
                'date': date,
                'score': score_val,
                'note': full[:200],
                'full_text': full,
                'channel': None,
                'workout': bool(val.get('workout')),
                'workout_dates': val.get('workout_dates') or [],
                'is_manual': True,
                # Manual entries default to T5 (Area scout, +1 pt) — same floor
                # as Slack records: a team being on file for this player implies
                # at least an area scout was tracking. Adjustable via popup.
                'attendee_tier': 5,
                'tier_multiplier': TIER_MULTIPLIERS[5],
                'tier_label': TIER_LABELS[5],
                'color': color,
            })
        return out
    except Exception as e:
        print(f"WARN: Failed to load manual records from Redis: {e}")
        return []


def apply_overrides(records, overrides):
    if not overrides:
        return records

    score_ov = {}
    pdw_ov = {}
    points_ov = {}  # 't|player|team|date' → manual tier_multiplier override
    for key, val in overrides.items():
        if key.startswith('w|'):
            parts = key.split('|', 2)
            if len(parts) == 3:
                pdw_ov[(parts[1], parts[2])] = val
        elif key.startswith('t|'):
            parts = key.split('|')
            if len(parts) == 4:
                points_ov[(parts[1], parts[2], parts[3])] = val
        else:
            parts = key.split('|')
            if len(parts) == 3:
                score_ov[(parts[0], parts[1], parts[2])] = val

    out = []
    applied_score = 0
    applied_points = 0
    excluded = 0
    for r in records:
        rkey = (r.get('player'), r.get('team'), r.get('date'))
        copy = dict(r)
        if rkey in score_ov:
            val = score_ov[rkey]
            if val == 'NA':
                excluded += 1
                continue
            copy['score'] = val
            copy['score_overridden'] = True
            applied_score += 1
        if rkey in points_ov:
            v = points_ov[rkey]
            if isinstance(v, (int, float)):
                copy['tier_multiplier'] = int(v)
                copy['points_overridden'] = True
                applied_points += 1
        out.append(copy)

    pdw_flipped = set()
    pdw_missing = set()
    for (player, team), val in pdw_ov.items():
        matched = False
        for r in out:
            if r.get('player') == player and r.get('team') == team:
                r['workout'] = bool(val)
                r['workout_overridden'] = True
                matched = True
        (pdw_flipped if matched else pdw_missing).add((player, team))

    print(
        f"Applied overrides: {applied_score} score edits, {applied_points} point edits, "
        f"{excluded} excluded, {len(pdw_flipped)} PDW pairs flipped, "
        f"{len(pdw_missing)} PDW with no records"
    )
    for p, t in sorted(pdw_missing):
        print(f"  (skipped PDW override {p}/{t} — no records for pair)")
    return out


# --- MAIN ---
if __name__ == '__main__':
    token = os.environ.get('SLACK_BOT_TOKEN')
    if not token:
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith('SLACK_BOT_TOKEN='):
                    token = line.split('=', 1)[1].strip()

    if not token:
        print("ERROR: SLACK_BOT_TOKEN not set")
        exit(1)

    password = os.environ.get('DASHBOARD_PASSWORD', 'SVintel2026')

    messages = fetch_messages(token)
    records = parse_messages(messages)

    # Merge manual records (matrix "+ Add Entry") before building HTML and JSON.
    # Manual records live in Redis key `manual_records` and follow the same shape
    # as Slack-parsed records so matrix/detail/calendar rendering needs no changes.
    manual = load_manual_records()
    if manual:
        print(f"Merging {len(manual)} manual record(s) into RECORDS.")
        records = records + manual

    # Pull game schedule from the shared Google Sheet. Read-only — filtered to roster.
    games = fetch_game_schedule()

    html = build_html(records, password, games=games)

    out_dir = os.environ.get('OUTPUT_DIR', os.path.join(os.path.dirname(__file__), 'public'))
    out_path = os.path.join(out_dir, 'index.html')
    with open(out_path, 'w') as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")

    # Also emit teamintel.json for downstream consumers (sv-draft-fit-workout).
    # Merge manual KV overrides (website edits) so PDW toggles + score edits
    # propagate downstream. Dashboard HTML applies overrides client-side,
    # so we only merge into the JSON output.
    overrides = load_kv_overrides()
    records_for_json = apply_overrides(records, overrides)
    json_path = os.path.join(out_dir, 'teamintel.json')
    with open(json_path, 'w') as f:
        json.dump(records_for_json, f, indent=2)
    print(f"Records JSON written to {json_path}")
