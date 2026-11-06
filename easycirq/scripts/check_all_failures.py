"""确认整套测试的失败**全部既有**（用 git 祖先关系，而不是"我觉得"）。

用法：python scripts/check_preexisting_failures.py --base <会话首提交> <文件...>
"""
import re
import subprocess
import sys
import pathlib

BASE = "7aa5a843"          # 本会话第一次提交
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None

# 从 pytest 输出里取出失败用例所属的测试文件
text = OUT.read_text(encoding="utf-8", errors="replace") if OUT else ""
files = sorted({m.group(1).replace("\\", "/")
                for m in re.finditer(r"FAILED (tests/[^:]+)::", text)})
if not files:
    print("  没有解析到失败文件")
    raise SystemExit(1)


def git(*a):
    return subprocess.run(["git"] + list(a), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


bad = []
for f in files:
    r = git("log", "--oneline", "-1", "--", f)
    if not r.stdout.strip():
        bad.append((f, "无提交记录"))
        continue
    head = r.stdout.split()[0]
    if git("merge-base", "--is-ancestor", head, BASE).returncode != 0:
        bad.append((f, head))

print("  失败测试文件 %d 个" % len(files))
if bad:
    print("  **本会话改过的**：")
    for f, h in bad:
        print("    %s（最后改动 %s）" % (f, h))
else:
    print("  全部既有：这些文件的最后一次改动都早于本会话")
