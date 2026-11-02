"""交付包自检：文件存在、链接可解、key 数字自洽。

交付包是客户唯一会打开的东西。里面任何一个断链、任何一个和工具输出不一致的数字，
都会让"有证据"变成"看起来有证据"。
"""
import hashlib
import pathlib
import re
import sys

# 目录从命令行取，默认报警板。
# 原来这里写死了 deliverables/alarm，于是 `python tools/check_deliverable.py
# deliverables/fan-controller` 看起来"跑过了"，其实查的是报警板——
# 输出里 BOM 11 个（报警板的数）而风扇板是 12 个，才发现参数被无声忽略。
# 检查器忽略传入参数，比没有参数更糟：它给出的是一个看似针对目标的结论。
d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "deliverables/alarm")
if not d.is_dir():
    raise SystemExit(f"交付包目录不存在: {d}")
print(f"检查交付包: {d}")
problems = []

# 1. every file listed in README's table must exist, and every file present should be listed
readme = (d / "README.md").read_text(encoding="utf-8")
listed = set(re.findall(r"\| `([^`]+)` \|", readme))
# 用**相对路径**而不是顶层名。
#
# 原来取 p.name，然后拿它跟 README 里的相对路径比，于是任何嵌套目录的交付包
# 都会被判「列出了不存在的文件」+「存在但未列出」两条。报警板是平铺的所以没暴露，
# 风扇包有 design/ snapshot/ manufacturing/ 三层，一上来就撞上。
# 比对的是"哪个文件"，路径才是它的身份。
present = {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()}
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
    # 「必查」是 KPI 总数的一个子集（软指标不算必查），所以只能查"必查不超过总数"，
    # 不能要求相等。第二轮修改曾把这里写成 expected != total，立刻产生假失败。
    if expected > total:
        problems.append(f"卡片说必查 {expected} 项，但 KPI 定义只有 {total} 项")
    # 曾经要求 passed == expected，于是门禁红的时候卡片合法地写「必查 14/15 通过」
    # 反而被判成"自相矛盾"。门禁红不是矛盾，是事实——只要不虚报就行。
    if passed > expected:
        problems.append(f"卡片吹牛: 必查 {passed}/{expected}，通过数超过必查数")
    if passed < 0 or expected < 0:
        problems.append(f"卡片计数异常: 必查 {passed}/{expected}")
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

# 6. 卡片判定必须和随包的门禁报告一致
#
# 2026-11-01 踩到：原理图加了 R6、板子还没同步，门禁里 pcb_match 是红的，
# 而 card.txt 第一行还写着"可以下单"——那张卡是加 R6 之前生成的。
# 五条检查没有一条会看这件事，于是"交付卡不虚报"只能靠我记得重新生成。
#
# 现在包里必须随附门禁报告（design/kpi-report.json），卡片判定与它比对：
#   卡片说"可以下单"  <=>  报告 verdict 是 PASS
# 不一致就是交付卡在虚报。
report_path = d / "design" / "kpi-report.json"
card_text = (d / "card.txt").read_text(encoding="utf-8")
card_line = card_text.strip().splitlines()[0] if card_text.strip() else ""
card_says_ok = "可以下单" in card_line

if not report_path.is_file():
    problems.append("交付包没有随附门禁报告 design/kpi-report.json，"
                    "无法核对卡片判定是否与门禁一致")
else:
    import json

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"随包门禁报告不是合法 JSON: {exc}")
        report = None
    if report is not None:
        verdict = str(report.get("verdict") or "").upper()
        report_says_ok = verdict == "PASS"
        if card_says_ok != report_says_ok:
            problems.append(
                f"卡片判定与门禁报告矛盾：卡片说"
                f"{'可以下单' if card_says_ok else '还不能打样'}，"
                f"而随包报告 verdict={verdict or '(空)'}。"
                f"重跑门禁并用新报告重新生成卡片")

print(f"package files: {len(present)}   listed in README: {len(listed)}")
print(f"KPI total: {total}   card: {m.group(0) if m else 'n/a'}   "
      f"BOM designators: {len(designators)}   "
      f"report verdict: {locals().get('verdict') or 'n/a'}")
print()
if problems:
    print(f"PROBLEMS ({len(problems)}):")
    for item in problems:
        print("  -", item)
    raise SystemExit(1)
print("交付包自检通过")
