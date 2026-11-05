"""S1 规格自检的验收 —— **一个永远通过的 checker 毫无价值**。

所以这里既测"好 spec 通过"，也测"坏 spec 被抓"，而且四类错误各来一条：
端口名打错、绑到不存在的轨、NC 指向不存在的端口、跨页网不在电源树里。

这四类都是真实会发生的：前两类我在板1/板2 上亲手犯过，
后两类是 S2 排线时才暴露、而那时已经很难分清是规划错还是落图错。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKER = ROOT / "easycirq" / "scripts" / "sch_spec_check.py"
SPEC = ROOT / "reports" / "hard-board" / "board2" / "spec.json"
BLOCKS = ROOT / "runtime" / "internal" / "blocks" / "data"

pytestmark = pytest.mark.skipif(
    not CHECKER.is_file() or not BLOCKS.is_dir(),
    reason="没有 S1 自检脚本或块库数据",
)


def run_checker(spec_path):
    p = subprocess.run([sys.executable, str(CHECKER), str(spec_path),
                        "--blocks-dir", str(BLOCKS), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    return p.returncode, json.loads(p.stdout)


def test_board2_spec_passes(tmp_path):
    if not SPEC.is_file():
        pytest.skip("板2 的 spec.json 不在")
    code, out = run_checker(SPEC)
    assert code == 0, "板2 的 spec 应当通过自检：%r" % out.get("problems")
    assert out["verdict"] == "pass"


@pytest.mark.parametrize("mutate,expect", [
    # 端口名打错
    (lambda d: d["modules"][0]["ports"].update(
        {"VBAT_RAWW": d["modules"][0]["ports"].pop("VBAT_RAW")}), "不存在"),
    # 绑到不存在的轨
    (lambda d: d["modules"][2]["ports"]["VIN"].update({"bind_to": "+9V"}), "+9V"),
    # NC 指向不存在的端口
    (lambda d: d["nc"].append({"id": "NC-BAD", "pin": "M9:NOPE", "reason": "x"}), "M9:NOPE"),
    # 跨页网不在电源树里
    (lambda d: d["cross_page_nets"]["nets"].append("+42V"), "+42V"),
])
def test_checker_catches_real_mistakes(tmp_path, mutate, expect):
    if not SPEC.is_file():
        pytest.skip("板2 的 spec.json 不在")
    d = json.loads(SPEC.read_text(encoding="utf-8"))
    mutate(d)
    bad = tmp_path / "broken.json"
    bad.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    code, out = run_checker(bad)
    assert code != 0, "坏 spec 必须被拒"
    joined = "\n".join(out["problems"])
    assert expect in joined, "没有点名这个错误（%s）：%r" % (expect, joined)


def test_checker_flags_missing_schema(tmp_path):
    """没有 schema 的 JSON 不该被当成 spec 收下。"""
    bad = tmp_path / "no-schema.json"
    bad.write_text(json.dumps({"modules": []}), encoding="utf-8")
    code, out = run_checker(bad)
    assert code != 0
    assert any("schema" in p for p in out["problems"])
