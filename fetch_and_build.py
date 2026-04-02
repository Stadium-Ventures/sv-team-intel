#!/usr/bin/env python3
"""
Fetch TeamIntel messages from Slack, parse, and build dashboard.html
Runs locally or via GitHub Actions.
"""

import json, re, os, time
from collections import defaultdict
from datetime import datetime
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
                if 'teamintel' in tl or 'team intel' in tl:
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
    return found

def score_line_for_team(line, full_text=""):
    ll = line.lower()
    if re.search(r'\bred\b', ll) and 'green' not in ll:
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
                        'channel': channel, 'full_text': text[:400],
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
                    'channel': channel, 'full_text': text[:400],
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
                                'channel': channel, 'full_text': text[:400],
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
                                    'channel': channel, 'full_text': text[:400],
                                })
                    elif lp and not lt and all_teams:
                        score = score_line_for_team(ls, text)
                        for p in lp:
                            for t in all_teams:
                                records.append({
                                    'player': p, 'team': t, 'date': date,
                                    'score': score, 'note': text.strip()[:200],
                                    'channel': channel, 'full_text': text[:400],
                                })

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
    now_str = datetime.now().strftime('%B %d, %Y %I:%M %p')
    all_2026_js = json.dumps(ALL_2026_PLAYERS)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, shrink-to-fit=no">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>Stadium Ventures - TeamIntel Dashboard</title>
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
    white-space: nowrap;
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
.score-n1 {{ background-color: #fce4ec !important; color: #9a2020; font-weight: 600; }}
.score-n2 {{ background-color: #f4c7c3 !important; color: #8b1a1a; font-weight: 700; }}
td.score-cell {{ position: relative; }}
td.score-cell.clickable:hover {{ outline: 2px solid #2d5016; outline-offset: -2px; }}

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
    <div style="margin-left:auto;display:flex;align-items:center;gap:12px;">
        <span style="font-size:11px;color:#999;">Tap any score to see details</span>
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
    <div class="player-select-wrapper">
        <label>Select Player:</label>
        <select class="player-select" id="playerSelect" onchange="renderDetail()">
            <option value="">-- Choose a player --</option>
        </select>
    </div>
    <div id="playerSummary" class="player-summary"></div>
    <table class="detail-table" id="detailTable"></table>
</div>

</div><!-- /appContent -->

<script>
const RECORDS = {records_js};
const ALL_TEAMS = {json.dumps(ALL_TEAMS)};
const ALL_2026_PLAYERS = {all_2026_js};

function showScoreDetail(player) {{
    document.getElementById('playerSelect').value = player;
    renderDetail();
    showView('detail');
}}

function buildMatrix() {{
    const latest = {{}};
    RECORDS.forEach(r => {{
        const key = r.player + '|' + r.team;
        if (!latest[key] || r.date > latest[key].date) latest[key] = r;
    }});
    const playerTeams = {{}}, playerAllScores = {{}};
    Object.values(latest).forEach(r => {{
        if (!playerTeams[r.player]) playerTeams[r.player] = {{}};
        playerTeams[r.player][r.team] = r.score;
        if (!playerAllScores[r.player]) playerAllScores[r.player] = [];
        playerAllScores[r.player].push(r.score);
    }});
    ALL_2026_PLAYERS.forEach(p => {{
        if (!playerTeams[p]) playerTeams[p] = {{}};
        if (!playerAllScores[p]) playerAllScores[p] = [];
    }});
    const playerAvgs = {{}};
    Object.keys(playerAllScores).forEach(p => {{
        const s = playerAllScores[p];
        playerAvgs[p] = s.length > 0 ? s.reduce((a,b) => a+b, 0) / s.length : null;
    }});
    const sortedPlayers = Object.keys(playerAvgs).sort((a,b) => {{
        if (playerAvgs[a] === null && playerAvgs[b] === null) return a.localeCompare(b);
        if (playerAvgs[a] === null) return 1;
        if (playerAvgs[b] === null) return 1;
        return playerAvgs[b] - playerAvgs[a];
    }});
    return {{ playerTeams, playerAvgs, sortedPlayers }};
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
    const {{ playerTeams, playerAvgs, sortedPlayers }} = buildMatrix();

    var fHtml = '<thead><tr><th>AVG</th><th>Client</th></tr></thead><tbody>';
    var sHtml = '<thead><tr>';
    ALL_TEAMS.forEach(t => sHtml += '<th>' + t + '</th>');
    sHtml += '</tr></thead><tbody>';

    sortedPlayers.forEach(player => {{
        const avg = playerAvgs[player];
        const avgDisplay = avg !== null ? avg.toFixed(2) : '-';
        const avgClass = avg === null ? '' : avg >= 1.5 ? 'score-2' : avg >= 0.75 ? 'score-1' : avg >= 0 ? 'score-0' : 'score-n1';
        fHtml += '<tr><td class="' + avgClass + '">' + avgDisplay + '</td>';
        fHtml += '<td class="clickable" onclick="jumpToDetail(\\'' + player.replace(/'/g, "\\\\'") + '\\')">' + player + '</td></tr>';
        sHtml += '<tr>';
        const esc = player.replace(/'/g, "\\\\'");
        ALL_TEAMS.forEach(team => {{
            const s = playerTeams[player] && playerTeams[player][team];
            if (s !== undefined && s !== null) {{
                sHtml += '<td class="' + scoreClass(s) + ' score-cell clickable" onclick="showScoreDetail(\\'' + esc + '\\')">' + s + '</td>';
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

function renderDetail() {{
    const player = document.getElementById('playerSelect').value;
    if (!player) return;
    const pr = RECORDS.filter(r => r.player === player).sort((a,b) => b.date.localeCompare(a.date));
    const teams = new Set(pr.map(r => r.team));
    const avg = pr.length > 0 ? pr.reduce((a,r) => a + r.score, 0) / pr.length : 0;
    document.getElementById('playerSummary').innerHTML =
        '<div class="summary-item"><span class="summary-label">Player</span><span class="summary-value">' + player + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Intel Reports</span><span class="summary-value">' + pr.length + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Teams Connected</span><span class="summary-value">' + teams.size + '</span></div>' +
        '<div class="summary-item"><span class="summary-label">Avg Score</span><span class="summary-value">' + (pr.length > 0 ? avg.toFixed(2) : '-') + '</span></div>';
    let html = '<thead><tr><th>Date</th><th>Team</th><th>Intel Note</th><th>Score</th></tr></thead><tbody>';
    if (pr.length === 0) {{
        html += '<tr><td colspan="4" style="text-align:center;color:#999;padding:20px;">No intel reports yet</td></tr>';
    }}
    pr.forEach(r => {{
        const note = r.note.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>').replace(/&amp;/g,'&');
        html += '<tr><td>' + r.date + '</td><td>' + r.team + '</td><td>' + note + '</td>' +
            '<td><span class="score-badge ' + badgeClass(r.score) + '">' + r.score + '</span></td></tr>';
    }});
    html += '</tbody>';
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

function init() {{
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

    out_dir = os.environ.get('OUTPUT_DIR', os.path.dirname(__file__))
    out_path = os.path.join(out_dir, 'index.html')
    with open(out_path, 'w') as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")
