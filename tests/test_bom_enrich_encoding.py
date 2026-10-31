"""BOM 文本解码：探测顺序错了会把好文件读成乱码。

事故：read_text 先试 utf-16。任何偶数长度的字节串几乎都能被 utf-16 无异常解码，
于是云淡风轻地返回乱码，调用方随后报「BOM missing expected columns」——真正的
原因（编码）被藏在一条无关的错误里。

这组用例把三种输入固定下来：我们自己导出的 UTF-8、带 BOM 标记的 UTF-8、以及
真正的 UTF-16LE。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "bom-enrich.py"

HEADER = "No.\tQuantity\tComment\tDesignator\tFootprint\tValue\n"
ROW = "1\t1\t10k\tR1\tR0603\t10k\n"


def load_module():
    spec = importlib.util.spec_from_file_location("bom_enrich", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bom_enrich"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


def test_reads_plain_utf8(module, tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text(HEADER + ROW, encoding="utf-8")
    text = module.read_text(str(path))
    assert text.startswith("No.\tQuantity"), text[:60]


def test_reads_utf8_with_bom_marker(module, tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text(HEADER + ROW, encoding="utf-8-sig")
    text = module.read_text(str(path))
    assert text.startswith("No.\tQuantity"), text[:60]
    assert "\ufeff" not in text


def test_reads_utf16le_with_marker(module, tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text(HEADER + ROW, encoding="utf-16")  # writes a BOM
    text = module.read_text(str(path))
    assert text.startswith("No.\tQuantity"), text[:60]


def test_chinese_content_survives(module, tmp_path):
    path = tmp_path / "bom.csv"
    content = "No.\tComment\n1\t5025贴片蜂鸣器\n"
    path.write_text(content, encoding="utf-8")
    text = module.read_text(str(path))
    assert "5025贴片蜂鸣器" in text


def test_empty_file_returns_empty_string(module, tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(b"")
    assert module.read_text(str(path)) == ""


def test_real_exported_bom_parses(module, tmp_path):
    """我们自己的导出必须能被自己的工具解析。

    这是最初暴露问题的那一步：easycirq 导出的 BOM 交给 bom-enrich 时，
    表头被 utf-16 解成乱码，报「missing expected columns」。
    """
    sample = ROOT / "deliverables" / "alarm" / "bom.csv"
    if not sample.is_file():
        pytest.skip("no sample BOM in the delivery package")
    text = module.read_text(str(sample))
    header = text.splitlines()[0]
    assert header.startswith("No."), header[:80]
    assert "Designator" in header
