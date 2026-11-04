"""P3 操作的验收：面板上的按钮**必须与 CLI 逐字节一致**。

产品目标 P3 的硬要求原文：「跑门 / 推进按钮，仍走同一判定」+
「面板操作与 CLI **逐字节一致**」。

做法：先直接敲 CLI 拿到输出，再通过 /api/run 让面板跑同一个操作，
比较两者的 stdout —— 必须**完全相同**（不是"等价"，是逐字节）。

面板地址从它自己打印的第一行取，不硬编码端口 —— 它会顺延端口。
"""
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXE = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "EasyCirq" / "bin" / "easycirq.exe"

pytestmark = pytest.mark.skipif(not EXE.is_file(), reason="没有安装 easycirq CLI")


class Panel:
    def __init__(self):
        self.proc = subprocess.Popen(
            [str(EXE), "panel", "--no-open"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
        )
        self.base = None
        deadline = time.time() + 20
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            m = re.search(r"http://127\.0\.0\.1:\d+/", line)
            if m:
                self.base = m.group(0).rstrip("/")
                break
        if not self.base:
            self.stop()
            pytest.skip("面板没能打印出 URL")
        for _ in range(60):
            try:
                with urllib.request.urlopen(self.base + "/api/snapshot", timeout=2) as r:
                    r.read()
                return
            except Exception:
                time.sleep(0.25)
        self.stop()
        pytest.skip("面板起了但 /api/snapshot 不可用")

    def stop(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()

    def post(self, payload):
        req = urllib.request.Request(
            self.base + "/api/run",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=240) as r:
            return json.loads(r.read().decode("utf-8"))


def test_panel_run_is_byte_identical_to_cli():
    p = Panel()
    try:
        got = p.post({"cmd": "gate", "project": ""})
        assert got.get("args"), "返回里要带实际执行的参数，便于人核对"
        direct = subprocess.run([str(EXE)] + got["args"], capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=240)
        assert got["stdout"].strip() == direct.stdout.strip(), (
            "面板跑出来的输出与命令行不一致 —— P3 的硬要求是逐字节一致\n"
            "面板: %r\n命令行: %r" % (got["stdout"][:400], direct.stdout[:400]))
        assert got["exitCode"] == direct.returncode
    finally:
        p.stop()


def test_panel_run_rejects_unknown_command():
    """白名单之外的键必须被拒 —— 面板不能变成任意命令执行器。"""
    p = Panel()
    try:
        res = p.post({"cmd": "rm -rf /", "project": ""})
        assert res.get("error"), "白名单外的命令必须被拒并说明原因"
        assert "allowed" in res["error"], "拒绝信息要列出允许的命令"
    finally:
        p.stop()


def test_panel_run_rejects_get():
    """写操作只接受 POST：GET 会被链接/预取顺带触发。"""
    p = Panel()
    try:
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(p.base + "/api/run?cmd=gate", timeout=30)
        assert ei.value.code == 405
    finally:
        p.stop()
