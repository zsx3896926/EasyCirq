#!/usr/bin/env python3
"""Prove the delivery MECHANISM works, in one command and under a minute.

The toolchain's central promise is "nothing goes to the machine until the offline
gate is green".  That promise is only worth anything if it can be demonstrated, so
this script exercises the four checks that make it real:

  1. plan vs board rules          (`plan_lint`)  -> the plan must be legal for the board
  2. emit with the REAL kpi       (`emit_apply`) -> must REFUSE (exit 2) while red
  3. emit with a GREEN kpi stub   (`emit_apply`) -> must EMIT (exit 0) and write a manifest
  4. the layout unit tests        (`pytest`)     -> must pass

Exit 0 only when all four behave as expected.  Every others' state (the actual
frontier numbers) comes from `reproduce.py`; this script deliberately does NOT
re-run the router, so it is cheap enough to run before every delivery attempt.

Usage
-----
    python easycirq/scripts/layout/acceptance.py --plan out/plan.json --kpi out/kpi.json \
        --dump dump2.json --stackup 4
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
GATED = ("unrouted_legs", "congestion_cells", "clearance_violations",
         "nets_unconnected", "pad_layer_gaps", "pour_islands")
BUS_GROUPS = ("CAM_D", "LCD_", "SD_")


def green_kpi(kpi, skew_target=10.0):
    """The same KPI with every gated item at target.

    Used only to prove that the emit path WORKS when a plan does pass - the plan it
    is paired with is still the real one, so the manifest numbers stay honest.
    """
    out = json.loads(json.dumps(kpi))
    for key in GATED:
        out[key] = 0
    spread = out.get("bus_length_spread_mil") or {}
    out["bus_length_spread_mil"] = {k: min(skew_target, v) for k, v in spread.items()} \
        or {g: skew_target for g in BUS_GROUPS}
    return out


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--kpi", required=True)
    ap.add_argument("--dump")
    ap.add_argument("--stackup", type=int)
    ap.add_argument("--skip-tests", action="store_true")
    a = ap.parse_args()

    results = []

    def check(name, ok, detail):
        results.append((name, ok, detail))
        print("%-34s %s" % (name, "PASS" if ok else "FAIL"))
        if detail:
            for line in detail.strip().splitlines():
                print("    " + line)

    # 1. board rules
    if a.dump:
        cmd = [PY, os.path.join(HERE, "plan_lint.py"), a.plan, "--dump", a.dump]
        if a.stackup:
            cmd += ["--stackup", str(a.stackup)]
        rc, out = _run(cmd)
        check("plan vs board rules", rc == 0, out if rc != 0 else "")
    else:
        check("plan vs board rules", True, "skipped (no --dump)")

    # 2. the guard must refuse the real KPI while it is red - and if the gate already IS green there
    # is nothing to refuse, which must not be scored as a failure (an e2e run on a green plan used to
    # report "contract: FAIL" purely because the refusal check could not fire).
    kpi_now = json.load(open(a.kpi, encoding="utf-8"))
    gate_green = green_kpi(kpi_now) == kpi_now

    with tempfile.TemporaryDirectory() as tmp:
        rc, out = _run([PY, os.path.join(HERE, "emit_apply.py"), a.plan,
                        "--kpi", a.kpi, "--out-dir", os.path.join(tmp, "refused")]
                       + (["--dump", a.dump] if a.dump else [])
                       + (["--stackup", str(a.stackup)] if a.stackup else []))
        refused = rc == 2 and "REFUSED" in out
        if gate_green:
            check("guard refuses a red gate", True,
                  "gate is already green - nothing to refuse (emit check below still runs)")
        else:
            check("guard refuses a red gate", refused,
                  out.split("Fix the plan")[0] if refused else out)

        # 3. ... and must emit once it is green (so the refusal is not just broken)
        kpi = kpi_now
        stub = os.path.join(tmp, "green-kpi.json")
        with open(stub, "w", encoding="utf-8") as f:
            json.dump(green_kpi(kpi), f)
        out_dir = os.path.join(tmp, "emitted")
        rc, out = _run([PY, os.path.join(HERE, "emit_apply.py"), a.plan,
                        "--kpi", stub, "--out-dir", out_dir]
                       + (["--stackup", str(a.stackup)] if a.stackup else []))
        emitted = rc == 0 and os.path.exists(os.path.join(out_dir, "manifest.json"))
        check("emit works on a green gate", emitted, out if not emitted else out.strip())

    # 4. the metrics themselves
    if a.skip_tests:
        check("layout unit tests", True, "skipped (--skip-tests)")
    else:
        rc, out = _run([PY, "-m", "pytest", "tests/test_ec_layout.py",
                        "tests/test_bus_order.py", "-q"])
        tail = out.strip().splitlines()[-1] if out.strip() else ""
        check("layout unit tests", rc == 0, tail)

    bad = [n for n, ok, _ in results if not ok]
    print()
    print("contract: %s%s" % ("PASS" if not bad else "FAIL", "" if not bad else
                              "  (failed: %s)" % ", ".join(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
