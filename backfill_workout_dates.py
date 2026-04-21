#!/usr/bin/env python3
"""
One-off: add workout_dates to every record in public/teamintel.json
so the calendar UI can render before the next full fetch_and_build run.

Safe to re-run; it rewrites the same fields each time.
"""
import json, sys
from collections import defaultdict

sys.path.insert(0, '.')
from fetch_and_build import extract_workout_dates

PATH = 'public/teamintel.json'

with open(PATH) as f:
    records = json.load(f)

cache = {}
added = 0
for r in records:
    if r.get('workout'):
        ft = r.get('full_text', '')
        if ft not in cache:
            cache[ft] = extract_workout_dates(ft)
        dates = cache[ft].get(r['team'], [])
        r['workout_dates'] = dates
        if dates: added += 1
    else:
        r['workout_dates'] = []

with open(PATH, 'w') as f:
    json.dump(records, f, indent=2)

print(f'Backfilled workout_dates into {len(records)} records. '
      f'{added} workout records now have at least one parsed date.')
