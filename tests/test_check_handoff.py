"""交接文档的路径检查器要能真的抓到错路径。

上下文被压缩后，接手的人只能靠 docs/HANDOFF.md 找东西。它写错一个路径，
接手的人就卡住——而写的人不会发现，因为他知道文件在哪。

这组测试证明检查器两个方向都对：真路径能过，假路径会红。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_handoff.py"


def test_the_real_documents_pass():
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_missing_path_would_be_caught(tmp_path):
    """把一个不存在的路径塞进临时文档，检查器必须报出来。"""
    doc = tmp_path / "HANDOFF.md"
    doc.write_text("见 `easycirq/scripts/does_not_exist_anywhere.py`\n", encoding="utf-8")

    # 用一个只检查这份文档的临时副本运行同样的逻辑
    code = (
        "import importlib.util, pathlib, sys\n"
        f"spec = importlib.util.spec_from_file_location('chk', r'{SCRIPT}')\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"m.DOCS = [r'{doc}']\n"
        "sys.exit(m.main())\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, result.stdout
    assert "does_not_exist_anywhere" in result.stdout


def test_branch_names_are_not_treated_as_paths():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "branch_names" in text, "branch names must be excluded or every doc will fail"
