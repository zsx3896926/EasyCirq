"""交付包自检：文件存在、链接可解、key 数字自洽。

交付包是客户唯一会打开的东西。里面任何一个断链、任何一个和工具输出不一致的数字，
都会让"有证据"变成"看起来有证据"。
"""
import hashlib
import pathlib
import re

d = pathlib.Path("deliverables/alarm")
problems = []

# 1. every file listed in README's table must exist, and every file present should be listed
readme = (d / "README.md").read_text(encoding="utf-8")
listed = set(re.findall(r"\| `([^`]+)` \|", readme))
present = {p.name.rstrip("/") for p in d.iterdir() if p.is_file() or p.is_dir()}
present.discard("README.md")
listed = {name.rstrip("/") for name in listed}

missing_files = sorted(listed - present)
unlisted = sorted(present - listed)
if missing_files:
    problems.append(f"README 列出但不存在: {missing_files}")
if unlisted:
    problems.append(f"存在但 README 未列: {unlisted}")

# 2. relative links inside README must resolve
for target in re.findall(r"\]\(([^)]+)\)", readme):
    if target.startswith(("http://", "https://", "#")):
        continue
    if not (d / target).exists() and not pathlib.Path(target).exists():
        problems.append(f"README 断链: {target}")

# 3. checksums must match the files on disk
sums = {}
for line in (d / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, name = line.split("  ", 1)
    sums[name] = digest
for name, digest in sums.items():
    path = d / name
    if not path.is_file():
        problems.append(f"SHA256SUMS 指向不存在的文件: {name}")
        continue
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        problems.append(f"校验和不符: {name}")

# 4. the card's mandatory count must match the KPI definition
import json

kpi_def = json.loads(pathlib.Path("metrics/schematic-kpi.v1.json").read_text(encoding="utf-8"))
total = len(kpi_def["kpis"])
card = (d / "card.txt").read_text(encoding="utf-8")
m = re.search(r"必查\s*(\d+)/(\d+)", card)
if m:
    passed, expected = int(m.group(1)), int(m.group(2))
    if expected > total:
        problems.append(f"卡片说必查 {expected} 项，但 KPI 定义只有 {total} 项")
    if passed != expected:
        problems.append(f"卡片自相矛盾: 必查 {passed}/{expected}")
else:
    problems.append("card.txt 里找不到「必查 N/N」")

# 5. BOM designators must match the schematic part count stated in the card/README
import csv
import io

import sys

# Windows consoles default to GBK; these tools print Chinese status text, so pin
# the output encoding rather than depending on the caller's environment.
for _stream in ("stdout", "stderr"):
    _handle = getattr(sys, _stream, None)
    if hasattr(_handle, "reconfigure"):
        _handle.reconfigure(encoding="utf-8", errors="replace")


bom_text = (d / "bom.csv").read_text(encoding="utf-8-sig")
rows = list(csv.DictReader(io.StringIO(bom_text), delimiter="\t"))
designators = []
for row in rows:
    designators.extend(p.strip() for p in (row.get("Designator") or "").split(",") if p.strip())
# 位号数不再写死。原来写的是 9，加了 R5 之后立刻变成"预期 9、实际 10"的假失败——
# 而真正该查的是「BOM 与原理图一致」，那件事由 KPI 18 (bom_match) 负责，且它更严：
# 它会指名道姓说哪个位号缺、哪个多。这里只保留一个弱的合理性检查：
# 必须非空、不能有重复位号。
if not designators:
    problems.append("BOM 里没有任何位号")
dupes = sorted({d for d in designators if designators.count(d) > 1})
if dupes:
    problems.append(f"BOM 位号重复: {', '.join(dupes)}")

print(f"package files: {len(present)}   listed in README: {len(listed)}")
print(f"KPI total: {total}   card: {m.group(0) if m else 'n/a'}   BOM designators: {len(designators)}")
print()
if problems:
    print(f"PROBLEMS ({len(problems)}):")
    for item in problems:
        print("  -", item)
    raise SystemExit(1)
print("交付包自检通过")
