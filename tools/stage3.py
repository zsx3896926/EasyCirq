"""阶段 3：真实任务验证。

从 S0 走到 S5（并试图进 DELIVER），**如实记录每一次门运行与每一次拒绝**，
用来判断：这些拒绝里哪些是真拦住了问题，哪些是误报。

不外推、不美化。跑出来的就是数据。
"""
import json
import os
import pathlib
import subprocess
import sys
import time

EXE = pathlib.Path(os.environ["LOCALAPPDATA"]) / "EasyCirq" / "bin" / "easycirq.exe"
PHASE_DIR = os.environ.get("EASYCIRQ_PHASE_DIR") or (time.strftime("%Y%m%d-%H%M"))
RES = {"runs": [], "refusals": [], "falsePositiveCandidates": []}


def run(*args, timeout=1800):
    t0 = time.perf_counter()
    p = subprocess.run([str(EXE), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    dt = time.perf_counter() - t0
    return p.returncode, ((p.stdout or "") + (p.stderr or "")), dt


def note(kind, what, rc, dt, out):
    RES["runs"].append({"kind": kind, "what": what, "rc": rc,
                        "secs": round(dt, 2), "out": out.strip()[-400:]})
    print("  [%s] %s → rc=%d  %.1fs" % (kind, what, rc, dt))
    return rc


print("=== 1) 新建工程 ===")
rc, out, dt = run("project", "create", "--name",
                  "阶段3验证-" + time.strftime("%H%M"), "--open")
note("create", "project create --open", rc, dt, out)
try:
    i = out.find("{")
    created, _ = json.JSONDecoder().raw_decode(out[i:])
    proj = created["result"]["uuid"]
    act = created["result"].get("pageActivated") or {}
    print("  工程 uuid:", proj)
    print("  第一页自动激活:", act.get("activated"), act.get("pageName"),
          "waitedMs=", act.get("waitedMs"))
except Exception as exc:                                # noqa: BLE001
    print("  解析失败:", exc)
    sys.exit(1)

print()
print("=== 2) 相位状态（新建后）===")
rc, out, dt = run("phase", "show", "--project", proj, "--json")
note("phase", "phase show", rc, dt, out)

print()
print("=== 3) 试图直接跳到最后（S0 → DELIVER）===")
rc, out, dt = run("phase", "advance", "DELIVER", "--project", proj)
note("advance", "advance DELIVER from S0", rc, dt, out)
if rc != 0:
    RES["refusals"].append({"what": "advance DELIVER from S0", "out": out.strip()[:300]})

print()
print("=== 4) 一步一步推进 ===")
for _ in range(6):
    rc, out, dt = run("phase", "advance", "--project", proj)
    note("advance", "advance", rc, dt, out)
    if rc != 0:
        RES["refusals"].append({"what": "step advance", "out": out.strip()[:300]})
        break

print()
print("=== 5) 空板子跑 S5 门 ===")
rc, out, dt = run("phase", "run", "S5", "--project", proj)
note("gate", "phase run S5 (empty board)", rc, dt, out)

print()
print("=== 6) 空板子进 DELIVER（应被拒：没有器件）===")
rc, out, dt = run("phase", "advance", "DELIVER", "--project", proj)
note("advance", "advance DELIVER (empty board)", rc, dt, out)
if rc != 0:
    RES["refusals"].append({"what": "DELIVER with empty board", "out": out.strip()[:300]})

print()
print("=== 7) 落一个真器件 ===")
rc, out, dt = run("lib", "search", "10k 0603", "--limit", "1")
note("lib", "lib search", rc, dt, out)
try:
    i = out.find("{")
    lib, _ = json.JSONDecoder().raw_decode(out[i:])
    dev = lib["result"]["components"][0]
    print("  器件:", dev["manufacturerId"], dev["lcsc"],
          "lib=", dev["libraryUuid"][:8], "uuid=", dev["uuid"][:8])
except Exception as exc:                                # noqa: BLE001
    print("  解析失败:", exc)
    sys.exit(1)

rc, out, dt = run("sch", "place", "--lib", dev["libraryUuid"],
                  "--uuid", dev["uuid"], "--x", "100", "--y", "100",
                  "--designator", "R1", "--project", proj)
note("place", "sch place R1", rc, dt, out)
placed = rc == 0

print()
print("=== 8) 有器件后重跑 S5 门 ===")
if placed:
    rc, out, dt = run("phase", "run", "S5", "--project", proj)
    note("gate", "phase run S5 (1 part)", rc, dt, out)
    print()
    print("=== 9) 有器件后进 DELIVER ===")
    rc, out, dt = run("phase", "advance", "DELIVER", "--project", proj)
    note("advance", "advance DELIVER (1 part)", rc, dt, out)
    if rc != 0:
        RES["refusals"].append({"what": "DELIVER with 1 part", "out": out.strip()[:300]})

print()
print("=" * 60)
print("统计")
print("=" * 60)
print("  总动作数:", len(RES["runs"]))
print("  门运行次数:", sum(1 for r in RES["runs"] if r["kind"] == "gate"))
print("  推进尝试:", sum(1 for r in RES["runs"] if r["kind"] == "advance"))
print("  被拒次数:", len(RES["refusals"]))
print()
print("  每一次拒绝：")
for i, r in enumerate(RES["refusals"], 1):
    head = r["out"].splitlines()[0] if r["out"] else ""
    print("   %d) %-28s %s" % (i, r["what"], head[:110]))

out_path = pathlib.Path("reports/phase-stage3.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(RES, ensure_ascii=False, indent=2), encoding="utf-8")
print()
print("  明细已写入", out_path)
