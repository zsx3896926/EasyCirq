"""官方资料调研的守卫测试。

防的是：这份调研的结论被以后的人丢掉或改错。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "easyeda-official-resources.md"
DUMP = ROOT / "reports" / "eda-api-classes.txt"


def test_doc_exists():
    assert DOC.is_file(), "官方资料调研文档不见了"
    s = DOC.read_text(encoding="utf-8")
    assert "结论先行" in s


def test_records_the_netlist_api_answer():
    """网表有官方接口——这条决定"转换器不用做"。"""
    s = DOC.read_text(encoding="utf-8")
    assert "getNetlistFile" in s
    assert "JLCEDA" in s
    # 必须写明我们已经在用正确接口，不是废弃的那个
    assert "deprecated" in s
    assert "getNetlist" in s


def test_records_official_ai_bridge_as_competitor():
    """官方有自己的 AI 桥接，这条不能装作不知道。"""
    s = DOC.read_text(encoding="utf-8")
    assert "eext-run-api-gateway" in s
    assert "easyeda-api-skill" in s
    # 关键判断：我们做治理层，不做执行层
    assert "治理" in s


def test_records_official_cli_and_mcp():
    s = DOC.read_text(encoding="utf-8")
    assert "--mcp" in s
    assert "invoke" in s
    # 版本要求必须写清，否则会误判私有部署能不能用
    assert "V4.1.70" in s


def test_api_dump_is_kept():
    """API 全表要留档，否则核对结果无法复现。"""
    assert DUMP.is_file(), "API 全表 dump 丢了"
    text = DUMP.read_text(encoding="utf-8", errors="replace")
    assert "classToProperty" in text
    assert "sch_Netlist" in text
    assert "sys_WebSocket" in text, "没确认 sys_WebSocket 是官方接口"


def test_check_script_exists():
    p = ROOT / "tools" / "check_against_official.py"
    assert p.is_file(), "核对脚本丢了，结论就无法复现"
