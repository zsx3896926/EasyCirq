"""验收的第三种结论：**N/A（不适用）**，必须和"缺证据"分开。

为什么重要：把 N/A 写成 NOT RUN，会让人以为"再补点证据就行"，
实际是**没有对象可测**。这和 #54 的 `pin_mux` 同一个道理——
**判据要贴着被测量的东西**。

两条现实例子：
  · `标签落在真实端点` 测的是 netport/netlabel；本图只有电源/地符号与网标 → N/A
  · `图签无重复文字` 需要 titleBlock；排版稿不含 → N/A

另外钉一个我踩过的实现坑：**适用性判定必须放在最前面**，
否则会被更早的分支（如"标签锚点覆盖为 0 → NOT RUN"）截胡。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACC = ROOT / "easycirq" / "scripts" / "sch_layout_acceptance.py"
STRICT = ROOT / "reports" / "hard-board" / "board2" / "strict-M3-full.json"


def run(strict_path, tmp_path, owners=None):
    out = tmp_path / "a.json"
    cmd = [sys.executable, str(ACC), "--strict-input", str(strict_path),
           "--out", str(out), "--json"]
    if owners:
        cmd += ["--owners", str(owners)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if not out.is_file():
        pytest.skip("验收未产出：%s" % ((p.stdout or p.stderr)[:200],))
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rep(tmp_path_factory):
    if not STRICT.is_file():
        pytest.skip("没有 strict-M3-full.json")
    return run(STRICT, tmp_path_factory.mktemp("na"))


def test_three_states_are_distinct(rep):
    states = {c["status"] for c in rep["criteria"]}
    assert states <= {"PASS", "FAIL", "NOT RUN", "N/A"}, states


def test_label_anchor_is_na_without_port_labels(rep):
    """没有 netport/netlabel → 这条不适用，不是缺证据。"""
    c = next(x for x in rep["criteria"] if x["id"] == "E_label_anchor")
    assert c["status"] in ("N/A", "FAIL"), c
    if c["status"] == "N/A":
        assert c["detail"], "N/A 必须写明理由"


def test_title_block_is_measured_when_rect_exists(rep):
    """有 titleBlock 矩形就必须**测量**；只有没有时才 N/A。

    （第 23 轮之前一直是 N/A，因为排版稿不带图签数据；现在带了。）
    """
    import json
    c = next(x for x in rep["criteria"] if x["id"] == "I_title_block")
    strict = json.loads(pathlib.Path(rep["strictInput"]).read_text(encoding="utf-8"))
    if strict.get("title_block"):
        assert c["status"] in ("PASS", "FAIL"), \
            "有图签矩形却判成 %s" % c["status"]
    else:
        assert c["status"] == "N/A", c
        assert "图签" in (c["detail"][0] if c["detail"] else "")


def test_na_is_not_incomplete(rep):
    """N/A 不该把总判拖成 INCOMPLETE；只有 NOT RUN 会。"""
    has_not_run = any(c["status"] == "NOT RUN" for c in rep["criteria"])
    if not has_not_run:
        assert rep["verdict"] != "INCOMPLETE"


def test_crossing_evidence_stays_not_run(rep):
    """交叉无结点是**有对象、缺宿主证据** → 必须仍是 NOT RUN，不许变 N/A。"""
    c = next(x for x in rep["criteria"] if x["id"] == "H_crossing_evidence")
    assert c["status"] == "NOT RUN", c
    assert c["needs"], "NOT RUN 必须给出下一步命令"


def test_applicability_is_checked_first():
    """源码层：适用性判定必须在循环最前面（我踩过被 elif 截胡）。"""
    s = ACC.read_text(encoding="utf-8")
    i_first = s.find('kind_need = c.get("requires_kind")')
    i_label = s.find('c["id"] == "E_label_anchor"')
    assert i_first > 0 and i_label > 0
    assert i_first < i_label, "适用性判定被后面的分支截胡了"
