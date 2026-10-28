"""Finding records, stable IDs and the audit status decision.

Every rule reports through :func:`make` so a finding always answers the same
questions: which rule fired, which objects are involved, what was measured,
what was required, in which unit, with which declared tolerance, on what
evidence, and what the user could change.  A rule that cannot measure a
required property reports ``kind='unknown'``; it never silently drops the check.
"""
from __future__ import annotations

import math

from . import geometry

#: Human-readable contract for each rule.  ``capability`` maps to G1-G5 in the
#: task contract; ``requirement`` is reproduced in ``explain`` output.
RULE_CATALOG = {
    'G1.BOARD_OUTLINE': {
        'capability': 'G1', 'title': 'Board outline is a valid closed recessed shape',
        'requirement': 'outer boundary and cut-outs are simple, non-overlapping '
                       'closed polygons and do not replace a concave outline by its bbox'},
    'G1.OBJECT_INSIDE_BOARD': {
        'capability': 'G1', 'title': 'Fixed body, shell and pads respect the board material',
        'requirement': 'a body must be inside board material unless an explicit '
                       'overhang rule says otherwise; pads must stay on material'},
    'G1.HOLE_EDGE': {
        'capability': 'G1', 'title': 'Mounting hole keeps material around its full diameter',
        'requirement': 'hole radius + declared tolerance + edge margin must fit inside '
                       'board material, including cut-outs'},
    'G1.HOLE_PLACEMENT': {
        'capability': 'G1', 'title': 'Hole centres satisfy declared position constraints',
        'requirement': 'hole centre and diameter tolerance stay inside board and do not '
                       'contradict another hole or fixed feature'},
    'G1.EDGE_OVERHANG': {
        'capability': 'G1', 'title': 'Edge connector overhang is explicit and bounded',
        'requirement': 'outside-board body is allowed only by an explicit rule with a '
                       'maximum overhang; it never becomes a general permission'},
    'G1.FIXED_OBJECT': {
        'capability': 'G1', 'title': 'Locked/fixed objects cannot be moved by planning',
        'requirement': 'locked or fixed objects keep their declared pose; membership in '
                       'movable and fixed is contradictory'},
    'G1.PAD_ON_BOARD': {
        'capability': 'G1', 'title': 'Declared pads remain on board material',
        'requirement': 'every declared pad shape is inside the board material; this is '
                       'not a copper clearance or electrical rule'},
    'G1.GEOMETRY_UNKNOWN': {
        'capability': 'G1', 'title': 'A required mechanical object has no usable geometry',
        'requirement': 'missing body/shell geometry is reported as unknown coverage; a '
                       'missing model is not evidence that no solid exists'},
    'G2.OPENING_REQUIRED': {
        'capability': 'G2', 'title': 'Interface that requires an opening has one',
        'requirement': 'requires_opening=true must reference an enclosure opening'},
    'G2.OPENING_ALIGN': {
        'capability': 'G2', 'title': 'Mating datum aligns with the enclosure opening',
        'requirement': 'in-plane offset between the connector mating datum and the opening '
                       'centre is within the declared alignment tolerance; package centre '
                       'is not the mating datum'},
    'G2.OPENING_ANGLE': {
        'capability': 'G2', 'title': 'Mating direction aligns with the opening normal',
        'requirement': 'angle between the declared mating axis and opening normal is within '
                       'the declared angular tolerance'},
    'G2.OPENING_FIT': {
        'capability': 'G2', 'title': 'Plug cross-section fits through the opening',
        'requirement': 'opening minimum width/height minus tolerance is at least the plug '
                       'envelope width/height plus declared clearance'},
    'G2.PLUG_BLOCKED': {
        'capability': 'G2', 'title': 'Plug insertion envelope is clear of solids',
        'requirement': 'the plug envelope must not intersect board material, enclosure '
                       'posts/ribs/walls or neighbouring components in 2.5D'},
    'G2.WALL_CROSSING': {
        'capability': 'G2', 'title': 'Insertion path crosses the cavity wall only at an opening',
        'requirement': 'a plug envelope crossing the cavity boundary must pass through the '
                       'interface opening projection'},
    'G2.PLUG_UNKNOWN': {
        'capability': 'G2', 'title': 'Plug envelope is not modelled',
        'requirement': 'without an explicit plug envelope no arbitrary plug or cable may be '
                       'declared to fit'},
    'G2.CABLE_UNKNOWN': {
        'capability': 'G2', 'title': 'Cable bend space is not modelled',
        'requirement': 'only the declared cable space can be checked; missing space leaves '
                       'the cable check unknown'},
    'G2.CABLE_BLOCKED': {
        'capability': 'G2', 'title': 'Declared cable space is free of solids',
        'requirement': 'declared cable space must not intersect board, posts, ribs, walls or '
                       'components; this does not prove a flexible cable can bend there'},
    'G2.BUTTON_CAP': {
        'capability': 'G2', 'title': 'Button cap fits and is reachable through the panel opening',
        'requirement': 'cap diameter fits the opening with declared clearance and cap height '
                       'minus panel thickness leaves the declared travel'},
    'G2.BUTTON_TRAVEL': {
        'capability': 'G2', 'title': 'Declared button travel is available',
        'requirement': 'protrusion beyond the panel must cover pre-travel plus travel plus '
                       'declared margin when those facts are declared'},
    'G2.LED_PIPE': {
        'capability': 'G2', 'title': 'LED light path fits the opening',
        'requirement': 'declared light pipe / LED envelope fits within the opening and is '
                       'not blocked by an opaque neighbouring solid'},
    'G3.SCREW_HEAD': {
        'capability': 'G3', 'title': 'Screw head and washer keep-out is clear',
        'requirement': 'declared head/washer envelope must not interfere with components or '
                       'enclosure solids; undeclared hardware is unknown'},
    'G3.TOOL_SPACE': {
        'capability': 'G3', 'title': 'Assembly tool envelope is explicitly modelled and clear',
        'requirement': 'a declared finite tool cylinder must be clear; there is no implicit '
                       'infinite tool cylinder'},
    'G3.POST_INTERFERENCE': {
        'capability': 'G3', 'title': 'Component/interface does not hit a post or rib',
        'requirement': 'projection and Z interval must both overlap for a solid collision'},
    'G3.MOUNT_ALIGN': {
        'capability': 'G3', 'title': 'Declared mounting hole aligns with its screw post',
        'requirement': 'hole centre relative to the post is within the declared position '
                       'tolerance and their Z ranges can meet'},
    'G3.KEEPOUT': {
        'capability': 'G3', 'title': 'Declared mechanical keep-out is respected',
        'requirement': 'hard keep-outs reject candidates; preferred keep-outs lower the '
                       'score but never turn into a manufacturing failure'},
    'G3.INSULATION': {
        'capability': 'G3', 'title': 'Declared insulation clearance is respected',
        'requirement': 'only the declared clearance between the named objects is checked; '
                       'no safety approval is implied'},
    'G4.COLLISION': {
        'capability': 'G4', 'title': 'Component bodies do not collide in 2.5D',
        'requirement': 'projection overlap is not enough: Z intervals must also overlap, '
                       'including board thickness and bottom-side coordinates'},
    'G4.ENCLOSURE_HEIGHT': {
        'capability': 'G4', 'title': 'Component fits between cavity floor and ceiling',
        'requirement': 'top/bottom component Z extremes stay inside the declared enclosure '
                       'cavity Z interval'},
    'G4.POST_COLLISION': {
        'capability': 'G4', 'title': 'Component does not collide with enclosure posts/ribs',
        'requirement': '2.5D projection plus Z interval test against each declared solid'},
    'G4.COURTYARD': {
        'capability': 'G4', 'title': 'Courtyard overlap is reported separately',
        'requirement': 'courtyard overlap is a placement/assembly-space advisory and is not '
                       'the same finding as a solid collision'},
    'G4.SERVICE_SPACE': {
        'capability': 'G4', 'title': 'Declared service space stays free',
        'requirement': 'components must not intrude into declared service volumes'},
    'G4.HEIGHT_UNKNOWN': {
        'capability': 'G4', 'title': 'Height evidence is missing',
        'requirement': 'a missing height contributes unknown coverage; it never counts as '
                       'zero height and never proves clearance'},
    'G4.BOARD_VOLUME': {
        'capability': 'G4', 'title': 'Board thickness volume is available',
        'requirement': 'bottom-side checks need a bounded board thickness; nominal-only '
                       'thickness cannot bound the board volume'},
    'G5.NO_CANDIDATE': {
        'capability': 'G5', 'title': 'No candidate satisfied the hard constraints',
        'requirement': 'every enumerated combination was checked by the independent audit '
                       'path; the search space may still be incomplete'},
    'G5.SEARCH_INCOMPLETE': {
        'capability': 'G5', 'title': 'Candidate search budget was exhausted',
        'requirement': 'budget exhaustion is reported as search_incomplete, never as proof '
                       'that no solution exists'},
    'G5.CONTRADICTION': {
        'capability': 'G5', 'title': 'Hard constraints contradict each other',
        'requirement': 'the specific pair of constraints/objects is named; a full minimal '
                       'unsatisfiable core is not claimed'},
    'G5.FIXED_UNCHANGED': {
        'capability': 'G5', 'title': 'Planner left fixed objects unchanged',
        'requirement': 'fixed and locked components/holes keep their before pose exactly'},
    'G5.CANDIDATE_UNVERIFIED': {
        'capability': 'G5', 'title': 'Candidate has residual unknown coverage',
        'requirement': 'a candidate is only_planned; unknown checks are listed and are not '
                       'silently treated as verified'},
}


def make(rule, kind, objects, message, *, severity='hard', location=None,
         measured=None, required=None, unit='mm', tolerance=None, evidence=(),
         suggestion=None, unknown_reason=None):
    if rule not in RULE_CATALOG:
        raise KeyError(f'unknown rule {rule!r}')
    if kind not in ('violation', 'unknown', 'advisory'):
        raise ValueError(f'finding kind must be violation/unknown/advisory, got {kind!r}')
    if severity not in ('hard', 'preferred', 'info'):
        raise ValueError(f'finding severity must be hard/preferred/info, got {severity!r}')
    if isinstance(objects, str):
        objects = [objects]
    location_value = None
    if location is not None:
        frame = location.get('frame', 'world')
        location_value = {'frame': frame}
        for key in ('x', 'y', 'z'):
            if key in location and location[key] is not None:
                value = float(location[key])
                if not math.isfinite(value):
                    raise ValueError('finding location must be finite')
                location_value[key] = value
        if 'object' in location:
            location_value['object'] = location['object']
    finding = {
        'rule': rule,
        'capability': RULE_CATALOG[rule]['capability'],
        'title': RULE_CATALOG[rule]['title'],
        'kind': kind,
        'severity': severity,
        'objects': [str(item) for item in objects],
        'message': message,
    }
    if location_value:
        finding['location'] = location_value
    if measured is not None:
        finding['measured'] = measured
    if required is not None:
        finding['required'] = required
    if unit is not None:
        finding['unit'] = unit if isinstance(unit, str) else unit[0]
        if not isinstance(unit, str):
            finding['unit_scale'] = unit[1]
    if tolerance is not None:
        finding['tolerance'] = tolerance
    if evidence:
        finding['evidence'] = list(evidence)
    if suggestion:
        finding['suggestion'] = suggestion
    if unknown_reason:
        finding['unknown_reason'] = unknown_reason
    return finding


def sort_key(finding):
    return (finding['rule'], tuple(finding['objects']), finding['message'],
            finding['kind'], finding['severity'])


def finalize(findings):
    """Sort and assign stable ``F####`` identifiers."""
    ordered = sorted(findings, key=sort_key)
    result = []
    for index, finding in enumerate(ordered, start=1):
        item = {'id': f'F{index:04d}'}
        item.update(finding)
        result.append(item)
    return result


def status_of(findings):
    hard_violation = any(item['kind'] == 'violation' and item['severity'] == 'hard'
                         for item in findings)
    if hard_violation:
        return 'fail'
    hard_unknown = any(item['kind'] == 'unknown' and item['severity'] == 'hard'
                       for item in findings)
    preferred = any(item['kind'] in ('violation', 'unknown')
                    and item['severity'] == 'preferred' for item in findings)
    if hard_unknown or preferred:
        return 'review'
    return 'pass'


def summarize(findings):
    counts = {'violation': 0, 'unknown': 0, 'advisory': 0}
    for item in findings:
        counts[item['kind']] = counts.get(item['kind'], 0) + 1
    return {
        'status': status_of(findings),
        'counts': counts,
        'hard_failures': sum(1 for item in findings
                             if item['kind'] == 'violation' and item['severity'] == 'hard'),
        'hard_unknown': sum(1 for item in findings
                            if item['kind'] == 'unknown' and item['severity'] == 'hard'),
        'preferred_issues': sum(1 for item in findings
                                if item['severity'] == 'preferred'),
    }


def coverage_block(findings):
    """Split unknown checks into the capability groups they leave unverified."""
    unknown = {}
    for item in findings:
        if item['kind'] != 'unknown':
            continue
        unknown.setdefault(item['capability'], []).append(item['id'])
    return {key: sorted(value) for key, value in sorted(unknown.items())}


def midpoint(points):
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def shape_location(shape_world, z=None, frame='world'):
    if not shape_world:
        return None
    point = midpoint(shape_world['polygon'])
    if point is None:
        return None
    location = {'frame': frame, 'x': point[0], 'y': point[1]}
    if z is not None:
        location['z'] = z
    return location


def dim_text(dimension):
    """Compact, deterministic text for a prescribed dimension."""
    if dimension is None:
        return None
    nominal = dimension.get('nominal')
    low = dimension.get('min')
    high = dimension.get('max')
    if low is not None and high is not None and abs(high - low) <= 1e-12:
        return nominal if nominal is not None else low
    return {'nominal': nominal, 'min': low, 'max': high}
