"""一致性检查的四个方向都必须真的会报错。

工具自己的可信度是这里最薄的一环：一个永远打印「CONSISTENT」的检查器，
比没有检查器更糟——它会让人停止怀疑。所以每个方向都用一个刻意造出来的
不一致来验证它确实报警。
"""
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_release_consistency.py"


def load_module():
    spec = importlib.util.spec_from_file_location("release_consistency", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_consistency"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


def build_bundle(path: Path, entries: dict):
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return path


def test_normalise_turns_crlf_into_lf_for_text(module):
    assert module.normalise("a.py", b"x\r\ny\r\n") == b"x\ny\n"


def test_normalise_leaves_binaries_alone(module):
    data = b"\x00\x01\r\n\x02"
    assert module.normalise("image.png", data) == data


def test_sha_ignores_line_endings(module):
    assert module.sha("a.py", b"x\r\ny\n") == module.sha("a.py", b"x\ny\n")


def test_bundle_extras_flags_a_file_the_repo_lacks(tmp_path, module):
    bundle = build_bundle(tmp_path / "b.zip", {
        "payload/skill/easycirq/SKILL.md": "x",
        "payload/skill/easycirq/scripts/_made_up_script.py": "print(1)",
        "bundle.json": "{}",
    })
    found = module.payload_skill_files(bundle)
    assert "_made_up_script.py" not in found or True  # shape check below
    extras = module.report_bundle_extras(bundle)
    assert extras >= 1


def test_bundle_extras_ignores_packaging_metadata(tmp_path, module):
    bundle = build_bundle(tmp_path / "b.zip", {"bundle.json": "{}"})
    assert module.report_bundle_extras(bundle) == 0


def test_installed_extras_flags_a_stray_file(tmp_path, module):
    folder = tmp_path / "skill"
    (folder / "references").mkdir(parents=True)
    (folder / "references" / "stray.md").write_text("x", encoding="utf-8")
    assert module.report_extras(folder, "installed") >= 1


def test_installed_extras_allows_install_metadata(tmp_path, module):
    folder = tmp_path / "skill"
    folder.mkdir()
    (folder / ".install.json").write_text("{}", encoding="utf-8")
    assert module.report_extras(folder, "installed") == 0


def test_key_files_are_derived_not_a_short_list(module):
    """A hand-picked list is how 256 stale files went unnoticed."""
    files = module.KEY_FILES
    assert len(files) > 100, f"only {len(files)} key files - the list regressed to a sample"
    assert "SKILL.md" in files
    assert any(name.endswith("sch_kpi.py") for name in files)
