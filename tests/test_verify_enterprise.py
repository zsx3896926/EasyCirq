"""端到端演练必须一直是绿的。

这个工具的价值在于它**每条资产都跑正反例**，而不是列数量。
所以只要有任何一条链断了，它必须返回非零——测试就是把这件事钉住。
"""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "verify_enterprise.py"


@pytest.mark.skipif(not TOOL.is_file(), reason="演练脚本不存在")
def test_enterprise_loop_is_intact():
    # 产物可能不存在于全新 checkout（构建产物或可再生证据）。
    # 在就跑真断言，不在就明确 skip —— 不伪装成通过。
    if not (ROOT / "examples/enterprise-knowledge/parts.company.json").exists():
        pytest.skip("缺少 examples/enterprise-knowledge/parts.company.json（示例库）")
    proc = subprocess.run([sys.executable, str(TOOL)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900, cwd=str(ROOT))
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out[-2000:]
    assert "15/15" in out, out[-2000:]
    # 每一层都要有正反例，不能只报"加载了 N 条"
    for must in ("故意违规板 → 必须拦住",
                 "无关上下文不误召回",
                 "判据用企业实测值并标出来源",
                 "不加任何参数",
                 "违规板：说违反、给依据、给找人"):
        assert must in out, f"缺少这条生效证据：{must}\n{out[-1500:]}"
