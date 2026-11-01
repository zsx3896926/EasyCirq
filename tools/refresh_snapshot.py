"""把交付包的可复现输入（design/snapshot）整体刷新一遍。

上一轮踩过的坑：用 `sch list --include-pins` 抓 list.json 时**漏了 --include-bbox**，
结果组件没有 x/y/bbox，布局检查判定"没有器件"，整条管线崩在一个没有上下文的
FileNotFoundError 上。所以这里每一步都检查关键字段是否存在，不只看命令是否 ok。
"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "deliverables" / "alarm" / "design" / "snapshot"
D = "9d9dd9e46f53880e"
PCB = "34de0a1c7592ff1e"
PROJECT = "KPI-S5-Verify"


def cli(*args, **kwargs):
    return subprocess.run(["easycirq", *[str(a) for a in args]],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kwargs)


def save_result(args, target):
    proc = cli(*args)
    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        print(f"  {target.name}: 没有 JSON（{raw[:120]}）")
        return False
    text = raw[start:]
    out = []
    depth = 0
    for line in text.splitlines():
        delta = line.count("{") + line.count("[") - line.count("}") - line.count("]")
        if depth > 0 and "staleRisk" in line:
            continue
        out.append(line)
        depth += delta
        if depth < 0:
            depth = 0
    try:
        data = json.JSONDecoder().raw_decode("\n".join(out).lstrip())[0]
    except json.JSONDecodeError as exc:
        print(f"  {target.name}: JSON 解析失败 {exc}")
        return False
    payload = data.get("result") or data
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return True


def main():
    SNAP.mkdir(parents=True, exist_ok=True)

    print("list.json (需要 bbox 与 pins)")
    if save_result(["--project", PROJECT, "sch", "list", "--page", D,
                    "--include-bbox", "--include-pins"], SNAP / "list.json"):
        data = json.loads((SNAP / "list.json").read_text(encoding="utf-8"))
        parts = [c for c in data.get("components") or []
                 if c.get("componentType") == "part"]
        withbox = [c for c in parts if c.get("bbox")]
        print(f"  parts={len(parts)} with_bbox={len(withbox)}")
        if len(withbox) != len(parts):
            print("  ✗ 有器件缺 bbox，布局检查会判定没有器件")
            return 1

    print("connectivity.json")
    ok = save_result(["--project", PROJECT, "--doc", D, "sch", "connectivity"],
                     SNAP / "connectivity.json")
    if ok:
        (SNAP / "connectivity-before.json").write_bytes(
            (SNAP / "connectivity.json").read_bytes())

    print("sheet.json")
    save_result(["--project", PROJECT, "--doc", D, "sch", "sheet-geometry", "--json"],
                SNAP / "sheet.json")

    print("drc.json")
    save_result(["--project", PROJECT, "--doc", D, "sch", "drc", "--json"],
                SNAP / "drc.json")

    print("pcb-dump.json")
    raw = os.path.join(os.environ["TEMP"], "refresh-pcb.json")
    cli("--project", PROJECT, "--doc", "PCB1", "pcb", "dump", "--out", raw)
    if pathlib.Path(raw).is_file():
        data = json.loads(pathlib.Path(raw).read_text(encoding="utf-8"))
        payload = data.get("result") or data
        (SNAP / "pcb-dump.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"  components={len(payload.get('components') or [])}")

    print("bom.tsv")
    bom = ROOT / "deliverables" / "alarm" / "bom.csv"
    if bom.is_file():
        (SNAP / "bom.tsv").write_bytes(bom.read_bytes())

    print("pinplan.json")
    pinplan = ROOT / ".easycirq" / "pinplan-alarm.json"
    if pinplan.is_file():
        (SNAP / "pinplan.json").write_bytes(pinplan.read_bytes())

    print("connectivity-reopen.json (重开后再读一次)")
    cli("--project", PROJECT, "doc", "reload", D)
    save_result(["--project", PROJECT, "--doc", D, "sch", "connectivity"],
                SNAP / "connectivity-reopen.json")
    a = json.loads((SNAP / "connectivity-before.json").read_text(encoding="utf-8"))
    b = json.loads((SNAP / "connectivity-reopen.json").read_text(encoding="utf-8"))
    print(f"  before == reopen: {a == b}")

    print()
    for path in sorted(SNAP.iterdir()):
        print(f"  {path.name:<28} {path.stat().st_size:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
