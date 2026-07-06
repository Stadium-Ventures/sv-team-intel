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
    'torres': 'Boston Torres', 'neal': 'Brady Neal', 'diaz': 'Devin Diaz',
    'lawrence': 'Lucas Lawrence', 'beaird': 'Phinn Beaird', 'eckelman': 'Mason Eckelman',
    'fowler': 'Bryce Fowler', 'mccarron': 'Duke McCarron', 'ellis': 'Lee Ellis',
    'tryon': 'Ben Tryon', 'lay': 'Ethan Lay',
}

ALL_2026_PLAYERS = sorted(set(PLAYERS_2026.values()))

CHANNEL_TO_PLAYER = {
    'aiden-robbins': 'Aiden Robbins', 'cameron-flukey': 'Cameron Flukey',
    'kyle-jones': 'Kyle Jones', 'myles-bailey': 'Myles Bailey',
    'trevor-condon': 'Trevor Condon', 'bo-lowrance': 'Bo Lowrance',
    'taj-marchand': 'Taj Marchand', 'joe-tiroly': 'Joe Tiroly',
    'alex-kranzler': 'Alex Kranzler', 'boston-torres': 'Boston Torres',
    'brady-neal': 'Brady Neal', 'devin-diaz': 'Devin Diaz',
    'lucas-lawrence': 'Lucas Lawrence',
    'phinn-beaird': 'Phinn Beaird', 'mason-eckelman': 'Mason Eckelman',
    'bryce-fowler': 'Bryce Fowler',
    'ben-tryon': 'Ben Tryon', 'duke-mccarron': 'Duke McCarron',
    'lee-ellis': 'Lee Ellis', 'ethan-lay': 'Ethan Lay',
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

# 2026 MLB Draft board — every slotted pick (rounds 1-10, 313 picks):
# [overall_pick, team_abbrev, slot_bonus_value]. Source: MLB.com 2026 bonus-pool
# pick values. Team abbrevs normalized to repo conventions (CWS->CHW, OAK->ATH).
# Powers the Draft Card view; each square is seeded with the engine's most-recent
# color for that pick's team.
DRAFT_PICKS_2026 = [
    [1,'CHW',11350600], [2,'TB',10507000], [3,'MIN',9740100], [4,'SF',8988400], [5,'PIT',8336500],
    [6,'KC',7746100], [7,'BAL',7327200], [8,'ATH',6982600], [9,'ATL',6675300], [10,'COL',6393100],
    [11,'WSH',6133500], [12,'LAA',5889300], [13,'STL',5661300], [14,'MIA',5444900], [15,'ARI',5241000],
    [16,'TEX',5051900], [17,'HOU',4868600], [18,'CIN',4695500], [19,'CLE',4530500], [20,'BOS',4373900],
    [21,'SD',4224700], [22,'DET',4082700], [23,'CHC',3947600], [24,'SEA',3818700], [25,'MIL',3696000],
    [26,'ATL',3578800], [27,'NYM',3466500], [28,'HOU',3363600], [29,'SF',3270200], [30,'KC',3190500],
    [31,'ARI',3118300], [32,'STL',3044600], [33,'TB',2970200], [34,'PIT',2897400], [35,'NYY',2826700],
    [36,'PHI',2758800], [37,'COL',2696700], [38,'COL',2633100], [39,'TOR',2571700], [40,'LAD',2504200],
    [41,'CHW',2446100], [42,'WSH',2388800], [43,'MIN',2333200], [44,'PIT',2278700], [45,'LAA',2225800],
    [46,'BAL',2181600], [47,'ATH',2131300], [48,'ATL',2081900], [49,'TB',2033400], [50,'STL',1982700],
    [51,'PIT',1938100], [52,'MIA',1892500], [53,'ARI',1848200], [54,'TEX',1805300], [55,'SF',1763000],
    [56,'KC',1721700], [57,'HOU',1677400], [58,'CIN',1637700], [59,'CLE',1598900], [60,'SD',1561000],
    [61,'DET',1523600], [62,'CHC',1487200], [63,'NYY',1451700], [64,'PHI',1416600], [65,'SEA',1382600],
    [66,'MIL',1353100], [67,'BOS',1317300], [68,'STL',1285500], [69,'DET',1254200], [70,'CIN',1223100],
    [71,'MIA',1192600], [72,'STL',1174300], [73,'ATH',1156400], [74,'MIN',1138600], [75,'CHC',1120900],
    [76,'COL',1103500], [77,'CHW',1086600], [78,'WSH',1069600], [79,'MIN',1052700], [80,'PIT',1035700],
    [81,'LAA',1018500], [82,'BAL',1003800], [83,'ATH',988700], [84,'ATL',973700], [85,'TB',958500],
    [86,'STL',943600], [87,'MIA',929700], [88,'ARI',915100], [89,'TEX',900800], [90,'SF',887000],
    [91,'KC',872900], [92,'NYM',859900], [93,'HOU',846900], [94,'CIN',833800], [95,'CLE',823800],
    [96,'BOS',815700], [97,'SD',808100], [98,'CHC',800000], [99,'NYY',792300], [100,'PHI',784400],
    [101,'SEA',778200], [102,'MIL',770600], [103,'TOR',762900], [104,'COL',755300], [105,'CHW',747700],
    [106,'WSH',740500], [107,'MIN',733100], [108,'PIT',725900], [109,'LAA',718700], [110,'BAL',711800],
    [111,'ATH',704900], [112,'ATL',697700], [113,'TB',691000], [114,'STL',684300], [115,'MIA',677500],
    [116,'ARI',670900], [117,'TEX',664500], [118,'SF',658100], [119,'KC',651500], [120,'NYM',645100],
    [121,'HOU',638800], [122,'CIN',632500], [123,'CLE',626500], [124,'SD',620300], [125,'DET',614500],
    [126,'CHC',609200], [127,'NYY',603500], [128,'PHI',597400], [129,'SEA',591700], [130,'MIL',585700],
    [131,'TOR',581100], [132,'LAD',575300], [133,'HOU',569600], [134,'SD',563900], [135,'PHI',558400],
    [136,'COL',553100], [137,'CHW',547700], [138,'WSH',542200], [139,'MIN',536900], [140,'PIT',532000],
    [141,'LAA',526600], [142,'BAL',521500], [143,'ATH',516300], [144,'ATL',511400], [145,'TB',506100],
    [146,'STL',501300], [147,'MIA',496400], [148,'ARI',491700], [149,'TEX',486800], [150,'SF',481800],
    [151,'KC',476900], [152,'NYM',472500], [153,'HOU',467700], [154,'CIN',463200], [155,'CLE',458500],
    [156,'BOS',454100], [157,'SD',449500], [158,'DET',445200], [159,'CHC',441300], [160,'NYY',437200],
    [161,'PHI',433200], [162,'SEA',429100], [163,'MIL',425400], [164,'TOR',421300], [165,'COL',417400],
    [166,'CHW',413900], [167,'WSH',410300], [168,'MIN',406800], [169,'PIT',403500], [170,'LAA',399800],
    [171,'BAL',396300], [172,'ATH',393100], [173,'ATL',389900], [174,'TB',386500], [175,'STL',383400],
    [176,'MIA',380200], [177,'ARI',377000], [178,'TEX',373800], [179,'SF',370600], [180,'KC',367600],
    [181,'NYM',364600], [182,'HOU',361900], [183,'CIN',358900], [184,'CLE',355700], [185,'BOS',352900],
    [186,'SD',350100], [187,'DET',347300], [188,'CHC',344400], [189,'NYY',341800], [190,'PHI',338800],
    [191,'SEA',335900], [192,'MIL',333200], [193,'TOR',330300], [194,'COL',327700], [195,'CHW',325100],
    [196,'WSH',322300], [197,'MIN',319600], [198,'PIT',317100], [199,'LAA',314300], [200,'BAL',311700],
    [201,'ATH',310000], [202,'ATL',307300], [203,'TB',304800], [204,'STL',302300], [205,'MIA',299700],
    [206,'ARI',297100], [207,'TEX',294800], [208,'SF',292300], [209,'KC',289900], [210,'NYM',287800],
    [211,'HOU',285400], [212,'CIN',283000], [213,'CLE',280900], [214,'BOS',278700], [215,'SD',276400],
    [216,'DET',274300], [217,'CHC',272000], [218,'NYY',270000], [219,'PHI',267800], [220,'SEA',266100],
    [221,'MIL',264100], [222,'TOR',262300], [223,'LAD',260300], [224,'COL',258400], [225,'CHW',256500],
    [226,'WSH',254900], [227,'MIN',253300], [228,'PIT',251500], [229,'LAA',249300], [230,'BAL',247900],
    [231,'ATH',245800], [232,'ATL',244500], [233,'TB',242700], [234,'STL',241000], [235,'MIA',239200],
    [236,'ARI',237800], [237,'TEX',236100], [238,'SF',234700], [239,'KC',233400], [240,'NYM',232100],
    [241,'HOU',231000], [242,'CIN',229700], [243,'CLE',228600], [244,'BOS',227200], [245,'SD',226300],
    [246,'DET',225300], [247,'CHC',224100], [248,'NYY',223100], [249,'PHI',222200], [250,'SEA',220900],
    [251,'MIL',220400], [252,'TOR',219500], [253,'LAD',218500], [254,'COL',217800], [255,'CHW',217000],
    [256,'WSH',216100], [257,'MIN',215400], [258,'PIT',214800], [259,'LAA',213900], [260,'BAL',213300],
    [261,'ATH',212600], [262,'ATL',212000], [263,'TB',211200], [264,'STL',210600], [265,'MIA',210200],
    [266,'ARI',209500], [267,'TEX',209000], [268,'SF',208500], [269,'KC',207900], [270,'NYM',207200],
    [271,'HOU',206800], [272,'CIN',206300], [273,'CLE',205800], [274,'BOS',205400], [275,'SD',205000],
    [276,'DET',204400], [277,'CHC',204100], [278,'NYY',203500], [279,'PHI',202900], [280,'SEA',202700],
    [281,'MIL',202500], [282,'TOR',202100], [283,'LAD',201700], [284,'COL',201500], [285,'CHW',200900],
    [286,'WSH',200100], [287,'MIN',199900], [288,'PIT',199500], [289,'LAA',199200], [290,'BAL',198900],
    [291,'ATH',198600], [292,'ATL',198300], [293,'TB',197900], [294,'STL',197400], [295,'MIA',197200],
    [296,'ARI',196500], [297,'TEX',196200], [298,'SF',196000], [299,'KC',195600], [300,'NYM',195200],
    [301,'HOU',195000], [302,'CIN',194800], [303,'CLE',194500], [304,'BOS',194000], [305,'SD',193700],
    [306,'DET',193600], [307,'CHC',193300], [308,'NYY',193000], [309,'PHI',192500], [310,'SEA',192300],
    [311,'MIL',191900], [312,'TOR',191900], [313,'LAD',191900],
]

# Channels to search
CHANNELS = [
    ("2026-draft-general", "C09BB2NE1D4"),
    ("winter-meetings-2026", "C0A1XFUMQFM"),
    ("aiden-robbins", "C08DQTL4TGE"), ("cameron-flukey", "C08FL69S1S6"),
    ("kyle-jones", "C08CMC78D9Q"), ("myles-bailey", "C08CEPHABRC"),
    ("trevor-condon", "C08CJHA0C4D"), ("bo-lowrance", "C08CJHP13V3"),
    ("taj-marchand", "C08CZQFEGCR"), ("joe-tiroly", "C08LWQUEBQE"),
    ("alex-kranzler", "C08F4HDD9TR"), ("boston-torres", "C08M293RD19"),
    ("brady-neal", "C08FDPYARRP"),
    ("devin-diaz", "C08CMD0V802"),
    ("lucas-lawrence", "C08CMA913BL"),
    ("phinn-beaird", "C09344354UA"), ("mason-eckelman", "C09A0TL8KNY"),
    ("bryce-fowler", "C08C6RT634P"),
    ("ben-tryon", "C0A3EKND2P4"), ("duke-mccarron", "C0A605KCVJ7"),
    ("lee-ellis", "C0A844F4SUF"),
    ("ethan-lay", "C0AT6H9ME9G"),
    ("2026-mlb-combine", "C0BDQBG9G2X"),
    ("2026-private-draft-notes", "C0BEAC9UAKB"),
]

# Channels whose every record is, by definition, a combine meeting (the channel
# itself scopes the context). Treated as unfiltered in fetch (posts here won't
# contain the "teamintel" keyword) and every (player, team) record drawn from
# them is flagged combine=True → blue dot in the matrix. Names are lowercase to
# match Slack's normalization.
_COMBINE_CHANNELS = {'2026-mlb-combine'}

# Channels where the actual intel date is written in the message header as
# "(M/D/YY)" rather than implied by the Slack post time. Notes here are often
# back-filled days after the contact happened (e.g. an intel from 6/11 posted
# on 6/30), so the post timestamp would mis-date the record. For these channels
# the header date is used as the record date; we fall back to post time when no
# header date is present.
_HEADER_DATED_CHANNELS = {'2026-private-draft-notes'}

_HEADER_DATE_RE = re.compile(r'\((\d{1,2})/(\d{1,2})/(\d{2,4})\)')


def _header_intel_date(text):
    """Extract a '(M/D/YY)' intel date from the first line of a message.

    Returns 'YYYY-MM-DD', or None if the header has no parenthesized date or
    the date is invalid. Two-digit years are interpreted as 20YY.
    """
    if not text:
        return None
    first_line = text.split('\n', 1)[0]
    m = _HEADER_DATE_RE.search(first_line)
    if not m:
        return None
    mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yr < 100:
        yr += 2000
    try:
        return datetime(yr, mo, day).strftime('%Y-%m-%d')
    except ValueError:
        return None


# --- STEP 1: FETCH FROM SLACK ---
def fetch_messages(token):
    client = WebClient(token=token)
    all_messages = []
    # Per-channel fetch failures, as (channel_name, slack_error_code). main()
    # inspects these to abort a degraded build instead of committing empty data.
    channel_errors = []

    # Workspace base URL (e.g. https://stadium-ventures.slack.com/) for building
    # message permalinks. Falls back to None if auth_test fails — UI hides the
    # "View in Slack" link in that case.
    workspace_url = None
    try:
        info = client.auth_test()
        u = (info.get('url') or '').rstrip('/')
        if u:
            workspace_url = u
    except Exception as e:
        print(f"WARN: auth_test failed, Slack permalinks will be unavailable: {e}")

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
                # Pull Slack's structured error code (missing_scope, not_in_channel,
                # invalid_auth, …) so main() can tell a fatal auth/scope loss apart
                # from an isolated channel hiccup.
                code = None
                resp_obj = getattr(e, 'response', None)
                if resp_obj is not None:
                    try:
                        code = resp_obj.get('error')
                    except Exception:
                        code = None
                code = code or str(e)
                print(f"  Error #{name}: {code}")
                channel_errors.append((name, code))
                break

            for msg in resp['messages']:
                text = msg.get('text', '')
                tl = text.lower()
                # Include ALL messages from 2026-draft-general (keyword often omitted)
                # For other channels, require "teamintel" / "team intel" keyword
                is_teamintel = (
                    name == '2026-draft-general'
                    or name in _COMBINE_CHANNELS
                    or 'teamintel' in tl
                    or 'team intel' in tl
                )
                if is_teamintel:
                    rec_date = datetime.fromtimestamp(float(msg['ts'])).strftime('%Y-%m-%d')
                    if name in _HEADER_DATED_CHANNELS:
                        rec_date = _header_intel_date(text) or rec_date
                    all_messages.append({
                        'channel': name, 'channel_id': cid,
                        'ts': msg['ts'],
                        'date': rec_date,
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
                            rep_date = datetime.fromtimestamp(float(reply['ts'])).strftime('%Y-%m-%d')
                            if name in _HEADER_DATED_CHANNELS:
                                rep_date = _header_intel_date(combined) or rep_date
                            all_messages.append({
                                'channel': name, 'channel_id': cid,
                                'ts': reply['ts'],
                                'date': rep_date,
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

    print(f"Fetched {len(unique)} TeamIntel messages from {len(CHANNELS)} channels"
          f"{f' ({len(channel_errors)} channel error(s))' if channel_errors else ''}")
    return unique, workspace_url, channel_errors


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
            # Skip 2-letter abbrevs that look like state codes (",<space>XX" pattern):
            # 'Florida Southern, FL', 'Phoenix, AZ', 'Tampa, FL' should not register as a team.
            if len(key) == 2 and re.search(r',\s*' + re.escape(key) + r'\b', lu):
                continue
            found.add(TEAM_ABBR[key])
    if lu in TEAM_ABBR:
        found.add(TEAM_ABBR[lu])
    return found

def find_players_in_text(text):
    found = set()
    tl = text.lower()
    for last, full in PLAYERS_2026.items():
        # 'lay' is a substring of common words (player, playoff, display, relay,
        # delay). Skip the naive substring match and detect Ethan Lay by his
        # distinctive first name below instead.
        if last == 'lay':
            continue
        if last in tl:
            found.add(full)
    if re.search(r'\bcam\b', tl) and 'Cameron Flukey' not in found:
        found.add('Cameron Flukey')
    if re.search(r'\b(?:trev|trevor)\b', tl) and 'Trevor Condon' not in found:
        found.add('Trevor Condon')
    if re.search(r'\bbo\b', tl) and 'Bo Lowrance' not in found:
        found.add('Bo Lowrance')
    if re.search(r'\btaj\b', tl) and 'Taj Marchand' not in found:
        found.add('Taj Marchand')
    if re.search(r'\bphinn\b', tl) and 'Phinn Beaird' not in found:
        found.add('Phinn Beaird')
    if re.search(r'\bmyles\b', tl) and 'Myles Bailey' not in found:
        found.add('Myles Bailey')
    if re.search(r'\bkyle\b', tl) and 'Kyle Jones' not in found:
        found.add('Kyle Jones')
    if re.search(r'\baiden\b', tl) and 'Aiden Robbins' not in found:
        found.add('Aiden Robbins')
    if re.search(r'\bmason\b', tl) and 'Mason Eckelman' not in found:
        found.add('Mason Eckelman')
    if re.search(r'\bduke\b', tl) and 'Duke McCarron' not in found:
        found.add('Duke McCarron')
    if re.search(r'\bbrady\b', tl) and 'Brady Neal' not in found:
        found.add('Brady Neal')
    if re.search(r'\blee\b', tl) and 'Lee Ellis' not in found:
        found.add('Lee Ellis')
    if re.search(r'\bethan\b', tl) and 'Ethan Lay' not in found:
        found.add('Ethan Lay')
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
    # "workout in Orlando (TNXL), want Condon and Woodward there" — invite phrasing
    # where the players come AFTER the workout reference. Matches either order
    # so "want Condon there for the workout" also fires.
    r'\bworkout[\s\S]{0,80}?\bwant\w*\s+\w+(?:\s+(?:and|,)\s+\w+)?\s+there\b',
    r'\bwant\w*\s+\w+(?:\s+(?:and|,)\s+\w+)?\s+there\b[\s\S]{0,80}?\bworkout',
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

# --- Combine-meeting detection ---
# The MLB Combine (Phoenix, 6/21–6/26) — TeamIntel messages note when a player
# sat down with a club there. Auto-detected from Slack: a "combine" + meeting/
# interview phrase, attributed to whichever team is named in a short window
# around it. Drives the matrix's blue dot. Noisier than the workout flag by
# design — there's no manual override layer for it.
_COMBINE_MEETING_PATTERNS = [
    r'\bcombine\b[\s\S]{0,50}?\b(?:meeting|met|meet|interview|interviewed|sit[- ]?down|sat\s+down|spoke|talked|conversation|chat)\b',
    r'\b(?:meeting|met|meet|interview|interviewed|sit[- ]?down|sat\s+down|spoke|talked|conversation|chat)\b[\s\S]{0,50}?\bcombine\b',
]

def combine_meeting_teams(text):
    """Return the set of team abbrevs this message ties to a combine meeting.
    A combine-meeting phrase must appear AND a team must be named within ~60
    chars of it, so a multi-team post only flags the team actually mentioned."""
    tl = text.lower()
    teams = set()
    for s, e in _spans_for(tl, _COMBINE_MEETING_PATTERNS):
        window = text[max(0, s - 60):min(len(text), e + 60)]
        teams |= find_teams_in_line(window)
    return teams

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
    r'(?:\bin|\bat|@)\s+([A-Z][\w\.\- ]+?)(?=[\.,;:\n]|\s*[\(\)\[\]]|\s+or\s+|\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b|\s+\d|\Z)',
    re.I,
)
# Words that disqualify a line from being a "standalone location" (notes/intent words
# that sometimes appear in PDW invite blocks).
_WD_LOC_BAD_SUBSTR = (
    'workout', 'invite', 'tentative', 'maybe', 'likely', 'possible', 'pending',
    'cancelled', 'canceled', 'confirmed', 'declined', 'declining', 'pre-draft',
    'predraft', 'pdw', 'team intel', 'in the mix', 'follow up', 'follow-up',
    'will be', "won't", 'not going', 'just signed', 'note:', 'update:',
)


def _wd_is_standalone_location(line):
    """Heuristic: does this line look like a place name on its own, with no date/team-header/notes?
    City names like 'Atlanta'/'Lakeland' that collide with TEAM_ABBR full-name keys are allowed
    here — caller must skip team-header lines so 'BAL' alone isn't picked up as a location."""
    s = line.strip().rstrip('.,')
    if not s or len(s) > 50:
        return False
    if re.search(r'\d', s):
        return False
    if re.search(_WD_MONTH_RE, s, re.I):
        return False
    if s.upper() in TEAM_ABBR and len(s) <= 4:
        return False
    if find_players_in_text(s):
        return False
    sl = s.lower()
    if any(b in sl for b in _WD_LOC_BAD_SUBSTR):
        return False
    words = s.split()
    if not words or len(words) > 4:
        return False
    if not words[0][0].isupper():
        return False
    lowercase_ok = {'of', 'the', 'and', 'at', 'in', 'on', 'a', 'an'}
    upper_count = 0
    for w in words:
        clean = re.sub(r'[^A-Za-z]', '', w)
        if not clean:
            continue
        if clean[0].isupper():
            upper_count += 1
        elif clean.lower() in lowercase_ok:
            continue
        else:
            return False
    return upper_count >= 1


# 'June 11 - Atlanta', 'May 29 - Lakeland', 'June 3-Metro Atl. (Either Pace HS …)'
# — captures the tail location after a date+separator. Allows zero-or-more
# whitespace around the separator (so "June 3-Metro" works) and stops at a
# trailing parenthetical so the location doesn't absorb "(Either Pace HS …)".
_WD_DATE_TAIL_LOC_RE = re.compile(
    r'\b\d{1,2}(?:st|nd|rd|th)?\s*[-–—:]\s*([A-Z][A-Za-z\.\-\' ,]+?)\s*(?:\(|$)'
)
# 'May 18th Columbia, SC 9am' — date followed by whitespace, then a Capitalized place,
# bounded by a trailing time/number or end-of-line. No separator required.
_WD_DATE_LOC_NOSEP_RE = re.compile(
    r'\b\d{1,2}(?:st|nd|rd|th)?\s+([A-Z][A-Za-z\.\-\' ,]+?)(?=\s+\d|\s*$)'
)
# Explicit 'Location:' label lines: 'Location: Pirate City complex in Bradenton, FL'.
_WD_LOC_PREFIX_RE = re.compile(r'^\s*(?:Location|Loc)\s*[:\-]\s*(.+?)\s*$', re.I)
# Reversed form: 'Florida Southern, FL - June 2' / 'Charlotte, NC - June 3'.
_WD_LOC_DATE_RE = re.compile(
    r'^\s*([A-Z][A-Za-z\.\-\' ,]+?)\s*[-–—:]\s+(?:' + _WD_MONTH_RE + r'\s+\d|\d{1,2}/\d{1,2})',
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


# Trailing capitalized word/phrase, optionally led by comma/semicolon, anchored
# at the end of the chunk. Used to pull the location prefix out of a per-date
# segment like " CIN " or ", Daytona ".
_WD_CHUNK_LOC_RE = re.compile(
    r'(?:^|[,;])\s*([A-Z][A-Za-z\.\-]*(?:\s+[A-Z][A-Za-z\.\-]+){0,2})\s*$'
)
# Conversational openers that often precede a comma-separated workout list.
_WD_CHUNK_LEAD_STRIP_RE = re.compile(
    r'^\s*(?:workouts?|pdw|pre-?\s*draft\s+workouts?)\s*:\s*', re.I,
)


def _wd_chunk_leading_location(chunk_pre):
    """Given the text immediately preceding a date in a multi-date line, return
    the most likely location label (team abbrev or short title-cased place
    name), or None when nothing usable is found.
    """
    if not chunk_pre or not chunk_pre.strip():
        return None
    cp = _WD_CHUNK_LEAD_STRIP_RE.sub('', chunk_pre)
    m = _WD_CHUNK_LOC_RE.search(cp)
    if not m:
        return None
    cand = m.group(1).strip().rstrip('.,')
    if not cand:
        return None
    if re.match(_WD_MONTH_RE + r'\b', cand, re.I):
        return None
    cl = cand.lower()
    if any(b in cl for b in _WD_LOC_BAD_SUBSTR):
        return None
    # Recognized team abbrev → uppercased so display is consistent.
    if cand.upper() in TEAM_ABBR and len(cand) <= 4:
        return cand.upper()
    return cand


def _wd_extract_dates_pos(line):
    """Like _wd_extract_dates but returns (date_str, start, end) per match,
    sorted by position. Used to chunk multi-date lines so each date can carry
    its own location.
    """
    found = []
    for m in re.finditer(
        _WD_MONTH_RE + r'\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?',
        line, re.I,
    ):
        month = _WD_MONTH_NUM.get(m.group(1).upper()[:3])
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else 2026
        d = _wd_safe(year, month, day)
        if d and _WD_MIN <= d <= _WD_MAX:
            found.append((d.strftime('%Y-%m-%d'), m.start(), m.end()))
    for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b', line):
        month = int(m.group(1))
        day = int(m.group(2))
        year = m.group(3)
        if year:
            year = int(year)
            if year < 100:
                year += 2000
        else:
            year = 2026
        d = _wd_safe(year, month, day)
        if d and _WD_MIN <= d <= _WD_MAX:
            found.append((d.strftime('%Y-%m-%d'), m.start(), m.end()))
    found.sort(key=lambda x: x[1])
    return found


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
    current_location = None
    raw_lines = full_text.split('\n')
    for idx, raw_line in enumerate(raw_lines):
        line = raw_line.strip()
        if not line: continue
        is_date_list = bool(_WD_DATE_LIST_LINE_RE.match(line))
        # "Atlanta, GA - June 1 (Kennesaw)" is a date entry, not a team header —
        # without this, the leading city overwrites current_team (ATL absorbs
        # dates belonging to the team from a prior "Workout invite - SDP" line).
        if not is_date_list:
            _ld = _WD_LOC_DATE_RE.match(line)
            if _ld:
                _cand = _ld.group(1).strip().rstrip('.,')
                if _cand and re.search(r',\s*[A-Z]{2}\b', _cand) and _wd_is_standalone_location(_cand):
                    is_date_list = True
        teams_in_line = find_teams_in_line(line)
        if teams_in_line and not is_date_list:
            new_team = _wd_first_team(line) or sorted(teams_in_line)[0]
            if new_team != current_team:
                current_team = new_team
                current_location = None
            hdr_loc = _WD_LOC_RE.search(line)
            if hdr_loc:
                current_location = hdr_loc.group(1).strip()
        dates = _wd_extract_dates(line)
        if not dates:
            # Standalone location line (e.g., "Bradenton") under the current team —
            # remember so subsequent dated bullets in the same block inherit it.
            if not teams_in_line and current_team and not current_location and _wd_is_standalone_location(line):
                current_location = line.strip().rstrip('.,')
            continue
        tentative = bool(_WD_TENTATIVE_RE.search(line))
        tm = _WD_TIME_RE.search(line)
        time_str = tm.group(1).strip() if tm else None
        lm = _WD_LOC_RE.search(line)
        location = lm.group(1).strip() if lm else None
        # Same-line "<date> - <Location>" pattern. Strips trailing comma but
        # keeps a trailing period so abbreviations like "Metro Atl." render
        # the way they were written.
        if not location:
            tail = _WD_DATE_TAIL_LOC_RE.search(line)
            if tail:
                cand = tail.group(1).strip().rstrip(',')
                if cand and _wd_is_standalone_location(cand):
                    location = cand
        # Same-line "<date> <Location> <time>" with no separator — "May 18th Columbia, SC 9am".
        if not location:
            tail2 = _WD_DATE_LOC_NOSEP_RE.search(line)
            if tail2:
                cand = tail2.group(1).strip().rstrip('.,')
                if cand and _wd_is_standalone_location(cand):
                    location = cand
        # Reversed form: "Florida Southern, FL - June 2" — location FIRST, then date.
        if not location:
            ld = _WD_LOC_DATE_RE.match(line)
            if ld:
                cand = ld.group(1).strip().rstrip('.,')
                if cand and _wd_is_standalone_location(cand):
                    location = cand
        # Carry-forward from team header / earlier standalone line.
        if not location:
            location = current_location
        # Look-ahead inside the same paragraph block — break on dates/blanks only,
        # not on team-name strings (city names like 'Atlanta' register as teams via TEAM_ABBR).
        if not location:
            for j in range(idx + 1, min(idx + 5, len(raw_lines))):
                nxt = raw_lines[j].strip()
                if not nxt:
                    break
                if _wd_extract_dates(nxt):
                    break
                # Explicit "Location: ..." label wins.
                pref = _WD_LOC_PREFIX_RE.match(nxt)
                if pref:
                    cand = pref.group(1).strip().rstrip('.,')
                    if cand:
                        location = cand[:80]
                        current_location = location
                        break
                # Standalone short place name ("Bradenton").
                if _wd_is_standalone_location(nxt):
                    location = nxt.rstrip('.,')
                    current_location = location
                    break
                # In/at/@ phrase embedded in a longer line.
                lm2 = _WD_LOC_RE.search(nxt)
                if lm2:
                    cand = lm2.group(1).strip().rstrip('.,')
                    if cand:
                        location = cand
                        current_location = location
                        break
        # Per-date location for multi-date lines like
        #   "Workouts: CIN June 4, ATL June 10, Daytona June 11"
        # Each date carries the location/team prefix that immediately precedes
        # it. Falls back to the line-wide `location` when no chunk prefix
        # parses out (e.g. "April 15, 16, 17" — same workout, no per-date loc).
        # Also scans the chunk AFTER each date for an "in/at/@ X" phrase
        # ("June 8 in Fayetteville NC") — that wins over the leading prefix
        # because it's more explicit about which date a location belongs to.
        per_date_loc = {}
        date_positions = _wd_extract_dates_pos(line)
        if len(date_positions) >= 2:
            for i, (d_str, d_start, d_end) in enumerate(date_positions):
                prev_end = date_positions[i-1][2] if i > 0 else 0
                next_start = date_positions[i+1][1] if i+1 < len(date_positions) else len(line)
                loc = _wd_chunk_leading_location(line[prev_end:d_start])
                m_post = _WD_LOC_RE.search(line[d_end:next_start])
                if m_post:
                    cand = m_post.group(1).strip().rstrip('.,')
                    if cand:
                        loc = cand
                if loc:
                    per_date_loc[d_str] = loc
        targets = sorted(teams_in_line) if (teams_in_line and not is_date_list) else [current_team]
        for team in targets:
            for d in dates:
                eff_loc = per_date_loc.get(d) or location
                ev = merged[team].get(d)
                if ev is None:
                    merged[team][d] = {'date': d, 'tentative': tentative, 'time': time_str, 'location': eff_loc}
                else:
                    if tentative: ev['tentative'] = True
                    if time_str and not ev['time']: ev['time'] = time_str
                    if eff_loc and (not ev['location'] or len(eff_loc) > len(ev['location'])):
                        ev['location'] = eff_loc
    # Orphan-date reassignment: dates parsed before any team header land under
    # `None`. When the whole message references exactly one team, attribute
    # them to it. Handles the "date first, team below" Slack shape, e.g.
    # "June 12 workout invite\n\nChuck Ricci - Rays". Multi-team messages keep
    # their line-by-line resolution untouched.
    if None in merged and merged[None]:
        teams_in_text = find_teams_in_line(full_text)
        if len(teams_in_text) == 1:
            sole_team = next(iter(teams_in_text))
            tgt = merged[sole_team]
            for d_str, ev in merged[None].items():
                existing = tgt.get(d_str)
                if existing is None:
                    tgt[d_str] = ev
                else:
                    if ev.get('tentative'): existing['tentative'] = True
                    if ev.get('time') and not existing.get('time'): existing['time'] = ev['time']
                    if ev.get('location') and (not existing.get('location') or len(ev['location']) > len(existing['location'])):
                        existing['location'] = ev['location']
        del merged[None]
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

    def _attach_tier(rec, line_text, header_text=None):
        """Write attendee_tier / tier_multiplier / tier_label / raw_score / color
        onto a record in place, and bump rec['score'] to the tier floor when a
        senior attendee was detected.

        `header_text` is the message header line (e.g.
        "Team Intel - BOS - Jake Bruml"). The intel source named there weights
        the whole report: if that contact is a known front-office higher-up,
        their tier becomes the floor for every record in the message, even on
        body lines that don't re-name them. More senior (lower tier #) wins.
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
        if header_text:
            ht, hmult, hlabel = detect_attendee_tier(header_text, rec.get('team'), _front_office)
            if ht and (t == 0 or ht < t):
                t, mult, label = ht, hmult, hlabel
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
        # First line is the report header ("Team Intel - BOS - Jake Bruml ...").
        # Passed into _attach_tier so a front-office source named there sets the
        # tier floor for the whole report.
        msg_header = text.split('\n', 1)[0] if text else ''
        # Slack source fields — propagated onto every record produced from this
        # message so the popup can render a clickable permalink. parent_ts is
        # only set for thread replies (used in ?thread_ts= query).
        ts = msg.get('ts')
        channel_id = msg.get('channel_id')
        parent_ts = msg.get('parent_ts')

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
                        'ts': ts, 'channel_id': channel_id, 'parent_ts': parent_ts,
                    })
                    _attach_tier(records[-1], ls, msg_header)

        elif channel in CHANNEL_TO_PLAYER:
            player = CHANNEL_TO_PLAYER[channel]
            # Prefer an explicit "Team Intel - <ABBR>" header. Without it, city/team-name
            # words anywhere in the body (Atlanta, Detroit, Lakeland, ...) would create
            # phantom records via TEAM_ABBR's full-name keys.
            header_match = re.search(r'[Tt]eam\s*[Ii]ntel\s*[-:]?\s*\n?\s*(\w+)', text)
            header_team = None
            if header_match:
                header_team = normalize_team(header_match.group(1))
            if header_team:
                all_teams = {header_team}
            else:
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
                    'ts': ts, 'channel_id': channel_id, 'parent_ts': parent_ts,
                })
                _attach_tier(records[-1], best_tier_line or text, msg_header)

        elif channel in _COMBINE_CHANNELS:
            # Combine reports are per-player: a header line ("Robbins - Team Intel")
            # followed by one "<TEAM> - <note>" line per club the player met with.
            # The player comes from the header (first line that names one); each
            # team line becomes a (player, team) record. Differs from the generic
            # `else` path, which would misread the first team line as a header team
            # and emit only a single record per message.
            lines = text.split('\n')
            player = None
            for line in lines:
                pl = find_players_in_text(line)
                if pl:
                    player = sorted(pl)[0]
                    break
            if not player:
                continue
            for line in lines:
                ls = line.strip()
                if not ls or re.match(r'^[Tt]eam\s*[Ii]ntel', ls):
                    continue
                line_teams = find_teams_in_line(ls)
                if not line_teams:
                    continue
                score = score_line_for_team(ls, text)
                for t in line_teams:
                    records.append({
                        'player': player, 'team': t, 'date': date,
                        'score': score, 'note': ls[:200],
                        'channel': channel, 'full_text': text[:3000],
                        'ts': ts, 'channel_id': channel_id, 'parent_ts': parent_ts,
                    })
                    _attach_tier(records[-1], ls, msg_header)

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
                                'ts': ts, 'channel_id': channel_id, 'parent_ts': parent_ts,
                            })
                            _attach_tier(records[-1], ls, msg_header)
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
                                    'ts': ts, 'channel_id': channel_id, 'parent_ts': parent_ts,
                                })
                                _attach_tier(records[-1], ls, msg_header)
                    elif lp and not lt and all_teams:
                        score = score_line_for_team(ls, text)
                        for p in lp:
                            for t in all_teams:
                                records.append({
                                    'player': p, 'team': t, 'date': date,
                                    'score': score, 'note': text.strip()[:200],
                                    'channel': channel, 'full_text': text[:3000],
                                    'ts': ts, 'channel_id': channel_id, 'parent_ts': parent_ts,
                                })
                                _attach_tier(records[-1], ls, msg_header)

    # Add workout flag + match details based on note/full_text
    # Also attach parsed workout_dates (pre-draft window, May–Jul 2026),
    # filtered to the record's team so cross-team mentions don't bleed in.
    _wd_cache = {}
    for r in records:
        text = r.get('full_text', '') + '\n' + r.get('note', '')
        matches = workout_match_details(text, r.get('player'), r.get('channel'))
        r['workout'] = len(matches) > 0
        r['workout_matches'] = [m['text'] for m in matches]
        # Combine dots come ONLY from the dedicated #2026-mlb-combine channel.
        # Keyword/team-proximity detection in other channels produced false
        # positives, so it is intentionally not used here.
        r['combine'] = r.get('channel') in _COMBINE_CHANNELS

        if r['workout']:
            ft = r.get('full_text', '')
            if ft not in _wd_cache:
                _wd_cache[ft] = extract_workout_dates(ft)
            r['workout_dates'] = _wd_cache[ft].get(r['team'], [])
        else:
            r['workout_dates'] = []

    # Deduplicate — but MERGE workout_dates across same-key records so a later
    # message can't silently lose its workout dates to an earlier short one.
    # `records` is already in chronological order (parse_messages iterates
    # messages sorted by ts), so when we encounter a duplicate the current
    # record is the more recent one. The merge keeps the later record's text
    # and permalink (most recent source of truth) and unions workout_dates by
    # date with the later entry winning. The workout flag is OR-ed.
    seen = {}
    order = []
    for r in records:
        key = (r['player'], r['team'], r['date'], r['score'])
        if key not in seen:
            seen[key] = r
            order.append(key)
            continue
        existing = seen[key]
        by_date = {}
        for wd in (existing.get('workout_dates') or []):
            if wd.get('date'):
                by_date[wd['date']] = wd
        for wd in (r.get('workout_dates') or []):
            if wd.get('date'):
                by_date[wd['date']] = wd  # later wins for conflicting date
        merged = dict(r)
        merged['workout'] = bool(r.get('workout') or existing.get('workout'))
        merged['combine'] = bool(r.get('combine') or existing.get('combine'))
        if by_date:
            merged['workout_dates'] = sorted(by_date.values(), key=lambda x: x.get('date', ''))
        seen[key] = merged
    unique = [seen[k] for k in order]

    print(f"Parsed {len(unique)} unique intel records")
    return unique


# --- STEP 3: BUILD HTML ---
def load_team_draft_info():
    """Read 2026 bonus pool + first picks + farm system ranking per team.
    Returns { abbrev: { 'pool': str, 'picks': [int], 'farm_rank': int|None } }.
    Empty dict if the main draft CSV is missing.

    Sources:
      - data/team_draft_2026.csv (pool + picks). Originates from the "Review"
        sheet rows 3 ("Pool Amount") + 4 ("Pick #") in sv-org-review.
      - data/farm_system_2026.csv (farm_rank). Canonical source is the
        "ORG Rankings" tab of `Org.Review.2026.update_5-3-26.xlsx` in
        sv-org-review (column "COMP" = composite 1-30 overall rank).
        Refresh by re-extracting that column when the xlsx updates.
    Both files are hand-refreshed when org-review updates — keep them in sync
    when the org review is re-run.
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
                'farm_rank': None,
            }
    # Merge farm system rankings (optional — silently skip if file is missing).
    farm_path = os.path.join(os.path.dirname(__file__), 'data', 'farm_system_2026.csv')
    if os.path.exists(farm_path):
        with open(farm_path) as f:
            for row in csv.DictReader(f):
                abbr = (row.get('abbrev') or '').strip().upper()
                rank = (row.get('farm_rank') or '').strip()
                if abbr in out and rank.isdigit():
                    out[abbr]['farm_rank'] = int(rank)
    return out


def load_recommended_schedule():
    """Read per-player tentative recommended workout schedule.
    Returns { player_name: { 'tiers': [{ 'label': str, 'entries': [{team,schedule}] }] } }.
    Empty dict if the file is missing. This is the SV recommendation that appears
    on the right side of each player block in the PDF — distinct from the
    auto-generated PDW Invites table on the left (which comes from Slack).
    Hand-edited at data/recommended_schedule_2026.json until we build a UI.
    """
    path = os.path.join(os.path.dirname(__file__), 'data', 'recommended_schedule_2026.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'WARN: recommended_schedule_2026.json parse error: {e}')
        return {}
    # Drop the README key so it doesn't get treated as a player.
    return {k: v for k, v in data.items() if not k.startswith('_')}


def build_html(records, password="SVintel2026", games=None, slack_workspace_url=None):
    records_js = json.dumps(records)
    games_js = json.dumps(games or [])
    eastern = timezone(timedelta(hours=-4))
    now_str = datetime.now(eastern).strftime('%B %d, %Y %I:%M %p') + ' ET'
    all_2026_js = json.dumps(ALL_2026_PLAYERS)
    # Serialize alias map (sets aren't JSON-safe — convert to lists)
    player_aliases_js = json.dumps({name: sorted(aliases) for name, aliases in PLAYER_ALIASES.items()})
    team_draft_js = json.dumps(load_team_draft_info())
    draft_picks_js = json.dumps(DRAFT_PICKS_2026)
    recommended_schedule_js = json.dumps(load_recommended_schedule())
    slack_workspace_js = json.dumps(slack_workspace_url or '')

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

/* --- DASHBOARD ---
   Density pass (2026-04-25): the dashboard targets information-dense scanning
   for a small group of users. Defaults trimmed to a compact desktop layout;
   mobile breakpoint stacks sensibly below 768px. */
.header {{
    background: #000000;
    color: white; padding: 10px 22px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3); position: relative; z-index: 100;
    border-bottom: 2px solid #ff2a22;
}}
.header-left {{ display: flex; align-items: center; gap: 14px; }}
.header h1 {{ font-size: 17px; font-weight: 700; letter-spacing: 0.4px; }}
.header .subtitle {{ font-size: 11px; opacity: 0.8; font-weight: 400; }}
.logo-icon {{
    height: 30px; width: auto; display: flex; align-items: center; justify-content: center;
}}
.logo-icon img {{ height: 30px; width: auto; display: block; }}
.nav-tabs {{ display: flex; gap: 4px; }}
.nav-tab {{
    padding: 5px 14px; border-radius: 5px; cursor: pointer;
    font-size: 12px; font-weight: 600; transition: all 0.2s;
    border: 1px solid rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.8);
}}
.nav-tab:hover {{ background: rgba(255,255,255,0.15); color: white; }}
.nav-tab.active {{ background: rgba(255,255,255,0.25); color: white; border-color: rgba(255,255,255,0.4); }}

.stats-bar {{
    background: white; padding: 6px 22px; display: flex; gap: 22px;
    border-bottom: 1px solid #e8e8e8; font-size: 11px; align-items: center;
}}
.stat-item {{ display: flex; gap: 5px; align-items: center; }}
.stat-label {{ color: #888; font-weight: 500; }}
.stat-value {{ font-weight: 700; color: #000000; }}

.legend {{
    display: flex; gap: 14px; padding: 5px 22px; font-size: 11px;
    align-items: center; background: white; border-bottom: 1px solid #e8e8e8;
}}
.legend-title {{ font-weight: 600; color: #666; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.date-window {{ display: flex; align-items: center; gap: 4px; margin-left: auto; }}
.dw-btn {{
    font-size: 11px; font-weight: 600; padding: 3px 9px; cursor: pointer;
    border: 1px solid #d0d0d0; background: #fff; color: #555; border-radius: 5px;
    transition: all 0.12s;
}}
.dw-btn:hover {{ background: #f2f2f2; }}
.dw-btn.active {{ background: #000; color: #fff; border-color: #000; }}
.legend-swatch {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1); }}

.matrix-container {{ padding: 10px 14px; }}
.matrix-scroll {{
    /* Fill the page below the sticky header + slim legend + statsBar so the
       matrix doesn't feel cut off. Compact desktop chrome: ~46px header +
       ~24px legend + ~28px stats + ~30px paddings ≈ 130px. */
    max-height: calc(100vh - 145px); overflow: auto;
    -webkit-overflow-scrolling: touch; overscroll-behavior: contain;
    border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); background: white;
}}
.matrix-table {{
    border-collapse: separate; border-spacing: 0; font-size: 11px;
    width: auto; min-width: 100%; background: white;
}}
.matrix-table th, .matrix-table td {{
    padding: 4px 5px; text-align: center;
    border-right: 1px solid #ececec; border-bottom: 1px solid #ececec;
    white-space: nowrap; height: 26px; background: white;
}}
.matrix-table thead th {{
    background: #000000; color: white; font-weight: 600; font-size: 10px;
    letter-spacing: 0.3px; border-right: 1px solid #2a2a2a; border-bottom: 1px solid #2a2a2a;
    position: sticky; top: 0; z-index: 3;
}}
.matrix-table thead tr:first-child th {{ height: 22px; }}
/* Sub-header row: 2026 bonus pool + first 5 picks per team. Top-aligned so the
   pool $ stays in the same place across all columns regardless of how many
   picks land in the cell below. */
.matrix-table thead th.team-info {{
    background: #1a1a1a; color: #d8d8d8; font-weight: 500;
    padding: 4px 5px 5px; white-space: normal; vertical-align: top;
    border-bottom: 2px solid #000000; min-width: 60px;
    position: sticky; top: 22px; z-index: 3;
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
    min-width: 132px; max-width: 132px;
}}
.matrix-table tbody td:nth-child(1) {{
    background: white; text-align: left; padding-left: 9px; font-size: 11px; font-weight: 600;
    color: #000000;
    box-shadow: 2px 0 3px -1px rgba(0,0,0,0.08);
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
td.score-cell .cell-dot {{ position: absolute; width: 7px; height: 7px; border-radius: 50%; pointer-events: none; z-index: 1; }}
td.score-cell .dot-pdw {{ top: 2px; left: 2px; background: #000; }}        /* pre-draft workout */
td.score-cell .dot-combine {{ top: 2px; right: 2px; background: #1565c0; box-shadow: 0 0 0 1px rgba(255,255,255,0.6); }}  /* combine meeting */
.workout-badge {{ display: inline-block; background: #d4a017; color: white; font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px; margin-left: 6px; vertical-align: middle; letter-spacing: 0.3px; }}
td.overridden {{ position: relative; }}
td.overridden::after {{ content: '*'; position: absolute; top: 1px; right: 3px; font-size: 9px; color: rgba(0,0,0,0.4); }}

#scorePopup {{
    display: none; position: fixed; z-index: 9000;
    background: white; border-radius: 10px; padding: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25); min-width: 220px;
    max-height: calc(100vh - 16px); overflow-y: auto;
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
#scorePopup .popup-color {{
    display: flex; align-items: center; gap: 7px;
    padding: 5px 9px; margin: 0 0 8px; font-size: 11px;
    border-radius: 5px; border: 1px solid rgba(0,0,0,0.08);
}}
#scorePopup .popup-color .pc-swatch {{
    width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.15);
}}
#scorePopup .popup-color .pc-label {{ color: #444; font-weight: 600; }}
#scorePopup .popup-color .pc-value {{ color: #1a1a1a; font-weight: 700; text-transform: capitalize; }}
/* Source attribution: where the most-recent color came from. Sits in its own
   row below the color line so a wide chip can't push the popup off-screen. */
#scorePopup .popup-source {{
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    margin: -4px 0 10px;
}}
#scorePopup .popup-source-note {{
    font-size: 11px; color: #666; font-style: italic; font-weight: 500;
    white-space: normal; flex-basis: 100%;
}}
#scorePopup .popup-source-label {{
    font-size: 10px; color: #888; font-weight: 600; letter-spacing: 0.3px;
    text-transform: uppercase;
}}
#scorePopup .popup-source-chip {{
    font-size: 11px; font-weight: 600; padding: 3px 8px;
    border-radius: 4px; background: #f0f0f0; color: #444;
    border: 1px solid #e0e0e0; white-space: nowrap;
}}
#scorePopup button.popup-source-chip {{
    background: #2a2a2a; color: #fff; border-color: #2a2a2a;
    cursor: pointer; transition: background 0.15s;
}}
#scorePopup button.popup-source-chip:hover {{ background: #000; }}
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
#scorePopup .popup-combine {{
    display: flex; align-items: center; justify-content: center; gap: 6px;
    margin-bottom: 8px; padding: 6px 0; border: 2px solid #1565c0; border-radius: 6px;
    cursor: pointer; font-size: 12px; font-weight: 600; color: #1565c0; background: white;
    transition: all 0.15s;
}}
#scorePopup .popup-combine:hover {{ background: #eef4fc; }}
#scorePopup .popup-combine.active {{ background: #1565c0; color: white; }}
#scorePopup .popup-color-label {{ font-size: 11px; color: #888; font-weight: 600; letter-spacing: 0.3px; margin-bottom: 5px; text-transform: uppercase; }}
.edits-tbl {{ width: 100%; border-collapse: collapse; font-size: 12px; background: white; border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden; }}
.edits-tbl th {{ background: #000; color: #fff; padding: 6px 10px; text-align: left; font-weight: 700; font-size: 11px; letter-spacing: 0.3px; text-transform: uppercase; }}
.edits-tbl td {{ padding: 6px 10px; border-top: 1px solid #f0f0f0; color: #222; }}
.edits-tbl tr:hover td {{ background: #fafafa; }}
#scorePopup .popup-colors {{ display: flex; gap: 5px; margin-bottom: 10px; align-items: center; }}
#scorePopup .popup-reassign {{ display: flex; margin-bottom: 10px; }}
#scorePopup .popup-reassign select {{ flex: 1; padding: 5px 7px; font-size: 12px; border: 1px solid #ccc; border-radius: 5px; background: white; }}
/* Color-only mode: hide everything that isn't the color picker (used when the popup
   is opened from the detail-view 'Most Recent' block). */
#scorePopup.color-only .popup-color,
#scorePopup.color-only .popup-source,
#scorePopup.color-only .popup-team-info,
#scorePopup.color-only .popup-points-label,
#scorePopup.color-only .popup-points,
#scorePopup.color-only .popup-scores,
#scorePopup.color-only .popup-pdw,
#scorePopup.color-only .popup-combine,
#scorePopup.color-only .popup-picks-wrap,
#scorePopup.color-only .popup-reassign-wrap,
#scorePopup.color-only .popup-reset {{ display: none !important; }}
#scorePopup .popup-picks {{ display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px; }}
#scorePopup .pk-chip {{ display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 700; color: #777; border: 1px solid #d5d5d5; border-radius: 5px; padding: 3px 6px; cursor: pointer; background: #fff; }}
#scorePopup .pk-chip.on {{ color: #111; border-color: #7ba7e0; background: #eef4fc; }}
#scorePopup .pk-chip input {{ width: 13px; height: 13px; cursor: pointer; margin: 0; }}
/* Default mode hides the color picker — the cell popup edits points/score/PDW;
   color editing lives in the detail-view 'Most Recent' block (color-only mode). */
#scorePopup .popup-set-color-wrap {{ display: none; }}
#scorePopup.color-only .popup-set-color-wrap {{ display: block; }}
#scorePopup .popup-color-note {{
    width: 100%; box-sizing: border-box; margin-bottom: 8px; padding: 6px 8px;
    font-size: 12px; border: 1px solid #ccc; border-radius: 5px; background: white;
}}
#scorePopup .popup-color-note::placeholder {{ color: #aaa; }}
#scorePopup .popup-colors button {{
    flex: 1; height: 28px; border: 2px solid rgba(0,0,0,0.15); border-radius: 5px;
    cursor: pointer; padding: 0; transition: transform 0.1s, border-color 0.1s;
}}
#scorePopup .popup-colors button:hover {{ transform: scale(1.06); }}
#scorePopup .popup-colors button.active {{ border-color: #000; box-shadow: 0 0 0 1px #000 inset; }}
#scorePopup .popup-colors .cs-green   {{ background: rgb(130, 200, 140); }}
#scorePopup .popup-colors .cs-lgreen  {{ background: rgb(200, 230, 180); }}
#scorePopup .popup-colors .cs-yellow  {{ background: rgb(252, 232, 130); }}
#scorePopup .popup-colors .cs-orange  {{ background: rgb(245, 160, 95); }}
#scorePopup .popup-colors .cs-red     {{ background: rgb(225, 110, 105); }}
#scorePopup .popup-colors .cs-clear {{
    flex: 0 0 28px; background: white; color: #888; font-size: 16px; font-weight: 700;
    line-height: 1; border: 2px solid #ccc;
}}
#scorePopup .popup-colors .cs-clear:hover {{ color: #c0392b; border-color: #c0392b; }}
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

.detail-container {{ padding: 12px 18px; display: none; }}
.player-select-wrapper {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
.player-select-wrapper label {{ font-weight: 600; font-size: 12px; color: #555; }}
.player-select {{
    padding: 7px 12px; font-size: 13px; border: 1px solid #ccc;
    border-radius: 6px; background: white; min-width: 230px; cursor: pointer;
}}
.player-select:focus {{ outline: none; border-color: #000000; }}

.player-summary {{
    display: flex; gap: 22px; margin-bottom: 12px; background: white;
    padding: 12px 18px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
.summary-item {{ display: flex; flex-direction: column; gap: 2px; }}
.summary-label {{ font-size: 10px; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
.summary-value {{ font-size: 17px; font-weight: 700; color: #000000; }}

/* Per-player color breakdown — at-a-glance "who's hot, who's cold". Each row
   is the literal cell color so the eye can scan; empty buckets dim out so the
   active colors pop without removing the structural overview. */
.color-breakdown {{
    display: flex; flex-direction: column; gap: 3px; margin-bottom: 12px;
}}
.cb-row {{
    display: flex; align-items: center; gap: 14px;
    padding: 6px 12px; border-radius: 5px; font-size: 12px;
    border: 1px solid rgba(0,0,0,0.08); min-height: 28px;
}}
.cb-empty-row {{ opacity: 0.4; }}
.cb-label {{ font-weight: 700; min-width: 110px; color: #1a1a1a; }}
.cb-teams {{ color: #1a1a1a; font-weight: 600; letter-spacing: 0.4px; }}
.cb-empty {{ opacity: 0.5; font-weight: 500; font-style: italic; }}

.detail-table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    background: white; border-radius: 6px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); font-size: 12px;
}}
.detail-table th {{
    background: #000000; color: white; font-weight: 600; padding: 8px 12px;
    text-align: left; font-size: 11px; letter-spacing: 0.3px;
}}
.detail-table td {{ padding: 7px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
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
/* The 769–1024px breakpoint was removed: the compact desktop default now
   works comfortably at tablet width without further override. */

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
.cal-month-btn {{
    font-family: inherit; background: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 4px 10px; cursor: pointer;
}}
.cal-month-btn:hover {{ background: #fff5f5; border-color: #f5c4c1; }}
.cal-range-panel {{ min-width: 240px; padding: 8px 0 4px; }}
.cal-range-row {{ display: flex; align-items: center; gap: 8px; padding: 4px 12px; font-size: 12px; color: #444; }}
.cal-range-row select {{ flex: 1; padding: 4px 6px; font-size: 12px; border: 1px solid #ccc; border-radius: 4px; }}
.cal-range-actions {{
    display: flex; gap: 6px; justify-content: flex-end;
    padding: 8px 12px; border-top: 1px solid #eee; margin-top: 4px;
}}
.cal-range-actions button {{
    padding: 4px 12px; font-size: 12px; font-weight: 600; border-radius: 4px; cursor: pointer; border: 1px solid;
}}
.cal-range-actions .cal-range-clear {{ background: white; color: #555; border-color: #ccc; }}
.cal-range-actions .cal-range-apply {{ background: #ff2a22; color: white; border-color: #ff2a22; }}
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
.cal-grid {{ display: flex; flex-direction: column; gap: 16px; }}
.cal-month-block {{ display: flex; flex-direction: column; }}
.cal-month-hdr {{
    font-size: 13px; font-weight: 800; color: #000; padding: 4px 0 6px;
    border-bottom: 2px solid #000; margin-bottom: 6px; letter-spacing: 0.4px;
    display: none;
}}
.cal-grid.multi .cal-month-hdr {{ display: block; }}
.cal-month-grid {{
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
/* Workout chip for a (player, team) pair whose most-recent color is "green" — bold lettering. */
.cal-chip.workout-green-conn {{ font-weight: 800; }}
.cal-chip.tentative {{ opacity: 0.75; font-style: italic; }}
.cal-chip.manual::after {{ content: ' *'; opacity: 0.8; }}
.cal-legend {{ display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 10px; font-size: 10px; color: #666; }}
.cal-legend-item {{ display: flex; align-items: center; gap: 4px; }}
.cal-legend-swatch, .cal-legend-sw {{ width: 12px; height: 12px; border-radius: 3px; }}
.cal-pad {{ background: #fafafa !important; cursor: default !important; }}
.cal-pad:hover {{ background: #fafafa !important; }}
.cal-cell.cal-draft {{ background: #fff5e0; }}
.cal-cell.cal-combine {{ background: #e8f0fb; }}
.cal-cell.cal-today {{ background: #fff0ed; }}
.cal-cell.cal-today::before {{
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #ff2a22;
}}
.cal-drafttag {{
    display: inline-block; font-size: 8px; padding: 1px 4px; background: #ff2a22; color: white;
    border-radius: 2px; vertical-align: middle; font-weight: 700; letter-spacing: 0.5px;
}}
.cal-combinetag {{
    display: inline-block; font-size: 8px; padding: 1px 4px; background: #1e6fbb; color: white;
    border-radius: 2px; vertical-align: middle; font-weight: 700; letter-spacing: 0.5px;
}}

/* --- Event modal --- */
#evOverlay, #mrOverlay, #gameDetailsOverlay, #teamInfoOverlay {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000;
    display: none; align-items: center; justify-content: center;
}}
#evOverlay.open, #mrOverlay.open, #gameDetailsOverlay.open, #teamInfoOverlay.open {{ display: flex; }}
#evModal, #mrModal, #gameDetailsModal, #teamInfoModal {{
    background: white; border-radius: 8px; padding: 20px 22px; width: 420px; max-width: 92vw;
    max-height: 90vh; overflow-y: auto; box-shadow: 0 6px 32px rgba(0,0,0,0.3);
}}
#teamInfoBody .gd-row .ti-pool {{ color: #1a5e1a; font-weight: 700; }}
#teamInfoBody .gd-row .ti-picks {{ color: #c0392b; font-weight: 600; }}
#teamInfoModal {{ position: relative; }}
.ti-modal-x {{
    position: absolute; top: 8px; right: 10px;
    width: 26px; height: 26px; padding: 0; line-height: 1;
    background: transparent; border: none; cursor: pointer;
    color: #888; font-size: 22px; font-weight: 400;
    border-radius: 4px;
}}
.ti-modal-x:hover {{ background: #f0f0f0; color: #333; }}
.ti-actions {{ display: flex; gap: 8px; margin-top: 14px; }}
.ti-actions button {{ flex: 1; padding: 9px 14px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; color: white; }}
.ti-actions .ti-edit {{ background: #ff2a22; }}
.ti-actions .ti-edit:hover {{ background: #d4221a; }}
.ti-actions .ti-slack {{ background: #000; }}
.ti-actions .ti-slack:hover {{ background: #222; }}
.ti-actions .ti-slack:disabled {{ background: #ccc; cursor: not-allowed; }}
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
.agenda-day.agenda-combine {{ background: #e8f0fb; }}
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
.agenda-combinetag {{
    display: inline-block; font-size: 8px; padding: 1px 4px; background: #1e6fbb; color: white;
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

/* ===================== Client (row) filter ===================== */
.client-hdr {{ position: relative; }}
.client-filter-btn {{ margin-left: 7px; background: none; border: none; color: #ccc; font-size: 16px; cursor: pointer; padding: 0 3px; vertical-align: middle; line-height: 1; }}
.client-filter-btn:hover {{ color: #fff; }}
.client-filter-btn.active {{ color: #ff5a52; }}
#clientFilterPanel {{ position: fixed; z-index: 9300; display: none; background: #fff; border: 1px solid #d0d0d0; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,.2); padding: 8px; width: 210px; }}
#clientFilterPanel .cfp-head {{ display: flex; justify-content: space-between; align-items: center; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #888; padding: 2px 2px 7px; border-bottom: 1px solid #eee; margin-bottom: 5px; }}
#clientFilterPanel .cfp-head button {{ background: none; border: 1px solid #d0d0d0; border-radius: 4px; font-size: 10px; font-weight: 700; color: #444; cursor: pointer; padding: 2px 6px; margin-left: 4px; }}
#clientFilterPanel .cfp-head button:hover {{ background: #f2f2f2; }}
#clientFilterPanel .cfp-list {{ max-height: 340px; overflow-y: auto; }}
#clientFilterPanel .cfp-row {{ display: flex; align-items: center; gap: 8px; padding: 4px 5px; font-size: 12.5px; color: #222; cursor: pointer; border-radius: 5px; }}
#clientFilterPanel .cfp-row:hover {{ background: #f5f5f5; }}
#clientFilterPanel .cfp-row input {{ width: 15px; height: 15px; cursor: pointer; flex: none; }}

/* ===================== Draft Card view ===================== */
#draftCardView {{ padding: 18px 22px 48px; }}
#draftCardView .dc-head {{ display: flex; align-items: center; gap: 18px; flex-wrap: wrap; margin-bottom: 6px; }}
#draftCardView .dc-head-titles {{ display: flex; flex-direction: column; gap: 1px; }}
#draftCardView .dc-kicker {{ font-size: 10px; font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase; color: #ff2a22; }}
#draftCardView .dc-title {{ font-size: 22px; font-weight: 800; letter-spacing: -0.02em; margin: 0; color: #111; }}
#draftCardView .dc-controls {{ display: flex; align-items: center; gap: 8px; }}
#draftCardView .dc-controls label {{ font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: #888; }}
#draftCardView .dc-controls select {{ font-size: 15px; font-weight: 700; border: 1px solid #d0d0d0; border-radius: 8px; padding: 7px 10px; background: #fff; color: #111; min-width: 190px; cursor: pointer; }}
#draftCardView .dc-status {{ margin-left: auto; display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; color: #888; }}
#draftCardView .dc-dot {{ width: 9px; height: 9px; border-radius: 50%; background: #9aa; flex: none; }}
#draftCardView .dc-dot.live {{ background: #1faa4d; }}
#draftCardView .dc-dot.saving {{ background: #e8a300; }}
#draftCardView .dc-dot.err {{ background: #d33; }}
#draftCardView .dc-toolbar {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; background: #fff; border: 1px solid #e3e3e3; border-radius: 12px; padding: 10px 14px; margin: 12px 0 18px; }}
#draftCardView .dc-hint {{ color: #666; font-size: 12.5px; line-height: 1.4; max-width: 640px; }}
#draftCardView .dc-spacer {{ flex: 1; }}
#draftCardView .dc-act {{ border: 1px solid #d0d0d0; background: #fff; border-radius: 8px; padding: 8px 13px; font-size: 13px; font-weight: 700; cursor: pointer; color: #111; }}
#draftCardView .dc-act:hover {{ background: #f3f3f3; }}
#draftCardView .dc-act.dc-danger {{ color: #b00; }}
/* Flat, matrix-style grid: contiguous cells separated by thin lines (the grid
   gap over a light background), no rounded corners or drop shadows. */
#draftCardView .dc-grid {{ display: grid; grid-template-columns: repeat(10, 1fr); gap: 1px; background: #ececec; border: 1px solid #ececec; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
#draftCardView .dc-cell {{ position: relative; background: #fff; min-height: 66px; padding: 7px 6px; cursor: pointer; display: flex; flex-direction: column; align-items: center; justify-content: space-between; text-align: center; overflow: hidden; }}
#draftCardView .dc-cell:hover {{ outline: 2px solid #000; outline-offset: -2px; z-index: 2; }}
#draftCardView .dc-cell.sel {{ outline: 2px solid #000; outline-offset: -2px; z-index: 2; }}
#draftCardView .dc-cell.edited::after {{ content: ''; position: absolute; bottom: 4px; right: 5px; width: 5px; height: 5px; border-radius: 50%; background: rgba(0,0,0,.4); }}
#draftCardView .dc-cell.dark.edited::after {{ background: rgba(255,255,255,.7); }}
#draftCardView .dc-cell.dark.edited::after {{ background: rgba(255,255,255,.75); }}
#draftCardView .dc-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; }}
#draftCardView .dc-slot {{ font-size: 10px; font-weight: 800; color: #6b6b6b; line-height: 1; }}
#draftCardView .dc-cell.dark .dc-slot {{ color: rgba(255,255,255,.82); }}
#draftCardView .dc-team {{ font-size: 18px; font-weight: 800; letter-spacing: -.01em; line-height: 1; color: #111; }}
#draftCardView .dc-cell.dark .dc-team {{ color: #fff; }}
#draftCardView .dc-bottom {{ display: flex; flex-direction: column; align-items: center; }}
#draftCardView .dc-bonus {{ font-size: 10.5px; font-weight: 700; color: #333; line-height: 1.1; }}
#draftCardView .dc-cell.dark .dc-bonus {{ color: rgba(255,255,255,.92); }}
#draftCardView .dc-tag {{ font-size: 7.5px; font-weight: 800; letter-spacing: .08em; color: #777; margin-top: 1px; text-transform: uppercase; }}
#draftCardView .dc-cell.dark .dc-tag {{ color: rgba(255,255,255,.8); }}
#draftCardView .dc-section {{ grid-column: 1 / -1; background: #fafafa; padding: 5px 10px 4px; font-size: 10px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: #888; border-top: 2px solid #d8d8d8; }}
/* Corner dots — always the same corner: workout top-left (black), combine top-right (blue). */
#draftCardView .dc-work {{ position: absolute; top: 5px; left: 6px; width: 10px; height: 10px; border-radius: 50%; background: #000; pointer-events: none; box-shadow: 0 0 0 1px rgba(255,255,255,.7); }}
#draftCardView .dc-cell.dark .dc-work {{ box-shadow: 0 0 0 1px rgba(255,255,255,.85); }}
#draftCardView .dc-comb {{ position: absolute; top: 5px; right: 6px; width: 10px; height: 10px; border-radius: 50%; background: #1565c0; pointer-events: none; box-shadow: 0 0 0 1px rgba(255,255,255,.7); }}
#draftCardView .dc-cell.dark .dc-comb {{ box-shadow: 0 0 0 1px rgba(0,0,0,.3); }}
#draftCardView .dc-keyrow {{ display: flex; gap: 18px; flex-wrap: wrap; align-items: center; margin-top: 18px; font-size: 12px; color: #666; }}
#draftCardView .dc-keyrow .dc-k {{ display: inline-flex; align-items: center; gap: 6px; font-weight: 700; }}
#draftCardView .dc-keyrow .dc-k i {{ width: 14px; height: 14px; border-radius: 4px; border: 1px solid rgba(0,0,0,.15); display: inline-block; }}
#draftCardView .dc-footer {{ margin-top: 18px; color: #888; font-size: 12px; }}
#draftCardView .dc-print-head {{ display: none; }}  /* shown only when printing */
#draftCardView .dc-head-player {{ font-size: 15px; font-weight: 800; color: #222; margin-top: 2px; }}
#draftCardView .dc-window {{ display: flex; align-items: center; gap: 4px; }}
#draftCardView .dc-window-label {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #888; margin-right: 2px; }}
#draftCardView .dc-range {{ display: flex; align-items: center; gap: 4px; }}
#draftCardView .dc-range input {{ width: 54px; padding: 5px 6px; font-size: 12px; font-weight: 700; border: 1px solid #d0d0d0; border-radius: 5px; text-align: center; }}
#draftCardView .dc-range-dash {{ color: #999; }}
/* Multi-player selector */
#draftCardView .dc-controls {{ position: relative; }}
#draftCardView .dc-player-btn {{ font-size: 15px; font-weight: 700; border: 1px solid #d0d0d0; border-radius: 8px; padding: 7px 12px; background: #fff; color: #111; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; min-width: 190px; justify-content: space-between; }}
#draftCardView .dc-player-btn .dc-caret {{ color: #888; font-size: 11px; }}
#draftCardView .dc-player-panel {{ display: none; position: absolute; top: 100%; left: 0; margin-top: 4px; z-index: 9300; background: #fff; border: 1px solid #d0d0d0; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,.2); padding: 8px; width: 230px; }}
#draftCardView .dc-pp-head {{ display: flex; justify-content: space-between; align-items: center; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #888; padding: 2px 2px 7px; border-bottom: 1px solid #eee; margin-bottom: 5px; }}
#draftCardView .dc-pp-head button {{ background: none; border: 1px solid #d0d0d0; border-radius: 4px; font-size: 10px; font-weight: 700; color: #444; cursor: pointer; padding: 2px 6px; }}
#draftCardView .dc-pp-list {{ max-height: 340px; overflow-y: auto; }}
#draftCardView .dc-pp-row {{ display: flex; align-items: center; gap: 8px; padding: 4px 5px; font-size: 12.5px; color: #222; cursor: pointer; border-radius: 5px; }}
#draftCardView .dc-pp-row:hover {{ background: #f5f5f5; }}
#draftCardView .dc-pp-row input {{ width: 15px; height: 15px; flex: none; cursor: pointer; }}
/* Compare mode: neutral cell + one initial-chip per selected player */
#draftCardView .dc-cell.dc-multi {{ background: #fff !important; justify-content: flex-start; gap: 3px; min-height: 78px; }}
#draftCardView .dc-chips {{ display: flex; flex-wrap: wrap; gap: 3px; justify-content: center; margin: 1px 0; }}
#draftCardView .dc-chip {{ font-size: 10px; font-weight: 800; padding: 2px 5px; border-radius: 4px; color: #222; cursor: pointer; border: 1px solid rgba(0,0,0,.12); line-height: 1.15; }}
#draftCardView .dc-chip.dark {{ color: #fff; border-color: rgba(255,255,255,.25); }}
#draftCardView .dc-chip.empty {{ color: #aaa; }}
/* In-play checkbox on single-player squares (bottom-right corner) */
#draftCardView .dc-pickbox {{ position: absolute; bottom: 4px; right: 5px; width: 13px; height: 13px; border-radius: 3px; border: 1.5px solid rgba(0,0,0,.4); background: rgba(255,255,255,.85); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 900; line-height: 1; color: #111; cursor: pointer; }}
#draftCardView .dc-pickbox:hover {{ border-color: #111; }}
#draftCardView .dc-pickbox.on {{ background: #111; border-color: #111; color: #fff; }}
#draftCardView .dc-cell.dark .dc-pickbox {{ border-color: rgba(255,255,255,.7); }}
/* Cell editor popup (fixed, shared with the dashboard overlay stack) */
#dcBackdrop {{ position: fixed; inset: 0; background: transparent; display: none; z-index: 8500; }}
#dcEditor {{ position: fixed; z-index: 9100; display: none; width: 252px; background: #fff; border: 1px solid #e3e3e3; border-radius: 14px; box-shadow: 0 12px 34px rgba(0,0,0,.22); padding: 13px 14px; }}
#dcEditor .dc-ed-title {{ font-size: 13px; font-weight: 800; margin-bottom: 11px; color: #111; }}
#dcEditor .dc-ed-title b {{ color: #ff2a22; }}
#dcEditor .dc-ed-label {{ font-size: 10px; font-weight: 800; letter-spacing: .09em; text-transform: uppercase; color: #888; margin-bottom: 7px; }}
#dcEditor .dc-ed-colors {{ display: flex; gap: 7px; margin-bottom: 14px; flex-wrap: wrap; }}
#dcEditor .dc-ed-sw {{ width: 30px; height: 30px; border-radius: 8px; border: 2px solid rgba(0,0,0,.18); cursor: pointer; transition: .1s; }}
#dcEditor .dc-ed-sw:hover {{ transform: translateY(-1px); }}
#dcEditor .dc-ed-sw.sel {{ border-color: #111; box-shadow: 0 0 0 2px #fff, 0 0 0 4px #111; }}
#dcEditor .dc-ed-sw.clear {{ background: #fff; display: flex; align-items: center; justify-content: center; color: #b00; font-weight: 800; font-size: 15px; }}
#dcEditor .dc-ed-row {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }}
#dcEditor .dc-ed-row .dc-ed-label {{ margin-bottom: 0; }}
#dcEditor input#dcEdTeam {{ width: 86px; border: 1px solid #d0d0d0; border-radius: 8px; padding: 6px 8px; font-size: 14px; font-weight: 700; text-transform: uppercase; outline: none; }}
#dcEditor #dcEdCombine {{ border: 1px solid #d0d0d0; border-radius: 8px; padding: 6px 16px; font-size: 13px; font-weight: 800; cursor: pointer; background: #fff; color: #555; min-width: 60px; }}
#dcEditor #dcEdCombine.yes {{ background: #1565c0; border-color: #1565c0; color: #fff; }}
#dcEditor .dc-ed-actions {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 2px; }}
#dcEditor #dcEdReset {{ border: none; background: none; color: #888; font-size: 11px; font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0; }}
#dcEditor #dcEdDone {{ border: none; background: #111; color: #fff; border-radius: 8px; padding: 7px 18px; font-size: 13px; font-weight: 800; cursor: pointer; }}
/* Hover tooltip: the most-recent intel message behind a square */
#dcTip {{ position: fixed; z-index: 9200; display: none; max-width: 340px; background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,.2); padding: 10px 12px; pointer-events: none; }}
#dcTip .dc-tip-head {{ font-size: 12px; font-weight: 800; color: #111; margin-bottom: 3px; }}
#dcTip .dc-tip-meta {{ font-size: 10px; font-weight: 600; letter-spacing: .02em; color: #888; text-transform: uppercase; margin-bottom: 6px; }}
#dcTip .dc-tip-body {{ font-size: 11.5px; line-height: 1.42; color: #333; white-space: pre-wrap; max-height: 190px; overflow: hidden; }}
#dcTip .dc-tip-empty {{ font-size: 11.5px; color: #999; font-style: italic; }}
@media (max-width: 900px) {{
    #draftCardView .dc-grid {{ grid-template-columns: repeat(5, 1fr); }}
}}
@media print {{
    /* Draft Card print: landscape fits the 10-wide board; force color so the
       cell fills actually print (browsers drop backgrounds by default). */
    @page {{ size: landscape; margin: 0.4in; }}
    html, body {{ background: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    * {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
    /* Hide all chrome + the non-printing views. */
    .header, .nav-tabs, .stats-bar, .legend,
    #matrixView, #detailView, #calendarView, #editsView,
    #clientFilterPanel, #scorePopup, #scoreOverlay, #toast,
    #draftCardView .dc-head, #draftCardView .dc-controls, #draftCardView .dc-toolbar, #draftCardView .dc-status {{ display: none !important; }}
    #dcEditor, #dcBackdrop {{ display: none !important; }}
    #draftCardView {{ display: block !important; padding: 0 !important; }}
    #draftCardView .dc-print-head {{ display: flex; justify-content: space-between; align-items: baseline;
        border-bottom: 3px solid #ff2a22; padding-bottom: 6px; margin-bottom: 10px; }}
    #draftCardView .dc-ph-title {{ font-size: 15px; font-weight: 800; letter-spacing: .02em; color: #000; }}
    #draftCardView .dc-ph-player {{ font-size: 17px; font-weight: 800; color: #000; }}
    #draftCardView .dc-grid {{ gap: 1px; }}
    #draftCardView .dc-cell {{ box-shadow: none !important; transform: none !important; break-inside: avoid; }}
    #draftCardView .dc-pickbox {{ display: none !important; }}
    #draftCardView .dc-section {{ break-inside: avoid; break-after: avoid; }}
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
        <div class="nav-tab" onclick="showView('draftcard')">Draft Card</div>
        <div class="nav-tab" onclick="showView('detail')">Detail View</div>
        <div class="nav-tab" onclick="showView('edits')">Edits</div>
    </div>
</div>

<div id="statsBar" class="stats-bar"></div>

<div class="legend">
    <span class="legend-title">Key:</span>
    <div class="legend-item"><div class="legend-swatch" style="background:#fff;border:1px solid #ccc;position:relative;"><span style="position:absolute;top:1px;left:1px;width:6px;height:6px;border-radius:50%;background:#000;"></span></div>Pre-Draft Workout</div>
    <div class="legend-item"><div class="legend-swatch" style="background:#fff;border:1px solid #ccc;position:relative;"><span style="position:absolute;top:1px;right:1px;width:6px;height:6px;border-radius:50%;background:#1565c0;"></span></div>Combine Meeting</div>
    <span class="legend-title" style="margin-left:14px;">Points</span>
    <span style="font-size:11px;color:#666;">GM 5 &middot; Dir 4 &middot; NXC 3 &middot; X 2 &middot; Area 1</span>
    <div id="dateWindowCtl" class="date-window">
        <span class="legend-title">Window:</span>
        <button id="dw_0"  class="dw-btn active" onclick="setDateWindow(0)"  title="Show all intel">All</button>
        <button id="dw_30" class="dw-btn"        onclick="setDateWindow(30)" title="Only records from the last 30 days">30d</button>
        <button id="dw_14" class="dw-btn"        onclick="setDateWindow(14)" title="Only records from the last 14 days">14d</button>
        <button id="dw_7"  class="dw-btn"        onclick="setDateWindow(7)"  title="Only records from the last 7 days">7d</button>
    </div>
</div>

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
            <div class="cal-multi cal-range" id="calRangeDropdown">
                <button type="button" class="cal-month-label cal-month-btn" id="calMonthLabel"
                        title="Click to pick a range of months"
                        onclick="event.stopPropagation(); toggleCalRangePanel()"></button>
                <div class="cal-multi-panel cal-range-panel" id="calRangePanel" onclick="event.stopPropagation()">
                    <div style="padding:6px 12px 4px;font-size:11px;color:#666;font-weight:700;letter-spacing:0.3px;">SHOW A RANGE OF MONTHS</div>
                    <div class="cal-range-row"><label style="min-width:32px;">From</label><select id="calRangeFrom"></select></div>
                    <div class="cal-range-row"><label style="min-width:32px;">To</label><select id="calRangeTo"></select></div>
                    <div class="cal-range-actions">
                        <button type="button" class="cal-range-clear" onclick="calClearMonthRange()">Single month</button>
                        <button type="button" class="cal-range-apply" onclick="calApplyMonthRange()">Apply</button>
                    </div>
                </div>
            </div>
            <button onclick="calShiftMonth(1)" title="Next month">&#8594;</button>
            <button onclick="calJumpTo('today')" title="Jump to today" style="margin-left:6px;">Today</button>
        </div>
        <button class="cal-addbtn" onclick="openEventModal(null, null)">+ Add Event</button>
        <button class="cal-pdfbtn" onclick="exportCalendarPDF()" title="Download this month as PDF">&#x2B07; PDF</button>
        <label class="cal-pdfopt" title="Include MLB Combine row in the PDW Invites table" style="display:inline-flex;align-items:center;gap:5px;font-size:11px;color:#555;cursor:pointer;user-select:none;margin-right:4px;">
            <input type="checkbox" id="pdfIncludeCombine" onchange="_pdfSaveCombineToggle(this.checked)" style="margin:0;cursor:pointer;">
            Add Combine
        </label>
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
        <div class="cal-filter cal-multi" id="calTypeDropdown">
            <label>Type:</label>
            <button type="button" class="cal-multi-btn" onclick="event.stopPropagation(); toggleCalTypePanel()">
                <span id="calTypeBtnLabel">All</span><span class="caret">&#9662;</span>
            </button>
            <div class="cal-multi-panel" id="calTypePanel" onclick="event.stopPropagation()">
                <div class="cal-multi-header">
                    <span class="cal-multi-ctl" onclick="calSelectAllTypes()">All</span>
                    <span class="cal-multi-ctl" onclick="calSelectNoTypes()">None</span>
                </div>
                <div id="calTypeChips"></div>
            </div>
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

<div id="editsView" style="display:none;padding:18px 22px;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px;">
        <button onclick="showView('matrix')" style="padding:6px 14px;font-size:13px;font-weight:600;background:#000000;color:white;border:none;border-radius:6px;cursor:pointer;">&#8592; Back</button>
        <h2 style="margin:0;font-size:18px;color:#000;">Manual Edits &amp; Additions</h2>
        <span id="editsCount" style="color:#666;font-size:13px;"></span>
    </div>
    <div id="editsBody"></div>
</div>

<div id="draftCardView" style="display:none;">
    <div class="dc-print-head">
        <span class="dc-ph-title">Stadium Ventures &middot; 2026 MLB Draft Card</span>
        <span class="dc-ph-player" id="dcPrintPlayer"></span>
    </div>
    <div class="dc-head">
        <div class="dc-head-titles">
            <div class="dc-kicker">Stadium Ventures &middot; 2026 MLB Draft</div>
            <h2 class="dc-title">Draft Card</h2>
            <div class="dc-head-player" id="dcHeadPlayer"></div>
        </div>
        <div class="dc-controls">
            <label>Players</label>
            <button id="dcPlayerBtn" class="dc-player-btn" onclick="dcTogglePlayerPanel(event)"><span id="dcPlayerBtnLabel">&mdash;</span><span class="dc-caret">&#9662;</span></button>
            <div id="dcPlayerPanel" class="dc-player-panel">
                <div class="dc-pp-head"><span>Compare up to 5</span><button onclick="dcClearCompare()">Clear extra</button></div>
                <div class="dc-pp-list" id="dcPlayerList"></div>
            </div>
        </div>
        <div class="dc-status"><span class="dc-dot live" id="dcDot"></span><span id="dcStatusText">Seeded from TeamIntel</span></div>
    </div>
    <div class="dc-toolbar">
        <div class="dc-hint"><b>Click any square</b> to see the latest TeamIntel message behind it. Colors, workout &amp; combine dots come straight from the engine.</div>
        <div class="dc-spacer"></div>
        <div class="dc-range">
            <span class="dc-window-label">Picks</span>
            <input type="number" id="dcRangeMin" min="1" max="313" value="1" onchange="dcSetRange()" title="First pick to show">
            <span class="dc-range-dash">&ndash;</span>
            <input type="number" id="dcRangeMax" min="1" max="313" value="313" onchange="dcSetRange()" title="Last pick to show">
        </div>
        <div class="dc-window">
            <span class="dc-window-label">Window</span>
            <button id="dcw_0" class="dw-btn active" onclick="setDateWindow(0)" title="All intel">All</button>
            <button id="dcw_30" class="dw-btn" onclick="setDateWindow(30)" title="Last 30 days">30d</button>
            <button id="dcw_14" class="dw-btn" onclick="setDateWindow(14)" title="Last 14 days">14d</button>
            <button id="dcw_7" class="dw-btn" onclick="setDateWindow(7)" title="Last 7 days">7d</button>
        </div>
        <button class="dc-act" onclick="dcPrint()">Print / PDF</button>
    </div>
    <div class="dc-grid" id="dcGrid"></div>
    <div class="dc-keyrow" id="dcKeyrow"></div>
    <div class="dc-footer">Live shared board &middot; 2026 MLB Draft order &amp; assigned slot values &middot; seeded from TeamIntel; per-square overrides sync within a few seconds.</div>
</div>


</div><!-- /appContent -->

<div id="evOverlay" onclick="if(event.target===this) closeEventModal()">
    <div id="evModal">
        <div class="ev-title" id="evTitle">Add Event</div>
        <div class="ev-row">
            <label>Date</label>
            <input type="date" id="evDate" min="2026-04-01" max="2026-08-31">
        </div>
        <div class="ev-row" id="evExtraDatesRow">
            <label>Also on</label>
            <div style="flex:1;">
                <div id="evExtraDates"></div>
                <button type="button" onclick="addExtraDate()" style="margin-top:4px;font-size:11px;padding:3px 8px;border:1px solid #ccc;background:#f9f9f9;border-radius:4px;cursor:pointer;">+ Add date</button>
            </div>
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
        <div class="ev-row" id="evExtraPlayersRow">
            <label>Also for</label>
            <select id="evExtraPlayers" multiple size="4" style="flex:1;font-size:13px;padding:4px;" title="Hold Cmd/Ctrl to pick multiple"></select>
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
// Per-player SV recommendation that shows on the right side of each PDF
// player block. Distinct from the auto-generated PDW Invites table on the
// left. Shape: see data/recommended_schedule_2026.json.
const RECOMMENDED_SCHEDULE = {recommended_schedule_js};
// Slack workspace base URL (e.g. https://stadium-ventures.slack.com). Empty
// string when auth_test failed at fetch time — UI hides the "View in Slack"
// link in that case.
const SLACK_WORKSPACE_URL = {slack_workspace_js};

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

var scoreOverridesMeta = {{}};  // 'key' -> ISO timestamp of last edit (Edits tab uses this).
var scoreOverridesNotes = {{}};  // 'key' -> free-text reason (color overrides only, for now).
async function loadOverrides() {{
    try {{
        const res = await fetch('/api/overrides?meta=1');
        if (!res.ok) {{
            const body = await res.text();
            showToast('Could not load overrides (' + res.status + '). Manual edits may not persist. ' + body.slice(0, 120));
            return;
        }}
        const blob = await res.json();
        // Server returns {{ values, meta, notes }} when ?meta=1; fall back to flat shape if older.
        if (blob && typeof blob === 'object' && blob.values !== undefined) {{
            scoreOverrides = blob.values || {{}};
            scoreOverridesMeta = blob.meta || {{}};
            scoreOverridesNotes = blob.notes || {{}};
        }} else {{
            scoreOverrides = blob || {{}};
            scoreOverridesMeta = {{}};
            scoreOverridesNotes = {{}};
        }}
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

// --- Date-range (recency) window ---
// Filters the Slack/notes records that feed the matrix and detail view to the
// last N days. Manual overrides (color/score/PDW/etc.) are NOT date-filtered —
// they always apply. 0 = all time (default).
var _dateWindowDays = 0;
var _dateWindowCutoff = null;  // 'YYYY-MM-DD' cutoff, or null for all-time
function _inDateWindow(r) {{
    if (!_dateWindowCutoff) return true;
    return (r.date || '') >= _dateWindowCutoff;
}}
function setDateWindow(days) {{
    _dateWindowDays = days || 0;
    if (_dateWindowDays) {{
        var d = new Date();
        d.setDate(d.getDate() - _dateWindowDays);
        var pad = function(n) {{ return String(n).padStart(2, '0'); }};
        _dateWindowCutoff = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }} else {{
        _dateWindowCutoff = null;
    }}
    // Sync both toggle groups (matrix legend + draft card toolbar) — shared window.
    ['0', '30', '14', '7'].forEach(function(k) {{
        var el = document.getElementById('dw_' + k);
        if (el) el.classList.toggle('active', String(_dateWindowDays) === k);
        var el2 = document.getElementById('dcw_' + k);
        if (el2) el2.classList.toggle('active', String(_dateWindowDays) === k);
    }});
    renderMatrix();
    if (document.getElementById('detailView').style.display !== 'none' &&
        document.getElementById('playerSelect').value) {{
        renderDetail();
    }}
    if (typeof dcStarted !== 'undefined' && dcStarted &&
        document.getElementById('draftCardView').style.display !== 'none') {{
        dcRenderGrid();
    }}
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
            delete scoreOverridesMeta[key];
        }} else {{
            scoreOverrides[key] = score;
            scoreOverridesMeta[key] = new Date().toISOString();
        }}
        // "Reset to original" should also clear any manual points override.
        if (isReset && scoreOverrides.hasOwnProperty(tKey)) {{
            await fetch('/api/overrides', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ key: tKey, score: null }})
            }});
            delete scoreOverrides[tKey];
            delete scoreOverridesMeta[tKey];
        }}
        showToast('Saved', true);
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    renderMatrix();
    renderDetail();
}}

// Manual team reassignment for a single (player, original-team, date) record.
// Override key: 'mt|player|orig_team|date' -> new_team. Empty/null clears.
async function saveTeamReassign(newTeam) {{
    if (!newTeam) return;
    const player = _popupPlayer, team = _popupTeam, date = _popupDate;
    if (newTeam === team) return;  // dropdown was reset
    const mtKey = 'mt|' + player + '|' + team + '|' + date;
    closeScorePopup();
    try {{
        const res = await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ key: mtKey, score: newTeam }})
        }});
        if (!res.ok) {{
            const body = await res.text();
            showToast('Save failed (' + res.status + '). ' + body.slice(0, 120));
            return;
        }}
        scoreOverrides[mtKey] = newTeam;
        scoreOverridesMeta[mtKey] = new Date().toISOString();
        // Apply locally so the matrix/detail update without a full reload.
        RECORDS.forEach(r => {{
            if (r.player === player && r.team === team && r.date === date) {{
                r.team = newTeam;
                r.team_overridden = true;
            }}
        }});
        showToast('Team reassigned to ' + newTeam, true);
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    renderMatrix();
    renderDetail();
}}

// Manual most-recent-color override (popup color picker).
// `color` is one of: 'green', 'light green', 'yellow', 'orange', 'red', or null to clear.
async function saveColor(color) {{
    const player = _popupPlayer, team = _popupTeam;
    const ck = 'c|' + player + '|' + team;
    // Optional reason typed into the "Set most-recent color" section. Sent only
    // when setting a color (clearing removes the note server-side).
    const noteEl = document.getElementById('colorNoteInput');
    const note = (color === null || color === undefined) ? undefined : (noteEl ? noteEl.value.trim() : '');
    const payload = {{ key: ck, score: color }};
    if (note !== undefined) payload.note = note;
    try {{
        const res = await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
        }});
        if (!res.ok) {{
            const body = await res.text();
            showToast('Save failed (' + res.status + '). ' + body.slice(0, 120));
            return;
        }}
        if (color === null || color === undefined) {{
            delete scoreOverrides[ck];
            delete scoreOverridesMeta[ck];
            delete scoreOverridesNotes[ck];
        }} else {{
            scoreOverrides[ck] = color;
            scoreOverridesMeta[ck] = new Date().toISOString();
            if (note) scoreOverridesNotes[ck] = note;
            else delete scoreOverridesNotes[ck];
        }}
        showToast('Saved', true);
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    // Refresh the popup's "Most recent" label and the matrix/detail cell colors.
    openScorePopupRefresh();
    renderMatrix();
    renderDetail();
}}

function openScorePopupRefresh() {{
    // Re-render the most-recent label inside the still-open popup after a color change.
    const player = _popupPlayer, team = _popupTeam;
    if (!player || !team) return;
    _renderPopupColorBox(player, team);
    _renderPopupSourceBox(player, team);
    updateColorPicker();
}}

function updateColorPicker() {{
    // Mark the active swatch (matches the resolved current color) and toggle the Clear button.
    const player = _popupPlayer, team = _popupTeam;
    const cur = getLatestColor(player, team);
    const ovd = isColorOverridden(player, team);
    const COLORS = ['green', 'light green', 'yellow', 'orange', 'red'];
    COLORS.forEach(function(c) {{
        const id = 'colorSwatch_' + c.replace(' ', '_');
        const el = document.getElementById(id);
        if (!el) return;
        if (c === cur) el.classList.add('active');
        else el.classList.remove('active');
    }});
    const clr = document.getElementById('colorClearBtn');
    if (clr) clr.style.display = ovd ? 'inline-block' : 'none';
    // Prefill the reason field with any saved note for this cell's override.
    const noteEl = document.getElementById('colorNoteInput');
    if (noteEl) noteEl.value = scoreOverridesNotes['c|' + player + '|' + team] || '';
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
        scoreOverridesMeta[tKey] = new Date().toISOString();
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

// Combine-interview flag for a (player, team) pair. Auto-detected from the
// #2026-mlb-combine channel (r.combine); a manual 'cb|player|team' override
// can force it on or off, mirroring the PDW flag.
function isCombine(player, team) {{
    var ck = 'cb|' + player + '|' + team;
    if (scoreOverrides.hasOwnProperty(ck)) return scoreOverrides[ck];
    var hasAuto = false;
    RECORDS.forEach(function(r) {{ if (r.player === player && r.team === team && r.combine) hasAuto = true; }});
    return hasAuto;
}}

// Most-recent literal color for a (player, team) pair, with manual override applied.
// Returns null if no color is set. The override key is 'c|<player>|<team>' and the
// value is one of: 'green', 'light green', 'yellow', 'orange', 'red'.
function _autoLatestColor(player, team) {{
    var latest = null, latestDate = '';
    RECORDS.forEach(function(r) {{
        if (r.player !== player || r.team !== team || !r.color) return;
        if (isExcluded(r)) return;
        if ((r.date || '') > latestDate) {{ latestDate = r.date || ''; latest = r.color; }}
    }});
    return latest;
}}
// Source record (not just the color word) of the most-recent color for a
// (player, team) pair. Returns the actual record object so the UI can build
// a Slack permalink or label it as manual. Returns null when no underlying
// record carries a color — e.g. when only a manual color override exists.
function _autoLatestColorRecord(player, team) {{
    var latest = null, latestDate = '';
    RECORDS.forEach(function(r) {{
        if (r.player !== player || r.team !== team || !r.color) return;
        if (isExcluded(r)) return;
        if ((r.date || '') > latestDate) {{ latestDate = r.date || ''; latest = r; }}
    }});
    return latest;
}}
// A manual color override AUTO-EXPIRES: it holds only until a Slack colored
// record dated AFTER the override's edit supersedes it. Returns true when the
// override exists AND is still winning. Legacy overrides with no edit timestamp
// never expire (preserve manual work made before timestamps were tracked).
function _colorOverrideActive(player, team) {{
    var ck = 'c|' + player + '|' + team;
    if (!scoreOverrides.hasOwnProperty(ck)) return false;
    var ots = scoreOverridesMeta[ck];
    var odate = ots ? ots.slice(0, 10) : '9999-12-31';
    var rec = _autoLatestColorRecord(player, team);
    if (rec && (rec.date || '') > odate) return false;  // newer Slack color wins
    return true;
}}
function getLatestColor(player, team) {{
    if (_colorOverrideActive(player, team)) {{
        var v = scoreOverrides['c|' + player + '|' + team];
        return v || null;  // empty/null override means "no color"
    }}
    return _autoLatestColor(player, team);
}}
function isColorOverridden(player, team) {{
    return _colorOverrideActive(player, team);
}}

// Build a Slack permalink for a record. Format:
//   <workspace>/archives/<channel_id>/p<ts_no_dot>[?thread_ts=<parent_ts>&cid=<channel_id>]
// Returns null when we lack the workspace URL or the record's source fields.
function slackPermalink(r) {{
    if (!SLACK_WORKSPACE_URL || !r || !r.ts || !r.channel_id) return null;
    var ts = String(r.ts).replace('.', '');
    var url = SLACK_WORKSPACE_URL + '/archives/' + r.channel_id + '/p' + ts;
    if (r.parent_ts) {{
        url += '?thread_ts=' + encodeURIComponent(r.parent_ts) + '&cid=' + r.channel_id;
    }}
    return url;
}}

// Source descriptor for the most-recent color on a (player, team) pair.
// Shape: {{ kind: 'override' | 'slack' | 'manual_entry' | 'none',
//          slack_url?, channel?, date?, is_reply? }}
function getLatestColorSource(player, team) {{
    if (isColorOverridden(player, team)) {{
        return {{ kind: 'override' }};
    }}
    var rec = _autoLatestColorRecord(player, team);
    if (!rec) return {{ kind: 'none' }};
    if (rec.is_manual) {{
        return {{ kind: 'manual_entry', date: rec.date || '' }};
    }}
    return {{
        kind: 'slack',
        slack_url: slackPermalink(rec),
        channel: rec.channel || '',
        date: rec.date || '',
        is_reply: !!rec.parent_ts,
    }};
}}

// Compact "Apr 22" rendering for the source chip — saves horizontal space
// over the full ISO date.
function _fmtShortDate(iso) {{
    if (!iso) return '';
    var m = /^(\\d{{4}})-(\\d{{2}})-(\\d{{2}})$/.exec(iso);
    if (!m) return iso;
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return months[parseInt(m[2],10)-1] + ' ' + parseInt(m[3],10);
}}

// Render the popup's "Most recent" color line. Source attribution lives in
// its own row below — see _renderPopupSourceBox.
function _renderPopupColorBox(player, team) {{
    var cBox = document.getElementById('popupColor');
    if (!cBox) return;
    var color = getLatestColor(player, team);
    if (!color) {{ cBox.style.display = 'none'; cBox.innerHTML = ''; return; }}
    var bg = COLOR_BG[color] || '#ccc';
    cBox.innerHTML =
        '<span class="pc-swatch" style="background:' + bg + ';"></span>' +
        '<span class="pc-label">Most recent:</span>' +
        '<span class="pc-value">' + color + '</span>';
    cBox.style.background = bg;
    cBox.style.display = 'flex';
}}

// Synthetic key under which we register the source record so the existing
// message modal (which keys off _modalIndex) can render it. Reused across
// popup opens — last write wins.
var _POPUP_SOURCE_MODAL_KEY = '__popup_source__';

// Render the "Source: ..." row under the most-recent color line. Shows where
// the active color word came from and, when there's an underlying record,
// makes the chip click-through to the full message modal.
function _renderPopupSourceBox(player, team) {{
    var sBox = document.getElementById('popupSource');
    if (!sBox) return;
    var color = getLatestColor(player, team);
    if (!color) {{ sBox.style.display = 'none'; sBox.innerHTML = ''; return; }}
    var src = getLatestColorSource(player, team);
    var label = '<span class="popup-source-label">Source</span>';
    var chip = '';
    if (src.kind === 'override') {{
        var _note = scoreOverridesNotes['c|' + player + '|' + team] || '';
        var _noteHtml = _note ? ' <span class="popup-source-note">\\u2014 ' + _escapeHtml(_note) + '</span>' : '';
        chip = '<span class="popup-source-chip" title="Color set manually via the popup picker">Manual override</span>' + _noteHtml;
    }} else if (src.kind === 'manual_entry') {{
        var sourceRec = _autoLatestColorRecord(player, team);
        if (sourceRec) _modalIndex[_POPUP_SOURCE_MODAL_KEY] = sourceRec;
        var meLbl = 'Manual entry' + (src.date ? ' \\u00b7 ' + _fmtShortDate(src.date) : '');
        chip = '<button class="popup-source-chip" title="Click to view the manual entry" ' +
            'onclick="closeScorePopup(); openMessageModal(\\'' + _POPUP_SOURCE_MODAL_KEY + '\\');">' +
            meLbl + '</button>';
    }} else if (src.kind === 'slack') {{
        var sourceRec = _autoLatestColorRecord(player, team);
        if (sourceRec) _modalIndex[_POPUP_SOURCE_MODAL_KEY] = sourceRec;
        var slLbl = 'Slack' + (src.date ? ' \\u00b7 ' + _fmtShortDate(src.date) : '') +
            (src.is_reply ? ' (reply)' : '');
        var ch = src.channel ? ('#' + src.channel + ' \\u00b7 ' + (src.date || '')) : (src.date || '');
        chip = '<button class="popup-source-chip" title="Click to view the Slack message — ' + ch + '" ' +
            'onclick="closeScorePopup(); openMessageModal(\\'' + _POPUP_SOURCE_MODAL_KEY + '\\');">' +
            slLbl + '</button>';
    }} else {{
        sBox.style.display = 'none'; sBox.innerHTML = ''; return;
    }}
    sBox.innerHTML = label + chip;
    sBox.style.display = 'flex';
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
            delete scoreOverridesMeta[wk];
        }} else {{
            scoreOverrides[wk] = toStore;
            scoreOverridesMeta[wk] = new Date().toISOString();
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

async function toggleCombine() {{
    var ck = 'cb|' + _popupPlayer + '|' + _popupTeam;
    var hasAuto = false;
    RECORDS.forEach(function(r) {{ if (r.player === _popupPlayer && r.team === _popupTeam && r.combine) hasAuto = true; }});
    var current = isCombine(_popupPlayer, _popupTeam);
    var newVal = !current;
    // If the new value matches the auto-detected state, clear the override.
    // Otherwise persist the explicit true/false so an auto-true flag can be turned off.
    var toStore = (newVal === hasAuto) ? null : newVal;
    try {{
        const res = await fetch('/api/overrides', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ key: ck, score: toStore }})
        }});
        if (!res.ok) {{
            const body = await res.text();
            showToast('Save failed (' + res.status + '). ' + body.slice(0, 120));
            return;
        }}
        if (toStore === null) {{
            delete scoreOverrides[ck];
            delete scoreOverridesMeta[ck];
        }} else {{
            scoreOverrides[ck] = toStore;
            scoreOverridesMeta[ck] = new Date().toISOString();
        }}
        showToast('Saved', true);
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    updateCombineButton();
    renderMatrix();
    renderDetail();
}}

function updateCombineButton() {{
    var btn = document.getElementById('combineToggle');
    if (isCombine(_popupPlayer, _popupTeam)) {{
        btn.classList.add('active');
        btn.textContent = '\\u2713 Combine Interview';
    }} else {{
        btn.classList.remove('active');
        btn.textContent = 'Combine Interview';
    }}
}}

// --- "In play for picks": restricts which Draft Card picks show a player's color ---
// Stored as override 'pk|player|team' = array of in-play overall pick numbers.
// Absent = every pick is in play (default / current behavior).
function _teamPickList(team) {{ return DRAFT_SEED.filter(r => r[1] === team).map(r => r[0]); }}
function dcInPlay(player, team, pick) {{
    const key = 'pk|' + player + '|' + team;
    if (!scoreOverrides.hasOwnProperty(key)) return true;
    return (scoreOverrides[key] || []).indexOf(pick) !== -1;
}}
async function togglePickInPlay(player, team, pick) {{
    const key = 'pk|' + player + '|' + team;
    const all = _teamPickList(team);
    let arr = scoreOverrides.hasOwnProperty(key) ? (scoreOverrides[key] || []).slice() : all.slice();
    if (arr.indexOf(pick) !== -1) arr = arr.filter(x => x !== pick); else arr.push(pick);
    const toStore = (arr.length === all.length) ? null : arr;  // all in play → clear override
    try {{
        const res = await fetch('/api/overrides', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ key: key, score: toStore }}) }});
        if (!res.ok) {{ const b = await res.text(); showToast('Save failed (' + res.status + '). ' + b.slice(0, 120)); return; }}
        if (toStore === null) {{ delete scoreOverrides[key]; delete scoreOverridesMeta[key]; }}
        else {{ scoreOverrides[key] = toStore; scoreOverridesMeta[key] = new Date().toISOString(); }}
    }} catch(e) {{ showToast('Save failed: ' + (e.message || 'network error')); return; }}
    if (typeof dcStarted !== 'undefined' && dcStarted) dcRenderGrid();
}}

function openScorePopup(player, team, date, event, colorOnly) {{
    _popupPlayer = player;
    _popupTeam = team;
    _popupDate = date;
    var popupRoot = document.getElementById('scorePopup');
    if (colorOnly) popupRoot.classList.add('color-only');
    else popupRoot.classList.remove('color-only');
    document.getElementById('popupTitle').textContent = player + ' \\u2014 ' + team + (date ? ' (' + date + ')' : '');
    // Most-recent literal color for this (player, team) pair — same signal the
    // matrix cell shows. Skips records the user marked NA. Honors manual
    // override; source row below shows where the color came from.
    _renderPopupColorBox(player, team);
    _renderPopupSourceBox(player, team);
    // Build the color override picker — five swatches + a clear button when overridden.
    updateColorPicker();
    // Populate the team-reassign dropdown (skip current team) and reset selection.
    const reSel = document.getElementById('popupReassignTeam');
    if (reSel) {{
        if (reSel.options.length <= 1) {{
            ALL_TEAMS.forEach(t => {{
                const o = document.createElement('option');
                o.value = t; o.textContent = t;
                reSel.appendChild(o);
            }});
        }}
        Array.from(reSel.options).forEach(o => {{ o.disabled = (o.value === team); }});
        reSel.value = '';
    }}
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
    updateCombineButton();
    var popup = document.getElementById('scorePopup');
    var overlay = document.getElementById('scoreOverlay');
    popup.style.display = 'block';
    overlay.style.display = 'block';
    var rect = event.target.getBoundingClientRect();
    // Measure the popup's actual rendered height (it's already display:block) so
    // tall popups don't run off the bottom of the screen.
    var ph = popup.offsetHeight;
    var x = rect.left + rect.width / 2 - 110;
    var y = rect.bottom + 6;
    if (x < 8) x = 8;
    if (x + 220 > window.innerWidth) x = window.innerWidth - 228;
    // If it would overflow the bottom, prefer flipping above the cell; if it
    // doesn't fit there either, clamp to the viewport (max-height + overflow-y
    // keeps the full popup reachable by scrolling).
    if (y + ph > window.innerHeight - 8) {{
        var above = rect.top - 6 - ph;
        y = (above >= 8) ? above : Math.max(8, window.innerHeight - 8 - ph);
    }}
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

// Bonus-pool color scale: deep green = more $ to spend, deep red = less.
// 2026 MLB pool range is ~$3.95m (LAD) to ~$19.13m (PIT). Anchored to that
// span so the gradient hugs the actual data; values outside clamp.
// Anchored colors (mid → high → low) chosen for readability on both white and
// dark backgrounds, so the same value reads cleanly on the matrix header
// (black bg) and the detail card (white bg).
function poolTextColor(poolStr) {{
    if (!poolStr) return '#888';
    const m = String(poolStr).match(/([\\d.]+)/);
    if (!m) return '#888';
    const v = parseFloat(m[1]);
    const lo = 4, hi = 19;
    const t = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    // Anchors: low = deep red (170,40,35), mid = neutral gray (130,130,130),
    // high = deep green (35,140,60). Linear interp through the gray pivot.
    if (t >= 0.5) {{
        const u = (t - 0.5) * 2;
        const r = Math.round(130 + ( 35 - 130) * u);
        const g = Math.round(130 + (140 - 130) * u);
        const b = Math.round(130 + ( 60 - 130) * u);
        return 'rgb(' + r + ',' + g + ',' + b + ')';
    }} else {{
        const u = (0.5 - t) * 2;
        const r = Math.round(130 + (170 - 130) * u);
        const g = Math.round(130 + ( 40 - 130) * u);
        const b = Math.round(130 + ( 35 - 130) * u);
        return 'rgb(' + r + ',' + g + ',' + b + ')';
    }}
}}

function buildMatrix() {{
    // Number = sum of attendee-tier points across all touches for that
    // (player, team) cell (GM=+5, Dir=+4, NXC=+3, X=+2, Area=+1, T0=0).
    // Color = literal color word from the most recent record with one set.
    // Total column = sum of points across teams; ranks players by who has been
    // seen the most by the most senior people.
    const activeRecords = RECORDS.filter(r => !isExcluded(r) && _inDateWindow(r));
    const cellPoints = {{}};       // key -> sum of tier points
    const cellLatestColor = {{}};  // key -> {{date, color}} of most-recent colored record
    const workoutMap = {{}};
    const combineMap = {{}};        // key -> true if a combine meeting was detected

    activeRecords.forEach(r => {{
        const key = r.player + '|' + r.team;
        cellPoints[key] = (cellPoints[key] || 0) + getPoints(r);
        if (r.workout) workoutMap[key] = true;
        if (r.combine) combineMap[key] = true;
    }});
    // Colors are all-time: the most-recent color word shows even when its
    // source record falls outside the active date window (points stay windowed).
    RECORDS.forEach(r => {{
        if (isExcluded(r) || !r.color) return;
        const key = r.player + '|' + r.team;
        const cur = cellLatestColor[key];
        if (!cur || (r.date || '') > (cur.date || '')) {{
            cellLatestColor[key] = {{ date: r.date || '', color: r.color }};
        }}
    }});
    // Manual PDW overrides (matrix popup) still apply to the workout map.
    // Manual color overrides (c|player|team) override most-recent color.
    Object.keys(scoreOverrides).forEach(k => {{
        if (k.startsWith('cb|')) {{
            const parts = k.substring(3);
            if (scoreOverrides[k]) combineMap[parts] = true;
            else delete combineMap[parts];
        }} else if (k.startsWith('w|')) {{
            const parts = k.substring(2);
            if (scoreOverrides[k]) workoutMap[parts] = true;
            else delete workoutMap[parts];
        }} else if (k.startsWith('c|')) {{
            const key = k.substring(2);
            const val = scoreOverrides[k];
            // Auto-expire: a newer Slack colored record (already in cellLatestColor)
            // supersedes the override. Legacy overrides with no edit timestamp are
            // dated 9999 so they never expire.
            const ots = scoreOverridesMeta[k];
            const odate = ots ? ots.slice(0, 10) : '9999-12-31';
            const cur = cellLatestColor[key];
            if (cur && (cur.date || '') > odate) {{
                // newer Slack color wins — leave it in place
            }} else if (val) {{
                cellLatestColor[key] = {{ date: odate, color: val, manual: true }};
            }} else {{
                delete cellLatestColor[key];
            }}
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
    // Colored cells paint even when the pair has no intel records in the
    // active date window — covers manual overrides and out-of-window Slack
    // colors (color-only cell, 0 points, no connection counted).
    Object.keys(cellLatestColor).forEach(key => {{
        const [player, team] = key.split('|');
        if (!playerTeamColors[player]) playerTeamColors[player] = {{}};
        if (!playerTeamColors[player][team]) playerTeamColors[player][team] = cellLatestColor[key].color;
        if (playerTotals[player] === undefined) playerTotals[player] = 0;
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
    return {{ playerTeams, playerTeamColors, playerTotals, sortedPlayers, workoutMap, combineMap, coloredTeamCount }};
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

// Earliest draft pick a team holds (Infinity if unknown) — drives column order.
function minPickFor(team) {{
    const info = TEAM_DRAFT[team];
    if (info && info.picks && info.picks.length) {{
        const n = parseInt(info.picks[0], 10);
        if (!isNaN(n)) return n;
    }}
    return Infinity;
}}

// --- Client (row) filter: choose which players' rows show in the matrix ---
var _matrixHiddenPlayers = new Set();
try {{ _matrixHiddenPlayers = new Set(JSON.parse(localStorage.getItem('ti_matrix_hidden') || '[]')); }} catch(e) {{}}
function _persistClientFilter() {{ try {{ localStorage.setItem('ti_matrix_hidden', JSON.stringify([..._matrixHiddenPlayers])); }} catch(e) {{}} }}
function _allClientNames() {{ return [...new Set([...RECORDS.map(r => r.player), ...ALL_2026_PLAYERS])].sort(); }}
function buildClientFilterList() {{
    const host = document.getElementById('clientFilterList'); if (!host) return;
    host.innerHTML = '';
    _allClientNames().forEach(p => {{
        const row = document.createElement('label'); row.className = 'cfp-row';
        const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !_matrixHiddenPlayers.has(p);
        cb.onchange = () => {{ if (cb.checked) _matrixHiddenPlayers.delete(p); else _matrixHiddenPlayers.add(p); _persistClientFilter(); renderMatrix(); }};
        const span = document.createElement('span'); span.textContent = p;
        row.appendChild(cb); row.appendChild(span); host.appendChild(row);
    }});
}}
function clientFilterAll(show) {{
    if (show) _matrixHiddenPlayers.clear();
    else _allClientNames().forEach(p => _matrixHiddenPlayers.add(p));
    _persistClientFilter(); buildClientFilterList(); renderMatrix();
}}
function toggleClientFilter(ev) {{
    if (ev) ev.stopPropagation();
    const p = document.getElementById('clientFilterPanel'); if (!p) return;
    if (p.style.display === 'block') {{ p.style.display = 'none'; return; }}
    buildClientFilterList();
    p.style.display = 'block';
    const btn = document.getElementById('clientFilterBtn'); const r = btn.getBoundingClientRect();
    const pw = p.offsetWidth, ph = p.offsetHeight;
    let left = r.left, top = r.bottom + 4;
    if (left + pw > window.innerWidth - 8) left = window.innerWidth - 8 - pw;
    if (left < 8) left = 8;
    if (top + ph > window.innerHeight - 8) top = Math.max(8, window.innerHeight - 8 - ph);
    p.style.left = left + 'px'; p.style.top = top + 'px';
}}
document.addEventListener('click', function(e) {{
    const p = document.getElementById('clientFilterPanel');
    if (!p || p.style.display !== 'block') return;
    const btn = document.getElementById('clientFilterBtn');
    if (p.contains(e.target) || (btn && btn.contains(e.target))) return;
    p.style.display = 'none';
}});

function renderMatrix() {{
    const {{ playerTeams, playerTeamColors, playerTotals, sortedPlayers, workoutMap, combineMap }} = buildMatrix();

    // Columns ordered by each team's earliest pick (BAL #7 before ATH #8 …).
    // Teams with no pick data fall to the end, alphabetically.
    const orderedTeams = ALL_TEAMS.slice().sort((a, b) => {{
        const pa = minPickFor(a), pb = minPickFor(b);
        if (pa !== pb) return pa - pb;
        return a.localeCompare(b);
    }});

    const filterActive = _matrixHiddenPlayers.size > 0;
    var html = '<thead><tr><th rowspan="2" class="client-hdr">Client<button class="client-filter-btn' + (filterActive ? ' active' : '') + '" id="clientFilterBtn" onclick="toggleClientFilter(event)" title="Choose which clients to show">\\u25be</button></th>';
    orderedTeams.forEach(t => html += '<th>' + t + '</th>');
    html += '</tr><tr>';
    orderedTeams.forEach(t => {{
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

    const visiblePlayers = sortedPlayers.filter(p => !_matrixHiddenPlayers.has(p));
    visiblePlayers.forEach(player => {{
        const total = playerTotals[player] || 0;
        const rowTitle = ' title="' + total + ' total point' + (total === 1 ? '' : 's') + ' (GM=5, Dir=4, NXC=3, X=2, Area=1)"';
        const esc = player.replace(/'/g, "\\\\'");
        html += '<tr' + rowTitle + '>';
        html += '<td class="clickable" onclick="jumpToDetail(\\'' + esc + '\\')">' + player + '</td>';
        orderedTeams.forEach(team => {{
            const pts = playerTeams[player] && playerTeams[player][team];
            const colorWord = playerTeamColors[player] && playerTeamColors[player][team];
            const wk = workoutMap[player + '|' + team];
            const cm = combineMap[player + '|' + team];
            const hasData = (typeof pts === 'number' && pts > 0);
            if (hasData || colorWord || wk || cm) {{
                const bg = colorWord ? COLOR_BG[colorWord] : '';
                const cellStyle = bg ? 'background:' + bg + ';' : '';
                const display = (typeof pts === 'number' && pts > 0) ? String(pts) : '';
                const title = (pts || 0) + ' point' + (pts === 1 ? '' : 's') + (colorWord ? ' \\u2022 latest: ' + colorWord : '') + (wk ? ' \\u2022 pre-draft workout' : '') + (cm ? ' \\u2022 combine meeting' : '');
                const dots = (wk ? '<span class="cell-dot dot-pdw"></span>' : '') + (cm ? '<span class="cell-dot dot-combine"></span>' : '');
                html += '<td class="score-cell clickable" style="' + cellStyle + '" onclick="jumpToDetail(\\'' + esc + '\\', \\'' + team + '\\')" title="' + title + '">' + dots + display + '</td>';
            }} else {{
                // Empty cells are still clickable — drop the user on the team-filtered
                // detail view so they can set a color or add an entry.
                html += '<td class="score-cell clickable" onclick="jumpToDetail(\\'' + esc + '\\', \\'' + team + '\\')" title="No intel yet — click to open"></td>';
            }}
        }});
        html += '</tr>';
    }});
    html += '</tbody>';
    document.getElementById('matrixTable').innerHTML = html;

    let uniquePairs = 0;
    Object.keys(playerTeams).forEach(p => uniquePairs += Object.keys(playerTeams[p]).length);
    // Intel Reports and Date Range reflect the active recency window.
    const windowedCount = RECORDS.filter(r => _inDateWindow(r)).length;
    let dateRangeLabel;
    if (_dateWindowCutoff) {{
        const _mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const _p = _dateWindowCutoff.split('-');
        dateRangeLabel = _mon[parseInt(_p[1], 10) - 1] + ' ' + parseInt(_p[2], 10) + ', ' + _p[0] + ' - Present';
    }} else {{
        dateRangeLabel = 'Aug 2025 - Present';
    }}
    document.getElementById('statsBar').innerHTML =
        '<div class="stat-item"><span class="stat-label">Players:</span><span class="stat-value">' + visiblePlayers.length + (_matrixHiddenPlayers.size ? ' of ' + sortedPlayers.length : '') + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Intel Reports:</span><span class="stat-value">' + windowedCount + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Player-Team Connections:</span><span class="stat-value">' + uniquePairs + '</span></div>' +
        '<div class="stat-item"><span class="stat-label">Date Range:</span><span class="stat-value">' + dateRangeLabel + '</span></div>' +
        '<button class="mr-addentry-btn" id="matrixAddEntryBtn" onclick="openManualEntryModal(null, null, null)" title="Add a manual player-team connection">&#x2B;&nbsp;Add Entry</button>';
}}

function toggleHidden() {{
    _showHidden = !_showHidden;
    renderDetail();
}}

function renderDetail() {{
    const player = document.getElementById('playerSelect').value;
    if (!player) return;
    let allPr = RECORDS.filter(r => r.player === player && _inDateWindow(r)).sort((a,b) => b.date.localeCompare(a.date));
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
        // "Teams Connected" only matters when looking at the player as a whole;
        // when filtered to one team it's always 1. Hide in that case.
        (_filterTeam ? '' : '<div class="summary-item"><span class="summary-label">Teams Connected</span><span class="summary-value">' + teams.size + '</span></div>') +
        '<div class="summary-item"><span class="summary-label">Total Points</span><span class="summary-value">' + (visible.length > 0 ? totalPoints : '-') + '</span></div>';

    let hiddenBar = '';
    // Color breakdown (only visible when looking at the player across all teams):
    // group every team they have a literal color from, by that most-recent color.
    if (!_filterTeam) {{
        const latestByTeam = {{}};
        // Colors are all-time: build from every record for the player, not
        // just those inside the active date window.
        RECORDS.forEach(r => {{
            if (r.player !== player || isExcluded(r) || !r.color) return;
            const cur = latestByTeam[r.team];
            if (!cur || (r.date || '') > (cur.date || '')) {{
                latestByTeam[r.team] = {{ date: r.date, color: r.color }};
            }}
        }});
        // Apply manual color overrides (c|player|team) — replace or remove the auto entry.
        Object.keys(scoreOverrides).forEach(k => {{
            if (!k.startsWith('c|')) return;
            const parts = k.substring(2).split('|');
            if (parts.length !== 2 || parts[0] !== player) return;
            const t = parts[1];
            const v = scoreOverrides[k];
            if (v) latestByTeam[t] = {{ date: '9999-12-31', color: v }};
            else delete latestByTeam[t];
        }});
        const buckets = {{ 'green': [], 'light green': [], 'yellow': [], 'orange': [], 'red': [] }};
        Object.keys(latestByTeam).forEach(team => {{
            const c = latestByTeam[team].color;
            if (buckets[c]) buckets[c].push(team);
        }});
        const order = ['green', 'light green', 'yellow', 'orange', 'red'];
        const labels = {{ 'green':'Green', 'light green':'Light Green', 'yellow':'Yellow', 'orange':'Orange', 'red':'Red' }};
        const totalColored = order.reduce((a, c) => a + buckets[c].length, 0);
        if (totalColored > 0) {{
            let rows = '';
            order.forEach(c => {{
                const teams = buckets[c].sort();
                const bg = COLOR_BG[c];
                const teamsHtml = teams.length
                    ? teams.join(' \\u00b7 ')
                    : '<span class="cb-empty">none</span>';
                const emptyCls = teams.length === 0 ? ' cb-empty-row' : '';
                rows += '<div class="cb-row' + emptyCls + '" style="background:' + bg + ';">' +
                    '<span class="cb-label">' + labels[c] + ' <span style="color:#555;font-weight:600;">(' + teams.length + ')</span></span>' +
                    '<span class="cb-teams">' + teamsHtml + '</span>' +
                    '</div>';
            }});
            hiddenBar += '<div class="color-breakdown">' + rows + '</div>';
        }}
    }}
    if (_filterTeam) {{
        const tInfo = TEAM_DRAFT[_filterTeam];
        // Most-recent literal color word for this (player, team) — same signal
        // the matrix shows. Skips NA-excluded records. Honors manual color override.
        // Use the dropdown's player so the block renders even when no records yet exist
        // for the (player, team) pair (so the user can manually set a color).
        const _fcPlayer = (visible[0] && visible[0].player) || document.getElementById('playerSelect').value;
        let _fcLatest = _fcPlayer ? getLatestColor(_fcPlayer, _filterTeam) : null;
        // Anchor the popup to the latest record's date if any; empty string otherwise
        // (the color override doesn't need a date).
        let _fcLatestDate = '';
        if (_fcPlayer) {{
            visible.forEach(r => {{
                if ((r.date || '') > _fcLatestDate) _fcLatestDate = r.date || '';
            }});
        }}
        const _fcEsc = (_fcPlayer || '').replace(/'/g, "\\\\'");
        const _fcOnclick = _fcPlayer
            ? ' onclick="openScorePopup(\\'' + _fcEsc + '\\', \\'' + _filterTeam + '\\', \\'' + _fcLatestDate + '\\', event, true)"'
            : '';
        const _fcCursor = _fcOnclick ? 'cursor:pointer;' : '';
        const _fcSwatchBg = _fcLatest ? (COLOR_BG[_fcLatest] || '#ccc') : '#f0f0f0';
        const _fcLabel = _fcLatest
            ? '<span style="color:#1a1a1a;font-weight:800;font-size:18px;text-transform:capitalize;letter-spacing:0.3px;">' + _fcLatest + '</span>'
            : '<span style="color:#aaa;font-weight:600;font-size:14px;letter-spacing:0.3px;">(set color)</span>';
        const _fcSwatchBorder = _fcLatest ? 'rgba(0,0,0,0.15)' : '#bbb';
        const _fcSwatchStyle = _fcLatest ? '' : 'border-style:dashed;';
        // Source chip — same kinds the popup shows: Slack / Manual entry / Manual override.
        // Sits beneath the swatch so a glance answers "where did this color come from?"
        // Clicking the chip opens the in-app message modal (skipping the color-only
        // popup); event.stopPropagation prevents the parent click from firing too.
        let _fcSourceHtml = '';
        if (_fcPlayer && _fcLatest) {{
            const _src = getLatestColorSource(_fcPlayer, _filterTeam);
            const _srcRec = _autoLatestColorRecord(_fcPlayer, _filterTeam);
            const baseStyle = 'font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;white-space:nowrap;letter-spacing:0.2px;';
            if (_src.kind === 'override') {{
                _fcSourceHtml = '<span style="' + baseStyle + 'background:#f0f0f0;color:#444;border:1px solid #e0e0e0;" title="Color set manually via the popup picker">Manual override</span>';
            }} else if ((_src.kind === 'manual_entry' || _src.kind === 'slack') && _srcRec) {{
                _modalIndex[_POPUP_SOURCE_MODAL_KEY] = _srcRec;
                const lbl = (_src.kind === 'slack' ? 'Slack' : 'Manual entry') +
                    (_src.date ? ' \\u00b7 ' + _fmtShortDate(_src.date) : '') +
                    (_src.kind === 'slack' && _src.is_reply ? ' (reply)' : '');
                const tip = _src.kind === 'slack'
                    ? 'Click to view the Slack message' + (_src.channel ? ' \\u2014 #' + _src.channel : '')
                    : 'Click to view the manual entry';
                _fcSourceHtml = '<button style="' + baseStyle + 'background:#2a2a2a;color:#fff;border:1px solid #2a2a2a;cursor:pointer;" ' +
                    'onclick="event.stopPropagation(); openMessageModal(\\'' + _POPUP_SOURCE_MODAL_KEY + '\\');" ' +
                    'title="' + tip + '">' + lbl + '</button>';
            }}
        }}
        const colorBlock = _fcPlayer
            ? '<div style="display:flex;flex-direction:column;gap:4px;' + _fcCursor + '"' + _fcOnclick + ' title="Click to set/override most-recent color">' +
                  '<span style="color:#888;font-weight:700;font-size:10px;letter-spacing:0.6px;text-transform:uppercase;">Most Recent</span>' +
                  '<span style="display:flex;align-items:center;gap:8px;">' +
                      '<span style="display:inline-block;width:24px;height:24px;border-radius:5px;background:' + _fcSwatchBg + ';border:1px solid ' + _fcSwatchBorder + ';' + _fcSwatchStyle + '"></span>' +
                      _fcLabel +
                      (_fcSourceHtml ? '<span style="margin-left:4px;">' + _fcSourceHtml + '</span>' : '') +
                  '</span>' +
              '</div>'
            : '';
        // Always render the team-info container when filtered, so the color block
        // is reachable even on teams without draft-info data.
        if (_fcPlayer || (tInfo && (tInfo.pool || (tInfo.picks && tInfo.picks.length)))) {{
            const picks = ((tInfo && tInfo.picks) || []).slice(0, 5).join(', ');
            hiddenBar += '<div style="background:white;border:1px solid #e0e0e0;border-radius:8px;padding:16px 22px;margin-bottom:12px;display:flex;flex-wrap:wrap;gap:36px;align-items:center;box-shadow:0 1px 3px rgba(0,0,0,0.04);">' +
                '<div style="display:flex;flex-direction:column;gap:2px;">' +
                    '<span style="color:#888;font-weight:700;font-size:10px;letter-spacing:0.6px;text-transform:uppercase;">2026 Draft</span>' +
                    '<span style="color:#000;font-weight:800;font-size:20px;letter-spacing:0.3px;">' + _filterTeam + '</span>' +
                '</div>' +
                (tInfo && tInfo.pool ? '<div style="display:flex;flex-direction:column;gap:2px;">' +
                    '<span style="color:#888;font-weight:700;font-size:10px;letter-spacing:0.6px;text-transform:uppercase;">Bonus Pool</span>' +
                    '<span style="color:' + poolTextColor(tInfo.pool) + ';font-weight:800;font-size:22px;letter-spacing:0.3px;">' + fmtPool(tInfo.pool) + '</span>' +
                '</div>' : '') +
                (picks ? '<div style="display:flex;flex-direction:column;gap:2px;">' +
                    '<span style="color:#888;font-weight:700;font-size:10px;letter-spacing:0.6px;text-transform:uppercase;">First Picks</span>' +
                    '<span style="color:#222;font-weight:700;font-size:18px;letter-spacing:0.4px;">' + picks + '</span>' +
                '</div>' : '') +
                colorBlock +
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
        // PDW badge attaches to the specific record whose source message triggered the
        // workout flag (r.workout), not to every record for the (player, team) pair.
        const wBadge = !excluded && r.workout ? '<span class="workout-badge">PDW</span>' : '';
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
    const ed = document.getElementById('editsView');
    const dc = document.getElementById('draftCardView');
    mx.style.display = 'none'; dt.style.display = 'none'; cl.style.display = 'none';
    if (ed) ed.style.display = 'none';
    if (dc) dc.style.display = 'none';
    // Top-right matrix-only "+ Add Entry" button: hide outside the matrix view so the
    // detail-view header's pre-filled "+ Add Entry" is the only one visible.
    const matrixAdd = document.getElementById('matrixAddEntryBtn');
    if (matrixAdd) matrixAdd.style.display = (view === 'matrix') ? '' : 'none';
    // Date-window toggle only affects matrix + detail; hide it elsewhere.
    const dwCtl = document.getElementById('dateWindowCtl');
    if (dwCtl) dwCtl.style.display = (view === 'matrix' || view === 'detail') ? 'flex' : 'none';
    if (view === 'matrix') {{
        mx.style.display = 'block';
        document.querySelectorAll('.nav-tab')[0].classList.add('active');
    }} else if (view === 'draftcard') {{
        dc.style.display = 'block';
        document.querySelectorAll('.nav-tab')[1].classList.add('active');
        dcShow();
    }} else if (view === 'detail') {{
        dt.style.display = 'block';
        document.querySelectorAll('.nav-tab')[2].classList.add('active');
    }} else if (view === 'calendar') {{
        // Calendar has no nav tab now (hidden), but stays reachable via internal
        // links (e.g. workout chips). Don't set a nav-tab active — none matches.
        cl.style.display = 'block';
        if (!window._calInitialized) {{ initCalendar(); }}
    }} else if (view === 'edits') {{
        ed.style.display = 'block';
        document.querySelectorAll('.nav-tab')[3].classList.add('active');
        renderEdits();
    }}
}}

function _editsEsc(s) {{
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

async function renderEdits() {{
    // Manual calendar events live in /api/calendar-events. Lazy-load if the
    // calendar tab hasn't been opened yet so this view doesn't depend on init order.
    if (!window._calInitialized) {{
        try {{ _calEvents = await _calApi('GET', null) || {{}}; }}
        catch(e) {{ _calEvents = _calEvents || {{}}; }}
    }}

    // Combine every kind of manual change into one chronological list, sorted
    // by edit timestamp (most recent first). Items missing a timestamp (older
    // overrides written before timestamp tracking was added) sort last.
    const rows = [];

    RECORDS.filter(r => r.is_manual).forEach(r => {{
        rows.push({{
            edited_at: r.updated_at || r.created_at || '',
            ref_date: r.date || '',
            type: 'Manual Record',
            player: r.player || '',
            team: r.team || '',
            details: 'score=' + r.score
                + (r.color ? ', color=' + r.color : '')
                + (r.workout ? ', PDW' : '')
                + (r.combine ? ', Combine' : '')
                + ((r.full_text || r.note) ? ' — ' + (r.full_text || r.note).slice(0, 200) : ''),
        }});
    }});

    Object.keys(scoreOverrides).forEach(k => {{
        const v = scoreOverrides[k];
        const ts = scoreOverridesMeta[k] || '';
        if (k.startsWith('cb|')) {{
            const p = k.substring(3).split('|');
            if (p.length !== 2) return;
            rows.push({{ edited_at: ts, ref_date: '', type: 'Combine Flag', player: p[0], team: p[1], details: v ? 'On' : 'Off' }});
        }} else if (k.startsWith('w|')) {{
            const p = k.substring(2).split('|');
            if (p.length !== 2) return;
            rows.push({{ edited_at: ts, ref_date: '', type: 'PDW Flag', player: p[0], team: p[1], details: v ? 'On' : 'Off' }});
        }} else if (k.startsWith('t|')) {{
            const p = k.substring(2).split('|');
            if (p.length !== 3) return;
            rows.push({{ edited_at: ts, ref_date: p[2], type: 'Tier Points', player: p[0], team: p[1], details: 'points=' + v }});
        }} else if (k.startsWith('c|')) {{
            const p = k.substring(2).split('|');
            if (p.length !== 2) return;
            const cnote = scoreOverridesNotes[k] || '';
            rows.push({{ edited_at: ts, ref_date: '', type: 'Most-Recent Color', player: p[0], team: p[1], details: (v || '(cleared)') + (cnote ? ' \\u2014 ' + cnote : ''), _color: v || null }});
        }} else if (k.startsWith('mt|')) {{
            const p = k.substring(3).split('|');
            if (p.length !== 3) return;
            rows.push({{ edited_at: ts, ref_date: p[2], type: 'Team Reassign', player: p[0], team: p[1], details: 'reassigned to ' + v }});
        }} else if (k.startsWith('pk|')) {{
            const p = k.substring(3).split('|');
            if (p.length !== 2) return;
            const picks = Array.isArray(v) ? v : [];
            rows.push({{ edited_at: ts, ref_date: '', type: 'Picks In Play', player: p[0], team: p[1], details: picks.length ? ('#' + picks.join(', #')) : '(none)' }});
        }} else {{
            const p = k.split('|');
            if (p.length !== 3) return;
            rows.push({{ edited_at: ts, ref_date: p[2], type: 'Score', player: p[0], team: p[1], details: 'score=' + v }});
        }}
    }});

    Object.values(_calEvents || {{}}).forEach(ev => {{
        const bits = [];
        if (ev.team) bits.push(ev.team);
        if (ev.type) bits.push(ev.type);
        if (ev.time) bits.push(ev.time);
        if (ev.location) bits.push(ev.location);
        if (ev.confirmed) bits.push('confirmed');
        rows.push({{
            edited_at: ev.updated_at || ev.created_at || '',
            ref_date: ev.date || '',
            type: 'Calendar Event',
            player: ev.player || '',
            team: ev.team || '',
            details: bits.join(' \\u00b7 '),
        }});
    }});

    // Sort by edited_at desc, missing timestamps last.
    rows.sort((a, b) => {{
        if (!a.edited_at && b.edited_at) return 1;
        if (a.edited_at && !b.edited_at) return -1;
        if (a.edited_at !== b.edited_at) return b.edited_at.localeCompare(a.edited_at);
        // Within the same (or no) timestamp, fall back to the change's reference date desc.
        if (a.ref_date !== b.ref_date) return (b.ref_date || '').localeCompare(a.ref_date || '');
        return (a.player || '').localeCompare(b.player || '');
    }});

    function fmtTs(iso) {{
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        // Local time, e.g. "Apr 28, 2026 2:35 PM".
        const opts = {{ year:'numeric', month:'short', day:'numeric', hour:'numeric', minute:'2-digit' }};
        return d.toLocaleString(undefined, opts);
    }}

    let html = '';
    if (!rows.length) {{
        html = '<div style="color:#999;font-size:13px;font-style:italic;padding:18px;background:white;border:1px solid #e0e0e0;border-radius:6px;">No manual edits or additions yet.</div>';
    }} else {{
        html += '<table class="edits-tbl"><thead><tr>' +
            '<th>Edited</th><th>Type</th><th>Player</th><th>Team</th><th>Ref. Date</th><th>Details</th>' +
            '</tr></thead><tbody>';
        rows.forEach(r => {{
            const sw = (r.type === 'Most-Recent Color' && r._color)
                ? '<span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:' + (COLOR_BG[r._color] || '#ccc') + ';margin-right:6px;vertical-align:-2px;"></span>'
                : '';
            const editedDisp = r.edited_at ? fmtTs(r.edited_at) : '';
            html += '<tr>' +
                '<td style="white-space:nowrap;color:' + (r.edited_at ? '#222' : '#999') + ';">' + _editsEsc(editedDisp || '\\u2014') + '</td>' +
                '<td style="white-space:nowrap;font-weight:600;">' + _editsEsc(r.type) + '</td>' +
                '<td style="white-space:nowrap;">' + _editsEsc(r.player) + '</td>' +
                '<td style="white-space:nowrap;">' + _editsEsc(r.team) + '</td>' +
                '<td style="white-space:nowrap;color:' + (r.ref_date ? '#222' : '#999') + ';">' + _editsEsc(r.ref_date || '\\u2014') + '</td>' +
                '<td style="max-width:520px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + sw + _editsEsc(r.details || '') + '</td>' +
                '</tr>';
        }});
        html += '</tbody></table>';
    }}

    document.getElementById('editsCount').textContent = rows.length + ' total change' + (rows.length === 1 ? '' : 's');
    document.getElementById('editsBody').innerHTML = html;
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
var _calSelectedTypes = null;     // Set<'workout'|'game'|'other'> — null = uninitialized
var _calMonthEnd = null;          // Date|null. null = single-month mode (uses _calMonth only).
                                  // Set = multi-month mode showing _calMonth..._calMonthEnd inclusive.

const _CAL_PLAYERS_LS_KEY = 'ti_cal_selected_players_v1';
const _CAL_TYPES_LS_KEY = 'ti_cal_selected_types_v1';
const _CAL_PDF_COMBINE_LS_KEY = 'ti_cal_pdf_include_combine_v1';
const _CAL_TYPES_ALL = ['workout','game','other'];
const _CAL_TYPE_LABELS = {{ workout: 'Workouts', game: 'Games', other: 'Other' }};
const MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

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
    ['calPlayerDropdown','calTypeDropdown','calRangeDropdown'].forEach(function(id) {{
        const dd = document.getElementById(id);
        if (!dd || !dd.classList.contains('open')) return;
        if (!dd.contains(e.target)) dd.classList.remove('open');
    }});
}});

// --- Type multi-select ---
function _calLoadTypeSelection() {{
    try {{
        const raw = localStorage.getItem(_CAL_TYPES_LS_KEY);
        if (raw) {{
            const saved = JSON.parse(raw);
            if (Array.isArray(saved)) {{
                const known = new Set(_CAL_TYPES_ALL);
                const restored = new Set(saved.filter(t => known.has(t)));
                if (restored.size > 0) return restored;
            }}
        }}
    }} catch(e) {{ /* ignore */ }}
    return new Set(_CAL_TYPES_ALL);
}}
function _calSaveTypeSelection() {{
    try {{ localStorage.setItem(_CAL_TYPES_LS_KEY, JSON.stringify([..._calSelectedTypes])); }} catch(e) {{}}
}}
function _calEnsureTypeSelection() {{
    if (_calSelectedTypes === null) _calSelectedTypes = _calLoadTypeSelection();
}}
// PDF "Add Combine" toggle — controls whether the MLB Combine row is appended
// to each player's PDW Invites table in the exported PDF. Default ON.
function _pdfLoadCombineToggle() {{
    try {{
        const raw = localStorage.getItem(_CAL_PDF_COMBINE_LS_KEY);
        if (raw === '0') return false;
        if (raw === '1') return true;
    }} catch(e) {{ /* ignore */ }}
    return true;
}}
function _pdfSaveCombineToggle(on) {{
    try {{ localStorage.setItem(_CAL_PDF_COMBINE_LS_KEY, on ? '1' : '0'); }} catch(e) {{}}
}}
function _pdfSyncCombineCheckbox() {{
    const cb = document.getElementById('pdfIncludeCombine');
    if (cb) cb.checked = _pdfLoadCombineToggle();
}}
function _calRenderTypeChips() {{
    const host = document.getElementById('calTypeChips');
    if (!host) return;
    let html = '';
    _CAL_TYPES_ALL.forEach(t => {{
        const on = _calSelectedTypes.has(t);
        html += '<label class="cal-multi-item" onclick="event.stopPropagation()">'
             +  '<input type="checkbox" ' + (on ? 'checked' : '') + ' onchange="calToggleType(\\'' + t + '\\')">'
             +  '<span>' + _CAL_TYPE_LABELS[t] + '</span>'
             +  '</label>';
    }});
    host.innerHTML = html;
    _calUpdateTypeBtnLabel();
}}
function _calUpdateTypeBtnLabel() {{
    const el = document.getElementById('calTypeBtnLabel');
    if (!el) return;
    const sel = _calSelectedTypes ? _calSelectedTypes.size : 0;
    const total = _CAL_TYPES_ALL.length;
    let label;
    if (sel === 0) label = 'None';
    else if (sel === total) label = 'All';
    else if (sel === 1) label = _CAL_TYPE_LABELS[[..._calSelectedTypes][0]];
    else label = sel + ' selected';
    el.textContent = label;
}}
function toggleCalTypePanel() {{
    const el = document.getElementById('calTypeDropdown');
    if (el) el.classList.toggle('open');
}}
function calToggleType(t) {{
    if (_calSelectedTypes.has(t)) _calSelectedTypes.delete(t);
    else _calSelectedTypes.add(t);
    _calSaveTypeSelection();
    _calRenderTypeChips();
    renderCalendar();
}}
function calSelectAllTypes() {{
    _calSelectedTypes = new Set(_CAL_TYPES_ALL);
    _calSaveTypeSelection();
    _calRenderTypeChips();
    renderCalendar();
}}
function calSelectNoTypes() {{
    _calSelectedTypes = new Set();
    _calSaveTypeSelection();
    _calRenderTypeChips();
    renderCalendar();
}}
// Bucket an event into one of the three Type filter slots. "other" catches
// anything that isn't a workout or a game (legacy playoff/travel/other events).
function _calEventTypeBucket(ev) {{
    if (ev.type === 'workout' || ev.type === 'game') return ev.type;
    return 'other';
}}

// --- Month-range picker ---
// _calMonth is always the start of the range. _calMonthEnd === null means single-month mode.
function _calMonthsInRange() {{
    const out = [];
    const start = new Date(_calMonth.getFullYear(), _calMonth.getMonth(), 1);
    const end = _calMonthEnd ? new Date(_calMonthEnd.getFullYear(), _calMonthEnd.getMonth(), 1) : start;
    let d = new Date(start);
    while (d <= end) {{
        out.push(new Date(d.getFullYear(), d.getMonth(), 1));
        d = new Date(d.getFullYear(), d.getMonth()+1, 1);
    }}
    return out;
}}
function _fmtRangeLabel() {{
    if (!_calMonthEnd) return _fmtMonth(_calMonth);
    const sM = _calMonth.getMonth(), sY = _calMonth.getFullYear();
    const eM = _calMonthEnd.getMonth(), eY = _calMonthEnd.getFullYear();
    if (sY === eY) return MONTH_SHORT[sM] + ' \\u2013 ' + MONTH_SHORT[eM] + ' ' + sY;
    return MONTH_SHORT[sM] + ' ' + sY + ' \\u2013 ' + MONTH_SHORT[eM] + ' ' + eY;
}}
function _calRangeOptions() {{
    // Show every month between the earliest and latest event in the dataset,
    // expanded to also cover at least 6 months before/after today. Ensures
    // the picker offers a useful span even when there are no events yet.
    const ev = _getMergedEvents();
    const today = new Date();
    let minY = today.getFullYear(), minM = today.getMonth() - 6;
    let maxY = today.getFullYear(), maxM = today.getMonth() + 6;
    while (minM < 0) {{ minM += 12; minY -= 1; }}
    while (maxM > 11) {{ maxM -= 12; maxY += 1; }}
    let minIso = minY + '-' + String(minM+1).padStart(2,'0');
    let maxIso = maxY + '-' + String(maxM+1).padStart(2,'0');
    ev.forEach(e => {{
        if (!e.date) return;
        const yyyymm = e.date.slice(0, 7);
        if (yyyymm < minIso) minIso = yyyymm;
        if (yyyymm > maxIso) maxIso = yyyymm;
    }});
    const out = [];
    let [y, m] = minIso.split('-').map(s => parseInt(s, 10));
    m -= 1;
    const endParts = maxIso.split('-').map(s => parseInt(s, 10));
    const endY = endParts[0], endM = endParts[1] - 1;
    while (y < endY || (y === endY && m <= endM)) {{
        out.push({{ y: y, m: m, val: y + '-' + String(m+1).padStart(2,'0'), label: MONTH_SHORT[m] + ' ' + y }});
        m += 1; if (m > 11) {{ m = 0; y += 1; }}
    }}
    return out;
}}
function _calPopulateRangeSelects() {{
    const fromSel = document.getElementById('calRangeFrom');
    const toSel = document.getElementById('calRangeTo');
    if (!fromSel || !toSel) return;
    const opts = _calRangeOptions();
    const startVal = _calMonth.getFullYear() + '-' + String(_calMonth.getMonth()+1).padStart(2,'0');
    const endVal = (_calMonthEnd || _calMonth).getFullYear() + '-'
        + String((_calMonthEnd || _calMonth).getMonth()+1).padStart(2,'0');
    const buildHtml = (selectedVal) => opts.map(o =>
        '<option value="' + o.val + '"' + (o.val === selectedVal ? ' selected' : '') + '>' + o.label + '</option>'
    ).join('');
    fromSel.innerHTML = buildHtml(startVal);
    toSel.innerHTML = buildHtml(endVal);
}}
function toggleCalRangePanel() {{
    const el = document.getElementById('calRangeDropdown');
    if (!el) return;
    _calPopulateRangeSelects();
    el.classList.toggle('open');
}}
function _calCloseRangePanel() {{
    const el = document.getElementById('calRangeDropdown');
    if (el) el.classList.remove('open');
}}
function calApplyMonthRange() {{
    const fromSel = document.getElementById('calRangeFrom');
    const toSel = document.getElementById('calRangeTo');
    if (!fromSel || !toSel) return;
    const [fy, fm] = fromSel.value.split('-').map(s => parseInt(s, 10));
    let [ty, tm] = toSel.value.split('-').map(s => parseInt(s, 10));
    let start = new Date(fy, fm-1, 1);
    let end = new Date(ty, tm-1, 1);
    if (end < start) {{ const tmp = start; start = end; end = tmp; }}
    _calMonth = start;
    _calMonthEnd = (start.getTime() === end.getTime()) ? null : end;
    _calCloseRangePanel();
    renderCalendar();
}}
function calClearMonthRange() {{
    _calMonthEnd = null;
    _calCloseRangePanel();
    renderCalendar();
}}

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

function _buildPdfGridHtml(year, month, eventsByDate, includeCombine) {{
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
        const isCombine = !!includeCombine && (iso >= '2026-06-21' && iso <= '2026-06-26');
        const bg = isDraft ? '#fff5e0' : (isCombine ? '#e8f0fb' : 'white');
        html += '<div style="background:' + bg + ';min-height:90px;padding:4px 5px;vertical-align:top;">';
        html += '<div style="font-size:10px;color:#888;font-weight:700;margin-bottom:3px;">' + dayNum
            + (isDraft ? ' <span style="font-size:8px;padding:1px 4px;background:#ff2a22;color:white;border-radius:2px;font-weight:700;">DRAFT</span>' : '')
            + (isCombine ? ' <span style="font-size:8px;padding:1px 4px;background:#1e6fbb;color:white;border-radius:2px;font-weight:700;">COMBINE</span>' : '')
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

// MLB Combine canonical info — used to append a static PDW row when the
// active range overlaps the combine window. Edit here to change everywhere.
const COMBINE_INFO = {{ startIso: '2026-06-21', endIso: '2026-06-26', dateLabel: '6/21\\u20136/26', location: 'Phoenix, AZ' }};

// Compact date-range label for a list of ISO dates:
//   1 date     -> "5/18"
//   2 adjacent -> "5/17 or 5/18"
//   3+ adjacent in same month -> "5/27\\u201329"   (en-dash + bare last day)
//   3+ adjacent across months -> "5/30\\u20136/2"
//   Multiple non-adjacent groups joined with " or "
function _fmtPdwDateLabel(isoList) {{
    if (!isoList || !isoList.length) return '';
    const uniq = [...new Set(isoList)].sort();
    const groups = [[uniq[0]]];
    for (let i = 1; i < uniq.length; i++) {{
        const prev = new Date(uniq[i-1] + 'T00:00:00');
        const next = new Date(uniq[i] + 'T00:00:00');
        const diffDays = Math.round((next - prev) / 86400000);
        if (diffDays === 1) groups[groups.length-1].push(uniq[i]);
        else groups.push([uniq[i]]);
    }}
    const fmtMD = (iso) => {{
        const d = new Date(iso + 'T00:00:00');
        return (d.getMonth()+1) + '/' + d.getDate();
    }};
    const fmtGroup = (g) => {{
        if (g.length === 1) return fmtMD(g[0]);
        if (g.length === 2) return fmtMD(g[0]) + ' or ' + fmtMD(g[1]);
        const firstM = g[0].split('-')[1];
        const lastM = g[g.length-1].split('-')[1];
        if (firstM === lastM) {{
            // same month: "5/27–29" (drop the duplicate month on the right side)
            const lastDay = new Date(g[g.length-1] + 'T00:00:00').getDate();
            return fmtMD(g[0]) + '\\u2013' + lastDay;
        }}
        return fmtMD(g[0]) + '\\u2013' + fmtMD(g[g.length-1]);
    }};
    return groups.map(fmtGroup).join(' or ');
}}

// Build PDW-only groups for a single player, scoped to the active month range.
// Groups are bucketed by team; each entry within a group is one workout date
// with its (possibly empty) location. The agenda renderer prints the team
// once per group on the first row and leaves it blank on follow-ups.
// Walks _getMergedEvents() (not RECORDS directly) so manual location/date
// edits made in the calendar UI are reflected in the PDF summary.
function _gatherPdwGroupsForPlayer(player, monthKeySet) {{
    const byTeam = {{}};
    _getMergedEvents().forEach(ev => {{
        if (ev.player !== player) return;
        if (ev.type !== 'workout') return;
        if (!ev.team) return;
        if (!ev.date || !monthKeySet.has(ev.date.slice(0,7))) return;
        if (!byTeam[ev.team]) byTeam[ev.team] = [];
        byTeam[ev.team].push({{ date: ev.date, location: ev.location || '' }});
    }});
    const groups = [];
    Object.keys(byTeam).forEach(team => {{
        const entries = byTeam[team].slice().sort((a,b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
        if (!entries.length) return;
        const di = TEAM_DRAFT[team] || {{}};
        // Only the first two picks per the user's preference — keeps the cell
        // compact in the half-page block. Farm rank rendered as "#N".
        const firstTwoPicks = (di.picks || []).slice(0, 2).join(', ');
        const farm = (di.farm_rank != null) ? ('#' + di.farm_rank) : '';
        groups.push({{
            team: team,
            entries: entries,
            firstDate: entries[0].date,
            pool: di.pool ? fmtPool(di.pool) : '',
            picks: firstTwoPicks,
            farm: farm,
        }});
    }});
    groups.sort((a,b) => a.firstDate < b.firstDate ? -1 : a.firstDate > b.firstDate ? 1 : 0);
    return groups;
}}

// PDW Invites section for the PDF. One block per player; 3-col table inside
// (Team / Date(s) / Location). MLB Combine appended as a static row when the
// active range overlaps the combine window.
function _buildPdfAgendaHtml(players, monthKeySet, includeCombine) {{
    const combineOverlap = !!includeCombine && (monthKeySet.has(COMBINE_INFO.startIso.slice(0,7))
        || monthKeySet.has(COMBINE_INFO.endIso.slice(0,7)));
    const HDR_STYLE = 'font-size:9px;font-weight:800;color:#888;letter-spacing:0.6px;'
        + 'text-transform:uppercase;border-bottom:1px solid #ddd;padding-bottom:2px;';
    const SUB_HEADER_STYLE = 'font-size:11px;font-weight:800;color:#000;'
        + 'letter-spacing:0.4px;border-bottom:1.5px solid #000;padding-bottom:2px;margin-bottom:5px;'
        + 'text-align:center;';
    // Single-column layout of full-width player blocks. Each block splits
    // internally into a left half (auto-generated PDW Invites from Slack) and
    // a right half (SV recommendation hand-curated in
    // data/recommended_schedule_2026.json). The whole section starts on a
    // fresh page (page-break-before:always); page-break-after on the section
    // title keeps it glued to the first player block.
    let html = '<div style="margin-top:0;page-break-before:always;break-before:page;">'
             + '<div style="font-size:14px;font-weight:800;color:#000;border-bottom:2px solid #ff2a22;padding-bottom:3px;margin-bottom:6px;letter-spacing:0.3px;page-break-after:avoid;break-after:avoid;">Pre-Draft Workout Invites</div>'
             + '<div style="display:flex;flex-direction:column;gap:10px;page-break-before:avoid;break-before:avoid;">';
    players.forEach(p => {{
        const groups = _gatherPdwGroupsForPlayer(p, monthKeySet);
        const totalEntries = groups.reduce((sum, g) => sum + g.entries.length, 0);
        // No break-inside:avoid here — for players with many invites the block
        // is taller than a single landscape page, which (with CSS grid inside)
        // produced a phantom empty wrapper on one page and the actual content
        // on the next. Letting it paginate naturally fixes that; the player
        // header still re-anchors visually because of the border and bold name.
        html += '<div style="border:1px solid #ddd;border-radius:4px;padding:8px 12px;">';
        html += '<div style="font-size:13px;font-weight:800;color:#000;margin-bottom:6px;border-bottom:1px solid #eee;padding-bottom:3px;letter-spacing:0.2px;page-break-after:avoid;break-after:avoid;">' + _escHtml(p) + '</div>';
        // Internal split: flexbox instead of CSS grid because Chrome/Edge
        // print pagination handles flex containers more predictably across
        // page breaks. align-items:flex-start so the two columns top-align
        // even when one is much taller than the other.
        html += '<div style="display:flex;gap:18px;align-items:flex-start;">';
        // ----- LEFT: auto-generated PDW Invites -----
        // flex:1 1 0 + min-width:0 makes both columns share width equally and
        // lets long cells (e.g. "Birmingham, AL") shrink rather than overflow.
        html += '<div style="flex:1 1 0;min-width:0;">';
        html += '<div style="' + SUB_HEADER_STYLE + '">Invites Received</div>';
        if (!totalEntries && !combineOverlap) {{
            html += '<div style="font-size:10px;color:#999;font-style:italic;">No PDW invites in this range.</div>';
        }} else {{
            // HTML table with one <tbody> per team — page-break-inside:avoid
            // on each tbody keeps a team's rows from being split across pages.
            // <thead> with display:table-header-group lets the column headers
            // repeat at the top of each page if the table spans multiple pages.
            // Very tight vertical packing so high-volume players (Trevor's
            // ~40 invite rows across 16 teams) still fit on a single landscape
            // page. Font shrinks to 8.5px to recover an extra ~30% of vertical
            // space; readability is still fine in a printed PDF.
            // Mason Eckelman: hide the Picks column entirely and bump font.
            const hidePicks = (p === 'Mason Eckelman');
            // Trevor-volume players (~50+ rows across 20+ teams) overflow the
            // page at the default 8.5px / 1.55 line-height. Tighten line-height
            // and inter-team spacers when row count crosses the threshold.
            const totalRows = groups.reduce((s, g) => s + g.entries.length, 0) + (combineOverlap ? 1 : 0);
            const ultraTight = !hidePicks && totalRows >= 45;
            const fontPx = hidePicks ? '12px' : '8.5px';
            const lineHt = ultraTight ? '1.3' : '1.55';
            const spacerHt = ultraTight ? '1px' : '3px';
            const colspanAll = hidePicks ? 5 : 6;
            const TD = 'padding:0 4px 0 4px;vertical-align:top;text-align:center;font-size:' + fontPx + ';line-height:' + lineHt + ';';
            const TH = 'padding:1px 4px 2px 4px;vertical-align:bottom;text-align:center;font-size:' + fontPx + ';font-weight:800;color:#888;letter-spacing:0.6px;text-transform:uppercase;border-bottom:1px solid #ddd;';
            html += '<table style="border-collapse:collapse;width:100%;table-layout:fixed;">';
            html += '<colgroup>'
                 +    '<col style="width:38px;">'
                 +    '<col style="width:50px;">'
                 +    (hidePicks ? '' : '<col style="width:58px;">')
                 +    '<col style="width:36px;">'
                 +    '<col style="width:44px;">'
                 +    '<col>'
                 +  '</colgroup>';
            html += '<thead style="display:table-header-group;"><tr>'
                 +    '<th style="' + TH + '">Team</th>'
                 +    '<th style="' + TH + '">Pool</th>'
                 +    (hidePicks ? '' : '<th style="' + TH + '">Picks</th>')
                 +    '<th style="' + TH + '">Farm</th>'
                 +    '<th style="' + TH + '">Date</th>'
                 +    '<th style="' + TH + '">Location</th>'
                 +  '</tr></thead>';
            groups.forEach((g, gi) => {{
                html += '<tbody style="page-break-inside:avoid;break-inside:avoid;">';
                // Subtle spacer row above every team after the first.
                if (gi > 0) html += '<tr><td colspan="' + colspanAll + '" style="height:' + spacerHt + ';padding:0;"></td></tr>';
                g.entries.forEach((entry, i) => {{
                    const teamCell  = (i === 0) ? _escHtml(g.team)  : '';
                    const poolCell  = (i === 0) ? _escHtml(g.pool)  : '';
                    const picksCell = (i === 0) ? _escHtml(g.picks) : '';
                    const farmCell  = (i === 0) ? _escHtml(g.farm)  : '';
                    const d = new Date(entry.date + 'T00:00:00');
                    const dateStr = (d.getMonth()+1) + '/' + d.getDate();
                    html += '<tr>'
                         +    '<td style="' + TD + 'font-weight:800;color:#000;">' + teamCell + '</td>'
                         +    '<td style="' + TD + 'color:#444;">' + poolCell + '</td>'
                         +    (hidePicks ? '' : '<td style="' + TD + 'color:#444;">' + picksCell + '</td>')
                         +    '<td style="' + TD + 'color:#444;font-weight:700;">' + farmCell + '</td>'
                         +    '<td style="' + TD + 'color:#222;">' + dateStr + '</td>'
                         +    '<td style="' + TD + 'color:#555;">' + _escHtml(entry.location) + '</td>'
                         +  '</tr>';
                }});
                html += '</tbody>';
            }});
            if (combineOverlap) {{
                html += '<tbody style="page-break-inside:avoid;break-inside:avoid;">';
                if (groups.length > 0) html += '<tr><td colspan="' + colspanAll + '" style="height:' + spacerHt + ';padding:0;"></td></tr>';
                html += '<tr>'
                     +    '<td style="' + TD + 'font-weight:800;color:#000;">MLB Combine</td>'
                     +    '<td style="' + TD + '"></td>'
                     +    (hidePicks ? '' : '<td style="' + TD + '"></td>')
                     +    '<td style="' + TD + '"></td>'
                     +    '<td style="' + TD + 'color:#222;">' + COMBINE_INFO.dateLabel + '</td>'
                     +    '<td style="' + TD + 'color:#555;">' + _escHtml(COMBINE_INFO.location) + '</td>'
                     +  '</tr>';
                html += '</tbody>';
            }}
            html += '</table>';
        }}
        html += '</div>';   // close LEFT
        // ----- RIGHT: SV recommended schedule -----
        html += '<div style="flex:1 1 0;min-width:0;">';
        html += '<div style="' + SUB_HEADER_STYLE + '">Our Recommendation</div>';
        html += _buildPdwRecommendationHtml(p);
        html += '</div>';   // close RIGHT
        html += '</div>';   // close internal 2-col split
        html += '</div>';   // close player block
    }});
    html += '</div></div>';
    return html;
}}

// SV's tentative recommended workout schedule for a player. Pulls from the
// hand-curated RECOMMENDED_SCHEDULE map; picks are looked up from TEAM_DRAFT
// and capped at 2 (first + second pick, regardless of round).
function _buildPdwRecommendationHtml(player) {{
    const rec = RECOMMENDED_SCHEDULE[player];
    if (!rec || !rec.tiers || !rec.tiers.length) {{
        return '<div style="font-size:10px;color:#999;font-style:italic;">No recommendation entered yet.</div>';
    }}
    let html = '';
    rec.tiers.forEach((tier, ti) => {{
        // Wrap each tier (label + entries) in a break-inside:avoid block so a
        // tier never splits across pages.
        html += '<div style="page-break-inside:avoid;break-inside:avoid;'
             + (ti > 0 ? 'margin-top:6px;' : '') + '">';
        // Empty string label -> render no header (clean tier-gap-only separator).
        // Missing label falls back to "Tier N" for legacy entries.
        const _label = (tier.label === undefined || tier.label === null) ? ('Tier ' + (ti + 1)) : tier.label;
        if (_label !== '') {{
            html += '<div style="font-size:12px;font-weight:800;color:#ff2a22;letter-spacing:0.5px;text-transform:uppercase;margin-bottom:3px;text-align:center;">'
                 + _escHtml(_label) + '</div>';
        }}
        (tier.entries || []).forEach(entry => {{
            const team = (entry.team || '').toUpperCase();
            const di = TEAM_DRAFT[team] || {{}};
            // Mason Eckelman: picks suppressed at his request.
            const earlyPicks = (player === 'Mason Eckelman')
                ? ''
                : (di.picks || []).slice(0, 2).join(', ');
            // Empty team + no schedule -> blank spacer row (visual gap between entries).
            if (!team && !entry.schedule) {{
                html += '<div style="font-size:12px;line-height:1.4;padding:1px 0;">&nbsp;</div>';
                return;
            }}
            html += '<div style="font-size:12px;color:#222;line-height:1.4;padding:1px 0;text-align:center;">'
                 +    '<span style="font-weight:800;color:#000;">' + _escHtml(team) + '</span>'
                 +    (earlyPicks ? ' \\u00b7 <span style="color:#555;">' + earlyPicks + '</span>' : '')
                 +    (entry.schedule ? ' \\u00b7 ' + _escHtml(entry.schedule) : '')
                 + '</div>';
        }});
        html += '</div>';
    }});
    return html;
}}

function exportCalendarPDF() {{
    // Switched from html2canvas/html2pdf to the browser's native print-to-PDF
    // pipeline. html2canvas kept producing blank canvases regardless of positioning
    // tricks; the browser's own print engine handles layout + print-safe rendering
    // reliably. UX cost: the user clicks "Save as PDF" in the print dialog (1 extra step).
    _calEnsureSelection();
    _calEnsureTypeSelection();
    const players = [..._calSelectedPlayers].sort();
    if (!players.length) {{
        showToast('Select at least one player first.', false);
        return;
    }}

    const merged = _getMergedEvents().filter(ev => {{
        if (!_calSelectedPlayers.has(ev.player)) return false;
        if (!_calSelectedTypes.has(_calEventTypeBucket(ev))) return false;
        return true;
    }});
    const byDate = {{}};
    merged.forEach(ev => {{ (byDate[ev.date] = byDate[ev.date] || []).push(ev); }});

    const months = _calMonthsInRange();
    const isMulti = months.length > 1;
    const monthKeys = new Set(months.map(d => d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0')));
    const rangeLabel = isMulti ? _fmtRangeLabel() : (MONTH_NAMES[months[0].getMonth()] + ' ' + months[0].getFullYear());
    const filenameRange = isMulti
        ? (MONTH_SHORT[months[0].getMonth()] + months[0].getFullYear()
            + '-' + MONTH_SHORT[months[months.length-1].getMonth()] + months[months.length-1].getFullYear())
        : (MONTH_NAMES[months[0].getMonth()] + '-' + months[0].getFullYear());
    const nowIso = _fmtIso(new Date());
    const filename = 'SV-TeamIntel-' + filenameRange
        + (players.length <= 3 ? '-' + players.map(p => p.split(' ').pop()).join('-') : '');

    // One grid per month, each on its own page. The first month follows the
    // PDF header on page 1; every subsequent month gets a page break before it.
    // break-inside:avoid keeps a month's grid from splitting across pages.
    const includeCombine = _pdfLoadCombineToggle();
    let gridsHtml = '';
    months.forEach((m, i) => {{
        const pageBreak = i > 0 ? 'page-break-before:always;break-before:page;' : '';
        gridsHtml += '<div style="' + pageBreak + 'page-break-inside:avoid;break-inside:avoid;">';
        if (isMulti) {{
            gridsHtml += '<div style="font-size:13px;font-weight:800;color:#000;padding:0 0 6px;border-bottom:2px solid #000;margin-bottom:6px;letter-spacing:0.4px;">'
                + MONTH_NAMES[m.getMonth()] + ' ' + m.getFullYear() + '</div>';
        }}
        gridsHtml += _buildPdfGridHtml(m.getFullYear(), m.getMonth(), byDate, includeCombine);
        gridsHtml += '</div>';
    }});

    const bodyHtml =
        '<div class="pdf-header">'
      +   '<div>'
      +     '<div class="pdf-title">Stadium Ventures &middot; ' + rangeLabel + '</div>'
      +     '<div class="pdf-sub">Players: ' + _escHtml(players.join(', ')) + '</div>'
      +   '</div>'
      +   '<div class="pdf-gen">SV TeamIntel<br>Generated ' + nowIso + '</div>'
      + '</div>'
      + gridsHtml
      + _buildPdfAgendaHtml(players, monthKeys, includeCombine);

    const doc = '<!DOCTYPE html>\\n<html><head><meta charset="utf-8"><title>' + filename + '</title>'
      + '<style>'
      // @page margin: 0 suppresses the browser-added print header/footer
      // (URL, page number, filename, timestamp). We move the visual margin
      // into body padding so content doesn't touch the page edge.
      +   '@page {{ size: letter landscape; margin: 0; }}'
      +   '@media print {{ body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}'
      +   'body {{ margin: 0; padding: 16mm 12mm 14mm; font-family: Arial, sans-serif; color: #222; font-size: 10px; }}'
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
    // Range mode: shift both endpoints by the same delta so the window slides as a block.
    _calMonth = new Date(_calMonth.getFullYear(), _calMonth.getMonth()+delta, 1);
    if (_calMonthEnd) {{
        _calMonthEnd = new Date(_calMonthEnd.getFullYear(), _calMonthEnd.getMonth()+delta, 1);
    }}
    renderCalendar();
}}

function calJumpTo(which) {{
    if (which === 'today') {{
        const now = new Date();
        _calMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        _calMonthEnd = null;  // collapse back to single-month view
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
        const loc = ev.location ? ' (' + ev.location + ')' : '';
        return (ev.team || '?') + ' · ' + (ev.player || '?') + loc + (ev.tentative ? ' [T]' : '');
    }}
    if (ev.type === 'game') {{
        const opp = ev.opponent || '?';
        return (ev.player || '?') + ' vs ' + opp;
    }}
    const t = ev.title || ({{playoff:'Playoff', travel:'Travel', other:'Event'}}[ev.type] || 'Event');
    return (ev.player || '?') + ' · ' + t;
}}

function renderCalendar() {{
    _calEnsureSelection();
    _calEnsureTypeSelection();
    _calRenderPlayerChips();
    _calRenderTypeChips();

    const months = _calMonthsInRange();   // [Date, Date, ...] each at day 1
    const isMulti = months.length > 1;
    const monthKeys = new Set(months.map(d => d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0')));

    document.getElementById('calMonthLabel').textContent = _fmtRangeLabel();

    const merged = _getMergedEvents().filter(ev => {{
        if (!_calSelectedPlayers.has(ev.player)) return false;
        if (!_calSelectedTypes.has(_calEventTypeBucket(ev))) return false;
        return true;
    }});
    // Reset chip dispatch table for this render.
    _calChipIndex = {{}};
    _calChipCounter = 0;
    const byDate = {{}};
    merged.forEach(ev => {{ (byDate[ev.date] = byDate[ev.date] || []).push(ev); }});

    const todayIso = _fmtIso(new Date());

    // ----- Per-month grids -----
    let html = '';
    months.forEach(monthDate => {{
        const year = monthDate.getFullYear(), month = monthDate.getMonth();
        const first = new Date(year, month, 1);
        const startDow = first.getDay();
        const daysInMonth = new Date(year, month+1, 0).getDate();
        const cells = Math.ceil((startDow + daysInMonth) / 7) * 7;

        html += '<div class="cal-month-block">';
        html += '<div class="cal-month-hdr">' + MONTH_NAMES[month] + ' ' + year + '</div>';
        html += '<div class="cal-month-grid">';
        ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d => {{
            html += '<div class="cal-dow">' + d + '</div>';
        }});
        for (let i = 0; i < cells; i++) {{
            const dayNum = i - startDow + 1;
            if (dayNum < 1 || dayNum > daysInMonth) {{
                html += '<div class="cal-cell cal-pad"></div>';
                continue;
            }}
            const d = new Date(year, month, dayNum);
            const iso = _fmtIso(d);
            const isDraft = (iso === '2026-07-11' || iso === '2026-07-12' || iso === '2026-07-13');
            const isCombine = (iso >= '2026-06-21' && iso <= '2026-06-26');
            const isToday = (iso === todayIso);
            let cls = 'cal-cell';
            if (isDraft) cls += ' cal-draft';
            if (isCombine) cls += ' cal-combine';
            if (isToday) cls += ' cal-today';
            html += '<div class="' + cls + '" data-iso="' + iso + '">';
            html += '<div class="cal-daynum">' + dayNum
                + (isDraft ? ' <span class="cal-drafttag">DRAFT</span>' : '')
                + (isCombine ? ' <span class="cal-combinetag">COMBINE</span>' : '')
                + '</div>';
            const evs = byDate[iso] || [];
            evs.forEach(ev => {{
                const color = _chipColor(ev);
                const marker = ev.auto ? '' : '*';
                const cid = 'c' + (_calChipCounter++);
                _calChipIndex[cid] = ev;
                const safeTitle = (ev.notes || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
                const isWorkout = ev.type === 'workout';
                const isConfirmed = isWorkout && !!ev.confirmed;
                let cls2 = 'cal-chip';
                let style = '';
                let prefix = '';
                if (isWorkout && !isConfirmed) {{
                    cls2 += ' workout-invite';
                    style = 'border-color:' + color + ';color:' + color + ';--chip-color:' + color + ';';
                }} else {{
                    if (isConfirmed) cls2 += ' workout-confirmed';
                    style = 'background:' + color + ';';
                    if (isConfirmed) prefix = '&#10003; ';
                }}
                if (ev.tentative) cls2 += ' tentative';
                // Bold the chip when the (player, team) connection's most-recent color is GREEN
                // (the strongest signal — not light green).
                if (isWorkout && ev.player && ev.team && getLatestColor(ev.player, ev.team) === 'green') {{
                    cls2 += ' workout-green-conn';
                }}
                html += '<div class="' + cls2 + '" style="' + style + '" ' +
                    'onclick="openEventChip(\\'' + cid + '\\')" ' +
                    'title="' + safeTitle + '">' +
                    prefix + _chipLabel(ev) + marker + '</div>';
            }});
            html += '</div>';
        }}
        html += '</div></div>';   // close cal-month-grid + cal-month-block
    }});
    const gridEl = document.getElementById('calGrid');
    gridEl.innerHTML = html;
    gridEl.classList.toggle('multi', isMulti);

    // ----- Agenda (mobile + always-visible bottom block) -----
    // Spans every month in the active range.
    const agendaDates = Object.keys(byDate).filter(d => monthKeys.has(d.slice(0,7))).sort();
    // Always surface draft days even if empty (only within the active range).
    ['2026-07-11','2026-07-12','2026-07-13'].forEach(d => {{
        if (monthKeys.has(d.slice(0,7)) && agendaDates.indexOf(d) === -1) agendaDates.push(d);
    }});
    agendaDates.sort();
    let agendaHtml = '';
    if (!agendaDates.length) {{
        agendaHtml = '<div class="agenda-empty">No events in this range.</div>';
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
            if (isMulti) agendaHtml += '<div style="font-size:9px;color:#888;font-weight:600;">' + MONTH_SHORT[d.getMonth()] + '</div>';
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
                    if (isWorkout && ev.player && ev.team && getLatestColor(ev.player, ev.team) === 'green') {{
                        cls += ' workout-green-conn';
                    }}
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

    // Legend: unique workout teams across every month in the active range.
    const activeTeams = new Set();
    merged.forEach(ev => {{
        if (monthKeys.has(ev.date.slice(0,7)) && ev.type === 'workout' && ev.team) activeTeams.add(ev.team);
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
    // Workouts with a team: surface 2026 bonus pool + first-3-round picks first;
    // an "Edit Workout" button passes through to the editable event modal.
    if (ev.type === 'workout' && ev.team && TEAM_DRAFT[ev.team]) {{
        openTeamInfoPopover(ev);
        return;
    }}
    openEventModal(ev.id || null, ev.date, ev);
}}

var _teamInfoCtx = null;

function openTeamInfoPopover(ev) {{
    _teamInfoCtx = ev;
    const tInfo = TEAM_DRAFT[ev.team] || {{}};
    const poolDisplay = tInfo.pool ? fmtPool(tInfo.pool) : '—';
    const picks = (tInfo.picks && tInfo.picks.length) ? tInfo.picks.join(', ') : '—';
    const subBits = [];
    if (ev.player) subBits.push(ev.player);
    if (ev.date) subBits.push(ev.date);
    document.getElementById('teamInfoTitle').textContent = ev.team || 'Team Info';
    document.getElementById('teamInfoSub').textContent = subBits.join(' · ');
    document.getElementById('teamInfoBody').innerHTML =
        '<div class="gd-row"><span class="gd-label">Pool</span><span class="ti-pool">' + poolDisplay + '</span></div>'
      + '<div class="gd-row"><span class="gd-label">Picks (Rds 1-3)</span><span class="ti-picks">' + picks + '</span></div>';
    // Slack button is only meaningful when an underlying record exists for this
    // (player, team). Manual calendar events without a backing Slack post show
    // the button disabled rather than vanishing it (keeps layout stable).
    const slackBtn = document.getElementById('teamInfoSlackBtn');
    const pool = _calRecordsByPlayerTeam[(ev.player || '') + '|' + (ev.team || '')] || [];
    slackBtn.disabled = pool.length === 0;
    document.getElementById('teamInfoOverlay').classList.add('open');
}}

function closeTeamInfoPopover() {{
    document.getElementById('teamInfoOverlay').classList.remove('open');
}}

function editFromTeamInfo() {{
    const ev = _teamInfoCtx;
    closeTeamInfoPopover();
    if (ev) openEventModal(ev.id || null, ev.date, ev);
}}

function openSlackFromTeamInfo() {{
    const ev = _teamInfoCtx;
    if (!ev) return;
    const pool = _calRecordsByPlayerTeam[(ev.player || '') + '|' + (ev.team || '')] || [];
    if (!pool.length) {{ showToast('No Slack message found for this player/team', false); return; }}
    let picked = pool.find(r => (r.workout_dates || []).some(wd => wd.date === ev.date));
    if (!picked) picked = pool.slice().sort((a,b) => (b.date || '').localeCompare(a.date || ''))[0];
    const rowKey = picked.player + '|' + picked.team + '|' + picked.date + '|cal';
    _modalIndex[rowKey] = picked;
    // Coming from team info, not the event modal — clear any stale "Back to Event"
    // context so the message modal doesn't offer a misleading return target.
    _mmReturnToEvent = null;
    document.getElementById('mmBackBtn').style.display = 'none';
    closeTeamInfoPopover();
    openMessageModal(rowKey);
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
    const isEdit = !!(id && ev && !ev.auto) || !!(ev && ev.auto);
    document.getElementById('evTitle').textContent = (id && ev && !ev.auto) ? 'Edit Event' : (ev && ev.auto ? 'Edit Auto-Workout' : 'Add Event');
    document.getElementById('evDate').value = (ev && ev.date) || isoDate || _fmtIso(new Date());
    document.getElementById('evType').value = (ev && ev.type) || 'workout';
    const playerSel = document.getElementById('evPlayer');
    const extraSel = document.getElementById('evExtraPlayers');
    if (playerSel.options.length === 0) {{
        const players = [...new Set([...RECORDS.map(r => r.player), ...ALL_2026_PLAYERS])].sort();
        players.forEach(p => {{ const o = document.createElement('option'); o.value = p; o.textContent = p; playerSel.appendChild(o); }});
        // Mirror the same player list into the multi-select.
        players.forEach(p => {{ const o = document.createElement('option'); o.value = p; o.textContent = p; extraSel.appendChild(o); }});
    }}
    // Default to a currently-selected player when adding a new event.
    let calFilterPlayer = '';
    if (_calSelectedPlayers && _calSelectedPlayers.size >= 1) {{
        const sel = [..._calSelectedPlayers].sort();
        calFilterPlayer = sel[0];
    }}
    playerSel.value = (ev && ev.player) || calFilterPlayer || playerSel.options[0].value;
    // Reset multi-select / extra dates each open. Hide both rows when editing.
    Array.from(extraSel.options).forEach(o => {{ o.selected = false; }});
    document.getElementById('evExtraDates').innerHTML = '';
    document.getElementById('evExtraPlayersRow').style.display = isEdit ? 'none' : '';
    document.getElementById('evExtraDatesRow').style.display = isEdit ? 'none' : '';
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
        // Default to the current month. If the player has no events this month,
        // jump to their nearest upcoming event (or most recent past event if none upcoming).
        const now = new Date();
        const todayIso = _fmtIso(now);
        const curYM = now.getFullYear() * 12 + now.getMonth();
        const autoDates = _calAutoEvents.filter(e => e.player === player).map(e => e.date);
        const hasThisMonth = autoDates.some(iso => {{
            const d = new Date(iso + 'T00:00:00');
            return (d.getFullYear() * 12 + d.getMonth()) === curYM;
        }});
        if (hasThisMonth || autoDates.length === 0) {{
            _calMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        }} else {{
            const upcoming = autoDates.filter(iso => iso >= todayIso).sort();
            const past = autoDates.filter(iso => iso < todayIso).sort();
            const pick = upcoming.length ? upcoming[0] : past[past.length - 1];
            const d = new Date(pick + 'T00:00:00');
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

function addExtraDate() {{
    const wrap = document.getElementById('evExtraDates');
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:6px;margin-bottom:4px;';
    const input = document.createElement('input');
    input.type = 'date';
    input.min = '2026-04-01';
    input.max = '2026-08-31';
    input.className = 'ev-extra-date';
    input.style.flex = '1';
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.textContent = '\\u00d7';
    rm.title = 'Remove';
    rm.style.cssText = 'padding:0 8px;background:#f0f0f0;border:1px solid #ccc;border-radius:4px;cursor:pointer;';
    rm.onclick = function() {{ row.remove(); }};
    row.appendChild(input);
    row.appendChild(rm);
    wrap.appendChild(row);
    input.focus();
}}

async function saveEvent() {{
    const baseBody = {{
        type: document.getElementById('evType').value,
        team: document.getElementById('evTeam').value || null,
        title: document.getElementById('evTitleInput').value || null,
        time: document.getElementById('evTime').value || null,
        location: document.getElementById('evLocation').value || null,
        tentative: document.getElementById('evTentative').checked,
        confirmed: document.getElementById('evConfirmed').checked,
        notes: document.getElementById('evNotes').value || null,
    }};
    const editId = document.getElementById('evOverlay').dataset.editId;

    // Edit path: keep single-event semantics, never fan out.
    if (editId) {{
        const body = Object.assign({{}}, baseBody, {{
            id: editId,
            date: document.getElementById('evDate').value,
            player: document.getElementById('evPlayer').value,
        }});
        try {{
            const r = await _calApi('POST', body);
            if (r && r.event) {{ _calEvents[r.id] = r.event; }}
            closeEventModal();
            renderCalendar();
            showToast('Event saved', true);
        }} catch(e) {{ showToast('Save failed: ' + e.message, false); }}
        return;
    }}

    // Add path: fan out across (players × dates).
    const primaryPlayer = document.getElementById('evPlayer').value;
    const extraPlayers = Array.from(document.getElementById('evExtraPlayers').selectedOptions).map(o => o.value);
    const players = [...new Set([primaryPlayer, ...extraPlayers].filter(Boolean))];
    const primaryDate = document.getElementById('evDate').value;
    const extraDates = Array.from(document.querySelectorAll('#evExtraDates .ev-extra-date'))
        .map(i => i.value).filter(Boolean);
    const dates = [...new Set([primaryDate, ...extraDates].filter(Boolean))];
    if (!players.length || !dates.length) {{
        showToast('Pick at least one player and one date', false);
        return;
    }}

    let saved = 0, failed = 0;
    for (const p of players) {{
        for (const d of dates) {{
            const body = Object.assign({{}}, baseBody, {{ player: p, date: d }});
            try {{
                const r = await _calApi('POST', body);
                if (r && r.event) {{ _calEvents[r.id] = r.event; }}
                saved++;
            }} catch(e) {{ failed++; }}
        }}
    }}
    closeEventModal();
    renderCalendar();
    if (failed) showToast(`Saved ${{saved}}, ${{failed}} failed`, saved > 0);
    else showToast(saved === 1 ? 'Event saved' : `Saved ${{saved}} events`, true);
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
    _pdfSyncCombineCheckbox();
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
    document.getElementById('mrCombine').checked = !!(existing && existing.combine);

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
        combine: document.getElementById('mrCombine').checked,
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

// ===================== Draft Card view =====================
// Baked-in 2026 board: [overallPick, team, slotBonus] for all 313 slotted picks.
const DRAFT_SEED = {draft_picks_js};
// ci 0..4 -> color word (matches the matrix palette / COLOR_BG). ci -1 = forced blank.
const DC_PALETTE = [
    {{ word: 'red',         name: 'Red' }},
    {{ word: 'orange',      name: 'Orange' }},
    {{ word: 'yellow',      name: 'Yellow' }},
    {{ word: 'light green', name: 'Light Green' }},
    {{ word: 'green',       name: 'Green' }},
];
// Special-pick tags (2026 MLB draft): overall pick # -> label.
// PPI = Prospect Promotion Incentive (26, 28); Comp A = Competitive Balance
// Round A (29-37); Comp B = Competitive Balance Round B (67-74).
const DC_PICK_TAG = (function() {{
    const t = {{}};
    [26, 28].forEach(n => t[n] = 'PPI');
    for (let n = 29; n <= 37; n++) t[n] = 'COMP A';
    for (let n = 67; n <= 74; n++) t[n] = 'COMP B';
    return t;
}})();
// Section header before the pick that STARTS each round/segment (2026 order).
const DRAFT_SECTIONS = {{
    1: 'Round 1', 26: 'PPI', 29: 'Comp Balance A', 38: 'Round 2',
    67: 'Comp Balance B', 75: 'FA Comp', 76: 'Round 3', 104: 'Round 4',
    136: 'Round 5', 165: 'Round 6', 194: 'Round 7', 224: 'Round 8',
    254: 'Round 9', 284: 'Round 10',
}};
// Per-pick short round/segment label (R1..R10, PPI, CBA, CBB, COMP) for the
// square's top line, so each square shows "<round> · #<overall>".
const DC_ROUND = (function() {{
    const short = {{ 'Round 1':'R1','PPI':'PPI','Comp Balance A':'CBA','Round 2':'R2',
        'Comp Balance B':'CBB','FA Comp':'COMP','Round 3':'R3','Round 4':'R4','Round 5':'R5',
        'Round 6':'R6','Round 7':'R7','Round 8':'R8','Round 9':'R9','Round 10':'R10' }};
    const map = {{}}; let cur = '';
    for (let pick = 1; pick <= 313; pick++) {{
        if (DRAFT_SECTIONS[pick]) cur = short[DRAFT_SECTIONS[pick]] || DRAFT_SECTIONS[pick];
        map[pick] = cur;
    }}
    return map;
}})();
let dcCurrent = null;        // primary player NAME (= dcSelected[0])
let dcSelected = [];         // 1-5 selected players; >1 = compare mode
let dcStarted = false;
const DC_MODAL_KEY = '__draftcard__';
const DC_MAX_COMPARE = 5;

const dcMoney = (n) => '$' + Number(n).toLocaleString('en-US');
function dcIsDark(hex) {{
    // Accepts rgb(...) or #hex. Returns true for dark backgrounds (light text).
    let r, g, b;
    const m = /rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/.exec(hex);
    if (m) {{ r = +m[1]; g = +m[2]; b = +m[3]; }}
    else {{ const h = hex.replace('#',''); if (h.length < 6) return false; r = parseInt(h.substr(0,2),16); g = parseInt(h.substr(2,2),16); b = parseInt(h.substr(4,2),16); }}
    return (0.299*r + 0.587*g + 0.114*b) < 150;
}}
const dcTeamOf = (i) => DRAFT_SEED[i][1];
// Square color = the engine's most-recent color for that pick's team (or blank).
function dcHexOf(i) {{
    const word = dcCurrent ? getLatestColor(dcCurrent, dcTeamOf(i)) : null;
    return word ? (COLOR_BG[word] || '#FFFFFF') : '#FFFFFF';
}}
// Most-recent intel record for (player, team) — opened on click.
function dcLatestRecord(player, team) {{
    let best = null;
    RECORDS.forEach(function(r) {{
        if (r.player !== player || r.team !== team) return;
        if (isExcluded(r)) return;
        if (best === null || (r.date || '') > (best.date || '') ||
            ((r.date || '') === (best.date || '') && (r.ts || '') > (best.ts || ''))) best = r;
    }});
    return best;
}}
// Click a square -> open the full most-recent Slack/notes message behind it.
function dcOpenMessageFor(player, i) {{
    const team = dcTeamOf(i);
    const rec = player ? dcLatestRecord(player, team) : null;
    if (!rec) {{ showToast('No intel on file for ' + player + ' \\u00b7 ' + team + '.'); return; }}
    _modalIndex[DC_MODAL_KEY] = rec;
    openMessageModal(DC_MODAL_KEY);
}}
function dcOpenMessage(i) {{ dcOpenMessageFor(dcCurrent, i); }}
function dcInitials(name) {{
    const parts = String(name || '').trim().split(/\\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}}
// Per-player min/max pick range (localStorage). Default = all 313 picks.
var dcRanges = {{}};
try {{ dcRanges = JSON.parse(localStorage.getItem('ti_dc_range') || '{{}}'); }} catch(e) {{}}
function dcCurRange() {{
    const r = dcRanges[dcCurrent];
    return (Array.isArray(r) && r.length === 2) ? r : [1, 313];
}}
function dcSyncRangeInputs() {{
    const r = dcCurRange();
    const mn = document.getElementById('dcRangeMin'), mx = document.getElementById('dcRangeMax');
    if (mn) mn.value = r[0]; if (mx) mx.value = r[1];
}}
function dcSetRange() {{
    if (!dcCurrent) return;
    let mn = parseInt(document.getElementById('dcRangeMin').value, 10);
    let mx = parseInt(document.getElementById('dcRangeMax').value, 10);
    if (isNaN(mn)) mn = 1; if (isNaN(mx)) mx = 313;
    mn = Math.max(1, Math.min(313, mn)); mx = Math.max(1, Math.min(313, mx));
    if (mn > mx) {{ const t = mn; mn = mx; mx = t; }}
    if (mn === 1 && mx === 313) delete dcRanges[dcCurrent]; else dcRanges[dcCurrent] = [mn, mx];
    try {{ localStorage.setItem('ti_dc_range', JSON.stringify(dcRanges)); }} catch(e) {{}}
    dcSyncRangeInputs();
    dcRenderGrid();
}}

function dcRenderKey() {{
    const k = document.getElementById('dcKeyrow'); if (!k) return; k.innerHTML = '';
    DC_PALETTE.forEach(c => {{ const s = document.createElement('span'); s.className = 'dc-k'; s.innerHTML = '<i style="background:' + (COLOR_BG[c.word]||'#fff') + '"></i>' + c.name; k.appendChild(s); }});
    const s1 = document.createElement('span'); s1.className = 'dc-k'; s1.innerHTML = '<span class="dc-work" style="position:static;box-shadow:none;margin-right:2px"></span>Pre-draft workout'; k.appendChild(s1);
    const s2 = document.createElement('span'); s2.className = 'dc-k'; s2.innerHTML = '<span class="dc-comb" style="position:static;box-shadow:none;margin-right:2px"></span>Met at combine'; k.appendChild(s2);
}}

function dcRenderGrid() {{
    const g = document.getElementById('dcGrid'); if (!g) return;
    if (!dcSelected.length) {{ g.innerHTML = ''; return; }}
    const multi = dcSelected.length > 1;
    g.innerHTML = '';
    const rmin = dcCurRange()[0], rmax = dcCurRange()[1];
    DRAFT_SEED.forEach((row, i) => {{
        const slot = row[0], bonus = row[2];
        if (slot < rmin || slot > rmax) return;  // outside the selected pick range
        const team = dcTeamOf(i);
        const el = document.createElement('div');
        const sl = document.createElement('div'); sl.className = 'dc-slot'; sl.textContent = DC_ROUND[slot] + ' \\u00b7 #' + slot;
        const tm = document.createElement('div'); tm.className = 'dc-team'; tm.textContent = team;
        const bn = document.createElement('div'); bn.className = 'dc-bonus'; bn.textContent = dcMoney(bonus);

        if (multi) {{
            // Compare mode: neutral cell, one initial-chip per selected player.
            el.className = 'dc-cell dc-multi';
            el.appendChild(sl); el.appendChild(tm);
            const chips = document.createElement('div'); chips.className = 'dc-chips';
            dcSelected.forEach(pl => {{
                const word = dcInPlay(pl, team, slot) ? getLatestColor(pl, team) : null;
                const hex = word ? (COLOR_BG[word] || '#eee') : '#f1f1f1';
                const chip = document.createElement('div');
                chip.className = 'dc-chip' + (word && dcIsDark(hex) ? ' dark' : '') + (word ? '' : ' empty');
                chip.style.background = hex;
                chip.textContent = dcInitials(pl);
                let tip = pl + (word ? ' \\u00b7 ' + word : ' \\u00b7 no color');
                if (isPDW(pl, team)) tip += ' \\u00b7 PDW';
                if (isCombine(pl, team)) tip += ' \\u00b7 combine';
                chip.title = tip;
                chip.onclick = (ev) => {{ ev.stopPropagation(); dcOpenMessageFor(pl, i); }};
                chips.appendChild(chip);
            }});
            el.appendChild(chips); el.appendChild(bn);
            el.onclick = () => dcOpenMessageFor(dcCurrent, i);
        }} else {{
            // Single-player mode: full-color cell with corner workout/combine dots.
            const word = getLatestColor(dcCurrent, team);
            const inPlay = dcInPlay(dcCurrent, team, slot);
            // Unchecked (turned off) => RED; otherwise the engine color (or white).
            const hex = !inPlay ? (COLOR_BG['red'] || '#e16e69') : (word ? (COLOR_BG[word] || '#FFFFFF') : '#FFFFFF');
            const combine = isCombine(dcCurrent, team), workout = isPDW(dcCurrent, team);
            el.className = 'dc-cell' + (dcIsDark(hex) ? ' dark' : '');
            el.style.background = hex;
            el.onclick = () => dcOpenMessage(i);
            if (workout) {{ const wk = document.createElement('div'); wk.className = 'dc-work'; wk.title = 'Pre-draft workout'; el.appendChild(wk); }}
            if (combine) {{ const cb = document.createElement('div'); cb.className = 'dc-comb'; cb.title = 'Met at combine'; el.appendChild(cb); }}
            el.appendChild(sl); el.appendChild(tm); el.appendChild(bn);
            // In-play checkbox on EVERY pick: checked = in play; unchecked = red (off).
            const pb = document.createElement('div');
            pb.className = 'dc-pickbox' + (inPlay ? ' on' : '');
            pb.textContent = inPlay ? '\\u2713' : '';
            pb.title = inPlay ? (dcCurrent + ' in play for #' + slot + ' — click to turn off') : (dcCurrent + ' OFF for #' + slot + ' — click to turn back on');
            pb.onclick = (ev) => {{ ev.stopPropagation(); togglePickInPlay(dcCurrent, team, slot); }};
            el.appendChild(pb);
        }}
        g.appendChild(el);
    }});
}}

// Set the selected players (order preserved; dcSelected[0] is primary).
function dcSetSelected(arr) {{
    dcSelected = (arr || []).filter(Boolean).slice(0, DC_MAX_COMPARE);
    dcCurrent = dcSelected[0] || null;
    const names = dcSelected.join(', ');
    const lbl = document.getElementById('dcPlayerBtnLabel');
    if (lbl) lbl.textContent = !dcSelected.length ? '\\u2014'
        : (dcSelected.length === 1 ? dcSelected[0] : (dcSelected[0].split(' ')[0] + ' +' + (dcSelected.length - 1)));
    const hp = document.getElementById('dcHeadPlayer'); if (hp) hp.textContent = dcSelected.length > 1 ? ('Compare: ' + names) : names;
    const pp = document.getElementById('dcPrintPlayer'); if (pp) pp.textContent = dcSelected.length > 1 ? ('Compare: ' + names) : names;
    dcBuildPlayerList();
    dcSyncRangeInputs();
    dcRenderGrid();
}}
function dcBuildPlayerList() {{
    const host = document.getElementById('dcPlayerList'); if (!host) return;
    const players = buildMatrix().sortedPlayers;  // matrix order
    const atCap = dcSelected.length >= DC_MAX_COMPARE;
    host.innerHTML = '';
    players.forEach(p => {{
        const on = dcSelected.includes(p);
        const row = document.createElement('label'); row.className = 'dc-pp-row';
        const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = on; cb.disabled = (!on && atCap);
        cb.onchange = () => {{
            let next = dcSelected.slice();
            if (cb.checked) next.push(p); else next = next.filter(x => x !== p);
            if (!next.length) next = [p];  // never empty
            dcSetSelected(next);
        }};
        const span = document.createElement('span'); span.textContent = p;
        row.appendChild(cb); row.appendChild(span); host.appendChild(row);
    }});
}}
function dcTogglePlayerPanel(ev) {{
    if (ev) ev.stopPropagation();
    const p = document.getElementById('dcPlayerPanel'); if (!p) return;
    p.style.display = (p.style.display === 'block') ? 'none' : 'block';
}}
function dcClearCompare() {{ dcSetSelected([dcSelected[0]]); }}
document.addEventListener('click', function(e) {{
    const p = document.getElementById('dcPlayerPanel');
    if (!p || p.style.display !== 'block') return;
    const btn = document.getElementById('dcPlayerBtn');
    if (p.contains(e.target) || (btn && btn.contains(e.target))) return;
    p.style.display = 'none';
}});
function dcPrint() {{ window.print(); }}
// Called by showView('draftcard'). Engine-seeded view; supports compare mode.
function dcShow() {{
    if (!dcStarted) {{ dcStarted = true; dcRenderKey(); }}
    ['0', '30', '14', '7'].forEach(function(k) {{
        var el = document.getElementById('dcw_' + k);
        if (el) el.classList.toggle('active', String(_dateWindowDays) === k);
    }});
    const players = buildMatrix().sortedPlayers;
    // Keep valid current selection; default to the top matrix player.
    let sel = dcSelected.filter(p => players.includes(p));
    if (!sel.length) sel = players.length ? [players[0]] : [];
    dcSetSelected(sel);
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
    <div class="popup-color" id="popupColor" style="display:none;"></div>
    <div class="popup-source" id="popupSource" style="display:none;"></div>
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
    <div class="popup-combine" id="combineToggle" onclick="toggleCombine()">Combine Interview</div>
    <div class="popup-reassign-wrap">
        <div class="popup-color-label">Reassign team</div>
        <div class="popup-reassign">
            <select id="popupReassignTeam" onchange="saveTeamReassign(this.value)">
                <option value="">— pick team —</option>
            </select>
        </div>
    </div>
    <div class="popup-set-color-wrap">
        <div class="popup-color-label">Set most-recent color</div>
        <input type="text" id="colorNoteInput" class="popup-color-note" maxlength="280"
               placeholder="Reason (optional) — why this grade?">
        <div class="popup-colors">
            <button id="colorSwatch_green"       class="cs-green"   onclick="saveColor('green')"       title="Green"></button>
            <button id="colorSwatch_light_green" class="cs-lgreen"  onclick="saveColor('light green')" title="Light Green"></button>
            <button id="colorSwatch_yellow"      class="cs-yellow"  onclick="saveColor('yellow')"      title="Yellow"></button>
            <button id="colorSwatch_orange"      class="cs-orange"  onclick="saveColor('orange')"      title="Orange"></button>
            <button id="colorSwatch_red"         class="cs-red"     onclick="saveColor('red')"         title="Red"></button>
            <button id="colorClearBtn" class="cs-clear" onclick="saveColor(null)" title="Clear manual override" style="display:none;">&times;</button>
        </div>
    </div>
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
        <div class="ev-row cb">
            <input type="checkbox" id="mrCombine">
            <label for="mrCombine">Combine Interview</label>
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
<!-- Team Info popover (calendar workout chip first-click destination) -->
<div id="teamInfoOverlay" onclick="if(event.target===this) closeTeamInfoPopover()">
    <div id="teamInfoModal">
        <button class="ti-modal-x" onclick="closeTeamInfoPopover()" aria-label="Close">&times;</button>
        <div class="gd-title" id="teamInfoTitle">Team Info</div>
        <div class="gd-sub" id="teamInfoSub"></div>
        <div id="teamInfoBody"></div>
        <div class="ti-actions">
            <button class="ti-edit" onclick="editFromTeamInfo()">Edit Workout</button>
            <button class="ti-slack" id="teamInfoSlackBtn" onclick="openSlackFromTeamInfo()">See Slack Message</button>
        </div>
    </div>
</div>
<div id="clientFilterPanel">
    <div class="cfp-head"><span>Show clients</span><span><button onclick="clientFilterAll(true)">All</button><button onclick="clientFilterAll(false)">None</button></span></div>
    <div class="cfp-list" id="clientFilterList"></div>
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
#   "player|team|date"   -> int (-2..2) or "NA"     (score edit / exclusion)
#   "w|player|team"      -> true | false             (PDW flag toggle)
#   "cb|player|team"     -> true | false             (combine-interview flag toggle)
#   "t|player|team|date" -> int 0..5                 (manual tier-points override)
#   "c|player|team"      -> 'green'|'light green'|'yellow'|'orange'|'red'  (color override)
#   "mt|player|orig_team|date" -> 'NEW'                  (manual team reassignment)
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
    """Return (overrides, meta) from Redis. `meta` maps each override key to its
    last-edit ISO timestamp (used to auto-expire color overrides against newer
    Slack records). Both default to {} when Redis is unavailable."""
    url = os.environ.get('REDIS_URL')
    if not url:
        print("INFO: REDIS_URL not set — skipping manual overrides.")
        return {}, {}
    try:
        import redis as _redis
    except ImportError:
        print("WARN: 'redis' package not installed — skipping manual overrides.")
        return {}, {}
    try:
        client = _redis.from_url(url, socket_connect_timeout=10, socket_timeout=8)
        raw = client.get('score_overrides')
        raw_meta = client.get('score_overrides_meta')
        try:
            client.close()
        except Exception:
            pass
        def _load(r):
            if not r:
                return {}
            if isinstance(r, bytes):
                r = r.decode('utf-8')
            return json.loads(r)
        return _load(raw), _load(raw_meta)
    except Exception as e:
        print(f"WARN: Failed to load overrides from Redis: {e}")
        return {}, {}


def load_manual_records():
    """Read the `manual_records` Redis blob and return records in the same shape as
    Slack-parsed records so they can be concatenated into the RECORDS list.
    Each blob value becomes one record with {player, team, date, score, full_text,
    workout, combine, workout_dates, channel: None, is_manual: True, id}.
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
                'combine': bool(val.get('combine')),
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


def apply_overrides(records, overrides, meta=None):
    if not overrides:
        return records
    meta = meta or {}

    score_ov = {}
    pdw_ov = {}
    combine_ov = {}  # 'cb|player|team'     → manual combine-interview flag
    points_ov = {}  # 't|player|team|date' → manual tier_multiplier override
    color_ov = {}   # 'c|player|team'      → manual most-recent-color override
    team_ov = {}    # 'mt|player|orig_team|date' → new team
    for key, val in overrides.items():
        if key.startswith('cb|'):
            parts = key.split('|', 2)
            if len(parts) == 3:
                combine_ov[(parts[1], parts[2])] = val
        elif key.startswith('w|'):
            parts = key.split('|', 2)
            if len(parts) == 3:
                pdw_ov[(parts[1], parts[2])] = val
        elif key.startswith('t|'):
            parts = key.split('|')
            if len(parts) == 4:
                points_ov[(parts[1], parts[2], parts[3])] = val
        elif key.startswith('c|'):
            parts = key.split('|', 2)
            if len(parts) == 3:
                # Store the edit date alongside the value so the override can
                # auto-expire against a newer Slack colored record. Legacy
                # overrides with no timestamp get 9999 (never expire).
                edit_date = (meta.get(key) or '')[:10] or '9999-12-31'
                color_ov[(parts[1], parts[2])] = (val, edit_date)
        elif key.startswith('pk|'):
            # 'pk|player|team' -> in-play pick list; dashboard-only (drives the
            # Draft Card). Not merged into teamintel.json — skip here so it isn't
            # misread as a score edit.
            continue
        elif key.startswith('mt|'):
            parts = key.split('|')
            if len(parts) == 4:
                team_ov[(parts[1], parts[2], parts[3])] = val
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

    # Team reassignments: rewrite the team on records matching (player, orig_team, date).
    # Done AFTER score/points (those keys reference the original team) but BEFORE
    # PDW/color (those reference the post-reassignment team).
    team_reassigned = 0
    team_unmatched = 0
    for (player, orig_team, date), new_team in team_ov.items():
        matched = False
        for r in out:
            if r.get('player') == player and r.get('team') == orig_team and r.get('date') == date:
                r['team'] = new_team
                r['team_overridden'] = True
                matched = True
        if matched:
            team_reassigned += 1
        else:
            team_unmatched += 1

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

    combine_flipped = set()
    combine_missing = set()
    for (player, team), val in combine_ov.items():
        matched = False
        for r in out:
            if r.get('player') == player and r.get('team') == team:
                r['combine'] = bool(val)
                r['combine_overridden'] = True
                matched = True
        (combine_flipped if matched else combine_missing).add((player, team))

    # Color overrides: rewrite the color of the most-recent record for each
    # (player, team) pair so downstream consumers (teamintel.json) see the
    # manual color when picking "most recent". AUTO-EXPIRE: if a Slack colored
    # record is dated AFTER the override's edit, the fresh Slack color wins and
    # the override is skipped (matches the dashboard's client-side behavior).
    color_applied = set()
    color_missing = set()
    color_expired = set()
    for (player, team), (val, edit_date) in color_ov.items():
        latest = None          # most-recent record (any) — the row we rewrite
        latest_colored = None  # most-recent record carrying a color — expiry check
        for r in out:
            if r.get('player') == player and r.get('team') == team:
                if latest is None or (r.get('date') or '') > (latest.get('date') or ''):
                    latest = r
                if r.get('color') and (latest_colored is None or (r.get('date') or '') > (latest_colored.get('date') or '')):
                    latest_colored = r
        if latest is None:
            color_missing.add((player, team))
            continue
        if latest_colored is not None and (latest_colored.get('date') or '') > edit_date:
            color_expired.add((player, team))  # newer Slack color supersedes the override
            continue
        latest['color'] = val if val else None
        latest['color_overridden'] = True
        color_applied.add((player, team))

    print(
        f"Applied overrides: {applied_score} score edits, {applied_points} point edits, "
        f"{excluded} excluded, {len(pdw_flipped)} PDW pairs flipped, "
        f"{len(pdw_missing)} PDW with no records, "
        f"{len(combine_flipped)} combine pairs flipped, {len(combine_missing)} combine with no records, "
        f"{len(color_applied)} color overrides, "
        f"{len(color_missing)} color overrides with no records, "
        f"{len(color_expired)} color overrides expired (newer Slack color), "
        f"{team_reassigned} team reassignments ({team_unmatched} unmatched)"
    )
    for p, t in sorted(pdw_missing):
        print(f"  (skipped PDW override {p}/{t} — no records for pair)")
    for p, t in sorted(color_missing):
        print(f"  (skipped color override {p}/{t} — no records for pair)")
    for p, t in sorted(color_expired):
        print(f"  (expired color override {p}/{t} — newer Slack color wins)")
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

    messages, slack_workspace_url, channel_errors = fetch_messages(token)
    records = parse_messages(messages)

    # Merge manual records (matrix "+ Add Entry") before building HTML and JSON.
    # Manual records live in Redis key `manual_records` and follow the same shape
    # as Slack-parsed records so matrix/detail/calendar rendering needs no changes.
    manual = load_manual_records()
    if manual:
        print(f"Merging {len(manual)} manual record(s) into RECORDS.")
        records = records + manual

    out_dir = os.environ.get('OUTPUT_DIR', os.path.join(os.path.dirname(__file__), 'public'))

    # --- Guard against silent degraded builds ---
    # If the Slack channels flip to private without the bot having groups:* scopes
    # (or the token is revoked, etc.), every fetch errors out and we'd otherwise
    # commit a near-empty dataset over good data. Abort loudly instead, leaving the
    # last good public/index.html and public/teamintel.json untouched so the cron
    # surfaces a red run. See memory: project_teamintel_slack_private_channels.
    FATAL_SLACK_ERRORS = {
        'missing_scope', 'invalid_auth', 'not_authed', 'token_revoked',
        'token_expired', 'account_inactive', 'no_permission',
    }
    MEMBERSHIP_ERRORS = {'not_in_channel', 'channel_not_found'}

    fatal = [(n, c) for (n, c) in channel_errors if c in FATAL_SLACK_ERRORS]
    membership = [(n, c) for (n, c) in channel_errors if c in MEMBERSHIP_ERRORS]

    # Hard reasons are never overridable — they mean we cannot trust the fetch.
    hard_reasons = []
    if fatal:
        codes = sorted({c for _, c in fatal})
        hard_reasons.append(
            f"token-wide Slack auth/scope failure on {len(fatal)} channel(s) "
            f"{codes} (e.g. #{fatal[0][0]}). Bot needs groups:history + "
            "groups:read for private channels (api.slack.com/apps → OAuth)."
        )
    # A couple of membership errors can be one un-invited channel; a broad sweep
    # means the bot lost access to most channels and the build is untrustworthy.
    if len(membership) >= max(2, len(CHANNELS) // 2):
        hard_reasons.append(
            f"bot not a member of {len(membership)}/{len(CHANNELS)} channels "
            "(/invite @teamintel needed)."
        )

    # Soft reason: record-count collapse vs the last committed teamintel.json — a
    # backstop for failures that don't surface as explicit errors. Overridable via
    # ALLOW_RECORD_DROP=1 for an intentional roster purge.
    soft_reasons = []
    prev_json = os.path.join(out_dir, 'teamintel.json')
    if os.path.exists(prev_json):
        try:
            with open(prev_json) as f:
                prev = json.load(f)
            prev_count = len(prev) if isinstance(prev, list) else None
        except Exception:
            prev_count = None
        if prev_count and len(records) < prev_count * 0.25:
            soft_reasons.append(
                f"record count collapsed {prev_count} → {len(records)} "
                "(>75% drop). Set ALLOW_RECORD_DROP=1 to override for an "
                "intentional roster purge."
            )

    blocking = list(hard_reasons)
    if os.environ.get('ALLOW_RECORD_DROP') != '1':
        blocking += soft_reasons
    if blocking:
        print("\nERROR: aborting build to avoid overwriting good data:")
        for r in blocking:
            print(f"  - {r}")
        print("Last good public/index.html and public/teamintel.json left untouched.")
        exit(1)

    # Pull game schedule from the shared Google Sheet. Read-only — filtered to roster.
    games = fetch_game_schedule()

    html = build_html(records, password, games=games, slack_workspace_url=slack_workspace_url)

    out_path = os.path.join(out_dir, 'index.html')
    with open(out_path, 'w') as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")

    # Also emit teamintel.json for downstream consumers (sv-draft-fit-workout).
    # Merge manual KV overrides (website edits) so PDW toggles + score edits
    # propagate downstream. Dashboard HTML applies overrides client-side,
    # so we only merge into the JSON output.
    overrides, overrides_meta = load_kv_overrides()
    records_for_json = apply_overrides(records, overrides, overrides_meta)
    json_path = os.path.join(out_dir, 'teamintel.json')
    with open(json_path, 'w') as f:
        json.dump(records_for_json, f, indent=2)
    print(f"Records JSON written to {json_path}")
