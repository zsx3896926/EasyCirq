"""诊断包的验收判据（C19）+ 无遥测（B15）。

C19 的重点不是"能导出"，是**导出的东西里没有客户的设计数据**。
所以测试的做法是：**先故意把秘密放进去，再断言它没被带出来**。
只断言"README 里写了不含"，等于相信承诺，不算验证。
"""
import json
import os
import pathlib
import re
import subprocess
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"

pytestmark = pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")

# 故意放进环境里的假凭据。诊断包必须一个字都不带。
FAKE_SECRETS = {
    "OPENAI_API_KEY": "sk-LEAKCANARY-0123456789abcdef",
    "DEEPSEEK_API_KEY": "sk-LEAKCANARY-deepseek-abcdef",
    "EASYCIRQ_LLM_KEY": "sk-LEAKCANARY-llm-abcdef",
    "AWS_SECRET_ACCESS_KEY": "LEAKCANARY-aws-secret",
}
# 故意放进相位目录的假网表内容。
FAKE_NETLIST = "LEAKCANARY_NETLIST R1 10k 0402 NET_3V3 NET_GND"


def _make_bundle(tmp_path):
    phase_dir = tmp_path / "phase"
    phase_dir.mkdir()
    (phase_dir / "leakcanary.json").write_text(json.dumps({
        "schema": "easycirq-phase/v1",
        "phase": "S5",
        "fingerprint": "deadbeefdeadbeef",
        "evidence": {"S5": {"verdict": "pass", "detail": FAKE_NETLIST}},
        # 未来可能加的字段：故意塞一份网表，看会不会被带出去
        "netlist": FAKE_NETLIST,
    }), encoding="utf-8")

    env = {**os.environ, "EASYCIRQ_PHASE_DIR": str(phase_dir)}
    env.update(FAKE_SECRETS)
    out = tmp_path / "diag.zip"
    p = subprocess.run([str(EXE), "diag", "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300, env=env)
    assert p.returncode == 0, p.stderr[-1500:]
    assert out.is_file(), "诊断包没生成"
    return out


def _all_bytes(zpath):
    with zipfile.ZipFile(zpath) as z:
        return {name: z.read(name) for name in z.namelist()}


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return _make_bundle(tmp_path_factory.mktemp("diag"))


def test_bundle_has_the_expected_entries(bundle):
    names = set(_all_bytes(bundle))
    for must in ("manifest.json", "README.txt", "doctor.txt", "phase.json", "env.json"):
        assert must in names, "诊断包缺 %s" % must


def test_bundle_carries_no_secrets(bundle):
    """故意放进环境的四个假密钥，一个都不许出现在包里。"""
    for name, data in _all_bytes(bundle).items():
        text = data.decode("utf-8", "replace")
        assert "LEAKCANARY" not in text, (
            "诊断包的 %s 里出现了标记串，说明有东西被带出来了：\n%s"
            % (name, text[:600]))
        for var, value in FAKE_SECRETS.items():
            assert value not in text, "%s 的值泄漏进了 %s" % (var, name)


def test_bundle_carries_no_netlist_even_from_unexpected_fields(bundle):
    """相位证据文件里塞了一份网表，连"未来才加的字段"也不许带出去。"""
    for name, data in _all_bytes(bundle).items():
        assert b"LEAKCANARY_NETLIST" not in data, "网表内容泄漏进了 %s" % name


def test_phase_json_keeps_only_state_and_fingerprint(bundle):
    """证据只留状态与指纹 —— 白名单挑字段，不是整份复制。"""
    doc = json.loads(_all_bytes(bundle)["phase.json"])
    projects = doc.get("projects") or {}
    assert "leakcanary" in projects, "没读到我们种的那份证据：%s" % list(projects)
    one = projects["leakcanary"]
    assert one.get("phase") == "S5"
    assert set(one).issubset({"schema", "phase", "fingerprint", "evidence"}), one
    assert "netlist" not in one, "整份复制了证据文件"


def test_readme_tells_the_user_what_is_and_is_not_inside(bundle):
    text = _all_bytes(bundle)["README.txt"].decode("utf-8")
    assert "没有收录" in text
    assert "网表" in text and "密钥" in text
    assert "是我们的 bug" in text, "要允许用户质疑这个包"


def test_manifest_declares_its_own_exclusions(bundle):
    doc = json.loads(_all_bytes(bundle)["manifest.json"])
    assert doc["schema"] == "easycirq-diag/v1"
    assert doc["version"]
    joined = " ".join(doc["excluded"])
    for word in ("netlist", "credentials", "schematic"):
        assert word in joined, "清单没声明排除 %s" % word


def test_env_is_an_allowlist_not_a_dump(bundle):
    """环境变量走白名单：不含任何 *_KEY / *_SECRET / *_TOKEN。"""
    doc = json.loads(_all_bytes(bundle)["env.json"])
    for k in doc:
        upper = k.upper()
        assert not upper.endswith(("_KEY", "_SECRET", "_TOKEN", "_PASSWORD")), (
            "env.json 里出现了凭据类变量：%s" % k)


# ── B15 无遥测：静态检查，代码里不该有对外网络调用 ────────────────────
def test_panel_and_diag_never_call_out():
    """面板与诊断包都不该往外发东西。

    这条是静态检查：这两个文件里不该出现 http.Client / net.Dial 之类的出站调用，
    也不该出现外部域名。served 页面里的 CSP 另有测试管。
    """
    for rel in ("runtime/internal/app/cmd_panel.go",
                "runtime/internal/app/cmd_diag.go"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "net/http" in src or "archive/zip" in src
        for forbidden in ("http.Get(", "http.Post(", "http.NewRequest(",
                          "net.Dial(", "net.DialTimeout("):
            assert forbidden not in src, "%s 里出现了出站调用：%s" % (rel, forbidden)
        urls = re.findall(r'https?://[A-Za-z0-9.\-]+', src)
        external = [u for u in urls if "127.0.0.1" not in u and "localhost" not in u]
        assert not external, "%s 里有外部地址：%s" % (rel, external)


def test_panel_page_loads_nothing_external():
    html = (ROOT / "runtime/internal/app/panel/index.html").read_text(encoding="utf-8")
    for tag in ("<script src=", "<link ", "<img src=\"http", "@import"):
        assert tag not in html, "页面引用了外部资源：%s" % tag
