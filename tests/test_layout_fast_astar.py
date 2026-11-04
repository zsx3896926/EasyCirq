"""C 搜索核的守卫测试。

三件必须一直成立：
  1. 扩展在时，产物与纯 Python **逐字节相同**（等价性）
  2. 扩展不在时，**能正常回退**（不能因为缺 .pyd 就崩）
  3. 构建脚本可用，且 .pyx 与 .pyd 的名字一致（否则 PyInit 符号对不上）
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "easycirq" / "scripts" / "layout"
PYX = LAYOUT / "_astar_c.pyx"
PYD = LAYOUT / "_astar_c.pyd"
BUILD = LAYOUT / "build_astar_c.py"


def test_sources_and_build_script_exist():
    assert PYX.is_file(), "Cython 源码不见了"
    assert BUILD.is_file(), "构建脚本不见了"
    s = PYX.read_text(encoding="utf-8")
    # 语义常量必须与 ec_layout 一致
    assert "1.414" in s, "对角线代价没有对齐 1.414"
    assert "DEF_DIRTY = 400.0" in s, "via 污染代价没有对齐"
    assert "NMOVES = 8" in s


def test_module_name_matches_file_name():
    """.pyd 的 PyInit 符号由 .pyx 文件名决定；改名会让导入失败。"""
    assert PYX.name == "_astar_c.pyx"
    if PYD.is_file():
        assert PYD.name == "_astar_c.pyd", (
            f"编译产物叫 {PYD.name}，与 PyInit__astar_c 不匹配，导入会失败")


def test_loader_falls_back_when_extension_is_absent():
    """没有 .pyd 时必须照常工作——这是部署到没有编译器的机器的前提。"""
    code = (
        "import sys, importlib.util\n"
        f"sys.path.insert(0, r'{LAYOUT}')\n"
        "import ec_layout\n"
        "print('FAST_IS_NONE', ec_layout._FAST_ASTAR is None)\n"
        "print('ENABLED', ec_layout._fast_astar_enabled())\n"
    )
    # 用一个屏蔽 _astar_c 的导入钩子模拟"扩展不存在"
    blocker = (
        "import sys\n"
        "class _Block:\n"
        "    def find_module(self, name, path=None):\n"
        "        return self if name == '_astar_c' else None\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == '_astar_c':\n"
        "            raise ImportError('blocked for test')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Block())\n"
    )
    p = subprocess.run([sys.executable, "-c", blocker + code],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out[-800:]
    assert "FAST_IS_NONE True" in out, f"屏蔽扩展后没有回退：\n{out[-500:]}"
    assert "ENABLED False" in out, f"扩展缺失时不该声称启用：\n{out[-500:]}"


def test_equivalence_passes_with_the_extension_present():
    """扩展在时，产物必须逐字节相同（这是这道闸存在的理由）。"""
    if not PYD.is_file():
        import pytest
        pytest.skip("本机没有编译产物，等价性由纯 Python 路径保证")
    env = {**os.environ, "EASYCIRQ_ASTAR_C": "1"}
    p = subprocess.run([sys.executable, "equivalence.py", "--iters", "3",
                        "--compare"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800, cwd=str(LAYOUT), env=env)
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out[-1200:]
    assert "产物逐字节相同" in out


def test_off_switch_disables_the_fast_path():
    """EASYCIRQ_ASTAR_C=0 必须真的关掉。"""
    code = (
        f"import sys; sys.path.insert(0, r'{LAYOUT}')\n"
        "import ec_layout\n"
        "print('ENABLED', ec_layout._fast_astar_enabled())\n"
    )
    for val, want in (("0", "False"), ("1", "True")):
        env = {**os.environ, "EASYCIRQ_ASTAR_C": val}
        p = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=300, env=env)
        out = (p.stdout or "") + (p.stderr or "")
        assert f"ENABLED {want}" in out, f"EASYCIRQ_ASTAR_C={val} 期望 {want}：\n{out}"
