import json
import pathlib

p = pathlib.Path("distribution/toolchain.json")
if not p.is_file():
    print("没有 toolchain.json")
    raise SystemExit

d = json.loads(p.read_text(encoding="utf-8"))
print("顶层键:", sorted(d))
text = json.dumps(d, ensure_ascii=False)
print("提到 python:", "python" in text.lower())

# 找 python 相关
for line in text.split(","):
    if "python" in line.lower():
        print("  ", line.strip()[:120])
