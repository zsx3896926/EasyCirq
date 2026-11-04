"""一站式验证入口的测试：正常包通过，故意弄坏的包必须失败。

为什么要有这条：这个入口的价值在于它**真的会跑**那四个判据。
如果它自己判错了（比如 exit code 聚合错、或者包坏了还报通过），
那它就是又一个"看起来在执行"的东西。
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "verify_fan_board.py"
PKG = ROOT / "deliverables" / "fan-controller"


def run_verify(package):
    return subprocess.run(
        [sys.executable, str(TOOL), "--package", str(package)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900, cwd=str(ROOT))


@pytest.mark.skipif(not PKG.is_dir(), reason="风扇板交付包不存在")
def test_real_package_passes():
    # 产物可能不存在于全新 checkout（构建产物或可再生证据）。
    # 在就跑真断言，不在就明确 skip —— 不伪装成通过。
    if not (ROOT / "reports/fan-controller/evidence").exists():
        pytest.skip("缺少 reports/fan-controller/evidence（可再生的证据，不入库）")
    proc = run_verify(PKG)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]
    assert "总判定：全部通过" in proc.stdout


@pytest.mark.skipif(not PKG.is_dir(), reason="风扇板交付包不存在")
def test_package_with_wrong_intent_fails():
    """把意图里的位号改成网表里没有的 → 判据必须报错，入口必须返回非 0。

    这是"故意制造该问题 → 必须报错"那条：如果入口不管内容只跑命令，
    这个用例会失败。
    """
    with tempfile.TemporaryDirectory() as tmp:
        copy = pathlib.Path(tmp) / "pkg"
        shutil.copytree(PKG, copy)
        intent_path = copy / "design" / "intent.json"
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        intent["switches"][0]["part"] = "Q99"     # 网表里没有这颗
        intent_path.write_text(json.dumps(intent, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        proc = run_verify(copy)
        assert proc.returncode != 0, (
            "位号改成不存在的之后仍然报通过：\n" + proc.stdout[-1500:])
        assert "总判定：全部通过" not in proc.stdout
