"""按门禁意见修风扇板：
  1. 加去耦电容 C1（100nF / 0603 / C1591，三星 CL10B104KB8NNNC）到 PWR5V 与 GND 之间
  2. 处理 LM393 闲置的第二路：pin5(IN2+) / pin6(IN2-) / pin7(OUT2) 全部接 GND

器件身份从 `lib by-lcsc` 取，不用 `lib search` —— 后者对 C1591 只返回模糊候选
（`No device exactly matches`），两者的区别值得记住。
"""
import json
import subprocess

PROJECT = "Fan-Controller-12V"
PAGE = "664436e68d969739"
LIB = "78757fbff56447419bdcfbdb07cfbf65"
UUID = "0b5a7f30091b47f2a06c8afe232033da"


def cli(*args):
    return subprocess.run(["easycirq", *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def main():
    proc = cli("--project", PROJECT, "--doc", PAGE, "sch", "place",
               "--lib", LIB, "--uuid", UUID,
               "--designator", "C1", "--x", "330", "--y", "620", "--rotation", "0")
    out = (proc.stdout or "") + (proc.stderr or "")
    ok = '"ok": true' in out
    print("放置 C1 (100nF 去耦):", "✓" if ok else "✗ " + out[:240])
    if not ok:
        return 1

    for pin, net, kind in (("1", "PWR5V", "power"), ("2", "GND", "ground")):
        proc = cli("--project", PROJECT, "--doc", PAGE, "sch", "autoconnect",
                   "--pin", f"C1:{pin}", "--kind", kind, "--net", net)
        out = (proc.stdout or "") + (proc.stderr or "")
        print(f"  C1.{pin} → {net}:", "✓" if "✓" in out else "✗ " + out[:160])

    for pin in ("5", "6", "7"):
        proc = cli("--project", PROJECT, "--doc", PAGE, "sch", "autoconnect",
                   "--pin", f"U1:{pin}", "--kind", "ground", "--net", "GND")
        out = (proc.stdout or "") + (proc.stderr or "")
        print(f"  U1.{pin} → GND:", "✓" if "✓" in out else "✗ " + out[:160])

    return 0


raise SystemExit(main())
