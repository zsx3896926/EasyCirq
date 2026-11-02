"""往 standard-parts.json 里补这块板要用、但库里没有的 9 个标准件。

库里 0603 电阻、二极管、MOS、NTC 一个都没有——所以这个块会是第一个需要它们的。
deviceUuid 从 lib search 现取，不手抄。
"""
import json
import pathlib
import subprocess

STANDARD = pathlib.Path("easycirq/references/standard-parts.json")

# key -> (LCSC, 期望的 value/footprint 说明)
NEEDED = {
    "res.4k3_0603": ("C23159", "4.3k 1% 0603"),
    "res.39k_0603": ("C23153", "39k 1% 0603"),
    "res.100k_0603": ("C25803", "100k 1% 0603"),
    "res.100r_0603": ("C22775", "100R 1% 0603 (gate series)"),
    "res.10k_0603": ("C25804", "10k 1% 0603"),
    "ic.lm393_sop8": ("C504553", "LM393 dual comparator, SOP-8"),
    "mos.ao3400a_sot23": ("C700953", "AO3400A N-MOSFET, SOT-23, logic level Vgs(th) 1.05V, Id 4A"),
    "dio.1n4148w_sod123": ("C2892570", "1N4148W signal diode, SOD-123; pin1=K, pin2=A"),
    "ntc.10k_3950": ("C9900004021", "10K NTC thermistor B=3950, radial TH"),
    "conn.xh254_2p": ("C9900016027", "2P 2.54 through-hole connector (fan)"),
}


def lookup(lcsc):
    proc = subprocess.run(["easycirq", "lib", "search", lcsc, "--limit", "1"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        return None, (raw or proc.stderr)[:160]
    data = json.loads(raw[start:])
    comps = (data.get("result") or {}).get("components") or []
    if not comps:
        return None, "没有结果"
    return comps[0], None


def main():
    data = json.loads(STANDARD.read_text(encoding="utf-8"))
    parts = data["parts"]
    added, skipped = [], []

    for key, (lcsc, desc) in NEEDED.items():
        if key in parts:
            skipped.append(key)
            continue
        entry, err = lookup(lcsc)
        if err:
            print(f"✗ {key}: 查不到 {lcsc} — {err}")
            return 1
        parts[key] = {
            "value": entry.get("value") or entry.get("name"),
            "mpn": entry.get("manufacturerId") or entry.get("name"),
            "lcsc": entry.get("lcsc"),
            "manufacturer": entry.get("manufacturer"),
            "deviceUuid": entry.get("uuid"),
            "footprint": entry.get("footprintName"),
            "basic": True,
            "desc": desc,
        }
        added.append(key)
        print(f"✓ {key:24} {entry.get('lcsc'):12} {str(entry.get('footprintName'))[:30]}")

    STANDARD.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print()
    print(f"新增 {len(added)} 个，跳过已存在 {len(skipped)} 个；库现在 {len(parts)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
