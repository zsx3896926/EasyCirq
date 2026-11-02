"""把风扇板的器件逐个放到 P1 上。

布局（1170x825 画幅）从左到右是信号流：传感 → 比较 → 驱动 → 负载。
先只放，不连线——连线要单独一步并且逐段核对。
"""
import json
import subprocess
import sys

PROJECT = "Fan-Controller-12V"
PAGE = "664436e68d969739"

# (位号, 查询词, x, y, 说明)
PLAN = [
    ("NTC1", "C9900004021", 200, 520, "10K NTC"),
    ("R1", "C25804", 200, 360, "10k 上拉 NTC_MID"),
    ("U1", "C504553", 480, 440, "LM393 比较器"),
    ("R2", "C25804", 400, 240, "阈值上臂 10k"),
    ("R3", "C23159", 520, 240, "阈值下臂 4.3k"),
    ("R6", "C23153", 620, 600, "回差反馈 39k"),
    ("R5", "C25803", 760, 300, "栅极上拉 100k"),
    ("R7", "C22775", 780, 440, "栅极串联 100Ω"),
    ("Q1", "C700953", 860, 560, "AO3400A NMOS"),
    ("D1", "C2892570", 960, 400, "1N4148W 续流"),
    ("FAN1", "C9900016027", 1060, 300, "风扇 2P 端子"),
]


def cli(*args, **kwargs):
    return subprocess.run(["easycirq", *[str(a) for a in args]],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kwargs)


def resolve(lcsc):
    proc = cli("lib", "search", lcsc, "--limit", "1")
    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        return None, f"查询无输出: {(raw or proc.stderr)[:120]}"
    try:
        data = json.loads(raw[start:])
    except json.JSONDecodeError as exc:
        return None, f"JSON 失败: {exc}"
    comps = (data.get("result") or {}).get("components") or []
    if not comps:
        return None, "没有结果"
    entry = comps[0]
    return (entry.get("libraryUuid"), entry.get("uuid")), None


def main():
    placed = []
    for designator, lcsc, x, y, note in PLAN:
        ident, err = resolve(lcsc)
        if err:
            print(f"✗ {designator} 解析失败: {err}")
            return 1
        lib, uuid = ident
        proc = cli("--project", PROJECT, "--doc", PAGE, "sch", "place",
                   "--lib", lib, "--uuid", uuid,
                   "--designator", designator, "--x", x, "--y", y, "--rotation", "0")
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = '"ok": true' in out
        print(f"{'✓' if ok else '✗'} {designator:6} @({x},{y})  {note}")
        if not ok:
            print("   ", out[:300].replace("\n", " "))
            return 1
        placed.append(designator)
    print()
    print(f"已放置 {len(placed)} 个：{', '.join(placed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
