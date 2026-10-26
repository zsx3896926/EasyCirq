#!/usr/bin/env python
"""Deeper read-only analysis: concurrency, repeats, failures, per-client structure."""
import json, sys, datetime, collections, statistics

PATH = sys.argv[1]
OUT = sys.argv[2]
LO = datetime.datetime.fromisoformat('2026-10-26T02:55:07+00:00')
HI = datetime.datetime.fromisoformat('2026-10-26T06:07:36+00:00')
TARGET = 'dual-scope-instrument-01'
PAGES = {
    '86ba6c25b129b9da': 'P1', '5c43266561531ce8': 'P2', '3f8f4311ac1d0a48': 'P3',
    '8647f339f0bdb334': 'P4', '3d0c41eb8994b8fe': 'P5', '3a6bc41ccd30345f': 'P6',
    '4e543b44b6cf4b06': 'P7', '5c2d0e8284e8a094': 'P8', '16f93f802f1f2c16': 'P9',
    '5042e927fb8effd2': 'P10', '80f699c84790b779': 'P11', '82e694c4a09f61f2': 'P12',
    'f31ffe03a7036175': 'P13', '004cde4d99de4fe3': 'P14', '2fd8a6a67c536700': 'P15',
    '29dafbb1f45a1d49': 'P16', '1093a44e8a348cb1': 'P17', 'e68283a824c1e483': 'P18',
    '5de8fb141b41474b': 'P19', '51c5025fcb65ac': 'P20', '51c5025fcb65c7ac': 'P20',
    'a46148ddda2cd3fb': 'P21',
}

def parse_ts(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))

recs = []
allrecs = []
with open(PATH, encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        t = parse_ts(r['ts'])
        if not (LO <= t <= HI):
            continue
        allrecs.append((t, r))
        ctx = r.get('context') or {}
        p = ctx.get('projectName') or (r.get('mutationContext') or {}).get('projectName') or 'NONE'
        payload = r.get('payload') if isinstance(r.get('payload'), dict) else {}
        recs.append({
            'ts': t, 'action': r.get('action'), 'cmd': r.get('command') or '',
            'ok': r.get('ok') is True, 'ms': int(r.get('durationMs') or 0),
            'doc': ctx.get('documentUuid') or '', 'win': r.get('windowId') or '',
            'client': r.get('clientId') or '', 'proj': p,
            'err': (r.get('errorCode') or '') + ':' + (r.get('errorMsg') or ''),
            'payload': payload,
        })
recs.sort(key=lambda x: x['ts'])

out = {}

# ---------- concurrency / union busy ----------
intervals = sorted([(r['ts'], r['ts'] + datetime.timedelta(milliseconds=r['ms'])) for r in recs])
union = 0.0
cur_s = cur_e = None
maxconc = 0
starts = sorted([(r['ts'], 1) for r in recs] + [(r['ts'] + datetime.timedelta(milliseconds=r['ms']), -1) for r in recs])
conc = 0
for t, d in starts:
    conc += d
    maxconc = max(maxconc, conc)
for s, e in intervals:
    if cur_e is None or s > cur_e:
        if cur_e is not None:
            union += (cur_e - cur_s).total_seconds()
        cur_s, cur_e = s, e
    else:
        cur_e = max(cur_e, e)
if cur_e is not None:
    union += (cur_e - cur_s).total_seconds()
span = (recs[-1]['ts'] - recs[0]['ts']).total_seconds()
sum_ms = sum(r['ms'] for r in recs) / 1000.0
out['concurrency'] = {
    'span_s': round(span, 1), 'sum_call_s': round(sum_ms, 1), 'union_busy_s': round(union, 1),
    'idle_s': round(span - union, 1), 'max_concurrent': maxconc,
    'parallel_inflation_ratio': round(sum_ms / union, 3) if union else None,
    'calls_started_while_busy': sum(1 for i, (s, e) in enumerate(intervals)
                                    if any(s2 <= s < e2 for (s2, e2) in intervals[max(0, i - 60):i])),
}

# ---------- place repeats ----------
place_seq = collections.defaultdict(list)
for r in recs:
    if r['action'] == 'schematic.component.place':
        d = r['payload'].get('designator')
        if d:
            place_seq[r['doc']].append((r['ts'], d, r['ms'], r['ok']))
repeat_places = []
for doc, seq in place_seq.items():
    seen = {}
    for t, d, ms, ok in seq:
        if d in seen:
            repeat_places.append({'doc': PAGES.get(doc, doc), 'designator': d,
                                  'first': seen[d][0].isoformat(), 'repeat': t.isoformat(),
                                  'gap_s': round((t - seen[d][0]).total_seconds(), 1),
                                  'repeat_ms': ms})
        else:
            seen[d] = (t, ms)
out['place_repeats'] = {'total_place_calls': sum(len(v) for v in place_seq.values()),
                        'distinct_designators': {PAGES.get(k, k): len(v) for k, v in place_seq.items()},
                        'repeat_events': repeat_places[:40], 'repeat_count': len(repeat_places)}

# ---------- connect repeats by coordinate+net ----------
conn_seq = collections.defaultdict(list)
for r in recs:
    if r['action'] == 'schematic.power.connect_pin':
        p = r['payload']
        key = (p.get('pinX'), p.get('pinY'), p.get('net'), p.get('kind'))
        conn_seq[r['doc']].append((r['ts'], key, r['ms'], r['ok']))
conn_rep = 0
conn_rep_examples = []
for doc, seq in conn_seq.items():
    seen = {}
    for t, key, ms, ok in seq:
        if key in seen:
            conn_rep += 1
            if len(conn_rep_examples) < 20:
                conn_rep_examples.append({'doc': PAGES.get(doc, doc), 'key': key,
                                          'first': seen[key].isoformat(), 'repeat': t.isoformat(),
                                          'gap_s': round((t - seen[key]).total_seconds(), 1), 'ms': ms})
        else:
            seen[key] = t
out['connect_repeats'] = {'total_connect_calls': sum(len(v) for v in conn_seq.values()),
                          'repeat_count': conn_rep, 'examples': conn_rep_examples}

# ---------- per-client structure ----------
clients = collections.defaultdict(lambda: {'cmd': '', 'first': None, 'last': None, 'ms': 0,
                                          'actions': collections.Counter(), 'reads': 0,
                                          'pins': 0, 'places': 0, 'saves': 0, 'maxread': 0})
for r in recs:
    c = clients[r['client']]
    c['cmd'] = c['cmd'] or r['cmd']
    if c['first'] is None or r['ts'] < c['first']:
        c['first'] = r['ts']
    if c['last'] is None or r['ts'] > c['last']:
        c['last'] = r['ts']
    c['ms'] += r['ms']
    c['actions'][r['action']] += 1
    if r['action'] == 'schematic.components.list':
        c['reads'] += 1
        c['maxread'] = max(c['maxread'], r['ms'])
    elif r['action'] == 'schematic.power.connect_pin':
        c['pins'] += 1
    elif r['action'] == 'schematic.component.place':
        c['places'] += 1
    elif r['action'] == 'schematic.save':
        c['saves'] += 1
auto = [c for c in clients.values() if c['cmd'] == 'easyeda sch autoconnect']
auto_stats = [{
    'span_s': round((c['last'] - c['first']).total_seconds(), 1), 'sum_s': round(c['ms'] / 1000, 1),
    'reads': c['reads'], 'pins': c['pins'], 'reads_per_pin': round(c['reads'] / c['pins'], 2) if c['pins'] else None,
    'maxread_ms': c['maxread'],
} for c in auto]
out['autoconnect_clients'] = {
    'clients': len(auto),
    'with_pins': sum(1 for c in auto_stats if c['pins']),
    'total_pins': sum(c['pins'] for c in auto_stats),
    'total_reads': sum(c['reads'] for c in auto_stats),
    'median_reads_per_pin': statistics.median([c['reads_per_pin'] for c in auto_stats if c['pins']]),
    'max_reads_per_pin': max([c['reads_per_pin'] for c in auto_stats if c['pins']] or [0]),
    'total_span_s': round(sum(c['span_s'] for c in auto_stats), 1),
    'slowest_clients': sorted(auto_stats, key=lambda x: -x['sum_s'])[:6],
}
place_clients = [c for c in clients.values() if c['cmd'] == 'easyeda sch place']
out['place_clients'] = {
    'clients': len(place_clients),
    'total_places': sum(c['places'] for c in place_clients),
    'total_reads': sum(c['reads'] for c in place_clients),
    'median_reads_per_place': statistics.median([c['reads'] / c['places'] for c in place_clients if c['places']]),
    'sum_span_s': round(sum((c['last'] - c['first']).total_seconds() for c in place_clients), 1),
}

# ---------- failures ----------
fails = [r for r in recs if not r['ok']]
fb = collections.Counter((r['action'], r['err']) for r in fails)
out['failures'] = {'count': len(fails),
                   'by_action_error': [{'action': a, 'error': e[:90], 'count': v} for (a, e), v in fb.most_common(20)],
                   'timeline': [{'ts': r['ts'].isoformat(), 'action': r['action'], 'ms': r['ms'],
                                 'err': r['err'][:90]} for r in fails[:60]]}
# blind retry: place failure followed within 120s by a place of same designator (from payload)
fretry = []
for i, r in enumerate(recs):
    if r['ok'] or r['action'] != 'schematic.component.place':
        continue
    d = r['payload'].get('designator')
    if not d:
        continue
    for r2 in recs[i + 1:i + 400]:
        if (r2['ts'] - r['ts']).total_seconds() > 120:
            break
        if r2['action'] == 'schematic.component.place' and r2['payload'].get('designator') == d:
            fretry.append({'designator': d, 'fail_ts': r['ts'].isoformat(), 'retry_ts': r2['ts'].isoformat(),
                           'gap_s': round((r2['ts'] - r['ts']).total_seconds(), 1), 'retry_ok': r2['ok']})
            break
out['place_fail_then_retry_120s'] = {'count': len(fretry), 'examples': fretry[:20]}

# ---------- saves ----------
saves = collections.defaultdict(list)
for r in recs:
    if r['action'] == 'schematic.save':
        saves[r['doc']].append((r['ts'], r['ms'], r['ok'], r['cmd']))
dup = []
for d, s in saves.items():
    s.sort()
    for k in range(1, len(s)):
        gap = (s[k][0] - s[k - 1][0]).total_seconds()
        if gap <= 30:
            dup.append({'page': PAGES.get(d, d), 'gap_s': round(gap, 1), 'ms': s[k][1]})
out['saves'] = {'total': sum(len(v) for v in saves.values()),
                'per_page': {PAGES.get(k, k): len(v) for k, v in saves.items()},
                'duplicates_within_30s': len(dup), 'duplicate_examples': dup[:10],
                'slow_saves': sorted([{'page': PAGES.get(d, d), 'ts': t.isoformat(), 'ms': ms, 'ok': ok}
                                      for d, s in saves.items() for t, ms, ok, _ in s],
                                     key=lambda x: -x['ms'])[:10]}

# ---------- page switching ----------
opens = [r for r in recs if r['action'] == 'document.open']
seq = [PAGES.get(r['doc'], r['doc']) for r in opens]
out['page_switches'] = {'opens': len(opens),
                        'per_page': dict(collections.Counter(seq)),
                        'rapid_reopens_le_10s': sum(1 for k in range(1, len(opens))
                                                    if (opens[k]['ts'] - opens[k - 1]['ts']).total_seconds() <= 10),
                        'pingpong_pairs': collections.Counter(
                            tuple(sorted((seq[k - 1], seq[k]))) for k in range(1, len(seq))
                            if seq[k] != seq[k - 1]).most_common(8)}

# ---------- long-tail contribution ----------
lst = [r for r in recs if r['action'] == 'schematic.components.list']
lst_sorted = sorted(lst, key=lambda r: -r['ms'])
def share(k):
    return round(sum(r['ms'] for r in lst_sorted[:k]) / 1000.0, 1)
out['components_list_tail'] = {'calls': len(lst), 'total_s': round(sum(r['ms'] for r in lst) / 1000.0, 1),
                               'top10_s': share(10), 'top50_s': share(50), 'top100_s': share(100),
                               'ge10s_calls': sum(1 for r in lst if r['ms'] >= 10000),
                               'ge10s_s': round(sum(r['ms'] for r in lst if r['ms'] >= 10000) / 1000.0, 1),
                               'by_command': {c: {'calls': v[0], 's': round(v[1] / 1000.0, 1)}
                                              for c, v in ((c, (sum(1 for r in lst if r['cmd'] == c),
                                                                sum(r['ms'] for r in lst if r['cmd'] == c)))
                                                           for c in {r['cmd'] for r in lst})}}

# ---------- module baseline P1/P2/P18 ----------
mod_docs = {'86ba6c25b129b9da', '5c43266561531ce8', 'e68283a824c1e483'}
mod = [r for r in recs if r['doc'] in mod_docs]
per_page = {}
for d in mod_docs:
    rs = [r for r in mod if r['doc'] == d]
    per_page[PAGES.get(d, d)] = {
        'calls': len(rs), 'seconds': round(sum(r['ms'] for r in rs) / 1000.0, 1),
        'lists': sum(1 for r in rs if r['action'] == 'schematic.components.list'),
        'list_seconds': round(sum(r['ms'] for r in rs if r['action'] == 'schematic.components.list') / 1000.0, 1),
        'places': sum(1 for r in rs if r['action'] == 'schematic.component.place'),
        'connects': sum(1 for r in rs if r['action'] == 'schematic.power.connect_pin'),
        'saves': sum(1 for r in rs if r['action'] == 'schematic.save'),
        'opens': sum(1 for r in rs if r['action'] == 'document.open'),
        'first': min(r['ts'] for r in rs).isoformat(), 'last': max(r['ts'] for r in rs).isoformat(),
    }
out['module_baseline_P1_P2_P18'] = {
    'per_page': per_page,
    'total_calls': len(mod), 'total_seconds': round(sum(r['ms'] for r in mod) / 1000.0, 1),
    'total_lists': sum(1 for r in mod if r['action'] == 'schematic.components.list'),
    'total_list_seconds': round(sum(r['ms'] for r in mod if r['action'] == 'schematic.components.list') / 1000.0, 1),
    'total_places': sum(1 for r in mod if r['action'] == 'schematic.component.place'),
    'total_connects': sum(1 for r in mod if r['action'] == 'schematic.power.connect_pin'),
}

# ---------- reads per mutation (read amplification) ----------
mut = {'schematic.component.place', 'schematic.power.connect_pin', 'schematic.save',
       'schematic.page.create', 'schematic.page.clear', 'schematic.page.rename',
       'schematic.pin.set_no_connect', 'schematic.primitives.delete'}
nm = sum(1 for r in recs if r['action'] in mut)
nr = sum(1 for r in recs if r['action'] == 'schematic.components.list')
out['read_amplification'] = {'mutations': nm, 'page_readbacks': nr,
                             'reads_per_mutation': round(nr / nm, 2),
                             'readback_seconds': round(sum(r['ms'] for r in recs if r['action'] == 'schematic.components.list') / 1000.0, 1)}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print(json.dumps(out, ensure_ascii=False, indent=1)[:12000])
