"""从 pcb drc --json 的输出里取判定。

已知缺陷：这个命令会把一行人类摘要插到 JSON 中间，例如

    "param": { "obj1": "Object 1", "type": "ConnectError"
    pcb drc: native verdict failed; inspect the returned violations
    }, ...

于是 json.loads 直接失败。这里的做法是逐行尝试：只保留能被"括号平衡"接受的
行，遇到不平衡就丢掉那一行。比正则猜格式可靠。
"""
import json
import os
import pathlib
import sys


def strip_intruders(text):
    lines = text.splitlines()
    out = []
    depth = 0
    for line in lines:
        delta = line.count("{") + line.count("[") - line.count("}") - line.count("]")
        if depth > 0 and line.strip() and not line.strip().startswith('"') \
                and '":' not in line and delta == 0 and line.rstrip().endswith(tuple("abcdefghijklmnopqrstuvwxyz.")):
            # a plain sentence sitting inside the structure
            continue
        out.append(line)
        depth += delta
        if depth < 0:
            depth = 0
    return "\n".join(out)


def load(path):
    raw = pathlib.Path(path).read_text(encoding="utf-8-sig")
    start = raw.find("{")
    text = strip_intruders(raw[start:])
    decoder = json.JSONDecoder()
    return decoder.raw_decode(text.lstrip())[0]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["TEMP"], "drc.json")
    data = load(path)
    print("passed:", data.get("passed"), " total:", data.get("total"))
    violations = data.get("violations") or []
    kinds = {}
    for item in violations:
        name = item.get("ruleName") or item.get("rule") or "?"
        kinds[name] = kinds.get(name, 0) + 1
    print("by kind:", kinds)
    for item in violations[:6]:
        print(f"  - {item.get('ruleName')}: {str(item.get('message'))[:110]}")
    return 0 if data.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
