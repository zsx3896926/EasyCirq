#!/usr/bin/env python3
"""One-command offline pipeline: frozen snapshot -> checks -> KPI verdict.

Turns the manual S3+S4 sequence into one deterministic call:

    connectivity.json (+ list.json / svg-text.json)
        -> layout.json (via layout_from_easycirq.py)
        -> sch_connectivity_metrics.py / sch_layout_check.py / sch_wire_metrics.py
        -> sch_kpi.py -> PASS | REVIEW | BLOCKED

It never calls EDA and never edits a project. Every intermediate report is
written to ``--out-dir`` so the verdict can be audited, and the exit code is
the KPI gate's own (0/1/2). A missing input is a ``BLOCKED`` verdict, never a
silent pass.

Snapshot directory contract (only 1 is required):
  connectivity.json   easycirq sch connectivity --page <P>            (required)
  list.json           easycirq sch list --include-bbox --include-pins
                      --include-wires --include-page-primitives      (needed when layout.json is absent)
  svg-text.json       svg_text_bbox.py over the exported SVG         (optional, enables full text coverage)
  layout.json         layout_from_easycirq.py output                 (optional, skips the adapter)

Usage:
  python scripts/sch_offline_pipeline.py --snapshot-dir reports/p1-snapshot \
      --project RetroCam-02 --page P1 --out-dir reports/p1

Exit codes: 0 PASS, 1 REVIEW, 2 BLOCKED (also invalid/missing input).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
SCHEMA_SUMMARY = "easycirq-sch-offline-pipeline/v1"


# 引脚复用（KPI 10）只对**有复用资源**的器件成立：MCU / SoC / FPGA 之类。
# 电源 IC（buck/boost/ldo）的引脚是固定功能，没有复用可言。
MCU_HEADS = {"mcu", "soc", "fpga", "cpu", "dsp", "stm32", "esp", "rp2040",
             "nrf", "atmega", "ch32", "gd32", "apm32", "mm32"}


def _is_mcu_component(comp):
    """这算不算一颗有复用资源的 MCU/SoC。

    **判据要贴着被测量的东西。** `pin_plan_check.py` 判的是引脚复用与资源分配，
    只有 MCU 类器件才有这些；用"有任何 IC"当代理会把纯电源板也拖进来，
    而它对那块板根本无从测量（friction #54）。
    """
    name = str(((comp.get("device") or {}).get("name")) or "")
    head = name.split(".", 1)[0].lower() if "." in name else ""
    return head in MCU_HEADS


def _is_ic_component(comp):
    """这算不算一颗 IC。

    **先看器件身份**（型号前缀），位号只作兜底 —— 位号是派生的，
    拿它当判据时只要生成规则变了就会静默误判（friction #53：
    `buck.*` 落成 `X2`，于是"这页没有 IC"）。
    """
    name = str(((comp.get("device") or {}).get("name")) or "")
    head = name.split(".", 1)[0].lower() if "." in name else ""
    try:
        from sch_spec_netlist import PREFIX
        if PREFIX.get(head) == "U":
            return True
    except Exception:                                        # noqa: BLE001
        pass
    # 兜底：位号前缀（老口径）
    return str(comp.get("ref", "")).upper().startswith(("U", "IC"))


def _run(args, *, label, allow=(0,)):
    proc = subprocess.run([sys.executable, *map(str, args)],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    if proc.returncode not in allow:
        raise RuntimeError(f"{label} failed rc={proc.returncode}: "
                           f"{(proc.stderr or proc.stdout or '')[:800]}")
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _need(path, label):
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Frozen snapshot -> offline checks -> 15-KPI verdict")
    ap.add_argument("--snapshot-dir", required=True,
                    help="directory holding the frozen reads")
    ap.add_argument("--project", required=True)
    ap.add_argument("--project-uuid", default="",
                    help="project uuid stored in the gate token; pass it so a "
                         "uuid-targeted write passes the daemon check even when "
                         "the display name differs from what callers type")
    ap.add_argument("--page", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--profile", default="default")
    ap.add_argument("--stage", default="schematic",
                    choices=["schematic", "placed", "pcb"],
                    help="当前阶段。证据要到更晚阶段才可能产出的 KPI 记 "
                         "not_run（不阻断、也不算通过）；该测却缺证据仍记 missing（阻断）")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--design-intent",
                    help="设计意图 JSON（阈值目标、开关管负载）；不给则设计有效性报不适用")
    ap.add_argument("--reuse-layout", action="store_true",
                    help="use snapshot/layout.json instead of rebuilding from list.json")
    ap.add_argument("--json", action="store_true", help="print the summary JSON")
    args = ap.parse_args(argv)

    snap = Path(args.snapshot_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    steps = []

    def step(name, ok, detail):
        steps.append({"step": name, "ok": ok, "detail": detail})

    try:
        connectivity = _need(snap / "connectivity.json", "connectivity.json")
        listing = snap / "list.json"
        prebuilt = snap / "layout.json"
        # A prebuilt layout.json can predate the latest list read and then hide
        # what a write actually changed. Rebuild from list.json by default and
        # only reuse when there is no list read or the caller says so.
        if listing.is_file() and (not prebuilt.is_file() or not args.reuse_layout):
            layout = out / "layout.json"
            cmd = [HERE / "layout_from_easycirq.py", "--list", listing,
                   "--out", layout]
            svg = snap / "svg-text.json"
            if svg.is_file():
                cmd += ["--rendered-text", svg]
            # The list read carries no page bounds for a page that was just
            # drawn, so the adapter needs the sheet geometry explicitly:
            #   easycirq sch sheet-geometry --json > sheet.json
            sheet = snap / "sheet.json"
            if sheet.is_file():
                cmd += ["--sheet-geometry", sheet]
            try:
                _run(cmd, label="layout_from_easycirq", allow=(0,))
                step("layout", True, f"rebuilt from list -> {layout.name}")
            except RuntimeError:
                if not prebuilt.is_file():
                    raise
                # no page/sheet bounds in the list read: fall back, but say so
                layout = prebuilt
                step("layout", True,
                     "rebuild failed (missing sheet bounds); used prebuilt layout.json")
        elif prebuilt.is_file():
            layout = prebuilt
            step("layout", True, "reused prebuilt layout.json (--reuse-layout)")
        else:
            raise FileNotFoundError(
                "需要 list.json（用于生成布局）或预置 layout.json")

        checks = []
        conn_out = out / "connectivity-check.json"
        conn_cmd = [HERE / "sch_connectivity_metrics.py", "--input", connectivity]
        listing = snap / "list.json"
        if listing.is_file():
            # the connectivity IR carries no NC flag; the list read does
            conn_cmd += ["--list", listing]
        conn_cmd += ["--out", conn_out, "--quiet"]
        _run(conn_cmd, label="connectivity metrics", allow=(0, 1))
        checks.append(("connectivity", conn_out))
        step("connectivity", True, str(conn_out.name))

        drc = snap / "drc.json"
        if drc.is_file():
            erc_out = out / "erc-check.json"
            _run([HERE / "sch_drc_metrics.py", "--input", drc,
                  "--out", erc_out, "--quiet"],
                 label="drc metrics", allow=(0, 1, 2))
            checks.append(("erc", erc_out))
            step("erc", True, str(erc_out.name))

        # Schematic vs PCB: only meaningful when a board read is in the snapshot.
        pcb_dump = next((snap / name for name in ("pcb-dump.json", "pcb.json")
                         if (snap / name).is_file()), None)
        if listing.is_file() and pcb_dump is not None:
            match_out = out / "pcb-match-check.json"
            _run([HERE / "sch_pcb_net_match.py", "--schematic", listing,
                  "--pcb", pcb_dump, "--out", match_out],
                 label="schematic/pcb net match", allow=(0, 1))
            checks.append(("pcb_match", match_out))
            step("pcb_match", True, str(match_out.name))

        if listing.is_file():
            pnet_out = out / "power-net-check.json"
            # Pass the plan when present: a declared power_nets list is checked by
            # name, which works even for symbols whose pins are just "1"/"2" -
            # the case the pin-name heuristic cannot see.
            pnet_cmd = [HERE / "sch_power_net_check.py", "--list", listing]
            plan_file = snap / "pinplan.json"
            if plan_file.is_file():
                pnet_cmd += ["--plan", plan_file]
            pnet_cmd += ["--out", pnet_out]
            _run(pnet_cmd, label="power net check", allow=(0, 1))
            checks.append(("power_net", pnet_out))
            step("power_net", True, str(pnet_out.name))

        power_out = out / "power-check.json"
        power_cmd = [HERE / "sch_decoupling_metrics.py", "--input", connectivity]
        if listing.is_file():
            power_cmd += ["--list", listing]
        power_cmd += ["--out", power_out, "--quiet"]
        _run(power_cmd, label="decoupling metrics", allow=(0, 1))
        checks.append(("power", power_out))
        step("decoupling", True, str(power_out.name))

        bom = next((snap / name for name in ("bom.tsv", "bom.csv")
                    if (snap / name).is_file()), None)
        if bom is not None:
            bom_out = out / "bom-check.json"
            _run([HERE / "sch_bom_metrics.py", bom, "--out", bom_out, "--quiet"],
                 label="bom metrics", allow=(0, 1, 2))
            checks.append(("identity", bom_out))
            step("bom", True, str(bom_out.name))

            # Schematic vs BOM: a BOM stuck at an older revision ships the wrong
            # parts. On 2026-11-01 the delivered file lacked Q1 and R4 - the
            # transistor and its base resistor - while the card still said ready.
            if listing.is_file():
                bom_match_out = out / "bom-match-check.json"
                _, bom_stdout, _ = _run(
                    [HERE / "sch_bom_match.py", "--schematic", listing,
                     "--bom", bom, "--json"],
                    label="schematic/bom match", allow=(0, 2))
                bom_match_out.write_text(bom_stdout, encoding="utf-8")
                checks.append(("bom_match", bom_match_out))
                step("bom_match", True, str(bom_match_out.name))

        pinplan = snap / "pinplan.json"
        if pinplan.is_file():
            pin_out = out / "pinplan-check.json"
            rc, stdout, stderr = _run([HERE / "pin_plan_check.py", pinplan],
                                      label="pin plan check", allow=(0, 1, 2))
            if not stdout.strip():
                raise RuntimeError(f"pin_plan_check produced no report: {stderr[:400]}")
            pin_out.write_text(stdout, encoding="utf-8")
            checks.append(("pinplan", pin_out))
            step("pinplan", True, str(pin_out.name))
        else:
            # no plan supplied: only N/A when the page has no IC at all;
            # otherwise the gap stays missing and blocks the gate
            ir_data = json.loads(Path(connectivity).read_text(encoding="utf-8"))
            has_mcu = any(_is_mcu_component(c)
                          for c in ir_data.get("components") or [])
            if not has_mcu:
                pin_out = out / "pinplan-check.json"
                pin_out.write_text(json.dumps({
                    "schema": "easycirq-sch-pinplan-na/v1",
                    "verdict": "n/a",
                    "note": "页面没有 MCU/SoC（无复用资源），引脚复用不适用 —— "
                            "本判据测的是引脚复用与资源分配，"
                            "电源 IC 的引脚是固定功能",
                }, ensure_ascii=False) + "\n", encoding="utf-8")
                checks.append(("pinplan", pin_out))
                step("pinplan", True, "n/a (no IC)")

        before = snap / "connectivity-before.json"
        if before.is_file():
            diff_out = out / "netlist-diff-check.json"
            _run([HERE / "sch_connectivity_diff.py", "--before", before,
                  "--after", connectivity, "--out", diff_out, "--quiet"],
                 label="connectivity diff", allow=(0, 1))
            checks.append(("netlist", diff_out))
            step("netlist-diff", True, str(diff_out.name))

        reopen = snap / "connectivity-reopen.json"
        if reopen.is_file():
            # S5 readback: the post-reopen read must match the pre-write read
            rb_out = out / "readback-check.json"
            _run([HERE / "sch_connectivity_diff.py", "--before", connectivity,
                  "--after", reopen, "--metric", "readback_diff",
                  "--out", rb_out, "--quiet"],
                 label="readback diff", allow=(0, 1))
            checks.append(("readback", rb_out))
            step("readback", True, str(rb_out.name))

        layout_out = out / "layout-check.json"
        # rc=2 means "incomplete/blocking findings": still a usable report, the
        # KPI gate decides; do not abort the pipeline on it.
        _run([HERE / "sch_layout_check.py", layout, "--strict",
              "--out", layout_out], label="layout check", allow=(0, 1, 2))
        checks.append(("layout", layout_out))
        step("layout-check", True, str(layout_out.name))

        wire_out = out / "wire-check.json"
        try:
            _run([HERE / "sch_wire_metrics.py", layout, "--out", wire_out],
                 label="wire metrics", allow=(0,))
            step("wire", True, str(wire_out.name))
        except RuntimeError as exc:
            # A page connected entirely with net labels/flags has no wire
            # primitives, so the wire KPIs have no subject. That is "not
            # applicable", not a gate failure - and it is the normal shape of a
            # freshly drawn page.
            if "no wires" not in str(exc):
                raise
            wire_out.write_text(json.dumps({
                "schema": "easycirq-sch-wire-na/v1",
                "verdict": "n/a",
                "note": "这一页没有导线（只用网络标签/旗标连接），几何类指标不适用",
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            step("wire", True, "n/a (no wires)")
        checks.append(("wire", wire_out))

        read_out = out / "readability-check.json"
        _run([HERE / "sch_readability_metrics.py", "--ir", connectivity,
              "--layout", layout, "--out", read_out, "--quiet"],
             label="readability metrics", allow=(0, 2))
        checks.append(("readability", read_out))
        step("readability", True, str(read_out.name))
    except (OSError, RuntimeError) as exc:
        summary = {"schema": SCHEMA_SUMMARY, "project": args.project,
                   "project_uuid": args.project_uuid,
                   "page": args.page, "verdict": "BLOCKED",
                   "steps": steps, "error": str(exc)}
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"offline pipeline: BLOCKED — {exc}", file=sys.stderr)
        return 2

    history = out / "kpi-history.jsonl"
    kpi_input = out / "kpi-input.json"
    kpi_input.write_text(json.dumps({
        "schema": "easycirq-sch-kpi-input/v1",
        "project": args.project,
        "page": args.page,
        "round": args.round,
        "profile": args.profile,
        # 当前阶段：更晚阶段才可能产出的 KPI 记 not_run（不阻断、不算通过）
        "stage": args.stage,
        "history": history.name,
        "checks": [],
        "note": "由 sch_offline_pipeline.py 生成；其余检查未采集，按缺失处理。",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 设计有效性：查"连上之后会不会工作"。没有意图文件时检查器自己报 na，
    # 不冒充 pass，也不假装成失败。
    dv_out = out / "design-validity-check.json"
    dv_cmd = [HERE / "sch_design_validity.py", "--netlist", snap / "list.json",
              "--out", dv_out]
    if getattr(args, "design_intent", None):
        dv_cmd += ["--intent", args.design_intent]
    dv_rc, dv_stdout, dv_stderr = _run(dv_cmd, label="design validity",
                                       allow=(0, 1, 2))
    if dv_out.is_file():
        checks.append(("design_validity", dv_out))
        step("design-validity", True, str(dv_out.name))
    else:
        raise RuntimeError(
            f"design validity rc={dv_rc} but wrote no report. "
            f"stdout={dv_stdout[-600:]!r} stderr={dv_stderr[-600:]!r}")

    cmd = [HERE / "sch_kpi.py", "--input", kpi_input,
           "--history", history, "--record-history",
           "--out", out / "kpi-report.json", "--md", out / "kpi-report.md"]
    if args.project_uuid:
        cmd += ["--project-uuid", args.project_uuid]
    for cid, path in checks:
        cmd += ["--check", f"{cid}={path}"]
    rc, stdout, stderr = _run(cmd, label="kpi gate", allow=(0, 1, 2))

    if not (out / "kpi-report.json").is_file():
        # 门禁返回了允许的码，却没写出报告。这时最要紧的是把门禁自己的输出留下，
        # 而不是让下一行 read_text 抛一个没有上下文的 FileNotFoundError。
        raise RuntimeError(
            f"kpi gate rc={rc} but wrote no report. "
            f"stdout={stdout[-800:]!r} stderr={stderr[-800:]!r}")

    report = json.loads((out / "kpi-report.json").read_text(encoding="utf-8"))
    summary = {
        "schema": SCHEMA_SUMMARY,
        "project": report["project"],
        "page": report["page"],
        "verdict": report["verdict"],
        "apply_allowed": report["stability"]["apply_allowed"],
        "kpi": {row["id"]: {"value": row["value"], "status": row["status"]}
                for row in report["kpis"]},
        "steps": steps,
        "artifacts": sorted(p.name for p in out.iterdir() if p.is_file()),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        advisory = {item["kpi"] for item in report.get("advisory", [])}
        print(f"offline pipeline: {report['verdict']} "
              f"(apply_allowed={report['stability']['apply_allowed']})")
        for row in report["kpis"]:
            if row["status"] in ("fail", "missing", "unknown"):
                tag = "advisory" if row["id"] in advisory else row["status"]
                print(f"  {tag:<8} #{row['no']} {row['id']}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
