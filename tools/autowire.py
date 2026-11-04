"""用 `sch autoconnect --spec --replace` 重做板1 连线。

为什么重做：上一轮用 `sch connect` 逐个引脚连，标号在物理上重叠，
`+5V` 被并成了 37 个引脚，门报 6 处真短路。

`--replace`：引脚已在别的网上时，先删旧引线+标号再重连。
`--strict`：候选打分不干净就**拒绝放置**，而不是带警告放上去。
"""
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path(r"C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method")
EXE = pathlib.Path(os.environ["LOCALAPPDATA"]) / "EasyCirq" / "bin" / "easycirq.exe"
PROJECT = "d3e50b4c213d409d8f641a6f484213e9"
OUT = ROOT / "reports/hard-board/board1"

NETS = {}
def n(name, *members):
    NETS[name] = list(members)

n("VBUS", ("J1", "B4A9"), ("J1", "A4B9"), ("F1", "1"))
n("VIN", ("F1", "2"), ("D_TVS1", "K"), ("Q_REV", "S"))
n("VIN_12V", ("Q_REV", "D"), ("U1", "2"), ("C1", "1"), ("C2", "1"))
n("+5V", ("L1", "2"), ("C3", "1"), ("C4", "1"), ("U2", "2"),
  ("RFB1", "1"), ("U4", "3"), ("RAD1", "1"), ("RAD3", "1"))
n("+3V3", ("L2", "2"), ("C5", "1"), ("U3", "3"),
  ("RFB3", "1"), ("RAD2", "1"), ("RAD4", "1"))
n("+1V8", ("U3", "2"), ("C6", "1"), ("C7", "1"))
n("+4V0", ("U4", "2"), ("C8", "1"), ("C9", "1"))
n("GND", ("J1", "0"), ("J1", "B1A12"), ("J1", "A1B12"),
  ("D_TVS1", "A"), ("Q_REV", "G"), ("RCC1", "2"), ("RCC2", "2"),
  ("R_IN1", "1"), ("U1", "7"), ("C1", "2"), ("C2", "2"), ("C3", "2"),
  ("U2", "7"), ("C4", "2"), ("C5", "2"), ("U3", "1"), ("C6", "2"), ("C7", "2"),
  ("U4", "1"), ("C8", "2"), ("C9", "2"), ("CB1", "2"), ("CD1", "2"),
  ("CD2", "2"), ("CRST", "2"), ("RAD2", "2"), ("RAD4", "2"), ("RFB2", "2"),
  ("RFB4", "2"), ("CAD1", "2"), ("CAD2", "2"))
n("SW1", ("U1", "8"), ("L1", "1"), ("CB1", "1"))
n("SW2", ("U2", "8"), ("L2", "1"))
n("FB1", ("U1", "5"), ("RFB1", "2"), ("RFB2", "1"))
n("FB2", ("U2", "5"), ("RFB3", "2"), ("RFB4", "1"))
n("EN1", ("U1", "3"), ("RSEQ1", "1"))
n("EN2", ("U2", "3"), ("RSEQ2", "1"), ("CSEQ1", "1"))
n("SEQ1", ("RSEQ1", "2"), ("CSEQ1", "2"))
n("SEQ2", ("CSEQ2", "1"), ("RSEQ2", "2"))
n("CC1", ("J1", "A5"), ("RCC1", "1"))
n("CC2", ("J1", "B5"), ("RCC2", "1"))
n("SENSE_5V", ("RAD1", "2"), ("RAD2", "1"), ("CAD1", "1"))
n("SENSE_3V3", ("RAD3", "2"), ("RAD4", "1"), ("CAD2", "1"))
n("LED1_A", ("D1", "A"), ("RL1", "2"))
n("LED2_A", ("D2", "A"), ("RL2", "2"))
n("LED3_A", ("D3", "A"), ("RL3", "2"))
n("LED4_A", ("D4", "A"), ("RL4", "2"))
n("LED1_K", ("D1", "C"))
n("LED2_K", ("D2", "C"))
n("LED3_K", ("D3", "C"))
n("LED4_K", ("D4", "C"))
n("RLED1", ("RL1", "1"))
n("RLED2", ("RL2", "1"))
n("RLED3", ("RL3", "1"))
n("RLED4", ("RL4", "1"))
n("MCU_NRST", ("U5", "7"), ("RRST", "1"), ("CRST", "1"))
n("MCU_BOOT0", ("U5", "44"), ("R_IN1", "2"))
n("MCU_ADC0", ("U5", "10"))
n("MCU_ADC1", ("U5", "11"))
n("MCU_SWDIO", ("U5", "34"))
n("MCU_SWCLK", ("U5", "37"))
n("MCU_TX", ("U5", "30"))
n("MCU_RX", ("U5", "31"))

conns = []
for net, members in NETS.items():
    kind = "gnd" if net.startswith(("GND", "LED")) and False else (
        "gnd" if net == "GND" else "power")
    for des, pin in members:
        conns.append({"pin": "%s:%s" % (des, pin), "kind": kind, "net": net})

spec = {"connections": conns}
OUT.mkdir(parents=True, exist_ok=True)
spec_path = OUT / "connect-spec.json"
spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
print("  spec 连接数:", len(conns), " 网络数:", len(NETS))


def run(args, timeout=1200):
    p = subprocess.run([str(EXE)] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    t = (p.stdout or "") + (p.stderr or "")
    i = t.find("{")
    if i < 0:
        return None, t
    try:
        return json.JSONDecoder().raw_decode(t[i:])[0], t
    except Exception:                                        # noqa: BLE001
        return None, t


for strict in (True, False):
    args = ["sch", "autoconnect", "--project", PROJECT,
            "--spec", str(spec_path), "--replace", "--json"]
    if strict:
        args.insert(2, "--strict")
    d, raw = run(args)
    if d is None:
        print("  %s 失败：%s" % ("strict" if strict else "non-strict", raw[:200]))
        continue
    res = d.get("result") or d
    okc = res.get("connected") if isinstance(res, dict) else None
    print("  %s: ok=%s connected=%s" % ("strict" if strict else "non-strict",
                                        d.get("ok"), okc))
    if d.get("ok"):
        OUT.joinpath("connect-result.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        break
    else:
        err = d.get("error") or {}
        print("     error:", json.dumps(err, ensure_ascii=False)[:300])

time.sleep(1)
