#!/usr/bin/env python
"""Read-only analysis of EasyEDA connector audit JSONL.

Usage: python -I analyze_audit.py <audit.jsonl> <out.json>
"""
import json, sys, datetime, collections, statistics, hashlib

PATH = sys.argv[1]
OUT = sys.argv[2]
LO = datetime.datetime.fromisoformat('2026-10-26T02:55:07+00:00')
HI = datetime.datetime.fromisoformat('2026-10-26T06:07:36+00:00')
TARGET = 'dual-scope-instrument-01'

MUT_ACTIONS = {
    'schematic.component.place', 'schematic.power.connect_pin', 'schematic.save',
    'schematic.page.create', 'schematic.page.clear', 'schematic.page.rename',
    'schematic.pin.set_no_connect', 'schematic.primitives.delete',
    'schematic.replace', 'schematic.text.create', 'schematic.text.modify',
    'project.import', 'project.export', 'schematic.export.bom', 'schematic.export.image',
    'pcb.import.changes', 'pcb.outline.set', 'pcb.outline.round', 'pcb.line.create',
    'pcb.fill.create', 'pcb.pour.rebuild', 'pcb.component.modify', 'pcb.route.delete',
    'pcb.save', 'document.open', 'document.close', 'schematic.component.modify',
    'schematic.wire.create', 'schematic.flag.create', 'schematic.net_label.create',
}
PROBE_ACTIONS = {
    'schematic.components.list', 'schematic.text.list', 'schematic.pages.list',
    'schematic.check', 'schematic.titleblock.get', 'schematic.visible_text.bboxes',
    'document.current', 'pcb.documents.list', 'pcb.components.list', 'pcb.line.list',
    'pcb.outline.get', 'pcb.via.list', 'pcb.fill.list', 'pcb.silk.list', 'pcb.layers.list',
    'pcb.constraint.list', 'pcb.pour.list', 'pcb.drc.rules', 'pcb.board.info',
    'library.device.get', 'library.symbol.export_source', 'project.current',
    'schematic.library.search', 'library.common.list', 'debug.exec_js',
}

def parse_ts(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))

def pct(vals, p):
    if not vals:
        return 0.0
    vals = sorted(vals)
    k = min(len(vals) - 1, int(round((len(vals) - 1) * p)))
    return vals[k]

def comp_sig(res):
    comps = res.get('components') or []
    items = []
    for c in comps:
        items.append((c.get('designator') or c.get('name'), c.get('x'), c.get('y'),
                      c.get('rotation'), c.get('primitiveId'), c.get('net') or ''))
    items.sort(key=lambda t: (str(t[0]), str(t[4])))
    h = hashlib.sha1(json.dumps(items, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:12]
    return f"{len(comps)}|{len(res.get('wires') or [])}|{h}"

records = []
byproj = collections.Counter()
with open(PATH, encoding='utf-8') as f:
    for line in f:
        try:
            r = json.loads(line)
        except Exception:
            continue
        t = parse_ts(r['ts'])
        ctx = r.get('context') or {}
        p = ctx.get('projectName') or (r.get('mutationContext') or {}).get('projectName') or 'NONE'
        if not (LO <= t <= HI):
            continue
        byproj[p] += 1
        if p != TARGET:
            continue
        rec = {
            'ts': t, 'action': r.get('action'), 'cmd': r.get('command') or '',
            'ok': r.get('ok') is True, 'ms': int(r.get('durationMs') or 0),
            'doc': ctx.get('documentUuid') or '', 'dtype': ctx.get('documentType') or '',
            'win': r.get('windowId') or '', 'client': r.get('clientId') or '',
            'linelen': len(line), 'req': r.get('requestId'),
            'err': (r.get('errorCode') or '') + ' ' + (r.get('errorMsg') or ''),
            'res': r.get('result'),
        }
        if rec['action'] == 'schematic.components.list' and isinstance(rec['res'], dict):
            rec['sig'] = comp_sig(rec['res'])
            rec['ncomp'] = len(rec['res'].get('components') or [])
        records.append(rec)

records.sort(key=lambda x: x['ts'])
n = len(records)
span = (records[-1]['ts'] - records[0]['ts']).total_seconds() if n else 0
daemon = sum(r['ms'] for r in records) / 1000.0

# ---------- per action ----------
act = collections.defaultdict(lambda: {'calls': 0, 'fail': 0, 'ms': 0, 'durs': [], 'bytes': 0, 'maxms': 0, 'maxts': None})
for r in records:
    a = act[r['action']]
    a['calls'] += 1
    a['ms'] += r['ms']
    a['bytes'] += r['linelen']
    a['durs'].append(r['ms'])
    if not r['ok']:
        a['fail'] += 1
    if r['ms'] > a['maxms']:
        a['maxms'] = r['ms']
        a['maxts'] = r['ts'].isoformat()
actions_out = []
for name, a in sorted(act.items(), key=lambda kv: -kv[1]['ms']):
    actions_out.append({
        'action': name, 'calls': a['calls'], 'failures': a['fail'],
        'seconds': round(a['ms'] / 1000.0, 1), 'median_ms': round(statistics.median(a['durs']), 1),
        'p95_ms': round(pct(a['durs'], 0.95), 1), 'max_ms': a['maxms'], 'max_ts': a['maxts'],
        'payload_mb': round(a['bytes'] / 1e6, 1),
    })

# ---------- per command group ----------
cmd = collections.defaultdict(lambda: {'records': 0, 'ms': 0, 'fail': 0, 'clients': set(), 'actions': collections.Counter()})
for r in records:
    c = cmd[r['cmd']]
    c['records'] += 1
    c['ms'] += r['ms']
    c['fail'] += 0 if r['ok'] else 1
    c['clients'].add(r['client'])
    c['actions'][r['action']] += 1
cmd_out = []
for name, c in sorted(cmd.items(), key=lambda kv: -kv[1]['ms']):
    cmd_out.append({'command': name or '(none)', 'records': c['records'], 'clients': len(c['clients']),
                    'seconds': round(c['ms'] / 1000.0, 1), 'failures': c['fail'],
                    'top_actions': c['actions'].most_common(6)})

# ---------- per document ----------
doc = collections.defaultdict(lambda: {'records': 0, 'ms': 0, 'fail': 0, 'opens': 0, 'saves': 0,
                                       'lists': 0, 'list_ms': 0, 'places': 0, 'connects': 0,
                                       'first': None, 'last': None})
for r in records:
    d = doc[r['doc'] or '(none)']
    d['records'] += 1
    d['ms'] += r['ms']
    d['fail'] += 0 if r['ok'] else 1
    a = r['action']
    if a == 'document.open':
        d['opens'] += 1
    elif a == 'schematic.save':
        d['saves'] += 1
    elif a == 'schematic.components.list':
        d['lists'] += 1
        d['list_ms'] += r['ms']
    elif a == 'schematic.component.place':
        d['places'] += 1
    elif a == 'schematic.power.connect_pin':
        d['connects'] += 1
    if d['first'] is None or r['ts'] < d['first']:
        d['first'] = r['ts']
    if d['last'] is None or r['ts'] > d['last']:
        d['last'] = r['ts']
doc_out = []
for name, d in sorted(doc.items(), key=lambda kv: -kv[1]['ms']):
    doc_out.append({'document': name, 'records': d['records'], 'seconds': round(d['ms'] / 1000.0, 1),
                    'failures': d['fail'], 'opens': d['opens'], 'saves': d['saves'],
                    'lists': d['lists'], 'list_seconds': round(d['list_ms'] / 1000.0, 1),
                    'places': d['places'], 'connects': d['connects'],
                    'first': d['first'].isoformat() if d['first'] else None,
                    'last': d['last'].isoformat() if d['last'] else None})

# ---------- gaps / think ----------
gaps = []
overlap = 0
for i in range(1, n):
    gap = (records[i]['ts'] - records[i - 1]['ts']).total_seconds()
    if gap < 0:
        overlap += 1
    gaps.append(gap)
gap_pos = [g for g in gaps if g > 0]
think = sum(g for g in gap_pos if g > 2.0)  # gaps longer than 2s counted as think/queue
big_gaps = sorted([(g, records[i]['ts'].isoformat(), records[i - 1]['action'], records[i]['action'])
                   for i, g in enumerate(gaps, start=1) if g >= 30], reverse=True)[:20]

# ---------- time buckets ----------
buckets = collections.defaultdict(lambda: {'records': 0, 'ms': 0, 'fail': 0, 'lists': 0, 'list_ms': 0,
                                           'places': 0, 'connects': 0, 'saves': 0})
for r in records:
    b = r['ts'].replace(minute=(r['ts'].minute // 10) * 10, second=0, microsecond=0)
    bb = buckets[b]
    bb['records'] += 1
    bb['ms'] += r['ms']
    bb['fail'] += 0 if r['ok'] else 1
    if r['action'] == 'schematic.components.list':
        bb['lists'] += 1
        bb['list_ms'] += r['ms']
    elif r['action'] == 'schematic.component.place':
        bb['places'] += 1
    elif r['action'] == 'schematic.power.connect_pin':
        bb['connects'] += 1
    elif r['action'] == 'schematic.save':
        bb['saves'] += 1
buckets_out = []
for b, bb in sorted(buckets.items()):
    buckets_out.append({'bucket': b.strftime('%H:%M'), 'records': bb['records'],
                        'seconds': round(bb['ms'] / 1000.0, 1), 'failures': bb['fail'],
                        'lists': bb['lists'], 'list_seconds': round(bb['list_ms'] / 1000.0, 1),
                        'places': bb['places'], 'connects': bb['connects'], 'saves': bb['saves']})

# ---------- slowest calls ----------
slow = sorted(records, key=lambda r: -r['ms'])[:30]
slow_out = [{'ts': r['ts'].isoformat(), 'action': r['action'], 'cmd': r['cmd'], 'ms': r['ms'],
             'doc': r['doc'], 'ok': r['ok'], 'err': r['err'][:120]} for r in slow]

# ---------- repeated reads (identical page state, same doc, no mutation between) ----------
last_read = {}   # doc -> (ts, sig)
dup_reads = collections.Counter()
dup_read_ms = collections.Counter()
dup_examples = []
prev_mut = {}    # doc -> ts of last mutation record
for r in records:
    a = r['action']
    if a == 'schematic.components.list' and 'sig' in r:
        d = r['doc']
        prev = last_read.get(d)
        if prev and prev[1] == r['sig'] and (r['ts'] - prev[0]).total_seconds() <= 120:
            dup_reads[d] += 1
            dup_read_ms[d] += r['ms']
            if len(dup_examples) < 12:
                dup_examples.append({'ts': r['ts'].isoformat(), 'doc': d, 'sig': r['sig'],
                                     'gap_s': round((r['ts'] - prev[0]).total_seconds(), 1), 'ms': r['ms']})
        last_read[d] = (r['ts'], r['sig'])
    elif a in MUT_ACTIONS:
        prev_mut[r['doc']] = r['ts']

# identical result anywhere in same doc regardless of mutation (page truly unchanged)
sig_repeat = collections.Counter()
sig_first = {}
for r in records:
    if r['action'] == 'schematic.components.list' and 'sig' in r:
        key = (r['doc'], r['sig'])
        sig_repeat[key] += 1
sig_repeat_out = [{'doc': k[0], 'sig': k[1], 'reads': v} for k, v in sig_repeat.most_common(12)]

# ---------- blind retries ----------
retry_groups = []
i = 0
while i < n:
    r = records[i]
    if not r['ok']:
        j = i + 1
        key = (r['action'], r['cmd'], r['doc'])
        while j < n and (records[j]['ts'] - records[j - 1]['ts']).total_seconds() <= 30 and \
                (records[j]['action'], records[j]['cmd'], records[j]['doc']) == key:
            j += 1
        if j - i >= 2:
            retry_groups.append({'start': r['ts'].isoformat(), 'action': r['action'], 'cmd': r['cmd'],
                                 'attempts': j - i, 'err': r['err'][:100]})
        i = j
    else:
        i += 1

# ---------- saves ----------
save_by_doc = collections.defaultdict(list)
for r in records:
    if r['action'] == 'schematic.save':
        save_by_doc[r['doc']].append((r['ts'], r['ms'], r['ok'], r['cmd']))
dupsave = []
for d, saves in save_by_doc.items():
    saves.sort()
    for k in range(1, len(saves)):
        gap = (saves[k][0] - saves[k - 1][0]).total_seconds()
        if gap <= 30:
            dupsave.append({'doc': d, 'gap_s': round(gap, 1), 'first': saves[k - 1][0].isoformat(),
                            'second': saves[k][0].isoformat(), 'ms': saves[k][1]})

# ---------- document opens / switches ----------
opens = [r for r in records if r['action'] == 'document.open']
open_seq = [{'ts': r['ts'].isoformat(), 'doc': r['doc']} for r in opens]
switch_rapid = 0
for k in range(1, len(open_seq)):
    if (parse_ts(open_seq[k]['ts']) - parse_ts(open_seq[k - 1]['ts'])).total_seconds() <= 10:
        switch_rapid += 1
open_counts = collections.Counter(r['doc'] for r in opens)

# ---------- probes vs mutations ----------
probe_calls = sum(1 for r in records if r['action'] in PROBE_ACTIONS)
probe_ms = sum(r['ms'] for r in records if r['action'] in PROBE_ACTIONS)
mut_calls = sum(1 for r in records if r['action'] in MUT_ACTIONS)
mut_ms = sum(r['ms'] for r in records if r['action'] in MUT_ACTIONS)
fail_calls = sum(1 for r in records if not r['ok'])

# ---------- payload sizes ----------
payload_by_action = collections.Counter()
for r in records:
    payload_by_action[r['action']] += r['linelen']

# ---------- long-call histogram ----------
bins = [(0, 200), (200, 500), (500, 1000), (1000, 2000), (2000, 5000), (5000, 10000),
        (10000, 30000), (30000, 60000), (60000, 10**9)]
hist = collections.Counter()
for r in records:
    for lo, hi in bins:
        if lo <= r['ms'] < hi:
            hist[f'{lo}-{hi}ms'] += 1
            break

out = {
    'window': {'from': records[0]['ts'].isoformat() if n else None,
               'to': records[-1]['ts'].isoformat() if n else None,
               'span_min': round(span / 60.0, 2)},
    'calls': n,
    'by_project_in_window': dict(byproj),
    'daemon_min': round(daemon / 60.0, 2),
    'think_min_gt2s': round(think / 60.0, 2),
    'failures': fail_calls,
    'probe_calls': probe_calls,
    'probe_seconds': round(probe_ms / 1000.0, 1),
    'probe_share_calls': round(probe_calls / n, 4) if n else 0,
    'mutation_calls': mut_calls,
    'mutation_seconds': round(mut_ms / 1000.0, 1),
    'result_mb': round(sum(r['linelen'] for r in records) / 1e6, 1),
    'actions': actions_out,
    'commands': cmd_out,
    'documents': doc_out,
    'buckets': buckets_out,
    'slowest': slow_out,
    'dup_reads_identical_within_120s': {'per_doc': dict(dup_reads), 'seconds': round(sum(dup_read_ms.values()) / 1000.0, 1),
                                       'examples': dup_examples},
    'identical_page_state_reads': sig_repeat_out,
    'blind_retry_groups': retry_groups[:30],
    'duplicate_saves_within_30s': dupsave,
    'document_opens': {'count': len(opens), 'rapid_switches_le10s': switch_rapid,
                       'per_doc': dict(open_counts), 'sequence': open_seq[:80]},
    'duration_histogram': dict(hist),
    'big_gaps_ge30s': [{'gap_s': round(g, 1), 'at': t, 'from': a, 'to': b} for g, t, a, b in big_gaps],
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

# compact digest to stdout
print('calls', n, 'span_min', out['window']['span_min'], 'daemon_min', out['daemon_min'],
      'think_min_gt2s', out['think_min_gt2s'], 'fail', fail_calls,
      'probes', probe_calls, f"({round(probe_calls/n*100,1)}%)", 'probe_s', out['probe_seconds'],
      'mutations', mut_calls, 'result_mb', out['result_mb'])
print('\nTOP ACTIONS (seconds):')
for a in actions_out[:14]:
    print(f"  {a['action']:34s} calls={a['calls']:5d} fail={a['failures']:4d} s={a['seconds']:8.1f} "
          f"med={a['median_ms']:7.1f} p95={a['p95_ms']:8.1f} max={a['max_ms']:7d} mb={a['payload_mb']}")
print('\nTOP COMMANDS (seconds):')
for c in cmd_out[:10]:
    print(f"  {c['command']:32s} rec={c['records']:5d} clients={c['clients']:4d} s={c['seconds']:8.1f} fail={c['failures']}")
print('\nTOP DOCUMENTS (seconds):')
for d in doc_out[:8]:
    print(f"  {d['document']:22s} rec={d['records']:5d} s={d['seconds']:8.1f} lists={d['lists']:4d} "
          f"list_s={d['list_seconds']:7.1f} places={d['places']:3d} conn={d['connects']:4d} saves={d['saves']:2d} opens={d['opens']:3d}")
print('\nBUCKETS:')
for b in buckets_out:
    print(f"  {b['bucket']} rec={b['records']:4d} s={b['seconds']:7.1f} fail={b['failures']:3d} "
          f"lists={b['lists']:4d}/{b['list_seconds']:6.1f}s place={b['places']:3d} conn={b['connects']:4d} save={b['saves']}")
print('\nSLOWEST:')
for s in slow_out[:12]:
    print(f"  {s['ts'][11:19]} {s['action']:30s} {s['ms']:7d}ms {s['cmd'][:28]}")
print('\nDUP READS identical <=120s:', out['dup_reads_identical_within_120s']['per_doc'],
      'seconds', out['dup_reads_identical_within_120s']['seconds'])
print('IDENTICAL STATE READS:', sig_repeat_out[:6])
print('BLIND RETRIES:', retry_groups[:8])
print('DUP SAVES <=30s:', dupsave[:8])
print('OPENS:', out['document_opens']['count'], 'rapid<=10s', switch_rapid)
print('HIST:', dict(hist))
print('BIG GAPS:', out['big_gaps_ge30s'][:6])
