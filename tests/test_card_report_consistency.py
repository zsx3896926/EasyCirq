"""给「卡片判定 vs 随包门禁报告」这条新检查加测试。

这个缺口是真实发生过的：原理图加了 R6、板子没同步，门禁里 pcb_match 是红的，
而 card.txt 第一行还写着"可以下单"——五条检查没有一条会看这件事。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_deliverable.py"
PACKAGE = ROOT / "deliverables" / "alarm"


def refresh_checksums(package: pathlib.Path) -> None:
    lines = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        if path.parent == package and path.name == "README.md":
            continue
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  "
                     + path.relative_to(package).as_posix())
    (package / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


class CardMatchesReportTests(unittest.TestCase):
    """卡片判定必须和随包报告一致。"""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="card-report-"))
        # 检查器内部用的是相对路径 deliverables/alarm 和 metrics/...，
        # 所以临时目录必须复现同样的结构，而不是随便放一个目录。
        self.pkg = self.tmp / "deliverables" / "alarm"
        shutil.copytree(PACKAGE, self.pkg)
        (self.tmp / "metrics").mkdir(parents=True)
        shutil.copy2(ROOT / "metrics" / "schematic-kpi.v1.json",
                     self.tmp / "metrics" / "schematic-kpi.v1.json")
        # README 里有指向 ../../docs/... 的相对链接；临时目录里也放一份占位，
        # 否则会被"README 断链"这条规则拦下，测不到本文件想测的东西。
        docs = self.tmp / "docs"
        docs.mkdir()
        (docs / "alarm-functional-defect.md").write_text("# 占位\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        return subprocess.run([sys.executable, str(SCRIPT)],
                              cwd=str(self.tmp), capture_output=True,
                              text=True, encoding="utf-8", errors="replace")

    def _set_report(self, verdict):
        report = json.loads((self.pkg / "design" / "kpi-report.json")
                            .read_text(encoding="utf-8"))
        report["verdict"] = verdict
        (self.pkg / "design" / "kpi-report.json").write_text(
            json.dumps(report, ensure_ascii=False), encoding="utf-8")

    def _set_card_first_line(self, line):
        card = self.pkg / "card.txt"
        rest = card.read_text(encoding="utf-8").splitlines()[1:]
        card.write_text(line + "\n" + "\n".join(rest) + "\n", encoding="utf-8")

    def test_consistent_pair_passes(self):
        self._set_report("BLOCKED")
        self._set_card_first_line("❌ 还不能打样")
        refresh_checksums(self.pkg)
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout[-800:])

    def test_card_claims_orderable_but_report_blocked(self):
        """真实踩过的情形：卡片说可以下单，报告说 BLOCKED。"""
        self._set_report("BLOCKED")
        self._set_card_first_line("✅ 可以下单（原理图与板子都通过）")
        refresh_checksums(self.pkg)
        proc = self._run()
        self.assertEqual(proc.returncode, 1, proc.stdout[-800:])
        self.assertIn("卡片判定与门禁报告矛盾", proc.stdout)

    def test_card_says_blocked_but_report_pass(self):
        """反过来也不行：报告通过了，卡片还说不能打样，同样不一致。"""
        self._set_report("PASS")
        self._set_card_first_line("❌ 还不能打样")
        refresh_checksums(self.pkg)
        proc = self._run()
        self.assertEqual(proc.returncode, 1, proc.stdout[-800:])
        self.assertIn("卡片判定与门禁报告矛盾", proc.stdout)

    def test_missing_report_is_reported(self):
        (self.pkg / "design" / "kpi-report.json").unlink()
        refresh_checksums(self.pkg)
        proc = self._run()
        self.assertEqual(proc.returncode, 1, proc.stdout[-800:])
        self.assertIn("没有随附门禁报告", proc.stdout)


if __name__ == "__main__":
    unittest.main()
