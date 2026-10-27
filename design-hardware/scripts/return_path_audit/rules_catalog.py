"""Rule catalogue: stable rule ids, groups, default severity and advice.

Severity is about *engineering action*, determinism is about *evidence*:

* ``error``            verified violation of the declared rule/geometry
* ``warning``          verified risk or an unproven-but-suspicious topology
* ``info``             recorded fact / limitation that changes nothing by itself

Determinism values: ``proven`` (geometry or declared evidence proves it),
``potential`` (topology suggests it, evidence incomplete), ``unknown`` (cannot
be decided from this input).

Every rule names the technical-source family it belongs to.  Concrete
``SRC-xx`` citations are attached by ``sources.py`` so the register
(``docs/parallel-return-path-audit/source-register.md``) stays the single
source of truth.  A rule with no first-party numeric source must keep its
threshold project-configured and say so in the report.
"""
from __future__ import annotations

RULES = {
    # ------------------------------------------------------------ E1 stackup
    "RP-E1-101": {
        "group": "E1", "title": "Stackup is incomplete",
        "severity": "info", "determinism": "unknown", "family": "R1",
        "description": "The stackup declares itself incomplete, so physical order and reference adjacency cannot be fully trusted.",
        "recommendation": "Provide the complete copper order, roles and dielectric thicknesses before relying on reference-intent results.",
    },
    "RP-E1-102": {
        "group": "E1", "title": "Signal layer has no adjacent reference plane layer",
        "severity": "warning", "determinism": "proven", "family": "R1",
        "description": "A copper layer with role=signal has neither an adjacent plane above nor below in the declared physical order.",
        "recommendation": "Declare which adjacent copper layer is the reference plane, or correct the physical layer order/roles.",
    },
    "RP-E1-103": {
        "group": "E1", "title": "Declared reference layer is not a plane layer",
        "severity": "error", "determinism": "proven", "family": "R1",
        "description": "reference_assignment points at a layer whose declared role is signal.",
        "recommendation": "Point the reference at the plane layer that actually carries the reference net, or fix the stackup roles.",
    },
    "RP-E1-104": {
        "group": "E1", "title": "Reference net missing on the declared reference layer",
        "severity": "error", "determinism": "proven", "family": "R1",
        "description": "The reference layer carries copper of other nets, but no copper object of the declared reference net.",
        "recommendation": "Correct the reference net, or supply the actual reference copper snapshot for that net.",
    },
    "RP-E1-105": {
        "group": "E1", "title": "No reference copper data for the declared reference layer",
        "severity": "info", "determinism": "unknown", "family": "R1",
        "description": "No reference_copper object exists on the declared reference layer, so continuity cannot be evaluated.",
        "recommendation": "Export the reference copper (actual fill) for that layer and net.",
    },
    "RP-E1-106": {
        "group": "E1", "title": "Reference copper is not an actual fill result",
        "severity": "info", "determinism": "unknown", "family": "R5",
        "description": "Reference copper availability is pour_boundary/ideal_plane/unknown instead of an actual filled-copper snapshot.",
        "recommendation": "Supply actual fill copper; a pour boundary or ideal plane cannot prove reference continuity.",
    },
    "RP-E1-107": {
        "group": "E1", "title": "Reference intent is only a candidate",
        "severity": "info", "determinism": "unknown", "family": "R1",
        "description": "reference_assignment basis is 'candidate': no single reference plane has been declared.",
        "recommendation": "Declare the intended reference layer per segment; the nearest copper layer is not automatically the reference.",
    },
    "RP-E1-108": {
        "group": "E1", "title": "Reference layer is not adjacent to the signal layer",
        "severity": "warning", "determinism": "proven", "family": "R1",
        "description": "The declared reference layer is more than one physical layer away from the signal layer.",
        "recommendation": "Confirm the intended stackup: return current needs a nearby reference plane, and non-adjacent references need an explicit justification.",
    },
    "RP-E1-109": {
        "group": "E1", "title": "Assignment evidence is bound to a different snapshot",
        "severity": "info", "determinism": "unknown", "family": "R5",
        "description": "reference_assignment evidence carries a source_snapshot different from the audited project snapshot.",
        "recommendation": "Re-export the assignment evidence against the current snapshot; do not reuse stale evidence.",
    },
    "RP-E1-110": {
        "group": "E1", "title": "Conflicting reference assignments",
        "severity": "error", "determinism": "proven", "family": "R1",
        "description": "Two or more assignments that match the same segment declare different reference layer/net pairs.",
        "recommendation": "Resolve the conflict explicitly; the auditor does not pick a winner.",
    },
    "RP-E1-111": {
        "group": "E1", "title": "Missing reference assignment",
        "severity": "info", "determinism": "unknown", "family": "R1",
        "description": "No reference_assignment matches the segment, so its reference plane is undeclared.",
        "recommendation": "Declare the intended reference layer and net for each signal segment.",
    },
    "RP-E1-112": {
        "group": "E1", "title": "Nearest-reference judgement impossible (thickness missing)",
        "severity": "info", "determinism": "unknown", "family": "R1",
        "description": "Multiple reference candidates exist but dielectric thickness is missing, so the nearer plane cannot be established.",
        "recommendation": "Declare dielectric thickness between copper layers, or declare the intended reference directly.",
    },

    # ------------------------------------------------------------- E2 planes
    "RP-E2-201": {
        "group": "E2", "title": "Signal crosses a gap between different reference nets (plane split)",
        "severity": "error", "determinism": "proven", "family": "R2",
        "description": "The signal projection passes over a region where reference copper exists on both sides but the nets differ, i.e. the return path must cross a split.",
        "recommendation": "Re-route or move the reference split so the signal stays over one reference net; do not rely on a nearby via to repair a split crossing.",
    },
    "RP-E2-202": {
        "group": "E2", "title": "Void/hole in reference copper under the signal",
        "severity": "error", "determinism": "proven", "family": "R2",
        "description": "The signal projection crosses a void or hole that belongs to the same reference copper region.",
        "recommendation": "Move the void/antipad or the signal so the projection stays over continuous reference copper.",
    },
    "RP-E2-203": {
        "group": "E2", "title": "Gap between same-net reference copper polygons",
        "severity": "warning", "determinism": "potential", "family": "R2",
        "description": "Reference copper of the correct net has a geometric gap under the signal; whether the two polygons are electrically joined elsewhere is not provable from this geometry.",
        "recommendation": "Close the gap or provide connectivity evidence (same filled polygon/island with proven stitch); geometry alone cannot prove the join.",
    },
    "RP-E2-204": {
        "group": "E2", "title": "Reference copper ends under the signal (copper/plane edge)",
        "severity": "error", "determinism": "proven", "family": "R2",
        "description": "The signal projection runs off the edge of the available reference copper, leaving no return plane on one side.",
        "recommendation": "Extend the reference copper or move the signal inward; keep a declared corridor from plane edges.",
    },
    "RP-E2-205": {
        "group": "E2", "title": "No reference copper under the signal projection",
        "severity": "error", "determinism": "proven", "family": "R2",
        "description": "No reference copper of the declared net covers the signal projection at all.",
        "recommendation": "Correct the declared reference or add the missing reference copper.",
    },
    "RP-E2-206": {
        "group": "E2", "title": "Reference edge corridor insufficient under the signal",
        "severity": "warning", "determinism": "proven", "family": "R2",
        "description": "The projection stays on copper, but the distance from the trace edge to the reference-copper boundary is smaller than the declared check corridor.",
        "recommendation": "Widen the reference copper or move the trace away from the plane edge according to the interface requirement.",
    },
    "RP-E2-207": {
        "group": "E2", "title": "Same-net copper polygons touch or nearly touch",
        "severity": "info", "determinism": "unknown", "family": "R5",
        "description": "Two same-net copper polygons are adjacent/touching or separated by a micro-gap; geometry cannot prove the electrical join.",
        "recommendation": "Provide filled-copper connectivity evidence (same connectivity island from the fill engine) instead of assuming the polygons are joined.",
    },
    "RP-E2-208": {
        "group": "E2", "title": "Coverage checked only under a declared idealization",
        "severity": "info", "determinism": "potential", "family": "R5",
        "description": "Coverage was evaluated against ideal_plane/declared geometry rather than actual filled copper.",
        "recommendation": "Re-run with actual fill copper before treating coverage as proven.",
    },
    "RP-E2-209": {
        "group": "E2", "title": "Narrow reference corridor relative to declared threshold",
        "severity": "warning", "determinism": "proven", "family": "R2",
        "description": "The measured reference-copper corridor under the signal is below the declared threshold at one or more intervals.",
        "recommendation": "Widen the reference copper or adjust the declared corridor with interface-specific evidence.",
    },

    # --------------------------------------------------------- E3 transitions
    "RP-E3-301": {
        "group": "E3", "title": "Transition via is not present in the via set",
        "severity": "error", "determinism": "unknown", "family": "R3",
        "description": "transitions[].via does not match any vias[] object, so span/net/connection cannot be verified (evidence rejected, not reused).",
        "recommendation": "Re-export the transition via with the current snapshot; do not assume the layer change is implemented.",
    },
    "RP-E3-302": {
        "group": "E3", "title": "Transition via net does not match the signal net",
        "severity": "error", "determinism": "proven", "family": "R3",
        "description": "The via declared for the signal layer change carries a different net.",
        "recommendation": "Correct the via/net binding before relying on the transition.",
    },
    "RP-E3-303": {
        "group": "E3", "title": "Transition via span does not cover the layer change",
        "severity": "error", "determinism": "proven", "family": "R3",
        "description": "layer_from..layer_to is physically wider than the declared via span (e.g. a blind via that stops short).",
        "recommendation": "Use a via whose physical span covers both layers, or remove the claimed transition.",
    },
    "RP-E3-304": {
        "group": "E3", "title": "Reference net changes at the layer transition",
        "severity": "warning", "determinism": "potential", "family": "R3",
        "description": "The reference plane net changes across the transition (e.g. GND to a power net); a GND return via alone is not a valid fix.",
        "recommendation": "Provide an interface-justified return bridge (decoupling capacitor with declared endpoints, evidence and applicable frequency range) or re-plan the stackup.",
    },
    "RP-E3-305": {
        "group": "E3", "title": "No return-path candidate declared at the transition",
        "severity": "warning", "determinism": "unknown", "family": "R3",
        "description": "No candidate_return_vias are declared for a genuine layer/reference change, so return continuity is unproven.",
        "recommendation": "Declare the stitching/return vias (or capacitor bridge) with span and connection evidence; a nearby same-net via is not proof.",
    },
    "RP-E3-306": {
        "group": "E3", "title": "Candidate return via does not span the reference layers",
        "severity": "error", "determinism": "proven", "family": "R3",
        "description": "A declared candidate return via's physical span does not reach the reference layer(s) involved.",
        "recommendation": "Use a via that physically spans the reference layer(s), or provide an alternative return structure.",
    },
    "RP-E3-307": {
        "group": "E3", "title": "Candidate return via has the wrong net",
        "severity": "error", "determinism": "proven", "family": "R3",
        "description": "A candidate return via carries a net other than the required reference net.",
        "recommendation": "Bind the return via to the correct reference net.",
    },
    "RP-E3-308": {
        "group": "E3", "title": "Candidate return via is missing or stale",
        "severity": "info", "determinism": "unknown", "family": "R3",
        "description": "A candidate via id is absent from the current via set, or its evidence is bound to a different snapshot.",
        "recommendation": "Re-export the via with current snapshot binding; stale evidence is rejected rather than reused.",
    },
    "RP-E3-309": {
        "group": "E3", "title": "Candidate return via has no proven connection to the reference copper",
        "severity": "warning", "determinism": "unknown", "family": "R3",
        "description": "The candidate via carries the right net and span, but the input does not show a pad/thermal/fill connection to the reference copper (island or connected-copper evidence).",
        "recommendation": "Supply fill/pad evidence linking the via to the reference copper; proximity and net name are not connection proof.",
    },
    "RP-E3-310": {
        "group": "E3", "title": "Potential return-path candidate (not proven)",
        "severity": "info", "determinism": "potential", "family": "R3",
        "description": "A candidate return structure has the declared net/span/connection evidence and lies within the declared distance threshold. This is a candidate, never a recovered return path.",
        "recommendation": "Keep as a candidate pending electrical verification; the report never asserts recovered_return_path=true.",
    },
    "RP-E3-311": {
        "group": "E3", "title": "Candidate return via is too far from the transition",
        "severity": "warning", "determinism": "proven", "family": "R3",
        "description": "The candidate return via is farther from the transition than the declared project threshold.",
        "recommendation": "Move the return via closer to the transition or justify a different threshold for this interface.",
    },
    "RP-E3-312": {
        "group": "E3", "title": "Nearby same-net via is not a return-path candidate",
        "severity": "info", "determinism": "unknown", "family": "R5",
        "description": "A via of the reference net lies near the transition but is not declared as a candidate and/or lacks connection evidence; proximity is not connection.",
        "recommendation": "Do not count it as a return path; either declare it with connection evidence or keep the transition unproven.",
    },
    "RP-E3-313": {
        "group": "E3", "title": "Decoupling capacitor bridge lacks required evidence",
        "severity": "warning", "determinism": "unknown", "family": "R3",
        "description": "A capacitor is proposed as a reference bridge but is missing endpoint nets, connection evidence, a frequency-applicability basis, or snapshot binding.",
        "recommendation": "Supply endpoints, connection/fill evidence and the applicable frequency/interface basis; a nearby capacitor does not prove high-frequency return.",
    },
    "RP-E3-314": {
        "group": "E3", "title": "Reference plane changes layer without a declared stitching structure",
        "severity": "warning", "determinism": "potential", "family": "R3",
        "description": "The reference layer changes at the transition (same net on another plane) and no candidate return structure bridges both reference layers.",
        "recommendation": "Add return/stitching vias spanning both reference layers, with connection evidence, or re-plan the transition.",
    },

    # ------------------------------------------------------------ E4 diff pair
    "RP-E4-401": {
        "group": "E4", "title": "Differential pair declaration is incomplete",
        "severity": "info", "determinism": "unknown", "family": "R4",
        "description": "A declared differential_pair does not contain exactly two declared signals.",
        "recommendation": "Declare both legs of the pair explicitly; membership is never guessed from P/N names.",
    },
    "RP-E4-402": {
        "group": "E4", "title": "Asymmetric reference-plane risk between differential legs",
        "severity": "error", "determinism": "proven", "family": "R4",
        "description": "One leg crosses a reference void/split/edge that the other leg does not, so the two legs do not share the same return environment.",
        "recommendation": "Make the reference environment symmetric (both legs over solid copper) or re-route the offending leg.",
    },
    "RP-E4-403": {
        "group": "E4", "title": "Differential legs use different reference planes",
        "severity": "error", "determinism": "proven", "family": "R4",
        "description": "The pair's legs resolve to different reference layer/net pairs.",
        "recommendation": "Use one reference plane for both legs, or provide the interface justification for the asymmetry.",
    },
    "RP-E4-404": {
        "group": "E4", "title": "Asymmetric layer transitions between differential legs",
        "severity": "warning", "determinism": "proven", "family": "R4",
        "description": "The pair's legs have different transition layers/counts, so their reference changes are not symmetric.",
        "recommendation": "Make the layer transitions symmetric (same layers, same reference change) or justify.",
    },
    "RP-E4-405": {
        "group": "E4", "title": "Differential pair reference coverage is incomplete",
        "severity": "info", "determinism": "unknown", "family": "R4",
        "description": "At least one leg's reference coverage could not be checked, so pair symmetry is undecided.",
        "recommendation": "Complete the reference/intent data for both legs.",
    },
    "RP-E4-406": {
        "group": "E4", "title": "Differential legs look reference-symmetric",
        "severity": "info", "determinism": "proven", "family": "R4",
        "description": "Both legs resolve to the same reference environment with the same geometric risk pattern; this is a reference-environment observation only.",
        "recommendation": "No action from this check; impedance/skew are out of scope here.",
    },
    "RP-E4-407": {
        "group": "E4", "title": "External length/skew report ignored or stale",
        "severity": "info", "determinism": "unknown", "family": "R5",
        "description": "An external length-match report is referenced but its snapshot/hash does not bind to this audit, or it is cited read-only.",
        "recommendation": "Bind the external report to the same snapshot; a length/skew pass never proves impedance or reference integrity.",
    },

    # ------------------------------------------------- E5 scope and coverage
    "RP-E5-501": {
        "group": "E5", "title": "Signal has no segments",
        "severity": "warning", "determinism": "proven", "family": "R5",
        "description": "A declared signal contains no segments, so nothing can be checked for it.",
        "recommendation": "Export the routed segments or remove the empty signal declaration.",
    },
    "RP-E5-502": {
        "group": "E5", "title": "Unsupported geometry on the signal path",
        "severity": "info", "determinism": "unknown", "family": "R5",
        "description": "The path contains arcs/curves/complex copper declared unsupported by this version, so coverage is partial for that net.",
        "recommendation": "Keep the net incomplete; supply polygonal approximations with an explicit tolerance or extend the geometry support.",
    },
    "RP-E5-503": {
        "group": "E5", "title": "Reference coverage could not be checked for the segment",
        "severity": "info", "determinism": "unknown", "family": "R5",
        "description": "The segment length is accounted as unknown because reference intent, actual fill copper or supported geometry is missing.",
        "recommendation": "Complete the input for this segment; unknown length is not silently treated as checked or passing.",
    },
    "RP-E5-504": {
        "group": "E5", "title": "No auditable signal was found",
        "severity": "warning", "determinism": "proven", "family": "R5",
        "description": "The input declares no signal segments at all, so a pass verdict would be meaningless.",
        "recommendation": "Provide at least one target net/segment; an empty design cannot pass.",
    },
    "RP-E5-505": {
        "group": "E5", "title": "Segment layer is not a signal layer",
        "severity": "warning", "determinism": "proven", "family": "R1",
        "description": "A segment declared on a plane layer cannot be treated as a routed signal over a reference plane.",
        "recommendation": "Correct the segment layer or remove the segment from the audited signal set.",
    },
}

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def rule(rule_id):
    return RULES[rule_id]


def rules_for_group(group):
    return {rule_id: meta for rule_id, meta in RULES.items() if meta["group"] == group}
