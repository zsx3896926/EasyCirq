"""读 easycirq 的 JSON 输出，兼容两种形状。

为什么要这个：本仓库的 CLI 输出**不是统一信封**。
  - `sch list` / `sch connectivity` / `pcb drc`  → {"ok":..., "result": {...}}
  - `pcb dump`                                  → 直接就是 {"components":[...]}
按一种形状写解析器，遇到另一种就静默返回空（`d.get("result") or {}` → {}），
看起来像"板子上什么都没有"，而不是解析错了。

这一条在本会话里已经造成两次误判，所以固化成函数。
"""
import json
import subprocess


def run_json(args, timeout=240):
    """跑一条 easycirq 命令，返回 (payload, raw_text)。

    payload 统一成"真正的数据"：有 result 就是 result，否则就是整个对象。
    """
    proc = subprocess.run(["easycirq", *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        raise RuntimeError(f"没有 JSON 输出；rc={proc.returncode}；"
                           f"stderr={(proc.stderr or '')[:200]}")
    data = json.loads(raw[start:])
    payload = data.get("result") if isinstance(data.get("result"), dict) else data
    return payload, raw


def pcb_state(project="Fan-Controller-12V", doc="PCB1"):
    payload, _ = run_json(["--project", project, "--doc", doc, "pcb", "dump"])
    comps = payload.get("components") or []
    tracks = payload.get("tracks") or []
    vias = payload.get("vias") or []
    routed = {}
    for track in tracks:
        net = track.get("net") or ""
        if net:
            routed[net] = routed.get(net, 0) + 1
    return comps, tracks, vias, routed


if __name__ == "__main__":
    comps, tracks, vias, routed = pcb_state()
    print(f"器件 {len(comps)}  走线段 {len(tracks)}  过孔 {len(vias)}")
    print("已布线的网络:", sorted(routed))
    print("器件位号:", sorted(c.get("designator") for c in comps))
