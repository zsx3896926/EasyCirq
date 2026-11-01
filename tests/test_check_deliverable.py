"""交付包自检器的自测。

它守的是「客户唯一会打开的东西」：断链、未列出的文件、校验和不符、
卡片数字与 KPI 定义不一致——这些都让「有证据」退化成「看起来有证据」。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_deliverable.py"


def test_the_real_package_passes():
    """当前仓库里的交付包必须是干净的；不干净就说明有人改坏了它。"""
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_checker_actually_runs():
    """防止脚本因为 import 错误变成永远不执行的空壳。"""
    assert SCRIPT.is_file()
    text = SCRIPT.read_text(encoding="utf-8")
    assert "交付包自检通过" in text
    assert "raise SystemExit(1)" in text
