"""指标 1：装到第一条审计，目标 ≤5 分钟。

测量分两段，因为一整段在单机上做不干净：

  A. 解包 + 只读检查 —— 完全可隔离，数字可信
  B. 一次真实派发 + 审计落盘 —— 必须用真实 HOME

B 段为什么不能隔离：`daemon start` 被 subprocess 拉起时**不返回**（前台进程，
已实测 120s 超时），而隔离 HOME 里的 daemon 又拿不到 EasyEDA 连接，派发必然失败。
所以 B 段在真实环境跑，用"审计行数增减"确认落盘，而不是靠隔离目录。

用法：
    python tools/measure_first_use.py
    python tools/measure_first_use.py --install-only
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATES = [p for p in (ROOT / "dist-release").glob("easycirq-toolchain-*.zip")
              if "-installer-" not in p.name]
BUNDLE = max(CANDIDATES, key=lambda p: p.stat().st_mtime)


def audit_lines() -> int:
    directory = pathlib.Path(os.path.expanduser("~")) / ".easycirq" / "audit"
    if not directory.is_dir():
        return 0
    total = 0
    for path in directory.glob("*.jsonl"):
        try:
            with path.open("rb") as handle:
                total += sum(1 for _ in handle)
        except OSError:
            continue
    return total


def measure_install() -> float:
    """A 段：解包到只读检查，完全在临时目录里。"""
    workspace = pathlib.Path(tempfile.mkdtemp(prefix="metric1-install-"))
    fake_home = workspace / "home"
    fake_home.mkdir()
    env = dict(os.environ)
    env["USERPROFILE"] = str(fake_home)
    env["HOME"] = str(fake_home)
    exe = workspace / "app" / "bin" / "easycirq.exe"

    clock = time.perf_counter()
    proc = subprocess.run([sys.executable, str(ROOT / "distribution" / "easycirq_install.py"),
                           "install", "--bundle", str(BUNDLE),
                           "--install-dir", str(workspace / "app"),
                           "--state-dir", str(workspace / "state"),
                           "--home", str(fake_home), "--skill-client", "none",
                           "--no-self-check"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=600)
    install = time.perf_counter() - clock
    print(f"A1 install      {install:6.2f}s  exit={proc.returncode}")

    if proc.returncode == 0:
        clock = time.perf_counter()
        subprocess.run([str(exe), "version"], capture_output=True, env=env, timeout=120)
        print(f"A2 version      {time.perf_counter() - clock:6.2f}s")
        clock = time.perf_counter()
        subprocess.run([str(exe), "setup"], capture_output=True, env=env, timeout=120)
        print(f"A3 setup        {time.perf_counter() - clock:6.2f}s")

    shutil.rmtree(workspace, ignore_errors=True)
    return install


def measure_dispatch() -> float:
    """B 段：一次真实派发到已在运行的 daemon，确认审计落盘。"""
    before = audit_lines()
    clock = time.perf_counter()
    proc = subprocess.run(["easycirq", "--project", "KPI-S5-Verify", "sch", "list"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    elapsed = time.perf_counter() - clock
    time.sleep(1.0)
    after = audit_lines()
    print(f"B  dispatch     {elapsed:6.2f}s  exit={proc.returncode}  "
          f"audit lines {before} -> {after} (+{after - before})")
    return elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-only", action="store_true")
    args = parser.parse_args()

    print(f"bundle: {BUNDLE.name}")
    print()
    install = measure_install()
    if args.install_only:
        print()
        print(f"A 段合计（安装 + 只读检查）约 {install:.2f}s")
        return 0

    print()
    dispatch = measure_dispatch()
    print()
    print("A 段可完全隔离，数字可信。")
    print("B 段跑在真实环境（daemon 已起、EasyEDA 已连），只测一次派发 + 审计落盘。")
    print("完整指标 1 还包含「装 EasyEDA 本体 + 导入插件 + 连接」——")
    print("那几步是人工操作，本脚本测不到。")
    print()
    print(f"A+B = {install + dispatch:.2f}s（不含 EasyEDA 安装与插件导入）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
