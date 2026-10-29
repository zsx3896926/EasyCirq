"""Deterministic EDA replay plan for an ``easycirq-page-template/v1`` file.

The plan is an ordered list of ``easycirq`` CLI command strings (clear page →
place every part → wire every net member → NC the explicit-NC pins → save →
snapshot + review), plus machine-readable checks.  It does not execute anything.

Output schema: ``easycirq-replay-plan/v1``.
"""

from __future__ import annotations

import json
import pathlib

SCHEMA = "easycirq-replay-plan/v1"
BIN = "easycirq"


def _kind(net):
    if net == "GND":
        return "gnd"
    if net in ("AGND", "DGND", "PGND"):
        return "agnd"
    if net in ("3V3", "+3V3", "5V", "+5V", "3V3_L3B_AU", "VBATT"):
        return "power"
    return "net_label"


def build(template, device_map, *, project, page):
    """Compile the replay plan; raises ValueError on missing device mappings."""
    commands = [f"{BIN} project open --project-uuid {project} --allow-discard-unsaved",
                f'{BIN} doc open {page} --project {project}']
    missing = []
    for part in template.get("parts") or []:
        info = device_map.get(part["ref"])
        if not info:
            missing.append(part["ref"])
            continue
        commands.append(
            f"{BIN} sch place --lib {info['lib']} --uuid {info['dev']} "
            f"--x {part['x']} --y {part['y']} --designator {part['ref']} "
            f"--doc {page}")
    if missing:
        raise ValueError("no device mapping for: %s" % ", ".join(sorted(missing)))
    nc_members = []
    for net in template.get("nets") or []:
        name = net["name"]
        if name == "__NC__":
            nc_members = list(net.get("members") or [])
            continue
        for ref, pin in net.get("members") or []:
            commands.append(
                f'{BIN} sch connect --pin {ref}:{pin} --kind {_kind(name)} '
                f'--net "{name}" --doc {page}')
    for ref, pin in nc_members:
        commands.append(f"{BIN} sch no-connect --designator {ref} --pin {pin} "
                        f"--doc {page}")
    commands.append(f"{BIN} doc reload {page} --project {project}")
    commands.append(f"python tools/ace_snapshot.py {page} replay.snapshot.json")
    commands.append("python tools/ace_review.py replay.snapshot.json")
    commands.append("python tools/net_integrity.py replay.snapshot.json")
    checks = [
        {"check": "parts_placed", "expect": len(template.get("parts") or [])},
        {"check": "nets_wired",
         "expect": sum(len(n.get("members") or []) for n in template.get("nets") or []
                       if n.get("name") != "__NC__")},
        {"check": "grid_aligned",
         "expect": all(float(p["x"]) % 5 == 0 and float(p["y"]) % 5 == 0
                       for p in template.get("parts") or [])},
        {"check": "review_verdict", "expect": "pass"},
        {"check": "net_integrity", "expect": "pass"},
    ]
    return {"schema": SCHEMA, "project": project, "page": page,
            "template": template.get("page"),
            "commands": commands, "checks": checks,
            "counts": {"commands": len(commands),
                       "parts": len(template.get("parts") or []),
                       "net_members": sum(len(n.get("members") or [])
                                          for n in template.get("nets") or []
                                          if n.get("name") != "__NC__")}}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("template")
    parser.add_argument("device_map")
    parser.add_argument("--project", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--emit")
    args = parser.parse_args()
    tpl = json.loads(pathlib.Path(args.template).read_text(encoding="utf-8"))
    devs = json.loads(pathlib.Path(args.device_map).read_text(encoding="utf-8"))
    plan = build(tpl, devs, project=args.project, page=args.page)
    if args.emit:
        pathlib.Path(args.emit).write_text(
            json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(plan["counts"], ensure_ascii=False))
