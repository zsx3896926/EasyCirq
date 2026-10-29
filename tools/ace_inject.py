"""Error-injection harness for the ACE-review checklist.

Loads a snapshot, applies one deterministic mutation at a time, and checks
whether the reviewer detects the injected defect with the expected rule.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ace_review as ar  # noqa: E402


def kinds(snap):
    return {c["ref"]: ar.designator_kind(c["ref"]) for c in snap["components"]}


def comp_by_ref(snap, ref):
    for c in snap["components"]:
        if c["ref"] == ref:
            return c
    return None


def remove_component(snap, ref):
    comp = comp_by_ref(snap, ref)
    if not comp:
        return None
    snap["components"] = [c for c in snap["components"] if c["ref"] != ref]
    return comp


def nets_of(comp):
    return {p.get("net") for p in comp.get("pins") or [] if p.get("net")}


def decoupling_candidates(snap):
    """Caps sitting on a power net within reach of an IC power pin."""
    k = kinds(snap)
    nets = ar._nets(snap)
    near = {}
    for comp in snap["components"]:
        if k.get(comp["ref"]) != "ic":
            continue
        ic = ar._bbox_center(comp)
        for pin in comp.get("pins") or []:
            pname = str(pin.get("name") or "").upper()
            pnet = pin.get("net") or ""
            if pname not in ("VDD", "VDDIO", "VCC", "AVDD", "DVDD", "PVDD",
                             "VDDA", "VDDD", "VBAT", "VSYS", "VIN"):
                continue
            if not ar.POWER_RE.match(pnet.replace("-", "_")):
                continue
            caps = []
            for ref, _ in nets.get(pnet, set()):
                if k.get(ref) != "capacitor":
                    continue
                cap = comp_by_ref(snap, ref)
                cpos = ar._bbox_center(cap)
                if ic and cpos and ar._dist(ic, cpos) <= 180.0:
                    if any(p.get("net") and ar.GROUND_RE.match(p["net"].replace("-", "_"))
                           for p in cap.get("pins") or []):
                        caps.append(ref)
            for ref in caps:
                near.setdefault(ref, (comp["ref"], pin.get("number"), pname, pnet))
    return near


def mutations(snap):
    out = []
    k = kinds(snap)

    for ref in decoupling_candidates(snap):
        def m(s=snap, ref=ref):
            remove_component(s, ref)
        out.append(("remove-decoupling:" + ref, "R03-decoupling", m))

    def move_cap(s=snap):
        for ref in decoupling_candidates(s):
            cap = comp_by_ref(s, ref)
            b = cap["bbox"]
            b["minX"] += 500
            b["maxX"] += 500
            return ref
        return None
    out.append(("move-decoupling-far", "R03-decoupling", move_cap))

    def remove_i2c_pullup(s=snap):
        nets = ar._nets(s)
        removed = []
        for name, pins in nets.items():
            if not ar.I2C_RE.match(name.replace("-", "_")):
                continue
            for ref, _ in list(pins):
                if k.get(ref) == "resistor":
                    remove_component(s, ref)
                    removed.append(ref)
        return removed
    out.append(("remove-i2c-pullup", "R02-i2c-pullup", remove_i2c_pullup))

    def break_ground_tie(s=snap):
        removed = []
        for comp in list(s["components"]):
            if k.get(comp["ref"]) not in ("resistor", "ferrite"):
                continue
            ns = {n for n in nets_of(comp) if n}
            grounds = {n for n in ns if ar.GROUND_RE.match(n.replace("-", "_"))}
            if len(grounds) >= 2:
                remove_component(s, comp["ref"])
                removed.append(comp["ref"])
        return removed
    out.append(("break-ground-tie", "R04-ground-tie", break_ground_tie))

    def float_power_pin(s=snap):
        for comp in s["components"]:
            if k.get(comp["ref"]) != "ic":
                continue
            for pin in comp.get("pins") or []:
                if str(pin.get("name") or "").upper() in (
                        "VDD", "VDDIO", "VCC", "AVDD", "PVDD"):
                    pin["net"] = None
                    return "%s:%s" % (comp["ref"], pin.get("number"))
        return None
    out.append(("float-power-pin", "R01-floating-pin", float_power_pin))

    def remove_feedback_cap(s=snap):
        nets = ar._nets(s)
        removed = []
        for name, pins in nets.items():
            if ar.FB_RE.match(name):
                for ref, _ in list(pins):
                    if "capacitor" == ar.designator_kind(ref):
                        remove_component(s, ref)
                        removed.append(ref)
        return removed
    out.append(("remove-feedback-cap", "R05-feedback-cap", remove_feedback_cap))

    def remove_enable_net(s=snap):
        for comp in s["components"]:
            if k.get(comp["ref"]) != "ic":
                continue
            for pin in comp.get("pins") or []:
                if ar.ENABLE_RE.match(str(pin.get("name") or "")) and pin.get("net"):
                    pin["net"] = None
                    return "%s:%s" % (comp["ref"], pin.get("number"))
        return None
    out.append(("remove-enable-net", "R06-enable-net", remove_enable_net))

    def remove_esd(s=snap):
        nets = ar._nets(s)
        for comp in s["components"]:
            if k.get(comp["ref"]) != "connector":
                continue
            for pin in comp.get("pins") or []:
                net = pin.get("net")
                if not net:
                    continue
                removed = []
                for ref, _ in list(nets.get(net, set())):
                    if k.get(ref) in ("diode", "resistor", "ferrite"):
                        remove_component(s, ref)
                        removed.append(ref)
                if removed:
                    return removed
        return None
    out.append(("remove-esd-series", "R07-esd-series", remove_esd))

    def remove_power_tp(s=snap):
        nets = ar._nets(s)
        for name, pins in nets.items():
            if ar.POWER_RE.match(name.replace("-", "_")):
                for ref, _ in list(pins):
                    if k.get(ref) == "testpoint":
                        remove_component(s, ref)
                        return ref
        return None
    out.append(("remove-power-testpoint", "R08-power-testpoint", remove_power_tp))

    def rename_auto_net(s=snap):
        for comp in s["components"]:
            for pin in comp.get("pins") or []:
                if pin.get("net"):
                    pin["net"] = "C1_N99"
                    return pin["net"]
        return None
    out.append(("rename-auto-net", "R09-auto-net-name", rename_auto_net))

    def clear_titleblock(s=snap):
        fields = (s.get("titleblock") or {}).get("fields") or {}
        for key in list(fields):
            fields[key] = ""
        s["titleblock"] = {"fields": fields or {"Title": ""}}
    out.append(("clear-titleblock", "R10-titleblock", clear_titleblock))

    return out


def run(snapshot):
    baseline = ar.review(copy.deepcopy(snapshot))
    base_rules = {f["rule"] for f in baseline["findings"]}
    base_counts = {}
    for f in baseline["findings"]:
        base_counts[f["rule"]] = base_counts.get(f["rule"], 0) + 1
    rows = []
    for name, expected, mutate in mutations(snapshot):
        snap = copy.deepcopy(snapshot)
        target = mutate(snap) if mutate.__code__.co_argcount >= 1 else mutate()
        # bind snapshots for closures created with default args is handled per lambda
        report = ar.review(snap)
        count = sum(1 for f in report["findings"] if f["rule"] == expected)
        base = base_counts.get(expected, 0)
        messages = " | ".join(f["message"] for f in report["findings"]
                              if f["rule"] == expected)
        changed = json.dumps(snap, sort_keys=True) != json.dumps(snapshot, sort_keys=True)
        if base > 0:
            changed = False  # baseline already violates this rule; delta is not measurable
        token_hit = bool(target) and str(target).split(":")[0] in messages
        detected = changed and count > 0 and (
            count > base or expected not in base_rules or token_hit)
        rows.append({"mutation": name, "expected_rule": expected,
                     "applicable": changed, "detected": bool(detected),
                     "target": target, "findings_of_rule": count,
                     "baseline_of_rule": base, "delta": count - base,
                     "token_hit": token_hit})
    applicable = [r for r in rows if r["applicable"]]
    total = len(applicable)
    hit = sum(1 for r in applicable if r["detected"])
    return {
        "schema": "easycirq-ace-injection/v1",
        "baseline": {"verdict": baseline["verdict"],
                     "errors": baseline["metrics"]["errors"],
                     "warnings": baseline["metrics"]["warnings"],
                     "rules": baseline["metrics"]["rules"]},
        "mutations": rows,
        "detected": hit, "total": total,
        "not_applicable": [r["mutation"] for r in rows if not r["applicable"]],
        "detection_rate": round(hit / total, 3) if total else None,
    }


if __name__ == "__main__":
    import json
    path = pathlib.Path(sys.argv[1])
    snap = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(run(snap), ensure_ascii=False, indent=1))
