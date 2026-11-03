import pathlib
import re

# 用官方全表核对：我们调用的 eda.<前缀>_ 是否都在官方 classToProperty 映射里
dump = pathlib.Path("reports/eda-api-classes.txt").read_text(encoding="utf-8")

m = re.search(r'"classToProperty":\{([^}]*)\}', dump)
if not m:
    print("没找到 classToProperty 映射")
    raise SystemExit(1)

official = set()
for pair in re.finditer(r'"[^"]+":"(\w+)"', m.group(1)):
    official.add(pair.group(1))

print("官方属性数:", len(official))
print("官方前缀:", sorted({p.split('_')[0] for p in official}))
print()

# 我们连接器用的
cnt = {}
for f in pathlib.Path("connector/src").glob("*.ts"):
    if "_test" in f.name or ".test." in f.name:
        continue
    text = f.read_text(encoding="utf-8")
    for mm in re.finditer(r"eda\.(\w+_[A-Za-z0-9]+)", text):
        cnt[mm.group(1)] = cnt.get(mm.group(1), 0) + 1

print("我们用了:", len(cnt), "个 da 属性")
print()
missing = sorted(k for k in cnt if k not in official)
print("=== 官方表里没有的（要查证）===")
for k in missing:
    print(f"  {k}  (用了 {cnt[k]} 次)")
if not missing:
    print("  无 —— 全部在官方表里")
print()
print("=== 我们用到的属性清单 ===")
for k in sorted(cnt):
    mark = "OK " if k in official else "?? "
    print(f"  {mark}{k:28} {cnt[k]}")
