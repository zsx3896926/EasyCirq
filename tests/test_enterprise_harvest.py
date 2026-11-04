"""harvest 的守卫测试：从历史 DRC 里长候选，但**绝不自动采纳**。

这套测试盯的是纪律，不是功能：
  · CLI 噪声（警告行 + 尾部日志）必须容忍，且警告要报出来
  · 目录里不是 DRC 的 JSON 不许算进来（否则违规数翻倍）
  · 输出必须没有 disposition —— 这样 promote 才会拒绝
  · 缺型号时必须明说"够阈值但补不上"，不许瞎猜一个
"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
HARVEST = SCRIPTS / "enterprise_harvest.py"
sys.path.insert(0, str(SCRIPTS))


def run(args, timeout=300):
    return subprocess.run([sys.executable, str(HARVEST), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, cwd=str(ROOT))


def drc_doc(violations, passed=False):
    return {"passed": passed,
            "counts": {}, "total": len(violations),
            "violations": violations}


def viol(rule, obj, msg, net=None):
    return {"rule": rule, "objType": obj, "message": msg,
            "net": net, "ruleName": "x"}


def write_report(path, doc, prefix="", suffix="\n\npcb drc: done\n"):
    """模拟 EasyEDA 的 CLI 输出：警告行 + JSON + 尾部日志。"""
    path.write_text(prefix + json.dumps(doc) + suffix, encoding="utf-8")


def dump_with(devices):
    comps = [{"designator": d, "device": v, "pads": [{"net": "N"}]}
             for d, v in devices.items()]
    return {"components": comps, "outline": {"bbox": {}}}


# ── 1. 容忍 CLI 噪声，并把警告报出来 ────────────────────────────────────
def test_tolerates_cli_noise_and_reports_warnings():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        write_report(td / "drc0.json",
                     drc_doc([viol("Clearance Error", "SMD Pad to Via",
                                   "(+3V3): e1 to (GND): e2 distance is 0mil")]),
                     prefix="\u26a0 staleRisk: PCB was mutated\n")
        p = run(["--drc", str(td), "--json"])
        assert p.returncode == 0, (p.stdout + p.stderr)[-800:]
        d = json.loads(p.stdout)
        h = d["harvest"]
        assert h["totals"]["violations"] == 1, "带噪声的 JSON 没读进来"
        warns = " ".join(w["warning"] for w in h["inputs"]["warnings"])
        assert "staleRisk" in warns, "staleRisk 警告没报出来"


# ── 2. 目录里非 DRC 的 JSON 不许算 ─────────────────────────────────────
def test_skips_non_drc_json_in_a_directory():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        write_report(td / "drc0.json",
                     drc_doc([viol("Connection Error", "SMD Pad",
                                   "(+3V3): U1_4 is disconnected")]))
        # 这不是 DRC 报告
        (td / "dump2.json").write_text(json.dumps(dump_with({"U1": "X"})),
                                       encoding="utf-8")
        (td / "plan.json").write_text(json.dumps({"tracks": [], "vias": []}),
                                      encoding="utf-8")
        p = run(["--drc", str(td), "--json"])
        h = json.loads(p.stdout)["harvest"]
        assert h["totals"]["violations"] == 1, (
            f"非 DRC 文件被算进来了：{h['totals']['violations']}")
        assert len(h["inputs"]["files_skipped"]) == 2, "没记录跳过的文件"


# ── 3. 干净的 DRC（violations 为空）必须当成 DRC，不是"非 DRC" ──────────
def test_clean_report_is_still_a_drc_report():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        write_report(td / "clean.json", drc_doc([], passed=True))
        p = run(["--drc", str(td), "--json"])
        h = json.loads(p.stdout)["harvest"]
        assert len(h["inputs"]["files_ok"]) == 1, "干净报告被误判成非 DRC"
        assert h["totals"]["violations"] == 0


# ── 4. 输出必须没有 disposition，且 promote 一定拒绝 ────────────────────
def test_candidates_have_no_disposition_and_promote_refuses():
    import review_ledger

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        vs = [viol("Clearance Error", "SMD Pad to Via",
                   "(+3V3): J3_1 to (GND): e2 distance is 0mil")
              for _ in range(60)]
        write_report(td / "drc0.json", drc_doc(vs))
        (td / "dump.json").write_text(
            json.dumps(dump_with({"J3": "FPC0.52H-WS-24P"})), encoding="utf-8")
        out = td / "cand.json"
        p = run(["--drc", str(td), "--dump", str(td / "dump.json"),
                 "--out", str(out)])
        assert p.returncode == 0, (p.stdout + p.stderr)[-800:]
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema"] == "easycirq-harvest/v1"
        assert payload["entries"], "够阈值却没出候选"
        for e in payload["entries"]:
            assert "disposition" not in e, (
                "候选里出现 disposition 就等于自动采纳，纪律被破坏")

        # 直接喂给 promote：必须被拒
        ledger = {"schema": review_ledger.SCHEMA, "entries": payload["entries"]}
        r = review_ledger.promote(ledger, td / "lib")
        assert r["ok"] is False, "promote 竟然接受了候选"
        assert any("必须显式选边" in str(pb) for pb in r["problems"])
        assert not (td / "lib" / "rules.from-review.json").is_file(), (
            "被拒时不该写出任何规则")


# ── 5. 缺型号必须明说，不许猜 ──────────────────────────────────────────
def test_missing_device_is_stated_not_guessed():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        vs = [viol("Connection Error", "SMD Pad",
                   "(+3V3): J4_8 is disconnected from other objects")
              for _ in range(60)]
        write_report(td / "drc0.json", drc_doc(vs))
        # dump 里故意没有 J4 的 device
        (td / "dump.json").write_text(json.dumps(dump_with({})), encoding="utf-8")
        out = td / "cand.json"
        p = run(["--drc", str(td), "--dump", str(td / "dump.json"),
                 "--out", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["entries"] == [], "缺型号却出了候选"
        notes = " ".join(payload["not_proposed"])
        assert "缺型号" in notes, f"没说明为什么不出候选：{notes[:300]}"


# ── 6. 两类违规都必须被标成"不能直接变规则"，并给出原因 ────────────────
def test_both_violation_kinds_are_explained_as_not_directly_rules():
    import enterprise_harvest as eh

    for rule in ("Connection Error", "Clearance Error"):
        why = eh.WHY_NOT_RULE.get(rule)
        assert why, f"{rule} 没有解释"
        assert "不能" in why or "只能" in why


# ── 7. 阈值以下不出候选，且逐条说明 ────────────────────────────────────
def test_below_threshold_is_reported_with_reason():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        vs = [viol("Clearance Error", "SMD Pad to Via",
                   "(+3V3): R1_1 to (GND): e2 distance is 0mil")
              for _ in range(5)]
        write_report(td / "drc0.json", drc_doc(vs))
        (td / "dump.json").write_text(
            json.dumps(dump_with({"R1": "RC0603"})), encoding="utf-8")
        out = td / "cand.json"
        p = run(["--drc", str(td), "--dump", str(td / "dump.json"),
                 "--out", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["entries"] == []
        assert any("低于候选阈值" in n for n in payload["not_proposed"])
