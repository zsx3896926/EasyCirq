"""把"既有失败"变成**可复现的证据**，而不是反复声明的推断。

做法：用 git 的祖先关系证明——那些失败涉及的测试与源码文件，
最后一次改动都发生在**本会话第一次提交之前**。

用法：
  python scripts/check_preexisting_failures.py --base <会话第一次提交> \
      --suites tests/test_xxx.py ...
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


def is_ancestor(commit: str, base: str) -> bool:
    return git("merge-base", "--is-ancestor", commit, base).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="证明哪些失败是既有的")
    ap.add_argument("--base", required=True, help="本会话第一次提交")
    ap.add_argument("files", nargs="+", help="失败用例涉及的文件")
    args = ap.parse_args()
    ok = True
    for f in args.files:
        r = git("log", "--oneline", "-1", "--", f)
        if r.returncode != 0 or not r.stdout.strip():
            print("  %-46s 没有提交记录（新文件？）" % f)
            ok = False
            continue
        head = r.stdout.split()[0]
        pre = is_ancestor(head, args.base)
        print("  %-46s 最后改动 %s  %s" %
              (f, head, "既有（早于会话）" if pre else "**本会话改过**"))
        ok = ok and pre
    print("  结论：%s" % ("全部既有" if ok else "有本会话改动，需重新评估"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
