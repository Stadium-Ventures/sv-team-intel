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
                if name == '2026-draft-general' or 'teamintel' in tl or 'team intel' in tl:
                    all_messages.append({
                        'channel': name, 'channel_id': cid,
                        'ts': msg['ts'],
                        'date': datetime.fromtimestamp(float(msg['ts'])).strftime('%Y-%m-%d'),
                        'text': text, 'user': msg.get('user', ''),
                    })

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
    for r in records:
        text = r.get('full_text', '') + '\n' + r.get('note', '')
        matches = workout_match_details(text, r.get('player'), r.get('channel'))
        r['workout'] = len(matches) > 0
        # Store just the matched phrases (lowercase text triggers highlighting in JS)
        r['workout_matches'] = [m['text'] for m in matches]

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
        <div class="player-select-wrapper" style="margin-bottom:0;">
            <label>Select Player:</label>
            <select class="player-select" id="playerSelect" onchange="renderDetail()">
                <option value="">-- Choose a player --</option>
            </select>
        </div>
    </div>
    <div id="playerSummary" class="player-summary"></div>
    <div id="hiddenBar"></div>
    <table class="detail-table" id="detailTable"></table>
</div>

</div><!-- /appContent -->

<script>
const RECORDS = {records_js};
const ALL_TEAMS = {json.dumps(ALL_TEAMS)};
const ALL_2026_PLAYERS = {all_2026_js};
const PLAYER_ALIASES = {player_aliases_js};

// --- Override system (Vercel KV) — per-record overrides ---
var scoreOverrides = {{}};
var _popupPlayer = '', _popupTeam = '', _popupDate = '';
var _showHidden = false;

async function loadOverrides() {{
    try {{
        const res = await fetch('/api/overrides');
        if (res.ok) scoreOverrides = await res.json();
    }} catch(e) {{ /* offline / local dev */ }}
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
}}

document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') closeMessageModal();
}});

async function saveScore(score) {{
    const player = _popupPlayer, team = _popupTeam, date = _popupDate;
    const key = player + '|' + team + '|' + date;
    closeScorePopup();
    try {{
        await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ player, team, date, score }})
        }});
        if (score === null) {{
            delete scoreOverrides[key];
        }} else {{
            scoreOverrides[key] = score;
        }}
    }} catch(e) {{ alert('Failed to save override'); }}
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
        await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ key: wk, score: toStore }})
        }});
        if (toStore === null) {{
            delete scoreOverrides[wk];
        }} else {{
            scoreOverrides[wk] = toStore;
        }}
    }} catch(e) {{ alert('Failed to save'); }}
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
                sHtml += '<td class="' + scoreClass(s) + ' score-cell clickable' + (wk ? ' workout' : '') + '" onclick="jumpToDetail(\\'' + esc + '\\')" title="Score: ' + s + ' \\u2022 ' + cnt + ' touch' + (cnt===1?'':'es') + '">' + cnt + '</td>';
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
    const allPr = RECORDS.filter(r => r.player === player).sort((a,b) => b.date.localeCompare(a.date));
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
    if (hiddenCount > 0) {{
        const label = _showHidden ? 'hide' : 'show';
        hiddenBar = '<div style="padding:6px 10px;font-size:12px;color:#888;margin-bottom:6px;">' +
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

function jumpToDetail(player) {{
    document.getElementById('playerSelect').value = player;
    renderDetail();
    showView('detail');
}}

function showView(view) {{
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    if (view === 'matrix') {{
        document.getElementById('matrixView').style.display = 'block';
        document.getElementById('detailView').style.display = 'none';
        document.querySelectorAll('.nav-tab')[0].classList.add('active');
    }} else {{
        document.getElementById('matrixView').style.display = 'none';
        document.getElementById('detailView').style.display = 'block';
        document.querySelectorAll('.nav-tab')[1].classList.add('active');
    }}
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
        <div class="mm-header">Full Slack Message</div>
        <div class="mm-title" id="mmTitle"></div>
        <div class="mm-meta" id="mmMeta"></div>
        <div class="mm-body" id="mmBody"></div>
        <div class="mm-legend" id="mmLegend" style="display:none;">
            <span class="pill">highlighted</span> = text that triggered the PDW flag
        </div>
    </div>
</div>
</body>
</html>'''
    return html


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
