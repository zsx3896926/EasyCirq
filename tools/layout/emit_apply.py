#!/usr/bin/env python3
"""Turn a routed plan into an on-machine application bundle - or refuse to.

This is the gate between "offline looks good" and "write it to the real board".
The project rule is one-way: nothing goes to the machine until the offline gate is
green.  So this tool's default behaviour for a failing plan is to REFUSE, and the
refusal is the product: it names exactly which KPIs are open.

For a passing plan it writes:

  apply-plan.json   normalised operations (one track/via per entry) in the same
                    shape easycirq's `pcb apply` playbook consumes
  manifest.json     counts per net/layer, board identity, sha256 of the plan
  APPLY.md          the exact commands and the read-back checklist

Usage:
    python tools/layout/emit_apply.py plan.json --kpi kpi.json --dump dump2.json --out-dir DIR
    python tools/layout/emit_apply.py plan.json --kpi kpi.json --force --reason "..."

Exit codes: 0 emitted, 2 refused (gate not green), 3 bad input.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ec_layout as ec  # noqa: E402


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gate_reasons(kpi):
    """Everything that must be zero (or under 50 mil for skew) before writing."""
    reasons = []
    for key in ("unrouted_legs", "congestion_cells", "clearance_violations",
                "nets_unconnected", "pad_layer_gaps", "pour_islands"):
        val = kpi.get(key)
        if val is None:
            reasons.append("%s: NOT MEASURED" % key)
        elif val != 0:
            reasons.append("%s: %s" % (key, val))
    for group, spread in (kpi.get("bus_length_spread_mil") or {}).items():
        if spread >= 50:
            reasons.append("bus skew %s: %.1f mil (target <50)" % (group, spread))
    return reasons


def board_rule_reasons(dump_path, plan):
    """Second gate: the plan must agree with the BOARD's own rules.

    The router's constants are not the board's rules. Measured: the board says via
    diameter 24.02 mil while the router assumed 20, which turned "121 violations"
    into 238; and the board declares 2 copper layers while the plan uses 4.
    """
    import plan_lint
    with open(dump_path, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    out = []
    for name, ok, detail in plan_lint.lint(board, plan):
        if not ok:
            out.append("%s: %s" % (name, detail))
    return out


def normalise(plan):
    tracks = []
    for t in plan.get("tracks") or []:
        tracks.append({
            "net": t["net"], "layer": int(t["layer"]), "width": round(float(t["width"]), 3),
            "x1": round(float(t["x1"]), 3), "y1": round(float(t["y1"]), 3),
            "x2": round(float(t["x2"]), 3), "y2": round(float(t["y2"]), 3),
        })
    vias = []
    for v in plan.get("vias") or []:
        entry = {"net": v["net"], "x": round(float(v["x"]), 3), "y": round(float(v["y"]), 3)}
        if v.get("plane_layer"):
            entry["pour_layer"] = int(v["plane_layer"])
        if v.get("in_pad"):
            entry["in_pad"] = True      # needs POFV resin fill - fabrication must know
        vias.append(entry)
    return {"tracks": tracks, "vias": vias}


def build_manifest(plan, kpi, dump_path, sha):
    tracks = plan["tracks"]
    per_layer = Counter(t["layer"] for t in tracks)
    per_net = Counter(t["net"] for t in tracks)
    return {
        "plan_sha256": sha,
        "dump": os.path.basename(dump_path) if dump_path else None,
        "counts": {
            "tracks": len(tracks),
            "vias": len(plan["vias"]),
            "access_vias": sum(1 for v in plan["vias"] if v.get("pour_layer")),
            "vias_in_pad": sum(1 for v in plan["vias"] if v.get("in_pad")),
            "tracks_per_layer": {str(k): v for k, v in sorted(per_layer.items())},
            "tracks_per_net_top": dict(per_net.most_common(10)),
        },
        "kpi_at_emit": {k: kpi.get(k) for k in (
            "unrouted_legs", "congestion_cells", "clearance_violations",
            "nets_unconnected", "pad_layer_gaps", "pour_islands", "vias",
            "total_length_mil", "diagonal_ratio", "bus_length_spread_mil")},
        "fabrication_notes": _fab_notes(plan),
    }


def _fab_notes(plan):
    notes = []
    in_pad = sum(1 for v in plan["vias"] if v.get("in_pad"))
    if in_pad:
        notes.append("%d via(s) are via-in-pad and need resin fill (POFV)" % in_pad)
    pours = sorted({v["pour_layer"] for v in plan["vias"] if v.get("pour_layer")})
    if pours:
        notes.append("copper pours required on layer(s) %s (GND/+3V3 modelled as pours)"
                     % ", ".join(str(l) for l in pours))
    return notes


def apply_md(plan, manifest):
    c = manifest["counts"]
    lines = [
        "# Apply bundle",
        "",
        "Plan sha256: `%s`" % manifest["plan_sha256"],
        "",
        "| item | count |",
        "|---|---|",
        "| tracks | %d |" % c["tracks"],
        "| vias | %d |" % c["vias"],
        "| access vias | %d |" % c["access_vias"],
        "| vias in pad (POFV) | %d |" % c["vias_in_pad"],
        "",
        "Tracks per layer: %s" % ", ".join("L%s=%s" % kv for kv in c["tracks_per_layer"].items()),
        "",
        "## Steps",
        "",
        "1. Take a board snapshot and keep it: `easycirq pcb dump --include-copper > before.json`",
        "2. Dry-run the plan: `easycirq apply --plan apply-plan.json --dry-run`",
        "3. Apply, then SAVE, then reload and dump again (`after.json`).",
        "4. Diff `after.json` against this bundle: track and via counts must match the table,",
        "   and `easycirq pcb drc` must be clean.",
        "5. Run `--via-relocate` style read-back ONLY from the reloaded dump, never from memory.",
        "",
        "## Fabrication notes",
        "",
    ]
    lines += ["- %s" % n for n in manifest["fabrication_notes"]] or ["- (none)"]
    lines += ["", "> Do not apply this bundle if the plan file's sha256 differs from the one above."]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--kpi", required=True)
    ap.add_argument("--dump")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--reason", default="")
    a = ap.parse_args()

    plan = load(a.plan)
    kpi = load(a.kpi)
    reasons = gate_reasons(kpi)
    if a.dump:
        try:
            reasons += board_rule_reasons(a.dump, plan)
        except Exception as exc:            # a lint that cannot run must not pass
            reasons.append("board rule lint failed: %s" % exc)
    if reasons and not a.force:
        print("REFUSED: the offline gate is not green, so nothing goes to the machine.")
        for r in reasons:
            print("  - %s" % r)
        print("\nFix the plan, or pass --force --reason '<who accepted it and why>'.")
        return 2
    if reasons and a.force and not a.reason.strip():
        print("REFUSED: --force needs --reason (why is it acceptable to write a dirty plan?)")
        return 2

    norm = normalise(plan)
    sha = hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()
    manifest = build_manifest(norm, kpi, a.dump, sha)

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "apply-plan.json"), "w", encoding="utf-8") as f:
        json.dump(norm, f, indent=1)
    with open(os.path.join(a.out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(a.out_dir, "APPLY.md"), "w", encoding="utf-8") as f:
        f.write(apply_md(norm, manifest))
    print("emitted %s: %d tracks, %d vias (%d access, %d in-pad)" % (
        a.out_dir, manifest["counts"]["tracks"], manifest["counts"]["vias"],
        manifest["counts"]["access_vias"], manifest["counts"]["vias_in_pad"]))
    if a.force:
        print("FORCED with reason: %s" % a.reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())

