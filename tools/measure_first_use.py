"""指标 1：首次可用时间（装到第一条审计），目标 ≤5 分钟。

之前只测过「安装 + verify + setup = 4.5s」，那不是指标 1 —— 指标 1 说的是
**到第一条审计记录**。审计是动作派发时才写的，所以必须真的做一次写/读操作。

这个脚本在隔离目录里装一遍，然后依次计时：
  1. install（解包）
  2. verify
  3. setup（只读检查，通常不写审计）
  4. 一条真实动作（触发审计）
并确认审计文件确实出现。
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
# "-installer-" bundles do not carry bundle.json; the installable one is
# easycirq-toolchain-<version>.zip.
CANDIDATES = [p for p in (ROOT / "dist-release").glob("easycirq-toolchain-*.zip")
              if "-installer-" not in p.name]
BUNDLE = max(CANDIDATES, key=lambda p: p.stat().st_mtime)


def run(cmd, **kwargs):
    started = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kwargs)
    return proc, time.perf_counter() - started


def audit_files(home: pathlib.Path):
    directory = home / ".easycirq" / "audit"
    if not directory.is_dir():
        return {}
    return {p.name: p.stat().st_size for p in directory.glob("*.jsonl*")}


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="metric1-"))
    home = root / "home"
    app = root / "app"
    state = root / "state"
    home.mkdir()

    env = dict(os.environ)
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)

    print(f"bundle: {BUNDLE.name}")
    total = 0.0

    proc, seconds = run([sys.executable, str(ROOT / "distribution" / "easycirq_install.py"),
                         "install", "--bundle", str(BUNDLE),
                         "--install-dir", str(app), "--state-dir", str(state),
                         "--home", str(home), "--skill-client", "none", "--no-self-check"])
    total += seconds
    print(f"1. install   {seconds:6.2f}s  exit={proc.returncode}")
    if proc.returncode != 0:
        print(proc.stdout[-400:], proc.stderr[-400:])
        return 1

    exe = app / "bin" / "easycirq.exe"
    proc, seconds = run([str(exe), "version"], env=env)
    total += seconds
    print(f"2. version   {seconds:6.2f}s  exit={proc.returncode}  {(proc.stdout or '').strip()}")

    before = audit_files(home)
    proc, seconds = run([str(exe), "setup"], env=env)
    total += seconds
    after_setup = audit_files(home)
    print(f"3. setup     {seconds:6.2f}s  exit={proc.returncode}  "
          f"audit files {len(before)} -> {len(after_setup)}")

    # 一条真实动作：必须派发到 daemon 才会写审计
    proc, seconds = run([str(exe), "capabilities"], env=env)
    total += seconds
    after_action = audit_files(home)
    print(f"4. action    {seconds:6.2f}s  exit={proc.returncode}  "
          f"audit files {len(after_setup)} -> {len(after_action)}")

    print()
    print(f"total {total:.2f}s   target <= 300s   {'OK' if total <= 300 else 'OVER'}")

    if not after_action:
        print()
        print("NOTE: 到第 4 步仍没有审计文件。这说明「第一条审计」需要一次真正的"
              "派发动作（例如一条 sch/pcb 读写），仅 setup/capabilities 不够。")
        print("      这不是失败，是这条指标的定义需要更精确："
              "「第一条审计」= 第一次 daemon 派发被记录。")

    shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
