"""全链路证据：CLI → daemon → 连接器 → EasyEDA 客户端 → 真实数据。"""
import json
import subprocess


def run(cmd):
    p = subprocess.run(["easycirq", *cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def parse(out):
    i = out.find("{")
    if i < 0:
        return None
    try:
        return json.loads(out[i:])
    except Exception:  # noqa: BLE001
        return None


# 先用 doc ls 拿真实窗口与页面
rc, out = run(["doc", "ls", "--project", "Fan-Controller-12V"])
print(f"--- easycirq doc ls (exit {rc}) ---")
print("  ", " ".join(out.strip().split())[:180])
print()

rc, out = run(["doc", "ls"])
d = parse(out)
win = None
if d and d.get("ok"):
    rows = (d.get("result") or {}).get("documents") or []
    for row in rows:
        if row.get("type") == "schematic":
            win = row
            break
print("找到原理图页:", bool(win))
if win:
    print("  ", json.dumps({k: win.get(k) for k in ("type", "name", "uuid")},
                           ensure_ascii=False))
print()

# 用 --window 消歧后跑真实读动作
rc, out = run(["doc", "ls"])
d = parse(out)
windows = (d.get("result") or {}).get("windows") or [] if d and d.get("ok") else []
if not windows:
    # 退而求其次：从 doctor 拿窗口
    rc2, out2 = run(["doctor"])
    dd = parse(out2) or {}
    windows = (dd.get("connector") or {}).get("windows") or []

wids = [w.get("windowId") or w.get("window_id") or w.get("id") for w in windows]
wids = [w for w in wids if w]
print("连接器窗口数:", len(wids))
if not wids:
    raise SystemExit("没有可用窗口，全链路无法演示")

wid = wids[0]
for cmd in (["project", "doc"], ["sch", "list", "--include-pins"]):
    rc, out = run([*cmd, "--window", wid])
    d = parse(out)
    print(f"--- easycirq {' '.join(cmd)} --window {wid[:8]}… (exit {rc}) ---")
    if d is None:
        first = out.strip().splitlines()[0][:140] if out.strip() else "(空)"
        print("  ", first)
        print()
        continue
    print("  ok:", d.get("ok"))
    r = d.get("result") or {}
    if d.get("ok") and isinstance(r, dict):
        for k in ("projectName", "name", "documentType", "pageName"):
            if k in r:
                print(f"    {k}: {r[k]}")
        comps = r.get("components")
        if isinstance(comps, list):
            names = [c.get("designator") for c in comps if c.get("designator")]
            print(f"    器件数: {len(comps)}，前几个位号: {names[:6]}")
    elif not d.get("ok"):
        e = d.get("error") or {}
        print("  error.code:", e.get("code"))
        print("  error.message:", str(e.get("message"))[:140])
    print()
