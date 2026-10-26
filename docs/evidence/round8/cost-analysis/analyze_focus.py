#!/usr/bin/env python
"""Focused checks: repeat legitimacy, long-call concurrency, duplicate saves, open commands."""
import json, sys, datetime, collections

PATH = sys.argv[1]
LO = datetime.datetime.fromisoformat('2026-10-26T02:55:07+00:00')
HI = datetime.datetime.fromisoformat('2026-10-26T06:07:36+00:00')
PAGES = {'86ba6c25b129b9da': 'P1', '5c43266561531ce8': 'P2', '3f8f4311ac1d0a48': 'P3',
         '8647f339f0bdb334': 'P4', '3d0c41eb8994b8fe': 'P5', '3a6bc41ccd30345f': 'P6',
         '4e543b44b6cf4b06': 'P7', '5c2d0e8284e8a094': 'P8', '16f93f802f1f2c16': 'P9',
         '5042e927fb8effd2': 'P10', '80f699c84790b779': 'P11', '82e694c4a09f61f2': 'P12',
         'f31ffe03a7036175': 'P13', '004cde4d99de4fe3': 'P14', '2fd8a6a67c536700': 'P15',
         '29dafbb1f45a1d49': 'P16', '1093a44e8a348cb1': 'P17', 'e68283a824c1e483': 'P18',
         '5de8fb141b41474b': 'P19', '51c5025fcb65c7ac': 'P20', 'a46148ddda2cd3fb': 'P21'}
def ts(s): return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
recs = []
for line in open(PATH, encoding='utf-8'):
    r = json.loads(line)
    t = ts(r['ts'])
    if not (LO <= t <= HI):
        continue
    ctx = r.get('context') or {}
    recs.append({'ts': t, 'action': r.get('action'), 'cmd': r.get('command') or '',
                 'ok': r.get('ok') is True, 'ms': int(r.get('durationMs') or 0),
                 'doc': ctx.get('documentUuid') or '', 'win': r.get('windowId') or '',
                 'client': r.get('clientId') or '',
                 'payload': r.get('payload') if isinstance(r.get('payload'), dict) else {},
                 'err': (r.get('errorCode') or '') + ':' + (r.get('errorMsg') or '')})
recs.sort(key=lambda x: x['ts'])

# 1) place repeats vs page.clear
clears = collections.defaultdict(list)
places = collections.defaultdict(list)
for r in recs:
    if r['action'] == 'schematic.page.clear':
        clears[r['doc']].append(r['ts'])
    elif r['action'] == 'schematic.component.place':
        places[r['doc']].append(r)
print('=== PLACE REPEATS BY PAGE GENERATION ===')
for d, plist in places.items():
    cl = sorted(clears.get(d, []))
    gens = collections.Counter()
    first_seen = {}
    reps_same_gen = 0
    for r in plist:
        gen = sum(1 for c in cl if c < r['ts'])
        des = r['payload'].get('designator')
        if not des: continue
        k = (gen, des)
        if k in first_seen:
            reps_same_gen += 1
        else:
            first_seen[k] = r['ts']
        gens[gen] += 1
    print(f"{PAGES.get(d,d):3s} clears={len(cl)} places={len(plist)} re-places_within_same_generation={reps_same_gen} per_gen={dict(gens)}")

# 2) long components.list calls: concurrency and context
lst = [r for r in recs if r['action'] == 'schematic.components.list']
def concurrent_count(t):
    n = 0
    for o in recs:
        if o is None: continue
        if o['ts'] <= t < o['ts'] + datetime.timedelta(milliseconds=o['ms']):
            n += 1
    return n
longs = sorted([r for r in lst if r['ms'] >= 10000], key=lambda r: -r['ms'])
print('\n=== COMPONENTS.LIST >=10s ===')
print('count', len(longs), 'seconds', round(sum(r['ms'] for r in longs)/1000,1))
by = collections.Counter()
for r in longs:
    by[(r['cmd'], PAGES.get(r['doc'], r['doc']))] += 1
for k, v in by.most_common(20): print(' ', v, k)
for r in longs[:12]:
    print(f"  {r['ts'].strftime('%H:%M:%S')} {r['ms']:7d}ms {r['cmd']:22s} {PAGES.get(r['doc'],r['doc']):3s} win={r['win'][:8]}")

# 3) duplicate saves with no mutation between
mut_actions = {'schematic.component.place', 'schematic.power.connect_pin', 'schematic.page.clear',
               'schematic.page.create', 'schematic.page.rename', 'schematic.pin.set_no_connect',
               'schematic.primitives.delete', 'schematic.component.modify', 'schematic.replace'}
last_mut = {}
saves = collections.defaultdict(list)
for r in recs:
    if r['action'] in mut_actions:
        last_mut[r['doc']] = r['ts']
    elif r['action'] == 'schematic.save':
        saves[r['doc']].append((r['ts'], r['ms'], r['ok']))
dup_no_mut = []
for d, sl in saves.items():
    sl.sort()
    for k in range(1, len(sl)):
        gap = (sl[k][0] - sl[k-1][0]).total_seconds()
        lm = last_mut.get(d)
        if gap <= 60 and (lm is None or lm < sl[k-1][0]):
            dup_no_mut.append((PAGES.get(d,d), round(gap,1), sl[k][1], sl[k][2]))
print('\n=== SAVES WITH NO INTERVENING MUTATION (<=60s) ===')
print('count', len(dup_no_mut), dup_no_mut[:20])

# 4) document.open commands
print('\n=== DOCUMENT.OPEN BY COMMAND ===')
c = collections.Counter(r['cmd'] or '(none)' for r in recs if r['action'] == 'document.open')
for k, v in c.most_common(): print(' ', v, k)
print('open seconds by command:')
s = collections.Counter()
for r in recs:
    if r['action'] == 'document.open': s[r['cmd'] or '(none)'] += r['ms']
for k, v in s.most_common(): print(' ', k, round(v/1000,1), 's')

# 5) explicit sch list reads per page during stall
print('\n=== sch list READBACKS (command=easyeda sch list) ===')
sl = [r for r in recs if r['action'] == 'schematic.components.list' and r['cmd'] == 'easyeda sch list']
per = collections.Counter(); pers = collections.Counter()
for r in sl:
    per[PAGES.get(r['doc'], r['doc'])] += 1; pers[PAGES.get(r['doc'], r['doc'])] += r['ms']
for k in per: print(f"  {k:3s} calls={per[k]:3d} s={round(pers[k]/1000,1)}")

# 6) failures around stall: per 10-min bucket and window
print('\n=== FAILURES PER BUCKET ===')
fb = collections.Counter()
for r in recs:
    if not r['ok']:
        fb[r['ts'].strftime('%H:%M')[:4] + '0'] += 1
for k in sorted(fb): print(' ', k, fb[k])

# 7) window overlap: which windows over time
print('\n=== WINDOWS ===')
for w, n in collections.Counter(r['win'] for r in recs).most_common():
    ws = [r['ts'] for r in recs if r['win'] == w]
    print(' ', w, n, min(ws).strftime('%H:%M:%S'), '->', max(ws).strftime('%H:%M:%S'))
