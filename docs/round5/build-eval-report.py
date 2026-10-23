"""Build the L-package evaluation report from a completed workflow journal."""
import json
import sys
from collections import OrderedDict

journal = sys.argv[1]
out_path = sys.argv[2]

prompts = {
    's1': '我想做一个能测房间温度、手机能看的小东西，你帮我搞定。',
    's2': '我需要一个 5V 输入转 3.3V 给传感器供电的模块，帮我设计一下。',
    's3': '把 F1 板上的 LED 限流电阻 R106 从 1k 改成 470R。',
    's4': '10µF 25V 的电容现在没货了，帮我找个能用的替代。',
    's5': '我不想要 Wi-Fi 了，想把 F1 改成只用有线串口通信。',
    's6': '帮我在 EDA 里把 R106 改成 470R 并保存。',
}

labels = {}
rows = OrderedDict()
for line in open(journal, encoding='utf-8', errors='replace'):
    line = line.strip()
    if not line.startswith('{'):
        continue
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        continue
    if rec.get('type') == 'started':
        labels[rec.get('key')] = rec.get('label')
    elif rec.get('type') == 'result':
        label = labels.get(rec.get('key')) or rec.get('agentId')
        res = rec.get('result')
        if label and res:
            rows[label] = res

parts = ['# L 包 Agent 行为评测（2026-10-23）', '',
         '条件：`skill` = 先阅读 design-hardware/SKILL.md 后作答；`base` = 同提示词、无 Skill。',
         '评审为匿名 A/B 盲评（奇数场景 A=skill，偶数场景 A=base，报告中按实际条件还原）。', '']

for sid, prompt in prompts.items():
    with_skill = rows.get(sid + ':skill')
    baseline = rows.get(sid + ':base')
    judge = rows.get(sid + ':judge')
    parts.append(f'## {sid} — {prompt}')
    parts.append('')
    parts.append(f'### with-skill（{"ok" if with_skill else "MISSING"}）')
    parts.append('')
    parts.append(with_skill.get('answer', '(missing)') if isinstance(with_skill, dict) else '(missing)')
    parts.append('')
    parts.append(f'### baseline（{"ok" if baseline else "MISSING"}）')
    parts.append('')
    parts.append(baseline.get('answer', '(missing)') if isinstance(baseline, dict) else '(missing)')
    parts.append('')
    if isinstance(judge, dict):
        parts.append(f"### 盲评：winner={judge.get('winner')}")
        parts.append('')
        parts.append('```json')
        parts.append(json.dumps(judge.get('scores'), ensure_ascii=False, indent=1))
        parts.append('```')
        parts.append('')
        parts.append('理由：' + str(judge.get('reason', '')))
    else:
        parts.append('### 盲评：MISSING')
    parts.append('')

with open(out_path, 'w', encoding='utf-8') as handle:
    handle.write('\n'.join(parts))
print('wrote', out_path, 'rows', len(rows))
