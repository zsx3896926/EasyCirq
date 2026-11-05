"""路径 A 的验收：**能不能离线从库符号读出引脚坐标**。

这是 S3 的关键前提。`lib-layout` 要 `measurements`（每件 bbox + 引脚坐标），
而块库没有原理图几何 —— 若库符号也读不出来，S5 就永远不可能是"一次性写入"。

答案：**能**。`lib symbol export-source` 导出的 `.elibz2` 里有 `ProLib_*.elibu`，
它是行内 JSON 记录流：

    {"type":"PIN","id":"e3"}                          ← 引脚记录
    {"x":-55,"y":-30,"length":20,"rotation":0}        ← 紧跟的几何
    {"parentId":"e3","key":"Pin Name","value":"VIN"}  ← 引脚的属性（名字）

记录之间用 `|` 分隔。注意 `symbol2.json` 只有元数据，**几何在 .elibu 里**。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_symbol_measure.py"
ARCHIVE = pathlib.Path(__import__("os").environ.get("TEMP", ".")) / "xl1509.elibz2"

pytestmark = pytest.mark.skipif(
    not SCRIPT.is_file() or not ARCHIVE.is_file(),
    reason="没有度量脚本，或没有已导出的符号档案",
)

# 块库里 XL1509 的 note 写着：1=VIN, 2=OUTPUT, 3=FEEDBACK, 4=ON/OFF, 5-8=GND
EXPECTED_NAMES = {"VIN", "OUTPUT", "FB", "ON/OFF", "GND"}


def _parse():
    sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
    import zipfile
    z = zipfile.ZipFile(ARCHIVE)
    name = next(n for n in z.namelist() if n.endswith(".elibu"))
    text = z.read(name).decode("utf-8", errors="replace")
    import sch_symbol_measure as m
    return m.parse_elibu(text)


def test_symbol_geometry_is_extractable_offline():
    """从 .elibu 里能解出引脚、名字和坐标 —— 这是 S3 能离线的前提。"""
    pins, shapes, records = _parse()
    assert len(records) > 0
    assert len(pins) == 8, "SOIC-8 应当有 8 个引脚，得到 %d" % len(pins)

    names = {p["name"] for p in pins.values() if p["name"]}
    assert names == EXPECTED_NAMES, (
        "引脚名必须与块库注明的说明一致（%r），得到 %r" % (EXPECTED_NAMES, names))

    for pid, p in pins.items():
        assert p.get("x") is not None and p.get("y") is not None, \
            "引脚 %s 没有坐标" % pid
        assert p.get("rotation") is not None, "引脚 %s 没有旋转" % pid

    xs = [p["x"] for p in pins.values()]
    ys = [p["y"] for p in pins.values()]
    assert max(xs) > min(xs) and max(ys) > min(ys), "引脚分布退化成一条线"


def test_pin_names_match_the_block_library():
    """块库的内部网用引脚**名**（`U5.VIN`），所以量出来的名字必须能对上。

    对不上的话，网表与几何就 join 不起来 —— 那这条离线链等于没通。
    """
    pins, _, _ = _parse()
    blk = json.loads(
        (ROOT / "runtime" / "internal" / "blocks" / "data" / "xl1509_buck_12v_5v.json")
        .read_text(encoding="utf-8"))
    block_pin_names = set()
    for members in blk.get("internal_nets") or []:
        for m in members:
            if m.startswith("PORT:"):
                continue
            role, _, pin = m.partition(".")
            if role.upper().startswith("U"):
                block_pin_names.add(pin)
    measured = {p["name"] for p in pins.values() if p["name"]}
    # 块库用 GND* 表示"多个同名地脚里的一个"，所以比对时去掉尾星号
    normalized = {n.rstrip("*") for n in block_pin_names}
    missing = normalized - measured
    assert not missing, "块库用到但符号里量不到的引脚名：%r" % missing


def test_cli_runs_and_reports_pins():
    p = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120)
    assert p.returncode == 0, p.stderr[-500:]
    out = p.stdout
    assert "引脚 8 个" in out, out[:400]
    for n in ("VIN", "OUTPUT", "FB", "ON/OFF", "GND"):
        assert n in out, "输出里没有引脚 %r" % n
