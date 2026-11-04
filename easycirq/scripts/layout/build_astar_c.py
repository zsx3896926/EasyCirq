#!/usr/bin/env python3
"""构建 `_astar_c.pyd` —— A* 内循环的 Cython 扩展。

# 为什么需要单独构建

编译产物与本机 **Python 版本 + 平台**绑定，不能假设它存在。
`ec_layout.astar` 在导入时尝试加载，拿不到就全部走纯 Python 路径
（见 ec_layout.py 里的 `_FAST_ASTAR`）。

# 工具链

本机没有 MSVC/cython 的常规组合，用的是：
  · `cython`（pip 装）
  · `ziglang`（pip 装的便携 C 编译器，`zig cc` = clang）

不用 setuptools：它按名字 spawn `gcc.exe`，而 Windows 的 CreateProcess
不能直接执行 `.bat` 包装脚本。

# 用法

    python easycirq/scripts/layout/build_astar_c.py

失败不是致命：没有它，工具链照常按纯 Python 跑，只是慢一些。
"""
import pathlib
import shutil
import subprocess
import sys
import sysconfig

HERE = pathlib.Path(__file__).resolve().parent
PYX = HERE / "_astar_c.pyx"
PYD = HERE / "_astar_c.pyd"


def main():
    if not PYX.is_file():
        print("缺 %s" % PYX)
        return 1
    try:
        import ziglang
    except Exception:                                   # noqa: BLE001
        print("没有 ziglang（pip install ziglang）—— 跳过编译，"
              "工具链会按纯 Python 运行")
        return 2
    zig = str(pathlib.Path(ziglang.__file__).parent / "zig.exe")
    if not pathlib.Path(zig).is_file():
        print("找不到 zig 可执行：%s" % zig)
        return 2

    inc = sysconfig.get_paths()["include"]
    libdir = str(pathlib.Path(sys.base_prefix) / "libs")
    ver = "python%d%d" % (sys.version_info.major, sys.version_info.minor)

    cfile = HERE / "_astar_c.c"
    print("[1/2] cython ...")
    p = subprocess.run([sys.executable, "-m", "cython", "-3", str(PYX),
                        "-o", str(cfile)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1200)
    if p.returncode:
        print((p.stderr or "")[-1500:])
        return 1

    print("[2/2] zig cc ...")
    p = subprocess.run([zig, "cc", "-shared", "-O3", "-I", inc,
                        str(cfile), "-L", libdir, "-l" + ver, "-o", str(PYD)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1200)
    if p.returncode:
        print((p.stderr or "")[-1500:])
        return 1

    print("产物：%s  %d bytes" % (PYD.name, PYD.stat().st_size))

    # 立刻验一遍：能导入、符号对
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, r'%s');"
                        "import _astar_c;"
                        "print('has astar_c:', hasattr(_astar_c, 'astar_c'))"
                        % HERE],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    print("自检 exit:", r.returncode)
    print(" ", ((r.stdout or "") + (r.stderr or "")).strip()[:300])
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
