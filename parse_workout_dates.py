#!/usr/bin/env python3
"""
Dry-run validator for workout-date parsing. Reads public/teamintel.json,
pulls workout:true records, runs fetch_and_build.extract_workout_dates
against each unique message, and prints a summary.

Not part of the build pipeline — keep for debugging parser changes.
"""
import json, sys
from collections import defaultdict

sys.path.insert(0, '.')
from fetch_and_build import extract_workout_dates

JSON_PATH = 'public/teamintel.json'


def main():
    with open(JSON_PATH) as f:
        records = json.load(f)

    workouts = [r for r in records if r.get('workout')]
    print(f'Loaded {len(records)} records, {len(workouts)} flagged workout:true\n')

    by_msg = defaultdict(list)
    for r in workouts:
        by_msg[(r['full_text'], r['date'])].append(r)

    print(f'Unique workout messages: {len(by_msg)}\n')

    parsed_any = 0
    parsed_match_team = 0
    unattributed = []

    for (full_text, msg_date), recs in sorted(by_msg.items(), key=lambda x: x[0][1]):
        by_team = extract_workout_dates(full_text)
        if not by_team:
            unattributed.append((msg_date, recs[0]['player'], full_text[:140]))
            continue
        parsed_any += 1
        players = sorted({r['player'] for r in recs})
        teams_in_records = sorted({r['team'] for r in recs})

        print(f'--- {msg_date}  players={players}  record_teams={teams_in_records}')
        for team, events in sorted(by_team.items()):
            for ev in events:
                extras = []
                if ev['tentative']: extras.append('tentative')
                if ev['time']: extras.append(ev['time'])
                if ev['location']: extras.append(ev['location'])
                extras_str = f' [{", ".join(extras)}]' if extras else ''
                hit = '  ' if team in teams_in_records else '* '
                print(f'  {hit}{team:>4}  {ev["date"]}{extras_str}')
                if team in teams_in_records:
                    parsed_match_team += 1
        print()

    print(f'Summary: {parsed_any}/{len(by_msg)} messages yielded at least one date.')
    print(f'Team-matched events (would surface on calendar): {parsed_match_team}')
    print(f'\nUnattributed ({len(unattributed)}):')
    for d, p, t in unattributed[:20]:
        print(f'  {d}  {p}  {t!r}')


if __name__ == '__main__':
    main()
