"""读 DRC 违规的具体内容：到底哪两类对象、哪两个网络在打架。

上一轮只知道"17 项 clearance"，不知道具体是谁跟谁。不看清就调参，等于瞎试
（上轮把 gap 从默认加到 120，违规从 17 变成 30，就是瞎试的代价）。
"""
import collections
import json
import subprocess


def dump(args):
    proc = subprocess.run(["easycirq", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)
    raw = proc.stdout or ""
    start = raw.find("{")
    return json.loads(raw[start:])


d = dump(["--project", "Fan-Controller-12V", "--doc", "PCB1", "pcb", "drc"])
payload = d.get("result") if isinstance(d.get("result"), dict) else d
print("passed:", payload.get("passed"))

pairs = collections.Counter()
samples = []
def walk(node):
    if isinstance(node, dict):
        if "errorObjType" in node:
            pairs[node.get("errorObjType")] += 1
            if len(samples) < 6:
                data = (node.get("explanation") or {}).get("errData") or {}
                samples.append({
                    "type": node.get("errorObjType"),
                    "err": node.get("errorType"),
                    "a": data.get("obj1Suffix"),
                    "b": data.get("obj2Suffix"),
                    "clearance": data.get("clearance"),
                    "minDistance": data.get("minDistance"),
                })
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)

walk(payload.get("violations") or [])
print("按对象类型:", dict(pairs))
print()
for s in samples:
    print(" ", json.dumps(s, ensure_ascii=False))

rules = dump(["--project", "Fan-Controller-12V", "--doc", "PCB1", "pcb", "drc-rules"])
rp = rules.get("result") if isinstance(rules.get("result"), dict) else rules
print()
print("DRC 规则里的间距:", {k: v for k, v in rp.items()
                          if "learance" in str(k) or "idth" in str(k)})
