#!/usr/bin/env python3
"""Run several routing profiles on the same board and print a Pareto table.

The two open decisions (stackup, pour strategy) are branches of one another, and
comparing them by hand means re-reading eight handoff sections. This runs the
profiles back to back and marks which ones are non-dominated, so "which branch is
better" is answered by numbers with a timestamp, not by memory.

Results are cached per (profile, dump, placement) so re-reading the table is
instant; pass --refresh to force a re-run.

Usage:
    python tools/layout/compare.py --dump dump2.json --place ec-placed.json \
        --profiles shared-pour,exclusive-pour,two-layer --out compare.md
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reproduce  # noqa: E402

# Lower is better for all of these; skew is the max across bus groups.
GATE_VECTOR = ("unrouted_legs", "congestion_cells", "clearance_violations",
               "nets_unconnected", "pad_layer_gaps", "pour_islands")


def _fingerprint(path):
    st = os.stat(path)
    return "%s:%d:%d" % (os.path.basename(path), st.st_size, int(st.st_mtime))


def _metric_version():
    """Fingerprint the code that DEFINES the KPIs, not just the inputs.

    The cache key used to be (profile, dump, placement) only, so changing what
    `clearance_violations` counts — which happened (track/pad was added) — would
    have served last version's numbers from the cache and compared new code
    against old results.  Any edit to the metric module or the profile presets
    now invalidates the whole cache by construction.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return "|".join(_fingerprint(os.path.join(here, n))
                    for n in ("ec_layout.py", "reproduce.py"))


def _cache_key(profile, dump, place):
    raw = "|".join([profile, _fingerprint(dump), _fingerprint(place), _metric_version()])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def measure(profile, dump, place, cache_dir=None, refresh=False):
    key = _cache_key(profile, dump, place)
    path = os.path.join(cache_dir, key + ".json") if cache_dir else None
    if path and not refresh and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    kpi, skew, ok, gate_fail, why = reproduce.run(dump, place, profile=profile)
    row = {"profile": profile, "ok": ok, "why": why,
           "kpi": {k: kpi.get(k) for k in GATE_VECTOR + ("vias", "plane_vias",
                                                         "vias_in_pad", "tracks",
                                                         "total_length_mil",
                                                         "diagonal_ratio")},
           "skew": skew,
           "skew_max": max(skew.values()) if skew else 0.0}
    if path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(row, f, indent=1)
    return row


def vector(row):
    return tuple([row["kpi"][k] or 0 for k in GATE_VECTOR] + [row["skew_max"]]) 


def dominates(a, b):
    va, vb = vector(a), vector(b)
    return all(x <= y for x, y in zip(va, vb)) and any(x < y for x, y in zip(va, vb))


def pareto(rows):
    return [r["profile"] for r in rows
            if not any(dominates(o, r) for o in rows if o is not r)]


def table(rows):
    head = ("| profile | unrouted | congestion | clearance | unconn | pad gaps | "
            "islands | vias | length | skew max | pareto |")
    sep = "|---" * 11 + "|"
    out = [head, sep]
    front = set(pareto(rows))
    for r in rows:
        k = r["kpi"]
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %.0f | %.1f | %s |" % (
            r["profile"], k["unrouted_legs"], k["congestion_cells"],
            k["clearance_violations"], k["nets_unconnected"], k["pad_layer_gaps"],
            k["pour_islands"], k["vias"], k["total_length_mil"] or 0.0,
            r["skew_max"], "**yes**" if r["profile"] in front else ""))
    return "\n".join(out), sorted(front)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--profiles", default="shared-pour,exclusive-pour")
    ap.add_argument("--cache-dir")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    names = [p.strip() for p in a.profiles.split(",") if p.strip()]
    unknown = [n for n in names if n not in reproduce.PROFILES]
    if unknown:
        print("unknown profile(s): %s (have: %s)" % (
            ", ".join(unknown), ", ".join(sorted(reproduce.PROFILES))))
        return 3

    rows = []
    for name in names:
        print("running %s ..." % name, flush=True)
        rows.append(measure(name, a.dump, a.place, a.cache_dir, a.refresh))

    text, front = table(rows)
    print()
    print(text)
    print()
    print("non-dominated: %s" % ", ".join(front) if front else "non-dominated: (none)")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n\nnon-dominated: " + ", ".join(front) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
