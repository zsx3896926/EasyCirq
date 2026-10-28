"""Q01/Q02 benchmark catalog for the offline engine.

The 12 circuits follow the 12 template families, but the layouts here are
*abstract synthetic geometry*, not real EDA drawings.  They test whether the
checker reproduces a declared candidate on a fixed input.  The real geometry
case is the frozen temp-alarm bundle; the real netlist case is the F1 snapshot.
"""
from __future__ import annotations

from .templates import TEMPLATES

TITLES = {identity: data['title'] for identity, data in TEMPLATES.items()}


def _layout(page, components, texts, wires, title_block=None, module_frames=None,
            labels=None, attachments=None):
    data = {
        'coordinate_units': 'synthetic schematic units (0.01 inch)',
        'components': components,
        'texts': texts,
        'wires': wires,
        'page_bbox': [0, 0, page[0], page[1]],
        'expected_counts': {'components': len(components), 'texts': len(texts), 'wires': len(wires)},
        'policy': {'connection_tolerance': 2.0, 'max_wire_length': 500},
        'coverage': {'components': {'status': 'complete'}, 'texts': {'status': 'complete'},
                     'wires': {'status': 'complete'}},
    }
    if title_block:
        data['title_block'] = title_block
    if module_frames:
        data['module_frames'] = module_frames
    if labels:
        data['label_anchors'] = labels
    if attachments:
        data['attachment_points'] = attachments
    return data


def _case(identity, problem, expected, layout):
    return {
        'id': identity,
        'title': TITLES[identity],
        'domain': TEMPLATES[identity]['category'],
        'problem': problem,
        'expected_codes': expected,
        'evidence_level': 'synthetic_offline_geometry_not_real_eda',
        'layout': layout,
    }


def cases():
    result = []
    # 1. Power entry: two text boxes overlap.
    result.append(_case('power-entry', '输入保护区的两个注释文字重叠',
                        ['bbox_overlap'],
                        _layout((400, 300),
                                [{'id': 'F1', 'bbox': [40, 40, 60, 50]},
                                 {'id': 'D1', 'bbox': [80, 40, 100, 50]}],
                                [{'id': 't1', 'bbox': [40, 60, 80, 70]},
                                 {'id': 't2', 'bbox': [50, 62, 90, 72]}],
                                [])))
    # 2. LDO: wire crosses a body.
    result.append(_case('ldo', 'VIN 导线穿过 U1 本体',
                        ['wire_enters_bbox'],
                        _layout((400, 300),
                                [{'id': 'U1', 'bbox': [150, 100, 190, 140]}],
                                [],
                                [{'id': 'w1', 'points': [[120, 120], [220, 120]]}])))
    # 3. Buck: component outside page.
    result.append(_case('buck', '电感放在页面外',
                        ['outside_page'],
                        _layout((200, 150),
                                [{'id': 'L1', 'bbox': [220, 20, 250, 40]}],
                                [], [])))
    # 4. MCU: text over title block.
    result.append(_case('mcu-min', '标题文字压到图签',
                        ['overlaps_title_block'],
                        _layout((400, 300),
                                [{'id': 'U1', 'bbox': [40, 40, 80, 80]}],
                                [{'id': 't1', 'bbox': [300, 20, 340, 30]}],
                                [], title_block=[280, 10, 390, 50])))
    # 5. Crystal: wire crosses text.
    result.append(_case('crystal', '时钟导线穿过负载电容注释',
                        ['wire_enters_bbox'],
                        _layout((400, 300),
                                [{'id': 'Y1', 'bbox': [100, 100, 120, 120]}],
                                [{'id': 't1', 'bbox': [80, 130, 150, 140]}],
                                [{'id': 'w1', 'points': [[90, 135], [160, 135]]}])))
    # 6. Reset: module frames overlap.
    result.append(_case('reset-supervisor', '复位与按键分区框互相重叠',
                        ['module_frames_overlap'],
                        _layout((400, 300),
                                [{'id': 'U1', 'bbox': [40, 40, 60, 60]}],
                                [], [],
                                module_frames=[
                                    {'id': 'reset', 'bbox': [20, 20, 150, 120]},
                                    {'id': 'button', 'bbox': [100, 20, 200, 120]}])))
    # 7. USB-C: dangling wire endpoint.
    result.append(_case('usb-c-power', 'VBUS 短桩端点悬空',
                        ['dangling_wire_endpoint'],
                        _layout((400, 300),
                                [{'id': 'J1', 'bbox': [20, 100, 60, 140]}],
                                [],
                                [{'id': 'w1', 'points': [[60, 120], [150, 120]]}],
                                attachments=[{'id': 'p1', 'x': 60, 'y': 120, 'kind': 'pin'}])))
    # 8. I2C: label anchor off connection.
    result.append(_case('i2c-sensor', 'SDA 网名标签不在连接端上',
                        ['label_anchor_off_connection'],
                        _layout((400, 300),
                                [{'id': 'U1', 'bbox': [40, 40, 80, 80]}],
                                [],
                                [{'id': 'w1', 'net': 'SDA', 'points': [[80, 60], [160, 60]]}],
                                labels=[{'id': 'l1', 'net': 'SDA', 'x': 100, 'y': 100}])))
    # 9. Divider: different named wires cross.
    result.append(_case('divider-sense', '不同网络导线交叉',
                        ['different_named_wires_cross'],
                        _layout((400, 300),
                                [{'id': 'R1', 'bbox': [40, 40, 60, 60]}],
                                [],
                                [{'id': 'w1', 'net': 'A', 'points': [[20, 20], [200, 200]]},
                                 {'id': 'w2', 'net': 'B', 'points': [[20, 200], [200, 20]]}])))
    # 10. Comparator: text covers body.
    result.append(_case('opamp-comparator', '阈值文字压在比较器本体上',
                        ['bbox_overlap'],
                        _layout((400, 300),
                                [{'id': 'U1', 'bbox': [100, 100, 140, 140]}],
                                [{'id': 't1', 'bbox': [110, 110, 130, 120]}],
                                [])))
    # 11. MOS: frame member outside.
    result.append(_case('mos-load', 'MOS 分区框成员在框外',
                        ['frame_member_outside'],
                        _layout((400, 300),
                                [{'id': 'Q1', 'bbox': [40, 40, 60, 60]}],
                                [], [],
                                module_frames=[{'id': 'load', 'bbox': [20, 20, 100, 100],
                                                'contains': ['Q1']}])
                        | {'components': [{'id': 'Q1', 'bbox': [200, 200, 220, 220]}]}))
    # 12. RS485: same anchor has two net labels.
    result.append(_case('rs485-can', '同一连接点出现两个网名',
                        ['label_anchor_conflict'],
                        _layout((400, 300),
                                [{'id': 'U1', 'bbox': [40, 40, 80, 80]}],
                                [],
                                [{'id': 'w1', 'net': 'A', 'points': [[80, 60], [160, 60]]}],
                                labels=[{'id': 'l1', 'net': 'A', 'x': 120, 'y': 60},
                                        {'id': 'l2', 'net': 'B', 'x': 120, 'y': 60}])))
    return result


def _analyze(layout):
    import sys
    from pathlib import Path
    scripts = str(Path(__file__).resolve().parents[1])
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import sch_layout_check
    return sch_layout_check.analyze(layout)


def run():
    rows = []
    for case in cases():
        result = _analyze(case['layout'])
        observed = sorted({finding['code'] for finding in result['findings']})
        missing = sorted(set(case['expected_codes']) - set(observed))
        rows.append({'id': case['id'], 'title': case['title'], 'domain': case['domain'],
                     'expected_codes': case['expected_codes'], 'observed_codes': observed,
                     'missing': missing, 'status': 'passed' if not missing else 'missing_candidates',
                     'evidence_level': case['evidence_level'],
                     'electrical_verified': False, 'visual_verified': False})
    failed = [row for row in rows if row['missing']]
    return {'status': 'ok' if not failed else 'missing_candidates', 'total': len(rows),
            'passed': len(rows) - len(failed), 'failed': len(failed), 'cases': rows,
            'coverage': 'synthetic geometry only; real temp-alarm/F1 cases are listed separately',
            'not_checked': ['real EDA import', 'electrical connectivity', 'visual review']}
