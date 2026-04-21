#!/usr/bin/env python3
"""
Fetch TeamIntel messages from Slack, parse, and build dashboard.html
Runs locally or via GitHub Actions.
"""

import json, re, os, time
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
    'MIA': 'MIA', 'MIAMI': 'MIA', 'MARLINS': 'MIA',
    'MIL': 'MIL', 'MILWAUKEE': 'MIL', 'BREWERS': 'MIL',
    'MIN': 'MIN', 'MINNESOTA': 'MIN', 'TWINS': 'MIN', 'MINN': 'MIN',
    'NYM': 'NYM', 'METS': 'NYM',
    'NYY': 'NYY', 'YANKEES': 'NYY',
    'OAK': 'OAK', 'ATH': 'OAK', 'ATHLETICS': 'OAK', "A'S": 'OAK',
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

# --- Workout-date parser (pre-draft window: May 1 – July 13, 2026) ---
_WD_MONTH_NUM = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_WD_MONTH_RE = r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
_WD_MIN = datetime(2026, 5, 1)
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

def parse_messages(messages):
    records = []

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

        elif channel in CHANNEL_TO_PLAYER:
            player = CHANNEL_TO_PLAYER[channel]
            all_teams = set()
            for line in text.split('\n'):
                all_teams.update(find_teams_in_line(line))
            if not all_teams:
                continue
            for team in all_teams:
                best_score = 1
                for line in text.split('\n'):
                    line_teams = find_teams_in_line(line)
                    if team in line_teams:
                        s = score_line_for_team(line, text)
                        if s != 1:
                            best_score = s
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
                    elif lp and not lt and all_teams:
                        score = score_line_for_team(ls, text)
                        for p in lp:
                            for t in all_teams:
                                records.append({
                                    'player': p, 'team': t, 'date': date,
                                    'score': score, 'note': text.strip()[:200],
                                    'channel': channel, 'full_text': text[:3000],
                                })

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
def build_html(records, password="SVintel2026"):
    records_js = json.dumps(records)
    eastern = timezone(timedelta(hours=-4))
    now_str = datetime.now(eastern).strftime('%B %d, %Y %I:%M %p') + ' ET'
    all_2026_js = json.dumps(ALL_2026_PLAYERS)
    # Serialize alias map (sets aren't JSON-safe — convert to lists)
    player_aliases_js = json.dumps({name: sorted(aliases) for name, aliases in PLAYER_ALIASES.items()})

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, shrink-to-fit=no">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>SV TeamIntel</title>
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
.login-box .logo {{ font-size: 28px; font-weight: 800; color: #2d5016; margin-bottom: 4px; }}
.login-box .tagline {{ font-size: 13px; color: #888; margin-bottom: 24px; }}
.login-box input {{
    width: 100%; padding: 12px 16px; font-size: 14px; border: 2px solid #ddd;
    border-radius: 8px; outline: none; margin-bottom: 12px; transition: border-color 0.2s;
}}
.login-box input:focus {{ border-color: #2d5016; }}
.login-box button {{
    width: 100%; padding: 12px; font-size: 14px; font-weight: 600;
    background: #2d5016; color: white; border: none; border-radius: 8px;
    cursor: pointer; transition: background 0.2s;
}}
.login-box button:hover {{ background: #3a6b1e; }}
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
    background: linear-gradient(135deg, #1a3a0a 0%, #2d5016 50%, #3a6b1e 100%);
    color: white; padding: 18px 30px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3); position: relative; z-index: 100;
}}
.header-left {{ display: flex; align-items: center; gap: 16px; }}
.header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
.header .subtitle {{ font-size: 13px; opacity: 0.8; font-weight: 400; }}
.logo-icon {{
    width: 38px; height: 38px; background: rgba(255,255,255,0.15);
    border-radius: 8px; display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: bold;
}}
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
.stat-value {{ font-weight: 700; color: #2d5016; }}

.legend {{
    display: flex; gap: 16px; padding: 10px 30px; font-size: 12px;
    align-items: center; background: white; border-bottom: 1px solid #e0e0e0;
}}
.legend-title {{ font-weight: 600; color: #666; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.legend-swatch {{ width: 18px; height: 18px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1); }}

.matrix-container {{ padding: 20px 30px; }}
.matrix-wrapper {{ display: flex; max-height: 75vh; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
.matrix-fixed {{ flex-shrink: 0; overflow: hidden; z-index: 10; box-shadow: 2px 0 4px rgba(0,0,0,0.1); }}
.matrix-scroll {{ flex: 1; overflow: auto; -webkit-overflow-scrolling: touch; overscroll-behavior: none; }}
.matrix-wrapper {{ overscroll-behavior: none; }}
.matrix-table {{
    border-collapse: separate; border-spacing: 0; font-size: 12px;
    width: auto; min-width: 100%; background: white;
    border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}}
.matrix-table th, .matrix-table td {{
    padding: 8px 6px; text-align: center;
    border-right: 1px solid #e8e8e8; border-bottom: 1px solid #e8e8e8;
    white-space: nowrap; height: 32px;
}}
.matrix-table thead th {{
    background: #2d5016; color: white; font-weight: 600; font-size: 11px;
    letter-spacing: 0.3px; border-right-color: #3a6520; border-bottom: 2px solid #1a3a0a;
    position: sticky; top: 0; z-index: 2;
}}
.matrix-fixed td:first-child {{ background: #f8faf6; color: #2d5016; font-size: 13px; font-weight: 700; min-width: 50px; }}
.matrix-fixed td:nth-child(2) {{ background: white; text-align: left; padding-left: 10px; font-size: 12px; font-weight: 600; min-width: 140px; }}
.matrix-table tbody tr:hover td {{ background-color: #f0f7ec !important; }}

.score-2 {{ background-color: #c6efce !important; color: #1a5e1a; font-weight: 700; }}
.score-1 {{ background-color: #e2efda !important; color: #3a6b30; font-weight: 600; }}
.score-0 {{ background-color: #fff2cc !important; color: #7a6b00; font-weight: 600; }}
.score-n1 {{ background-color: #ffd9b3 !important; color: #8a4500; font-weight: 600; }}
.score-na {{ background-color: #e0e0e0 !important; color: #666; font-weight: 600; font-style: italic; }}
.score-n2 {{ background-color: #f4c7c3 !important; color: #8b1a1a; font-weight: 700; }}
td.score-cell {{ position: relative; }}
td.score-cell.clickable:hover {{ outline: 2px solid #2d5016; outline-offset: -2px; }}
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
#scorePopup .popup-reset {{
    font-size: 11px; color: #888; cursor: pointer; text-decoration: underline;
    text-align: center; display: block;
}}
#scorePopup .popup-pdw {{
    display: flex; align-items: center; justify-content: center; gap: 6px;
    margin-bottom: 8px; padding: 6px 0; border: 2px solid #d4a017; border-radius: 6px;
    cursor: pointer; font-size: 12px; font-weight: 600; color: #d4a017; background: white;
    transition: all 0.15s;
}}
#scorePopup .popup-pdw:hover {{ background: #fdf6e3; }}
#scorePopup .popup-pdw.active {{ background: #d4a017; color: white; }}
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
    background: #d4a017; color: white; border: none; border-radius: 5px;
    font-size: 12px; font-weight: 600;
}}
#messageModal .mm-back:hover {{ background: #b8890f; }}
#messageModal .mm-header {{
    font-size: 12px; color: #666; font-weight: 600; letter-spacing: 0.3px; margin-bottom: 4px;
    text-transform: uppercase;
}}
#messageModal .mm-title {{
    font-size: 16px; font-weight: 700; color: #2d5016; margin-bottom: 2px;
}}
#messageModal .mm-meta {{
    font-size: 11px; color: #888; margin-bottom: 14px;
}}
#messageModal .mm-body {{
    background: #f8faf6; border-left: 3px solid #2d5016; padding: 12px 14px;
    white-space: pre-wrap; line-height: 1.5; font-size: 13px;
    border-radius: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}
#messageModal mark.mm-hl {{
    background: #fdf6c7; border-bottom: 2px solid #d4a017;
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
    display: inline-block; background: #fdf6c7; border-bottom: 2px solid #d4a017;
    padding: 1px 6px; border-radius: 2px; margin-right: 4px; color: #6a4c00; font-weight: 600;
}}
#messageModal .mm-legend .pill-player {{
    background: #d6e7f7; border-bottom-color: #1f6bb8; color: #0d3b6a;
}}
.detail-table td.note-cell {{ cursor: pointer; }}
.detail-table tr:hover td.note-cell {{ background: #f0f7ec; }}

.detail-container {{ padding: 20px 30px; display: none; }}
.player-select-wrapper {{ display: flex; align-items: center; gap: 14px; margin-bottom: 20px; }}
.player-select-wrapper label {{ font-weight: 600; font-size: 14px; color: #555; }}
.player-select {{
    padding: 10px 14px; font-size: 14px; border: 2px solid #ccc;
    border-radius: 6px; background: white; min-width: 250px; cursor: pointer;
}}
.player-select:focus {{ outline: none; border-color: #2d5016; }}

.player-summary {{
    display: flex; gap: 24px; margin-bottom: 20px; background: white;
    padding: 16px 24px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}}
.summary-item {{ display: flex; flex-direction: column; gap: 2px; }}
.summary-label {{ font-size: 11px; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
.summary-value {{ font-size: 20px; font-weight: 700; color: #2d5016; }}

.detail-table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    background: white; border-radius: 8px; overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1); font-size: 13px;
}}
.detail-table th {{
    background: #2d5016; color: white; font-weight: 600; padding: 12px 14px;
    text-align: left; font-size: 12px; letter-spacing: 0.3px;
}}
.detail-table td {{ padding: 10px 14px; border-bottom: 1px solid #eee; vertical-align: top; }}
.detail-table td:first-child {{ white-space: nowrap; font-weight: 500; width: 100px; }}
.detail-table td:nth-child(2) {{ white-space: nowrap; font-weight: 600; width: 60px; }}
.detail-table td:nth-child(3) {{ line-height: 1.5; color: #555; max-width: 600px; }}
.detail-table td:last-child {{ text-align: center; width: 70px; font-weight: 700; }}
.detail-table tbody tr:hover {{ background: #f8faf6; }}

.score-badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; }}
.score-badge.s2 {{ background: #c6efce; color: #1a5e1a; }}
.score-badge.s1 {{ background: #e2efda; color: #3a6b30; }}
.score-badge.s0 {{ background: #fff2cc; color: #7a6b00; }}
.score-badge.sn1 {{ background: #fce4ec; color: #9a2020; }}
.score-badge.sn2 {{ background: #f4c7c3; color: #8b1a1a; }}

.clickable {{ cursor: pointer; }}
.clickable:hover {{ outline: 2px solid #2d5016; outline-offset: -2px; }}
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

    .matrix-container {{ padding: 10px 0; overflow: auto; -webkit-overflow-scrolling: touch; }}
    .matrix-table {{ font-size: 11px; }}
    .matrix-table th, .matrix-table td {{ padding: 6px 4px; }}
    .matrix-fixed td:first-child {{ min-width: 36px; font-size: 10px; }}
    .matrix-fixed td:nth-child(2) {{ min-width: 90px; font-size: 10px; padding-left: 4px; }}
    .matrix-fixed th:first-child {{ min-width: 36px; font-size: 10px; }}
    .matrix-fixed th:nth-child(2) {{ min-width: 90px; font-size: 10px; }}

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
    background: #2d5016; color: white; border: none; border-radius: 6px; cursor: pointer;
}}
.cal-nav button:hover {{ background: #3a6b1d; }}
.cal-month-label {{ font-size: 16px; font-weight: 700; min-width: 150px; text-align: center; color: #2d5016; }}
.cal-addbtn {{
    padding: 6px 14px; font-size: 13px; font-weight: 600;
    background: #d4a017; color: white; border: none; border-radius: 6px; cursor: pointer;
}}
.cal-addbtn:hover {{ background: #b8890f; }}
.cal-filter {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: #555; }}
.cal-filter select, .cal-filter input {{ padding: 4px 8px; font-size: 12px; border: 1px solid #ccc; border-radius: 4px; }}
.cal-grid {{
    display: grid; grid-template-columns: repeat(7, 1fr);
    border: 1px solid #d6d6d6; border-radius: 6px; overflow: hidden; background: #eee; gap: 1px;
}}
.cal-dow {{
    background: #2d5016; color: white; padding: 6px 8px; font-size: 11px; font-weight: 600;
    text-align: center; letter-spacing: 0.5px;
}}
.cal-cell {{
    background: white; min-height: 92px; padding: 4px 5px; position: relative;
    cursor: pointer; transition: background 0.12s;
}}
.cal-cell:hover {{ background: #f0f7ec; }}
.cal-cell.other-month {{ background: #fafafa; color: #aaa; }}
.cal-cell.today {{ background: #fffbe6; }}
.cal-cell.today::before {{
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #d4a017;
}}
.cal-daynum {{ font-size: 11px; color: #888; font-weight: 600; margin-bottom: 2px; }}
.cal-cell.today .cal-daynum {{ color: #d4a017; }}
.cal-chip {{
    display: block; font-size: 10px; padding: 2px 5px; margin-bottom: 2px;
    border-radius: 3px; color: white; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    cursor: pointer; font-weight: 600;
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
.cal-cell.cal-today {{ background: #fffbe6; }}
.cal-cell.cal-today::before {{
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #d4a017;
}}
.cal-drafttag {{
    display: inline-block; font-size: 8px; padding: 1px 4px; background: #d4a017; color: white;
    border-radius: 2px; vertical-align: middle; font-weight: 700; letter-spacing: 0.5px;
}}

/* --- Event modal --- */
#evOverlay {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000;
    display: none; align-items: center; justify-content: center;
}}
#evOverlay.open {{ display: flex; }}
#evModal {{
    background: white; border-radius: 8px; padding: 20px 22px; width: 420px; max-width: 92vw;
    max-height: 90vh; overflow-y: auto; box-shadow: 0 6px 32px rgba(0,0,0,0.3);
}}
.ev-title {{ font-size: 16px; font-weight: 700; color: #2d5016; margin-bottom: 14px; }}
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
.ev-save {{ flex: 1; padding: 9px 14px; background: #2d5016; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; }}
.ev-save:hover {{ background: #3a6b1d; }}
.ev-cancel {{ padding: 9px 14px; background: #eee; color: #333; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; }}
.ev-delete {{ padding: 9px 14px; background: #c94040; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; margin-right: auto; }}
.ev-delete:hover {{ background: #a83030; }}
.ev-slack {{ padding: 9px 14px; background: #4a154b; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; margin-right: auto; }}
.ev-slack:hover {{ background: #611f62; }}
.ev-note {{ font-size: 11px; color: #888; margin-top: 6px; }}

@media (max-width: 640px) {{
    .cal-cell {{ min-height: 70px; padding: 3px; }}
    .cal-chip {{ font-size: 9px; padding: 1px 4px; }}
    .cal-daynum {{ font-size: 10px; }}
    .cal-toolbar {{ gap: 8px; }}
    .cal-month-label {{ font-size: 14px; min-width: 110px; }}
}}
</style>
</head>
<body>

<!-- PASSWORD GATE -->
<div id="loginGate">
    <div class="login-box">
        <div class="logo">SV TeamIntel</div>
        <div class="tagline">Stadium Ventures &mdash; 2026 Draft Intelligence</div>
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
        <div class="logo-icon">SV</div>
        <div>
            <h1>TeamIntel Dashboard</h1>
            <div class="subtitle">Player Intelligence Score By Team &mdash; 2026 MLB Draft</div>
            <div class="last-updated">Last updated: {now_str}</div>
        </div>
    </div>
    <div class="nav-tabs">
        <div class="nav-tab active" onclick="showView('matrix')">Matrix View</div>
        <div class="nav-tab" onclick="showView('detail')">Detail View</div>
        <div class="nav-tab" onclick="showView('calendar')">Calendar</div>
    </div>
</div>

<div class="legend">
    <span class="legend-title">Score Key:</span>
    <div class="legend-item"><div class="legend-swatch" style="background:#c6efce"></div>2 (Green / Strong Interest)</div>
    <div class="legend-item"><div class="legend-swatch" style="background:#e2efda"></div>1 (Light Green / Interest)</div>
    <div class="legend-item"><div class="legend-swatch" style="background:#fff2cc"></div>0 (Yellow / Neutral)</div>
    <div class="legend-item"><div class="legend-swatch" style="background:#fce4ec"></div>-1 (Red / Cool/No Contact)</div>
    <div class="legend-item"><div class="legend-swatch" style="background:#f4c7c3"></div>-2 (Dark Red / Negative)</div>
    <div class="legend-item"><div class="legend-swatch" style="background:#fff;box-shadow:inset 0 0 0 3px #d4a017"></div>Pre-Draft Workout</div>
    <div style="margin-left:auto;display:flex;align-items:center;gap:12px;">
        <span style="font-size:11px;color:#999;">Tap a score to view details, then click any score badge to edit</span>
    </div>
</div>

<div id="statsBar" class="stats-bar"></div>

<div id="matrixView" class="matrix-container">
    <div class="matrix-wrapper">
        <div class="matrix-fixed" id="matrixFixed">
            <table class="matrix-table" id="matrixFixedTable"></table>
        </div>
        <div class="matrix-scroll" id="matrixScroll">
            <table class="matrix-table" id="matrixScrollTable"></table>
        </div>
    </div>
</div>

<div id="detailView" class="detail-container">
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px;">
        <button onclick="showView('matrix')" style="padding:6px 14px;font-size:13px;font-weight:600;background:#2d5016;color:white;border:none;border-radius:6px;cursor:pointer;">&#8592; Back</button>
        <button onclick="jumpToCalendarForCurrentPlayer()" style="padding:6px 14px;font-size:13px;font-weight:600;background:#d4a017;color:white;border:none;border-radius:6px;cursor:pointer;" title="Show this player's workouts on the calendar">&#x1F4C5; View Calendar</button>
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
        <div class="cal-filter">
            <label for="calPlayerFilter">Player:</label>
            <select id="calPlayerFilter" onchange="renderCalendar()"><option value="">All</option></select>
        </div>
        <div class="cal-filter">
            <label for="calTypeFilter">Type:</label>
            <select id="calTypeFilter" onchange="renderCalendar()">
                <option value="">All</option>
                <option value="workout">Workouts</option>
                <option value="playoff">Playoffs</option>
                <option value="travel">Travel</option>
                <option value="other">Other</option>
            </select>
        </div>
    </div>
    <div class="cal-grid" id="calGrid"></div>
    <div class="cal-legend" id="calLegend"></div>
    <div style="margin-top:10px;font-size:11px;color:#888;">
        Workouts are auto-parsed from Slack messages. Click a chip to view/edit; use <b>+ Add Event</b> for new entries.
        <span style="opacity:0.8;display:inline-block;margin-left:10px;">
            <span style="display:inline-block;padding:1px 6px;border:1.5px dashed #2d5016;color:#2d5016;border-radius:3px;font-size:10px;font-weight:500;">DASHED</span> = invite &nbsp;·&nbsp;
            <span style="display:inline-block;padding:1px 6px;background:#2d5016;color:white;border-radius:3px;font-size:10px;font-weight:800;">&#10003; SOLID</span> = confirmed going &nbsp;·&nbsp;
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
                <option value="playoff">Playoff Game</option>
                <option value="travel">Travel</option>
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
            <button class="ev-slack" id="evSlackBtn" onclick="openSlackFromEvent()" style="display:none;" title="Open the originating Slack message">&#x1F4AC; View Slack Message</button>
            <button class="ev-cancel" onclick="closeEventModal()">Cancel</button>
            <button class="ev-save" onclick="saveEvent()">Save</button>
        </div>
        <div class="ev-note" id="evNote"></div>
    </div>
</div>

<script>
const RECORDS = {records_js};
const ALL_TEAMS = {json.dumps(ALL_TEAMS)};
const ALL_2026_PLAYERS = {all_2026_js};
const PLAYER_ALIASES = {player_aliases_js};

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
    // Default: no back button. openSlackFromEvent sets it after this call.
    _mmReturnToEvent = null;
    const bb = document.getElementById('mmBackBtn');
    if (bb) bb.style.display = 'none';
    const body = (r.full_text && r.full_text.length > r.note.length) ? r.full_text : r.note;
    const isPDWrow = !!r.workout;
    const playerAliases = (PLAYER_ALIASES[r.player] || []).concat([r.player]);
    document.getElementById('mmTitle').textContent = r.player + ' · ' + r.team;
    document.getElementById('mmMeta').textContent = r.date + ' · #' + (r.channel || 'unknown') +
        (isPDWrow ? ' · PDW flagged' : '');
    const groups = [
        // Draw PDW highlight first (it takes priority on overlap).
        {{ phrases: r.workout_matches || [], cls: 'mm-hl', wholeWord: false }},
        {{ phrases: playerAliases, cls: 'mm-hl-player', wholeWord: true }},
    ];
    document.getElementById('mmBody').innerHTML = _highlightMatches(body, groups);
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
        if (score === null) {{
            delete scoreOverrides[key];
        }} else {{
            scoreOverrides[key] = score;
        }}
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
    if (y + 120 > window.innerHeight) y = rect.top - 120;
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';
}}

function closeScorePopup() {{
    document.getElementById('scorePopup').style.display = 'none';
    document.getElementById('scoreOverlay').style.display = 'none';
}}

function buildMatrix() {{
    // Only count records that aren't manually flagged NA (false connections)
    const activeRecords = RECORDS.filter(r => !isExcluded(r));
    const latest = {{}};
    const counts = {{}};
    activeRecords.forEach(r => {{
        const key = r.player + '|' + r.team;
        if (!latest[key] || r.date > latest[key].date) latest[key] = r;
        counts[key] = (counts[key] || 0) + 1;
    }});
    // Track if any record for a player+team has a workout invite
    const workoutMap = {{}};
    activeRecords.forEach(r => {{
        const key = r.player + '|' + r.team;
        if (r.workout) workoutMap[key] = true;
    }});
    // Apply manual PDW overrides
    Object.keys(scoreOverrides).forEach(k => {{
        if (k.startsWith('w|')) {{
            const parts = k.substring(2);
            if (scoreOverrides[k]) workoutMap[parts] = true;
            else delete workoutMap[parts];
        }}
    }});
    const playerTeams = {{}}, playerTeamCounts = {{}}, playerAllScores = {{}};
    Object.values(latest).forEach(r => {{
        if (!playerTeams[r.player]) playerTeams[r.player] = {{}};
        if (!playerTeamCounts[r.player]) playerTeamCounts[r.player] = {{}};
        const score = getScore(r);
        playerTeams[r.player][r.team] = score;
        playerTeamCounts[r.player][r.team] = counts[r.player + '|' + r.team] || 0;
        if (!playerAllScores[r.player]) playerAllScores[r.player] = [];
        playerAllScores[r.player].push(score);
    }});
    ALL_2026_PLAYERS.forEach(p => {{
        if (!playerTeams[p]) playerTeams[p] = {{}};
        if (!playerTeamCounts[p]) playerTeamCounts[p] = {{}};
        if (!playerAllScores[p]) playerAllScores[p] = [];
    }});
    const playerAvgs = {{}};
    Object.keys(playerAllScores).forEach(p => {{
        const s = playerAllScores[p].filter(v => typeof v === 'number');
        playerAvgs[p] = s.length > 0 ? s.reduce((a,b) => a+b, 0) / s.length : null;
    }});
    const playerTotals = {{}};
    Object.keys(playerTeamCounts).forEach(p => {{
        playerTotals[p] = Object.values(playerTeamCounts[p]).reduce((a,b) => a+b, 0);
    }});
    const sortedPlayers = Object.keys(playerTotals).sort((a,b) => {{
        const ta = playerTotals[a] || 0, tb = playerTotals[b] || 0;
        if (tb !== ta) return tb - ta;
        return a.localeCompare(b);
    }});
    return {{ playerTeams, playerTeamCounts, playerAvgs, playerTotals, sortedPlayers, workoutMap }};
}}

function scoreClass(s) {{
    if (s === 2) return 'score-2';
    if (s === 1) return 'score-1';
    if (s === 0) return 'score-0';
    if (s === -1) return 'score-n1';
    if (s === -2) return 'score-n2';
    return '';
}}
function badgeClass(s) {{
    if (s === 2) return 's2';
    if (s === 1) return 's1';
    if (s === 0) return 's0';
    if (s === -1) return 'sn1';
    if (s === -2) return 'sn2';
    return '';
}}

function renderMatrix() {{
    const {{ playerTeams, playerTeamCounts, playerAvgs, playerTotals, sortedPlayers, workoutMap }} = buildMatrix();

    var fHtml = '<thead><tr><th>TOTAL</th><th>Client</th></tr></thead><tbody>';
    var sHtml = '<thead><tr>';
    ALL_TEAMS.forEach(t => sHtml += '<th>' + t + '</th>');
    sHtml += '</tr></thead><tbody>';

    sortedPlayers.forEach(player => {{
        const total = playerTotals[player] || 0;
        const avg = playerAvgs[player];
        const avgClass = avg === null ? '' : avg >= 1.5 ? 'score-2' : avg >= 0.75 ? 'score-1' : avg >= 0 ? 'score-0' : avg >= -1 ? 'score-n1' : 'score-n2';
        const titleAttr = avg !== null ? ' title="Avg score: ' + avg.toFixed(2) + '"' : '';
        fHtml += '<tr><td class="' + avgClass + '"' + titleAttr + '>' + total + '</td>';
        fHtml += '<td class="clickable" onclick="jumpToDetail(\\'' + player.replace(/'/g, "\\\\'") + '\\')">' + player + '</td></tr>';
        sHtml += '<tr>';
        const esc = player.replace(/'/g, "\\\\'");
        ALL_TEAMS.forEach(team => {{
            const s = playerTeams[player] && playerTeams[player][team];
            const cnt = (playerTeamCounts[player] && playerTeamCounts[player][team]) || 0;
            const wk = workoutMap[player + '|' + team];
            if (s !== undefined && s !== null && typeof s === 'number' && cnt > 0) {{
                sHtml += '<td class="' + scoreClass(s) + ' score-cell clickable' + (wk ? ' workout' : '') + '" onclick="jumpToDetail(\\'' + esc + '\\', \\'' + team + '\\')" title="Score: ' + s + ' \\u2022 ' + cnt + ' touch' + (cnt===1?'':'es') + '">' + cnt + '</td>';
            }} else {{
                sHtml += '<td></td>';
            }}
        }});
        sHtml += '</tr>';
    }});
    fHtml += '</tbody>';
    sHtml += '</tbody>';
    document.getElementById('matrixFixedTable').innerHTML = fHtml;
    document.getElementById('matrixScrollTable').innerHTML = sHtml;

    var scrollEl = document.getElementById('matrixScroll');
    var fixedEl = document.getElementById('matrixFixed');
    scrollEl.onscroll = function() {{ fixedEl.scrollTop = scrollEl.scrollTop; }};

    let uniquePairs = 0;
    Object.keys(playerTeams).forEach(p => uniquePairs += Object.keys(playerTeams[p]).length);
    document.getElementById('statsBar').innerHTML =
        '<div class="stat-item"><span class="stat-label">Players:</span><span class="stat-value">' + sortedPlayers.length + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Intel Reports:</span><span class="stat-value">' + RECORDS.length + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Player-Team Connections:</span><span class="stat-value">' + uniquePairs + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Date Range:</span><span class="stat-value">Aug 2025 - Present</span></div>';
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
    const teams = new Set(pr.filter(r => !isExcluded(r)).map(r => r.team));
    const numScores = pr.filter(r => !isExcluded(r)).map(r => getScore(r));
    const avg = numScores.length > 0 ? numScores.reduce((a,b) => a + b, 0) / numScores.length : 0;
    document.getElementById('playerSummary').innerHTML =
        '<div class="summary-item"><span class="summary-label">Player</span><span class="summary-value">' + player + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Intel Reports</span><span class="summary-value">' + numScores.length + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Teams Connected</span><span class="summary-value">' + teams.size + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Avg Score</span><span class="summary-value">' + (numScores.length > 0 ? avg.toFixed(2) : '-') + '</span></div>';

    let hiddenBar = '';
    if (_filterTeam) {{
        hiddenBar += '<div style="padding:6px 10px;font-size:12px;color:#555;margin-bottom:6px;">' +
            'Filtered to <strong>' + _filterTeam + '</strong> \\u00b7 ' +
            '<span style="text-decoration:underline;cursor:pointer;color:#2d5016;" onclick="clearTeamFilter()">show all teams</span></div>';
    }}
    if (hiddenCount > 0) {{
        const label = _showHidden ? 'hide' : 'show';
        hiddenBar += '<div style="padding:6px 10px;font-size:12px;color:#888;margin-bottom:6px;">' +
            hiddenCount + ' record' + (hiddenCount===1?'':'s') + ' hidden (marked NA) \\u00b7 ' +
            '<span style="text-decoration:underline;cursor:pointer;color:#2d5016;" onclick="toggleHidden()">' + label + '</span></div>';
    }}

    let html = '<thead><tr><th>Date</th><th>Team</th><th>Intel Note</th><th>Score</th></tr></thead><tbody>';
    if (pr.length === 0) {{
        html += '<tr><td colspan="4" style="text-align:center;color:#999;padding:20px;">No intel reports yet</td></tr>';
    }}
    pr.forEach((r, i) => {{
        const note = r.note.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>').replace(/&amp;/g,'&');
        const s = getScore(r);
        const esc = r.player.replace(/'/g, "\\\\'");
        const isOverridden = scoreOverrides.hasOwnProperty(r.player + '|' + r.team + '|' + r.date);
        const excluded = isExcluded(r);
        const wBadge = !excluded && isPDW(r.player, r.team) ? '<span class="workout-badge">PDW</span>' : '';
        const rowKey = r.player + '|' + r.team + '|' + r.date + '|' + i;
        const rowStyle = excluded ? ' style="opacity:0.45;"' : '';
        const scoreDisp = (s === 'NA') ? 'NA' : (s + (isOverridden ? ' *' : ''));
        const badgeCls = (s === 'NA') ? 'score-na' : badgeClass(s);
        html += '<tr' + rowStyle + '><td>' + r.date + '</td><td>' + r.team + wBadge + '</td>' +
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
    'MIL':'#12284B','MIN':'#002B5C','NYM':'#FF5910','NYY':'#003087','OAK':'#003831',
    'PHI':'#E81828','PIT':'#FDB827','SD':'#2F241D','SF':'#FD5A1E','SEA':'#0C2C56',
    'STL':'#C41E3A','TB':'#092C5C','TEX':'#003278','TOR':'#134A8E','WSH':'#AB0003'
}};
const TYPE_COLORS = {{ workout:null, playoff:'#6a3a9a', travel:'#555', other:'#999' }};
const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

var _calMonth = new Date(2026, 4, 1); // May 2026 default
var _calEvents = {{}};       // manual events from API
var _calAutoEvents = [];     // events derived from RECORDS.workout_dates
var _calRecordsByPlayerTeam = {{}};  // 'player|team' -> [records] for Slack link lookup
var _calChipIndex = {{}};    // 'c5' -> ev, rebuilt each render (dispatch table for chip clicks)
var _calChipCounter = 0;
var _calInitialized = false;

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
        if (!r.workout) return;
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
    return TYPE_COLORS[ev.type] || '#888';
}}

function _chipLabel(ev) {{
    if (ev.type === 'workout') {{
        return (ev.team || '?') + ' · ' + (ev.player || '?') + (ev.tentative ? ' (T)' : '');
    }}
    const t = ev.title || ({{playoff:'Playoff', travel:'Travel', other:'Event'}}[ev.type] || 'Event');
    return (ev.player || '?') + ' · ' + t;
}}

function renderCalendar() {{
    document.getElementById('calMonthLabel').textContent = _fmtMonth(_calMonth);

    const playerSel = document.getElementById('calPlayerFilter');
    if (playerSel.options.length <= 1) {{
        // Only players with a pre-draft workout invite (workout:true record) or a manual workout event.
        const workoutPlayers = new Set(RECORDS.filter(r => r.workout).map(r => r.player));
        Object.values(_calEvents || {{}}).forEach(ev => {{
            if (ev.type === 'workout' && ev.player) workoutPlayers.add(ev.player);
        }});
        [...workoutPlayers].sort().forEach(p => {{
            const o = document.createElement('option'); o.value = p; o.textContent = p; playerSel.appendChild(o);
        }});
    }}
    const fPlayer = playerSel.value;
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
        if (fPlayer && ev.player !== fPlayer) return false;
        if (fType && ev.type !== fType) return false;
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
    openEventModal(ev.id || null, ev.date, ev);
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
    playerSel.value = (ev && ev.player) || playerSel.options[0].value;
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
    document.getElementById('evDeleteBtn').style.display = (id && ev && !ev.auto) ? 'inline-block' : 'none';
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
    // Make sure calendar is initialized so filter dropdown is populated.
    (async () => {{
        if (!_calInitialized) {{ await initCalendar(); }}
        const sel = document.getElementById('calPlayerFilter');
        // Ensure option exists (players only-in-RECORDS go in at init)
        let found = false;
        for (let i = 0; i < sel.options.length; i++) {{ if (sel.options[i].value === player) {{ found = true; break; }} }}
        if (!found) {{ const o = document.createElement('option'); o.value = player; o.textContent = player; sel.appendChild(o); }}
        sel.value = player;
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

async function initCalendar() {{
    _calInitialized = true;
    buildAutoEvents();
    await loadCalendarEvents();
    renderCalendar();
}}

async function init() {{
    await loadOverrides();
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
    <div class="popup-scores">
        <button class="ps2" onclick="saveScore(2)">2</button>
        <button class="ps1" onclick="saveScore(1)">1</button>
        <button class="ps0" onclick="saveScore(0)">0</button>
        <button class="psn1" onclick="saveScore(-1)">-1</button>
        <button class="psn2" onclick="saveScore(-2)">-2</button>
        <button class="psna" onclick="saveScore('NA')" title="Not a real connection — hide this record">NA</button>
    </div>
    <div class="popup-pdw" id="pdwToggle" onclick="togglePDW()">Pre-Draft Workout</div>
    <span class="popup-reset" onclick="saveScore(null)">Reset to original</span>
</div>
<div id="messageOverlay" onclick="if(event.target===this) closeMessageModal()">
    <div id="messageModal">
        <button class="mm-close" onclick="closeMessageModal()">&times;</button>
        <button class="mm-back" id="mmBackBtn" onclick="returnToEvent()" style="display:none;">&#8592; Back to Event</button>
        <div class="mm-header">Full Slack Message</div>
        <div class="mm-title" id="mmTitle"></div>
        <div class="mm-meta" id="mmMeta"></div>
        <div class="mm-body" id="mmBody"></div>
        <div class="mm-legend" id="mmLegend" style="display:none;">
            <span class="pill">highlighted</span> = text that triggered the PDW flag
        </div>
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


def apply_overrides(records, overrides):
    if not overrides:
        return records

    score_ov = {}
    pdw_ov = {}
    for key, val in overrides.items():
        if key.startswith('w|'):
            parts = key.split('|', 2)
            if len(parts) == 3:
                pdw_ov[(parts[1], parts[2])] = val
        else:
            parts = key.split('|')
            if len(parts) == 3:
                score_ov[(parts[0], parts[1], parts[2])] = val

    out = []
    applied_score = 0
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
        f"Applied overrides: {applied_score} score edits, {excluded} excluded, "
        f"{len(pdw_flipped)} PDW pairs flipped, {len(pdw_missing)} PDW with no records"
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
    html = build_html(records, password)

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
