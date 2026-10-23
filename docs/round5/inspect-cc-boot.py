"""One-off: resolve CC resistor and boot-pin net mapping from the frozen v3 snapshot."""
import json

snap = json.load(open('docs/evidence/f1-b-2026-10-22/v3-snapshot-final.json', encoding='utf-8'))
snap = snap.get('snapshot', snap)
parts = {p['designator']: p for p in snap.get('parts') or []}

for des in ('R101', 'R102', 'R103', 'R104', 'R105', 'SW101', 'SW102', 'U101', 'J101'):
    p = parts.get(des)
    if not p:
        print(des, ': MISSING')
        continue
    pins = p.get('pins') or []
    print(des, p.get('component', {}).get('name'))
    for pin in pins:
        print('   pin', pin.get('number'), pin.get('name'), '-> net', pin.get('net'))
