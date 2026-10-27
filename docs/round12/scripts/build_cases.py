#!/usr/bin/env python3
"""Build the three round-12 feedback cases and the case index.

Every case records only the verification levels actually executed in this
round.  Structural evidence comes from the offline benchmark and the frozen
fixtures; host readback, ERC/DRC, simulation, manufacturing and physical are
``not_run`` because the user stopped real EDA work before any write.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / 'design-hardware' / 'scripts'
CASES = ROOT / 'design-hardware' / 'cases'
LIBRARY = CASES / 'feedback-r12'
sys.path.insert(0, str(SCRIPTS))

from feedback import cases as case_lib  # noqa: E402

BENCH = 'benchmarks/offline-round12/result.json'
MATRIX = 'docs/round12/acceptance-matrix.md'
BOARD = 'tests/fixtures/feedback/board-before.json'
SCH = 'tests/fixtures/feedback/schematic-before.json'


def level(status, *evidence):
    return {'status': status, 'evidence': list(evidence)}


def evidence(role, path, note=''):
    item = {'kind': 'file', 'role': role, 'path': path}
    if note:
        item['note'] = note
    return item


def not_run_levels():
    return {
        'structural': level('pass', evidence('benchmark', BENCH),
                            evidence('fixture', BOARD)),
        'host_readback': level('not_run'),
        'erc_drc': level('not_run'),
        'simulation': level('not_run'),
        'manufacturing': level('not_run'),
        'physical': level('not_run'),
    }


def base_case(**overrides):
    case = case_lib.case_template()
    case.update({
        'version': 1,
        'provenance': {
            'source_project': 'photo-led-pcb-20261026',
            'source_case': 'round12-offline',
            'artifacts': [
                'tests/fixtures/feedback/board-before.json',
                'tests/fixtures/feedback/schematic-before.json',
                'benchmarks/offline-round12/result.json',
            ],
            'verified_at': '2026-10-27',
            'stale': False,
        },
        'tool_versions': {
            'easyeda_host': '4.1.78 (observed, not written)',
            'easyeda_cli': '1.15.0 (observed) / fake 1.15.0-sim (offline)',
            'connector': '1.15.0 (observed)',
            'skill': '0.9.3',
        },
        'verification_levels': not_run_levels(),
        'source_tier': 'project-local',
    })
    case.update(overrides)
    return case


def build_schematic_case():
    case = base_case(
        id='sch-text-overlap-photo-led',
        goal='消除原理图功能区标题与说明文字重叠，同时保持全部网络端点与器件身份不变',
        applies_when={
            'power_w': {'min': None, 'max': None},
            'interfaces': [],
            'topologies': ['sheet-with-zone-labels'],
            'footprints': [],
            'layers': [],
            'process': '',
            'tags': ['schematic', 'readability', 'text-overlap'],
            'device': {},
        },
        does_not_apply_when=[
            '要移动的对象是网络标签、端口或引脚名（会改变连通语义）',
            '目标位置与任何可见文字或器件本体重叠',
            '文本 primitiveId 或坐标已变化（必须重新观察）',
            '页面图幅或分区结构不同（不是同一排版条件）',
        ],
        inputs=[
            evidence('before-schematic', SCH, 'frozen official read'),
            evidence('before-drc', 'docs/round12/evidence/live-baseline/copy-sch-drc.json'),
        ],
        original_problem=(
            '功能区标题 “2 光敏检测” (primitiveId ed1db1e2379b6cfd, 42,792) 与说明文字 '
            '“GL5528与4.7k分压，C4滤波；光照越强电压越高” (primitiveId '
            '7000fc9074f2508d, 42,778) 重叠 55.01×12.00 raw；其余网络检查正常。'),
        method=(
            '先用官方 visible_text.bboxes 与页面图元确认重叠双方的身份/位置；只移动说明文字到'
            '经几何检查的空位；移动前后分别读取 sch read，比较 designator.pin→net 端点集合；'
            '再用官方 text.move 的逐文本回读确认。'),
        before_after={
            'before': '标题与说明文字重叠 55.01×12.00 raw；网络端点集合作为基线',
            'after': '文字重叠 0；端点集合不变；器件身份不变；只允许该文本 primitiveId 的位置变化',
            'changes': [
                {'object': '7000fc9074f2508d', 'field': 'x/y',
                 'before': [42, 778], 'after': 'verified-free target'},
            ],
        },
        check_method=[
            'official schematic.visible_text.bboxes (before/after)',
            'sch read designator.pin→net endpoint set compare',
            'sch design-diff identity/connectivity',
            'scope diff: only the named text may change',
        ],
        evidence=[
            evidence('benchmark', BENCH, 'offline acceptance result'),
            evidence('matrix', MATRIX),
            evidence('fixture', SCH),
        ],
        limits=[
            '本轮未在真实宿主执行 text.move；host_readback/save/reopen 全部 NOT RUN',
            '4.1.78 下自由文本修改能否在重开后保留未实测；旧记录提示 text_modify 可能只在内存生效',
            '离线重叠宽度来自 layout-score 的估算文本带，不是官方导出图的像素测量',
        ],
        failed_attempts=[
            '直接把多个器件移到同一建议坐标 (330,245) 会互相重叠，已拒绝',
            '只比较网络数量或文件哈希不能证明连接保持，已改用端点集合',
        ],
        invalidation_conditions=[
            '文本 primitiveId、坐标或字号变化',
            '页面图幅/分区变化导致目标位置不再空闲',
            '目标文本被改成网络标签或端口',
            'Skill/CLI/宿主版本变化后未重跑结构检查',
        ],
    )
    return case


def build_decap_case():
    case = base_case(
        id='pcb-decap-c2-local-photo-led',
        goal='在电源区内把去耦电容 C2 移到 U1.8(+5V) 的 100mil 内，只重布 C2 的 +5V/GND 局部短线',
        applies_when={
            'power_w': {'min': 0, 'max': 5},
            'interfaces': ['KF301-2P', '2-pin-terminal'],
            'topologies': ['linear-5v', 'comparator-hysteresis'],
            'footprints': ['RAD104'],
            'layers': [2],
            'process': 'JLC 2-layer 1.6mm',
            'tags': ['pcb', 'power', 'decoupling', 'local-edit'],
            'device': {'designator': 'C2', 'value': '100nF', 'ic': 'LM358P'},
        },
        does_not_apply_when=[
            'C2 实际是 bulk 电容（≥1µF）而不是去耦电容',
            '目标板不是 2 层，或 U1 不是 LM358P/DIP-8 同脚位',
            'C2 的封装不是 RAD104 或引脚间距不同',
            '电源电流/温升要求超出 5V 小信号板条件',
            '锁定连接器、板框或安装孔落在可写范围内',
        ],
        inputs=[
            evidence('before-board', BOARD, 'frozen pcb dump with copper'),
            evidence('before-check', 'docs/round12/evidence/live-baseline/copy-pcb-check-before.json'),
        ],
        original_problem=(
            '原生 DRC passed=true total=0，但 pcb check 报告 decap-too-far：C2 距最近的 '
            '+5V 引脚 U1.8 150mil（>100mil）；同时 C1(10µF bulk) 890mil 被记录为可接受，'
            '因为它是 bulk 而非去耦。该案例证明 DRC 0 不等于工程质量通过。'),
        method=(
            '观察 dump + check → 只把 C2 与它的 +5V/GND 局部铜作为可写对象 → 预检目标位置/'
            '与 U1 本体间距 → 一次受控 apply（move + 局部 track）→ 回读 diff 检查范围外变化=0、'
            'J1 锁定/板框/孔位/其他网络不变 → 重新跑 check 确认 C2 距离改善。'),
        before_after={
            'before': 'C2 距 U1.8 150mil；DRC 0；C1 bulk 890mil 保留并记录理由',
            'after': 'C2 距 U1.8 ≤100mil（候选位置需真实 DRC 复核）；范围外变化 0；'
                     'J1/板框/孔位/其他网络不变',
            'changes': [
                {'object': 'C2', 'field': 'pose',
                 'before': [1546.84, 1500, 0], 'after': 'scoped candidate'},
                {'object': 'C2/+5V,GND', 'field': 'local copper',
                 'before': 'existing stubs', 'after': 'replaced local stubs only'},
            ],
        },
        check_method=[
            'pcb check decap-too-far before/after',
            'scope diff: unrelated changes = 0',
            'locked J1 / outline / holes invariant',
            'pad-net map invariant',
            'native DRC (NOT RUN in this round; simulated value is not evidence)',
        ],
        evidence=[
            evidence('benchmark', BENCH),
            evidence('matrix', MATRIX),
            evidence('fixture', BOARD),
        ],
        limits=[
            '真实宿主未执行 move/track/save/reopen；全部 NOT RUN',
            'PCB 写入需携带原始 pcb dump（plan.before_dump）；只用规范化 observation 重建的铺铜不完整',
            '候选位置只做结构/范围检查，未在真实 DRC 下复核间距与铜连接',
            '离线 DRC/check 为模拟值，不能当作 erc_drc 通过',
        ],
        failed_attempts=[
            '把 C1(10µF bulk) 也搬到 IC 旁会破坏输入储能/纹波条件，已拒绝',
            '按“所有去耦都必须 ≤100mil”的统一阈值处理 bulk 电容是错误规则',
        ],
        invalidation_conditions=[
            'C1/C2 的值或封装变化（bulk/去耦角色可能互换）',
            'U1 或引脚/封装变化',
            '板层数、电源拓扑或电流范围变化',
            'J1 锁定状态、板框或孔位变化',
            '真实 DRC/check 未重跑',
        ],
    )
    return case


def build_locked_case():
    case = base_case(
        id='pcb-locked-connector-preserve-photo-led',
        goal='保留锁定连接器 J1、板框与安装孔，只移动指定相邻器件/局部铜',
        applies_when={
            'power_w': {'min': 0, 'max': 5},
            'interfaces': ['KF301-2P', '2-pin-terminal'],
            'topologies': ['edge-connector'],
            'footprints': ['KF301-2P'],
            'layers': [2],
            'process': 'JLC 2-layer 1.6mm',
            'tags': ['pcb', 'mechanical', 'locked-interface', 'local-edit'],
            'device': {'designator': 'J1'},
        },
        does_not_apply_when=[
            'J1 不是锁定件，或用户要求改连接器位置/朝向',
            '板框、安装孔或禁布区需要修改',
            '目标修改需要跨到连接器所在网络或区域',
        ],
        inputs=[
            evidence('before-board', BOARD),
            evidence('before-check', 'docs/round12/evidence/live-baseline/copy-pcb-check-before.json'),
        ],
        original_problem=(
            'J1(KF301-2P) 被 pcb lock 固定在左板边 rotation 270，开口朝外；任何局部布局'
            '优化都必须证明它、板框和 4×M3 孔位没有被移动。'),
        method=(
            '把 J1/outline/holes 设为不可写并作为不变量；只允许指定相邻对象/网络；'
            '写前校验白名单，写后 diff 检查 locked/outline/holes/pad-net/unrelated=0。'),
        before_after={
            'before': 'J1 locked=true, x=250,y=550,rotation=-90；outline 3543.3×2362.2 mil',
            'after': 'J1/outline/holes 完全不变；仅白名单对象/网络变化；unrelated=0',
            'changes': [],
        },
        check_method=[
            'scope diff: locked/outline/holes invariants',
            'pad-net map invariant',
            'unrelated changes = 0',
        ],
        evidence=[
            evidence('benchmark', BENCH),
            evidence('matrix', MATRIX),
            evidence('fixture', BOARD),
        ],
        limits=[
            '本轮未执行真实移动；host_readback NOT RUN',
            '连接器插拔空间/开口方向只按 dump 字段核对，未做实机插拔',
        ],
        failed_attempts=['把 J1 当成可移动件参与对齐会破坏锁定接口，已拒绝'],
        invalidation_conditions=[
            'J1 锁定状态或位号变化',
            '板框/孔位变化',
            '连接器型号或朝向变化',
        ],
    )
    return case


def main():
    LIBRARY.mkdir(parents=True, exist_ok=True)
    cases = [build_schematic_case(), build_decap_case(), build_locked_case()]
    for case in cases:
        case_lib.validate_case(case)
        path = LIBRARY / (case['id'] + '.json')
        path.write_text(json.dumps(case, ensure_ascii=False, indent=1) + '\n',
                        encoding='utf-8')
        print('wrote', path)
    # Index base is design-hardware/cases so entry paths are
    # feedback-r12/<id>.json; other project cases are not hds-case/v1 and are
    # ignored by the scanner.
    index = case_lib.create_index(library=str(CASES))
    index_path = CASES / 'index.json'
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n',
                          encoding='utf-8')
    print('index', index_path, len(index.get('cases') or []))


if __name__ == '__main__':
    main()
