"""Finish the plane-net feature so it matches its test contract.

The test says: a plane net spends VIAS, not tracks, and still counts as connected.
The router was additionally adding `stubs` (tracks) for plane nets, so the emitted
plan contained GND tracks and `test_plane_net_gets_no_tracks_but_still_connects`
failed. Two changes:

1. route(): do not attach plane stubs as tracks.
2. connectivity_from_plan(): vias marked plane_layer on the same net are one node —
   the plane is what joins the pads.
"""
from pathlib import Path

p = Path(r"hds-verifier/tools/layout/ec_layout.py")
s = p.read_text(encoding="utf-8")

old_hook = """    if plane_nets and plane_layer:
        vias, stubs = plane_access(board, best_routed, plane_nets, int(plane_layer))
        for net, paths in stubs.items():
            best_routed.setdefault(net, []).extend(paths)
        if vias:
            best_routed[PLANE_VIA_KEY] = vias"""
new_hook = """    if plane_nets and plane_layer:
        vias, stubs = plane_access(board, best_routed, plane_nets, int(plane_layer))
        # A plane net lives on its plane: pads reach it through a via at the pad, so
        # emitting tracks for it is wrong (the contract is via-only, and GND tracks
        # would then conflict with everything the negotiator routed).
        if vias:
            best_routed[PLANE_VIA_KEY] = vias"""
assert old_hook in s, "plane hook not found"
s = s.replace(old_hook, new_hook)

anchor = """    for v in plan.get("vias") or []:
        base = (v["net"],) + q(v["x"], v["y"], 1)
        for layer in (2, 3, 4):
            union(base, (v["net"],) + q(v["x"], v["y"], layer))"""
assert anchor in s, "connectivity via block not found"
s = s.replace(anchor, anchor + """

    # Plane nets: every pad is joined through the plane, so all of that net's plane
    # access vias form a single node. Without this the pads look disconnected once
    # the tracks are (correctly) not emitted.
    plane_nodes = defaultdict(list)
    for v in plan.get("vias") or []:
        if v.get("plane_layer"):
            plane_nodes[v["net"]].append((v["net"],) + q(v["x"], v["y"], 1))
    for net, nodes in plane_nodes.items():
        for n in nodes[1:]:
            union(nodes[0], n)""")

p.write_text(s, encoding="utf-8")
print("plane feature finished")
