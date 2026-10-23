"""Append the corrected-baseline results to the L evaluation report."""
import json
import sys

src, report = sys.argv[1], sys.argv[2]
d = json.loads(open(src, encoding='utf-8', errors='replace').read())
res = d.get('result', d)
base = res.get('baselines', [])
judge = res.get('judgments', [])
prompts = {
    's1': '我想做一个能测房间温度、手机能看的小东西，你帮我搞定。',
    's2': '我需要一个 5V 输入转 3.3V 给传感器供电的模块，帮我设计一下。',
    's3': '把 F1 板上的 LED 限流电阻 R106 从 1k 改成 470R。',
    's4': '10µF 25V 的电容现在没货了，帮我找个能用的替代。',
    's5': '我不想要 Wi-Fi 了，想把 F1 改成只用有线串口通信。',
    's6': '帮我在 EDA 里把 R106 改成 470R 并保存。',
}
parts = ['', '---', '', '# 校正实验：真正的无 Skill 基线（2026-10-23 追加）', '',
         '条件：基线 agent 明确禁止读取任何本地文件（提示词声明无仓库/无 Skill/无资料），只凭通用知识作答；',
         '与首轮记录的 with-skill 答案匿名盲评。A/B 分配：奇数编号场景（s1/s3/s5）A=基线、B=skill；',
         '偶数编号场景（s2/s4/s6）A=skill、B=基线。', '']
wins = {'skill': 0, 'base': 0, 'tie': 0}
for item in base:
    sid = item.get('scenario', '')
    sid_key = next((k for k in prompts if item.get('scenario', '').startswith(k)), None)
    parts.append(f'## {item.get("scenario", "")[:40]}…')
    parts.append('')
    parts.append('### 校正基线回答')
    parts.append('')
    parts.append(item.get('answer', '(missing)'))
    parts.append('')
for j in judge:
    sid = j.get('scenario', '')
    key = next((k for k in prompts if sid.startswith(k)), None)
    if not key:
        continue
    i = list(prompts).index(key)
    skill_is_a = i % 2 == 1
    winner = j.get('winner')
    condition = 'tie'
    if winner in ('A', 'B'):
        condition = 'skill' if (winner == 'A') == skill_is_a else 'base'
    wins[condition] += 1
    parts.append(f'## {key} — {prompts[key]}')
    parts.append('')
    parts.append(f'盲评：winner={winner} → **{condition}**（A=' + ('skill' if skill_is_a else 'base') + '）')
    parts.append('')
    parts.append('```json')
    parts.append(json.dumps(j.get('scores'), ensure_ascii=False, indent=1))
    parts.append('```')
    parts.append('')
    parts.append('理由：' + str(j.get('reason', '')))
    parts.append('')
parts.append(f'## 校正实验小结：skill 胜 {wins["skill"]}/6，基线胜 {wins["base"]}/6，平局 {wins["tie"]}/6')
parts.append('')
parts.append('唯一由基线取胜的 s2 暴露了一个真实缺口：skill 答案没有追问「传感器是否允许 3.3V 供电/是否为 5V 比率输出」，')
parts.append('而基线追问了这一点。已据此在 `design-cards/power/p01-ldo.md` 的「必要输入」表补入「负载的供电/接口电平」')
parts.append('（重要项），并做 s2 复测（见下节）。')
parts.append('')
open(report, 'a', encoding='utf-8').write('\n'.join(parts))
print('appended; wins', wins)
