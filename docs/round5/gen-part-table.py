"""One-off: build the C-package per-designator evidence table from the frozen
v3 schematic snapshot, overlaid with the round-3 selected-parts.json."""
import json

snap = json.load(open('docs/evidence/f1-b-2026-10-22/v3-snapshot-final.json', encoding='utf-8'))
snap = snap.get('snapshot', snap)
sel = json.load(open('docs/evidence/f1-rev3-2026-10-22/selected-parts.json', encoding='utf-8'))

rows = []
for p in snap.get('parts') or []:
    des = p.get('designator')
    comp = (p.get('component') or {}).get('name')
    fp = (p.get('footprint') or {}).get('name')
    sup = p.get('supplier_id')
    mfr = p.get('manufacturer') or ''
    extra = sel.get(des) or {}
    props = extra.get('other_property') or {}
    rows.append({
        'designator': des,
        'component_name': comp,
        'footprint': fp,
        'supplier_id': sup or (extra.get('supplier_id') or ''),
        'manufacturer': mfr or (extra.get('manufacturer') or ''),
        'mpn': (extra.get('manufacturer_id') or mfr or comp or ''),
        'value': props.get('Value', ''),
        'rating': props.get('Voltage Rating', ''),
        'datasheet': props.get('Datasheet', ''),
        'lcsc_class': props.get('JLCPCB Part Class', ''),
        'source': 'selected-parts.json' if extra else 'schematic snapshot only',
    })

rows.sort(key=lambda r: (r['designator'] or ''))
print('| 位号 | 库器件名 | 封装 | C号 | 厂商 | MPN | 值/额定 | 数据手册 | 证据来源 |')
print('|---|---|---|---|---|---|---|---|---|')
for r in rows:
    ds = r['datasheet'] or '待查'
    mfr = r['manufacturer'] or '待查'
    val = '/'.join(x for x in (r['value'], r['rating']) if x) or '待查'
    print('| %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
        r['designator'], r['component_name'], r['footprint'], r['supplier_id'] or '待查',
        mfr, r['mpn'], val, ds, r['source']))
print()
missing_mpn = [r['designator'] for r in rows if not r['manufacturer'] or r['manufacturer'] == '待查']
missing_c = [r['designator'] for r in rows if not r['supplier_id']]
print('rows:', len(rows), '| missing manufacturer:', missing_mpn, '| missing C-number:', missing_c)
json.dump(rows, open('docs/round5/part-table-raw.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
